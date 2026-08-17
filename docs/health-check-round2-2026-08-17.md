> ## Status as of 18 August 2026
>
> **This report measures commit `95665e8`. Several findings below have since been fixed —
> the report body is left exactly as taken, so read it as a record of that commit, not of
> the current head.**
>
> **Closed since this audit:**
>
> | Finding | Closed by |
> |---|---|
> | Step-up PIN was a browser-side gate only; the two high-stakes writes accepted a bare JWT (Part F, reported here as analysis only) | **`495a34a`** — server-side enforcement on case register and SHO finalize; finalize has no bypass, since an SHO can PIN-login on a phone |
> | Model self-reported `confidence` shown as a large percentage, at 1.0 on wrong picks (96.3% of wrong sections scored ≥90%; AUC 0.735) | **`728e79f`** — removed from both display sites; kept in the DB, API and eval harness |
> | Setup gaps: no LAN config for `/m`, no RAG corpus build, no firewall rules, `OLLAMA_KEEP_ALIVE` unset, and no verification pass | **`8ae9f60`** — `verify.ps1` plus extended `setup.ps1`/`setup.sh`; the keep-alive check reads Ollama's live `expires_at`, not the env var |
> | Gujarati font warning cried wolf (Part E proved Word substitutes Shruti and renders correctly) | **`8ae9f60`** — replaced with an any-Gujarati-capable-font check |
>
> **Deliberately still open, not fixed:** section-selector non-determinism (Part B — 3
> distinct outcomes in 10 identical runs, no seed set anywhere; determinism is a separate
> decision, deferred), the ~1-in-20 JSON-repair retry tail on intake extraction (Part D —
> 127 s worst case, cause identified with a 1:1 correlation), and the three pre-existing
> auth findings — no IO-exclusive endpoint (RBAC is hierarchical by design), wrong PIN
> returns 200 rather than a uniform 401 (deliberate, to avoid killing the session), and
> the step-up lockout is 60 s rather than 5 minutes.
>
> Part F below is the **pre-implementation analysis only**; the implementation and its
> HTTP proof landed in `495a34a`.

# CrimeGPT — health check, Round 2, 17 August 2026

**Commit under test: `95665e88a47348cc222a5c03cebca9bd7a992805`**
Branch: `main`. Working tree clean apart from the two health-check reports (untracked).
Parts A–E were **read-only**: nothing in the project was created, edited or deleted.
Part F is **not implemented** — the pre-implementation analysis and proposal are below, awaiting go-ahead.

Environment: backend started with `python -m uvicorn app.main:app --host 0.0.0.0 --port 8000` from
`backend/.venv` (never bare `uvicorn`); frontend on port 3000. DEMO_MODE was **off** for every
measurement (asserted in-harness via `GET /api/system/demo-mode` before recording) and has been
**restored to `true`** — `backend/.env` line 5 still reads `DEMO_MODE=true` and was never edited.

| Part | Verdict |
|---|---|
| A — top-3 / top-5 contradiction | **RESOLVED** — the figures were from different pipeline stages; recomputed at one stage they are monotonic |
| B — determinism | **FAIL (confirmed non-deterministic)** — 3 distinct outcomes in 10 identical runs; no seed set anywhere |
| C — query expansion silent failure | **RESOLVED — my Round 1 claim was wrong.** 0 failures in 63 calls. The gap has a different cause |
| D — 79-second outlier | **RESOLVED** — cause identified with a 1:1 correlation, and it is *not* model eviction |
| E — Gujarati tofu risk | **PASS — my Round 1 inference was wrong.** Rendered and inspected; no tofu |
| F — server-side step-up enforcement | **NOT STARTED — awaiting your go-ahead** |
| G — human-only checklist | delivered below |

---

## 0. Calibration — localhost / IPv6 artifact

Done first, before any timing. The artifact is real, reproducible, and was in my Round 1 client.

```
getaddrinfo('localhost', 8000) ->  AF_INET6 ('::1', 8000)      <-- tried first
                                   AF_INET  ('127.0.0.1', 8000)
```

`GET /health` × 5, milliseconds:

| Client configuration | Runs (ms) | Median | Verdict |
|---|---|---|---|
| `localhost`, new connection each call | 2054.6, 2051.6, 2021.0, 2035.4, 2076.9 | **2051.63 ms** | **SLOW — unusable for timing** |
| `127.0.0.1`, new connection each call | 3.3, 8.4, 1.9, 13.9, 17.8 | 8.43 ms | OK |
| `localhost`, keep-alive session | 2068.5, 1.8, 1.7, 1.4, 1.4 | 1.66 ms | OK after first connection |
| **`127.0.0.1`, keep-alive session — what every Round 2 harness uses** | 24.2, 1.5, 1.2, 1.1, 1.1 | **1.20 ms** | **OK (single-digit ms)** |

