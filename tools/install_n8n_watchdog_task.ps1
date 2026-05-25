param(
    [string]$TaskName = "ChengWorkspaceN8nWatchdog",
    [int]$IntervalSeconds = 60
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Script = Join-Path $Root "tools\n8n_watchdog_windows.ps1"
$Pwsh = (Get-Command powershell.exe).Source
$Args = "-NoProfile -ExecutionPolicy Bypass -File `"$Script`" -IntervalSeconds $IntervalSeconds"

$Action = New-ScheduledTaskAction -Execute $Pwsh -Argument $Args -WorkingDirectory $Root
$Trigger = New-ScheduledTaskTrigger -AtLogOn
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Description "Keep n8n running for Cheng workspace" -Force | Out-Null
Start-ScheduledTask -TaskName $TaskName
Write-Output "installed_and_started=$TaskName"
