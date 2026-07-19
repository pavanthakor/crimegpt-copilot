#!/usr/bin/env python3
"""One-off corpus fix: backfill blank section titles + repair leading-character bleed.

58 sections in data/bns_bnss_bsa/all_sections.jsonl (BNS 26, BNSS 27, BSA 5) have a
blank `title` because the Gazette margin note was stripped too aggressively. `section_title`
flows into the remand docx sections table, so a blank could reach a court-bound document.

This script (idempotent, safe to re-run):
  1. Backfills each blank title with a short phrase derived from the first clause of the
     section text: strip the leading section number (and any stray leading character),
     drop enumerator markers, trim to a sensible clause, strip trailing punctuation, and
     sentence-case the first letter. Interior capitalisation (India, Court, High Court, …)
     is preserved so proper nouns are not mangled.
  2. Repairs the leading-character bleed where the text starts with a stray letter before
     the section number, e.g. BNS 44 "e 44. If in the exercise..." -> "44. If in the...".
     The same bleed also affects BNSS 279 and BNSS 401; all matches of the safe pattern
     `^<letter> <number>.` are fixed and char_len recomputed.
  3. Applies every change consistently to all_sections.jsonl AND the per-act JSON files,
     keyed by (act, section_code), preserving each file's existing order and formatting.

Run:  python data/backfill_section_titles.py
"""
from __future__ import annotations

import json
import re
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent / "bns_bnss_bsa"
JSONL = DATA_DIR / "all_sections.jsonl"
PER_ACT = {
    "BNS": DATA_DIR / "BNS_sections.json",
    "BNSS": DATA_DIR / "BNSS_sections.json",
    "BSA": DATA_DIR / "BSA_sections.json",
}

# A stray letter + space(s) directly before the section number that starts the text.
_LEADING_BLEED = re.compile(r"^[A-Za-z]\s+(?=\d+[A-Z]?\.)")

# Trailing filler words that read badly at the end of a truncated title.
_STOP_TRAIL = {
    "and", "or", "of", "to", "the", "in", "by", "with", "a", "an", "for", "on", "as",
    "that", "which", "any", "such", "he", "his", "him", "is", "be", "under", "from", "at",
}


def fix_leading_bleed(text: str) -> str:
    """Remove a stray leading character before the section number (e.g. 'e 44.' -> '44.')."""
    return _LEADING_BLEED.sub("", text, count=1)


def derive_title(text: str, min_words: int = 5, max_words: int = 12) -> str:
    """Derive a short, readable title from the first clause of a section's text."""
    t = fix_leading_bleed(text.strip())
    t = re.sub(r"^\s*\d+[A-Z]?\.?\s*", "", t)          # drop the section number
    t = re.sub(r"\((?:[ivxlcdm]+|[a-z]|\d+)\)", " ", t)  # drop (1) / (a) / (i) enumerators
    t = re.sub(r"\s*[—–]\s*", " ", t)          # em/en dash -> space
    t = re.sub(r"\s+", " ", t).strip()

    words = t.split(" ")
    chosen: list[str] | None = None
    acc: list[str] = []
    for i, w in enumerate(words):
        acc.append(w)
        if i + 1 >= max_words:
            chosen = acc[:]
            break
        if i + 1 >= min_words and re.search(r"[,;:.]$", w):  # natural clause boundary
            chosen = acc[:]
            break
    if chosen is None:
        chosen = words[:max_words]

    phrase = " ".join(chosen).rstrip(" .,;:—-")
    parts = phrase.split(" ")
    while len(parts) > min_words and parts[-1].lower().strip(".,;:—-") in _STOP_TRAIL:
        parts.pop()
    phrase = " ".join(parts).rstrip(" .,;:—-")
    return (phrase[0].upper() + phrase[1:]) if phrase else phrase


def compute_corrections(records: list[dict]) -> dict[tuple[str, str], dict]:
    """Return {(act, section_code): partial-update} for every record needing a change."""
    corrections: dict[tuple[str, str], dict] = {}
    for r in records:
        patch: dict = {}
        text = r.get("text", "")
        fixed = fix_leading_bleed(text)
        if fixed != text:
            patch["text"] = fixed
            patch["char_len"] = len(fixed)
            text = fixed  # derive the title from the cleaned text
        if not (r.get("title") or "").strip():
            patch["title"] = derive_title(text)
        if patch:
            corrections[(r["act"], r["section_code"])] = patch
    return corrections


def apply_corrections(records: list[dict], corrections: dict[tuple[str, str], dict]) -> int:
    n = 0
    for r in records:
        patch = corrections.get((r["act"], r["section_code"]))
        if patch:
            r.update(patch)
            n += 1
    return n


def _blank_count(records: list[dict]) -> int:
    return sum(1 for r in records if not (r.get("title") or "").strip())


def main() -> None:
    records = [json.loads(line) for line in JSONL.read_text(encoding="utf-8").splitlines() if line.strip()]
    before = _blank_count(records)
    corrections = compute_corrections(records)

    bleed = [k for k, v in corrections.items() if "text" in v]
    print(f"blank titles before: {before}")
    print(f"leading-bleed text fixes: {len(bleed)} -> {sorted(bleed)}")

    # 1. all_sections.jsonl (source of truth)
    apply_corrections(records, corrections)
    trailing_nl = JSONL.read_bytes().endswith(b"\n")
    out = "\n".join(json.dumps(r, ensure_ascii=False) for r in records)
    JSONL.write_text(out + ("\n" if trailing_nl else ""), encoding="utf-8")

    # 2. per-act JSON files (same corrections, keyed by act+code, order preserved)
    for act, path in PER_ACT.items():
        act_records = json.loads(path.read_text(encoding="utf-8"))
        changed = apply_corrections(act_records, corrections)
        nl = path.read_bytes().endswith(b"\n")
        path.write_text(
            json.dumps(act_records, ensure_ascii=False, indent=2) + ("\n" if nl else ""),
            encoding="utf-8",
        )
        print(f"  {act}: {changed} record(s) updated in {path.name}")

    after = _blank_count(records)
    print(f"blank titles after: {after}")

    examples = [
        (k[0], k[1], v["title"])
        for k, v in corrections.items()
        if "title" in v
    ][:5]
    print("sample backfilled titles:")
    for act, code, title in examples:
        print(f"  {act} {code}: {title}")


if __name__ == "__main__":
    main()
