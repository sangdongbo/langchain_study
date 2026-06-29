@echo off
setlocal

rem Keep this wrapper in cmd so Windows users can double-click it or pass args.
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_windows.ps1" %*

if errorlevel 1 (
    echo.
    echo AI Approval Assistant failed to start. See the error above.
    pause
)
