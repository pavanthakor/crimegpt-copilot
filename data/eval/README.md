# Section-mapping evaluation (deliverable)

An honest, re-runnable accuracy harness for `app.ai.legal.map_sections()` — the grounded
BNS charge-mapping step. It exists to answer "how good is section mapping, really?" and to
catch regressions after any change to prompts, retrieval, or thresholds.

## Files
| File | What it is |
|---|---|
| `section_eval.json` | The eval set: 21 plain-language complaints + expected BNS section(s). Ground truth. |
| `../../scripts/section_eval.py` | The runner + scorer. Calls `map_sections()` N times/case, live. |
| `section_eval_results.json` | Machine-readable output of the last run (per-run raw + metrics). |
| `section_eval_report.md` | Human report: per-case table + five headline numbers. |

## Run it
```bash
# needs Chroma ingested + Ollama serving LLM_MODEL (same as the app); no DEMO_MODE shortcut
python scripts/section_eval.py                 # 3 runs/case (default)
python scripts/section_eval.py --runs 5        # tighter stability estimate
python scripts/section_eval.py --cases cheating # subset by id substring
```
Re-run after any change and diff `section_eval_results.json` to spot regressions.

## The rules (so the number stays honest)
1. **Never tune prompts/retrieval/thresholds against these cases.** This is a held-out
   yardstick. Improve on *other* examples, then measure here.
2. **Verify ground truth before trusting scores.** Every `expected` starts `verified: false`.
   Check each against `data/bns_bnss_bsa/BNS.txt` and flip it to `true`. The report prints how
   many cases are still unverified.
3. **If the model's pick is a better/defensible section than `expected`, fix the ground truth —
   but only during verification, never reactively to raise the score.** (E.g. fire-mischief 326
   vs general mischief 324.) Document the change.

## Metrics
- **Top-1** — primary expected section was selected.
- **Recall** — expected sections found / expected total (micro = pooled over runs).
- **Precision** — selected sections that were expected / selected total.
- **Stability** — fraction of the N runs agreeing on the selected-code set.
- **Refusal** — out-of-scope inputs returning `no_grounded_match`.
