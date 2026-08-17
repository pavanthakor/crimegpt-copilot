#Requires -Version 5.1
<#
.SYNOPSIS
  Prove a CrimeGPT install actually works. Standalone - run any time the servers are up.

.DESCRIPTION
  setup.ps1 installs and ends at READY without starting servers. This script is the other
  half: it exercises the running stack and prints PASS/FAIL with a fix for every failure.

  Run it after .\start.ps1, or any time before a demo.

  Two deliberate choices:

  * Everything is hit on 127.0.0.1, never "localhost". On Windows "localhost" resolves to
    IPv6 ::1 first; uvicorn binds IPv4, so each NEW connection stalls ~2s before falling
    back. Measured and reproducible on the demo machine. A timing taken through
    "localhost" is measuring the resolver, not the app.

  * It does not re-implement scripts\preflight.py. That already checks Postgres, Alembic
    head, seed rows, Chroma = 1059, judgments = 41 and Ollama + qwen2.5:7b. This runs it
    (read-only: no --fix, no --no-start side effects) and then adds only what it cannot
    know - the things that need the HTTP stack alive.

.PARAMETER FullCheck
  Opt IN to the two checks that WRITE to the database: document generation and the
  step-up probe.

  READ-ONLY BY DEFAULT, deliberately. Generating a document bumps a real document
  version, and version history is shown on stage - a verification run must not quietly
  advance it. Without this switch nothing in the database changes.

.PARAMETER CaseId
  Case used by -FullCheck's document generation. Default 2, deliberately NOT the case 1
  demo case, so a verification run never touches the case you demo.
#>
[CmdletBinding()]
param(
    [switch]$FullCheck,
    [int]$CaseId = 2
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Continue"

$Root     = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $Root) { $Root = (Get-Location).Path }
$Backend  = Join-Path $Root "backend"
$VenvPy   = Join-Path $Backend ".venv\Scripts\python.exe"
$EnvLocal = Join-Path $Root "frontend\.env.local"

$API  = "http://127.0.0.1:8000"
$UI   = "http://127.0.0.1:3000"

$script:Pass = 0
$script:Fail = 0
$script:Notes = @()

function Ok([string]$name, [string]$detail) {
    Write-Host ("  PASS  " + $name) -ForegroundColor Green
    if ($detail) { Write-Host ("        " + $detail) -ForegroundColor DarkGray }
    $script:Pass++
}
function Bad([string]$name, [string]$detail, [string]$fix) {
    Write-Host ("  FAIL  " + $name) -ForegroundColor Red
    if ($detail) { Write-Host ("        " + $detail) -ForegroundColor DarkGray }
    Write-Host ("        FIX: " + $fix) -ForegroundColor Yellow
    $script:Fail++
}
function Note([string]$msg) { $script:Notes += $msg }
function Section([string]$msg) { Write-Host ""; Write-Host ("== " + $msg) -ForegroundColor Cyan }

function Try-Get([string]$url, [int]$timeoutSec = 10) {
    try { return Invoke-WebRequest -Uri $url -TimeoutSec $timeoutSec -UseBasicParsing }
    catch { return $null }
}

Write-Host ""
Write-Host "CrimeGPT verification" -ForegroundColor White
Write-Host "(all HTTP on 127.0.0.1 - 'localhost' costs ~2s per new connection on Windows)"

