"""Grounded landmark-judgment suggestion (CLAUDE.md §6-B, §4 Legal Section Intelligence).

Same shape as `app.ai.legal`, applied to case law instead of bare-act sections:

    1. RAG-retrieve the k most relevant judgments from the curated corpus.
    2. Ask the LLM to SELECT from those candidates only — never invent a case.
    3. HARD-VALIDATE: drop any judgment whose citation is not in the retrieved
       candidate set. Every rejection is logged and returned.

This matters more for case law than for sections: an LLM asked for "landmark
judgments" will happily produce a plausible-sounding case name with an invented
SCC citation, and a fabricated authority in a remand application is far worse
than no authority at all. The corpus is the only source of truth — nothing that
is not in it can ever be suggested.

The collection is SEPARATE from `legal_sections` so the two corpora never mix:
a judgment must never surface as a chargeable section, or vice versa.

Run as a script to ingest:
    python -m app.ai.judgments            # idempotent
    python -m app.ai.judgments --reset    # wipe and re-ingest
"""
from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from app.ai import rag
from app.ai.llm import call_llm
from app.ai.prompts import (
    JUDGMENTS_PROMPT,
    JUDGMENTS_SCHEMA,
    RELEVANCE_CHECK_PROMPT,
    RELEVANCE_CHECK_SCHEMA,
)

logger = logging.getLogger("crimegpt.judgments")

# Reuse rag's embedding model + Chroma client singletons (same store, own collection).
_REPO_ROOT = Path(__file__).resolve().parents[3]
DATA_FILE = _REPO_ROOT / "data" / "judgments" / "judgments.jsonl"
COLLECTION_NAME = "judgments"

_SYSTEM = (
    "You are a legal research assistant for Indian police. You must be strictly "
    "grounded: only ever cite judgments from the candidate list given to you. "
    "Never invent a case name or a citation."
)


def _collection():
    """Cosine-space judgments collection; created if absent."""
    return rag._client().get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


def _load_rows() -> list[dict]:
    if not DATA_FILE.exists():
        raise FileNotFoundError(f"Judgment corpus not found: {DATA_FILE}")
    rows = []
    with DATA_FILE.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


# ---------------------------------------------------------------------------
# Citation normalisation — the join key for grounding
# ---------------------------------------------------------------------------
def normalise_citation(citation: str) -> str:
    """Casefold and strip every non-alphanumeric character.

    "(2014) 8 SCC 273", "2014 8 SCC 273" and "(2014) 8 S.C.C. 273" all collapse to
    the same key, so a model that reformats punctuation is not wrongly rejected —
    while a genuinely different volume or page still fails to match.
    """
    return re.sub(r"[^a-z0-9]", "", (citation or "").lower())


# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------
def ingest(reset: bool = False) -> int:
    """Populate the judgments collection. Idempotent unless reset. Returns doc count."""
    if reset:
        try:
            rag._client().delete_collection(COLLECTION_NAME)
            logger.info("reset: deleted existing collection %r", COLLECTION_NAME)
        except Exception:  # noqa: BLE001 — absent collection is fine
            pass

    coll = _collection()
    rows = _load_rows()
    existing = coll.count()

    if existing >= len(rows) and not reset:
        logger.info("collection already populated (%d docs); skipping ingest", existing)
        return existing
    if existing and not reset:
        logger.warning("collection partially populated (%d/%d); rebuilding", existing, len(rows))
        rag._client().delete_collection(COLLECTION_NAME)
        coll = _collection()

    ids, documents, metadatas = [], [], []
    for r in rows:
        tags = r.get("relevance_tags", [])
        # Embed title + holding + tags: officers search by facts ("recovery from an
        # open place"), not by citation, so the holding text carries the signal.
        documents.append(
            f"{r['case_title']} ({r['citation']}, {r.get('court', '')} {r.get('year', '')})\n"
            f"{r.get('holding', '')}\nTopics: {', '.join(tags)}"
        )
        ids.append(normalise_citation(r["citation"]) or r["case_title"])
        metadatas.append(
            {
                "case_title": r["case_title"],
                "citation": r["citation"],
                "court": r.get("court", ""),
                "year": int(r.get("year") or 0),
                "holding": r.get("holding", ""),
                "relevance_tags": ", ".join(tags),  # Chroma metadata must be scalar
                "source_url": r.get("source_url", ""),
            }
        )

    logger.info("embedding %d judgments on CPU...", len(documents))
    coll.add(ids=ids, documents=documents, embeddings=rag._embed(documents),
             metadatas=metadatas)
    final = coll.count()
    logger.info("ingest complete: %d docs in %r", final, COLLECTION_NAME)
    return final


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------
def search(query: str, k: int = 8) -> list[dict]:
    """Return up to k candidate judgments most relevant to `query`."""
    coll = _collection()
    if coll.count() == 0:
        raise RuntimeError(
            "judgments collection is empty — run `python -m app.ai.judgments` first"
        )
    res = coll.query(
        query_embeddings=rag._embed([query]),
        n_results=min(k, coll.count()),
        include=["metadatas", "distances"],
    )
    out = []
    for meta, dist in zip(res["metadatas"][0], res["distances"][0]):
        out.append(
            {
                "case_title": meta.get("case_title", ""),
                "citation": meta.get("citation", ""),
                "court": meta.get("court", ""),
                "year": meta.get("year", 0),
                "holding": meta.get("holding", ""),
                "relevance_tags": [
                    t.strip() for t in (meta.get("relevance_tags") or "").split(",") if t.strip()
                ],
                "source_url": meta.get("source_url", ""),
                "score": round(1.0 - dist, 4),
            }
        )
    return out


