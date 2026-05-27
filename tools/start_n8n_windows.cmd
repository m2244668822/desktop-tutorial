@echo off
setlocal

REM CHANNEL_TAG: windows-n8n-cmd
REM Run n8n via cmd.exe to avoid PowerShell execution policy issues.

if "%~1"=="" (
  cmd /c "set N8N_HOST=127.0.0.1&& set N8N_PORT=5678&& n8n start"
) else (
  cmd /c "set N8N_HOST=127.0.0.1&& set N8N_PORT=5678&& n8n %*"
)
