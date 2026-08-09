# Mobile Field Intake — Phase 2 Report

**Branch:** `feat/mobile-intake`
**Commit:** `90b9f02` — *feat(mobile): register a case from a phone, on the station LAN*
**Main:** untouched at `a970120` · **NOT merged** · working tree clean
**Date:** 3 August 2026

---

## 1. What was built

An officer standing at the scene has a phone, not a keyboard. This adds a lean field page
at `/m` — purpose-built for a phone, not the desktop UI shrunk — plus a PIN login path so
they can get in without typing a password on a touchscreen.

Nothing new was invented behind it: the account is read by the same `/intake/extract` the
desktop calls, the wait is the same `ExtractionProgress` component, and **Register** is the
same `/intake/commit` writing into the same pool in one transaction. A case entered on a
phone is, once registered, indistinguishable from one entered at a desk.

### Files ADDED (2)

| File | What it is |
|---|---|
| `frontend/app/m/page.tsx` | The mobile field page. Two states — PIN login → field intake. Single column, ≥48px touch targets, own compact EN/हिं/ગુ switcher, no sidebar/topbar. Includes a self-contained ~20-line draft reconcile (see §5). |
| `frontend/components/MobileIdleLogout.tsx` | Idle sign-out for `/m`. Reuses the existing `evaluateIdle`/`secondsRemaining` policy and `clearToken()`, but lands back on `/m` rather than the desktop `/login`. |

### Files CHANGED (6)

| File | Change | Additive? |
|---|---|---|
| `backend/app/api/auth.py` | **+110 lines**: new `POST /api/auth/login-pin`, its own `_pin_login_failures` dict, `PinLoginRequest`, `_pin_login_rejected()`, `_ABSENT_PIN_HASH`. Existing `login` / `me` / `verify-pin` / `register` **untouched**. | Additive |
| `backend/app/core/config.py` | **+6 lines**: new `CORS_EXTRA_ORIGINS: str = ""` setting. | Additive (defaulted) |
| `backend/app/main.py` | CORS `allow_origins` now appends env-supplied origins to the existing two. | **Approved edit #2** |
| `frontend/lib/api.ts` | `baseURL` reads `NEXT_PUBLIC_API_URL`, falling back to the same hardcoded string. | **Approved edit #1** |
| `frontend/components/AppShell.tsx` | Bare-render condition now also matches `/m`. | **Approved edit #3** |
| `frontend/lib/i18n.ts` | **+96 lines**: 26 new `m.*` keys × EN/HI/GU. No existing key altered. | Additive |

**Diffstat vs main:** 6 files changed, 235 insertions(+), 3 deletions(-) — plus the 2 new files.

**No schema change. No migration. No existing endpoint, generator, chat capability, step-up
PIN, or desktop idle-logout modified.**

---

## 2. The three approved edits — desktop behaviour confirmed unchanged

### Edit 1 — `frontend/lib/api.ts`
```ts
export const api = axios.create({
  baseURL: process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000",
});
```
With the env var unset the string is byte-identical to before. A phone cannot reach
`localhost` (localhost *is* the phone), so this was unavoidable.

### Edit 2 — `backend/app/main.py`
```python
_EXTRA_ORIGINS = [o.strip() for o in settings.CORS_EXTRA_ORIGINS.split(",") if o.strip()]
allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", *_EXTRA_ORIGINS]
```
The two localhost origins are retained exactly. With `CORS_EXTRA_ORIGINS` empty the list is
unchanged. The phone's origin is the PC's LAN IP, which the browser would otherwise block.

### Edit 3 — `frontend/components/AppShell.tsx`
```ts
const bareRoute = pathname === "/login" || pathname === "/m" || pathname.startsWith("/m/");
const showChrome = ready && !!user && !bareRoute;
```
AppShell wraps every route from the root layout; without this the mobile page would render
inside a 280px sidebar. Only the new path matches — verified `/cases/intake` still receives
full chrome.

### Verification that desktop is unchanged
Tested with **`.env.local` removed entirely**, so the fallback path was the one exercised:

