param(
    [string]$TaskName = "ChengWorkspaceN8nWatchdog",
    [int]$IntervalSeconds = 60,
    [int]$StartupWaitSeconds = 90,
    [int]$LogRotateMB = 25
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Script = Join-Path $Root "tools\n8n_watchdog_windows.ps1"
$Pwsh = (Get-Command powershell.exe).Source
$Args = "-NoProfile -ExecutionPolicy Bypass -File `"$Script`" -IntervalSeconds $IntervalSeconds -StartupWaitSeconds $StartupWaitSeconds -LogRotateMB $LogRotateMB"

$Action = New-ScheduledTaskAction -Execute $Pwsh -Argument $Args -WorkingDirectory $Root
$Trigger = New-ScheduledTaskTrigger -AtLogOn
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -RestartCount 10 -RestartInterval (New-TimeSpan -Minutes 1) -MultipleInstances IgnoreNew
try {
    Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Description "Keep n8n running for Cheng workspace" -Force | Out-Null
    Start-ScheduledTask -TaskName $TaskName
    Write-Output "installed_and_started=$TaskName"
} catch {
    $StartupDir = [Environment]::GetFolderPath("Startup")
    $StartupCmd = Join-Path $StartupDir "$TaskName.cmd"
    $cmdText = @(
        "@echo off",
        "cd /d `"$Root`"",
        "`"$Pwsh`" -NoProfile -ExecutionPolicy Bypass -File `"$Script`" -IntervalSeconds $IntervalSeconds -StartupWaitSeconds $StartupWaitSeconds -LogRotateMB $LogRotateMB"
    ) -join [Environment]::NewLine
    [System.IO.File]::WriteAllText($StartupCmd, $cmdText, [System.Text.UTF8Encoding]::new($false))
    Start-Process -FilePath $Pwsh -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", $Script, "-IntervalSeconds", $IntervalSeconds, "-StartupWaitSeconds", $StartupWaitSeconds, "-LogRotateMB", $LogRotateMB) -WorkingDirectory $Root -WindowStyle Hidden
    Write-Output "scheduled_task_denied_startup_fallback=$StartupCmd"
}
