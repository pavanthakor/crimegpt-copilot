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
from functools import lru_cache
from pathlib import Path

from app.ai import rag
from app.ai.llm import call_llm

logger = logging.getLogger("crimegpt.legal")

# Curated pre-2024 concordance (BNS<->IPC, BNSS<->CrPC, BSA<->Evidence Act). This is a
# fixed published table, so a cross-reference is looked up here FIRST and only falls
# back to the LLM when a section is absent. app/ai/legal.py -> parents[3] = repo root.
_MAPPING_FILE = Path(__file__).resolve().parents[3] / "data" / "mappings" / "old_law_mapping.json"

SELECTION_SCHEMA = {
    "selected": [
        {
            # triggering_phrase FIRST, on purpose: the model fills JSON in field order, so
            # quoting the narrative before naming a section enforces the quote-first workflow
            # in _build_prompt and curbs the "name a section, then quote its definition" habit.
            "triggering_phrase": "exact run of words copied verbatim from the NARRATIVE (the "
            "complainant's own words) — never from a candidate section's legal definition",
            "act": "one of the candidate acts (BNS | BNSS | BSA)",
            "section_code": "must be one of the provided candidate section_codes",
            "reason": "short reason this quote proves this section",
            "confidence": "float 0.0-1.0",
            "cross_reference": (
                "the pre-2024 equivalent provision, or null. Object: "
                "{framework: 'IPC'|'CrPC'|'EVIDENCE_ACT', provision: 'e.g. 379', "
                "note: 'optional short note'}. Use null if you are not confident of the exact "
                "corresponding old-law section."
            ),
        }
    ]
}

# The only old-law frameworks a BNS/BNSS/BSA section can map back to. Anything else
# the model emits is discarded (conservative-null discipline).
_ALLOWED_FRAMEWORKS = {"IPC", "CRPC", "EVIDENCE_ACT"}
# Canonical display forms once validated.
_FRAMEWORK_CANON = {"IPC": "IPC", "CRPC": "CrPC", "EVIDENCE_ACT": "EVIDENCE_ACT"}

_SYSTEM = (
    "You are a legal assistant for Indian police working under the BNS, BNSS and BSA. "
    "You must be strictly grounded: only ever select from the candidate sections given to you."
)

