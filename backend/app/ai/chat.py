"""Case-chat routing: turn one officer message into an INTENT, and nothing else.

This module decides WHAT the officer asked for. It never carries out the request, never
touches the database and never writes a sentence the officer reads — the caller routes
the returned intent to an endpoint that already exists, and the UI phrases the answer in
the officer's language. Keeping classification and action apart is what lets the
confirmation gate sit between them.

TWO-STAGE, CHEAPEST FIRST:

1. An ALIAS TABLE, matched deterministically in all three languages. "prepare the remand
   application", "રિમાન્ડ અરજી", "रिमांड" all resolve with no model call at all — instant,
   free, and identical every time. This covers how officers actually phrase these
   requests, which is a small and highly repetitive set.

2. Only when the table finds nothing does a MODEL call run, and it may return one label
   out of a closed set (prompt H). Its answer is validated against the document registry,
   so a value that is not an exact registry key has no effect whatsoever.

AMBIGUITY IS AN ANSWER, NOT A PROBLEM. "custody" genuinely names two different documents
in Indian police practice — police custody is a REMAND application, judicial custody is a
CUSTODY_LETTER. The table maps that word to BOTH on purpose, so the officer is asked
which one they meant instead of being handed the wrong document. The same holds for a
bare "LERS".
"""
from __future__ import annotations

import importlib.util
import logging
import re
from datetime import date
from pathlib import Path

from app.ai.intake import _TEXT_THRESHOLD, _dt, _grounded, _match_tokens, _text
from app.ai.llm import call_llm
from app.ai.prompts import (
    DOC_REQUEST_PROMPT,
    DOC_REQUEST_SCHEMA,
    FIELD_ANSWER_PROMPT,
    FIELD_ANSWER_SCHEMA,
)

logger = logging.getLogger("crimegpt.chat")