`GET /health` does no work at all, so the 2.05 s is pure transport: uvicorn is bound IPv4-only, `::1`
is tried first and stalls before falling back. **Every Round 2 number below was taken over
`127.0.0.1` with a keep-alive `requests.Session`, median 1.20 ms overhead.** Round 1's Part 4 was
already re-run this way; Round 1's Part 2 per-document figures (~2.1 s) were *not*, and should be
read as ~2.05 s of artifact plus ~90 ms of real work.

---

## Part A — Reconciling top-1 / top-3 / top-5 — **RESOLVED**

You were right that the numbers could not all be true of one pipeline. They were not. Here is the
precise accounting.

### What each Round 1 figure actually measured

| Round 1 figure | Pipeline stage | Definition of "correct" used |
|---|---|---|
| top-1 = 57.9% | **Final output** of `map_sections()` — validated, grounded sections | primary expected code **appears anywhere in the returned set** |
| top-3 = 26.3%, top-5 = 47.4% | **Retrieval**, before any LLM selection — `retrieve_offences()` cosine ranking of 12 candidates | primary expected code sits **at rank ≤3 / ≤5** of that candidate list |
| present-in-candidate-set = 89.5% | **Retrieval union** — raw hits ∪ LLM statutory restatement, ~17–24 candidates | primary expected code is **present** in that pool |

Two separate mistakes made this look paradoxical:

1. **They are three different pipeline stages**, and the later stage is *better* than the earlier one.
   The LLM selection step is more accurate than the cosine ranking that feeds it, so a
   "top-3" taken before selection is legitimately *lower* than a "top-1" taken after it. Nesting
   never applied because the sets are not nested — they are different lists at different points.
2. **My "top-1" was not top-1.** It was set-membership in the final list — the same definition
   `scripts/section_eval.py` uses ("primary expected code appears in the run's selected sections").
   That is a "top-|selected|", not a rank-1 measure.

### Recomputed at ONE stage — the final ranked list the officer sees

Method: the validated BNS sections returned by `map_sections()`, ranked by the `confidence` the
model assigns, highest first — which is the list the UI renders. Same definition of "correct"
throughout: *the primary expected BNS code appears at or above position k*. 3 full runs of the
21-case set, live `qwen2.5:7b`, DEMO_MODE off.

| Metric (officer-visible final list) | Run 1 | Run 2 | Run 3 | **Median** | Range |
|---|---|---|---|---|---|
| **top-1** | 52.6% | 57.9% | 63.2% | **57.9%** | 52.6–63.2% |
| **top-3** | 52.6% | 57.9% | 63.2% | **57.9%** | 52.6–63.2% |
| **top-5** | 52.6% | 57.9% | 63.2% | **57.9%** | 52.6–63.2% |
| present anywhere in final list | 52.6% | 57.9% | 63.2% | **57.9%** | 52.6–63.2% |

**Monotonic in every run: TRUE** (top-1 ≤ top-3 ≤ top-5 ≤ anywhere ≤ candidate presence).

They are monotonic by being **equal**, and the reason is the important finding:

| Size of the final list | Share of 57 in-scope case-runs |
|---|---|
| exactly 1 section | 49/57 (86%) |
| exactly 2 sections | 8/57 (14%) |
| **3 or more** | **0/57 (0%)** |
| 5 or more | 0/57 (0%) |

Mean list length **1.16**, maximum **2**. **A third position never existed in any run.** So at the
officer-visible stage, "top-3" and "top-5" are not merely equal to top-1 — they are undefined as
discriminators. There is no candidate list of 3 or 5 for the officer to scan. The product shows one
charge (occasionally two) and that is the whole answer.

### Candidate-set presence, labelled plainly

**89.5%**, identical in all three runs — measured at the **retrieval-union stage**, i.e. the pool of
17–24 BNS sections assembled by `retrieve_offences_union()` and handed to the LLM as the closed set
it must choose from. **This is an internal pool. The officer never sees it.**

### Where the accuracy is actually lost

| Run | correct section in candidate pool | of those, it reached the officer | **lost by the selector** | never retrieved at all |
|---|---|---|---|---|
| 1 | 17/19 | 10 | **7** | 2 |
| 2 | 17/19 | 11 | **6** | 2 |
| 3 | 17/19 | 12 | **5** | 2 |

