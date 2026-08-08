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

# Optional font hint (non-fatal)
$font = Join-Path $Root "fonts\NotoSansGujarati-Regular.ttf"
if (Test-Path $font) {
    $installed = Test-Path "$env:LOCALAPPDATA\Microsoft\Windows\Fonts\NotoSansGujarati-Regular.ttf"
    if (-not $installed) {
        Write-Warn "Noto Sans Gujarati font is in fonts\ but not installed system-wide - Gujarati in .docx may show as boxes. See SETUP.md."
    } else {
        Write-Ok "Noto Sans Gujarati appears installed"
    }
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
Write-Host "Mobile / LAN field page: see SETUP.md (gitignored .env.local is a MANUAL step)."
Write-Host "Full notes: SETUP.md"
Write-Host ""
