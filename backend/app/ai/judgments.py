"""Grounded landmark-judgment suggestion (CLAUDE.md §6-B, §4 Legal Section Intelligence).

Same shape as `app.ai.legal`, applied to case law instead of bare-act sections:

    1. RAG-retrieve the k most relevant judgments from the curated corpus.
    2. Ask the LLM to SELECT from those candidates only — never invent a case —
       and to QUOTE two spans rather than write prose: `holding_clause` from the
       curated holding and `case_fact` from the narrative.
    3. HARD-VALIDATE, mechanically: drop any judgment whose citation is not in the
       retrieved candidate set, and downgrade any whose quoted spans do not appear
       verbatim in their sources. Every rejection is logged and returned.

The relevance sentence is then composed in code from the two re-extracted spans,
so the model never authors a legal proposition — it only points at text we already
trust. This mirrors `triggering_phrase` in section mapping (app.ai.legal).

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
from app.ai.prompts import JUDGMENTS_PROMPT, JUDGMENTS_SCHEMA

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
    """One block per candidate, each field on its own labelled line.

    The citation gets a line to itself: an earlier single-line format
    ("citation=X | Title (Court, Year)") led the model to copy the whole line as
    the citation, which then failed the grounding gate.
    """
    blocks = []
    for i, c in enumerate(candidates, 1):
        blocks.append(
            f"[{i}]\n"
            f"citation: {c['citation']}\n"
            f"case: {c['case_title']} ({c['court']}, {c['year']})\n"
            f"holding: {c['holding']}"
        )
    return "\n\n".join(blocks)


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
def first_clause(text: str) -> str:
    """The leading clause of a holding — up to the first comma, semicolon or period."""
    text = (text or "").strip()
    cut = len(text)
    for sep in (", ", "; ", ". "):
        i = text.find(sep)
        if i != -1:
            cut = min(cut, i)
    return text[:cut].rstrip(" ,;.")


def neutral_reason(holding: str) -> str:
    """The fallback shown when a quoted span could not be verified.

    States the authority's leading proposition and stops, rather than asserting a
    link to the facts that we could not check. Dull but never wrong.
    """
    return f"Relevant to: {first_clause(holding)}."


def _norm_with_map(text: str) -> tuple[str, list[int]]:
    """Casefold and collapse whitespace, keeping a map back to original offsets.

    Lets us match a model-quoted span tolerantly (it may reflow whitespace or change
    case) while still re-extracting the ORIGINAL characters from the source, so the
    officer reads our curated text rather than the model's transcription of it.
    """
    out: list[str] = []
    idx: list[int] = []
    prev_space = False
    for i, ch in enumerate(text):
        if ch.isspace():
            if prev_space:
                continue
            out.append(" ")
            idx.append(i)
            prev_space = True
        else:
            out.append(ch.lower())
            idx.append(i)
            prev_space = False
    return "".join(out), idx


# Quote characters a model tends to wrap a copied span in — straight and smart,
# single and double. Stripped from the ENDS of a span (never the source) so
# '"in any building"' still matches `in any building` in the statute.
_EDGE_QUOTES = "\"'‘’“”«»`"


def extract_verbatim(span: str, source: str) -> str | None:
    """Return the ORIGINAL text of `span` as it appears in `source`, or None.

    Matching ignores case, whitespace runs, and quote characters the model may have
    wrapped around the span; everything else must match exactly, so a paraphrase, an
    added word or a stitched-together phrase all fail.
    """
    span = (span or "").strip().strip(_EDGE_QUOTES).strip()
    if not span or not source:
        return None
    needle, _ = _norm_with_map(span)
    needle = needle.strip()
    if not needle:
        return None
    hay, hay_idx = _norm_with_map(source)
    pos = hay.find(needle)
    if pos == -1:
        return None
    start = hay_idx[pos]
    end = hay_idx[pos + len(needle) - 1] + 1
    return source[start:end]


def compose_reason(holding_clause: str, case_fact: str) -> str:
    """Join the two verified spans with a fixed connective. No model prose."""
    hc = holding_clause.strip().rstrip(" ,;.")
    cf = case_fact.strip().rstrip(" ,;.")
    return f"{hc} — here, {cf}."


def validate_judgments(
    suggestions: list[dict], candidates: list[dict], narrative: str = ""
) -> tuple[list[dict], list[dict]]:
    """Split suggestions into (validated, rejected). Pure — no LLM, no I/O.

    Two mechanical gates, both cheap and deterministic:

    1. `citation` must match one of the retrieved candidates (normalised) — else the
       judgment is rejected outright as possibly fabricated.
    2. `holding_clause` must appear verbatim in that candidate's curated holding and
       `case_fact` verbatim in the narrative. Both spans are re-extracted from their
       SOURCES and joined in code by `compose_reason`. If either fails to match, the
       reason degrades to `neutral_reason(holding)` and the entry is flagged
       `reason_fallback` — the judgment is still shown, just without an unverified
       link to the facts.

    Everything an officer reads is therefore either curated corpus text or narrative
    text they wrote themselves. The model only chooses which spans to point at.
    """
    by_cit = {normalise_citation(c["citation"]): c for c in candidates}
    validated: list[dict] = []
    rejected: list[dict] = []
    seen: set[str] = set()

    def resolve(raw: str) -> str | None:
        """Normalised key of the candidate this citation refers to, or None.

        Falls back to a prefix match so a model that appends the case name to the
        citation still resolves — the citation itself is still one we retrieved, so
        the grounding guarantee is unchanged.
        """
        norm = normalise_citation(raw)
        if not norm:
            return None
        if norm in by_cit:
            return norm
        for cand_key in by_cit:
            if cand_key and norm.startswith(cand_key):
                return cand_key
        return None

    for sug in suggestions:
        citation = (sug.get("citation") or "").strip()
        title = (sug.get("title") or sug.get("case_title") or "").strip()
        key = resolve(citation)

        if key is None:
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

        # Gate 2: both quoted spans must exist verbatim in their sources.
        clause = extract_verbatim(sug.get("holding_clause", ""), holding)
        fact = extract_verbatim(sug.get("case_fact", ""), narrative)

        if clause and fact:
            reason, fallback = compose_reason(clause, fact), False
        else:
            missing = []
            if not clause:
                missing.append(f"holding_clause {sug.get('holding_clause', '')!r} not in holding")
            if not fact:
                missing.append(f"case_fact {sug.get('case_fact', '')!r} not in narrative")
            logger.warning(
                "FALLBACK relevance for %s — %s", cand["citation"], "; ".join(missing)
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

    validated, rejected = validate_judgments(suggestions, candidates, narrative)
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
