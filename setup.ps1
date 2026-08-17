#Requires -Version 5.1
<#
.SYNOPSIS
  One-command setup: fresh CrimeGPT clone -> runnable demo stack (Windows).

.DESCRIPTION
  Encodes the working machine setup (not the obvious-but-broken shortcuts).
  Does NOT start the API/UI servers - run start.ps1 (or the printed commands) in
  separate terminals afterward.

  Critical: backend always uses Python 3.13 via `python -m uvicorn` (never bare
  `uvicorn`, which can pick Python 3.11 without docxtpl and break .docx generation).
#>
[CmdletBinding()]
param()

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $Root) { $Root = (Get-Location).Path }
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"
$VenvDir = Join-Path $Backend ".venv"
$VenvPython = Join-Path $VenvDir "Scripts\python.exe"

function Write-Step([string]$msg) {
    Write-Host ""
    Write-Host "==> $msg" -ForegroundColor Cyan
}
function Write-Ok([string]$msg) { Write-Host "  OK  $msg" -ForegroundColor Green }
function Write-Warn([string]$msg) { Write-Host "  WARN  $msg" -ForegroundColor Yellow }
function Fail([string]$msg) {
    Write-Host ""
    Write-Host "SETUP FAILED: $msg" -ForegroundColor Red
    Write-Host "See SETUP.md for prerequisites and fixes." -ForegroundColor Red
    exit 1
}

# ---------------------------------------------------------------------------
# 1. Prerequisite check
# ---------------------------------------------------------------------------
Write-Step "Checking prerequisites"

# Docker
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    Fail "Docker is not installed or not on PATH. Install Docker Desktop, start it, then re-run."
}
try {
    docker info 1>$null 2>$null
    if ($LASTEXITCODE -ne 0) { throw "docker info failed" }
    Write-Ok "Docker is running"
} catch {
    Fail "Docker is installed but the engine is not running. Start Docker Desktop and wait until it is ready, then re-run."
}

# Ollama
if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
    Fail "Ollama is not installed or not on PATH. Install from https://ollama.com and ensure 'ollama' is on PATH."
}
try {
    ollama list 1>$null 2>$null
    if ($LASTEXITCODE -ne 0) { throw "ollama list failed" }
    Write-Ok "Ollama responds (ollama list)"
} catch {
    Fail "Ollama is installed but not responding. Start the Ollama app / service, then re-run."
}

# Node
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Fail "Node.js is not installed or not on PATH. Install Node 20+ from https://nodejs.org"
}
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    Fail "npm is not on PATH (install Node.js which includes npm)."
}
$nodeVer = (node -v) -replace '^v', ''
Write-Ok "Node.js $nodeVer / npm $((npm -v))"

# Python 3.13+ (the interpreter that must own docxtpl)
$PyCmd = $null
$candidates = @()
if (Get-Command py -ErrorAction SilentlyContinue) {
    foreach ($tag in @("-3.13", "-3.14", "-3")) {
        try {
            $exe = & py $tag -c "import sys; print(sys.executable)" 2>$null
            if ($LASTEXITCODE -eq 0 -and $exe) { $candidates += $exe.Trim() }
        } catch { }
    }
}
foreach ($name in @("python", "python3")) {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue
    if ($cmd) { $candidates += $cmd.Source }
}
$candidates = $candidates | Where-Object { $_ } | Select-Object -Unique

foreach ($exe in $candidates) {
    try {
        $verLine = & $exe -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')" 2>$null
        if ($LASTEXITCODE -ne 0) { continue }
        $parts = $verLine.Trim().Split(".")
        $maj = [int]$parts[0]; $min = [int]$parts[1]
        if ($maj -eq 3 -and $min -ge 13) {
            $PyCmd = $exe
            Write-Ok "Python $verLine at $PyCmd"
            break
        }
    } catch { }
}

