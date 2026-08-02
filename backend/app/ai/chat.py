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
from pathlib import Path

from app.ai.llm import call_llm
from app.ai.prompts import DOC_REQUEST_PROMPT, DOC_REQUEST_SCHEMA

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
