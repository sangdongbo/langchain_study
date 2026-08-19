param(
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 8021,
    [switch]$NoReload,
    [switch]$SkipSync
)

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot
Set-Location $ProjectRoot

function Import-DotEnv {
    param([string]$Path)
    if (-not (Test-Path $Path)) { return }
    Get-Content -Path $Path | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith("#")) { return }
        $parts = $line.Split("=", 2)
        if ($parts.Count -ne 2) { return }
        $name = $parts[0].Trim()
        $value = $parts[1].Trim().Trim('"').Trim("'")
        if ($name) { [Environment]::SetEnvironmentVariable($name, $value, "Process") }
    }
}

Import-DotEnv (Join-Path $ProjectRoot ".env")
$uv = Get-Command uv -ErrorAction SilentlyContinue
if (-not $uv) { throw "uv is not installed or is not on PATH." }
if (-not $SkipSync) {
    $env:UV_LINK_MODE = "copy"
    uv sync --no-dev
}

$python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { throw "Missing .venv. Run uv sync from ai_erp_rag_assistant." }

$RepositoryRoot = Split-Path $ProjectRoot -Parent
$args = @(
    "-m", "uvicorn", "ai_erp_rag_assistant.app.main:app",
    "--app-dir", $RepositoryRoot,
    "--host", $BindHost,
    "--port", "$Port"
)
if (-not $NoReload) { $args += "--reload" }
Write-Host "Starting AI ERP RAG Assistant at http://${BindHost}:$Port" -ForegroundColor Green
& $python @args