Only **2 of 19** cases fail at retrieval (`cbt-01-money`, `cbt-02-goods`, both primary BNS 316 —
criminal breach of trust, never retrieved in any run). The other **5–7 losses per run are the LLM
choosing the wrong section from a pool that contained the right one:**

| Case | Primary | Runs lost by the selector |
|---|---|---|
| `trespass-01-house-trespass` | 329 | 3/3 |
| `trespass-02-house-breaking` | 331 | 3/3 |
| `cheating-02-personation` | 319 | 3/3 |
| `stolen-prop-01-receiving` | 317 | 3/3 |
| `theft-02-dwelling` | 305 | 2/3 |
| `hurt-01-simple` | 115 | 2/3 |
| `cheating-01-advance` | 318 | 2/3 |

### The one sentence you can say out loud

> **"On our 21-case held-out test set, CrimeGPT puts the correct BNS section in front of the officer
> 58% of the time, and the correct section is in the candidate list it chooses from 90% of the time."**

**Scope, if pressed:** 19 in-scope cases plus 2 out-of-scope, run 3 times against live `qwen2.5:7b`
with DEMO_MODE off; median 57.9%, range 52.6–63.2% across runs; BNS offence mapping only (BNSS/BSA
are out of scope for this metric by design); ground truth is stored in the repo and human-verified,
with 5 labels still under review. Top-1, top-3 and top-5 are the same number because the tool
returns a median of one section — there is no third position.

**Do not say** "top-3 recall is 90%". The 90% is an internal candidate pool, not a shortlist the
officer sees.

---

## Part B — Determinism — **FAIL (confirmed non-deterministic)**

### Every LLM call in the section-analysis path

`map_sections()` makes up to three kinds of call, all through the single `call_llm()` choke point.

| # | Call site | File:line | temperature | top_p | top_k | seed | other |
|---|---|---|---|---|---|---|---|
| 1 | `expand_query()` — statutory restatement for retrieval | `app/ai/legal.py:119` | **0.2** (default, not passed) | not set | not set | **not set** | no `json_schema` |
| 2 | `map_sections()` — the section selection itself | `app/ai/legal.py:439` | **0.2** (default, not passed) | not set | not set | **not set** | `json_schema=SELECTION_SCHEMA` |
| 3 | `_repair_phrase()` — one-shot verbatim-quote repair | `app/ai/legal.py:392` | **0.2** (default, not passed) | not set | not set | **not set** | `json_schema=_REPAIR_SCHEMA` |
| 4 | `translate()` — only when `lang != "en"` on the `/analyze` endpoint | `app/ai/translate.py:113` | **0.1** (explicit) | not set | not set | **not set** | — |

The default lives at `app/ai/llm.py:127` — `temperature: float = 0.2`.

What is actually sent to Ollama, `app/ai/llm.py:69`:

```python
options = {"temperature": temperature}
if max_tokens is not None:      options["num_predict"] = max_tokens
if repeat_penalty is not None:  options["repeat_penalty"] = repeat_penalty
```

**That is the complete options dict.** No `seed`, no `top_p`, no `top_k`, no `num_ctx`, no
`mirostat`. A repo-wide grep for `seed|top_p|top_k|num_ctx|mirostat` across `backend/app` returns
**zero** sampling hits — every "seed" match is the database seed script (`app/seed.py`).
Neither `max_tokens` nor `repeat_penalty` is passed by the legal path, so Ollama's own defaults
apply for everything except temperature: **top_p 0.9, top_k 40, and a fresh random seed per request.**

**Is a fixed seed set anywhere? No. Nowhere in the codebase.**

### Same case, 10 identical runs

Case `theft-02-dwelling` (chosen because it flip-flopped in Round 1), byte-identical input, same
process, same warm model:

| Run | Sections returned (ranked) | Confidences | Seconds |
|---|---|---|---|
| 1 | 305, 330 | 1.0, 1.0 | 16.3 |
| 2 | 305, 330 | 1.0, 0.9 | 10.3 |
| 3 | 305, 330 | 1.0, 1.0 | 9.9 |
| 4 | **303**, 330 | 1.0, 1.0 | 10.2 |
| 5 | **303**, 330 | 1.0, 1.0 | 10.2 |
| 6 | 305, 330 | 1.0, 1.0 | 10.4 |
| 7 | **303**, 330 | 1.0, 0.8 | 10.4 |
| 8 | 305, 330 | 1.0, 1.0 | 10.3 |
| 9 | **303**, 330 | 1.0, 1.0 | 10.3 |
| 10 | 305, **331** | 1.0, 0.8 | 10.2 |

