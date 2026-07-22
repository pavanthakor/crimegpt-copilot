#!/usr/bin/env python3
"""One-off corpus fix: realign section titles shifted by the Gazette margin-note extraction.

Roughly 72 sections in data/bns_bnss_bsa/all_sections.jsonl carry the NEXT section's title
(section TEXT and numbering are correct everywhere — only the `title` drifted). The drift is
a +1 shift over contiguous runs: a run begins where two margin notes were concatenated onto
one section (e.g. BNS 306 "Theft by clerk or servant... . Theft after preparation...") and
ends at a section whose note was dropped and later backfilled from its own text
(see backfill_section_titles.py). Example: BNS 105 was titled "Causing death by negligence"
but its text is culpable homicide; the negligence text is on 106.

Because titles feed both the remand docx sections table AND the RAG embedding
("{act} Section {code} — {title}\n{text}"), a wrong title reaches court-bound documents and
pollutes retrieval.

Algorithm (idempotent, safe to re-run):
  1. DETECT: for each section, compare its title's IDF-weighted content-word overlap against
     its own text vs the next section's text; flag where the title fits the next better.
  2. SPLIT + SHIFT: for each concatenated title (". " into two title-like clauses), give
     part1 to the section and part2 to the next, then walk the run forward assigning each
     section the title currently on the previous one, up to the backfilled run-end.
  3. VALIDATE per run and PER SECTION: apply a run only if it raises the run's average
     title<->own-text match, and never apply a title to a section that would LOWER its own
     match (monotone — no title is ever made worse, whatever the boundary detection).
  4. Concatenated titles are split as part of step 2.
  5. Report the flagged count before and after; residual flags (harder cases + a few
     detector false-positives where a correct abstract title's keyword is absent from the
     body, e.g. BNS 2 "Definitions") are LEFT untouched rather than risk corrupting them.
  6. Re-ingest ChromaDB separately:  python -m app.ai.rag --reset

Run:  python data/fix_misaligned_titles.py         # apply
      python data/fix_misaligned_titles.py --dry    # report only, write nothing
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sys
from pathlib import Path

from backfill_section_titles import derive_title  # reuse the run-end / fallback derivation

DATA_DIR = Path(__file__).resolve().parent / "bns_bnss_bsa"
JSONL = DATA_DIR / "all_sections.jsonl"
PER_ACT = {a: DATA_DIR / f"{a}_sections.json" for a in ("BNS", "BNSS", "BSA")}

MAX_RUN = 20          # a real drift run is short; refuse to shift a suspiciously long span
_STOP = set(
    "the a an of to in by with for on as that which any such and or is be under from at shall "
    "who whoever person persons act section this his her him its their they them not no if when "
    "whom made make done cause causes causing other others thereof having he she it been being "
    "are was were will may must into out upon whether".split()
)


def _toks(s: str) -> list[str]:
    return [w for w in re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).split()
            if w not in _STOP and len(w) > 2]


def _build_idf(rows: list[dict]):
    n = len(rows)
    df: dict[str, int] = {}
    for r in rows:
        for w in set(_toks(r["text"])):
            df[w] = df.get(w, 0) + 1
    return lambda w: math.log((n + 1) / (df.get(w, 0) + 1)) + 1


def _make_score(idf):
    def score(title: str, text: str) -> float:
        tw = _toks(title)
        if not tw:
            return 0.0
        xw = set(_toks(text))
        den = sum(idf(w) for w in tw)
        return sum(idf(w) for w in tw if w in xw) / den if den else 0.0
    return score


def _is_drift(score, r: dict, nxt: dict | None) -> bool:
    if nxt is None:
        return False
    return (score(r["title"], nxt["text"]) >= score(r["title"], r["text"]) + 0.20
            and score(r["title"], nxt["text"]) >= 0.45)


def _is_backfilled(r: dict) -> bool:
    """True if the title was derived from its own text (the run-end deletion point)."""
    return bool((r["title"] or "").strip()) and r["title"] == derive_title(r["text"])


def _split_concat(title: str):
    for m in re.finditer(r"\.\s+", title):
        a, b = title[:m.start()].strip(), title[m.end():].strip()
        if len(a.split()) >= 2 and len(b.split()) >= 2 and b[:1].isupper():
            return a, b
    return None


def _correct_act(secs: list[dict], score) -> list[str]:
    """Return the corrected title list for one act's sections (file order)."""
    old = [r["title"] for r in secs]
    new = old[:]
    n = len(secs)

    def run_self(titles, s, e):
        return (sum(score(titles[i], secs[i]["text"]) for i in range(s, e)) / (e - s)
                if e > s else 0.0)

    for p in range(n - 1):
        sc = _split_concat(old[p])
        if not sc:
            continue
        a, b = sc
        if len(a.split()) < 2 or len(b.split()) < 2:
            continue
        # run end D = first backfilled section after p+1, else treat as a concat pair
        D = None
        for j in range(p + 2, min(n, p + 2 + MAX_RUN)):
            if _is_backfilled(secs[j]):
                D = j
                break
        if D is None:
            D = p + 2
        prop = new[:]
        prop[p], prop[p + 1] = a, b
        for q in range(p + 2, D):
            prop[q] = old[q - 1]
        if run_self(prop, p, D) > run_self(new, p, D) + 0.12:
            for i in range(p, D):
                # monotone guard: never make a section's own-text match worse
                if score(prop[i], secs[i]["text"]) >= score(old[i], secs[i]["text"]) - 0.05:
                    new[i] = prop[i]
    return new