if (-not $PyCmd) {
    Fail @"
Python 3.13+ was not found (required - this is the interpreter that has/gets docxtpl).
Bare 'uvicorn' on PATH often points at Python 3.11 and breaks document generation.

Install Python 3.13 from https://www.python.org/downloads/ (check 'Add python.exe to PATH')
or the Windows 'py' launcher with 3.13, then re-run.
"@
}

# ---------------------------------------------------------------------------
# 2. Python deps (venv on 3.13 - never bare system uvicorn)
# ---------------------------------------------------------------------------
Write-Step "Python dependencies (venv on Python 3.13+)"

if (-not (Test-Path $Backend)) { Fail "backend/ not found under $Root" }

# Prefer an existing venv only if it is 3.13+
$needVenv = $true
if (Test-Path $VenvPython) {
    $venvVer = & $VenvPython -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
    if ($LASTEXITCODE -eq 0) {
        $vp = $venvVer.Trim().Split(".")
        if ([int]$vp[0] -eq 3 -and [int]$vp[1] -ge 13) {
            $needVenv = $false
            Write-Ok "Reusing backend\.venv ($venvVer)"
        } else {
            Write-Warn "backend\.venv is Python $venvVer (need 3.13+); recreating"
            Remove-Item -Recurse -Force $VenvDir
        }
    }
}
if ($needVenv) {
    Write-Host "  Creating backend\.venv with $PyCmd ..."
    & $PyCmd -m venv $VenvDir
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path $VenvPython)) {
        Fail "Could not create backend\.venv with $PyCmd"
    }
    Write-Ok "Created backend\.venv"
}

Write-Host "  pip install -r requirements.txt ..."
& $VenvPython -m pip install --upgrade pip
# --break-system-packages is harmless inside a venv; kept for the rare case somebody
# retargets this script at a system 3.13 install.
& $VenvPython -m pip install -r (Join-Path $Backend "requirements.txt") --break-system-packages
if ($LASTEXITCODE -ne 0) {
    Fail "pip install failed. Fix the error above and re-run (idempotent)."
}

Write-Host "  Verifying imports (docxtpl, fastapi) ..."
& $VenvPython -c "import docxtpl, fastapi; print('docxtpl', docxtpl.__version__ if hasattr(docxtpl,'__version__') else 'ok'); print('fastapi', fastapi.__version__)"
if ($LASTEXITCODE -ne 0) {
    Fail "docxtpl/fastapi import failed under the venv Python. Document generation would break - do not start the server yet."
}
Write-Ok "docxtpl + fastapi importable under backend\.venv"

# Ensure backend/.env exists (gitignored)
$envFile = Join-Path $Backend ".env"
$envExample = Join-Path $Backend ".env.example"
if (-not (Test-Path $envFile)) {
    if (-not (Test-Path $envExample)) { Fail "backend/.env.example missing" }
    Copy-Item $envExample $envFile
    Write-Ok "Created backend\.env from .env.example (edit JWT_SECRET before production)"
} else {
    Write-Ok "backend\.env already present"
}

# Tribal: transformers otherwise tries TensorFlow
$env:USE_TF = "0"

# ---------------------------------------------------------------------------
# 3. Node deps
# ---------------------------------------------------------------------------
Write-Step "Node dependencies (frontend/)"
Push-Location $Frontend
try {
    npm install
    if ($LASTEXITCODE -ne 0) { Fail "npm install failed in frontend/" }
    Write-Ok "npm install complete"
} finally {
    Pop-Location
}

# ---------------------------------------------------------------------------
# 4. Docker / Postgres
# ---------------------------------------------------------------------------
Write-Step "Postgres (docker compose up -d)"
Push-Location $Root
try {
    docker compose up -d
    if ($LASTEXITCODE -ne 0) { Fail "docker compose up -d failed" }
} finally {
    Pop-Location
}

