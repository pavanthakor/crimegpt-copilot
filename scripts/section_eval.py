"""Section-mapping accuracy harness (CLAUDE.md §6-A, §17).

Runs app.ai.legal.map_sections() over data/eval/section_eval.json, N times per case,
and scores it honestly. NOTHING here tunes the model — it only measures. Re-run after any
change to prompts / retrieval / thresholds to catch regressions.

    python scripts/section_eval.py                 # 3 runs/case, live Qwen + Chroma
    python scripts/section_eval.py --runs 5         # more runs = tighter stability estimate
    python scripts/section_eval.py --cases theft    # only case ids containing "theft"
    python scripts/section_eval.py --out-dir /tmp   # write results elsewhere

Writes, next to the eval set:
    section_eval_results.json   full per-run raw output + computed metrics (machine-readable)
    section_eval_report.md      the human report: per-case table + the five headline numbers

Requirements (same as the app): Chroma corpus ingested and Ollama serving LLM_MODEL, OR
FORCE_API=true with a working fallback. map_sections() calls the LLM directly (no DEMO_MODE
cache), so this measures the REAL model every time.

Metric definitions (see the printed report header for the same, in prose):
    top-1     primary expected code appears in the run's selected sections
    recall    |selected ∩ expected| / |expected|
    precision |selected ∩ expected| / |selected|
    stability fraction of runs whose selected-code SET equals the modal set
    refusal   out-of-scope input returned status == "no_grounded_match"
Headline recall/precision are micro-averaged (pooled TP/FP/FN over every in-scope run) so a
case with many expected sections is weighted by its size; macro (per-case mean) is reported
alongside for contrast.
"""
from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND = REPO_ROOT / "backend"
EVAL_DIR = REPO_ROOT / "data" / "eval"
EVAL_FILE = EVAL_DIR / "section_eval.json"

# Make `app.*` importable; keep Gujarati/Hindi console output from dying on cp1252.
sys.path.insert(0, str(BACKEND))
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
    except Exception:  # noqa: BLE001
        pass


def _log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


# ---------------------------------------------------------------------------
# Scoring helpers (pure — unit-testable, no model calls)
# ---------------------------------------------------------------------------
def selected_bns_codes(result: dict) -> list[str]:
    """The BNS section codes a map_sections() result selected, in order, de-duplicated."""
    seen: list[str] = []
    for s in result.get("sections", []):
        if s.get("act") == "BNS":
            code = str(s.get("section_code"))
            if code not in seen:
                seen.append(code)
    return seen


def score_run(selected: list[str], expected: set[str]) -> dict:
    """TP/FP/FN + derived precision/recall for one run against one case."""
    sel = set(selected)
    tp = len(sel & expected)
    fp = len(sel - expected)
    fn = len(expected - sel)
    recall = tp / len(expected) if expected else None
    precision = tp / (tp + fp) if (tp + fp) else None  # undefined on an empty selection
    return {"tp": tp, "fp": fp, "fn": fn, "recall": recall, "precision": precision}


def set_stability(run_code_sets: list[frozenset]) -> float:
    """Fraction of runs equal to the single most common selected-code set."""
    if not run_code_sets:
        return 0.0
    modal, n = Counter(run_code_sets).most_common(1)[0]
    return n / len(run_code_sets)


def mean(xs: list[float]) -> float | None:
    xs = [x for x in xs if x is not None]
    return statistics.fmean(xs) if xs else None


# ---------------------------------------------------------------------------
# Evaluation
# ---------------------------------------------------------------------------
def evaluate(cases: list[dict], runs: int) -> list[dict]:
    """Run map_sections() `runs` times per case; return per-case records with raw runs + metrics."""
    from app.ai.legal import map_sections  # imported here so --help works without the stack up

    per_case: list[dict] = []
    total = len(cases)
    for ci, case in enumerate(cases, 1):
        expected = {e["code"] for e in case.get("expected", [])}
        primary = case.get("primary")
        is_oos = bool(case.get("expect_refusal"))
        _log(f"[{ci}/{total}] {case['id']} ({case['crime_type']}) — {runs} runs")

        run_records: list[dict] = []
        for r in range(1, runs + 1):
            t0 = time.perf_counter()
            try:
                out = map_sections(case["complaint"])
                selected = selected_bns_codes(out)
                status = out.get("status")
                err = None
            except Exception as exc:  # noqa: BLE001 — one bad run must not sink the sweep
                selected, status, err = [], "error", f"{type(exc).__name__}: {exc}"
                _log(f"    run {r}: ERROR {err}")
            dt = time.perf_counter() - t0
            sc = score_run(selected, expected)
            refused = status == "no_grounded_match"
            top1 = (primary in selected) if primary is not None else None
            run_records.append({
                "run": r, "selected": selected, "status": status, "error": err,
                "seconds": round(dt, 2), "refused": refused, "top1": top1, **sc,
            })
            tag = "REFUSED" if refused else (",".join(selected) or "(none)")
            _log(f"    run {r}: {tag}  ({dt:.1f}s)")

        code_sets = [frozenset(rr["selected"]) for rr in run_records]
        ok_runs = [rr for rr in run_records if rr["status"] != "error"]
        per_case.append({
            "id": case["id"],
            "crime_type": case["crime_type"],
            "primary": primary,
            "expected": sorted(expected),
            "expect_refusal": is_oos,
            "all_verified": all(e.get("verified") for e in case.get("expected", [])) if not is_oos else True,
            "runs": run_records,
            "errored_runs": len(run_records) - len(ok_runs),
            # case-level aggregates (means over non-errored runs)
            "top1_rate": mean([rr["top1"] for rr in ok_runs]) if not is_oos else None,
            "recall": mean([rr["recall"] for rr in ok_runs]) if not is_oos else None,
            "precision": mean([rr["precision"] for rr in ok_runs]) if not is_oos else None,
            "refusal_rate": mean([1.0 if rr["refused"] else 0.0 for rr in ok_runs]),
            "stability": set_stability(code_sets),
            "modal_selection": sorted(Counter(code_sets).most_common(1)[0][0]) if code_sets else [],
        })
    return per_case


