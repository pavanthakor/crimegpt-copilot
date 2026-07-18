"""Populate backend/demo_cache/ by running the REAL pipeline once (CLAUDE.md §16).

Runs the live analyze + document pipelines for the seeded case across EN / HI / GU and
writes each output as editable JSON, so the machine-translated Gujarati/Hindi can be
hand-corrected before the demo. This script always runs live (it calls the LLM directly);
it does not consult DEMO_MODE.

    python -m app.demo_cache_build                 # seeded case I-CR-0142-2026
    python -m app.demo_cache_build --case I-CR-...  # a different case number
"""
from __future__ import annotations

import argparse
import logging
import time

from app import demo_cache
from app.ai import legal as ai_legal
from app.ai.translate import translate
from app.api.legal import _build_narrative
from app.core.db import SessionLocal
from app.models import Case, Statement, User
from app.services.documents import (
    _TRANSLATABLE_BY_DOC,
    _build_context,
)

logger = logging.getLogger("crimegpt.demo_cache_build")

LANGS = ["en", "hi", "gu"]
DOC_TYPES = ["SEIZURE_RECEIPT", "PANCHNAMA", "REMAND", "MEDICAL_LETTER"]
DEFAULT_CASE = "I-CR-0142-2026"


def build(case_number: str) -> None:
    db = SessionLocal()
    try:
        case = db.query(Case).filter(Case.case_number == case_number).first()
        if case is None:
            raise SystemExit(f"Case {case_number!r} not found — seed it first.")
        user = db.get(User, case.created_by) or db.query(User).first()

        # --- Analysis: run map_sections once (language-independent), translate reasons ---
        statements = db.query(Statement).filter(Statement.case_id == case.id).all()
        narrative = _build_narrative(case, statements)
        t0 = time.perf_counter()
        result = ai_legal.map_sections(narrative)
        logger.info("map_sections: %.1fs, %d section(s)", time.perf_counter() - t0, len(result["sections"]))

        # --- Documents: build the full context once (doc-type independent) ---
        base_ctx = _build_context(db, case, user)

        for lang in LANGS:
            # analysis payload
            sections = []
            for s in result["sections"]:
                reason = s.get("reason")
                if lang != "en" and reason:
                    reason = translate(reason, target=lang)
                sections.append({**s, "reason": reason})
            demo_cache.save_analysis(
                case.id, lang,
                {"status": result["status"], "sections": sections, "rejected": result["rejected"]},
            )
            print(f"  analysis  [{lang}] cached ({len(sections)} section(s))")

            # document contexts (one per doc type; only its clauses translated)
            for doc_type in DOC_TYPES:
                ctx = dict(base_ctx)
                if lang != "en":
                    for field in _TRANSLATABLE_BY_DOC.get(doc_type, []):
                        if ctx.get(field):
                            ctx[field] = translate(ctx[field], target=lang)
                demo_cache.save_document(case.id, doc_type, lang, ctx)
                print(f"  document  [{lang}] {doc_type} cached")

        print(f"\nDemo cache written to {demo_cache.DEMO_CACHE_DIR}")
        print("Edit the JSON files to hand-correct Gujarati/Hindi before the demo.")
    finally:
        db.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(description="Build the DEMO_MODE output cache.")
    ap.add_argument("--case", default=DEFAULT_CASE, help="case_number to cache")
    args = ap.parse_args()
    build(args.case)
