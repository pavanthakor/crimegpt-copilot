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


# ---------------------------------------------------------------------------
# Questions the assistant can answer — a CLOSED SET, every one of them a lookup of
# something already stored. There is deliberately no kind for "is this a strong case",
# "is he guilty" or "what should I charge": those call for judgement, and the assistant
# has no label to put them under, so they come back UNKNOWN and are declined.
#
# Weak-charge alerts and judgment retrieval are absent on purpose too. They are live
# legal-reasoning endpoints, and routing a chat question into one would turn a record
# lookup into an analysis the officer never asked to run. They stay on the Legal tab.
# ---------------------------------------------------------------------------
QUERY_KINDS = (
    "EVIDENCE", "WITNESSES", "ACCUSED", "PEOPLE", "ITEMS",
    "SECTIONS", "DIARY", "DOCUMENTS", "STATEMENTS", "STATUS",
)

_QUERY_ALIASES: dict[str, list[str]] = {
    "EVIDENCE":   ["evidence", "exhibit", "सबूत", "साक्ष्य", "पुरावा", "પુરાવા", "સાબિતી"],
    "WITNESSES":  ["witness", "witnesses", "गवाह", "साक्षी", "સાક્ષી", "સાક્ષીઓ"],
    "ACCUSED":    ["accused", "suspect", "आरोपी", "आरोपित", "આરોપી"],
    "PEOPLE":     ["people", "persons", "everyone", "व्यक्ति", "लोग", "વ્યક્તિ", "લોકો"],
    "ITEMS":      ["seized items", "items seized", "property", "मुद्दामाल", "जब्त सामान",
                   "મુદ્દામાલ", "જપ્ત મુદ્દામાલ"],
    "SECTIONS":   ["charges", "charge", "sections", "section", "धारा", "धाराएं", "आरोप",
                   "કલમ", "કલમો", "આરોપ"],
    "DIARY":      ["diary", "case diary", "डायरी", "केस डायरी", "ડાયરી", "કેસ ડાયરી"],
    "DOCUMENTS":  ["documents", "which documents", "दस्तावेज", "दस्तावेज़", "દસ્તાવેજ", "દસ્તાવેજો"],
    "STATEMENTS": ["statements", "statement", "बयान", "कथन", "નિવેદન", "નિવેદનો"],
    "STATUS":     ["status", "case status", "स्थिति", "स्तिथि", "સ્થિતિ"],
}

# ---------------------------------------------------------------------------
# Asking for JUDGEMENT is not asking for a record.
#
# "what should I charge him with?" contains the word "charge"; "do you think the evidence
# is enough?" contains "evidence". Matched on topic alone, both look like lookups — but
# neither wants a lookup. They want the assistant to evaluate the case, and it must not,
# whatever vocabulary the question happens to carry.
#
# So this is checked BEFORE any alias, and it forces UNKNOWN. The markers are of register
# rather than subject: the officer addressing the assistant's opinion ("do you think",
# "what do you advise"), asking what they ought to do ("should I"), or asking for an
# assessment ("strong", "enough", "guilty", "hold up"). None of those is answerable from a
# stored record no matter which table matched.
#
# The bias is deliberately toward declining. Wrongly declining costs one rephrase;
# wrongly answering makes the assistant look like it assessed a criminal case.
# ---------------------------------------------------------------------------
_JUDGEMENT_MARKERS = (
    # asking for advice or an opinion
    "should i", "should we", "do you think", "what do you think", "your opinion",
    "advise", "advice", "recommend", "suggest i", "suggest we",
    # asking for an assessment or a prediction
    "strong case", "weak case", "is it enough", "is the evidence enough", "enough evidence",
    "hold up", "hold in court", "will this", "would this", "chances", "likely to",
    "guilty", "innocent", "convict", "acquit", "prove the case",
    # Hindi
    "क्या करूं", "क्या करना", "सलाह", "आपको क्या लगता", "क्या लगता है",
    "मजबूत", "कमजोर", "दोषी", "निर्दोष", "पर्याप्त",
    # Gujarati
    "શું કરું", "શું કરવું", "સલાહ", "તમને શું લાગે", "શું લાગે છે",
    "મજબૂત", "નબળો", "દોષિત", "નિર્દોષ", "પૂરતું",
)


def _asks_for_judgement(text: str) -> bool:
    """True when the message asks the assistant to evaluate, predict or advise."""
    return any(marker in text for marker in _JUDGEMENT_MARKERS)


_WS = re.compile(r"\s+")


def _normalise(message: str) -> str:
    """Lowercase, collapse whitespace, and pad so word-boundary checks are simple."""
    return f" {_WS.sub(' ', (message or '').strip().lower())} "