def headline(per_case: list[dict], runs: int) -> dict:
    """The five headline numbers + the supporting breakdown."""
    inscope = [c for c in per_case if not c["expect_refusal"]]
    oos = [c for c in per_case if c["expect_refusal"]]

    # pooled (micro) TP/FP/FN across every non-errored in-scope run
    tp = fp = fn = 0
    top1_hits = top1_n = 0
    false_refusals = 0  # in-scope runs that wrongly returned nothing
    for c in inscope:
        for rr in c["runs"]:
            if rr["status"] == "error":
                continue
            tp += rr["tp"]; fp += rr["fp"]; fn += rr["fn"]
            top1_n += 1
            if rr["top1"]:
                top1_hits += 1
            if rr["refused"]:
                false_refusals += 1

    # out-of-scope refusal (the metric the request asks for) + its inverse (false positives)
    oos_n = oos_refused = 0
    for c in oos:
        for rr in c["runs"]:
            if rr["status"] == "error":
                continue
            oos_n += 1
            if rr["refused"]:
                oos_refused += 1

    return {
        "runs_per_case": runs,
        "n_cases": len(per_case),
        "n_inscope": len(inscope),
        "n_out_of_scope": len(oos),
        "unverified_inscope_cases": sum(1 for c in inscope if not c["all_verified"]),
        # ---- the five headline numbers ----
        "top1_accuracy": (top1_hits / top1_n) if top1_n else None,
        "recall_micro": (tp / (tp + fn)) if (tp + fn) else None,
        "precision_micro": (tp / (tp + fp)) if (tp + fp) else None,
        "stability": mean([c["stability"] for c in per_case]),
        "refusal_rate_oos": (oos_refused / oos_n) if oos_n else None,
        # ---- supporting ----
        "recall_macro": mean([c["recall"] for c in inscope]),
        "precision_macro": mean([c["precision"] for c in inscope]),
        "false_refusal_rate_inscope": (false_refusals / top1_n) if top1_n else None,
        "false_positive_rate_oos": (1 - oos_refused / oos_n) if oos_n else None,
        "pooled_tp": tp, "pooled_fp": fp, "pooled_fn": fn,
    }


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------
def _fmt_pct(x: float | None) -> str:
    return "—" if x is None else f"{x * 100:.0f}%"


