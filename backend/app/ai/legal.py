"""Grounded legal section mapping (CLAUDE.md §6-A, §16 "model gives bad section").

Raw Qwen hallucinates section numbers (e.g. maps chain-snatching to a non-existent
"BNS 376"). This module grounds the mapping in the actual bare-act corpus:

    1. RAG-retrieve the k most relevant real sections for the narrative.
    2. Ask the LLM to SELECT from those candidates only — never invent a code —
       and quote the triggering phrase verbatim from the narrative.
    3. HARD-VALIDATE the output: drop any (act, section_code) not in the candidate
       set, and drop any triggering_phrase that does not literally appear in the
       narrative. Every rejection is logged.

The validator (`validate_selections`) is pure and side-effect free so it can be
unit-tested against a mocked LLM response.
"""
from __future__ import annotations

import json
import logging

from app.ai import rag
from app.ai.llm import call_llm

logger = logging.getLogger("crimegpt.legal")

SELECTION_SCHEMA = {
    "selected": [
        {
            "act": "one of the candidate acts (BNS | BNSS | BSA)",
            "section_code": "must be one of the provided candidate section_codes",
            "triggering_phrase": "exact substring quoted verbatim from the narrative",
            "reason": "short reason this section applies",
            "confidence": "float 0.0-1.0",
        }
    ]
}

_SYSTEM = (
    "You are a legal assistant for Indian police working under the BNS, BNSS and BSA. "
    "You must be strictly grounded: only ever select from the candidate sections given to you."
)


# ---------------------------------------------------------------------------
# Purpose-scoped retrieval — each legal question searches only its own act, so
# offence mapping is never polluted by procedural/evidentiary sections.
#   BNS  = substantive offences (charge mapping)
#   BNSS = criminal procedure  (arrest, remand, custody, search) — used later
#   BSA  = evidence law                                          — used later
# ---------------------------------------------------------------------------
def retrieve_offences(query: str, k: int = 8) -> list[dict]:
    """Candidate substantive-offence sections (BNS) for charge mapping."""
    return rag.search(query, k=k, act="BNS")


def retrieve_procedure(query: str, k: int = 8) -> list[dict]:
    """Candidate procedure sections (BNSS) — arrest/remand/custody/search."""
    return rag.search(query, k=k, act="BNSS")


def retrieve_evidence(query: str, k: int = 8) -> list[dict]:
    """Candidate evidence-law sections (BSA)."""
    return rag.search(query, k=k, act="BSA")


def _format_candidates(candidates: list[dict]) -> str:
    lines = []
    for c in candidates:
        title = c.get("title", "")
        text = (c.get("text") or "").strip().replace("\n", " ")
        snippet = text[:300] + ("..." if len(text) > 300 else "")
        lines.append(f"- act={c['act']} section_code={c['section_code']} | {title}\n    {snippet}")
    return "\n".join(lines)


def _build_prompt(narrative: str, candidates: list[dict], language: str) -> str:
    return (
        f"A crime complaint (language: {language}) is given below, followed by a list of CANDIDATE "
        "legal sections retrieved from the bare acts.\n\n"
        "Select ONLY the candidate sections that genuinely apply to this narrative. "
        "You MUST NOT invent a section number — only choose from the candidate section_codes below.\n\n"
        "For each selected section provide:\n"
        "  - triggering_phrase: a run of words copied character-for-character FROM THE NARRATIVE "
        "below (the complaint text). It MUST appear verbatim in that narrative. Do NOT paraphrase, "
        "do NOT copy the candidate section definitions, and do NOT invent words. If you cannot find "
        "a supporting phrase in the narrative itself, omit that section.\n"
        "  - reason: a short reason it applies.\n"
        "  - confidence: 0.0-1.0.\n\n"
        f"NARRATIVE (quote triggering_phrase from HERE):\n\"\"\"{narrative}\"\"\"\n\n"
        f"CANDIDATE SECTIONS (choose section_code from HERE):\n{_format_candidates(candidates)}\n"
    )


def validate_selections(
    selections: list[dict], candidates: list[dict], narrative: str
) -> tuple[list[dict], list[dict]]:
    """Split selections into (validated, rejected).

    A selection survives only if:
      * its (act, section_code) pair is one of the retrieved candidates, AND
      * its triggering_phrase literally appears in the narrative.

    Surviving selections are enriched with the candidate's title/citation.
    Rejected selections carry a `rejection_reason` so the UI/demo can show why
    a suggestion was dropped rather than silently swallowing it.
    """
    by_key = {(c["act"], str(c["section_code"])): c for c in candidates}
    narrative_lc = narrative.lower()
    validated: list[dict] = []
    rejected: list[dict] = []

    for sel in selections:
        act = sel.get("act", "")
        code = str(sel.get("section_code", ""))
        phrase = (sel.get("triggering_phrase") or "").strip()
        key = (act, code)

        if key not in by_key:
            logger.warning(
                "REJECT ungrounded section %s %s — not in retrieved candidate set", act, code
            )
            rejected.append(
                {
                    "act": act,
                    "section_code": code,
                    "triggering_phrase": phrase,
                    "rejection_reason": "not in retrieved candidate set (possibly hallucinated)",
                }
            )
            continue

        if not phrase or (phrase not in narrative and phrase.lower() not in narrative_lc):
            logger.warning(
                "REJECT section %s %s — triggering_phrase %r not found in narrative",
                act, code, phrase,
            )
            rejected.append(
                {
                    "act": act,
                    "section_code": code,
                    "triggering_phrase": phrase,
                    "rejection_reason": "triggering_phrase not found verbatim in narrative",
                }
            )
            continue

        cand = by_key[key]
        validated.append(
            {
                "act": act,
                "section_code": code,
                "section_title": cand.get("title", ""),
                "citation": cand.get("citation", ""),
                "triggering_phrase": phrase,
                "reason": sel.get("reason", ""),
                "confidence": sel.get("confidence"),
            }
        )
    return validated, rejected


def map_sections(narrative: str, language: str = "EN", k: int = 8) -> dict:
    """Grounded offence (BNS) charge mapping.

    Returns a UI-ready result:
        {
          "sections": [...],   # validated, grounded sections (empty if none survive)
          "status":   "ok" | "no_grounded_match",
          "rejected": [...],   # dropped suggestions + why (for review / demo)
        }

    `status == "no_grounded_match"` means nothing cleared grounding — the UI should
    show an explicit "no confident match — review manually" state instead of a
    fabricated section.
    """
    candidates = retrieve_offences(narrative, k=k)
    logger.info("retrieved %d BNS candidate sections", len(candidates))

    prompt = _build_prompt(narrative, candidates, language)
    llm_out = call_llm(prompt, system=_SYSTEM, json_schema=SELECTION_SCHEMA)

    if not isinstance(llm_out, dict):
        raise ValueError(f"expected dict from call_llm, got {type(llm_out)}")
    selections = llm_out.get("selected", [])
    logger.info("LLM returned %d raw selections", len(selections))

    validated, rejected = validate_selections(selections, candidates, narrative)
    logger.info(
        "validated %d, rejected %d of %d selections",
        len(validated), len(rejected), len(selections),
    )
    return {
        "sections": validated,
        "status": "ok" if validated else "no_grounded_match",
        "rejected": rejected,
    }