def _format_candidates(candidates: list[dict]) -> str:
    lines = []
    for c in candidates:
        lines.append(
            f"- citation={c['citation']} | {c['case_title']} ({c['court']}, {c['year']})\n"
            f"    {c['holding']}"
        )
    return "\n".join(lines)


def _format_sections(accepted_sections: list[dict]) -> str:
    if not accepted_sections:
        return "(none accepted yet)"
    return "\n".join(
        f"- {s.get('act', '')} {s.get('section_code', '')} — {s.get('section_title', '')}"
        for s in accepted_sections
    )


# ---------------------------------------------------------------------------
# Validation — the grounding gate
# ---------------------------------------------------------------------------
def neutral_reason(holding: str) -> str:
    """The fallback shown when the model's own reasoning cannot be trusted.

    States the authority's proposition and stops, rather than asserting a link to
    the facts that we could not verify. Dull but never wrong.
    """
    return f"Relevant to: {holding}"


def validate_judgments(
    suggestions: list[dict],
    candidates: list[dict],
    verify_reason=None,
) -> tuple[list[dict], list[dict]]:
    """Split suggestions into (validated, rejected).

    A suggestion survives only if its citation matches one of the retrieved
    candidates (after normalisation). Surviving entries are rewritten from the
    CORPUS record — title, court, year, holding and source_url all come from our
    curated data, not from the model, so the officer never sees a model-authored
    summary of a real case.

    `relevance_reason` is the one field still authored by the model, and citation
    grounding says nothing about whether that reasoning is sound — a correctly
    cited case can carry an inverted reading of its own holding. `verify_reason`
    is an optional callable(reason, holding) -> bool; when it returns False the
    reason is replaced by `neutral_reason(holding)` and the entry is marked
    `reason_fallback`. Passing None skips the check, which keeps this function
    pure and unit-testable against a mocked response.
    """
    by_cit = {normalise_citation(c["citation"]): c for c in candidates}
    validated: list[dict] = []
    rejected: list[dict] = []
    seen: set[str] = set()

    for sug in suggestions:
        citation = (sug.get("citation") or "").strip()
        title = (sug.get("title") or sug.get("case_title") or "").strip()
        key = normalise_citation(citation)

        if not key or key not in by_cit:
            logger.warning(
                "REJECT ungrounded judgment %r (%s) — citation not in retrieved candidate set",
                title, citation or "no citation",
            )
            rejected.append(
                {
                    "title": title,
                    "citation": citation,
                    "rejection_reason": (
                        "citation not in retrieved candidate set (possibly fabricated)"
                    ),
                }
            )
            continue

        if key in seen:
            logger.info("skip duplicate judgment %s", citation)
            continue
        seen.add(key)

        cand = by_cit[key]
        holding = cand["holding"]
        reason = (sug.get("relevance_reason") or "").strip()
        fallback = False

        if not reason:
            reason, fallback = neutral_reason(holding), True
        elif verify_reason is not None and not verify_reason(reason, holding):
            logger.warning(
                "FALLBACK relevance_reason for %s — not entailed by the curated holding: %r",
                cand["citation"], reason,
            )
            reason, fallback = neutral_reason(holding), True

        validated.append(
            {
                "title": cand["case_title"],
                "citation": cand["citation"],
                "court": cand["court"],
                "year": cand["year"],
                # Corpus holding is the authoritative paraphrase — never the model's.
                "summary": holding,
                "relevance_reason": reason,
                "reason_fallback": fallback,
                "source_url": cand["source_url"],
                "relevance_tags": cand.get("relevance_tags", []),
                "score": cand.get("score"),
            }
        )

    return validated, rejected


