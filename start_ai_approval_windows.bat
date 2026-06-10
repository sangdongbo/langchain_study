@echo off
setlocal

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_ai_approval_windows.ps1" %*

endlocal
