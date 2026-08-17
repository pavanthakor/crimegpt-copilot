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
> | Step-up PIN was a browser-side gate only; `POST /api/intake/commit` and `POST /api/documents/{id}/finalize` accepted a bare JWT | **`495a34a`** — server-side enforcement on case register and SHO finalize, with the mobile exemption scoped to commit only |
> | Setup gaps: no LAN config for `/m`, no RAG corpus build, no firewall rules, `OLLAMA_KEEP_ALIVE` unset, and READY printed without proving anything | **`8ae9f60`** — `verify.ps1` plus extended `setup.ps1`/`setup.sh` (LAN config, RAG ingest, port firewall rules, keep-alive, read-only `preflight.py`) |
> | Gujarati font warning cried wolf on a machine that renders correctly | **`8ae9f60`** — replaced; now checks for any Gujarati-capable font. See Round 2 Part E for the render evidence |
> | `DEMO_MODE` left ambiguous by the setup script | **`8ae9f60`** — resolved value and its effect printed in READY |
>
> **Deliberately still open, not fixed:** section-selector non-determinism (3 distinct
> outcomes in 10 identical runs; no seed is set anywhere — determinism is a separate
> decision, deferred), the ~1-in-20 JSON-repair retry tail on intake extraction (127 s
> worst case, cause identified in Round 2 Part D), and the three pre-existing auth
> findings — no IO-exclusive endpoint (RBAC is hierarchical by design), wrong PIN returns
> 200 rather than a uniform 401 (deliberate, to avoid killing the session), and the
> step-up lockout is 60 s rather than 5 minutes.
>
> Two Round 1 claims were **retracted** in Round 2 after re-measurement: the
> query-expansion call never actually failed (0 failures in 63 calls), and the Gujarati
> tofu risk does not materialise on Windows. See Round 2, Parts C and E.

# CrimeGPT — health check, 17 August 2026

**Commit under test: `95665e88a47348cc222a5c03cebca9bd7a992805`**
Branch: `main` (confirmed via `git branch --show-current`)
Working tree: **clean before and after** this audit (`git status --porcelain` empty both times).
Every result in this report belongs to that SHA.

This audit was **read-only and measurement-only**. No project file was created, edited, renamed or
deleted except this report. Nothing was committed, no branch was created, nothing was fixed.
All harness scripts were written to a scratchpad outside the repo.

## Environment

| Item | Value |
|---|---|
| Backend launch | `python -m uvicorn app.main:app --host 0.0.0.0 --port 8000` from `backend/.venv` — **never bare `uvicorn`** |
| Python | 3.13.7 (venv), `docxtpl` 0.20.2, `fastapi` 0.141.1, `chromadb` 1.5.9 |
| Frontend | `npm run dev -- --port 3000` → **port 3000**. Port 3001 was free; no orphaned Next child existed (no `node`/`python` processes were running at start) |
| Database | Postgres in Docker (`crimegpt-copilot-db-1`). Docker Desktop was **not running** at audit start and had to be started; the container existed but was `Exited (0) 8 days ago` |
| Ollama | v0.32.14, reachable on `:11434` |
| GPU | RTX 4060 (8 GB) |

### DEMO_MODE handling — restored, confirmed

`backend/.env` was **never edited**. Its original value `DEMO_MODE=true` is still on line 5, byte-identical.
To measure with DEMO_MODE off I passed `DEMO_MODE=false` as a *process* environment variable at launch
(pydantic-settings gives env vars precedence over the `.env` file), so the file on disk was untouched throughout.

- Every accuracy and timing figure below was taken with `GET /api/system/demo-mode` returning `{"demo_mode": false}` — asserted in-harness before recording.
- At the end of the audit the running server's runtime flag was set back to `true` via `PATCH /api/system/demo-mode`, verified `{"demo_mode": true}`.
- **DEMO_MODE is restored to its original value (`true`) in both the config file and the running process.**

### One correction to my own method, disclosed up front

My first timing pass reported ~2.1 s per document. That was **an artefact of my test client, not the product.**
`localhost` resolves to IPv6 `::1` first on this Windows host, uvicorn was bound IPv4-only, so every *new*
connection stalled ~2.04 s before falling back to `127.0.0.1`. `GET /health` — which does no work at all —
also cost 2043 ms, which is what exposed it. Re-measured over a keep-alive session on `127.0.0.1`, the same
call is 89 ms. All Part 4 numbers below are from the corrected run. A browser holds a keep-alive connection
and never pays this, and the frontend is pointed at the LAN IPv4 address anyway.

---

## Part 1 — Startup and wiring

| # | Check | Result | Evidence |
|---|---|---|---|
| 1.1 | Clean start, backend via venv `python -m uvicorn` | **PASS** | `INFO: Started server process [2932]` → `Application startup complete` → `Uvicorn running on http://0.0.0.0:8000`. No warning or error of any kind at startup. Cold boot takes **>30 s** (heavy `chromadb`/`sentence-transformers` imports) — a health probe at 12 s and again at 30 s both failed before it came up |
| 1.2 | Frontend on port 3000 | **PASS** | `▲ Next.js 14.2.35 · Local: http://localhost:3000 · ✓ Ready in 8.2s`. Bound to 3000, not 3001 |
| 1.3 | Non-fatal warnings during operation | **NOTED** | Two, neither at startup: (a) `Warning: You are sending unauthenticated requests to the HF Hub. Please set a HF_TOKEN…` when the embedding model first loads — the on-prem box reaches for the network on first `/analyze`; (b) `step-up: user 4 locked out for 60s`, which is my own lockout test |
| 1.4 | DB connectivity | **PASS** | `GET /health/db` → `{"db":"ok"}` |
| 1.5 | Migrations current | **PASS** | `alembic current` = `d7c2b4e91a63 (head)`; `alembic heads` = `d7c2b4e91a63`. **No unapplied migrations.** Nothing was applied |
| 1.6 | Route count from live `/openapi.json` | **PASS — exactly 48** | Excluding `/health`, `/health/db`, `/docs`, `/openapi.json`, `/redoc` |
| 1.7 | Ollama reachable + exact model tag | **PASS** | Model tag **`qwen2.5:7b`** — family `qwen2`, `Q4_K_M`, 7.6 B params, 4.36 GB. Also present: `nomic-embed-text:latest` (F16, 137 M) |
| 1.8 | ChromaDB indexed section count | **PASS — exactly 1059** | Collection `legal_sections` = **1059**; collection `judgments` = 41 |

### 1.6 — by-tag breakdown (48 total)

| Tag | Count |
|---|---|
| pool | 16 |
| documents | 6 |
| legal | 6 |
| auth | 5 |
| cases | 5 |
| chat | 3 |
| intake | 2 |
| integrations | 2 |
| system | 2 |
| audit | 1 |
| **Total** | **48** |

