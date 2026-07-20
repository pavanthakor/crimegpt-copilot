"""Human-reviewed Gujarati strings for the DEMO_MODE cache — the protected overlay.

The demo cache is machine-built (`app.demo_cache_build`) by running the live LLM +
translation pipeline. A handful of Gujarati strings in it were then hand-corrected by
a reviewer (commit 3240143 "demo: human-reviewed Gujarati strings"). Rebuilding the
cache naively would silently replace that human work with fresh machine output.

This module makes the reviewed strings a first-class, protected artifact:

    reviewed_gu.json   the reviewed strings + a sha256 of each, checked into git
    extract()          capture the current cache's reviewed strings into that lockfile
    apply()            overlay the lockfile onto a freshly built context/analysis
    verify()           confirm the on-disk cache still matches the lockfile

`demo_cache_build` calls apply() as its final step, so a rebuild refreshes everything
EXCEPT these strings, which are written back byte-for-byte from the lockfile.

Analysis reasons are keyed by "ACT SECTION_CODE" (e.g. "BNS 305") rather than by list
index, so a reviewed reason re-attaches to the right section even if the model returns
the sections in a different order. If a locked section is absent from a fresh run, that
is reported rather than silently dropped.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from app.demo_cache import DEMO_CACHE_DIR

LOCKFILE = DEMO_CACHE_DIR / "reviewed_gu.json"

# Which fields are hand-reviewable, per doc type. Mirrors services.documents
# _TRANSLATABLE_BY_DOC: only translated free text is ever hand-corrected.
REVIEWABLE_DOC_FIELDS = {
    "PANCHNAMA": ["proceedings_narrative"],
    "REMAND": ["investigation_done", "pending_investigation", "grounds_for_custody"],
    "MEDICAL_LETTER": ["examination_purpose"],
    "SEIZURE_RECEIPT": [],
    "LERS_PRESERVATION_REQUEST": [],
    "LERS_RECORDS_REQUEST": [],
}

# The only language that carries hand-reviewed content today.
REVIEWED_LANG = "gu"


def sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _section_key(section: dict) -> str:
    return f"{section.get('act')} {section.get('section_code')}"


# ---------------------------------------------------------------------------
# Lockfile I/O
# ---------------------------------------------------------------------------
def load() -> dict:
    """Return the lockfile, or an empty skeleton if it does not exist yet."""
    if not LOCKFILE.exists():
        return {"documents": {}, "analysis": {}}
    return json.loads(LOCKFILE.read_text(encoding="utf-8"))


def save(lock: dict) -> Path:
    LOCKFILE.parent.mkdir(parents=True, exist_ok=True)
    LOCKFILE.write_text(
        json.dumps(lock, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return LOCKFILE


# ---------------------------------------------------------------------------
# Extract — capture what is currently on disk as the reviewed baseline
# ---------------------------------------------------------------------------
def extract(case_id: int, doc_types: list[str]) -> dict:
    """Build a lockfile from the CURRENT cache files. Run this after a human review."""
    from app import demo_cache

    lock: dict = {
        "_comment": (
            "Human-reviewed Gujarati strings. app.demo_cache_build overlays these "
            "after rebuilding, so machine translation never overwrites them. "
            "Regenerate with: python -m app.demo_cache_reviewed --extract"
        ),
        "documents": {},
        "analysis": {},
    }

    for doc_type in doc_types:
        fields = REVIEWABLE_DOC_FIELDS.get(doc_type, [])
        if not fields:
            continue
        ctx = demo_cache.load_document(case_id, doc_type, REVIEWED_LANG)
        if not ctx:
            continue
        captured = {f: ctx[f] for f in fields if ctx.get(f)}
        if captured:
            lock["documents"][f"{case_id}_{doc_type}_{REVIEWED_LANG}"] = {
                "fields": captured,
                "sha256": {f: sha256(v) for f, v in captured.items()},
            }

    analysis = demo_cache.load_analysis(case_id, REVIEWED_LANG)
    if analysis:
        sections = {}
        for section in analysis.get("sections", []):
            reason = section.get("reason")
            if reason:
                sections[_section_key(section)] = {
                    "reason": reason,
                    "sha256": sha256(reason),
                }
        if sections:
            lock["analysis"][f"{case_id}_{REVIEWED_LANG}"] = {"sections": sections}

    return lock


# ---------------------------------------------------------------------------
# Apply — overlay the reviewed strings onto freshly built output
# ---------------------------------------------------------------------------
def apply_document(lock: dict, case_id: int, doc_type: str, lang: str,
                   context: dict) -> list[str]:
    """Overlay reviewed fields onto `context` in place. Returns the fields restored."""
    if lang != REVIEWED_LANG:
        return []
    entry = lock.get("documents", {}).get(f"{case_id}_{doc_type}_{lang}")
    if not entry:
        return []
    restored = []
    for field, value in entry.get("fields", {}).items():
        if context.get(field) != value:
            context[field] = value
            restored.append(field)
        else:
            restored.append(field)  # already identical — still reviewer-owned
    return restored


def apply_analysis(lock: dict, case_id: int, lang: str,
                   payload: dict) -> tuple[list[str], list[str]]:
    """Overlay reviewed section reasons in place.

    Returns (restored_section_keys, missing_section_keys) where `missing` are locked
    sections the fresh run did not produce — those reviewed strings have nowhere to go.
    """
    if lang != REVIEWED_LANG:
        return [], []
    entry = lock.get("analysis", {}).get(f"{case_id}_{lang}")
    if not entry:
        return [], []
    locked = entry.get("sections", {})
    restored = []
    for section in payload.get("sections", []):
        key = _section_key(section)
        if key in locked:
            section["reason"] = locked[key]["reason"]
            restored.append(key)
    missing = [k for k in locked if k not in restored]
    return restored, missing


# ---------------------------------------------------------------------------
# Verify — does the on-disk cache still match the lockfile?
# ---------------------------------------------------------------------------
def verify(case_id: int) -> tuple[bool, list[str]]:
    """Check every locked string against the cache on disk. Returns (ok, problems)."""
    from app import demo_cache

    lock = load()
    problems: list[str] = []

    for name, entry in lock.get("documents", {}).items():
        _cid, _, rest = name.partition("_")
        doc_type, _, lang = rest.rpartition("_")
        ctx = demo_cache.load_document(int(_cid), doc_type, lang)
        if ctx is None:
            problems.append(f"{name}: cache file missing")
            continue
        for field, expected in entry.get("fields", {}).items():
            actual = ctx.get(field)
            if actual != expected:
                problems.append(f"{name}.{field}: differs from reviewed text")

    for name, entry in lock.get("analysis", {}).items():
        _cid, _, lang = name.rpartition("_")
        payload = demo_cache.load_analysis(int(_cid), lang)
        if payload is None:
            problems.append(f"analysis {name}: cache file missing")
            continue
        by_key = {_section_key(s): s for s in payload.get("sections", [])}
        for key, locked in entry.get("sections", {}).items():
            section = by_key.get(key)
            if section is None:
                problems.append(f"analysis {name}: section {key} absent")
            elif section.get("reason") != locked["reason"]:
                problems.append(f"analysis {name}: {key}.reason differs from reviewed text")

    return (not problems), problems


def locked_string_count() -> int:
    """Total number of protected strings — used by preflight."""
    lock = load()
    n = sum(len(e.get("fields", {})) for e in lock.get("documents", {}).values())
    n += sum(len(e.get("sections", {})) for e in lock.get("analysis", {}).values())
    return n


if __name__ == "__main__":
    import argparse

    from app.demo_cache_build import DOC_TYPES

    ap = argparse.ArgumentParser(description="Manage the reviewed-Gujarati lockfile.")
    ap.add_argument("--extract", action="store_true",
                    help="capture the current cache's reviewed strings into the lockfile")
    ap.add_argument("--verify", action="store_true",
                    help="check the on-disk cache against the lockfile")
    ap.add_argument("--case-id", type=int, default=1)
    args = ap.parse_args()

    if args.extract:
        lock = extract(args.case_id, DOC_TYPES)
        path = save(lock)
        print(f"Wrote {path} — {locked_string_count()} protected string(s):")
        for name, entry in lock["documents"].items():
            for field in entry["fields"]:
                print(f"  doc      {name}.{field}")
        for name, entry in lock["analysis"].items():
            for key in entry["sections"]:
                print(f"  analysis {name}.sections[{key}].reason")
    elif args.verify:
        ok, problems = verify(args.case_id)
        print("PASS — cache matches reviewed strings" if ok else "FAIL")
        for p in problems:
            print("  -", p)
        raise SystemExit(0 if ok else 1)
    else:
        ap.print_help()
