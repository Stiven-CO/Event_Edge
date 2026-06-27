# Event Edge — Start Server
param(
    [switch]$BackendOnly,
    [switch]$FrontendOnly
)

$ErrorActionPreference = "Stop"

$EnvName = "event_edge"
$CondaExe = "C:\Users\Junior\Anaconda3\Scripts\conda.exe"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path

if (-not (Test-Path $CondaExe)) {
    Write-Error "No se encontro conda.exe en: $CondaExe"
    exit 1
}

function Start-Backend {
    Write-Host "[Event Edge] Iniciando backend en http://localhost:8100 ..." -ForegroundColor Cyan
    Set-Location $Root
    & $CondaExe run -n $EnvName python -m uvicorn backend.main:app --reload --port 8100 --host 0.0.0.0
}

function Start-Frontend {
    Write-Host "[Event Edge] Iniciando frontend (puerto 3000)..." -ForegroundColor Cyan
    Set-Location "$Root\frontend"
    npm run dev -- --host 0.0.0.0 --port 3000
    Set-Location $Root
}

if ($BackendOnly) {
    Start-Backend
} elseif ($FrontendOnly) {
    Start-Frontend
} else {
    Start-Job -ScriptBlock {
        Set-Location $using:Root
        & $using:CondaExe run -n $using:EnvName python -m uvicorn backend.main:app --reload --port 8100 --host 0.0.0.0
    } | Out-Null
    Write-Host "[Event Edge] Backend iniciado en background." -ForegroundColor Green
    Start-Frontend
}
