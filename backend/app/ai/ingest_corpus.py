#!/usr/bin/env python3
"""
Ingest the BNS/BNSS/BSA corpus into ChromaDB for CrimeGPT's legal RAG.
Place at backend/app/ai/ingest_corpus.py and run once after setup.

    python -m app.ai.ingest_corpus
"""
import json
from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions

DATA = Path(__file__).resolve().parents[3] / "data" / "bns_bnss_bsa"
CHROMA_DIR = Path(__file__).resolve().parents[1] / "storage" / "chroma"
COLLECTION = "legal_sections"


def main():
    corpus = DATA / "all_sections.jsonl"
    sections = [json.loads(line) for line in corpus.open(encoding="utf-8")]
    print(f"Loaded {len(sections)} sections from {corpus}")

    client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    # Uses Ollama-independent local embeddings; swap for nomic-embed-text via Ollama if preferred.
    ef = embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name="all-MiniLM-L6-v2"
    )
    coll = client.get_or_create_collection(name=COLLECTION, embedding_function=ef)

    ids, docs, metas = [], [], []
    for s in sections:
        ids.append(f"{s['act']}-{s['section_code']}")
        # embed title + text so section headings are searchable too
        docs.append(f"{s['act']} Section {s['section_code']} — {s['title']}\n{s['text']}")
        metas.append({
            "act": s["act"],
            "act_name": s["act_name"],
            "section_code": s["section_code"],
            "title": s["title"],
            "citation": s["citation"],
        })

    B = 200
    for i in range(0, len(ids), B):
        coll.add(ids=ids[i:i + B], documents=docs[i:i + B], metadatas=metas[i:i + B])
        print(f"  indexed {min(i + B, len(ids))}/{len(ids)}")

    print(f"Done. Collection '{COLLECTION}' now holds {coll.count()} sections.")
    print("Sanity check — query 'dishonestly taking movable property':")
    res = coll.query(query_texts=["dishonestly taking movable property"], n_results=3)
    for m in res["metadatas"][0]:
        print("   ", m["citation"], "-", m["title"])


if __name__ == "__main__":
    main()