# ---------------------------------------------------------------------------
# 1. Dependencies that need no HTTP stack - delegate to preflight.py
# ---------------------------------------------------------------------------
Section "Dependencies (scripts\preflight.py - Postgres, Alembic, seed, Chroma 1059, Ollama)"
if (-not (Test-Path $VenvPy)) {
    Bad "backend venv present" "backend\.venv\Scripts\python.exe not found" "Run .\setup.ps1 first."
} else {
    # No --fix (never mutate during verification). --no-start so it reports Postgres
    # rather than silently starting containers behind your back.
    $pfOut = & $VenvPy (Join-Path $Root "scripts\preflight.py") --no-start 2>&1
    $pfExit = $LASTEXITCODE
    $pfOut | ForEach-Object { Write-Host ("        " + $_) -ForegroundColor DarkGray }

    if ($pfExit -eq 0) {
        Ok "preflight.py all checks" "Postgres, Alembic head, seed, Chroma=1059, judgments=41, Ollama+qwen2.5:7b"
    } else {
        # preflight's seed check asserts the EXACT seed baseline (got == want), so any
        # machine that has registered real cases fails it - which is normal, not broken.
        # verify_seed_counts.py answers the question we actually care about here
        # ("is the seed usable": users >= 4, cases >= 2), so use it to tell a surplus
        # apart from a genuinely missing/half-seeded database.
        $pfText = ($pfOut | Out-String)
        # @() forces an array - under Set-StrictMode a single match has no .Count.
        $failed = @([regex]::Matches($pfText, '\[FAIL\]\s+(.+?)\s{2,}') |
                    ForEach-Object { $_.Groups[1].Value.Trim() })
        $onlySeed = ($failed.Count -eq 1 -and $failed[0] -match 'Seed data present')

        & $VenvPy (Join-Path $Root "scripts\verify_seed_counts.py") 2>&1 | Out-Null
        $seedUsable = ($LASTEXITCODE -eq 0)

        if ($onlySeed -and $seedUsable) {
            Write-Host "  WARN  preflight: seed counts differ from the pristine baseline" -ForegroundColor DarkYellow
            Write-Host "        Your database has MORE than the seeded rows - normal on a machine that has" -ForegroundColor DarkGray
            Write-Host "        registered cases. verify_seed_counts.py confirms the seed is usable" -ForegroundColor DarkGray
            Write-Host "        (users >= 4, cases >= 2). Not treated as a failure." -ForegroundColor DarkGray
            Ok "preflight.py dependency checks" "all non-seed checks PASS (Postgres, Alembic, Chroma=1059, judgments=41, Ollama)"
        } else {
            Bad "preflight.py" "one or more dependency checks failed (detail above)" `
                "Read the FAIL lines above. Chroma empty -> cd backend; .\.venv\Scripts\python.exe -m app.ai.rag (~2 min). Migrations behind -> .\.venv\Scripts\python.exe ..\scripts\preflight.py --fix. Seed missing -> cd backend; .\.venv\Scripts\python.exe -m app.seed"
        }
    }
}

# ---------------------------------------------------------------------------
# 2. Backend on 127.0.0.1
# ---------------------------------------------------------------------------
Section "HTTP stack"
$health = Try-Get "$API/health"
if ($health -and $health.StatusCode -eq 200) {
    Ok "backend responds on 127.0.0.1:8000" $health.Content
} else {
    Bad "backend responds on 127.0.0.1:8000" "no response from $API/health" `
        "Start it: .\start.ps1 -BackendOnly   (never bare 'uvicorn' - it can bind Python 3.11 without docxtpl)"
}

$db = Try-Get "$API/health/db"
if ($db -and $db.StatusCode -eq 200 -and $db.Content -match '"ok"') {
    Ok "backend reaches Postgres" $db.Content
} else {
    Bad "backend reaches Postgres" "GET /health/db did not return db=ok" `
        "Start Docker Desktop, then: docker compose up -d"
}

# ---------------------------------------------------------------------------
# 3. Frontend on 3000
# ---------------------------------------------------------------------------
$ui = Try-Get $UI 20
if ($ui -and $ui.StatusCode -eq 200) {
    Ok "frontend responds on port 3000" "$($ui.RawContentLength) bytes"
} else {
    Bad "frontend responds on port 3000" "no response from $UI" `
        "Start it: .\start.ps1 -FrontendOnly. If it silently took 3001, kill the orphaned node and re-run (npm run dev -- -p 3000)."
}

# ---------------------------------------------------------------------------
# 4. Auth - all three roles
# ---------------------------------------------------------------------------
Section "Authentication and RBAC"
$tokens = @{}
$roleMap = @{ io = "IO"; sho = "SHO"; legal = "LEGAL_ADVISOR" }
$loginOk = $true
foreach ($u in @("io", "sho", "legal")) {
    try {
        $body = @{ username = $u; password = "$($u)123" } | ConvertTo-Json
        $r = Invoke-RestMethod "$API/api/auth/login" -Method Post -Body $body -ContentType "application/json" -TimeoutSec 20
        if ($r.role -ne $roleMap[$u]) { throw "role was $($r.role), expected $($roleMap[$u])" }
        $tokens[$u] = $r.token
    } catch {
        $loginOk = $false
        Bad "login $u" $_.Exception.Message "Re-seed: cd backend; .\.venv\Scripts\python.exe -m app.seed (idempotent, does not wipe)"
    }
}
if ($loginOk) { Ok "all 3 roles log in" "io/IO, sho/SHO, legal/LEGAL_ADVISOR" }

# ---------------------------------------------------------------------------
# 5. Document generation end to end
# ---------------------------------------------------------------------------
Section "Document generation"
if (-not $FullCheck) {
    Write-Host "  SKIP  document generation - read-only run. Pass -FullCheck to test it." -ForegroundColor DarkYellow
    Write-Host "        (it bumps a real document version; version history is demo material)" -ForegroundColor DarkGray
} elseif (-not $tokens.ContainsKey("sho")) {
    Bad "one document generates end to end" "no SHO token (login failed above)" "Fix login first."
} else {
    try {
        $h = @{ Authorization = "Bearer $($tokens['sho'])" }
        $doc = Invoke-RestMethod "$API/api/cases/$CaseId/documents/SEIZURE_RECEIPT?lang=en" -Method Post -Headers $h -TimeoutSec 120
        $dl = Invoke-WebRequest "$API/api/documents/$($doc.id)/download" -Headers $h -TimeoutSec 60 -UseBasicParsing
        if ($dl.StatusCode -eq 200 -and $dl.RawContentLength -gt 20000) {
            Ok "one document generates end to end" "case $CaseId -> doc $($doc.id) v$($doc.version) $($doc.status), $($dl.RawContentLength) bytes"
            Note "Document generation wrote: case $CaseId SEIZURE_RECEIPT is now v$($doc.version) (previous version archived to document_versions)."
        } else {
            Bad "one document generates end to end" "download was $($dl.RawContentLength) bytes" `
                "Check templates\ has all 8 .docx and that docxtpl imports under backend\.venv."
        }
    } catch {
        Bad "one document generates end to end" $_.Exception.Message `
            "A 400 means the case lacks required pool fields. A 500 usually means docxtpl is missing - re-run .\setup.ps1."
    }
}

# ---------------------------------------------------------------------------
# 6. Step-up enforcement (commit 495a34a) - server-side, silently important
# ---------------------------------------------------------------------------
Section "Step-up PIN enforcement (server-side)"
if (-not $FullCheck) {
    Write-Host "  SKIP  step-up probe - read-only run. Pass -FullCheck to test it." -ForegroundColor DarkYellow
    Write-Host "        (a refusal writes one auth.step_up audit row)" -ForegroundColor DarkGray
} elseif (-not $tokens.ContainsKey("io")) {
    Bad "commit without step-up is refused" "no IO token" "Fix login first."
} else {
    # A fresh password session has NOT stepped up, so commit must be refused with 401.
    # Nothing is written on refusal except the audit row that records it.
    $stamp = Get-Date -Format "HHmmss"
    $payload = @{
        case = @{ case_number = "VERIFY-$stamp"; title = "verify.ps1 step-up probe"
                  police_station = "Satellite Police Station"; district = "Ahmedabad" }
        persons = @(); seized_items = @()
    } | ConvertTo-Json -Depth 6
    $status = 0
    try {
        Invoke-RestMethod "$API/api/intake/commit" -Method Post `
            -Headers @{ Authorization = "Bearer $($tokens['io'])" } `
            -Body $payload -ContentType "application/json" -TimeoutSec 60 | Out-Null
        $status = 201
    } catch {
        if ($_.Exception.Response) { $status = [int]$_.Exception.Response.StatusCode }
    }
    if ($status -eq 401) {
        Ok "commit without step-up returns 401" "server-side gate live (495a34a); no case was created"
    } elseif ($status -eq 201) {
        Bad "commit without step-up returns 401" "commit SUCCEEDED without a step-up - the gate is NOT enforced" `
            "You are running code older than 495a34a, or require_step_up was removed from intake_commit. Check: git log --oneline -1"
    } else {
        Bad "commit without step-up returns 401" "got HTTP $status" `
            "Expected 401. A 403 means the role gate fired first; a 404 means the case is not visible."
    }
}

# ---------------------------------------------------------------------------
# 7. LAN / mobile - and the firewall diagnosis
# ---------------------------------------------------------------------------
Section "LAN / mobile field page"
$lanIp = $null
if (Test-Path $EnvLocal) {
    $line = Select-String -LiteralPath $EnvLocal -Pattern '^\s*NEXT_PUBLIC_API_URL\s*=\s*http://([0-9\.]+):8000' |
            Select-Object -First 1
    if ($line) { $lanIp = $line.Matches[0].Groups[1].Value }
}
if (-not $lanIp) {
    Bad "frontend\.env.local names a LAN IP" "NEXT_PUBLIC_API_URL not found or not an IP in $EnvLocal" `
        "Re-run .\setup.ps1 - it writes .env.local when missing. Without it the phone calls 'localhost', which is the phone itself."
} else {
    Ok "frontend\.env.local names a LAN IP" "NEXT_PUBLIC_API_URL -> http://${lanIp}:8000"

    $lanApi = Try-Get "http://${lanIp}:8000/health" 8
    $lanUi  = Try-Get "http://${lanIp}:3000/m" 15

    if ($lanUi -and $lanUi.StatusCode -eq 200) {
        Ok "/m reachable on the LAN IP" "http://${lanIp}:3000/m ($($lanUi.RawContentLength) bytes)"
    } else {
        # The signature failure: loopback fine, LAN blocked.
        if ($health) {
            Bad "/m reachable on the LAN IP" "port 3000 answers on 127.0.0.1 but NOT on ${lanIp} - this is the Windows firewall blocking the LAN interface" `
                "Run the two New-NetFirewallRule commands from the setup READY output in an ADMIN PowerShell, then re-run. Also confirm the server is bound to 0.0.0.0: .\start.ps1 -Lan"
        } else {
            Bad "/m reachable on the LAN IP" "nothing is listening" "Start the servers: .\start.ps1 -Lan"
        }
    }

    if ($lanApi -and $lanApi.StatusCode -eq 200) {
        Ok "API reachable on the LAN IP" "http://${lanIp}:8000/health"
    } else {
        Bad "API reachable on the LAN IP" "port 8000 answers on 127.0.0.1 but NOT on ${lanIp} - this is the Windows firewall blocking the LAN interface. This is the exact cause of '/m loads but sign-in hangs'." `
            "Admin PowerShell: New-NetFirewallRule -DisplayName 'CrimeGPT backend 8000' -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow. Then bind LAN: .\start.ps1 -Lan"
    }
}

# ---------------------------------------------------------------------------
# 8. Runtime configuration the demo depends on
# ---------------------------------------------------------------------------
Section "Runtime configuration"
# Check the LIVE eviction deadline, not the environment variable.
#
# An env var that is SET but NOT IN EFFECT is worse than one that is unset, because it
# reads as PASS while the model still evicts. OLLAMA_KEEP_ALIVE is read by the Ollama
# SERVER at startup, so setting it changes nothing until Ollama is restarted. The only
# honest source of truth is what Ollama itself reports: expires_at on the resident model.
$envKeep = [Environment]::GetEnvironmentVariable("OLLAMA_KEEP_ALIVE", "User")
$envNote = if ($envKeep) { "env var OLLAMA_KEEP_ALIVE='$envKeep' (user scope)" } else { "env var OLLAMA_KEEP_ALIVE is unset" }
try {
    $ps = Invoke-RestMethod "http://127.0.0.1:11434/api/ps" -TimeoutSec 10
    $resident = @($ps.models)
    if ($resident.Count -eq 0) {
        Write-Host "  WARN  model eviction deadline: no model resident in Ollama right now" -ForegroundColor DarkYellow
        Write-Host "        Cannot read a live deadline until something loads the model. $envNote" -ForegroundColor DarkGray
        Write-Host "        Run one analysis, then re-run this check." -ForegroundColor DarkGray
    } else {
        $m = $resident[0]
        $mins = ([datetime]$m.expires_at - (Get-Date)).TotalMinutes
        if ($mins -ge 60) {
            Ok "model stays resident (live check)" ("{0} evicts in {1:N1} h - keep-alive IS in effect. {2}" -f $m.name, ($mins / 60), $envNote)
        } else {
            Bad "model stays resident (live check)" `
                ("{0} evicts in {1:N0} min - keep-alive is NOT in effect. {2}" -f $m.name, $mins, $envNote) `
                $(if ($envKeep) {
                    "The variable is set but Ollama has not picked it up. RESTART OLLAMA (quit it from the tray and reopen), then re-run."
                  } else {
                    "Re-run .\setup.ps1 to set OLLAMA_KEEP_ALIVE=24h, then RESTART OLLAMA. Otherwise the first request after a demo pause pays a ~6.9s reload."
                  })
        }
        Note "expires_at reflects the keep_alive of the most recent request, so this is the real deadline right now."
    }
} catch {
    Bad "model stays resident (live check)" "could not query http://127.0.0.1:11434/api/ps : $($_.Exception.Message)" `
        "Start the Ollama app, then re-run."
}

if ($tokens.ContainsKey("io")) {
    try {
        $dm = Invoke-RestMethod "$API/api/system/demo-mode" -Headers @{ Authorization = "Bearer $($tokens['io'])" } -TimeoutSec 20
        $what = if ($dm.demo_mode) { "cached analysis + documents for case 1 are served instantly; judgments and weak-charge still call Qwen live" }
                else { "everything runs live against Qwen - slower, and subject to the ~1-in-20 slow intake" }
        Ok "DEMO_MODE resolved" "DEMO_MODE = $($dm.demo_mode). In effect: $what"
    } catch {
        Bad "DEMO_MODE resolved" $_.Exception.Message "Backend must be up."
    }
}

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "========================================" -ForegroundColor White
if ($script:Fail -eq 0) {
    Write-Host "  VERIFIED - $($script:Pass) passed, 0 failed" -ForegroundColor Green
} else {
    Write-Host "  $($script:Fail) FAILED, $($script:Pass) passed" -ForegroundColor Red
    Write-Host "  Each FAIL above carries its own FIX line." -ForegroundColor Yellow
}
Write-Host "========================================" -ForegroundColor White
foreach ($n in $script:Notes) { Write-Host "  note: $n" -ForegroundColor DarkGray }
Write-Host ""
Write-Host "Phone reminder: a handset still holding a PIN token minted before commit 495a34a" -ForegroundColor Yellow
Write-Host "has no pin_login claim and will be refused at Register. Sign out on the phone and" -ForegroundColor Yellow
Write-Host "sign back in with the PIN once. One tap, per device." -ForegroundColor Yellow
Write-Host ""
exit ([int]($script:Fail -gt 0))