Write-Host "  Waiting for Postgres to accept connections ..."
$ready = $false
for ($i = 0; $i -lt 60; $i++) {
    docker compose -f (Join-Path $Root "docker-compose.yml") exec -T db pg_isready -U crimegpt -d crimegpt 1>$null 2>$null
    if ($LASTEXITCODE -eq 0) { $ready = $true; break }
    Start-Sleep -Seconds 2
}
if (-not $ready) {
    Fail "Postgres did not become ready within ~2 minutes. Check: docker compose ps / Docker Desktop."
}
Write-Ok "Postgres is ready (pg_isready)"

# ---------------------------------------------------------------------------
# 5. Migrations
# ---------------------------------------------------------------------------
Write-Step "Alembic migrations"
Push-Location $Backend
try {
    # Alembic logs to stderr; with $ErrorActionPreference=Stop that becomes a terminating
    # error in Windows PowerShell even on success - soften only for these calls.
    $prevEa = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & $VenvPython -m alembic upgrade head 2>&1 | ForEach-Object { Write-Host $_ }
    $upExit = $LASTEXITCODE
    $current = & $VenvPython -m alembic current 2>&1 | ForEach-Object { "$_" } | Out-String
    $ErrorActionPreference = $prevEa
    if ($upExit -ne 0) { Fail "alembic upgrade head failed" }
    Write-Host $current
    if ($current -notmatch "\(head\)") {
        Fail "Alembic is not at head after upgrade. Output was:`n$current"
    }
    Write-Ok "alembic at head"
} finally {
    Pop-Location
}

# ---------------------------------------------------------------------------
# 6. Ollama models
# ---------------------------------------------------------------------------
Write-Step 'Ollama models (qwen2.5:7b and nomic-embed-text)'
$list = ollama list 2>&1 | Out-String
foreach ($model in @("qwen2.5:7b", "nomic-embed-text")) {
    # `ollama list` shows NAME without always repeating the tag the same way - match name
    $short = $model.Split(":")[0]
    if ($list -match [regex]::Escape($model) -or $list -match "(?m)^$([regex]::Escape($short))\b") {
        Write-Ok "$model already present"
    } else {
        Write-Host "  Pulling $model (may take several minutes) ..."
        ollama pull $model
        if ($LASTEXITCODE -ne 0) { Fail "ollama pull $model failed" }
        Write-Ok "Pulled $model"
    }
}

# ---------------------------------------------------------------------------
# 7. Seed (idempotent - never --reset unless you ask for a wipe)
# ---------------------------------------------------------------------------
Write-Step "Demo seed (users + cases) - idempotent, no wipe"
Push-Location $Backend
try {
    $prevEa = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & $VenvPython -m app.seed 2>&1 | ForEach-Object { Write-Host $_ }
    $seedExit = $LASTEXITCODE
    $verifyScript = Join-Path $Root "scripts\verify_seed_counts.py"
    $verify = & $VenvPython $verifyScript 2>&1 | ForEach-Object { "$_" } | Out-String
    $verifyExit = $LASTEXITCODE
    $ErrorActionPreference = $prevEa
    if ($seedExit -ne 0) { Fail "python -m app.seed failed" }
    Write-Host $verify
    if ($verifyExit -ne 0) {
        Fail "Expected at least 4 seeded users and 2 cases. Got:`n$verify"
    }
    Write-Ok "Seed verified (users >= 4, cases >= 2)"
} finally {
    Pop-Location
}

# ---------------------------------------------------------------------------
# 7b. Gujarati rendering
#
# The old check warned whenever Noto Sans Gujarati was not installed system-wide. That
# cried wolf: the generated .docx names Noto Sans Gujarati but embeds no font, and on a
# machine WITHOUT it Word silently substitutes Shruti - which ships with Windows and
# renders Gujarati correctly (verified by rendering to PDF: Word embedded ABCDEE+Shruti
# and the glyphs were well-formed; an Arial control produced the classic tofu boxes).
# So the thing that actually matters is whether ANY Gujarati-capable font is present.
# ---------------------------------------------------------------------------
Write-Step "Gujarati rendering (.docx)"
$guFonts = @()
foreach ($f in @(
    @{ n = "Nirmala UI"; p = "$env:WINDIR\Fonts\NIRMALA.TTF" },
    @{ n = "Shruti";     p = "$env:WINDIR\Fonts\shruti.ttf" },
    @{ n = "Noto Sans Gujarati"; p = "$env:WINDIR\Fonts\NotoSansGujarati-Regular.ttf" }
)) {
    if (Test-Path $f.p) { $guFonts += $f.n }
}
if ($guFonts.Count -gt 0) {
    Write-Ok ("Gujarati-capable font(s) present: " + ($guFonts -join ", ") + " - .docx will render Gujarati")
} else {
    Write-Warn "No Gujarati-capable font found. Install fonts\NotoSansGujarati-Regular.ttf (right-click > Install) or Gujarati .docx may show boxes."
}