# Complaints are written in everyday language ("the scooter was missing", "push it out
# and ride away") that shares almost no vocabulary with the bare-act text ("dishonestly",
# "moves that property"), so semantic retrieval on the raw narrative misses the correct
# offence. This system prompt drives a one-shot restatement into statutory terms whose
# ONLY use is to widen retrieval (see `expand_query` / `retrieve_offences_union`).
_EXPANSION_SYSTEM = (
    "You convert a police complaint written in everyday language into a SHORT list of the "
    "criminal offences it describes, phrased in formal statutory terms. Output only the "
    "offence phrases, comma-separated — no explanation, no section numbers, no punishments."
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


def expand_query(narrative: str) -> str | None:
    """Restate the complaint in statutory-offence terms to bridge the lay/legal vocabulary
    gap before retrieval.

    Returns a short comma-separated phrase, or None on ANY failure (so a broken/slow LLM
    degrades to raw-narrative retrieval rather than breaking analysis). The result is used
    ONLY to widen retrieval — it is never shown to the officer, never persisted, and never
    reaches the grounding validator (selections are still quoted from and validated against
    the raw narrative).
    """
    prompt = (
        "Restate the following complaint as a SHORT, comma-separated list of the criminal "
        "offences it describes, in formal legal terminology. Example output: 'theft of a "
        "motor vehicle from a public parking area; removal of a two-wheeler without the "
        "owner's consent'. Keep it under 30 words. Do NOT include section numbers, "
        "punishments or prose.\n\n"
        f'COMPLAINT:\n"""{narrative}"""'
    )
    try:
        out = call_llm(prompt, system=_EXPANSION_SYSTEM)
    except Exception as exc:  # noqa: BLE001 — expansion is best-effort; never fatal
        logger.warning("query expansion failed (%s); using raw-narrative retrieval only", exc)
        return None
    if not isinstance(out, str):
        return None
    out = out.strip()
    return out or None


def retrieve_offences_union(narrative: str, k: int = 12) -> tuple[list[dict], str | None]:
    """BNS offence candidates for the raw narrative UNIONED with an LLM statutory
    restatement, de-duplicated by (act, section_code).

    Expansion can only ADD candidates: raw-narrative hits are inserted first, so a section
    the raw query found is never displaced. Returns (candidates, expanded_query); the
    second element is None when expansion was skipped/failed and exists only for logging.
    """
    raw_hits = retrieve_offences(narrative, k=k)
    expanded = expand_query(narrative)

    by_key: dict[tuple[str, str], dict] = {}
    for h in raw_hits:
        by_key.setdefault((h["act"], str(h["section_code"])), h)

    if expanded:
        for h in retrieve_offences(expanded, k=k):
            by_key.setdefault((h["act"], str(h["section_code"])), h)

    candidates = list(by_key.values())
    logger.debug(
        "offence retrieval union: raw_query=%r expanded_query=%r raw_hits=%d union=%d",
        narrative[:160], expanded, len(raw_hits), len(candidates),
    )
    return candidates, expanded


def _format_candidates(candidates: list[dict]) -> str:
    lines = []
    for c in candidates:
        title = c.get("title", "")
        text = (c.get("text") or "").strip().replace("\n", " ")
        snippet = text[:300] + ("..." if len(text) > 300 else "")
        lines.append(f"- act={c['act']} section_code={c['section_code']} | {title}\n    {snippet}")
    return "\n".join(lines)


def _build_prompt(narrative: str, candidates: list[dict], language: str) -> str:
    # QUOTE-FIRST design: previously the model chose a section and then hunted for a phrase,
    # which on plain-language complaints (hurt, intimidation) led it to quote the candidate's
    # statutory DEFINITION — the grounding validator then rejected it and the case fell to
    # no_grounded_match. Here the model must first COPY the complainant's own words, then label
    # each quote with a section. Grounding is UNCHANGED; only the prompt/field order changed.
    return (
        f"You are mapping a crime complaint (language: {language}) to the legal sections that "
        "apply. Below is the NARRATIVE (the complainant's own account) followed by a list of "
        "CANDIDATE sections retrieved from the bare acts.\n\n"
        "WORK IN THIS ORDER — quote first, label second. Do NOT pick a section and then hunt "
        "for words to justify it:\n"
        "  STEP 1 — Read the NARRATIVE and find the specific runs of words where the complainant "
        "describes WHAT HAPPENED: the acts, threats, injuries, losses, deception. These are the "
        "complainant's OWN plain words — e.g. \"hit me hard on my head\", \"he will beat me and "
        "my workers if I stop paying\", \"collected the day's cash ... but never deposited it\", "
        "\"our television ... missing\".\n"
        "  STEP 2 — For each such quote, choose the ONE candidate section whose offence that "
        "quote proves. Pick section_code ONLY from the CANDIDATE SECTIONS list — never invent "
        "one. If several candidates could fit, choose the one that MOST SPECIFICALLY matches the "
        "facts (e.g. property entrusted to a person who then keeps it is criminal breach of "
        "trust, not ordinary theft; entry into a house at night to take things is house-breaking "
        "as well as theft).\n\n"
        "For each (quote, section) output an object with:\n"
        "  - triggering_phrase: the exact words copied character-for-character FROM THE NARRATIVE. "
        "It MUST appear verbatim in the narrative below. It is the COMPLAINANT'S description of "
        "the event — NEVER the wording of a candidate section's legal definition. Statutory "
        "phrases like 'voluntarily causing hurt', 'criminal intimidation', 'dishonestly', 'means "
        "of transportation' do NOT appear in the narrative; if you are about to quote wording "
        "like that, STOP and quote the everyday sentence in the narrative that shows the same "
        "thing. If no narrative phrase proves a section, DROP that section.\n"
        "  - act, section_code: from the candidate list.\n"
        "  - reason: a short reason the quote proves this section.\n"
        "  - confidence: 0.0-1.0.\n"
        "  - cross_reference: the PRE-2024 provision this new-law section replaces. The BNS, BNSS "
        "and BSA (2023) renumbered most pre-existing offences from the IPC / CrPC / Indian Evidence "
        "Act, so the great majority of sections HAVE a direct old-law equivalent — provide it. "
        "Format: {\"framework\": \"IPC\" | \"CrPC\" | \"EVIDENCE_ACT\", \"provision\": "
        "\"<old section number>\", \"note\": \"<optional <=6-word note>\"}. Well-known examples: "
        "BNS 303 (theft) -> IPC 379; BNS 305 (theft in dwelling) -> IPC 380; BNS 318 (cheating) -> "
        "IPC 420; BNS 115 (voluntarily causing hurt) -> IPC 323; BNS 309 (robbery) -> IPC 392. "
        "Set cross_reference to null ONLY for a genuinely NEW offence with no pre-2024 predecessor. "
        "Do NOT guess a random number — give the established equivalent or null.\n\n"
        f"NARRATIVE (quote triggering_phrase from HERE — the complainant's own words):\n"
        f"\"\"\"{narrative}\"\"\"\n\n"
        f"CANDIDATE SECTIONS (choose section_code from HERE; do NOT quote their text):\n"
        f"{_format_candidates(candidates)}\n"
    )


def _sanitize_cross_reference(raw) -> dict | None:
    """Coerce the model's `cross_reference` to a trusted shape or drop it.

    Cross-refs are NOT corpus-grounded (the bare-act corpus has no IPC/CrPC mapping),
    so they are LLM-generated and treated conservatively: keep one only when it names a
    known old-law framework AND a non-empty provision. Anything else becomes null, so a
    section renders without a cross-ref rather than with a fabricated one.
    """
    if not isinstance(raw, dict):
        return None
    # Guard against literal None -> "None" (str(None) is truthy) for every field.
    fw_raw = raw.get("framework")
    fw = "" if fw_raw is None else str(fw_raw).strip().upper().replace(".", "").replace(" ", "_")
    if fw == "INDIAN_PENAL_CODE":
        fw = "IPC"
    if fw in ("CR_PC", "CRPC", "CR_P_C"):
        fw = "CRPC"
    if fw not in _ALLOWED_FRAMEWORKS:
        return None
    prov_raw = raw.get("provision")
    provision = "" if prov_raw is None else str(prov_raw).strip()
    if not provision or provision.lower() == "none":
        return None
    note_raw = raw.get("note")
    note = "" if note_raw is None else str(note_raw).strip()
    if note.lower() == "none":
        note = ""
    out = {"framework": _FRAMEWORK_CANON[fw], "provision": provision}
    if note:
        out["note"] = note
    return out


@lru_cache(maxsize=1)
def _load_mapping() -> dict:
    """Load the curated concordance once. Missing/broken file -> empty table (the
    resolver then just falls back to the AI path), never a hard failure."""
    try:
        data = json.loads(_MAPPING_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:  # noqa: BLE001
        logger.warning("cross-reference mapping unavailable (%s); using AI fallback only", exc)
        return {}
    # Keep only the act tables (drop `_meta` and any other bookkeeping keys).
    return {act: data[act] for act in ("BNS", "BNSS", "BSA") if isinstance(data.get(act), dict)}


def mapping_size() -> int:
    """Total number of curated (act, section_code) mappings — for logs/diagnostics."""
    return sum(len(tbl) for tbl in _load_mapping().values())


def lookup_curated(act: str, code: str) -> dict | None:
    """Deterministic cross-reference from the curated table, or None if absent."""
    entry = _load_mapping().get(act, {}).get(str(code))
    if not isinstance(entry, dict) or not entry.get("framework") or not entry.get("provision"):
        return None
    out = {
        "framework": str(entry["framework"]),
        "provision": str(entry["provision"]),
        "source": "curated",
    }
    title = str(entry.get("title", "")).strip()
    if title:
        out["title"] = title
    return out


def resolve_cross_reference(act: str, code: str, llm_raw) -> dict | None:
    """Resolution order (never a cross-reference without provenance):
      1. curated table  -> source="curated"
      2. sanitised LLM  -> source="ai_suggested"
      3. neither        -> None
    """
    curated = lookup_curated(act, code)
    if curated is not None:
        return curated
    ai = _sanitize_cross_reference(llm_raw)
    if ai is not None:
        return {**ai, "source": "ai_suggested"}
    return None


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
                "cross_reference": resolve_cross_reference(act, code, sel.get("cross_reference")),
            }
        )
    return validated, rejected


