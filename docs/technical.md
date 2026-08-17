# CrimeGPT — Technical Reference

This document describes what CrimeGPT does, how each part works, what has been measured,
and what does not work yet. It is written to be checked rather than believed. Every number
here traces to a measurement recorded in the audit reports linked at the end.

For the officer-facing walkthrough see [user-guide.md](user-guide.md). For the layered
design and request flow see [architecture.md](architecture.md).

---

## 1. What the system is

CrimeGPT is an on-premise web application for Indian police. One structured case entry
becomes the source of truth for every required document, the legal sections that apply, and
the case diary. It runs entirely inside the police network. No case data leaves the station.

The whole product rests on one rule: **enter each fact once**. Persons, seized items,
evidence and statements are written to a shared pool, and every document reads from that
pool at generation time. No field is typed twice.

---

## 2. The five-layer stack

| Layer | What it is | Technology |
|---|---|---|
| **L1 Presentation** | Browser UI: login, dashboard, case workspace, conversational intake, mobile field page, analysis, audit | Next.js 14, React 18, TypeScript, Tailwind |
| **L2 API and auth** | 48 endpoints, JWT validation, RBAC role gates, step-up PIN enforcement | FastAPI, python-jose, passlib/bcrypt |
| **L3 Services** | Document generation, cross-document consistency, CCTNS IIF mapping, audit and diary writes | docxtpl, python-docx |
| **L4 AI and legal core** | `call_llm()` choke point, RAG retrieval, grounding validator, transcription, translation | Ollama (Qwen 2.5 7B Q4), sentence-transformers, faster-whisper |
| **L5 Data** | Unified Case Data Pool, vector store, generated files, local infrastructure | PostgreSQL 15 (Docker), ChromaDB, local filesystem |

Every LLM call goes through `call_llm()` in L4. Feature code never calls Ollama directly.
That gives one place to route between Ollama and the API fallback, enforce JSON output,
retry once on malformed JSON, and serve cached outputs in `DEMO_MODE`.

---

## 3. API surface

**48 endpoints**, counted as path by method from the live `/openapi.json`, excluding
`/health`, `/health/db`, `/docs`, `/openapi.json` and `/redoc`.

| Tag | Count | What it covers |
|---|---|---|
| `pool` | 16 | Persons, seized items, statements, evidence upload and serving, diary, transcription |
| `documents` | 6 | Generation, listing, download, version history, finalize, consistency |
| `legal` | 6 | Section analysis, accept/reject, judgments, weak-charge alerts |
| `auth` | 5 | Login, current user, register, step-up PIN verify, mobile PIN login |
| `cases` | 5 | Create, list, search, detail, update |
| `chat` | 3 | Intent routing, missing-field split, field answers |
| `intake` | 2 | Conversational extraction and commit |
| `integrations` | 2 | CCTNS export and mock receiver |
| `system` | 2 | Read and toggle `DEMO_MODE` |
| `audit` | 1 | Paginated audit trail |

---

## 4. Document generation

Eight document types generate end to end, each from a Word template with `{{ jinja }}`
placeholders:

1. Seizure Receipt (CCTNS Form IF4 layout)
2. Panchnama
3. Remand Request (police custody)
4. Court Custody Letter (judicial custody)
5. Medical Treatment / Examination Letter
6. LERS Preservation Request
7. LERS Records Request
8. Final Form / Report (BNSS §193), Form I, with `report_type=original` or `supplementary`

All eight render in English, Hindi and Gujarati. The Accused Face Identification Form is an
enum value with no template and does not generate.

**There is no LLM in the document path.** Every narrative sentence is assembled
deterministically from per-language label templates in `templates/_labels.py`, with
identifiers substituted verbatim. This is why generation is fast and repeatable, and why a
document never contains invented text.

Regeneration is version-aware. The current state is archived into `document_versions` and
the same row is bumped to a new draft version. Nothing is silently overwritten.

Missing pool data produces a 400 listing the exact missing fields, not a document with
blanks. On a case with no persons, items or sections, all eight refuse, and
`police_station` is the single most common blocker.

---

## 5. Legal section mapping

The signature flow. A raw 7B model hallucinates section numbers, so the design never trusts
model output directly.

