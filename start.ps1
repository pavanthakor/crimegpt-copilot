#Requires -Version 5.1
<#
.SYNOPSIS
  Start CrimeGPT backend and/or frontend after ./setup.ps1.

.DESCRIPTION
  Uses backend\.venv\Scripts\python.exe -m uvicorn (never bare uvicorn).
  Pins the Next.js dev server to port 3000.
#>
[CmdletBinding()]
param(
    [switch]$BackendOnly,
    [switch]$FrontendOnly,
    [switch]$Lan,  # bind 0.0.0.0 for phone / mobile field page
    [switch]$NoNewWindow,
    # Optional convenience: wait for the stack to come up, then run .\verify.ps1.
    # verify.ps1 is standalone - this only saves you typing it in a second terminal.
    [switch]$Verify
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Backend = Join-Path $Root "backend"
$Frontend = Join-Path $Root "frontend"
$VenvPython = Join-Path $Backend ".venv\Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
    Write-Host "backend\.venv missing. Run .\setup.ps1 first." -ForegroundColor Red
    exit 1
}

$hostBind = if ($Lan) { "0.0.0.0" } else { "127.0.0.1" }
$frontHost = if ($Lan) { "0.0.0.0" } else { "127.0.0.1" }

$doBackend = -not $FrontendOnly
$doFrontend = -not $BackendOnly

function Start-Backend {
    $cmd = @"
`$env:USE_TF = '0'
Set-Location '$Backend'
Write-Host 'CrimeGPT backend - python -m uvicorn (venv 3.13+) on ${hostBind}:8000' -ForegroundColor Cyan
& '$VenvPython' -m uvicorn app.main:app --reload --host $hostBind --port 8000
"@
    if ($NoNewWindow) {
        Invoke-Expression $cmd
    } else {
        Start-Process powershell -ArgumentList "-NoExit", "-Command", $cmd
        Write-Host "Backend window started → http://${hostBind}:8000/docs"
    }
}

function Start-Frontend {
    $npmArgs = "run dev -- -H $frontHost -p 3000"
    $cmd = @"
Set-Location '$Frontend'
Write-Host 'CrimeGPT frontend - Next.js on ${frontHost}:3000 (pinned; not 3001)' -ForegroundColor Cyan
npm $npmArgs
"@
    if ($NoNewWindow) {
        Invoke-Expression $cmd
    } else {
        Start-Process powershell -ArgumentList "-NoExit", "-Command", $cmd
        Write-Host "Frontend window started → http://localhost:3000"
    }
}

Write-Host ""
Write-Host "Remember: never use bare 'uvicorn' - it may bind Python 3.11 without docxtpl." -ForegroundColor Yellow
if ($Lan) {
    Write-Host "LAN mode: bind 0.0.0.0 - also create frontend/.env.local and set CORS (SETUP.md)." -ForegroundColor Yellow
}

if ($doBackend) { Start-Backend }
if ($doFrontend) { Start-Frontend }

if (-not $NoNewWindow) {
    Write-Host ""
    Write-Host "Opened separate PowerShell windows. Close them to stop the servers."
}

if ($Verify) {
    $verifyScript = Join-Path $Root "verify.ps1"
    if (-not (Test-Path $verifyScript)) {
        Write-Host "verify.ps1 not found next to start.ps1 - skipping." -ForegroundColor Yellow
    } else {
        # Poll on 127.0.0.1, never localhost (IPv6 ::1 first costs ~2s per new connection).
        Write-Host ""
        Write-Host "Waiting for the backend to answer before verifying ..." -ForegroundColor Cyan
        $up = $false
        for ($i = 0; $i -lt 45; $i++) {
            try {
                Invoke-WebRequest "http://127.0.0.1:8000/health" -TimeoutSec 2 -UseBasicParsing | Out-Null
                $up = $true; break
            } catch { Start-Sleep -Seconds 2 }
        }
        if (-not $up) {
            Write-Host "Backend did not answer within ~90s. Run .\verify.ps1 yourself once it is up." -ForegroundColor Yellow
        } else {
            & $verifyScript
        }
    }
} elseif (-not $NoNewWindow) {
    Write-Host "Prove the install once they are up:  .\verify.ps1" -ForegroundColor Cyan
}