**3 distinct section sets in 10 runs:** `{305,330}` ×5, `{303,330}` ×4, `{305,331}` ×1.
The primary (305) was the top section in **6/10** runs.

The detail that matters for the demo: **the top pick carries confidence 1.0 in nine of the ten
runs, including the four where it is wrong.** The confidence score does not track correctness and
gives the officer no signal that the answer is unstable.

### What determinism would cost — analysis only, NOT implemented

| | Change |
|---|---|
| **Files that change** | `backend/app/ai/llm.py` only — one function, `_ollama_generate()` (~line 69), to add `"seed"` and set `"temperature": 0` in the `options` dict; optionally `call_llm()`'s default at line 127. |
| **Blast radius** | `call_llm()` is the single choke point, so *every* AI feature changes behaviour at once: section mapping, intake extraction, judgments, weak-charge alerts, chat routing, translation. This is a one-file change with a whole-product effect. |
| **Would it be truly deterministic?** | Ollama honours `seed` with `temperature: 0` for a fixed model + fixed prompt on the same build and GPU. Expect *stable*, not cryptographically guaranteed — batching and GPU non-associativity can still perturb rare ties. Treat it as "reproducible in practice", and re-measure rather than assume. |
| **Would it change accuracy?** | **Yes, and the direction is unknown.** Greedy decoding picks the single highest-probability path every time. On this case that path is whichever of 303/305 the model marginally prefers — locking it in could freeze in the *wrong* answer just as easily as the right one. Top-1 would stop varying (no more 52.6–63.2% spread) but the fixed value could land anywhere in or near that band. |
| **Honest recommendation** | Do it, but re-run the full 21-case eval immediately after and compare — the number you quote must come from the configuration you ship. Budget ~10 minutes of eval per configuration. |

**No change has been made.**

---

## Part C — The query-expansion call — **RESOLVED, and my Round 1 claim was wrong**

### The code

`backend/app/ai/legal.py:118-126`:

```python
    try:
        out = call_llm(prompt, system=_EXPANSION_SYSTEM)
    except Exception as exc:  # noqa: BLE001 — expansion is best-effort; never fatal
        logger.warning("query expansion failed (%s); using raw-narrative retrieval only", exc)
        return None
    if not isinstance(out, str):
        return None
    out = out.strip()
    return out or None
```

One correction to my own Round 1 wording: I called this a **silent** failure. It is not silent — it
logs at `WARNING` with the exception. It is a *non-fatal* failure that does not reach the officer.
The distinction matters because it means the failure *is* diagnosable from the backend log.

### How often it actually fires — a count, not an impression

Instrumented observationally (my harness wrapped the function to record every call and return the
original result unchanged — no behaviour change, no file edited), across the full 3-run eval:

| | |
|---|---|
| `expand_query()` calls | **63** (21 cases × 3 runs) |
| Returned `None` — failed or empty | **0** |
| Succeeded | **63** |
| Median duration | 2.67 s |
| Max duration | 7.53 s |

**It never fired once.** Zero failures in 63 calls.

Sample restatements it produced (this is what it adds to retrieval):

- *"theft of a telecommunications device from a retail establishment; unauthorized use and removal of a two-wheeler"*
- *"unauthorized entry with intent to commit theft, theft of personal property, theft of currency"*
- *"theft of personal property from a person; unauthorized taking and carrying away"*

### So what is the fallback, and is it the cause of the gap?

If it *did* fail, `retrieve_offences_union()` falls back to raw-narrative retrieval only. Round 1
measured that path directly: correct section present in the raw top-12 only **57.9%** of the time
versus **89.5%** with expansion. So the fallback is genuinely much worse — **but it is not in play.**

**As you anticipated: the gap has a different cause, and it is not retrieval at all.** The
89.5% → 57.9% drop is the **selector**. The correct section is sitting in the candidate pool and the
LLM picks a neighbouring one — 5 to 7 cases per run (table in Part A). The confusions are
systematic, not random: house-trespass (329) vs house-breaking (330/331), cheating (318/319) vs
personation (316/335), receiving stolen property (317) vs misappropriation (314), simple hurt (115)
vs grievous hurt (117). These are precisely the distinctions that turn on a legal ingredient the
7B model is not reliably reading out of the narrative.

