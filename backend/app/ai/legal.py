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
        "  - triggering_phrase: an EXACT substring copied word-for-word FROM THE NARRATIVE below "
        "(the complaint text). It must appear verbatim in the narrative. "
        "Do NOT quote the candidate section definitions — quote the complaint.\n"
        "  - reason: a short reason it applies.\n"
        "  - confidence: 0.0-1.0.\n\n"
        "Example: if the narrative says 'the accused snatched her purse', a valid "
        "triggering_phrase is \"snatched her purse\" (copied from the narrative), never the "
        "statutory definition of the section.\n\n"
        f"NARRATIVE (quote triggering_phrase from HERE):\n\"\"\"{narrative}\"\"\"\n\n"
        f"CANDIDATE SECTIONS (choose section_code from HERE):\n{_format_candidates(candidates)}\n"
    )


def validate_selections(
    selections: list[dict], candidates: list[dict], narrative: str
) -> list[dict]:
    """Drop any selection not grounded in both the candidate set and the narrative.

    A selection survives only if:
      * its (act, section_code) pair is one of the retrieved candidates, AND
      * its triggering_phrase literally appears in the narrative.

    Surviving selections are enriched with the candidate's title/citation/act_name.
    """
    by_key = {(c["act"], str(c["section_code"])): c for c in candidates}
    narrative_lc = narrative.lower()
    validated: list[dict] = []

    for sel in selections:
        act = sel.get("act", "")
        code = str(sel.get("section_code", ""))
        phrase = (sel.get("triggering_phrase") or "").strip()
        key = (act, code)

        if key not in by_key:
            logger.warning(
                "REJECT ungrounded section %s %s — not in retrieved candidate set", act, code
            )
            continue

        if not phrase or (phrase not in narrative and phrase.lower() not in narrative_lc):
            logger.warning(
                "REJECT section %s %s — triggering_phrase %r not found in narrative",
                act, code, phrase,
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
    return validated


def map_sections(narrative: str, language: str = "EN", k: int = 8) -> dict:
    """Full grounded pipeline. Returns {candidates, validated}."""
    candidates = rag.search(narrative, k=k)
    logger.info("retrieved %d candidate sections", len(candidates))

    prompt = _build_prompt(narrative, candidates, language)
    llm_out = call_llm(prompt, system=_SYSTEM, json_schema=SELECTION_SCHEMA)

    if not isinstance(llm_out, dict):
        raise ValueError(f"expected dict from call_llm, got {type(llm_out)}")
    selections = llm_out.get("selected", [])
    logger.info("LLM returned %d raw selections", len(selections))

    validated = validate_selections(selections, candidates, narrative)
    logger.info("validated %d / %d selections", len(validated), len(selections))
    return {"candidates": candidates, "validated": validated}