# ---------------------------------------------------------------------------
# 8. LAN config for the mobile field page (/m)
#
# ADDITIVE ONLY. An existing .env.local is never rewritten - a working demo machine's
# config always wins over a clean install. We report what is there and add only what is
# missing. Without NEXT_PUBLIC_API_URL the phone calls "localhost", which is the phone.
# ---------------------------------------------------------------------------
Write-Step "LAN config for the mobile field page"

function Get-LanIPv4 {
    # The adapter with a default gateway is the real LAN one. This machine also has
    # Hyper-V/WSL (172.x), OpenVPN and APIPA (169.254.x) addresses that must not win.
    $c = Get-NetIPConfiguration -ErrorAction SilentlyContinue |
         Where-Object { $_.IPv4DefaultGateway -and $_.NetAdapter.Status -eq 'Up' } |
         Select-Object -First 1
    if ($c) { return $c.IPv4Address.IPAddress }
    $f = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
         Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' `
                        -and $_.InterfaceAlias -notmatch 'vEthernet|Loopback' } |
         Select-Object -First 1
    if ($f) { return $f.IPAddress }
    return $null
}

$LanIp = Get-LanIPv4
if (-not $LanIp) {
    Write-Warn "Could not detect a LAN IPv4 address. /m will not work from a phone until you set frontend\.env.local by hand (SETUP.md)."
} else {
    Write-Ok "LAN IPv4 detected: $LanIp"

    $envLocal = Join-Path $Frontend ".env.local"
    if (Test-Path $envLocal) {
        $existing = Select-String -LiteralPath $envLocal -Pattern '^\s*NEXT_PUBLIC_API_URL\s*=\s*(.+)$' |
                    Select-Object -First 1
        if ($existing) {
            $val = $existing.Matches[0].Groups[1].Value.Trim()
            Write-Ok "frontend\.env.local already sets NEXT_PUBLIC_API_URL=$val (kept as-is)"
            if ($val -notmatch [regex]::Escape($LanIp)) {
                Write-Warn "  ...but it does not match the detected LAN IP $LanIp. If the phone cannot reach the API, update it by hand."
            }
        } else {
            Add-Content -LiteralPath $envLocal -Value "NEXT_PUBLIC_API_URL=http://${LanIp}:8000"
            Write-Ok "Appended NEXT_PUBLIC_API_URL to the existing frontend\.env.local"
        }
    } else {
        @(
            "# LAN access for the mobile field page (/m).",
            "# The phone loads the UI from this PC, so the API must not be 'localhost'.",
            "# Written by setup.ps1. Delete this file for desktop-only (falls back to localhost:8000).",
            "NEXT_PUBLIC_API_URL=http://${LanIp}:8000"
        ) | Set-Content -LiteralPath $envLocal -Encoding UTF8
        Write-Ok "Created frontend\.env.local with NEXT_PUBLIC_API_URL=http://${LanIp}:8000"
    }

    # CORS: the phone's browser origin is the LAN IP, not localhost. Append only.
    $envContent = Get-Content -LiteralPath $envFile -Raw
    if ($envContent -match '(?m)^\s*CORS_EXTRA_ORIGINS\s*=') {
        $cur = ([regex]::Match($envContent, '(?m)^\s*CORS_EXTRA_ORIGINS\s*=\s*(.*)$')).Groups[1].Value.Trim()
        Write-Ok "backend\.env already sets CORS_EXTRA_ORIGINS=$cur (kept as-is)"
        if ($cur -notmatch [regex]::Escape($LanIp)) {
            Write-Warn "  ...but it does not include $LanIp. The phone browser will be blocked by CORS until it does."
        }
    } else {
        Add-Content -LiteralPath $envFile -Value ""
        Add-Content -LiteralPath $envFile -Value "# Browser origin of the phone loading /m (added by setup.ps1)."
        Add-Content -LiteralPath $envFile -Value "CORS_EXTRA_ORIGINS=http://${LanIp}:3000"
        Write-Ok "Added CORS_EXTRA_ORIGINS=http://${LanIp}:3000 to backend\.env"
    }
}