**Revised risk statement, replacing Round 1 finding #4:** query expansion is load-bearing (it is
worth ~32 points of candidate coverage) and it is a single point of failure *by design*, but it was
100% reliable under test. The accuracy ceiling is set by the selection step, not by retrieval.

---

## Part D — The 79-second outlier — **RESOLVED**

20 back-to-back intake extractions on the locked `NARRATIVE_HOUSE_THEFT` (bilingual GU+EN, **613
chars** — confirmed), warm model, DEMO_MODE off, IPv4 + keep-alive.

### Full distribution

| Statistic | Value |
|---|---|
| min | **11.45 s** |
| median | **13.45 s** |
| p90 | **18.13 s** |
| max | **127.59 s** |

All 20 runs: 12.36, 13.16, 11.45, 13.90, 14.20, 13.31, 11.96, 11.95, 13.58, 15.22, 14.10, 12.21,
12.43, 18.13, 14.38, 15.17, 19.23, 11.95, **127.59**, 13.13.

**Runs over 30 s: exactly one — run 19, at 127.59 s.**

### Cause — identified, with a 1:1 correlation

The harness watched the backend log for a new `bad JSON; retrying once with fix reprompt` warning
after each run.

**Run 19 is the only run over 30 s, and it is the only run in which the JSON-fix retry fired.**
Perfect correlation, 1 for 1.

The mechanism is in `app/ai/llm.py:186-204`. When the model returns unparseable JSON, `call_llm`
builds a repair prompt that embeds **the entire broken output** and re-generates:

```python
fix_prompt = ("The following text was supposed to be valid JSON but is not. ...\n\n"
              f"Schema:\n{json.dumps(json_schema, ...)}\n\n"
              f"Broken output:\n{raw}")
```

Intake extraction runs with `max_tokens=3000` (`app/ai/intake.py:463`), so the first generation can
be long, and the retry then re-processes that entire long output as *input* plus generates a fresh
long output. That is why the penalty is ~10× the median rather than 2×.

This also explains Round 1's 79 s outlier: the backend log for the whole of Round 1 contains
**exactly one** `bad JSON; retrying once` warning — the same signature, the same single event.

### The eviction hypothesis — tested and ruled out

Controlled experiment: unloaded `qwen2.5:7b` from VRAM (`keep_alive: 0`), confirmed with `/api/ps`
that no model was resident, then timed an extraction on the cold model.

| | |
|---|---|
| Models resident before unload | `qwen2.5:7b`, 4,748,056,984 bytes **fully in VRAM** |
| Models resident after unload | **none — evicted** |
| Intake extraction on the **cold** model | **18.55 s** |
| Immediately after, warm again | **11.64 s** |
| **Model reload penalty** | **≈ 6.91 s** |

**A full reload from cold costs about 7 seconds. It cannot produce a 79 s or 128 s run.**
Eviction is not the cause. GPU memory pressure is also ruled out: `size_vram` equals the full model
size, so the model is 100% GPU-resident with no CPU spill.

### Ollama keep-alive configuration, as requested

| | |
|---|---|
| `OLLAMA_KEEP_ALIVE` env var | **not set** — at process, user, or machine level |
| Effective keep-alive | **Ollama's default, 5 minutes** (confirmed: `/api/ps` reports a rolling `expires_at` ~5 min ahead) |
| Does the app override it? | **No** — `_ollama_generate()` sends only `model`, `prompt`, `stream`, `options`; no `keep_alive` key |
| Model context length | 4096 |

So the model *is* evicted after 5 idle minutes, and the next call pays ~7 s. For a demo with pauses
between steps that is worth pinning, even though it is not the outlier cause. Setting
`OLLAMA_KEEP_ALIVE=-1` (or `24h`) in the Ollama service environment holds the model in VRAM
indefinitely. **I have not set it** — it is an environment change, outside the authorised scope.

### What this means for the demo

The tail risk is **not** solvable by keep-alive. It is a ~1-in-20 chance that the model emits
malformed JSON on intake and the repair path costs ~2 minutes. Options, for your decision:
run intake with DEMO_MODE on (the cache makes it instant and deterministic); or accept a 5%
chance of a two-minute pause. **Nothing changed.**

---

## Part E — Gujarati `.docx` rendering — **PASS, and my Round 1 inference was wrong**

I inferred tofu risk in Round 1 from a missing embedded font. I verified it properly this time and
the inference was wrong in the direction that matters — **it renders.**

### 1. All 8 documents generated in Gujarati

