# Event Edge — Start Server
# Activa el entorno conda 'event_edge' si existe, luego arranca el backend.

$envName = "event_edge"
$condaExe = "C:\Users\Junior\Anaconda3\Scripts\conda.exe"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path

if (-not (Test-Path $condaExe)) {
    Write-Error "No se encontro conda.exe en: $condaExe"
    exit 1
}

Write-Host "Iniciando Event Edge API en http://localhost:8100 ..." -ForegroundColor Green
Set-Location $root
& $condaExe run -n $envName python -m uvicorn backend.main:app --reload --port 8100 --host 0.0.0.0
