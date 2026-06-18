param(
    [int]$Port = 8010,
    [switch]$NoStudio,
    [switch]$DryRun
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

    if (-not $Value) {
        return $false
    }
    return @("1", "true", "yes", "on") -contains $Value.ToLowerInvariant()
}

function Get-ProcessTreeIds {
    param([int]$RootProcessId)

    $Ids = New-Object System.Collections.Generic.HashSet[int]
    $Queue = New-Object System.Collections.Generic.Queue[int]
    $Queue.Enqueue($RootProcessId)

    while ($Queue.Count -gt 0) {
        $CurrentId = $Queue.Dequeue()
        if (-not $Ids.Add($CurrentId)) {
            continue
        }
        Get-CimInstance Win32_Process |
            Where-Object { $_.ParentProcessId -eq $CurrentId } |
            ForEach-Object { $Queue.Enqueue([int]$_.ProcessId) }
    }

    return $Ids
}

function Stop-PortListeners {
    param(
        [int]$LocalPort,
        [string]$Label
    )

    $Listeners = Get-NetTCPConnection -LocalPort $LocalPort -State Listen -ErrorAction SilentlyContinue
    if (-not $Listeners) {
        Write-Host "$Label is not listening on port $LocalPort." -ForegroundColor DarkGray
        return
    }

    $ProcessIds = $Listeners | Select-Object -ExpandProperty OwningProcess -Unique
    foreach ($ProcessId in $ProcessIds) {
        if (-not $ProcessId) {
            continue
        }

        $TreeIds = Get-ProcessTreeIds -RootProcessId ([int]$ProcessId)
        $Processes = $TreeIds |
            ForEach-Object { Get-Process -Id $_ -ErrorAction SilentlyContinue } |
            Sort-Object Id -Unique

        foreach ($Process in $Processes) {
            $Message = "Stopping $Label on port ${LocalPort}: $($Process.ProcessName) ($($Process.Id))"
            if ($DryRun) {
                Write-Host "[DryRun] $Message" -ForegroundColor Cyan
                continue
            }
            Write-Host $Message -ForegroundColor Yellow
            Stop-Process -Id $Process.Id -Force -ErrorAction Stop
        }
    }
}

Import-DotEnv (Join-Path $ProjectRoot ".env")

$StudioEnabled = (Test-Truthy $env:AI_APPROVAL_STUDIO_ENABLED) -and (-not $NoStudio)
$StudioPort = if ($env:AI_APPROVAL_STUDIO_PORT) { [int]$env:AI_APPROVAL_STUDIO_PORT } else { 2024 }

if ($StudioEnabled) {
    Stop-PortListeners -LocalPort $StudioPort -Label "LangGraph Studio"
}

Stop-PortListeners -LocalPort $Port -Label "AI Approval Assistant"

if ($DryRun) {
    Write-Host "Dry run finished. No processes were stopped." -ForegroundColor Green
} else {
    Write-Host "Stop command finished." -ForegroundColor Green
}