def _load_registry() -> dict:
    """Load templates/_registry.py by path, the same way services.documents does.

    The registry is the single source of truth for which documents exist (CLAUDE.md §8);
    reading it here rather than restating the list means a document added or removed there
    changes what the chat will route to, with no second list to keep in step.
    """
    path = Path(__file__).resolve().parents[3] / "templates" / "_registry.py"
    spec = importlib.util.spec_from_file_location("doc_registry_chat", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.REGISTRY


VALID_DOC_TYPES = set(_load_registry())

# Substrings, lowercased, matched against the normalised message. Multi-word aliases are
# matched as phrases, so "police custody" scores REMAND without "custody" alone doing so.
# A word deliberately listed under two documents makes the request AMBIGUOUS, which asks.
_ALIASES: dict[str, list[str]] = {
    "SEIZURE_RECEIPT": [
        "seizure receipt", "seizure", "seized", "receipt", "if4", "if-4",
        "japti", "जब्ती", "जब्ती रसीद", "જપ્તી", "જપ્તી પહોંચ", "કબજે",
    ],
    "PANCHNAMA": [
        "panchnama", "panch nama", "panch", "पंचनामा", "પંચનામા", "પંચનામુ",
    ],
    "REMAND": [
        "remand", "police custody", "pc remand", "custody",
        "रिमांड", "पुलिस हिरासत", "રિમાન્ડ", "પોલીસ કસ્ટડી",
    ],
    "CUSTODY_LETTER": [
        "custody letter", "judicial custody", "jc letter", "court custody", "custody",
        "न्यायिक हिरासत", "अदालती हिरासत", "ન્યાયિક કસ્ટડી", "કોર્ટ કસ્ટડી",
    ],
    "CHARGESHEET": [
        "chargesheet", "charge sheet", "final form", "final report", "form i", "form 1",
        "आरोप पत्र", "आरोपपत्र", "चार्जशीट", "ચાર્જશીટ", "આરોપનામું", "આખરી અહેવાલ",
    ],
    "MEDICAL_LETTER": [
        "medical letter", "medical", "examination letter", "hospital letter",
        "मेडिकल", "चिकित्सा", "મેડિકલ", "તબીબી",
    ],
    "LERS_PRESERVATION_REQUEST": [
        "preservation", "preserve", "lers preservation", "data preservation", "lers",
        "संरक्षण", "સંરક્ષણ", "જાળવણી",
    ],
    "LERS_RECORDS_REQUEST": [
        "records request", "records disclosure", "disclosure", "lers records", "lers",
        "रिकॉर्ड", "अभिलेख", "રેકોર્ડ", "માહિતી માંગણી",
    ],
}

# ---------------------------------------------------------------------------
# Which missing document fields can actually be FILLED, and where the value lands.
#
# A document's required_fields are names in the RENDER CONTEXT, not columns. Working out
# what an officer can answer means tracing each one back through _build_context to the
# pool row it is derived from — and several trace back to nothing an officer can type:
#
#   sections_applied / acts_sections_line  come from ACCEPTED legal sections. The chat
#       must never create these. Accepting a section is the officer's reviewed decision in
#       the legal flow, and a chat that could add one would be authoring law.
#   io_name / sho_name                     come from user records, not case data.
#   panchnama_date, investigation_done,
#   grounds_for_custody, examination_purpose,
#   report_type                            are derived or boilerplate and never empty.
#
# What remains is the set below: real facts an officer can state, each landing in the pool
# through an endpoint that already exists. `target` says which one:
#   case   -> PATCH /api/cases/{id}
#   person -> POST  /api/cases/{id}/persons          (with the given role)
#   item   -> POST/PATCH /api/cases/{id}/seized-items
# ---------------------------------------------------------------------------
FILL_PLAN: dict[str, dict] = {
    "fir_number":       {"target": "case",   "field": "fir_number",        "type": "text"},
    "fir_date":         {"target": "case",   "field": "fir_date",          "type": "date"},
    "police_station":   {"target": "case",   "field": "police_station",    "type": "text"},
    "district":         {"target": "case",   "field": "district",          "type": "text"},
    # panchnama_place falls back to incident_location, which IS officer-supplied.
    "panchnama_place":  {"target": "case",   "field": "incident_location", "type": "text"},
    "accused_name":     {"target": "person", "role": "ACCUSED",            "type": "text"},
    "witnesses":        {"target": "person", "role": "WITNESS",            "type": "text"},
    "subject_name":     {"target": "person", "role": "VICTIM",             "type": "text"},
    "seized_items":     {"target": "item",   "field": "description",       "type": "text"},
    "seizure_datetime": {"target": "item",   "field": "seizure_datetime",  "type": "datetime"},
    "seizure_location": {"target": "item",   "field": "seizure_location",  "type": "text"},
}

# Missing fields the chat must NOT offer to fill, with the surface that owns them. The UI
# says so plainly rather than silently dropping them from the question.
NOT_FILLABLE: dict[str, str] = {
    "sections_applied": "legal",
    "acts_sections_line": "legal",
    "io_name": "profile",
    "sho_name": "profile",
}


def split_missing(missing: list[str]) -> dict[str, list[str]]:
    """Split a checklist into what the officer can answer here and what they cannot."""
    fillable, blocked, unknown = [], [], []
    for field in missing:
        key = (field or "").strip()
        if key in FILL_PLAN:
            fillable.append(key)
        elif key in NOT_FILLABLE:
            blocked.append(key)
        elif key:
            unknown.append(key)
    return {"fillable": fillable, "blocked": blocked, "unknown": unknown}


_WS = re.compile(r"\s+")


def _normalise(message: str) -> str:
    """Lowercase, collapse whitespace, and pad so word-boundary checks are simple."""
    return f" {_WS.sub(' ', (message or '').strip().lower())} "


def _alias_matches(message: str) -> list[str]:
    """Document types the message names, best first — THE MOST SPECIFIC PHRASE WINS.

    Scored by the length of the longest alias that matched, because a longer alias is a
    more specific phrase. "custody" alone is a real ambiguity and stays one; "judicial
    custody letter" is not, and must not be dragged into ambiguity by the bare "custody"
    it happens to contain. Only a genuine TIE — two documents matched with equal
    specificity — is reported as ambiguous.
    """
    text = _normalise(message)
    scores: dict[str, int] = {}
    for doc_type, aliases in _ALIASES.items():
        if doc_type not in VALID_DOC_TYPES:
            continue  # a doc type removed from the registry stops being routable
        matched = [len(alias) for alias in aliases if alias in text]
        if matched:
            scores[doc_type] = max(matched)
    if not scores:
        return []
    best = max(scores.values())
    return [doc_type for doc_type, score in scores.items() if score == best]


def _model_doc_type(message: str) -> str | None:
    """Ask the model for ONE label. Anything not an exact registry key is discarded."""
    try:
        raw = call_llm(
            DOC_REQUEST_PROMPT.format(message=message),
            json_schema=DOC_REQUEST_SCHEMA,
            temperature=0.0,
            max_tokens=64,
        )
    except Exception as exc:  # noqa: BLE001 — a routing failure must not break the chat
        logger.warning("chat: doc-type classification failed (%s); asking the officer", exc)
        return None
    if not isinstance(raw, dict):
        return None
    value = str(raw.get("doc_type") or "").strip().upper()
    if value in VALID_DOC_TYPES:
        return value
    if value and value != "NONE":
        logger.info("chat: discarding non-registry doc_type %r from model", value)
    return None


def classify_document_request(message: str) -> dict:
    """Which document is this officer asking for?

    Returns:
        {"intent": "GENERATE" | "AMBIGUOUS" | "UNKNOWN",
         "doc_type": str | None,      # set only when intent is GENERATE
         "candidates": list[str],     # set only when intent is AMBIGUOUS
         "source": "alias" | "model" | "none"}   # which stage decided, for the log
    """
    if not (message or "").strip():
        return {"intent": "UNKNOWN", "doc_type": None, "candidates": [], "source": "none"}

    hits = _alias_matches(message)
    if len(hits) == 1:
        return {"intent": "GENERATE", "doc_type": hits[0], "candidates": [], "source": "alias"}
    if len(hits) > 1:
        # Two documents fit the same words. Ask; never pick one and hope.
        logger.info("chat: ambiguous document request -> %s", hits)
        return {"intent": "AMBIGUOUS", "doc_type": None, "candidates": hits, "source": "alias"}

    doc_type = _model_doc_type(message)
    if doc_type:
        return {"intent": "GENERATE", "doc_type": doc_type, "candidates": [], "source": "model"}
    return {"intent": "UNKNOWN", "doc_type": None, "candidates": [], "source": "model"}


# ---------------------------------------------------------------------------
# Reading an officer's answer onto the fields that were asked for.
# ---------------------------------------------------------------------------
def extract_field_answers(answer: str, fields: list[str], today: date | None = None) -> dict:
    """Map a free-text reply onto the requested fields. Answers nothing it was not asked.

    Three filters, each closing a different failure:

      WHITELIST — only the fields actually asked for survive, so a model that decides to
      also fill in a police station nobody asked about has no way to deliver it.
      TYPE      — dates are coerced through the same parser intake uses; an uncoercible
      value becomes None rather than reaching a legal document as a raw string.
      GROUNDING — every value must be traceable to the words the officer just typed. This
      is what stops a plausible invention: the officer answering "the police station is
      Satellite" can set police_station, but a model volunteering "Naranpura" from nowhere
      cannot, because that word is not in their reply.

    A field the officer did not answer is simply absent. It stays empty, and the document
    goes on refusing to generate until they supply it.
    """
    asked = [f for f in fields if f in FILL_PLAN]
    if not asked or not (answer or "").strip():
        return {}

    try:
        raw = call_llm(
            FIELD_ANSWER_PROMPT.format(
                fields="\n".join(f"- {f}" for f in asked),
                answer=answer,
                today=(today or date.today()).isoformat(),
            ),
            json_schema=FIELD_ANSWER_SCHEMA,
            temperature=0.0,
            max_tokens=512,
        )
    except Exception as exc:  # noqa: BLE001 — a failed read must not break the chat
        logger.warning("chat: field-answer extraction failed (%s)", exc)
        return {}

    values = raw.get("values") if isinstance(raw, dict) else None
    if not isinstance(values, dict):
        return {}

    source_text = " ".join(_match_tokens(answer))
    source_tokens = set(source_text.split())

    out: dict[str, str] = {}
    for field in asked:                      # iterate the WHITELIST, not the model's keys
        value = _text(values.get(field))
        if value is None:
            continue
        if FILL_PLAN[field]["type"] in {"date", "datetime"}:
            # "yesterday" resolves to a date that appears nowhere in the reply, so dates
            # are type-checked rather than grounded — the coercion is the guard.
            coerced = _dt(value)
            if coerced:
                out[field] = coerced
            else:
                logger.info("chat: dropping uncoercible %s=%r", field, value)
            continue
        if not _grounded(value, source_text, source_tokens, _TEXT_THRESHOLD):
            logger.info("chat: dropping ungrounded answer %s=%r", field, value)
            continue
        out[field] = value
    return out
