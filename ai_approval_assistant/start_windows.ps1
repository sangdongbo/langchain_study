param(
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 8010,
    [switch]$NoReload,
    [switch]$SkipSync,
    [switch]$NoStudio
)

$ErrorActionPreference = "Stop"

$ProjectRoot = $PSScriptRoot
Set-Location $ProjectRoot

function Import-DotEnv {
    param([string]$Path)

    if (-not (Test-Path $Path)) {
        return
    }

    Get-Content -Path $Path | ForEach-Object {
        $Line = $_.Trim()
        if (-not $Line -or $Line.StartsWith("#")) {
            return
        }
        $Parts = $Line.Split("=", 2)
        if ($Parts.Count -ne 2) {
            return
        }
        $Name = $Parts[0].Trim()
        $Value = $Parts[1].Trim().Trim('"').Trim("'")
        if ($Name) {
            [Environment]::SetEnvironmentVariable($Name, $Value, "Process")
        }
    }
}

function Test-Truthy {
    param([string]$Value)

    return @("1", "true", "yes", "on") -contains $Value.ToLowerInvariant()
}

function Stop-PortListeners {
    param([int]$LocalPort)

    $Listeners = Get-NetTCPConnection -LocalPort $LocalPort -State Listen -ErrorAction SilentlyContinue
    foreach ($Listener in $Listeners) {
        $ProcessId = $Listener.OwningProcess
        if (-not $ProcessId) {
            continue
        }
        try {
            $Process = Get-Process -Id $ProcessId -ErrorAction Stop
            Write-Host "Stopping existing process on port ${LocalPort}: $($Process.ProcessName) ($ProcessId)" -ForegroundColor Yellow
            Stop-Process -Id $ProcessId -Force
        } catch {
            Write-Host "Could not stop process $ProcessId on port ${LocalPort}: $($_.Exception.Message)" -ForegroundColor Red
            throw
        }
    }
}

function Assert-PortAvailable {
    param([int]$LocalPort)

    $Listeners = Get-NetTCPConnection -LocalPort $LocalPort -State Listen -ErrorAction SilentlyContinue
    if ($Listeners) {
        $Processes = $Listeners | ForEach-Object {
            "$($_.OwningProcess)"
        }
        Write-Host "Port $LocalPort is already in use by process id(s): $($Processes -join ', ')." -ForegroundColor Red
        Write-Host "Set AI_APPROVAL_KILL_EXISTING_PORT_PROCESS=true in .env, or start with another -Port." -ForegroundColor Yellow
        exit 1
    }
}

Import-DotEnv (Join-Path $ProjectRoot ".env")

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
    uv sync --dev
}

$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$LangGraph = Join-Path $ProjectRoot ".venv\Scripts\langgraph.exe"
if (-not (Test-Path $Python)) {
    Write-Host "Virtual environment was not created at .venv\Scripts\python.exe." -ForegroundColor Red
    Write-Host "Run 'uv sync' from ai_approval_assistant and try again."
    exit 1
}

if ((Test-Truthy $env:AI_APPROVAL_STUDIO_ENABLED) -and (-not $NoStudio)) {
    if (-not (Test-Path $LangGraph)) {
        Write-Host "LangGraph CLI was not found at .venv\Scripts\langgraph.exe." -ForegroundColor Red
        Write-Host "Run 'uv sync --dev' from ai_approval_assistant and try again."
        exit 1
    }
    $StudioHost = if ($env:AI_APPROVAL_STUDIO_HOST) { $env:AI_APPROVAL_STUDIO_HOST } else { "127.0.0.1" }
    $StudioPort = if ($env:AI_APPROVAL_STUDIO_PORT) { [int]$env:AI_APPROVAL_STUDIO_PORT } else { 2024 }
    $LogDir = Join-Path $ProjectRoot "logs"
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
    $env:PYTHONIOENCODING = "utf-8"
    $env:PYTHONUTF8 = "1"
    if (Test-Truthy $env:AI_APPROVAL_KILL_EXISTING_PORT_PROCESS) {
        Stop-PortListeners -LocalPort $StudioPort
    }
    $StudioArgs = @("dev", "--host", $StudioHost, "--port", "$StudioPort", "--no-browser")
    Write-Host "Starting LangGraph Studio server at http://${StudioHost}:$StudioPort" -ForegroundColor Green
    Write-Host "LangGraph Studio logs: $LogDir\studio.out.log and $LogDir\studio.err.log" -ForegroundColor Cyan
    Start-Process `
        -FilePath $LangGraph `
        -ArgumentList $StudioArgs `
        -WorkingDirectory $ProjectRoot `
        -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $LogDir "studio.out.log") `
        -RedirectStandardError (Join-Path $LogDir "studio.err.log")
}

if (Test-Truthy $env:AI_APPROVAL_KILL_EXISTING_PORT_PROCESS) {
    Stop-PortListeners -LocalPort $Port
} else {
    Assert-PortAvailable -LocalPort $Port
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
