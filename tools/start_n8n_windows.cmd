@echo off
setlocal

REM CHANNEL_TAG: windows-n8n-cmd
REM Run n8n via cmd.exe to avoid PowerShell execution policy issues.

if "%~1"=="" (
  cmd /c "set N8N_HOST=127.0.0.1&& set N8N_PORT=5678&& set N8N_DIAGNOSTICS_ENABLED=false&& set N8N_VERSION_NOTIFICATIONS_ENABLED=false&& set N8N_TEMPLATES_ENABLED=false&& set N8N_PERSONALIZATION_ENABLED=false&& set N8N_PUBLIC_API_DISABLED=true&& set N8N_HIRING_BANNER_ENABLED=false&& set SKIP_STATISTICS_EVENTS=true&& set EXTERNAL_FRONTEND_HOOKS_URLS=&& n8n start"
) else (
  cmd /c "set N8N_HOST=127.0.0.1&& set N8N_PORT=5678&& set N8N_DIAGNOSTICS_ENABLED=false&& set N8N_VERSION_NOTIFICATIONS_ENABLED=false&& set N8N_TEMPLATES_ENABLED=false&& set N8N_PERSONALIZATION_ENABLED=false&& set N8N_PUBLIC_API_DISABLED=true&& set N8N_HIRING_BANNER_ENABLED=false&& set SKIP_STATISTICS_EVENTS=true&& set EXTERNAL_FRONTEND_HOOKS_URLS=&& n8n %*"
)