- Password login `io/io123` → `/cases` ✅ (used `http://localhost:8000`)
- Sidebar renders all 7 links; topbar search present; `main.ml-[280px]` on `/cases/intake` ✅
- `frontend` typecheck (`tsc --noEmit`) exit 0 ✅

---

## 3. Proof results

### Proof 1 — Desktop unchanged ✅

| Check | Result |
|---|---|
| Password login | ✅ `io/io123` → `/cases`, localhost fallback |
| Desktop chrome | ✅ 7 sidebar links, topbar search, sidebar offset on `/cases/intake` |
| Desktop intake | ✅ extracted `[('Ramesh Patel','COMPLAINANT')]`; `auto_filled: [police_station, district, fir_date]` → Satellite Police Station / Ahmedabad |
| 8 generators | ✅ all produced files — PANCHNAMA v23, REMAND v33, SEIZURE_RECEIPT v18, MEDICAL_LETTER v15, LERS_PRESERVATION v13, LERS_RECORDS v13, CHARGESHEET v36, CUSTODY_LETTER v16 |
| 4 chat capabilities | ✅ `QUERY/EVIDENCE`, `QUERY/WITNESSES`, `QUERY/ITEMS`, `GENERATE/PANCHNAMA` |
| Chat guard | ✅ "is the accused guilty?" → `UNKNOWN` (still refuses legal opinion) |
| Step-up PIN | ✅ `ok:true` / `wrong_pin, attempts_remaining:4` / resets on success — **60s lockout unchanged** |
| Desktop idle-logout | ✅ `IdleLogout.tsx` not in the diff; still mounted in AppShell's chrome branch |

### Proof 2 — PIN login ✅

**Valid login**
- `io` + `1234` → `200`, role `IO`, "Inspector Rajesh Chauhan"
- JWT works on `/api/auth/me` and `/api/cases` — RBAC applies identically
- **Claims identical to password login**, verified by decoding both:
  - password JWT: `{'sub': '1', 'role': 'IO'}`
  - PIN JWT: `{'sub': '1', 'role': 'IO'}` → `IDENTICAL SHAPE: True`

**Uniform 401 — all four modes returned the byte-identical body `{"detail":"Invalid username or PIN"}`**

| Case | Status |
|---|---|
| Wrong PIN (real user, has PIN) | 401 ✅ |
| Unknown username | 401 ✅ |
| Real user with **no PIN set** (fails closed) | 401 ✅ |
| Empty username | 401 ✅ |

**Lockout (5 attempts → 5 minutes)**
- 5 wrong PINs for `io2` → all 401
- The **correct** PIN for `io2` afterwards → still 401, same uniform body ✅
- `io` unaffected → 200 ✅ (per-username keying works)

**Audit trail**
- 9 `auth.pin_login` rows written, action `CREATE`
- `performed_by` set when the username matched an account, `NULL` for `nosuchofficer` / empty
- Progression recorded: `attempt 1..4 = "failed"`, `attempt 5 = "locked_out"`
- **Zero PIN values anywhere**: counts for `0000`, `1234`, `9999`, `5678` all **0**; no `pin` key present
- Backend log line contains no digits: `pin-login: 'io2' is locked out`

**No redirect-loop**: a wrong PIN in the browser stayed on `/m`, showed the error and cleared
the PIN field. The `/api/auth/login-**pin**` naming is what makes this work — the existing
401 interceptor matches any URL containing `/api/auth/login` and treats it as a failed
sign-in rather than a dead session. `pin-login` would NOT have matched and would have
bounced the page.

**Step-up counter untouched** — re-verified after all of the above:
`ok:true` → `wrong_pin, attempts_remaining:4` → `ok:true`. Still max 5 / 60s.

### Proof 3 — Mobile intake end-to-end, reaching the shared pool ✅

Driven through the browser at **`http://192.168.29.188:3000/m`** — the real LAN URL, so
CORS was exercised for real, not via localhost.

1. PIN login as `io` → field intake, header shows "Inspector Rajesh Chauhan"
2. Described: *"On 3 August 2026 at about 9 pm, complainant Meena Shah reported that Dinesh
   Rana broke the lock of her shop at Bopal, Ahmedabad and stole cash of forty thousand
   rupees and a laptop."*