All 8 returned HTTP 200 on case 67 (`HCT-203320-TIMING`, fully populated).

### 2. What is actually in the XML

Identical across all 8 documents:

| Property | Finding |
|---|---|
| Fonts referenced in `word/document.xml` (`w:rFonts`) | **`Noto Sans Gujarati`** — and nothing else |
| Font applied to the runs that carry Gujarati characters | **`Noto Sans Gujarati`** |
| `word/fontTable.xml` `w:name` entries | none |
| **Embedded font parts** (`word/fonts/*.odttf`) | **NONE — confirmed, no font is embedded** |
| `w:embedRegular` / `w:embedBold` tags | **NONE** |
| Gujarati text present as correct Unicode (U+0A80–U+0AFF) | **Yes** — Seizure 587, Panchnama 654, Remand 959, Custody 684, Chargesheet 1285, Medical 474, LERS-P 892, LERS-R 905 codepoints |
| Mojibake | **None detected in any of the 8** |

So the Round 1 structural finding stands: **the `.docx` is not self-contained.** It names a font it
does not carry.

### 3. Rendered to PDF and inspected — what I actually saw

LibreOffice is **not installed** on this machine. **Microsoft Word (COM, version 15.0) is**, so I
rendered with Word itself — which is a better test than LibreOffice, because Word is what an officer
or judge would open the file with.

Method: Word COM, `Documents.Open` → `ExportAsFixedFormat(wdExportFormatPDF)`, headless
(`Visible=false`, `DisplayAlerts=0`). Rendered `PANCHNAMA_gu.docx` and `CHARGESHEET_gu.docx`.

**The decisive fact: `Noto Sans Gujarati` is NOT installed on this machine.** So this render *is* the
missing-font scenario, not a lucky one. What Word embedded in the resulting PDF:

```
PANCHNAMA_gu.pdf   /BaseFont entries:  ABCDEE+Cambria, ABCDEE+Shruti, ABCDEE+Shruti-Bold,
                                       TimesNewRomanPSMT, TimesNewRomanPS-BoldMT
CHARGESHEET_gu.pdf /BaseFont entries:  ABCDEE+Cambria, ABCDEE+Cambria-Bold, ABCDEE+Shruti,
                                       ABCDEE+Shruti-Bold, TimesNewRomanPSMT, TimesNewRomanPS-BoldMT
```

**Word silently substituted `Shruti` and embedded a subset of it** (the `ABCDEE+` prefix is a subset
tag — Word only subsets glyphs it actually drew). The Gujarati was rendered with real glyphs.

I could not rasterise the PDF (no poppler/PyMuPDF available), so I verified glyph rendering directly
instead: I took the actual Gujarati string out of the generated Panchnama
(`પંચનામુંપોલીસ સ્ટેશન`) and rendered it with each candidate font plus a deliberate control, then
looked at the image.

**What I saw** (`scratchpad/gu_docs/gujarati_font_comparison.png`):

| Font | Installed here | Result I observed |
|---|---|---|
| Noto Sans Gujarati — what the `.docx` asks for | **NO** | cannot render, font absent |
| **Nirmala UI** — ships with Windows | yes | **Gujarati renders correctly**, conjuncts and matras well-formed |
| **Shruti** — ships with Windows, and what Word chose | yes | **Gujarati renders correctly** |
| Arial — deliberate tofu control, no Gujarati coverage | yes | **19 empty rectangles — textbook tofu** |

The control matters: it proves the method can detect tofu, and that what the other two rows show is
genuinely not tofu.

### 4. Which font must be installed, and is it on a default Windows install?

| | |
|---|---|
| Font the document requests | `Noto Sans Gujarati` — **not required in practice**, and not present on this machine |
| Font actually used by Word here | **`Shruti`** |
| Fonts on this machine that cover Gujarati | `Shruti` (`shruti.ttf`, `shrutib.ttf`) and `Nirmala UI` (`Nirmala.ttc`, `NIRMALA.TTF`, `NIRMALAB.TTF`) — both in `C:\Windows\Fonts`, both Microsoft-shipped Windows Indic fonts |
| On a default Windows install? | **Yes.** Nirmala UI is a default Windows 8+ system font and Shruti has shipped with Windows Indic support since XP. Both were present on this stock Windows 11 machine without anyone installing them |

**Correction to Round 1:** I wrote that Gujarati renders here "because Noto Sans Gujarati is
installed". That was wrong — **it is not installed anywhere on this machine.** Shruti did the work
via Word's font fallback.