_REPAIR_SCHEMA = {"triggering_phrase": "a run of words copied verbatim from the narrative"}


def _repair_phrase(narrative: str, candidate: dict) -> str | None:
    """One-shot phrase repair for an already-chosen section.

    When a selection is grounding-rejected because its triggering_phrase is not in the
    narrative (the section itself is a valid candidate), ask the LLM ONCE for a corrected
    verbatim phrase supporting THAT SAME section — section choice is not re-opened. Returns a
    phrase that literally appears in the narrative, or None (then the caller drops it, as before).
    """
    title = candidate.get("title", "")
    code = candidate.get("section_code", "")
    definition = (candidate.get("text") or "").strip().replace("\n", " ")[:200]
    prompt = (
        "The offence below has already been identified as applicable to this complaint. Quote "
        "the SHORT run of words FROM THE NARRATIVE — the complainant's own description of what "
        "happened — that proves this offence. Copy it character-for-character from the narrative; "
        "it MUST appear verbatim there. Do NOT quote the legal definition; quote the "
        "complainant's plain words.\n\n"
        f"OFFENCE: section {code} — {title}\n"
        f"(definition, for your understanding only — do NOT quote it: {definition})\n\n"
        f"NARRATIVE:\n\"\"\"{narrative}\"\"\""
    )
    try:
        out = call_llm(prompt, system=_SYSTEM, json_schema=_REPAIR_SCHEMA)
    except Exception as exc:  # noqa: BLE001 — repair is best-effort; never fatal
        logger.warning("repair phrase call failed for section %s (%s)", code, exc)
        return None
    if not isinstance(out, dict):
        return None
    phrase = (out.get("triggering_phrase") or "").strip()
    if phrase and (phrase in narrative or phrase.lower() in narrative.lower()):
        return phrase
    return None


