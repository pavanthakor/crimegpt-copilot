# Cluster-disambiguation fix — findings (attempted, REVERTED)

**Verdict: reverted.** The ingredient-based cluster fix produced a large, genuine in-scope
accuracy gain but **regressed out-of-scope refusal** (a named safety constraint) in a way
that cannot be cleanly fixed without tuning to the eval set. Per the task timebox, the code
was backed out; `backend/app/ai/legal.py` on this branch's tip equals the signed-off
baseline. The fix itself is preserved in the commit immediately below the revert
(`git show` it / check it out to re-run), so you can review and re-apply if you judge the
trade-off acceptable.

## What the fix did (principled, no eval-tuning)
Additive layer over the BNS property/deception cluster, designed from statutory ingredients
only (BNS.txt), never from eval cases:
1. **Candidate completion** — if any of {314,315,316}, {318,319}, {314,317}, {336,338} was
   retrieved, its siblings were added as candidates (score inherited) so the correct specific
   offence was selectable.
2. **Ingredient guidance** — the prompt surfaced the single distinguishing element for each
   cluster present: entrustment (316 vs 314/315), personation (319 vs 318),
   already-stolen-when-received (317 vs 314), valuable-security/deed (338 vs 336).

## Measurement — 5-run medians (live qwen2.5:7b, `scripts/section_eval.py` x5)

| Metric | BEFORE | AFTER | Δ |
|---|---|---|---|
| Top-1 | 56.1% | 68.4% | **+12.3** |
| Recall | 44.0% | 56.0% | **+12.0** |
| Precision | 50.8% | 61.1% | **+10.3** |
| Stability | 85.7% | 85.7% | 0.0 |
| **Refusal (OOS)** | **83.3%** | **50.0%** | **−33.3 ⚠** |

Cluster subset (cbt-01, cbt-02, cheating-01, cheating-02, stolen-prop-01, forgery-01) pooled
top-1: **20.0% → 58.9% (+38.9)**.

### Per-case pooled top-1 (5×3 = 15 runs each)
| Case | BEFORE | AFTER | note |
|---|---|---|---|
| cbt-01-money | 20% | 60% | cluster ↑ |
| cbt-02-goods | 0% | 73% | cluster ↑ |
| cheating-01-advance | 7% | 20% | cluster ↑ (still weak) |
| cheating-02-personation | 0% | 0% | cluster, unchanged |
| stolen-prop-01-receiving | 27% | 100% | cluster ↑ |
| forgery-01-deed | 67% | 100% | cluster ↑ |
| extortion-01-protection | 40% | 20% | non-cluster wobble (sampling) |
| negligence-01-death | 93% | 87% | sampling |
| (all other in-scope) | — | — | unchanged |

## In-scope regression check: NONE
No in-scope case that passed (top-1 ≥ 50%) before drops below 50% after.

## The regression that forces the revert: OOS refusal
- `oos-01-passport` refusal collapsed **73% → 0%**: it now selects **BNS 210** (*omission to
  produce a document to a public servant*) on **15/15** runs.
- `oos-02-good-news` stayed 100% → 100%.

### Root cause (diagnosed, not guessed)
The passport enquiry says *"what documents I need to bring."* The word "documents" retrieves
the forgery cluster (335–340) with cosine scores **0.25–0.38 — above** the 0.25
`RELEVANCE_THRESHOLD`. So the disambiguation guidance fires legitimately, and its
"pick the MOST SPECIFIC applicable section" framing tips a borderline-refusal input into a
confident selection of a document-adjacent section (210). The layer fired on an input where
a cluster was *spuriously but not sub-threshold* present.

### Why the obvious guard fails
Gating the layer on the relevance floor does **not** help: the forgery candidates for the
passport case (0.26–0.38) sit above 0.25, while genuine forgery cases retrieve 338 at ~0.4x.
There is **no principled, non-eval threshold** that separates them — raising the bar to
exclude the passport case specifically would be tuning to the eval set, which is forbidden.

## Conclusion / recommendation
A retrieval-plus-prompt nudge **can** disambiguate the cluster (+39 pts on the cluster, +12
top-1 overall) but the same nudge suppresses refusal on out-of-scope inputs that legitimately
retrieve a cluster. Separating "help choose within a cluster" from "become more willing to
select" needs one of:
- a **dedicated out-of-scope / is-this-a-crime gate** run *before* section selection (so the
  disambiguation layer only ever sees genuine-offence inputs), or
- **fine-tuning / a stronger model** that disambiguates on ingredients without the
  refusal side effect.

Both are out of scope for a one-pass retrieval fix. Baseline left intact at
top-1 ≈ 53% (ground-truth-only) / ≈ 56% (5-run live median). The fix commit is retained on
this branch for review; **do not merge as-is.**
