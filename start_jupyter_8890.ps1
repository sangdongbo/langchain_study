param(
    [int]$Port = 8890
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$RuntimeDir = Join-Path $env:TEMP "learnone-jupyter-runtime-$Port"

if (-not (Test-Path -LiteralPath $Python)) {
    throw "Python interpreter not found: $Python"
}

New-Item -ItemType Directory -Path $RuntimeDir -Force | Out-Null
$env:JUPYTER_RUNTIME_DIR = $RuntimeDir

$PortInUse = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
if ($PortInUse) {
    $Pids = ($PortInUse | Select-Object -ExpandProperty OwningProcess -Unique) -join ", "
    throw "Port $Port is already in use by PID(s): $Pids"
}

Write-Host "Starting Jupyter on http://127.0.0.1:$Port ..." -ForegroundColor Cyan
Write-Host "Project root: $ProjectRoot" -ForegroundColor Cyan
Write-Host "Jupyter runtime dir: $RuntimeDir" -ForegroundColor Cyan
Write-Host "Copy the printed URL with token into your IDE if it asks for a Jupyter server." -ForegroundColor Yellow

& $Python -m jupyter notebook `
    --no-browser `
    --ip 127.0.0.1 `
    --port $Port `
    --notebook-dir $ProjectRoot
