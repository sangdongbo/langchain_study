param(
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 8010,
    [switch]$NoReload,
    [switch]$SkipSync
)

$ErrorActionPreference = "Stop"

$ProjectRoot = $PSScriptRoot
Set-Location $ProjectRoot

$Uv = Get-Command uv -ErrorAction SilentlyContinue
if (-not $Uv) {
    Write-Host "uv is not installed or is not on PATH." -ForegroundColor Red
    Write-Host "Install it in PowerShell with:" -ForegroundColor Yellow
    Write-Host "  irm https://astral.sh/uv/install.ps1 | iex"
    exit 1
}

$env:UV_LINK_MODE = "copy"
if (-not $env:AI_APPROVAL_CRM_BASE_URL) {
    $env:AI_APPROVAL_CRM_BASE_URL = "http://localhost:8002"
}

if (-not $SkipSync) {
    Write-Host "Syncing AI Approval Assistant dependencies with uv..." -ForegroundColor Cyan
    uv sync
}

$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    Write-Host "Virtual environment was not created at .venv\Scripts\python.exe." -ForegroundColor Red
    Write-Host "Run 'uv sync' from ai_approval_assistant and try again."
    exit 1
}

$UvicornArgs = @(
    "-m", "uvicorn",
    "app.main:app",
    "--host", $BindHost,
    "--port", $Port
)

if (-not $NoReload) {
    $UvicornArgs += "--reload"
}

Write-Host "Starting AI Approval Assistant at http://${BindHost}:$Port" -ForegroundColor Green
& $Python @UvicornArgs
