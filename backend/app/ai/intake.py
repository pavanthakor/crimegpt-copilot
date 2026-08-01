"""Conversational intake extraction (CLAUDE.md §6 prompt G).

Turns an officer's free-text description of an incident into a STRUCTURED DRAFT shaped
like the existing Unified Case Data Pool (cases / persons / seized_items, §5). Nothing
here writes to the database — the draft is returned to the officer for review and is
only persisted when they confirm it (`app.api.intake`).

Two properties this module is responsible for:

1. PURITY. Intake extracts facts and decides nothing. It must not produce charges,
   BNS/BNSS/BSA sections or legal characterisation — that is a separate, RAG-grounded
   accept/reject flow. The prompt says so, but the guarantee here is STRUCTURAL:
   `_pick()` whitelists every key against the pool schema, so an invented "sections" or
   "charges" field is dropped before it can reach an officer. A prompt can be ignored
   by a 7B model; a whitelist cannot.

2. SHAPE SAFETY. A local model returns "35" for an age and "yesterday" for a date often
   enough that the caller cannot trust raw output. Every value is coerced to the type
   its pool column expects, and anything uncoercible becomes None rather than blowing up
   the request — a missing field is reviewable, a 500 is not.
"""
from __future__ import annotations

import logging
import re
from datetime import date, datetime

from app.ai.llm import call_llm
from app.ai.prompts import INTAKE_EXTRACTION_PROMPT, INTAKE_EXTRACTION_SCHEMA
from app.models.enums import PersonRole

logger = logging.getLogger("crimegpt.intake")

# The ONLY keys allowed out of extraction, per pool table. Anything else the model
# emits — most importantly a legal section or charge — is discarded (see PURITY above).
_CASE_KEYS = {
    "title",
    "incident_datetime",
    "incident_location",
    "complaint_narrative",
    "fir_number",
    "police_station",
    "district",
}
_PERSON_KEYS = {
    "role",
    "full_name",
    "alias",
    "father_name",
    "age",
    "gender",
    "address",
    "phone",
    "occupation",
}
_ITEM_KEYS = {
    "description",
    "quantity",
    "estimated_value",
    "seized_from_name",
    "seizure_datetime",
    "seizure_location",
}

_LANG_NAME = {"en": "English", "hi": "Hindi", "gu": "Gujarati"}
_ROLES = {r.value for r in PersonRole}

# Shown when the officer's message contains no incident to record. Written here rather
# than taken from the model: on meaningless input the model's own `reply` refers to the
# case it just invented ("Please provide the name of the shop"), which is worse than useless.
_NO_CONTENT_REPLY = {
    "en": (
        "I could not find any case details in that. Please describe what happened — "
        "who was involved, what was taken or done, and when and where."
    ),
    "hi": (
        "इसमें मुझे कोई केस विवरण नहीं मिला। कृपया बताइए क्या हुआ — कौन शामिल था, "
        "क्या लिया गया या किया गया, और कब और कहाँ।"
    ),
    "gu": (
        "એમાં મને કોઈ કેસ વિગત મળી નથી. કૃપા કરીને જણાવો શું થયું — કોણ સંડોવાયેલું હતું, "
        "શું લેવાયું કે કરવામાં આવ્યું, અને ક્યારે અને ક્યાં."
    ),
}


# ---------------------------------------------------------------------------
# Coercion helpers — every one returns None rather than raising.
# ---------------------------------------------------------------------------
def _text(value) -> str | None:
    """A trimmed non-empty string, else None. Also rejects the model's 'null'/'N/A'."""
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"null", "none", "n/a", "na", "-", "unknown"}:
        return None
    return text


def _int(value) -> int | None:
    if value is None:
        return None
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _float(value) -> float | None:
    if value is None:
        return None
    try:
        # Tolerate "₹45,000" / "45000 INR" — keep digits, separators and sign only.
        cleaned = "".join(ch for ch in str(value) if ch.isdigit() or ch in ".-")
        return float(cleaned) if cleaned not in {"", ".", "-"} else None
    except (TypeError, ValueError):
        return None


def _dt(value) -> str | None:
    """Normalise to an ISO 8601 string Pydantic will accept, else None.

    Returned as a STRING (not a datetime) because the draft round-trips through JSON to
    the officer's browser and back; the Pydantic request model parses it on commit.
    """
    text = _text(value)
    if text is None:
        return None
    text = text.replace("Z", "+00:00").replace("/", "-")
    try:
        return datetime.fromisoformat(text).isoformat()
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%Y-%m-%d %H:%M", "%d-%m-%Y %H:%M"):
        try:
            return datetime.strptime(text, fmt).isoformat()
        except ValueError:
            continue
    logger.info("intake: dropping unparseable datetime %r", text)
    return None


def _pick(raw, allowed: set[str]) -> dict:
    """Whitelist a model-returned object down to `allowed` keys. Non-dict -> {}."""
    if not isinstance(raw, dict):
        return {}
    dropped = set(raw) - allowed
    if dropped:
        # Worth seeing in the log: it is how we notice the model trying to volunteer
        # legal conclusions we deliberately refuse to carry.
        logger.info("intake: dropped non-pool keys from extraction: %s", sorted(dropped))
    return {k: raw[k] for k in raw if k in allowed}