```
narrative
   |
   +-- (1a) retrieve BNS candidates by cosine similarity on the raw narrative
   +-- (1b) LLM restates the complaint in statutory terms, retrieve again
   |        union, de-duplicated -> 17 to 24 real candidate sections
   |
   +-- (2)  LLM selects ONLY from those candidates and must quote a
   |        triggering phrase verbatim from the narrative
   |
   +-- (3)  grounding validator drops any section outside the candidate set,
   |        and any phrase not found literally in the narrative
   |        one repair attempt is allowed for a bad phrase, not a bad section
   |        a relevance floor drops weakly-related survivors
   |
   +-- (4)  persist as SUGGESTED, officer accepts or rejects
```

Step 1b matters more than it looks. Raw retrieval on the officer's own words is weak,
because a complaint says "the scooter was missing" while the statute says "dishonestly
moves that property". Measured over three runs, the correct section is present in the
candidate set **89.5%** of the time with the restatement step, and **57.9%** without it.

Only accepted sections flow into documents.

---

## 6. Conversational intake and chat

Two separate surfaces, both of which propose and never write on their own.

**Intake** (`POST /api/intake/extract`, `POST /api/intake/commit`). The officer describes an
incident in plain language and the system returns a structured draft: case header, persons,
seized items. `/extract` takes no database session at all, which is the mechanical proof
that it cannot persist anything. `/commit` writes the case, its persons and its items in one
transaction, so a failure leaves nothing half-registered.

**Chat** covers four capabilities:

1. **Intake from narrative.** Entities extracted into the pool draft.
2. **Document generation by request.** `chat/route` classifies the message and returns a
   label such as `GENERATE` with a `doc_type`. It does not generate. The caller then uses the
   same documents endpoint the Documents tab uses, so there is only one generation path.
3. **Missing-field prompting.** `chat/missing` splits a checklist into what the officer can
   answer here, what belongs to another surface, and what is unrecognised.
4. **Case query.** Questions about what is already recorded return a `QUERY` intent.

The chat returns **labels from a closed set, never prose**. The sentence the officer reads
is composed by the UI from its own translated strings. The model therefore has no channel
through which to state law or offer an opinion. Asked "is he guilty?" or "is this a strong
case?", the API returns `{"intent":"UNKNOWN","source":"guard"}` and the UI declines.

---

## 7. Mobile field capture

`/m` is a purpose-built one-column page for a phone on the station LAN, not the desktop UI
shrunk.

- **PIN sign-in.** `POST /api/auth/login-pin` takes a username and PIN and issues the same
  JWT as the password login, so every endpoint and RBAC rule applies unchanged. Failures
  return one uniform 401 for every cause, run a bcrypt verify even when no account exists so
  timing cannot enumerate usernames, and lock out for five minutes after five attempts.
- **Capture only.** The page's entire API surface is three calls: `login-pin`,
  `intake/extract`, `intake/commit`. There is no document generation, chat or legal analysis
  reachable from it.
- **Shared pool.** A case registered on a phone is written by the same `/intake/commit` the
  desktop uses. It appears in the desktop case list and the SHO supervision view immediately.
- **Idle sign-out** is active on `/m` as on the desktop.

---

## 8. Security model

**Authentication.** Local JWT, 12-hour expiry, bcrypt password hashes. Accounts are created
by an admin or the seed script. There is no self-signup.

**Authorization.** Three roles, gated at the endpoint and hidden in the UI. IO creates and
edits cases and pool data and sees only their own cases. SHO sees every case and can
finalize documents. Legal Advisor reviews sections and judgments and cannot alter evidence.
An IO requesting a case they do not own receives a 404, so the case's existence is hidden.

**Step-up PIN.** High-stakes writes require a fresh proof of identity beyond the session
token. This is enforced **server-side**, not only in the browser:

- **Case register** requires a step-up, except on the mobile path where the PIN was itself
  the sign-in. Asking again seconds later would be ceremony rather than security.
- **Document finalize** requires a step-up with **no exemption at all**. An SHO can sign in
  on a phone with four digits, so exempting finalize would let four digits approve a
  document.
- A refusal is a uniform 401, is audited with the attempted action, and happens before the
  endpoint body runs, so nothing is written. The PIN itself is never logged.

**Idle auto-logout.** An unattended terminal is a way into the case file. The session ends
after inactivity, configurable without a code change:

| Variable | Default | Meaning |
|---|---|---|
| `NEXT_PUBLIC_IDLE_TIMEOUT_MINUTES` | 15 | Session lifetime with no activity |
| `NEXT_PUBLIC_IDLE_TIMEOUT_SECONDS` | 0 | Overrides the minutes value when above 0 |
| `NEXT_PUBLIC_IDLE_WARNING_SECONDS` | 60 | Warning before sign-out, capped at half the timeout |