# Minimum retrieval similarity a validated section must clear to be kept. This is a
# RELEVANCE gate, not a grounding gate: the k=12 union window can admit a catch-all
# section (e.g. BNS 125 "act endangering life by a rash/negligent act") that is genuinely
# in the candidate set with a genuinely verbatim phrase, yet is only weakly related to the
# narrative — grounding cannot catch that. Empirically the correct charge retrieves well
# above this floor (case 1 BNS 305 ~0.39, case 2 BNS 303 ~0.47–0.49) while an off-topic
# catch-all on contentless input lands far below it (BNS 125 ~0.06); 0.25 sits comfortably
# in that gap (real cases clear by +0.14/+0.22, the catch-all is excluded by −0.19).
RELEVANCE_THRESHOLD = 0.25


def map_sections(narrative: str, language: str = "EN", k: int = 12) -> dict:
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
    candidates, expanded = retrieve_offences_union(narrative, k=k)
    logger.info(
        "retrieved %d BNS candidate sections (raw + %s expansion, k=%d)",
        len(candidates), "no" if expanded is None else "1", k,
    )

    # The expanded query only widened retrieval; the prompt and validator below still use
    # the RAW narrative, so triggering phrases are quoted from and checked against the
    # officer's own words — grounding discipline is unchanged.
    prompt = _build_prompt(narrative, candidates, language)
    llm_out = call_llm(prompt, system=_SYSTEM, json_schema=SELECTION_SCHEMA)

    if not isinstance(llm_out, dict):
        raise ValueError(f"expected dict from call_llm, got {type(llm_out)}")
    selections = llm_out.get("selected", [])
    logger.info("LLM returned %d raw selections", len(selections))

    validated, rejected = validate_selections(selections, candidates, narrative)

    # Repair pass: a selection rejected ONLY because its phrase was not verbatim (the section
    # itself IS a valid candidate) gets ONE shot at a corrected narrative phrase. Section choice
    # is never re-opened, hallucinated-section rejections are never repaired, and each section is
    # attempted at most once. Grounding is unchanged — the repaired phrase is re-validated the
    # same way, so a bad repair is still dropped.
    by_key = {(c["act"], str(c["section_code"])): c for c in candidates}
    attempted: set = set()
    resolved: set = set()
    still_rejected: list[dict] = []
    for rej in rejected:
        key = (rej.get("act", ""), str(rej.get("section_code", "")))
        if key in resolved:
            continue  # section already recovered via repair — drop the stale rejection
        if (rej.get("rejection_reason") != "triggering_phrase not found verbatim in narrative"
                or key in attempted or key not in by_key):
            still_rejected.append(rej)
            continue
        attempted.add(key)
        phrase = _repair_phrase(narrative, by_key[key])
        orig = next(
            (s for s in selections
             if s.get("act") == rej.get("act")
             and str(s.get("section_code")) == str(rej.get("section_code"))),
            {},
        )
        fixed, _ = validate_selections(
            [{"act": rej.get("act"), "section_code": rej.get("section_code"),
              "triggering_phrase": phrase or "", "reason": orig.get("reason", ""),
              "confidence": orig.get("confidence"),
              "cross_reference": orig.get("cross_reference")}],
            candidates, narrative,
        ) if phrase else ([], [])
        if fixed:
            validated.extend(fixed)
            resolved.add(key)
            logger.info("REPAIR ok: %s %s phrase corrected to %r", key[0], key[1], phrase)
        else:
            still_rejected.append(rej)
    rejected = still_rejected

    # Relevance floor — drop grounded-but-weakly-related sections (see RELEVANCE_THRESHOLD).
    # Uses the retrieval similarity score already carried on each candidate by rag.search().
    score_by_key = {(c["act"], str(c["section_code"])): c.get("score") for c in candidates}
    relevant: list[dict] = []
    for s in validated:
        score = score_by_key.get((s["act"], str(s["section_code"])))
        if score is None or score < RELEVANCE_THRESHOLD:
            logger.warning(
                "REJECT section %s %s — retrieval score %s below relevance threshold %.2f",
                s["act"], s["section_code"], score, RELEVANCE_THRESHOLD,
            )
            rejected.append(
                {
                    "act": s["act"],
                    "section_code": s["section_code"],
                    "triggering_phrase": s.get("triggering_phrase", ""),
                    "rejection_reason": "below relevance threshold",
                }
            )
        else:
            relevant.append(s)
    validated = relevant

    # De-duplicate by (act, section_code), keeping the highest-confidence instance. The LLM can
    # emit the same section several times (once per supporting phrase); the officer should see
    # each charge once. First-occurrence order is preserved; only the kept instance may change.
    deduped: dict[tuple, dict] = {}
    for s in validated:
        key = (s["act"], str(s["section_code"]))
        cur = deduped.get(key)
        if cur is None or (s.get("confidence") or 0) > (cur.get("confidence") or 0):
            deduped[key] = s
    validated = list(deduped.values())

    logger.info(
        "validated %d, rejected %d of %d selections",
        len(validated), len(rejected), len(selections),
    )
    return {
        "sections": validated,
        "status": "ok" if validated else "no_grounded_match",
        "rejected": rejected,
    }