**Residual risk, stated honestly and now much smaller:** the substitution is Word's, not yours, so
the *typeface* is not what the template designer chose — Shruti instead of Noto Sans Gujarati, which
will look slightly different from the Gujarati you have been reviewing. On a non-Windows machine
(macOS Pages, Google Docs, a Linux box with no Indic fonts) the fallback may differ or fail, and I
did not test those. **On Windows with Word, the tofu risk is not real.** I did not verify page
layout — see Part G.

---

## Part F — Server-side step-up PIN enforcement — **NOT IMPLEMENTED, AWAITING GO-AHEAD**

As instructed, analysis first. No code has been written.

### How step-up state is represented today, and whether the server can verify it

I traced the whole path. The answer is blunt:

| Question | Finding |
|---|---|
| What does `POST /api/auth/verify-pin` return? | `{"ok": true, "reason": null, "attempts_remaining": null}` — **a boolean and nothing else** (`app/api/auth.py:161-191`) |
| Does it issue a token, cookie, or ticket? | **No.** |
| Does it record anything server-side? | **No.** It writes nothing to the database and stores nothing in memory. The only in-memory state in that module is `_pin_failures`, which counts *failures* and is cleared on success. |
| Where does "this session is stepped up" actually live? | **Entirely in the browser.** `markPinVerified()` → `setStepUpVerified()` → `sessionStorage["<STEPUP_KEY>"] = "1"` (`frontend/lib/api.ts:155-157`), plus React state `pinVerified` in `AuthProvider`. Cleared by `clearToken()` on logout; dies with the tab session. |
| Is anything sent to the server on the protected write? | **No.** `POST /api/intake/commit` and `POST /api/documents/{id}/finalize` receive only the normal `Authorization: Bearer <jwt>` header. |
| Does the JWT carry a step-up claim? | **No.** Payload is `{"sub": <user id>, "role": <role>, "exp": <+12h>}` (`app/core/security.py:24-32`). No `jti`, no `amr`, no step-up marker. |

**Conclusion: there is currently no server-verifiable representation of step-up whatsoever.** The
server cannot check it today because nothing exists to check. Enforcing it requires *introducing* a
representation — which is why this is additive rather than a wiring fix.

### Proposed approach — 5 lines

1. On a successful `verify-pin`, record the step-up server-side in an in-process dict keyed by a SHA-256 of the presented bearer token, with an expiry — mirroring the existing `_pin_failures` pattern in the same module, so no schema change and no new dependency.
2. Add one FastAPI dependency, `require_step_up`, that looks up that record for the caller's token and raises a uniform `401` when it is missing or expired.
3. Apply it to exactly two endpoints — `POST /api/intake/commit` and `POST /api/documents/{doc_id}/finalize` — and nowhere else; the mobile `/m` path reaches `commit` too, so it is exempted by allowing tokens minted by `login-pin` (where the PIN *was* the sign-in) to satisfy the check.
4. On rejection, write an `audit_log` row (`entity_type="auth.step_up"`, the attempted action, the user) and return before any write begins, so nothing is persisted and the PIN itself is never logged.
5. Tie validity to the token's own lifetime (12 h, bounded by JWT `exp`) so "once per session" matches the browser's `sessionStorage` semantics exactly and the existing UI keeps working with **zero frontend changes**.

### Two things I need you to decide, because they change the design

- **Point 3, the mobile exemption.** `/m` calls the *same* `POST /api/intake/commit`. To leave the mobile path working while enforcing on desktop, the server must distinguish them. The only clean signal available is how the token was minted, so `login-pin` tokens would need a marker claim — which means touching `create_access_token`/`login_pin`. **If you would rather I not touch the token at all, the alternative is to exempt nothing and accept that `/m` register would break** — tell me which.
- **Point 1, in-process state.** It is per-worker and clears on restart (fail-closed, so safe). That matches how `_pin_failures` already works and needs no migration. A DB-backed alternative survives restarts and multiple workers, but is a schema change close to the demo.

**Estimated blast radius:** `app/api/auth.py` (record + dependency), `app/api/intake.py` (one
dependency added), `app/api/documents.py` (one dependency added). Roughly 60 lines, no migration,
no frontend change. I will not touch the browser gate or `/m`'s page code.

**Waiting for your go-ahead before writing any of it**, and for your answer on the mobile exemption.

---

## Part G — Your manual checklist for tonight

From the Round 1 "DID NOT TEST AND WHY" list, these genuinely need a human at a browser. Parts E
and C removed two others from the list; the rest are below.

