"""Populate backend/demo_cache/ by running the REAL pipeline once (CLAUDE.md §16).

Runs the live analyze + document pipelines for the seeded case across EN / HI / GU and
writes each output as editable JSON. This script always runs live (it calls the LLM
directly); it does not consult DEMO_MODE.

    python -m app.demo_cache_build                    # seeded case I-CR-0142-2026
    python -m app.demo_cache_build --case I-CR-...    # a different case number
    python -m app.demo_cache_build --langs en gu      # subset of languages

DOCUMENTS ARE DETERMINISTIC. Document generation makes no LLM call — every boilerplate
narrative comes from the per-language label templates (templates/_labels.py) with verbatim
identifiers — so this script builds each document context directly in its language and the
cache is a byte-for-byte copy of live output. No translation, no reviewed-string overlay.

HUMAN-REVIEWED ANALYSIS REASON IS PROTECTED. The one remaining machine-translated string
is the Gujarati analysis reason, hand-corrected by a reviewer and pinned in
`demo_cache/reviewed_gu.json`. This script overlays it back after building the analysis
payload, so a rebuild refreshes everything except the reviewer's own words. The summary at
the end reports which strings were preserved. See app/demo_cache_reviewed.py.

NO DB RESIDUE. The remand/panchnama contexts read ACCEPTED legal sections from the
case, so this script accepts the freshly-mapped sections inside its own transaction to
build a realistic context — then rolls back. The database is left exactly as it was,
so the demo still starts from the pristine seeded state.
"""
from __future__ import annotations

import argparse
import logging
import time

from app import demo_cache, demo_cache_reviewed
from app.ai import legal as ai_legal
from app.ai.translate import translate
from app.api.legal import _build_narrative
from app.core.db import SessionLocal
from app.models import Case, LegalSection, Statement, User
from app.models.enums import LegalAct, SectionStatus
from app.services.documents import _build_context, _load_registry

logger = logging.getLogger("crimegpt.demo_cache_build")

LANGS = ["en", "hi", "gu"]
# Every registered doc type (CLAUDE.md §8) — the registry is the single source of
# truth, so adding a template automatically adds it to the demo cache.
DOC_TYPES = sorted(_load_registry())
DEFAULT_CASE = "I-CR-0142-2026"


def _accept_sections(db, case: Case, user: User, sections: list[dict]) -> int:
    """Insert the mapped sections as ACCEPTED *within the caller's transaction*.

    The remand/panchnama context renders `sections_applied` from accepted sections;
    without this the cached contexts would carry an empty charge list. Flushed, never
    committed — build() rolls back.
    """
    added = 0
    for s in sections:
        try:
            act = LegalAct(s.get("act", "BNS"))
        except ValueError:
            act = LegalAct.OTHER
        db.add(LegalSection(
            case_id=case.id,
            act=act,
            section_code=s.get("section_code"),
            section_title=s.get("section_title"),
            reason=s.get("reason"),
            triggering_phrase=s.get("triggering_phrase"),
            confidence=s.get("confidence"),
            status=SectionStatus.ACCEPTED,
            added_by=user.id,
        ))
        added += 1
    db.flush()
    return added


def build(case_number: str, langs: list[str]) -> None:
    lock = demo_cache_reviewed.load()
    preserved: list[str] = []
    orphaned: list[str] = []

    db = SessionLocal()
    try:
        case = db.query(Case).filter(Case.case_number == case_number).first()
        if case is None:
            raise SystemExit(f"Case {case_number!r} not found — seed it first.")
        user = db.get(User, case.created_by) or db.query(User).first()

        # --- Analysis: run map_sections once (language-independent) ---
        statements = db.query(Statement).filter(Statement.case_id == case.id).all()
        narrative = _build_narrative(case, statements)
        t0 = time.perf_counter()
        result = ai_legal.map_sections(narrative)
        logger.info("map_sections: %.1fs, %d section(s)",
                    time.perf_counter() - t0, len(result["sections"]))

        # --- Make the document context realistic, then roll back (see docstring) ---
        existing_accepted = (
            db.query(LegalSection)
            .filter(LegalSection.case_id == case.id,
                    LegalSection.status == SectionStatus.ACCEPTED)
            .count()
        )
        if existing_accepted == 0:
            n = _accept_sections(db, case, user, result["sections"])
            print(f"  staged {n} accepted section(s) for context (rolled back after)")

        for lang in langs:
            # --- analysis payload ---
            sections = []
            for s in result["sections"]:
                reason = s.get("reason")
                if lang != "en" and reason:
                    reason = translate(reason, target=lang)
                sections.append({**s, "reason": reason})
            payload = {
                "status": result["status"],
                "sections": sections,
                "rejected": result["rejected"],
            }
            restored, missing = demo_cache_reviewed.apply_analysis(
                lock, case.id, lang, payload
            )
            preserved += [f"analysis[{k}].reason ({lang})" for k in restored]
            orphaned += [f"analysis[{k}].reason ({lang})" for k in missing]
            demo_cache.save_analysis(case.id, lang, payload)
            note = f" [{len(restored)} reviewed]" if restored else ""
            print(f"  analysis  [{lang}] cached ({len(sections)} section(s)){note}")

            # --- document contexts: built directly in this language. Document generation
            # is fully deterministic now (every boilerplate narrative comes from the
            # per-language label templates in templates/_labels.py), so there is no
            # translation pass and no reviewed-string overlay — the cache is a byte-for-byte
            # copy of what live generation produces. The context does not vary by doc type
            # (each template renders a subset), so it is built once per language.
            ctx = _build_context(db, case, user, lang=lang)
            for doc_type in DOC_TYPES:
                demo_cache.save_document(case.id, doc_type, lang, ctx)
                print(f"  document  [{lang}] {doc_type} cached")
    finally:
        # Never persist the staged sections — the demo DB stays pristine.
        db.rollback()
        db.close()

    print(f"\nDemo cache written to {demo_cache.DEMO_CACHE_DIR}")
    print(f"Protected {len(preserved)} human-reviewed string(s) from being overwritten:")
    for p in preserved:
        print("  kept  ", p)
    if orphaned:
        print("\nWARNING — reviewed strings with no matching section in this run:")
        for o in orphaned:
            print("  ORPHAN", o)
        print("  The model returned different sections; re-review before the demo.")

    ok, problems = demo_cache_reviewed.verify(1)
    print("\nreviewed-string verification:",
          "PASS — on-disk cache matches reviewed_gu.json" if ok else "FAIL")
    for p in problems:
        print("  -", p)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(description="Build the DEMO_MODE output cache.")
    ap.add_argument("--case", default=DEFAULT_CASE, help="case_number to cache")
    ap.add_argument("--langs", nargs="+", default=LANGS, help="languages to build")
    args = ap.parse_args()
    build(args.case, args.langs)