A request in flight holds the session open, because the officer is waiting rather than
absent, but only for two minutes, so one hung connection cannot disable the safeguard.

**Audit trail.** Every create, update and delete writes an `audit_log` row with the entity,
the action, field-level old and new values, the performing officer and the timestamp.
Combined with the automatic case diary and per-document version history, this gives a
reviewable record of who did what and when.

---

## 9. Measured performance

Hardware: RTX 4060 (8 GB). All figures are **5-run medians with the demo cache off**, taken
over a keep-alive connection to `127.0.0.1`, on the warm model.

| Operation | Median | Range |
|---|---|---|
| Intake extraction, **613-char** bilingual Gujarati and English narrative | **14.1 s** | 12.0 s to 137.5 s |
| Intake extraction, **384-char** English narrative | **9.7 s** | 9.5 s to 10.1 s |
| Section analysis, live | **7.8 s** | 7.6 s to 7.8 s |
| Document generation, each of the eight | **89 ms** | 82 ms to 103 ms |

**Language dominates, not length.** The bilingual Gujarati narrative is 1.6 times the length
of the English one but takes 1.5 times as long at the median, and the gap is driven by
script rather than characters: Gujarati consumes far more tokens per character than Latin
text. A longer English complaint would not cost proportionally more.

**Document generation is fast because there is no LLM in that path.** All eight types are
comfortably under the 0.12 s target, and the figure is stable because the work is template
rendering, not inference.

**The upper end of the intake range is not noise.** See the slow tail in section 11. One run
in five during this measurement took 137.5 s and then failed.

Provenance: the two intake figures were measured on 18 August 2026. Section analysis and
document generation are from the round 2 audit, measured the same way. Nothing in either
path has changed since.

**A note on measuring this yourself.** On Windows, `localhost` resolves to IPv6 `::1` first
and uvicorn binds IPv4, so every new connection stalls about two seconds before falling
back. Measure against `127.0.0.1` with a keep-alive connection, or you will be timing the
resolver rather than the application.

---

## 10. Measured accuracy

On our 21-case held-out test set, CrimeGPT puts the correct BNS section in front of the
officer **58% of the time**, and the correct section is in the candidate list it chooses
from **90% of the time**.

Scope, stated so the number cannot be over-read: 19 in-scope cases plus 2 out-of-scope, run
three times against live `qwen2.5:7b` with `DEMO_MODE` off, BNS offence mapping only. Ground
truth is stored in the repository at `data/eval/section_eval.json` and was human-verified
against the bare acts.

**Guardrails, independently re-verified:**

| Guardrail | Result |
|---|---|
| Grounding validator: cited sections outside the retrieved candidate set | **0 violations** across 3 full runs |
| Verbatim-quote guardrail: triggering phrases not present in the narrative | **0 violations** across 3 full runs |

These were checked by capturing the candidate set for every call and re-testing every
returned section independently of the application's own validator.

**Out-of-scope refusal.** The system returns `no_grounded_match` rather than inventing a
section when nothing clears grounding. We do not publish a refusal percentage: the
out-of-scope portion of the eval set is two cases, which cannot support one. No genuine
in-scope complaint was refused in any run.

**Confidence is not displayed.** The model emits a self-reported confidence value, which is
retained in the database and API for regression measurement, but it is not shown to the
officer. Measured across 65 displayed sections, 96.3% of **wrong** sections scored 90% or
above and a third of them reported exactly 100%. A number that high on a wrong answer invites
misplaced trust, so it was removed from the interface.

---

## 11. Known limitations, stated openly

These are real. They are listed because a system used in police work should be judged on what
it does not do as much as on what it does.

**Section selection is not deterministic.** No seed is set anywhere, and sampling
temperature is 0.2. The same complaint, run ten times, produced **three distinct section
sets**. The top pick reported confidence 1.0 in nine of those ten runs, including runs where
it was wrong, which is why that number is no longer displayed. The design answer is that the
officer accepts or rejects every section. The system proposes. It does not decide.

**Intake extraction has a slow tail, and it can fail outright.** Roughly one call in twenty,
the model returns malformed JSON and `call_llm()` retries once with a repair prompt that
re-sends the entire broken output. Measured over 20 runs: median 13.45 s, p90 18.13 s, and
one run at **127.59 s**. The slow run correlated one to one with the retry. Model eviction was
ruled out by a controlled test: a cold reload costs about 7 seconds, which cannot explain it.