# ---------------------------------------------------------------------------
# Grounding — the anti-hallucination guarantee.
#
# Handed meaningless input ("kll"), a 7B model does not refuse: it free-associates a
# complete, plausible case with invented names. The prompt now tells it to return
# nothing, but a prompt is a request. The GUARANTEE is that every extracted value must
# be traceable to words the officer actually wrote — the same discipline prompts B and C
# already apply to judgments and statutory ingredients, where a quote not found in its
# source is discarded.
#
# Matching is token-based, not exact-substring, because extraction legitimately reorders
# and lightly normalises ("his motorcycle, a red Honda Shine" -> "red Honda Shine
# motorcycle") and Gujarati carries case endings ("શાહે" for "શાહ"). A token counts as
# grounded if it appears in the source as a whole word, as a substring, or sharing a
# prefix with a source word.
#
# NOTE the source is the OFFICER's turns only. Grounding against the assistant's replies
# too would let a name the model invented on one turn validate itself on the next.
# ---------------------------------------------------------------------------
_WORD_RE = re.compile(r"[^\W_]+", re.UNICODE)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?।])\s+")

# A name must be near-fully accounted for; free text is allowed more slack because it is
# a restatement rather than a copy.
_NAME_THRESHOLD = 0.6
_TEXT_THRESHOLD = 0.5

# Copied verbatim per the prompt, so they can be grounded. incident_datetime is NOT in
# this list: "yesterday" legitimately resolves to a date that appears nowhere in the text.
_VERBATIM_CASE_FIELDS = ("incident_location", "police_station", "district", "fir_number")


def _match_tokens(text: str | None) -> list[str]:
    """Lowercased word tokens, script-agnostic (Latin, Devanagari, Gujarati)."""
    return [t.lower() for t in _WORD_RE.findall(text or "")]


def _grounded(value, source_text: str, source_tokens: set[str], threshold: float) -> bool:
    """True when enough of `value`'s tokens are traceable to the officer's words."""
    tokens = [t for t in _match_tokens(str(value or "")) if len(t) >= 2]
    if not tokens:
        return False
    hits = 0
    for token in tokens:
        if token in source_tokens or token in source_text:
            hits += 1
        elif any(s.startswith(token) or token.startswith(s) for s in source_tokens if len(s) >= 3):
            hits += 1
    return hits / len(tokens) >= threshold


def _dedupe(rows: list[dict], key) -> list[dict]:
    """Drop rows repeating an earlier key — the structural half of the repetition fix."""
    seen: set[str] = set()
    out: list[dict] = []
    for row in rows:
        identity = key(row)
        if identity:
            if identity in seen:
                logger.info("intake: dropping repeated entry %r", identity)
                continue
            seen.add(identity)
        out.append(row)
    return out


def _collapse_repeats(text: str | None) -> str | None:
    """Collapse a sentence the model emitted more than once (degenerate-loop output)."""
    if not text:
        return text
    kept: list[str] = []
    seen: set[str] = set()
    for sentence in _SENTENCE_SPLIT.split(text):
        identity = " ".join(_match_tokens(sentence))
        if identity:
            if identity in seen:
                continue
            seen.add(identity)
        kept.append(sentence)
    return " ".join(kept).strip() or None


def _empty_result(lang: str) -> dict:
    """A draft with nothing in it, plus the ask-for-details reply, in the officer's language."""
    return {
        "case": {
            "title": None,
            "incident_datetime": None,
            "incident_location": None,
            "complaint_narrative": None,
            "fir_number": None,
            "police_station": None,
            "district": None,
        },
        "persons": [],
        "seized_items": [],
        "reply": _NO_CONTENT_REPLY.get((lang or "en").lower(), _NO_CONTENT_REPLY["en"]),
    }


def _officer_text(messages: list[dict]) -> str:
    """Everything the OFFICER typed — the only admissible source for grounding."""
    return " ".join(
        _text(m.get("content")) or ""
        for m in messages
        if (m.get("role") or "").lower() != "assistant"
    ).strip()


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------
def _clean_case(raw) -> dict:
    picked = _pick(raw, _CASE_KEYS)
    return {
        "title": _text(picked.get("title")),
        "incident_datetime": _dt(picked.get("incident_datetime")),
        "incident_location": _text(picked.get("incident_location")),
        "complaint_narrative": _text(picked.get("complaint_narrative")),
        "fir_number": _text(picked.get("fir_number")),
        "police_station": _text(picked.get("police_station")),
        "district": _text(picked.get("district")),
    }


def _clean_person(raw) -> dict | None:
    picked = _pick(raw, _PERSON_KEYS)
    role = (_text(picked.get("role")) or "").upper()
    if role not in _ROLES:
        return None  # the prompt says to omit people whose role is unclear
    person = {
        "role": role,
        "full_name": _text(picked.get("full_name")),
        "alias": _text(picked.get("alias")),
        "father_name": _text(picked.get("father_name")),
        "age": _int(picked.get("age")),
        "gender": _text(picked.get("gender")),
        "address": _text(picked.get("address")),
        "phone": _text(picked.get("phone")),
        "occupation": _text(picked.get("occupation")),
    }
    # A person with no identifier at all is an empty row, not a record.
    if not person["full_name"] and not person["alias"]:
        return None
    return person