def _score_aliases(text: str, table: dict[str, list[str]], valid=None) -> tuple[list[str], int]:
    """Best-scoring labels in one table, and that score. THE MOST SPECIFIC PHRASE WINS.

    Scored by the length of the longest alias that matched, because a longer alias is a
    more specific phrase. "custody" alone is a real ambiguity and stays one; "judicial
    custody letter" is not, and must not be dragged into ambiguity by the bare "custody"
    it happens to contain. Only a genuine TIE is reported as ambiguous.
    """
    scores: dict[str, int] = {}
    for label, aliases in table.items():
        if valid is not None and label not in valid:
            continue  # a doc type removed from the registry stops being routable
        matched = [len(alias) for alias in aliases if alias in text]
        if matched:
            scores[label] = max(matched)
    if not scores:
        return [], 0
    best = max(scores.values())
    return [label for label, score in scores.items() if score == best], best


def _alias_matches(message: str) -> list[str]:
    """Document types the message names (kept for direct callers/tests)."""
    return _score_aliases(_normalise(message), _ALIASES, VALID_DOC_TYPES)[0]


def _model_labels(message: str) -> tuple[str | None, str | None]:
    """Ask the model for ONE label of each kind. Anything not in the closed set is dropped.

    This is the whole of the model's authority in a query: it may name a label, and the
    caller does the rest. It cannot write the answer, so it cannot interpret the case,
    speculate about it, or state law — there is no channel through which a sentence of its
    composition could reach the officer.
    """
    try:
        raw = call_llm(
            DOC_REQUEST_PROMPT.format(message=message),
            json_schema=DOC_REQUEST_SCHEMA,
            temperature=0.0,
            max_tokens=64,
        )
    except Exception as exc:  # noqa: BLE001 — a routing failure must not break the chat
        logger.warning("chat: classification failed (%s); asking the officer", exc)
        return None, None
    if not isinstance(raw, dict):
        return None, None

    doc = str(raw.get("doc_type") or "").strip().upper()
    kind = str(raw.get("query_kind") or "").strip().upper()
    if doc and doc != "NONE" and doc not in VALID_DOC_TYPES:
        logger.info("chat: discarding non-registry doc_type %r from model", doc)
    if kind and kind != "NONE" and kind not in QUERY_KINDS:
        logger.info("chat: discarding unknown query_kind %r from model", kind)
    return (
        doc if doc in VALID_DOC_TYPES else None,
        kind if kind in QUERY_KINDS else None,
    )


def classify_document_request(message: str) -> dict:
    """What is this officer asking for — a document prepared, or a fact read back?

    Both alias tables are scored, and THE MORE SPECIFIC MATCH WINS ACROSS THEM. That is
    what keeps "show me the seized items" a question (query alias "seized items", 12
    characters) while "generate the seizure receipt" stays a command (doc alias "seizure
    receipt", 15). Only when the two tie — or neither matches — does the model arbitrate.

    Returns:
        {"intent": "GENERATE" | "AMBIGUOUS" | "QUERY" | "UNKNOWN",
         "doc_type": str | None,      # set only when intent is GENERATE
         "query_kind": str | None,    # set only when intent is QUERY
         "candidates": list[str],     # set only when intent is AMBIGUOUS
         "source": "alias" | "model" | "none"}
    """
    blank = {"intent": "UNKNOWN", "doc_type": None, "query_kind": None,
             "candidates": [], "source": "none"}
    if not (message or "").strip():
        return blank

    text = _normalise(message)

    # Checked before anything else: a request for judgement is never a lookup, however
    # much of a lookup's vocabulary it borrows.
    if _asks_for_judgement(text):
        logger.info("chat: declining a request for judgement, not a record lookup")
        return {**blank, "source": "guard"}

    doc_hits, doc_score = _score_aliases(text, _ALIASES, VALID_DOC_TYPES)
    query_hits, query_score = _score_aliases(text, _QUERY_ALIASES)

    # A question beats a document request only by being MORE specific, and vice versa.
    if query_hits and query_score > doc_score and len(query_hits) == 1:
        return {"intent": "QUERY", "doc_type": None, "query_kind": query_hits[0],
                "candidates": [], "source": "alias"}
    if doc_hits and doc_score > query_score:
        if len(doc_hits) == 1:
            return {"intent": "GENERATE", "doc_type": doc_hits[0], "query_kind": None,
                    "candidates": [], "source": "alias"}
        # Two documents fit the same words. Ask; never pick one and hope.
        logger.info("chat: ambiguous document request -> %s", doc_hits)
        return {"intent": "AMBIGUOUS", "doc_type": None, "query_kind": None,
                "candidates": doc_hits, "source": "alias"}

    doc_type, query_kind = _model_labels(message)
    if doc_type:
        return {"intent": "GENERATE", "doc_type": doc_type, "query_kind": None,
                "candidates": [], "source": "model"}
    if query_kind:
        return {"intent": "QUERY", "doc_type": None, "query_kind": query_kind,
                "candidates": [], "source": "model"}
    return {**blank, "source": "model"}


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
