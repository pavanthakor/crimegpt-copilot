# Section-mapping accuracy — baseline report

- Eval set created: 2026-07-25
- Cases: **21** (19 in-scope + 2 out-of-scope) · **3 runs each**
- Model path: live `map_sections()` (RAG candidates -> LLM select -> grounding validator). No tuning to this set.

## Headline numbers

| Metric | Value | Notes |
|---|---|---|
| Top-1 accuracy | **63%** | primary expected section was selected (pooled over in-scope case×run) |
| Recall | **51%** | micro (pooled TP/FN); macro 54% |
| Precision | **58%** | micro (pooled TP/FP); macro 61% |
| Stability | **86%** | mean fraction of runs agreeing on the modal selected-code set |
| Refusal rate (out-of-scope) | **100%** | correctly returned no_grounded_match |

Supporting: false-refusal on in-scope inputs **2%** · false-positive on out-of-scope inputs **0%** · pooled TP/FP/FN = 38/28/37.

## Per-case results

`sel/runs` columns list what each run selected (∅ = refused). ✔ before an expected code = the primary.

| Case | Crime type | Expected (primary ✔) | Selected per run | Top-1 | Recall | Precision | Stability | Ver. |
|---|---|---|---|---|---|---|---|---|
| `theft-01-shop` | theft | ✔303 | 303 · 303 · 303 | 100% | 100% | 100% | 100% | yes |
| `theft-02-dwelling` | theft | 303 ✔305 | 305,330 · 305,330 · 305,330 | 100% | 50% | 50% | 100% | yes |
| `theft-03-snatching` | theft | ✔304 | 304 · 304 · 304 | 100% | 100% | 100% | 100% | yes |
| `hurt-01-simple` | hurt | ✔115 | 117 · 117 · 117 | 0% | 0% | 0% | 100% | yes |
| `hurt-02-grievous-weapon` | hurt | 117 ✔118 | 118 · 118 · 118 | 100% | 50% | 100% | 100% | yes |
| `trespass-01-house-trespass` | house-trespass | ✔329 | 330,333 · 330 · 330,331 | 0% | 0% | 0% | 33% | yes |
| `trespass-02-house-breaking` | house-trespass | 330 ✔331 | 305,331 · 305,330 · 305,330 | 33% | 50% | 50% | 67% | yes |
| `cbt-01-money` | criminal-breach-of-trust | ✔316 | 316 · 315 · 315 | 33% | 33% | 33% | 67% | yes |
| `cbt-02-goods` | criminal-breach-of-trust | ✔316 | 314 · 314 · 314 | 0% | 0% | 0% | 100% | yes |
| `cheating-01-advance` | cheating | ✔318 | 340 · 335 · 335,318 | 33% | 33% | 17% | 33% | yes |
| `cheating-02-personation` | cheating | 318 ✔319 | 316 · 217 · 316 | 0% | 0% | 0% | 67% | yes |
| `intimidation-01-threat` | criminal-intimidation | ✔351 | 351 · 351 · 351 | 100% | 100% | 100% | 100% | yes |
| `intimidation-02-phone` | criminal-intimidation | ✔351 | 351 · 351 · 351 | 100% | 100% | 100% | 100% | yes |
| `extortion-01-protection` | extortion | ✔308 | 308,309 · 351 · 351 | 33% | 33% | 17% | 67% | yes |
| `mischief-01-crop-fire` | mischief | 324 ✔326 | 326 · 326 · 326 | 100% | 50% | 100% | 100% | yes |
| `forgery-01-deed` | forgery | ✔336 338 | ∅ · 336 · 336 | 67% | 33% | 100% | 67% | yes |
| `negligence-01-death` | negligence-causing-death | ✔106 | 106 · 106 · 106 | 100% | 100% | 100% | 100% | yes |
| `restraint-01-blocked` | wrongful-restraint | ✔126 | 126 · 126 · 126 | 100% | 100% | 100% | 100% | yes |
| `stolen-prop-01-receiving` | receiving-stolen-property | ✔317 | 317 · 317 · 317 | 100% | 100% | 100% | 100% | yes |
| `oos-01-passport` | out-of-scope | — (refuse) | ∅ · ∅ · ∅ | n/a | n/a | n/a | 100% | — |
| `oos-02-good-news` | out-of-scope | — (refuse) | ∅ · ∅ · ∅ | n/a | n/a | n/a | 100% | — |

### How to read this
- **Top-1 / Recall / Precision** are computed only on in-scope cases; out-of-scope cases score on **Refusal** instead.
- **Precision** is undefined for a run that selected nothing (no TP, no FP) and is skipped in that run's average, so a wrongful refusal shows up as a Recall/Top-1 miss and in *false-refusal*, not as inflated precision.
- **A section counts as correct only if it is in the case's `expected` set.** A genuinely-applicable section the author didn't list will (honestly) count against precision — that is the signal to expand `expected` after human review, never to tune the model.
- Re-run with `python scripts/section_eval.py`; compare `section_eval_results.json` across commits to catch regressions.