def make_reason_verifier(narrative: str):
    """Build a callable(reason, holding) -> bool backed by a focused LLM check.

    Deliberately fail-closed: any error, malformed response or ambiguity returns
    False, which downgrades the reason to the neutral fallback. A dull-but-correct
    line costs the demo nothing; an invented legal proposition in a remand
    application costs a great deal.
    """

    def verify(reason: str, holding: str) -> bool:
        prompt = RELEVANCE_CHECK_PROMPT.format(
            holding=holding, narrative=narrative, reason=reason
        )
        try:
            out = call_llm(
                prompt,
                system=(
                    "You are a strict legal auditor. You answer only with the requested "
                    "JSON. When in doubt you answer supported=false."
                ),
                json_schema=RELEVANCE_CHECK_SCHEMA,
                temperature=0.0,
            )
        except Exception as exc:  # noqa: BLE001 — provider/JSON failure -> fail closed
            logger.warning("relevance check failed (%s); falling back to neutral", exc)
            return False
        if not isinstance(out, dict):
            return False
        supported = out.get("supported")
        if supported is not True:  # covers False, None, "false", missing
            logger.info("relevance check rejected: %s", out.get("problem", "")[:160])
            return False
        return True

    return verify


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def suggest_judgments(
    narrative: str, accepted_sections: list[dict] | None = None, k: int = 8
) -> dict:
    """Suggest landmark judgments grounded in the curated corpus.

    Returns {"judgments": [...], "status": "ok" | "no_grounded_match", "rejected": [...]}.
    `status == "no_grounded_match"` means nothing survived grounding — the UI should say
    so plainly rather than showing a fabricated authority.
    """
    accepted_sections = accepted_sections or []
    # Retrieve on the narrative plus the accepted charges: the sections steer retrieval
    # towards the procedural/evidentiary law that actually applies to this case.
    query = narrative
    if accepted_sections:
        query += "\n" + " ".join(
            f"{s.get('act', '')} {s.get('section_code', '')} {s.get('section_title', '')}"
            for s in accepted_sections
        )

    candidates = search(query, k=k)
    logger.info("retrieved %d candidate judgments", len(candidates))

    prompt = JUDGMENTS_PROMPT.format(
        narrative=narrative,
        sections=_format_sections(accepted_sections),
        candidates=_format_candidates(candidates),
    )
    llm_out = call_llm(prompt, system=_SYSTEM, json_schema=JUDGMENTS_SCHEMA)
    if not isinstance(llm_out, dict):
        raise ValueError(f"expected dict from call_llm, got {type(llm_out)}")

    suggestions = llm_out.get("judgments", [])
    logger.info("LLM returned %d raw judgment(s)", len(suggestions))

    validated, rejected = validate_judgments(
        suggestions, candidates, verify_reason=make_reason_verifier(narrative)
    )
    n_fallback = sum(1 for v in validated if v.get("reason_fallback"))
    logger.info(
        "validated %d (%d reason(s) downgraded to neutral), rejected %d of %d judgment(s)",
        len(validated), n_fallback, len(rejected), len(suggestions),
    )
    return {
        "judgments": validated,
        "status": "ok" if validated else "no_grounded_match",
        "rejected": rejected,
    }


if __name__ == "__main__":
    import argparse

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(description="Ingest landmark judgments into ChromaDB.")
    ap.add_argument("--reset", action="store_true", help="wipe and re-ingest")
    args = ap.parse_args()
    count = ingest(reset=args.reset)
    print(f"collection {COLLECTION_NAME!r} now holds {count} judgments at {rag.CHROMA_DIR}")
