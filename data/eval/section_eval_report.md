# Section-mapping accuracy — baseline report

- Eval set created: 2026-07-25
- Cases: **21** (19 in-scope + 2 out-of-scope) · **3 runs each**
- Model path: live `map_sections()` (RAG candidates -> LLM select -> grounding validator). No tuning to this set.
- ⚠️ **19 of 19 in-scope cases have UNVERIFIED expected sections.** Verify each `expected` against `data/bns_bnss_bsa/BNS.txt` and set `verified: true` before trusting these scores.

## Headline numbers

| Metric | Value | Notes |
|---|---|---|
| Top-1 accuracy | **47%** | primary expected section was selected (pooled over in-scope case×run) |
| Recall | **39%** | micro (pooled TP/FN); macro 40% |
| Precision | **44%** | micro (pooled TP/FP); macro 46% |
| Stability | **83%** | mean fraction of runs agreeing on the modal selected-code set |
| Refusal rate (out-of-scope) | **100%** | correctly returned no_grounded_match |

Supporting: false-refusal on in-scope inputs **2%** · false-positive on out-of-scope inputs **0%** · pooled TP/FP/FN = 28/36/44.

## Per-case results

`sel/runs` columns list what each run selected (∅ = refused). ✔ before an expected code = the primary.

| Case | Crime type | Expected (primary ✔) | Selected per run | Top-1 | Recall | Precision | Stability | Ver. |
|---|---|---|---|---|---|---|---|---|
| `theft-01-shop` | theft | ✔303 | 303 · 303 · 303 | 100% | 100% | 100% | 100% | **no** |
| `theft-02-dwelling` | theft | 303 ✔305 | 305,330 · 305,330 · 305,331 | 100% | 50% | 50% | 67% | **no** |
| `theft-03-snatching` | theft | ✔304 | 304 · 304 · ∅ | 67% | 67% | 100% | 67% | **no** |
| `hurt-01-simple` | hurt | ✔115 | 117 · 117 · 117 | 0% | 0% | 0% | 100% | **no** |
| `hurt-02-grievous-weapon` | hurt | 117 ✔118 | 118 · 118 · 118 | 100% | 50% | 100% | 100% | **no** |
| `trespass-01-house-trespass` | house-trespass | ✔329 | 330,333 · 330 · 330 | 0% | 0% | 0% | 67% | **no** |
| `trespass-02-house-breaking` | house-trespass | 330 ✔331 | 305,330 · 305,331 · 305 | 33% | 33% | 33% | 33% | **no** |
| `cbt-01-money` | criminal-breach-of-trust | ✔316 | 315 · 315 · 315 | 0% | 0% | 0% | 100% | **no** |
| `cbt-02-goods` | criminal-breach-of-trust | ✔316 | 314 · 314 · 314 | 0% | 0% | 0% | 100% | **no** |
| `cheating-01-advance` | cheating | ✔318 | 335 · 335 · 340 | 0% | 0% | 0% | 67% | **no** |
| `cheating-02-personation` | cheating | 318 ✔319 | 316 · 316 · 316 | 0% | 0% | 0% | 100% | **no** |
| `intimidation-01-threat` | criminal-intimidation | ✔351 | 351 · 351 · 351 | 100% | 100% | 100% | 100% | **no** |
| `intimidation-02-phone` | criminal-intimidation | ✔351 | 351 · 351 · 351 | 100% | 100% | 100% | 100% | **no** |
| `extortion-01-protection` | extortion | ✔308 | 308,321 · 351,120 · 351 | 33% | 33% | 17% | 33% | **no** |
| `mischief-01-crop-fire` | mischief | ✔324 | 326 · 326 · 326 | 0% | 0% | 0% | 100% | **no** |
| `forgery-01-deed` | forgery | ✔336 338 | 336 · 322 · 336 | 67% | 33% | 67% | 67% | **no** |
| `negligence-01-death` | negligence-causing-death | ✔106 | 281 · 106 · 106 | 67% | 67% | 67% | 67% | **no** |
| `restraint-01-blocked` | wrongful-restraint | ✔126 | 126 · 126 · 126 | 100% | 100% | 100% | 100% | **no** |
| `stolen-prop-01-receiving` | receiving-stolen-property | ✔317 | 314 · 317 · 314 | 33% | 33% | 33% | 67% | **no** |
| `oos-01-passport` | out-of-scope | — (refuse) | ∅ · ∅ · ∅ | n/a | n/a | n/a | 100% | — |
| `oos-02-good-news` | out-of-scope | — (refuse) | ∅ · ∅ · ∅ | n/a | n/a | n/a | 100% | — |

### How to read this
- **Top-1 / Recall / Precision** are computed only on in-scope cases; out-of-scope cases score on **Refusal** instead.
- **Precision** is undefined for a run that selected nothing (no TP, no FP) and is skipped in that run's average, so a wrongful refusal shows up as a Recall/Top-1 miss and in *false-refusal*, not as inflated precision.
- **A section counts as correct only if it is in the case's `expected` set.** A genuinely-applicable section the author didn't list will (honestly) count against precision — that is the signal to expand `expected` after human review, never to tune the model.
- Re-run with `python scripts/section_eval.py`; compare `section_eval_results.json` across commits to catch regressions.
