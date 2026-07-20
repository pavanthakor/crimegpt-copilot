"""Legal RAG retrieval layer (CLAUDE.md §6 / §13).

Loads the BNS/BNSS/BSA bare-act sections into a PERSISTENT ChromaDB collection and
exposes `search()` for grounded section mapping. One chunk per section, embedded with
sentence-transformers `all-MiniLM-L6-v2` on CPU so the RTX 4060 stays free for Qwen.

Run as a script to ingest:
    python -m app.ai.rag            # idempotent — skips if already populated
    python -m app.ai.rag --reset    # wipe and re-ingest
"""
from __future__ import annotations

import os

# Force the torch backend in transformers; avoids a Keras 3 / TensorFlow import clash
# on machines that happen to have Keras installed. Must precede the imports below.
os.environ.setdefault("USE_TF", "0")
os.environ.setdefault("TRANSFORMERS_NO_ADVISORY_WARNINGS", "1")

import argparse
import json
import logging
from functools import lru_cache
from pathlib import Path

import chromadb
from sentence_transformers import SentenceTransformer

logger = logging.getLogger("crimegpt.rag")

# app/ai/rag.py -> parents[1]=app, parents[2]=backend, parents[3]=repo root
_APP_DIR = Path(__file__).resolve().parents[1]
_REPO_ROOT = Path(__file__).resolve().parents[3]

CHROMA_DIR = _APP_DIR / "storage" / "chroma"
DATA_FILE = _REPO_ROOT / "data" / "bns_bnss_bsa" / "all_sections.jsonl"
COLLECTION_NAME = "legal_sections"
EMBED_MODEL = "all-MiniLM-L6-v2"


# ---------------------------------------------------------------------------
# Lazily-loaded singletons (model + chroma client) — expensive to construct.
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def _model() -> SentenceTransformer:
    """all-MiniLM-L6-v2 pinned to CPU (keep GPU free for the LLM)."""
    logger.info("loading embedding model %s on CPU", EMBED_MODEL)
    return SentenceTransformer(EMBED_MODEL, device="cpu")


@lru_cache(maxsize=1)
def _client() -> chromadb.ClientAPI:
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    return chromadb.PersistentClient(path=str(CHROMA_DIR))


def _collection():
    """Cosine-space collection; created if absent."""
    return _client().get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )


def _embed(texts: list[str]) -> list[list[float]]:
    return _model().encode(texts, normalize_embeddings=True, show_progress_bar=False).tolist()


def _load_sections() -> list[dict]:
    if not DATA_FILE.exists():
        raise FileNotFoundError(f"Section corpus not found: {DATA_FILE}")
    rows = []
    with DATA_FILE.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------
def ingest(reset: bool = False) -> int:
    """Populate the collection. Idempotent: skips if already populated unless reset.

    Returns the final document count in the collection.
    """
    if reset:
        try:
            _client().delete_collection(COLLECTION_NAME)
            logger.info("reset: deleted existing collection %r", COLLECTION_NAME)
        except Exception:  # noqa: BLE001 — absent collection is fine
            pass

    coll = _collection()
    existing = coll.count()
    rows = _load_sections()

    if existing >= len(rows) and not reset:
        logger.info("collection already populated (%d docs); skipping ingest", existing)
        return existing

    if existing and not reset:
        # Partial/stale population — safest is a clean rebuild.
        logger.warning("collection partially populated (%d/%d); rebuilding", existing, len(rows))
        _client().delete_collection(COLLECTION_NAME)
        coll = _collection()

    ids, documents, metadatas = [], [], []
    for r in rows:
        act, code = r["act"], r["section_code"]
        title, text = r.get("title", ""), r.get("text", "")
        ids.append(f"{act}:{code}")
        documents.append(f"{act} Section {code} — {title}\n{text}")
        metadatas.append(
            {
                "act": act,
                "act_name": r.get("act_name", ""),
                "section_code": code,
                "title": title,
                "citation": r.get("citation", ""),
                "text": text,
            }
        )

    logger.info("embedding %d sections on CPU...", len(documents))
    # Batch to keep memory sane and give progress feedback.
    BATCH = 256
    for start in range(0, len(documents), BATCH):
        end = start + BATCH
        embs = _embed(documents[start:end])
        coll.add(
            ids=ids[start:end],
            documents=documents[start:end],
            embeddings=embs,
            metadatas=metadatas[start:end],
        )
        logger.info("  ingested %d/%d", min(end, len(documents)), len(documents))

    final = coll.count()
    logger.info("ingest complete: %d docs in %r", final, COLLECTION_NAME)
    return final


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------
def search(query: str, k: int = 8, act: str | None = None) -> list[dict]:
    """Return up to k candidate sections most relevant to `query`.

    Each result: {citation, act, section_code, title, text, score}.
    `score` is cosine similarity in [0, 1] (higher = more relevant).
    Optional `act` restricts to one of BNS / BNSS / BSA.
    """
    coll = _collection()
    if coll.count() == 0:
        raise RuntimeError("legal_sections collection is empty — run `python -m app.ai.rag` first")

    where = {"act": act} if act else None
    res = coll.query(
        query_embeddings=_embed([query]),
        n_results=k,
        where=where,
        include=["metadatas", "documents", "distances"],
    )

    metas = res["metadatas"][0]
    dists = res["distances"][0]
    out = []
    for meta, dist in zip(metas, dists):
        out.append(
            {
                "citation": meta.get("citation", ""),
                "act": meta.get("act", ""),
                "section_code": meta.get("section_code", ""),
                "title": meta.get("title", ""),
                "text": meta.get("text", ""),
                "score": round(1.0 - dist, 4),  # cosine distance -> similarity
            }
        )
    return out


def get_section(act: str, section_code: str) -> dict | None:
    """Fetch one section's exact corpus record by (act, section_code), or None.

    Direct id lookup (id == "ACT:CODE") — NOT a similarity search — so callers that
    already know the section (e.g. weak-charge review of an ACCEPTED charge) get its
    authoritative statutory text rather than the nearest embedding.
    Returns {citation, act, section_code, title, text} on hit.
    """
    res = _collection().get(ids=[f"{act}:{section_code}"], include=["metadatas"])
    metas = res.get("metadatas") or []
    if not metas:
        return None
    m = metas[0]
    return {
        "citation": m.get("citation", ""),
        "act": m.get("act", act),
        "section_code": m.get("section_code", section_code),
        "title": m.get("title", ""),
        "text": m.get("text", ""),
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Ingest BNS/BNSS/BSA sections into ChromaDB.")
    parser.add_argument("--reset", action="store_true", help="wipe and re-ingest")
    args = parser.parse_args()
    count = ingest(reset=args.reset)
    print(f"collection {COLLECTION_NAME!r} now holds {count} sections at {CHROMA_DIR}")