3. **`ExtractionProgress` visible mid-flight** — `"progress_activityReading the narrative…0s"`
   (the reused component, not a copy)
4. Draft appeared: Meena Shah (COMPLAINANT), Dinesh Rana (ACCUSED), 1 seized item,
   `incident_location = Bopal, Ahmedabad`, station chip *Satellite Police Station · Ahmedabad*
5. **Register → no second PIN prompt** (`secondPinPrompted: false`)
6. Registered as **case 44 `M-FIELD-0001-2026`**

**Shared pool confirmed** — queried back with a *password-login desktop token*:
```
search hit  : M-FIELD-0001-2026 | matched case_number
case_number : M-FIELD-0001-2026 | fir 221/2026
station     : Satellite Police Station / Ahmedabad
persons     : [('Meena Shah','COMPLAINANT'), ('Dinesh Rana','ACCUSED')]
seized      : ['cash of forty thousand rupees and a laptop']
diary       : 4 entries
```
Also **visible in the desktop case list** in the browser.

### Proof 4 — Gujarati ✅

- UI switched to ગુ: all labels Gujarati (`ક્રાઈમGPT ફિલ્ડ`, `વિગતો વાંચો`, `કેસ નોંધો`)
- Progress component in Gujarati: `"વિગત વાંચી રહ્યા છીએ…0 સે"`
- Described in Gujarati; extracted સુરેશ પટેલ (ACCUSED), items સોનાની ચેઈન + રોકડ રૂપિયા,
  location બોપલ ખાતે, narrative in Gujarati script
- Registered as **case 45 `M-FIELD-0002-2026`**, `complaint_language = GU`
- **Stored cleanly in Postgres** (verified directly, not through the console):
  `full_name = સુરેશ પટેલ` (10 chars), items and narrative intact
- Appears in the desktop case list with its Gujarati title

### Proof 5 — Idle-logout on `/m` ✅

Using the **existing** env knob `NEXT_PUBLIC_IDLE_TIMEOUT_SECONDS=30` (no code change):

- Warning appeared in Gujarati: *"9 સેકંડમાં સાઇન આઉટ — કોઈ પ્રવૃત્તિ નથી."*
- On expiry it landed on the **mobile PIN screen**, with the notice
  *"લાંબા સમય સુધી નિષ્ક્રિય રહેવાથી સાઇન આઉટ કરાયું."*
- Session fully torn down and **stayed on `/m`** (not the desktop `/login`):

```json
{ "stayedOnMobileRoute": true, "tokenCleared": true,
  "userCleared": true, "stepUpCleared": true,
  "noticeShown": true, "pinFormShown": true }
```

Temporary env lines were reverted afterwards.

### Proof 6 — LAN run instructions

See §4 below.

---

## 4. LAN run instructions

**PC IP: `192.168.29.188`** (Ethernet adapter).
Ignore `172.30.208.1` and `172.19.208.1` — those are WSL / Hyper-V virtual adapters and are
not reachable from a phone.

### Start both servers on all interfaces

```bash
# 1. Backend
cd backend
set USE_TF=0
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 2. Frontend
cd frontend
npm run dev -- -H 0.0.0.0
```

### `frontend/.env.local` — **gitignored, you must create this yourself**

`.gitignore:30` ignores `.env.local`, so it is NOT in the commit. It exists on this machine
but will not travel with the branch.

```
NEXT_PUBLIC_API_URL=http://192.168.29.188:8000
```

### `backend/.env` — already appended on this machine

```
CORS_EXTRA_ORIGINS=http://192.168.29.188:3000
```

### Firewall — run yourself in an **Administrator** PowerShell

I did not run these: changing system firewall rules is a security setting and is yours to make.

```powershell
New-NetFirewallRule -DisplayName "CrimeGPT frontend 3000" -Direction Inbound -Protocol TCP -LocalPort 3000 -Action Allow
New-NetFirewallRule -DisplayName "CrimeGPT backend 8000"  -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow
```

> **Your network profile is currently `Public`**, which is the strict Windows Firewall
> profile. Node.js already has inbound Allow rules (so port 3000 may already work), but
> **Python/uvicorn has none — port 8000 is the one most likely to block your phone.**
> Symptom: the page at `/m` loads fine but sign-in hangs or errors.