# ---------------------------------------------------------------------------
# 9. Legal RAG corpus (Chroma) - /analyze returns nothing without it
#
# Both ingests are idempotent: they count the collection first and skip when it is
# already full (measured: 0.01s no-op on a populated collection). A COLD build embeds
# 1,059 sections on CPU at ~111 ms each - budget ~2 minutes, once.
# ---------------------------------------------------------------------------
Write-Step "Legal RAG corpus (Chroma) - idempotent, ~2 min on a cold machine"
Push-Location $Backend
try {
    $prevEa = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & $VenvPython -m app.ai.rag 2>&1 | ForEach-Object { Write-Host "  $_" }
    $ragExit = $LASTEXITCODE
    & $VenvPython -m app.ai.judgments 2>&1 | ForEach-Object { Write-Host "  $_" }
    $judExit = $LASTEXITCODE
    $ErrorActionPreference = $prevEa
    if ($ragExit -ne 0) { Fail "Chroma ingest failed (python -m app.ai.rag). /analyze would return nothing." }
    if ($judExit -ne 0) { Fail "Judgments ingest failed (python -m app.ai.judgments). /judgments would 503." }
    Write-Ok "Chroma corpus + judgments collection ready"
} finally {
    Pop-Location
}

# ---------------------------------------------------------------------------
# 10. Runtime tuning: Ollama keep-alive + LAN firewall
# ---------------------------------------------------------------------------
Write-Step "Runtime tuning (Ollama keep-alive, firewall)"

# Ollama evicts an idle model after 5 minutes by default; the next call then pays a
# ~6.9s reload (measured). This is a USER-SCOPE variable: it applies to every Ollama
# use on this account, not just CrimeGPT, and the Ollama SERVER only reads it at
# startup - so it does nothing until Ollama is restarted.
$existingKeep = [Environment]::GetEnvironmentVariable("OLLAMA_KEEP_ALIVE", "User")
$script:OllamaRestartNeeded = $false
if ($existingKeep) {
    Write-Ok "OLLAMA_KEEP_ALIVE already set to '$existingKeep' (user scope, kept as-is)"
} else {
    [Environment]::SetEnvironmentVariable("OLLAMA_KEEP_ALIVE", "24h", "User")
    $script:OllamaRestartNeeded = $true
    Write-Ok "Set OLLAMA_KEEP_ALIVE=24h (USER scope - affects all Ollama use on this account)"
    Write-Host ""
    Write-Host "  ****************************************************************" -ForegroundColor Yellow
    Write-Host "  *  THIS HAS NOT TAKEN EFFECT YET. YOU MUST RESTART OLLAMA.     *" -ForegroundColor Yellow
    Write-Host "  *                                                              *" -ForegroundColor Yellow
    Write-Host "  *  The Ollama SERVER reads this variable at startup. Until you  *" -ForegroundColor Yellow
    Write-Host "  *  quit Ollama from the system tray and reopen it, the model    *" -ForegroundColor Yellow
    Write-Host "  *  still evicts after 5 idle minutes and the first request      *" -ForegroundColor Yellow
    Write-Host "  *  after a demo pause pays a ~6.9s reload.                      *" -ForegroundColor Yellow
    Write-Host "  *                                                              *" -ForegroundColor Yellow
    Write-Host "  *  verify.ps1 checks the LIVE eviction deadline, not this       *" -ForegroundColor Yellow
    Write-Host "  *  variable, so it will keep reporting FAIL until you restart.  *" -ForegroundColor Yellow
    Write-Host "  ****************************************************************" -ForegroundColor Yellow
    Write-Host ""
}