Re-measuring on 18 August 2026 reproduced it in a worse form. One run of five took **137.5 s
and then returned HTTP 422**, meaning both the first parse and the repair attempt failed and
the officer would have waited more than two minutes for an error. So the tail is not only
slow, it is sometimes a failure. The endpoint degrades honestly (422 tells the officer to
retry or type it manually rather than inventing a draft), but the wait is real. This is the
strongest argument for running the demo with `DEMO_MODE` on, where the intake step is served
from cache.

**The system does not judge whether an input describes an offence.** It maps a complaint to
grounded sections, or it returns `no_grounded_match`. It does not decide "this is not a
crime". That gate was built twice and reverted twice, and the evidence is preserved on the
`feat/crime-gate` branch. A 7B model cannot reliably make that categorical judgment on
speech-act offences such as criminal intimidation or extortion, where the offence is
constituted by words rather than physical acts. Worse, its errors are asymmetric: it fails
toward charging rather than toward turning a complainant away. Refusing a genuine complainant
at the station counter is a more serious failure than surfacing a section an officer then
rejects, so the capability stays out until it can be made reliable.

**Three open authentication findings**, known and not yet closed:

1. There is no endpoint an IO may call that an SHO may not. RBAC is strictly hierarchical by
   design, so the asymmetry cannot be demonstrated.
2. A wrong step-up PIN returns HTTP 200 with `ok:false`, not a uniform 401. This is
   deliberate, because the frontend treats any 401 as a dead session and a typo would
   destroy an in-progress draft. It does not match the stricter reading of the requirement.
3. The step-up PIN lockout is 60 seconds, not 5 minutes. The 5-minute window applies to the
   mobile PIN login only.

**The evaluation set is small and single-annotator.** 21 cases, 19 in-scope, labelled by one
project member and verified against the bare acts by the same person. Five ground-truth calls
remain open where the model's pick may be more defensible than the label. At this size, one
case changing its mind moves the headline by about five points, so treat the accuracy figure
as an indication rather than a precise measure.

**The fresh-machine setup path has never been executed.** `setup.ps1` and `setup.sh` were
extended and reviewed, and the new branches were dry-run against a working machine, but the
clean-install path (virtual environment creation, dependency install, the 4.7 GB model pull,
the cold ChromaDB build, creating configuration from nothing, creating firewall rules while
elevated) has not been run start to finish on a clean Windows machine. Until it has, treat it
as written and reviewed, not proven.

**Other standing limitations.** Judgment citations are grounded in a small curated corpus and
paraphrased, so they are a prompt to verify rather than confirmed law. The CCTNS export
targets a local mock receiver, not a live gateway. Documents export as `.docx` only, with no
PDF path. The legal corpus covers BNS, BNSS and BSA only, with IPC and CrPC cross-references
from a curated table rather than a corpus.

---

## 12. Verification

The install can be proved rather than assumed:

```powershell
.\start.ps1          # or .\start.ps1 -Lan for phone access
.\verify.ps1         # read-only by default
```

`verify.ps1` prints PASS or FAIL with a fix line for each failure, covering dependencies via
`scripts/preflight.py` (Postgres, migrations at head, seed, ChromaDB at 1,059 sections,
judgments at 41, Ollama serving `qwen2.5:7b`), the backend on `127.0.0.1`, the frontend on
3000, all three roles signing in, the LAN mobile page, the live model-eviction deadline, and
the resolved `DEMO_MODE`. Passing `-FullCheck` adds two checks that write: one document
generated end to end, and a commit without a step-up returning 401.

See [../SETUP.md](../SETUP.md) for installation.

---

## 13. Audit reports

The system was audited in two read-only passes. Both measure commit `95665e8` and carry
their own status headers mapping fixed findings to the commits that closed them.

- [health-check-2026-08-17.md](health-check-2026-08-17.md) — endpoint count, feature
  inventory across two independent runs, accuracy, timings, test-pool hygiene, repository
  consistency.
- [health-check-round2-2026-08-17.md](health-check-round2-2026-08-17.md) — reconciles the
  accuracy metrics to one pipeline stage, determinism, the query-expansion call, the slow-tail
  investigation, and Gujarati rendering.

Both list what was not tested and why. Neither has been browser-verified, and both say so.