def render_report(per_case: list[dict], h: dict, meta_created: str) -> str:
    L: list[str] = []
    L.append("# Section-mapping accuracy — baseline report")
    L.append("")
    L.append(f"- Eval set created: {meta_created}")
    L.append(f"- Cases: **{h['n_cases']}** ({h['n_inscope']} in-scope + {h['n_out_of_scope']} out-of-scope) · **{h['runs_per_case']} runs each**")
    L.append(f"- Model path: live `map_sections()` (RAG candidates -> LLM select -> grounding validator). No tuning to this set.")
    if h["unverified_inscope_cases"]:
        L.append(f"- ⚠️ **{h['unverified_inscope_cases']} of {h['n_inscope']} in-scope cases have UNVERIFIED expected sections.** "
                 f"Verify each `expected` against `data/bns_bnss_bsa/BNS.txt` and set `verified: true` before trusting these scores.")
    L.append("")
    L.append("## Headline numbers")
    L.append("")
    L.append("| Metric | Value | Notes |")
    L.append("|---|---|---|")
    L.append(f"| Top-1 accuracy | **{_fmt_pct(h['top1_accuracy'])}** | primary expected section was selected (pooled over in-scope case×run) |")
    L.append(f"| Recall | **{_fmt_pct(h['recall_micro'])}** | micro (pooled TP/FN); macro {_fmt_pct(h['recall_macro'])} |")
    L.append(f"| Precision | **{_fmt_pct(h['precision_micro'])}** | micro (pooled TP/FP); macro {_fmt_pct(h['precision_macro'])} |")
    L.append(f"| Stability | **{_fmt_pct(h['stability'])}** | mean fraction of runs agreeing on the modal selected-code set |")
    L.append(f"| Refusal rate (out-of-scope) | **{_fmt_pct(h['refusal_rate_oos'])}** | correctly returned no_grounded_match |")
    L.append("")
    L.append(f"Supporting: false-refusal on in-scope inputs **{_fmt_pct(h['false_refusal_rate_inscope'])}** · "
             f"false-positive on out-of-scope inputs **{_fmt_pct(h['false_positive_rate_oos'])}** · "
             f"pooled TP/FP/FN = {h['pooled_tp']}/{h['pooled_fp']}/{h['pooled_fn']}.")
    L.append("")
    L.append("## Per-case results")
    L.append("")
    L.append("`sel/runs` columns list what each run selected (∅ = refused). ✔ before an expected code = the primary.")
    L.append("")
    L.append("| Case | Crime type | Expected (primary ✔) | Selected per run | Top-1 | Recall | Precision | Stability | Ver. |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for c in per_case:
        exp = " ".join(("✔" + code if code == c["primary"] else code) for code in c["expected"]) or "— (refuse)"
        runs_str = " · ".join("∅" if not rr["selected"] else ",".join(rr["selected"]) for rr in c["runs"])
        if c["expect_refusal"]:
            top1 = rec = prec = "n/a"
        else:
            top1 = _fmt_pct(c["top1_rate"]); rec = _fmt_pct(c["recall"]); prec = _fmt_pct(c["precision"])
        ver = "—" if c["expect_refusal"] else ("yes" if c["all_verified"] else "**no**")
        L.append(f"| `{c['id']}` | {c['crime_type']} | {exp} | {runs_str} | {top1} | {rec} | {prec} | {_fmt_pct(c['stability'])} | {ver} |")
    L.append("")
    L.append("### How to read this")
    L.append("- **Top-1 / Recall / Precision** are computed only on in-scope cases; out-of-scope cases score on **Refusal** instead.")
    L.append("- **Precision** is undefined for a run that selected nothing (no TP, no FP) and is skipped in that run's average, so a wrongful refusal shows up as a Recall/Top-1 miss and in *false-refusal*, not as inflated precision.")
    L.append("- **A section counts as correct only if it is in the case's `expected` set.** A genuinely-applicable section the author didn't list will (honestly) count against precision — that is the signal to expand `expected` after human review, never to tune the model.")
    L.append("- Re-run with `python scripts/section_eval.py`; compare `section_eval_results.json` across commits to catch regressions.")
    L.append("")
    return "\n".join(L)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description="Measure section-mapping accuracy (honest baseline).")
    ap.add_argument("--runs", type=int, default=3, help="runs per case (default 3)")
    ap.add_argument("--cases", default="", help="only case ids containing this substring")
    ap.add_argument("--eval-file", default=str(EVAL_FILE), help="path to the eval set JSON")
    ap.add_argument("--out-dir", default=str(EVAL_DIR), help="where to write results + report")
    args = ap.parse_args()

    eval_path = Path(args.eval_file)
    data = json.loads(eval_path.read_text(encoding="utf-8"))
    cases = data["cases"]
    if args.cases:
        cases = [c for c in cases if args.cases in c["id"]]
    if not cases:
        _log("no cases matched — nothing to do")
        return 1

    _log(f"Evaluating {len(cases)} case(s) x {args.runs} run(s) = {len(cases) * args.runs} map_sections() calls...")
    t0 = time.perf_counter()
    per_case = evaluate(cases, args.runs)
    h = headline(per_case, args.runs)
    elapsed = time.perf_counter() - t0

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    results = {
        "eval_file": str(eval_path.name),
        "runs_per_case": args.runs,
        "elapsed_seconds": round(elapsed, 1),
        "headline": h,
        "per_case": per_case,
    }
    (out_dir / "section_eval_results.json").write_text(
        json.dumps(results, indent=2, ensure_ascii=False), encoding="utf-8")
    report = render_report(per_case, h, data.get("_meta", {}).get("created", "?"))
    (out_dir / "section_eval_report.md").write_text(report, encoding="utf-8")

    _log(f"\nDone in {elapsed:.0f}s. Wrote section_eval_results.json + section_eval_report.md to {out_dir}")
    # echo the headline block to stdout so a terminal run shows the numbers immediately
    print("\n" + report.split("## Per-case results")[0].rstrip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
