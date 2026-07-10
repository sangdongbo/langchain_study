param(
    [int]$Port = 8020
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

if (Test-Path ".venv\Scripts\python.exe") {
    $Python = ".venv\Scripts\python.exe"
} else {
    $Python = "python"
}

Set-Location (Split-Path -Parent $Root)
& $Python -m uvicorn ai_deep_agents_assistant.app.main:app --host 127.0.0.1 --port $Port --reload