def _flagged(secs: list[dict], titles: list[str], score) -> list[str]:
    out = []
    for i, r in enumerate(secs):
        rr = dict(r, title=titles[i])
        nxt = dict(secs[i + 1], title=titles[i + 1]) if i + 1 < len(secs) else None
        if _is_drift(score, rr, nxt):
            out.append(r["section_code"])
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Realign drifted section titles.")
    ap.add_argument("--dry", action="store_true", help="report only; write nothing")
    args = ap.parse_args()

    records = [json.loads(l) for l in JSONL.read_text(encoding="utf-8").splitlines() if l.strip()]
    score = _make_score(_build_idf(records))

    by_act: dict[str, list[dict]] = {}
    for r in records:
        by_act.setdefault(r["act"], []).append(r)

    corrections: dict[tuple[str, str], str] = {}
    before_total = after_total = 0
    print("act    before  after  changed")
    for act, secs in by_act.items():
        old = [r["title"] for r in secs]
        new = _correct_act(secs, score)
        before = len(_flagged(secs, old, score))
        after = len(_flagged(secs, new, score))
        changed = 0
        for i, r in enumerate(secs):
            if new[i] != old[i]:
                corrections[(act, r["section_code"])] = new[i]
                changed += 1
        before_total += before
        after_total += after
        print(f"{act:5}  {before:6}  {after:5}  {changed:7}")
    print(f"TOTAL  {before_total:6}  {after_total:5}  {len(corrections):7}")

    # every change must be monotone (never lower own-text match) — assert before writing
    worse = [
        (a, c) for (a, c), t in corrections.items()
        for r in [next(x for x in records if x["act"] == a and x["section_code"] == c)]
        if score(t, r["text"]) < score(r["title"], r["text"]) - 0.01
    ]
    if worse:
        sys.exit(f"ABORT: {len(worse)} change(s) would lower own-text match: {worse[:5]}")

    print("\nsample corrections (BNS 103-108, 306-307):")
    for r in records:
        key = (r["act"], r["section_code"])
        if r["act"] == "BNS" and r["section_code"] in {"103","104","105","106","107","108","306","307"}:
            print(f"  BNS {r['section_code']}: {r['title'][:45]!r} -> {corrections.get(key, r['title'])[:45]!r}")

    if args.dry:
        print("\n[--dry] no files written.")
        return

    # Apply to all_sections.jsonl (source of truth) + per-act JSON, preserving format.
    trailing_nl = JSONL.read_bytes().endswith(b"\n")
    for r in records:
        t = corrections.get((r["act"], r["section_code"]))
        if t is not None:
            r["title"] = t
    out = "\n".join(json.dumps(r, ensure_ascii=False) for r in records)
    JSONL.write_text(out + ("\n" if trailing_nl else ""), encoding="utf-8")

    for act, path in PER_ACT.items():
        act_records = json.loads(path.read_text(encoding="utf-8"))
        n = 0
        for r in act_records:
            t = corrections.get((act, r["section_code"]))
            if t is not None and r["title"] != t:
                r["title"] = t
                n += 1
        nl = path.read_bytes().endswith(b"\n")
        path.write_text(json.dumps(act_records, ensure_ascii=False, indent=2) + ("\n" if nl else ""),
                        encoding="utf-8")
        print(f"  {act}: {n} title(s) updated in {path.name}")

    print("\nDone. Re-ingest ChromaDB:  python -m app.ai.rag --reset")


if __name__ == "__main__":
    main()