def _clean_item(raw) -> dict | None:
    picked = _pick(raw, _ITEM_KEYS)
    description = _text(picked.get("description"))
    if not description:
        return None  # a seized item IS its description
    return {
        "description": description,
        "quantity": _int(picked.get("quantity")),
        "estimated_value": _float(picked.get("estimated_value")),
        "seized_from_name": _text(picked.get("seized_from_name")),
        "seizure_datetime": _dt(picked.get("seizure_datetime")),
        "seizure_location": _text(picked.get("seizure_location")),
    }


def _conversation(messages: list[dict]) -> str:
    """Render the chat turns as a transcript for the prompt."""
    lines = []
    for m in messages:
        role = "OFFICER" if (m.get("role") or "").lower() != "assistant" else "CLERK"
        content = _text(m.get("content"))
        if content:
            lines.append(f"{role}: {content}")
    return "\n".join(lines)


def extract_draft(messages: list[dict], lang: str = "en", today: date | None = None) -> dict:
    """Extract a structured pool draft from the officer's chat turns.

    Args:
        messages: full conversation so far, [{role: "officer"|"assistant", content: str}].
        lang: "en" | "hi" | "gu" — the officer's language, for the narrative and reply.
        today: reference date for resolving "yesterday"/"last Tuesday" (defaults to today).

    Returns:
        {"case": {...}, "persons": [...], "seized_items": [...], "reply": str}
        — pool-shaped, type-coerced, and free of any legal characterisation.
    """
    transcript = _conversation(messages)
    officer_text = _officer_text(messages)
    if not transcript or not officer_text:
        # Nothing to work from. Answer directly instead of asking the model what a blank
        # page means — it costs 12s and invites exactly the invention we are guarding against.
        return _empty_result(lang)

    prompt = INTAKE_EXTRACTION_PROMPT.format(
        today=(today or date.today()).isoformat(),
        language=_LANG_NAME.get((lang or "en").lower(), "English"),
        conversation=transcript,
    )
    # Runaway guard ONLY — it buys no speed. Generation stops naturally well inside this
    # bound (measured: ~500 tokens English, ~850-1050 Gujarati for a 3-person, 1-item
    # draft; Gujarati script tokenises roughly twice as heavily as Latin). A tighter
    # bound is actively harmful: 1500 truncated a Gujarati reply mid-string, and broken
    # JSON costs a whole fix-up round trip, so capping near the real length is SLOWER
    # than not capping. 3000 leaves room for several accused and a long item list while
    # still bounding a pathological repetition loop instead of burning the 180s timeout.
    raw = call_llm(
        prompt, json_schema=INTAKE_EXTRACTION_SCHEMA, temperature=0.1, max_tokens=3000
    )
    if not isinstance(raw, dict):
        raise ValueError("Extraction did not return a JSON object")

    # Everything below is checked against what the officer actually wrote.
    source_text = " ".join(_match_tokens(officer_text))
    source_tokens = set(source_text.split())

    persons = [p for p in (_clean_person(p) for p in raw.get("persons") or []) if p]
    persons = [
        p for p in persons
        if _grounded(p["full_name"] or p["alias"], source_text, source_tokens, _NAME_THRESHOLD)
    ]
    persons = _dedupe(persons, lambda p: (p["full_name"] or p["alias"] or "").strip().lower())

    items = [i for i in (_clean_item(i) for i in raw.get("seized_items") or []) if i]
    items = [
        i for i in items
        if _grounded(i["description"], source_text, source_tokens, _TEXT_THRESHOLD)
    ]
    items = _dedupe(items, lambda i: i["description"].strip().lower())

    case = _clean_case(raw.get("case"))
    for field in _VERBATIM_CASE_FIELDS:
        if case[field] and not _grounded(case[field], source_text, source_tokens, _TEXT_THRESHOLD):
            logger.info("intake: dropping ungrounded %s=%r", field, case[field])
            case[field] = None
    case["complaint_narrative"] = _collapse_repeats(case["complaint_narrative"])

    # If NOTHING survived, the officer described no incident: return an empty draft and
    # ask them to, rather than handing back a case assembled out of nothing. The narrative
    # counts as content on its own (a vague but real report — "my house was broken into"
    # — names no one and lists no property), but only when it is itself traceable.
    narrative_grounded = _grounded(
        case["complaint_narrative"], source_text, source_tokens, _TEXT_THRESHOLD
    )
    if not (persons or items or any(case[f] for f in _VERBATIM_CASE_FIELDS) or narrative_grounded):
        logger.info("intake: no grounded content extracted; returning empty draft")
        return _empty_result(lang)

    return {
        "case": case,
        "persons": persons,
        "seized_items": items,
        "reply": _text(raw.get("reply")) or "",
    }