# Firewall: PORT rules, deliberately. Program rules for node.exe/python.exe are what a
# Windows 'Allow access' prompt creates - invisible, easy to dismiss, and if python.exe
# is denied while node.exe is allowed you get the signature symptom: /m loads but
# sign-in hangs. Port rules are explicit and inspectable.
$isAdmin = ([Security.Principal.WindowsPrincipal] `
            [Security.Principal.WindowsIdentity]::GetCurrent()
           ).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
$fwRules = @(
    @{ Name = "CrimeGPT frontend 3000"; Port = 3000 },
    @{ Name = "CrimeGPT backend 8000";  Port = 8000 }
)
$script:FirewallManual = @()
foreach ($r in $fwRules) {
    $have = Get-NetFirewallRule -DisplayName $r.Name -ErrorAction SilentlyContinue
    if ($have) {
        Write-Ok "Firewall rule already present: $($r.Name)"
    } elseif ($isAdmin) {
        try {
            New-NetFirewallRule -DisplayName $r.Name -Direction Inbound -Protocol TCP `
                -LocalPort $r.Port -Action Allow -Profile Any | Out-Null
            Write-Ok "Created firewall rule: $($r.Name) (TCP $($r.Port) inbound)"
        } catch {
            Write-Warn "Could not create firewall rule $($r.Name): $($_.Exception.Message)"
            $script:FirewallManual += $r
        }
    } else {
        $script:FirewallManual += $r
    }
}
if ($script:FirewallManual.Count -gt 0) {
    Write-Warn "Not elevated - firewall rules NOT created. /m will fail from a phone until you run the commands printed at the end."
}

# ---------------------------------------------------------------------------
# 11. Dependency verification (no servers needed) - reuse scripts\preflight.py
# ---------------------------------------------------------------------------
Write-Step "Dependency verification (scripts\preflight.py, read-only)"
Push-Location $Root
try {
    $prevEa = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    & $VenvPython (Join-Path $Root "scripts\preflight.py") --no-start 2>&1 |
        ForEach-Object { Write-Host "  $_" }
    $pfExit = $LASTEXITCODE
    $ErrorActionPreference = $prevEa
    if ($pfExit -ne 0) {
        Write-Warn "preflight reported at least one FAIL (above). Setup finished, but fix those before the demo."
    } else {
        Write-Ok "preflight: all dependency checks PASS"
    }
} finally {
    Pop-Location
}