### On the phone (same Wi-Fi)

```
http://192.168.29.188:3000/m
```
Sign in: `io` / PIN `1234`.

### Current stack state (verified after the last restart)

```
http://192.168.29.188:3000/m       -> 200
http://192.168.29.188:8000/health  -> 200
http://localhost:3000/login        -> 200
port 3001                          -> refused (no orphan)
```

---

## 5. Design notes

### The mobile draft reconcile is NOT the desktop merge
The desktop `mergeExtraction` was **not imported, refactored or touched**. The desktop has an
"Add person" button, so a row there may have come from the officer's own hand, and its merge
needs provenance plus a two-turn sweep to tell a row the extractor retracted from one it never
saw. The mobile page has no such button — every row originates from an extraction, so the
latest extraction is simply the truth. The mobile rule is ~20 self-contained lines: rows the
officer has edited are kept exactly as they left them (and survive even if the extractor stops
mentioning them); everything else comes fresh from the latest extraction.

### No double PIN
The mobile page deliberately does **not** use `useStepUp()`. The officer authenticated by PIN
seconds earlier; asking again at Register would be ceremony, not security. The confirmation
gate itself remains — nothing is written until the draft has been read and the button pressed.
`markPinVerified()` is deliberately **not** called either, so a mobile session does not
silently pre-clear the desktop step-up flag. `StepUp.tsx` and desktop behaviour are untouched.

### PIN as a primary credential — the security trade-off
Everywhere else in the codebase a PIN is a *step-up*: the officer has already proven identity
with a password. Here the PIN **is** the credential — four digits between the station LAN and
a token that can register a case. Hardening applied:

- Its own `_pin_login_failures` counter, so the step-up's behaviour is untouched
- 5 attempts → **5 minute** lockout (step-up uses 60s)
- One identical 401 for every failure mode
- A bcrypt verify runs even when there is no account, so timing cannot enumerate usernames
- Fails closed: no `pin_hash` → 401, never a bypass
- Every failed attempt audit-logged; the PIN itself never logged, stored or echoed

**Recommendation: keep this LAN-only. Do not expose port 8000 beyond the station network.**

---

## 6. Gaps and things to know

Nothing failed outright. These are the honest caveats:

1. **Two test cases were created and left in place** — case 44 `M-FIELD-0001-2026` and case 45
   `M-FIELD-0002-2026` — so you can see them on the desktop. The pool is now 4 cases rather
   than the 2-case baseline. Say the word and I will remove them.
2. **`io2` is PIN-locked** from the lockout test. It self-clears 5 minutes after the test;
   `io2`'s *password* login was never affected.
3. **Mobile does not auto-suggest a case number.** The desktop suggests `I-CR-####-2026`; on
   the phone the officer must type one. That is typing friction on a touchscreen — a ~3-line
   addition if you want it.
4. **JWT-expiry edge**: if the token expires mid-session on mobile, the *existing* global 401
   interceptor sends the phone to `/login` (the desktop password screen). Fixing that needs a
   4th shared-file edit, so I left it alone. Idle-logout normally fires first.
5. **HTTP only, no TLS.** PINs and JWTs cross the LAN in clear text. Acceptable only on a
   trusted station network — worth stating in the deck rather than being discovered.
6. **Cosmetic**: the Gujarati auto-title reads "બોપલ ખાતે ખાતે બનેલ ઘટના" — "ખાતે" doubled
   because the extracted location already ended in it. This is pre-existing backend title
   composition, not introduced by this slice.
7. **Mobile is capture-only** by design — no evidence upload, no document generation, no chat,
   no legal analysis. Those stay on the desktop.
8. **No live desktop notification** when a field case lands. The case *is* in the shared pool
   immediately and a desktop refresh shows it; live push is the (b)-roadmap seam and was not
   built.
9. **`.env.local` is gitignored** — the branch alone will not configure a fresh machine for
   LAN use. See §4.

---

## 7. Status

- Built, tested, committed as **`90b9f02`** on **`feat/mobile-intake`**
- Working tree clean · frontend typecheck exit 0
- **Main untouched at `a970120`** · **NOT merged**