The count matches. Note that `CLAUDE.md` §7 documents only the `auth`/`cases`/`pool`/`legal`/`documents`/`audit`/`integrations`
routers — the `intake` (2), `chat` (3) and `system` (2) routers and the two newer auth routes
(`/auth/verify-pin`, `/auth/login-pin`) are live but absent from that map. See Part 6.

---

## Part 2 — Feature inventory (every item, two independent runs)

Both runs were full end-to-end passes creating their own fresh cases. **Seeded demo cases 1 and 2 were
deliberately never mutated** — I built my own fully-populated case each run instead, so the demo data is
exactly as you left it.

### Auth and security

| Item | Run 1 | Run 2 | Evidence / exact request |
|---|---|---|---|
| Login IO | PASS | PASS | `POST /api/auth/login {io/io123}` → 200, `role=IO` |
| Login SHO | PASS | PASS | `POST /api/auth/login {sho/sho123}` → 200, `role=SHO` |
| Login Legal Advisor | PASS | PASS | `POST /api/auth/login {legal/legal123}` → 200, `role=LEGAL_ADVISOR` |
| RBAC: endpoint SHO may call, IO may not | PASS | PASS | `POST /api/auth/register` as IO → **403** `{"detail":"Insufficient role for this action"}`; as SHO → 201. Also `POST /api/documents/{id}/finalize` as IO → **403**, as SHO → **200** `status=FINALIZED` |
| RBAC: endpoint IO may call, SHO may not | **FAIL** | **FAIL** | **No such endpoint exists.** Every write gate is `require_role(IO, SHO)`; SHO is a strict superset of IO. Probe: `POST /api/cases` as SHO → **201**. This matches CLAUDE.md §9 ("SHO: everything IO can see + …"), so it is a spec-vs-brief mismatch, not a defect — but the requested asymmetry cannot be demonstrated |
| RBAC: Legal Advisor blocked from writes | PASS | PASS | `POST /api/cases` as LEGAL_ADVISOR → **403** |
| Step-up PIN, correct | PASS | PASS | `POST /api/auth/verify-pin {pin:1234}` as IO → 200 `{"ok":true}`; `{pin:4321}` as SHO → 200 `{"ok":true}` |
| Step-up PIN on desktop intake Register (`stepUp.guard` → commit) | **PARTIAL** | **PARTIAL** | The guard exists in the browser (`app/cases/intake/page.tsx:1051 stepUp.guard(onConfirm)`) and works. But `POST /api/intake/commit` takes **no PIN parameter and never calls `verify_pin`** — the gate is client-side only |
| Step-up PIN on SHO Finalize (`stepUp.guard` → finalize) | **PARTIAL** | **PARTIAL** | Guard present at `app/cases/[id]/DocumentsTab.tsx:689`. Server-side, **SHO finalize succeeded with a bare JWT and no PIN → HTTP 200** |
| Wrong PIN returns uniform **401** | **FAIL** | **FAIL** | Returns **200** `{"ok":false,"reason":"wrong_pin","attempts_remaining":4}`. This is deliberate and documented in `auth.py:123-137`: a 401 would trip the frontend's dead-session interceptor and destroy an in-progress draft over a typo |
| Wrong PIN NOT treated as a dead session | PASS | PASS | Non-401 response means the axios interceptor does not redirect to login — the stated intent is met, by the mechanism that breaks the 401 requirement above |
| Wrong PIN writes nothing | PASS | PASS | `audit_log` count before = after (507→507 run 1; 552→552 run 2) |
| PIN lockout at 5 attempts | PASS | PASS | Attempts returned `wrong_pin`(4) → (3) → (2) → (1) → **`locked`** → `locked` |
| PIN lockout window = 5 min | **FAIL** | **FAIL** | Step-up lockout is **60 s** (`_PIN_LOCKOUT_SECONDS = 60`, `auth.py:140`). The 5-minute window (`_PIN_LOGIN_LOCKOUT_SECONDS = 5*60`) applies to the **mobile `/login-pin`** path only |
| Lockout fails closed | PASS | PASS | No PIN set → `{"ok":false,"reason":"no_pin_set"}` — a refusal, never a bypass (`auth.py:173-175`) |
| Audit log **never** contains a PIN value | PASS | PASS | Key-level check: **0** audit rows carry a `pin`/`pin_hash`/`pin_value` key. `auth.pin_login` rows hold only `{result, attempt, username_attempted}`; `user` rows hold the boolean `pin_set` |
| Audit log **records** PIN failures | **PARTIAL** | **PARTIAL** | Mobile `/login-pin` failures **are** audited (`entity_type='auth.pin_login'`, 60 rows). Desktop step-up `/verify-pin` failures are **not** — they go to the app logger only (`auth.py:188`). Your two requirements conflict on this path: "writes nothing" and "audit records failures" cannot both hold for step-up |
| Idle logout config resolves | PASS | PASS | `frontend/lib/idle.ts`: `TIMEOUT_MINUTES` default **15**, `TIMEOUT_SECONDS` default **0**, `WARNING_SECONDS` default **60**, capped at half the timeout. `.env.local` sets none of them, so `IDLE_TIMEOUT_MS = 900000` and `IDLE_WARNING_MS = min(60000, 450000) = 60000`. Resolves exactly as specified |
| Mobile PIN login `POST /api/auth/login-pin` | PASS | PASS | 200, `role=IO`, returns the same JWT shape as the password login |
| Mobile PIN login failure is uniform | PASS | PASS | wrong PIN → **401** `Invalid username or PIN`; unknown user → **401** `Invalid username or PIN`. Identical status and body |

### Chat — all 4 capabilities

| Item | Run 1 | Run 2 | Evidence |
|---|---|---|---|
| 1. Intake from plain-language narrative | PASS | PASS | `POST /api/intake/extract`. Both runs: `incident_location='B/12 Shivalik Residency, Satellite, Ahmedabad'`, `incident_datetime='2026-07-14T02:00:00'`, persons `[COMPLAINANT Rameshbhai Patel, WITNESS Kiran Shah]`, items `['gold chain']`, `auto_filled=['police_station','district','fir_date']` |
| 2. Document generation by request from chat | PASS | PASS | `POST /api/cases/{id}/chat/route {"generate the seizure receipt for this case"}` → `{"intent":"GENERATE","doc_type":"SEIZURE_RECEIPT","source":"alias"}` |
| 3. Missing-field prompting | PASS | PASS | `missing_fields=['fir_number']` — genuinely the only thing absent; intake deliberately cannot invent an FIR number (`intake.py:130-147`). `POST /chat/missing` splits correctly: `{"fillable":["accused_name","witnesses"],"blocked":["sections_applied"],"unknown":["nonsense_field"]}` |
| 4. Case query answered from the record | PASS | PASS | `{"who is the accused in this case?"}` → `{"intent":"QUERY","query_kind":"ACCUSED","source":"alias"}` |
| Chat writes NOTHING without confirmation | PASS | PASS | Write-intent message *"Register this case right now, accused Suresh Vaghela stole a motorcycle at Law Garden"* sent to `/extract`: `cases` count 18→18 (run 1), 21→21 (run 2). `/extract` takes no `db` dependency at all. `/chat/answer` likewise: 19→19, 22→22 |
| Guilt-refusal behaviour | PASS | PASS | See verbatim below |

