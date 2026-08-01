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
    if not transcript:
        raise ValueError("No conversation content to extract from")

    prompt = INTAKE_EXTRACTION_PROMPT.format(
        today=(today or date.today()).isoformat(),
        language=_LANG_NAME.get((lang or "en").lower(), "English"),
        conversation=transcript,
    )
    raw = call_llm(prompt, json_schema=INTAKE_EXTRACTION_SCHEMA, temperature=0.1)
    if not isinstance(raw, dict):
        raise ValueError("Extraction did not return a JSON object")

    persons = [p for p in (_clean_person(p) for p in raw.get("persons") or []) if p]
    items = [i for i in (_clean_item(i) for i in raw.get("seized_items") or []) if i]

    return {
        "case": _clean_case(raw.get("case")),
        "persons": persons,
        "seized_items": items,
        "reply": _text(raw.get("reply")) or "",
    }