**Desktop, at `http://localhost:3000`**

1. **Step-up PIN dialog** — Cases → new intake → fill a case → click **Register**. *Pass:* a PIN box appears before anything is written; typing `1234` registers the case, and Cancel leaves no new case in the list.
2. **Wrong PIN does not kill your session** — at that PIN box type `0000`. *Pass:* an inline error appears and **you stay on the page** — you are not bounced to the login screen.
3. **SHO finalize gate** — log in as `sho`/`sho123`, open a case → Documents → **Finalize** a draft. *Pass:* PIN box appears once; after `4321` the document flips to FINALIZED, and a second finalize in the same session does **not** ask again.
4. **Gujarati UI toggle** — click **ગુ** in the top bar, then reload the page. *Pass:* the whole interface is Gujarati and **stays** Gujarati after reload.
5. **Triggering-phrase highlight** — open case 1 → Legal sections → **Analyse**. *Pass:* the narrative is shown with the quoted phrase visibly highlighted, and the highlighted words appear word-for-word in the complaint text.
6. **Consistency display** — AI Analysis → **Consistency check** on a case whose accused you have renamed since generating documents. *Pass:* a high-severity `accused_name` row appears naming the documents that disagree.
7. **Version history** — Documents → regenerate any document → open its **version history**. *Pass:* version numbers increase and each entry shows a field-level diff against the previous one.
8. **Chat confirmation gate** — in case chat type *"generate the seizure receipt"*. *Pass:* it asks you to confirm and creates **nothing** until you click confirm.
9. **Idle logout** — sign in, then leave the tab untouched for 15 minutes (or set `NEXT_PUBLIC_IDLE_TIMEOUT_SECONDS=30` in `frontend/.env.local` for a fast check). *Pass:* a warning appears ~60 s before the deadline, then you are signed out and land on the login screen.

**On a real phone, on the station Wi-Fi, at `http://192.168.29.188:3000/m`**

10. **Mobile field capture** — sign in with `io` / PIN `1234`, dictate or type an incident, review the draft, tap **Register case**. *Pass:* it registers, and **no PIN is asked a second time** at Register. Then confirm the case appears on the desktop case list.
11. **Mobile idle logout** — leave `/m` untouched for 15 minutes. *Pass:* you are signed out and returned to the PIN screen with a "signed out" notice.

**In Word, not a browser**

12. **Open one Gujarati `.docx`** — I have left eight in `scratchpad/gu_docs/`, or generate fresh ones. Open `CHARGESHEET_gu.docx` in Word. *Pass:* Gujarati text is legible (not empty boxes) **and** the Form I table is not broken — no cells overflowing the page, no text clipped. I verified the glyphs render; **I did not verify page layout**, and that is what you are looking at.

**Not a browser, but only you can do it**

13. **The 5 open ground-truth calls** in `data/eval/GROUND_TRUTH_REVIEW.md` — `mischief-01-crop-fire` (324 vs 326), `hurt-01-simple` (115 vs 117), `cbt-01-money` (316 vs 315), `cbt-02-goods` (316 vs 314), `trespass-01-house-trespass` (329 vs 330). These are legal judgements reserved to you, and three of them currently score 0/3, so your ruling moves the headline accuracy number.

---

## Stated as unknown, not guessed

- **Whether locking `temperature=0` + a fixed seed helps or hurts accuracy.** Direction unknown until measured. I did not make the change.
- **Whether the Gujarati `.docx` renders on non-Windows** (macOS Pages, Google Docs, Linux without Indic fonts). Not tested; only Windows + Word was available.
- **Page layout fidelity of the generated documents.** I verified text, fields and glyphs; I did not visually inspect table layout or pagination (no PDF rasteriser available). Item 12 above.
- **Why the model emits malformed JSON on roughly 1 intake in 20.** I identified the retry as the cost, not the trigger. The broken output is not captured anywhere I can read after the fact — diagnosing the trigger would need the raw response logged, which is a code change.
- **Whether the 5-minute Ollama eviction ever bites during a real demo.** It costs ~7 s when it does; whether your demo has 5-minute gaps is a question about the script, not the system.
- **Whether step-up enforcement should exempt the mobile path via a token claim** — design decision returned to you in Part F.

---

*Round 2 generated 17 August 2026 against commit `95665e88a47348cc222a5c03cebca9bd7a992805` on `main`.
Parts A–E read-only; nothing fixed, nothing deleted, nothing committed. DEMO_MODE restored to `true`.
Part F awaiting approval.*
