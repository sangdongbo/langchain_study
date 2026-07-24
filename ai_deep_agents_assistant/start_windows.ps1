param(
    [string]$BindHost = "127.0.0.1",
    [int]$Port = 8020,
    [switch]$NoReload,
    [switch]$SkipSync
)

$ErrorActionPreference = "Stop"

$ProjectRoot = $PSScriptRoot
$RepoRoot = Split-Path -Parent $ProjectRoot

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
    if (-not $Value) {
        return $false
    }
    return @("1", "true", "yes", "on") -contains $Value.ToLowerInvariant()
}

function Assert-PortAvailable {
    param([int]$LocalPort)

    $Listeners = Get-NetTCPConnection -LocalPort $LocalPort -State Listen -ErrorAction SilentlyContinue
    if (-not $Listeners) {
        return
    }

    $Processes = $Listeners | ForEach-Object { "$($_.OwningProcess)" }
    Write-Host "Port $LocalPort is already in use by process id(s): $($Processes -join ', ')." -ForegroundColor Red
    Write-Host "ai_approval_assistant 默认使用 8010；ai_deep_agents_assistant 默认使用 8020。" -ForegroundColor Yellow
    Write-Host "请换一个 -Port，例如: .\start_windows.ps1 -Port 8021" -ForegroundColor Yellow
    exit 1
}

Import-DotEnv (Join-Path $RepoRoot ".env")
Import-DotEnv (Join-Path $ProjectRoot ".env")

Assert-PortAvailable $Port

$RootPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$ProjectPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"

if (Test-Path $RootPython) {
    $Python = $RootPython
} elseif (Test-Path $ProjectPython) {
    $Python = $ProjectPython
} else {
    $Python = "python"
}

if (-not $SkipSync) {
    $Uv = Get-Command uv -ErrorAction SilentlyContinue
    if ($Uv) {
        Push-Location $ProjectRoot
        try {
            Write-Host "Syncing ai_deep_agents_assistant dependencies with uv..." -ForegroundColor Cyan
            uv sync
            $ProjectPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
            if (Test-Path $ProjectPython) {
                $Python = $ProjectPython
            }
        } finally {
            Pop-Location
        }
    } else {
        Write-Host "uv not found; skip dependency sync. Use -SkipSync to hide this message." -ForegroundColor Yellow
    }
}

$ReloadArgs = @()
if (-not $NoReload) {
    $ReloadArgs += "--reload"
}

Set-Location $RepoRoot
Write-Host "Starting AI Deep Agents Approval Assistant on http://${BindHost}:${Port}" -ForegroundColor Green
Write-Host "Using Python: $Python" -ForegroundColor DarkGray

& $Python -m uvicorn ai_deep_agents_assistant.app.main:app --host $BindHost --port $Port @ReloadArgs
