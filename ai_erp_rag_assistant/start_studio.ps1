param(
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 2024,
    [switch]$NoReload,
    [switch]$NoBrowser,
    [switch]$SkipSync
)

$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot
$RepositoryRoot = Split-Path $ProjectRoot -Parent
Set-Location $ProjectRoot

$uv = Get-Command uv -ErrorAction SilentlyContinue
if (-not $uv) { throw "uv is not installed or is not on PATH." }

$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:UV_LINK_MODE = "copy"
$env:PYTHONPATH = if ($env:PYTHONPATH) {
    "$RepositoryRoot$([IO.Path]::PathSeparator)$env:PYTHONPATH"
} else {
    $RepositoryRoot
}
if (-not $SkipSync) {
    uv sync --group dev
}

$langgraph = Join-Path $ProjectRoot ".venv\Scripts\langgraph.exe"
if (-not (Test-Path $langgraph)) {
    throw "Missing LangGraph CLI. Run uv sync --group dev from ai_erp_rag_assistant."
}

# 只检查是否配置，不输出 API Key；Trace 仍由 .env 中的显式开关控制。
$projectEnv = Join-Path $ProjectRoot ".env"
$envLines = @(Get-Content $projectEnv -ErrorAction SilentlyContinue)
$tracingEnabled = (
    $env:LANGSMITH_TRACING -match '^(1|true|yes|on)$' -or
    [bool]($envLines | Where-Object {
        $_ -match '^\s*LANGSMITH_TRACING\s*=\s*(1|true|yes|on)\s*$'
    })
)
$apiKeyConfigured = (
    -not [string]::IsNullOrWhiteSpace($env:LANGSMITH_API_KEY) -or
    [bool]($envLines | Where-Object {
        $_ -match '^\s*LANGSMITH_API_KEY\s*=\s*\S+'
    })
)
if (-not $tracingEnabled -or -not $apiKeyConfigured) {
    Write-Warning "LangSmith Trace is not fully configured; Studio can open, but runs may not appear in the LangSmith project."
}

$args = @(
    "dev",
    "--config", (Join-Path $ProjectRoot "langgraph.json"),
    "--host", $BindHost,
    "--port", "$Port"
)
if ($NoReload) { $args += "--no-reload" }
if ($NoBrowser) { $args += "--no-browser" }

Write-Host "Available graphs: erp_rag_assistant, rag_deepagent, approval_deepagent" -ForegroundColor Cyan
Write-Host "Starting LangGraph Studio API at http://${BindHost}:$Port" -ForegroundColor Green
& $langgraph @args