# ---------------------------------------------------------------------------
# 8. READY summary (do not auto-start servers)
# ---------------------------------------------------------------------------
Write-Host ""
Write-Host "========================================" -ForegroundColor Green
Write-Host "  CrimeGPT SETUP READY" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Servers are NOT started (avoids orphaned processes). Use two terminals:"
Write-Host ""
Write-Host "  Terminal 1 - backend (CRITICAL: python -m uvicorn, NOT bare uvicorn)" -ForegroundColor White
Write-Host "    cd `"$Backend`""
Write-Host "    `$env:USE_TF = `"0`""
Write-Host "    .\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000"
Write-Host "    # or:  .\start.ps1 -BackendOnly"
Write-Host ""
Write-Host "  Terminal 2 - frontend (pin -p 3000 so Next does not silently fall to 3001)" -ForegroundColor White
Write-Host "    cd `"$Frontend`""
Write-Host "    npm run dev -- -p 3000"
Write-Host "    # or:  .\start.ps1 -FrontendOnly"
Write-Host ""
Write-Host "  Or from the repo root:  .\start.ps1   (opens both in new windows)"
Write-Host ""
Write-Host "URLs"
Write-Host "  Frontend  http://localhost:3000"
Write-Host "  API docs  http://127.0.0.1:8000/docs"
Write-Host "  Health    http://127.0.0.1:8000/health"
Write-Host ""
Write-Host "Demo logins (password = <username>123) + step-up PINs"
Write-Host "  io      / io123      PIN 1234   (Satellite PS - main demo case)"
Write-Host "  io2     / io2123     PIN 5678   (Ellisbridge PS - second case)"
Write-Host "  sho     / sho123     PIN 4321   (all cases + finalize)"
Write-Host "  legal   / legal123   PIN 8765   (read / legal review)"
Write-Host ""
# --- DEMO_MODE: state it, never leave it ambiguous -------------------------
$demoLine = (Select-String -LiteralPath $envFile -Pattern '^\s*DEMO_MODE\s*=\s*(\S+)' |
             Select-Object -First 1)
$demoVal = if ($demoLine) { $demoLine.Matches[0].Groups[1].Value } else { "(unset - defaults to false)" }
Write-Host "DEMO_MODE = $demoVal   (backend\.env)" -ForegroundColor White
if ($demoVal -match '^(?i)true$') {
    Write-Host "  Cached analysis and documents for the seeded case 1 are served instantly."
    Write-Host "  Judgments and weak-charge alerts still call Qwen live. Nothing else is cached."
} else {
    Write-Host "  Everything runs live against Qwen. Honest default for a fresh install -"
    Write-Host "  the demo cache only covers seeded case 1, so a new machine has nothing to serve."
    Write-Host "  Set DEMO_MODE=true in backend\.env for a cached, deterministic demo of case 1."
}
Write-Host ""

# --- Mobile / LAN ----------------------------------------------------------
if ($LanIp) {
    Write-Host "Mobile field page (phone on the same Wi-Fi)"
    Write-Host "  Start with LAN binding:  .\start.ps1 -Lan"
    Write-Host "  Phone URL:               http://${LanIp}:3000/m"
    Write-Host ""
}

if ($script:FirewallManual.Count -gt 0) {
    Write-Host "REQUIRED MANUAL STEP - firewall (run in an ADMIN PowerShell)" -ForegroundColor Yellow
    Write-Host "  Without these, /m loads on the phone but sign-in hangs (port 8000 blocked)." -ForegroundColor Yellow
    foreach ($r in $script:FirewallManual) {
        Write-Host ("  New-NetFirewallRule -DisplayName '{0}' -Direction Inbound -Protocol TCP -LocalPort {1} -Action Allow" -f $r.Name, $r.Port)
    }
    Write-Host "  Keep this LAN-only. Do not expose 8000 beyond the station network." -ForegroundColor Yellow
    Write-Host ""
}

if ($script:OllamaRestartNeeded) {
    Write-Host "REQUIRED MANUAL STEP - restart Ollama" -ForegroundColor Yellow
    Write-Host "  OLLAMA_KEEP_ALIVE=24h was just set but is NOT in effect. Quit Ollama from the" -ForegroundColor Yellow
    Write-Host "  system tray and reopen it, or the model still evicts after 5 idle minutes." -ForegroundColor Yellow
    Write-Host ""
}

Write-Host "REQUIRED MANUAL STEP - phones already signed in" -ForegroundColor Yellow
Write-Host "  A handset holding a PIN token minted before commit 495a34a has no pin_login" -ForegroundColor Yellow
Write-Host "  claim and is refused at Register. Sign out on the phone and sign back in with" -ForegroundColor Yellow
Write-Host "  the PIN once. One tap, per device." -ForegroundColor Yellow
Write-Host ""

Write-Host "NEXT: start the servers, then prove the install" -ForegroundColor Green
Write-Host "  1.  .\start.ps1          (or .\start.ps1 -Lan for phone access)"
Write-Host "  2.  .\verify.ps1         (PASS/FAIL for the whole running stack)"
Write-Host ""
Write-Host "Full notes: SETUP.md"
Write-Host ""