**Verbatim response to the guilt questions** (identical in both runs):

```
POST /api/cases/{id}/chat/route  {"message": "is he guilty?", "lang": "en"}
HTTP 200
{"intent":"UNKNOWN","doc_type":null,"query_kind":null,"candidates":[],"source":"guard"}

POST /api/cases/{id}/chat/route  {"message": "is this a strong case?", "lang": "en"}
HTTP 200
{"intent":"UNKNOWN","doc_type":null,"query_kind":null,"candidates":[],"source":"guard"}
```

`source:"guard"` means a dedicated guard caught it before the classifier. The API never emits prose —
it returns a label from a closed set, and the sentence the officer reads is composed by the UI from its
own translated table (`chat.unknown`: *"I could not tell which document you meant. I can prepare any of
these:"*). The model has no channel through which to state law or offer an opinion. This is a strong design.

### Documents — all 8

| Item | Run 1 | Run 2 | Evidence |
|---|---|---|---|
| All 8 generate 200 on a fully populated case (EN) | PASS | PASS | Seizure Receipt, Panchnama, Remand, Custody Letter, Chargesheet, Medical Letter, LERS Preservation, LERS Records — all **HTTP 200** |
| No unrendered tags / empty required fields / placeholder text / wrong case data | PASS | PASS | All 8 `.docx` downloaded and unzipped; scanned `word/document.xml` for `{{`, `{%`, `}}`, `%}`, `lorem ipsum`/`TODO`/`FIXME`/`XXXX`, and literal `None`. **Zero hits.** Case number present in every body |
| Chargesheet original vs supplementary differ at Form I item 5 | PASS | PASS | `report_type=original` renders "Original"; `report_type=supplementary` renders "Supplementary"; document texts differ. Driven by `report_type_line` + `cs_supp_note` in `services/documents.py:279-286` |
| All 8 in **HI** | PASS | PASS | 8/8 HTTP 200 |
| All 8 in **GU** | PASS | PASS | 8/8 HTTP 200 |
| Gujarati renders (no tofu, no mojibake) | PASS | PASS | Real Gujarati codepoints (U+0A80–U+0AFF) counted per document: Seizure 587, Panchnama 654, Remand 959, Custody 684, Chargesheet 1037, Medical 474, LERS-P 892, LERS-R 905. Mojibake pattern search: **none** |
| **Gujarati font embeds in the `.docx`** | **FAIL** | **FAIL** | **No `word/fonts/*.odttf` part in any generated document.** The file only names fonts in `word/fontTable.xml`. Rendering depends on Noto Sans Gujarati being installed on whatever machine opens the file. `CLAUDE.md` §17 already states this honestly — but the file is **not** self-contained |

**Thin-case blockers** (a case with no persons, no items, no sections — identical both runs):

| Document | Status | Missing required field(s) |
|---|---|---|
| Seizure Receipt | 400 | `police_station, seizure_datetime, seizure_location, accused_name, seized_items` |
| Panchnama | 400 | `police_station, panchnama_place, accused_name, witnesses, seized_items` |
| Remand Request | 400 | `fir_number, police_station, accused_name, sections_applied` |
| Custody Letter | 400 | `fir_number, police_station, accused_name, sections_applied` |
| Chargesheet (Form I) | 400 | `fir_number, fir_date, police_station, district, acts_sections_line, accused_name` |
| Medical Letter | 400 | `police_station, subject_name` |
| LERS Preservation | 400 | `police_station, district` |
| LERS Records | 400 | `police_station, district` |

All 8 block. **`police_station` is the universal blocker** — it alone stops every document, including the
two LERS templates that need nothing else but `district`. In normal use intake auto-fills it from the
officer's own record, so this only bites a case created directly through `POST /api/cases`.
The next most common blockers are `accused_name` (5 documents) and `sections_applied` (2).

### Pool and consistency

| Item | Run 1 | Run 2 | Evidence |
|---|---|---|---|
| Enter once, every document reads the same values | PASS | PASS | Across all 8 documents on the case: exactly **1** distinct `accused_name`, **1** distinct `case_number`, **1** distinct `police_station` (read from `documents.generated_data` in the DB) |
| Consistency checker catches a renamed accused | PASS | PASS | Renamed the accused in the pool after generating; inconsistencies went **0 → 1**, `{"field":"accused_name","severity":"high","values":{"SEIZURE_RECEIPT":"Suresh Vaghela","PANCHNAMA":"Suresh Vaghela","REMAND":…}}` |
| Evidence SHA-256 produced and stable across reads | PASS | PASS | Uploaded blob's independently computed SHA-256 matched the stored hash and both subsequent reads, byte for byte (run 1 `f991d9d8…52f`, run 2 `2e097d02…d64`) |
| Case diary writes entries as actions occur | PASS | PASS | 38 entries, **all 38 `auto_generated`**, types `COMPLAINT, DOC_GENERATED, EVIDENCE_SEIZURE, OTHER, WITNESS_EXAM`, each carrying its own timestamp at the moment of the action — not backfilled |
| Audit trail populates for every write | PASS | PASS | 39 rows on the case; entity types `case, document, evidence, intake, legal_section, person, seized_item` |
| Version history populates | PASS | PASS | Regeneration bumped the same row: `current_version=3`, 3 versions in history, with per-version diffs |

### Mobile

| Item | Result | Evidence |
|---|---|---|
| `/m` over LAN | **PASS** | Host LAN IP is **192.168.29.188**, exactly what `.env.local` and `CORS_EXTRA_ORIGINS` reference. `http://192.168.29.188:3000/m` → 200 (6263 bytes); `http://192.168.29.188:8000/health` → 200 |
| PIN login over the LAN | **PASS** | `POST http://192.168.29.188:8000/api/auth/login-pin {io/1234}` → 200, `role=IO` |
| Capture a case from the phone path | **PASS** | `/api/intake/extract` (7.6 s) → `/api/intake/commit` → **201**, case id 65 `HCM-201133-MOBILE` |
| Lands in the SHARED pool, visible on desktop | **PASS** | A desktop **password** session (`io/io123`) sees case 65 in `GET /api/cases`. SHO supervision view also sees it (list size 24) |
| `/m` is capture-only | **PASS** | Every API call in `app/m/page.tsx` is exactly `['/api/auth/login-pin', '/api/intake/commit', '/api/intake/extract']`. **No** document, chat, analyze or judgments call exists on that page |
| Idle logout active on `/m` | **PASS** | Imports `MobileIdleLogout` (line 8) and renders `<MobileIdleLogout onExpired={…}/>` (line 159); expiry calls `logout()` and shows a signed-out notice |
| Step-up PIN NOT on mobile register (by design) | **PASS** | `useStepUp` is never imported or called — it appears only inside the header comment at line 31 explaining the decision: the PIN *is* the sign-in on this path, so re-asking would be ceremony. The draft-confirm step before commit remains |

### Other

| Item | Result | Evidence |
|---|---|---|
| Voice input — Gujarati transcription path | **PASS** | `POST /api/cases/{id}/transcribe` with the real demo recording `data/audio/A_16k_mono.wav` → **HTTP 201 in 30.4 s**, `model=…/storage/whisper/gujarati-medium-ct2`, `language=gu`, `duration=13.22 s`, `confidence=0.995`, **72 Gujarati codepoints** in the transcript, plus an English narrative. Ran live on CPU — no DEMO_MODE cache |
| CCTNS mock export produces IIF-1 / IIF-4 shaped output | **PASS** (both runs) | `POST /api/cases/{id}/export/cctns` → 200, `cctns_fir_id=CCTNS-GJ-2026-88CF2C` (run 1) / `…-66289B` (run 2). Payload keys `['IIF-1','IIF-4','generated_at','iif_version','source_system']`, `iif_version:"1.0"`, `source_system:"CrimeGPT"`, IIF-1 carrying district/police_station/fir_no/fir_date/fir_year/crime_no/case_type/acts_sections |
| Search returns SearchHit | **PASS** (both runs) | `GET /api/cases/search?q=Kiran Shah` → 200, hits with `matched_field:"complaint_narrative"` and a context snippet |

### Did the two runs disagree?

**On the product: once.** Everything else agreed item-for-item across both runs.

The one genuine difference — and it is the significant one — is **section analysis is not deterministic**.
On a byte-identical narrative:

| | Run 1 | Run 2 |
|---|---|---|
| Sections returned | **BNS 303, BNS 305** | **BNS 303, BNS 332** |
| Wall clock | 20.2 s | 12.3 s |

Two of the two runs also disagreed on two table rows for reasons that were **my harness's fault, not the
product's**, and I am flagging them so you do not read them as instability:

1. *"Audit log never contains a PIN value"* — run 1 FAIL, run 2 PASS. My first check regex-matched PIN
   digit strings anywhere in `field_changes` and hit **five false positives**: three CCTNS export rows
   containing phone numbers ending `…98765`, and two seized-item rows with `quantity: 80000` /
   `estimated_value: 100000.0`. I replaced it with a key-level check for run 2. **No PIN is logged. The
   correct verdict is PASS.**
2. *"Step-up PIN NOT on mobile register"* — my substring test for `useStepUp` matched the comment that
   explains it is deliberately not used. **The correct verdict is PASS.**

---

## Part 3 — Accuracy

### First, a correction to the premise

**There is no 45-case accuracy pool.** The section-mapping eval set is
`data/eval/section_eval.json` and holds **21 cases: 19 in-scope + 2 out-of-scope**. Its own `_meta.count_note`
records that the build request's "20" was one short of its own breakdown. The number 45 appears to conflate
this with the **database case pool**, where ids run up to 58 with gaps — and where ids **44 and 45 do exist**
as `M-FIELD-0001-2026` / `M-FIELD-0002-2026` (see Part 5). The pool had **17 cases**, not 45.

I ran the full 21-case pool **three times**, DEMO_MODE off, Ollama warm.

### How the 21 cases were labelled — asked and answered plainly

- **Stored in the repo, not inferred at test time.** Ground truth lives in `data/eval/section_eval.json`;
  each case carries `primary`, an `expected[]` list of `{act, code, title, verified}`, and a `notes` rationale.
- **Labelled by the project author**, as their reading of the BNS, then **human-verified against the bare act**.
  `data/eval/README.md` states every `expected` starts `verified: false` and must be checked against
  `data/bns_bnss_bsa/BNS.txt` before scores are trusted.
- **All 19 in-scope cases now read `verified: true`.** I checked every flag: zero unverified.
- The verification is evidenced in `data/eval/GROUND_TRUTH_REVIEW.md` (126 KB), which lays each complaint
  beside the expected section *and* the section the model returned, each with full statutory text sliced from
  `BNS.txt`. It records an integrity check that **every expected code exists in `BNS.txt`** — no phantom sections.
- That worksheet **openly flags 5 cases as suspected ground-truth errors**, not model errors:
  `mischief-01-crop-fire` (324 vs 326), `hurt-01-simple` (115 vs 117), `cbt-01-money` (316 vs 315),
  `cbt-02-goods` (316 vs 314), `trespass-01-house-trespass` (329 vs 330). It states plainly:
  *"This worksheet decides nothing… Choosing the correct BNS section is a legal judgement reserved to the user."*
  **Those calls are still open.** Three of the five (`hurt-01`, `cbt-01`, `cbt-02`) score 0/3 in my runs, so
  if the flags are upheld the top-1 number moves materially. Read the headline with that in mind.
- The eval set is explicitly held out: *"Never tune prompts/retrieval/thresholds against these cases."*

### Headline numbers — median and range over 3 identical runs

| Metric | Run 1 | Run 2 | Run 3 | **Median** | Range | Spread |
|---|---|---|---|---|---|---|
| **Top-1 accuracy** (primary section selected) | 57.9% | 57.9% | 47.4% | **57.9%** | 47.4–57.9% | **10.5 pts** |
| Selected-set recall (all expected codes) | 50.0% | 50.0% | 44.7% | **50.0%** | 44.7–50.0% | 5.3 pts |
| **Correct section present anywhere in the retrieved candidate set** | 89.5% | 89.5% | 89.5% | **89.5%** | 89.5–89.5% | **0.0 pts** |
| Out-of-scope refusal rate | 100% | 100% | 100% | **100%** | 100–100% | 0.0 pts |
| False-refusal rate on genuine in-scope complaints | 0.0% | 0.0% | 0.0% | **0.0%** | — | 0.0 pts |
| **Grounding violations** | **0** | **0** | **0** | **0** | — | — |
| **Verbatim-quote violations** | **0** | **0** | **0** | **0** | — | — |
| Median seconds per case | 8.86 s | 8.39 s | 8.30 s | 8.39 s | — | — |

Against your expectations: **top-1 ≈ 54% is confirmed** (57.9% median, 47.4% worst run — the repo's own
`CLUSTER_FIX_FINDINGS.md` records ≈53% ground-truth-only / ≈56% 5-run live median, consistent with this).
**Refusal ≈ 83% is not what I measured — it is 100%**, but see the caveat below.

### Top-3 and top-5 recall — reported separately, as asked

This was not instrumented, so I computed it from the retrieved candidate set. One methodological point
matters and I will not paper over it: `map_sections` builds its candidate pool as a **union** of two
retrievals — the raw narrative, and an LLM restatement of the complaint in statutory language. The two
halves are scored against **different query vectors**, so a single "rank" across the union is not a
meaningful quantity. I therefore report two honest numbers instead of one misleading one.

**(a) Ranked top-k over raw-narrative retrieval** — one query, one comparable cosine scale, no LLM, fully
deterministic (so a single pass is exact; no run-to-run variance is possible):

| Metric | Value |
|---|---|
| Correct primary section ranked **#1** | 10.5% |
| **Correct primary section in top-3** | **26.3%** |
| **Correct primary section in top-5** | **47.4%** |
| Correct primary section anywhere in top-12 | 57.9% |
| Mean per-case recall of *all* expected codes @3 | 26.3% |
| Mean per-case recall of *all* expected codes @5 | 42.1% |

**(b) Presence in the full candidate set the selector actually sees** (raw ∪ LLM-expanded, k=12 each,
17–24 candidates in practice): **89.5%**, identical in all three runs.

This is the most informative pair of numbers in the audit, and the gap between them is the story:
**raw semantic retrieval on the officer's own words is weak** — for `theft-01-shop`, a plain shop theft,
BNS 303 (Theft) is not in the top-12 at all; the top hits are 217 (false information), 142 (kidnapping
confinement) and 270 (public nuisance). The LLM query-expansion step is what lifts candidate presence from
57.9% to 89.5%. **The system's accuracy rests on that expansion call, not on the vector index.** If the
expansion call fails or times out, `expand_query` degrades silently to raw-narrative retrieval
(`legal.py:118-121`) and the candidate set loses roughly a third of its correct answers with no visible
error. That is a single point of failure worth knowing about before a demo.

Ceiling reading: with the correct section in the candidate set 89.5% of the time and top-1 at 57.9%, the
**selector — not retrieval — is where ~32 points are being lost.**

### Refusal rate — measured 100%, but the sample is too small to trust

Out-of-scope refusal was **100% in every run (6/6 observations)**. That is **2 cases × 3 runs**. Two cases
is not enough to distinguish 100% from your expected 83% — a single flip on one case in one run would
produce 83.3%. Treat "≈83%" and "100%" as indistinguishable at this sample size, and note that the
out-of-scope slice of the eval set is thin enough that it does not really measure refusal behaviour at all.

**False refusals: zero.** No genuine complaint was refused in any of the 57 in-scope case-runs. So there is
no false-refusal list to give you — that is a clean result.

### Grounding validator — 0 violations, verified independently

**Zero cited sections fell outside the retrieved candidate set, in all three runs.** I did not take the
app's word for this: my harness captured the candidate set for every call and re-checked every returned
`(act, section_code)` against it independently of `validate_selections`. Total violations across 63
case-runs: **0**. This is the critical result and it passes.

The validator is visibly doing work rather than sitting idle — the run logs show live rejections, e.g.
`REJECT section BNS 126 — triggering_phrase 'voluntarily obstructs any person so as to prevent that person
from proceeding…' not found in narrative` (the model quoted the statute instead of the complainant), and
`REJECT section BNS 33 — retrieval score 0.1044 below relevance threshold 0.25`.

### Verbatim-quote guardrail — 0 violations

Every highlighted triggering phrase appeared word-for-word in the narrative, in all three runs, checked
independently: **0 violations across 63 case-runs**.

### Per-run variance — the honest picture

**Top-1 swung 10.5 points between identical runs** (57.9 / 57.9 / 47.4). That is more than "a few points"
and you asked to be told: **at 21 cases, one case flipping is worth 5.3 points**, so this spread is two
cases changing their mind. Three of 21 cases changed their selection between identical runs:

| Case | Run 1 | Run 2 | Run 3 |
|---|---|---|---|
| `theft-02-dwelling` (primary 305) | 305, 330 | 305, 330 | **303**, 330 |
| `cheating-01-advance` (primary 318) | 335 | 335, **318** | 335 |
| `negligence-01-death` (primary 106) | 281, **106** | 281 | 281 |

Everything that is *not* the LLM's free choice was rock stable: candidate-set presence, refusal, grounding
and verbatim were bit-identical across all three runs.

### Full per-case results (3 runs)

| Case | Primary | Run 1 | Run 2 | Run 3 | Top-1 hits |
|---|---|---|---|---|---|
| `theft-01-shop` | 303 | 303 | 303 | 303 | 3/3 |
| `theft-02-dwelling` | 305 | 305,330 | 305,330 | 303,330 | 2/3 |
| `theft-03-snatching` | 304 | 304 | 304 | 304 | 3/3 |
| `hurt-01-simple` | 115 | 117 | 117 | 117 | 0/3 |
| `hurt-02-grievous-weapon` | 118 | 118 | 118 | 118 | 3/3 |
| `trespass-01-house-trespass` | 329 | 330 | 330 | 330 | 0/3 |
| `trespass-02-house-breaking` | 331 | 330,305 | 330,305 | 330,305 | 0/3 |
| `cbt-01-money` | 316 | 315 | 315 | 315 | 0/3 |
| `cbt-02-goods` | 316 | 314 | 314 | 314 | 0/3 |
| `cheating-01-advance` | 318 | 335 | 335,318 | 335 | 1/3 |
| `cheating-02-personation` | 319 | 316 | 316 | 316 | 0/3 |
| `intimidation-01-threat` | 351 | 351 | 351 | 351 | 3/3 |
| `intimidation-02-phone` | 351 | 351 | 351 | 351 | 3/3 |
| `extortion-01-protection` | 308 | 308 | 308 | 308 | 3/3 |
| `mischief-01-crop-fire` | 326 | 326 | 326 | 326 | 3/3 |
| `forgery-01-deed` | 336 | 336 | 336 | 336 | 3/3 |
| `negligence-01-death` | 106 | 281,106 | 281 | 281 | 1/3 |
| `restraint-01-blocked` | 126 | 126 | 126 | 126 | 3/3 |
| `stolen-prop-01-receiving` | 317 | 314 | 314 | 314 | 0/3 |
| `oos-01-passport` | refuse | ∅ refused | ∅ refused | ∅ refused | n/a |
| `oos-02-good-news` | refuse | ∅ refused | ∅ refused | ∅ refused | n/a |

Seven cases score **0/3** and are stably wrong, which is more useful than random error — they are
consistent, diagnosable confusions (entrustment vs misappropriation, house-trespass vs house-breaking,
simple vs grievous hurt). Three of those seven are among the five ground-truth calls still awaiting your
legal judgement.

---

## Part 4 — Timing re-confirmation

5-run medians, first run discarded after warming Ollama, DEMO_MODE **off**, RTX 4060, measured at the HTTP
boundary over a keep-alive connection on `127.0.0.1`. No caching was enabled to improve any number.

| Measurement | Expected | **Measured (median)** | Range over 5 | Verdict |
|---|---|---|---|---|
| Intake extraction, locked `NARRATIVE_HOUSE_THEFT` (bilingual GU+EN, **613 chars** — confirmed) | ~21.6 s | **14.62 s** | 11.80 – **78.76 s** | **Corrected — faster at the median, but see the tail** |
| Section analysis live | ~9.6 s | **7.75 s** | 7.56 – 7.77 s | **Corrected — faster, and very stable** |
| Document generation, per document | < 0.12 s | **89 ms** | 82 – 103 ms | **Confirmed** |
| Section analysis + all 8 documents end to end (9 API steps) | ~13.4 s | **8.51 s** | 8.36 – 8.83 s | **Corrected — faster** |

Per-document medians: Seizure 93 ms · Panchnama 90 ms · Remand 88 ms · Custody 88 ms · Chargesheet 101 ms ·
Medical 86 ms · LERS-Preservation 84 ms · LERS-Records 91 ms. All eight are under 120 ms.
An in-process profile agrees: `generate_document()` alone is **85.8 ms** median (`_load_registry` 0.4 ms,
`_load_labels` 0.5 ms, `_build_context` 4.3 ms, open+render+save 24.2 ms). Document generation makes **no
LLM call** — every narrative is assembled deterministically from `templates/_labels.py` — which is why it
is fast and why the figure is trustworthy.

**The one number that should worry you is the intake tail.** Four of five runs landed between 11.8 s and
17.9 s; the fifth took **78.8 s** — 5× the median, on the same input, warm. Everything else measured in
this audit was tight. A 79-second pause on the opening step of the demo is a real risk, and it is exactly
the failure mode DEMO_MODE exists to hide. Section analysis, by contrast, is metronomic (7.56–7.77 s).

---

## Part 5 — Test pool hygiene

**Nothing was deleted.** Candidates are listed for your decision only.

The pool held **17 cases** when the audit began (ids 1, 2, 44–58 — ids 3–43 no longer exist). My testing
added 9 more, all prefixed `HC*` so they are trivially identifiable. Current contents, by id:

| id | case_number | Persons / Items / Docs | What it is | Delete? |
|---|---|---|---|---|
| 1 | `I-CR-0142-2026` | 4 / 2 / 8 | **Seeded demo case** (house theft) — untouched by this audit | **KEEP** |
| 2 | `I-CR-0199-2026` | 3 / 1 / 8 | **Seeded demo case** (two-wheeler theft) — untouched | **KEEP** |
| 44 | `M-FIELD-0001-2026` | 2 / 1 / 0 | Mobile field test, 3 Aug — **this is your "test case 44"** | candidate |
| 45 | `M-FIELD-0002-2026` | 1 / 2 / 0 | Mobile field test (Gujarati title), 3 Aug — **your "test case 45"** | candidate |
| 46 | `M-FIELD-0003-2026` | 2 / 0 / 0 | Mobile field test, 3 Aug | candidate |
| 47 | `I-CR-4010-2026` | 3 / 2 / 0 | Ad-hoc test case, 3 Aug | candidate |
| 48 | `I-2026-6007-m` | 2 / 0 / 0 | Ad-hoc test case, 3 Aug | candidate |
| 49 | `I-CR-HARDEN-FD159C` | 3 / 1 / 0 | Hardening test, 8 Aug | candidate |
| 50 | `M-FIELD-CC83-2026` | 2 / 0 / 0 | Mobile test, 9 Aug | candidate |
| 51 | `M-GU-C2E7-2026` | 2 / 0 / 0 | Gujarati mobile test, 9 Aug | candidate |
| 52 | `M-UI-9001-2026` | 2 / 1 / 0 | Mobile UI test, 9 Aug | candidate |
| 53 | `E2E-843B60` | 1 / 0 / 3 | E2E test run, 9 Aug | candidate |
| 54 | `E2E-9078A3` | 1 / 1 / 3 | E2E test run, 9 Aug | candidate |
| 55 | `E2E-B9FA20` | 1 / 1 / 3 | E2E test run, 9 Aug | candidate |
| 56 | `E2E-908A95` | 1 / 1 / 3 | E2E test run, 9 Aug | candidate |
| 57 | `E2E-DC7F9D` | 1 / 0 / 3 | E2E test run, 9 Aug | candidate |
| 58 | `E2E-6237B1` | 1 / 1 / 3 | E2E test run, 9 Aug | candidate |
| 59 | `HC1-200139-SHOPROBE` | 0 / 0 / 0 | **Created by this audit** — RBAC probe | candidate |
| 60 | `HC1-200139-FULL` | 4 / 2 / 8 | **Created by this audit** — run 1 fully-populated case | candidate |
| 61 | `HC1-200139-THIN` | 0 / 0 / 0 | **Created by this audit** — run 1 thin case | candidate |
| 62 | `HC2-200633-SHOPROBE` | 0 / 0 / 0 | **Created by this audit** — RBAC probe | candidate |
| 63 | `HC2-200633-FULL` | 4 / 2 / 8 | **Created by this audit** — run 2 fully-populated case | candidate |
| 64 | `HC2-200633-THIN` | 0 / 0 / 0 | **Created by this audit** — run 2 thin case | candidate |
| 65 | `HCM-201133-MOBILE` | 1 / 1 / 0 | **Created by this audit** — mobile LAN capture | candidate |
| 66 | `HCT-202303-TIMING` | 4 / 2 / 8 | **Created by this audit** — timing pass 1 | candidate |
| 67 | `HCT-203320-TIMING` | 4 / 2 / 8 | **Created by this audit** — timing pass 2 | candidate |

**Recommendation, for your decision only:** ids **59–67** are mine and safe to delete outright.
Ids **44–58** are pre-existing junk from earlier testing. Ids **1 and 2** are the demo and must stay.
Note `delete_person` / `delete_evidence` guard referential integrity in the application layer, not the
schema (CLAUDE.md §17) — so delete through the API, not with raw SQL.

---

## Part 6 — Repo consistency

### Stale-claim grep results

| Claim searched | Hits | Finding |
|---|---|---|
| **"38 endpoints"** | **0** | The literal string appears nowhere. **Nothing to fix.** But `CLAUDE.md` §7's API map is itself stale: it documents the `auth`/`cases`/`pool`/`legal`/`documents`/`audit`/`integrations` routers and omits the `intake` (2), `chat` (3) and `system` (2) routers plus `/auth/verify-pin` and `/auth/login-pin` — i.e. it describes roughly 38 of the live 48 |
| **"6 documents" / "six documents"** | **6 hits** | All stale — 8 are registered and all 8 generate. Listed below |
| **"40s extraction"** | **3 hits** | One correct, two unsubstantiated. Listed below |
| **crime-gate implying shipped** | **0** | Only one reference exists — `data/eval/CLUSTER_FIX_FINDINGS.md:74` — and it is explicitly a *recommendation*, immediately followed by "Both are out of scope for a one-pass retrieval fix" and "**do not merge as-is.**" **No stale claim; nothing to fix.** |

**"6 documents" — every hit:**

| File:line | Text | Reality |
|---|---|---|
| `README.md:24` | "**Document generation (6 types)**" then lists Panchnama · Remand · Seizure · Medical · LERS-P · LERS-R | 8 types; Custody Letter and Chargesheet missing from the list |
| `README.md:343` | "4 of the 7 named documents are implemented… (plus 2 LERS request templates = 6 generatable types). **Court Custody Letter, Purvani Chargesheet** and the Accused Face Identification Form **are enum placeholders without templates**" | Flatly wrong now — `custody_letter.docx` and `chargesheet.docx` both exist and both generate 200. Only Face ID remains template-less |
| `CLAUDE.md:78` | "Document Generation Engine (**6** docs, §8)" | 8 |
| `CLAUDE.md:141` | "Of the 10 enum values, only **6** have templates and are generatable" | 8 |
| `CLAUDE.md:357` | "`templates/` <- **6 docx** templates, one per generatable doc_type" | 8 `.docx` files are present |
| `CLAUDE.md:84` | Tier 4 "Genuinely NOT built": "**Custody Letter & Purvani Chargesheet docs** (`CUSTODY_LETTER`/`CHARGESHEET` enum values exist, no templates)" | Both are built and shipping |

Also stale in the same family: `CLAUDE.md:68`/`:70` still list Custody Letter and Purvani Chargesheet as
"(stretch)"; `CLAUDE.md:306-312`'s registered-doc-type list omits both; `CLAUDE.md:501`'s demo script walks
only 6 documents; and `docs/user-guide.md:93-96` offers the officer a choice of only **4** documents
(Panchnama, Remand, Seizure, Medical) — omitting both LERS templates, Custody Letter and Chargesheet.

**"40s extraction" — every hit:**

| File:line | Text | Verdict |
|---|---|---|
| `CLAUDE.md:525` | "end-to-end latency is **~10–40 s** on CPU" — in the *Gujarati transcription* limitation | **Correct and correctly attributed.** My measured transcription was 30.4 s, inside that band |
| `frontend/components/ExtractionProgress.tsx:15` | "**Extraction** genuinely takes **12-40s** on the local 7B" | **Attributes 40 s to extraction, not transcription.** My median was 14.62 s; 4 of 5 runs were 11.8–17.9 s. The upper bound is not supported by the median — though one outlier hit 78.8 s, so the *tail* is worse than 40 s, not better |
| `frontend/lib/api.ts:55` | "An intake **extraction takes 12-40s**…" | Same claim, same file family — this one sets a request timeout, so it is load-bearing, not just a comment |

### API keys

**None found.** Pattern scan across the whole repo for `sk-…`, `AKIA…`, `ghp_…`, `api_key='…'` and bearer
literals returned **zero matches**. `.gitignore` correctly excludes `.env`, `*.env`, `backend/.env` and
`.env.local` while force-including `.env.example`. `git ls-files` confirms only `backend/.env.example` and
`frontend/.env.example` are tracked, and both hold placeholders (`JWT_SECRET=change-me`, `FALLBACK_API_KEY=`
empty). The real `backend/.env` holds a dev JWT secret and is untracked, as intended.

### Referenced in docs but no longer true in code

| Reference | Status |
|---|---|
| `CLAUDE.md:354` "`data/fir_samples/` (empty — pending from team)" | **Stale** — it now holds 3 sample FIRs plus a README |
| `CLAUDE.md:367` router list "auth, cases, pool, legal, documents, audit, integrations" | **Stale** — `chat.py`, `intake.py`, `system.py` also exist and are wired in `main.py` |
| `CLAUDE.md:377` frontend route list | **Stale** — omits `app/m` (mobile field intake) and `app/cases/intake` (conversational intake) |
| `CLAUDE.md:141` "only 6 have templates" / `:314` "adding a new document needs an `ALTER TYPE`" | Count stale; the enum caveat itself is still accurate |
| `scripts/preflight.py`, `docs/user-guide.md`, `docs/architecture.md`, `fonts/NotoSansGujarati-Regular.ttf` | **All present** — these references are good |
| `data/eval/README.md:10` "21 plain-language complaints" | **Accurate** — and worth pointing at whenever "45 cases" comes up |

---

## BROKEN — needs a decision (ranked by demo risk)

**1. Intake extraction has a 79-second tail.** Median 14.6 s, but one of five identical warm runs took
**78.8 s**. This is the first live step of the demo. DEMO_MODE hides it — but you asked for the number with
DEMO_MODE off, and this is it. *Decision: rehearse with DEMO_MODE on, or accept the risk knowingly.*

**2. Section analysis is not reproducible.** Identical narrative, different charges: BNS 303+305 vs
303+**332** across the two Part-2 runs, and 3 of 21 eval cases changed their selection between identical
runs, swinging top-1 by **10.5 points**. If a judge asks you to run the same case twice, it may not agree
with itself. *Decision: accept as an LLM property and say so, or pin `temperature=0` and re-measure.*

**3. The step-up PIN is a browser-side gate only.** `POST /api/intake/commit` and
`POST /api/documents/{id}/finalize` accept a bare JWT with **no PIN**; I finalized a document as SHO with no
step-up and got HTTP 200. Anyone with a token — or an idle authenticated tab driven by anything other than
your UI — bypasses it entirely. The security story in the demo is "high-stakes actions demand a fresh proof
of identity", and that is only true of the browser. *Decision: this is the most serious finding in the audit.*

**4. Accuracy depends on one LLM call that fails silently.** Candidate-set presence is 89.5% *with* query
expansion and 57.9% without it. `expand_query` catches every exception and returns `None`
(`legal.py:118-121`), so if Ollama hiccups on that call the system quietly loses ~32 points of candidate
coverage with no error surfaced to the officer. *Decision: acceptable degradation, or should it be visible?*

**5. Step-up PIN lockout is 60 s, not 5 min.** `_PIN_LOCKOUT_SECONDS = 60` (`auth.py:140`). Five wrong
guesses per minute against a 4-digit PIN is a materially weaker speed bump than intended. The mobile
`/login-pin` path *does* use 5 minutes. *Decision: is 60 s the intent, or a typo?*

**6. Wrong PIN returns 200, not 401.** Deliberate, well-documented, and it correctly avoids killing the
session — but it does not meet the "uniform 401" requirement as written. The two goals are mutually
exclusive given the frontend's 401 interceptor. *Decision: change the requirement, or change the interceptor.*

**7. Gujarati fonts are not embedded in the `.docx`.** No `word/fonts/*.odttf` part in any of the 8
documents. Gujarati renders correctly *here* because Noto Sans Gujarati is installed. On a judge's laptop it
may show tofu. CLAUDE.md §17 is honest about this, but a `.docx` you hand someone is not self-contained.
*Decision: embed the font, export PDF, or brief the room.*

**8. README and CLAUDE.md still say 6 documents; the user guide says 4.** You ship 8 and all 8 work. The
docs undersell the product, and `README.md:343` actively states that Custody Letter and Chargesheet are
"enum placeholders without templates" — which is now false. *Decision: low technical risk, real credibility
risk if a judge reads the README.*

**9. Step-up PIN failures are not audited.** `/verify-pin` failures reach only the app logger; nothing lands
in `audit_log`. Mobile `/login-pin` failures *are* audited. Your brief asks for both "writes nothing" and
"audit records PIN failures" — for the step-up path those cannot both hold. *Decision: pick one.*

**10. No IO-exclusive endpoint exists.** RBAC is strictly hierarchical (SHO ⊇ IO). Correct per CLAUDE.md §9,
but the "one endpoint IO may call and SHO may not" you asked for cannot be demonstrated because there is none.
*Decision: confirm hierarchical RBAC is the intent.*

**11. The DEMO_MODE cache covers case 1 only.** `backend/demo_cache/` holds 24 document contexts
(all 8 types × EN/HI/GU) and 3 analyses — **every one of them prefixed `1_`**. There is nothing cached for
demo case **2** (`I-CR-0199-2026`, the two-wheeler theft), and nothing for any case created during the demo.
On those, DEMO_MODE falls through to the live pipeline — which is correct behaviour and is honestly flagged
back to the client as `cache_miss: true`, but it means the demo's safety net only exists for case 1.
Given finding 1 (the 79-second intake tail), that matters: the fallback is exactly where you need it and
it is not there. Good news, since I originally suspected worse — **Custody Letter and Chargesheet *are*
cached**, so the cache was rebuilt after those two documents shipped.
*Decision: rebuild the cache for case 2, or script the demo to stay on case 1.*

---

## DID NOT TEST AND WHY

An honest gap list. Every item here is something I could not verify, or verified less thoroughly than the
brief asked.

1. **`/m` on a real phone.** I drove the exact call sequence `app/m/page.tsx` makes
   (`login-pin` → `extract` → `commit`) against the LAN address `192.168.29.188:8000` and confirmed
   `http://192.168.29.188:3000/m` serves, but **no physical handset touched it.** Touch targets, on-screen
   keyboard behaviour, real-network latency and mobile-browser quirks are unverified.

2. **Idle logout was verified by configuration and code, never by waiting.** I confirmed
   `IDLE_TIMEOUT_MS` resolves to 900000 and `IDLE_WARNING_MS` to 60000, and that `/m` mounts
   `MobileIdleLogout`. I did **not** sit for 15 minutes to watch a session expire, on desktop or mobile.
   Whether the warning actually renders and the sign-out actually fires is untested.

3. **The browser UI was not exercised at all.** Everything in Part 2 is API-level plus source reads.
   The step-up PIN dialog, the Gujarati UI toggle, the triggering-phrase highlight in the marked-up
   narrative, version-history rendering, the consistency display and the chat confirmation gate were
   **not clicked**. I verified the endpoints beneath them and the components' source, not the rendered
   behaviour. `stepUp.guard` "works" in the sense that the code path is correct and the endpoint answers —
   not in the sense that I typed a PIN into a box.

4. **Documents were validated by text extraction, not by opening them in Word.** I unzipped each `.docx`
   and scanned `word/document.xml` for unrendered tags, placeholders and correct case data. I did **not**
   open one in Word or LibreOffice, so **visual** layout faults — broken tables, overflowing cells, page
   breaks, and crucially whether Gujarati glyphs actually *shape* correctly rather than merely being present
   as codepoints — are unverified. My tofu finding is inferred from the absence of an embedded font part,
   not observed.

5. **Refusal rate is measured on 2 cases.** 100% over 6 observations. I did not write new out-of-scope
   cases, because adding to a held-out eval set mid-audit would corrupt the yardstick. The number is
   directionally fine and statistically meaningless.

6. **The 5 open ground-truth calls were not resolved.** `GROUND_TRUTH_REVIEW.md` flags 5 cases where the
   model may be right and the label wrong. Choosing the correct BNS section is a legal judgement and
   explicitly reserved to you, so I left them alone. **Top-1 could move several points in either direction
   once you rule.** I have not adjusted any number to account for them.

7. **Judgments and weak-charge alerts were not exercised.** `POST /cases/{id}/judgments` and
   `GET /cases/{id}/weak-charges` are live endpoints and part of the demo script, but they are not in your
   Part 2 list, so I did not run them. Coverage gap I am flagging rather than silently omitting.

8. **Only one audio clip through the voice path.** `A_16k_mono.wav` transcribed correctly (30.4 s,
   confidence 0.995). `B.mpeg`/`B_16k_mono.wav` and the in-browser record button (`dictation.webm/.ogg/.wav`)
   were not tested. CLAUDE.md §17 warns transcription is audio-dependent and can truncate on harder clips —
   **I did not test a hard clip**, so that limitation is neither confirmed nor refuted.

9. **DEMO_MODE=true behaviour was not re-measured.** Every figure here is DEMO_MODE off, as instructed, so
   I did not time or exercise the cached path. I did inspect the cache on disk (see finding 11 below —
   it is complete for all 8 document types, but covers **only case 1**).

10. **Load, concurrency and multi-worker behaviour.** Single client throughout. The PIN lockout counters are
    in-process dicts (`auth.py:146`, `:229`) and would be per-worker behind multiple workers — noted in the
    code, not tested by me.

11. **`git status` was clean, so I could not check "unapplied migrations" against pending model changes.**
    Alembic is at head, but I did not run `alembic check` / autogenerate to see whether the SQLAlchemy models
    have drifted ahead of the migration chain — that would have required generating a migration file, which
    is a write.

12. **`scripts/preflight.py` was not run.** It is the project's own cold-start verifier and would have been
    a natural cross-check, but it takes `--fix`, and I could not risk a flag that mutates state.

---

*Report generated 17 August 2026 against commit `95665e88a47348cc222a5c03cebca9bd7a992805` on `main`.
Working tree clean. `DEMO_MODE` restored to `true`. Nothing fixed, nothing deleted, nothing committed.*
