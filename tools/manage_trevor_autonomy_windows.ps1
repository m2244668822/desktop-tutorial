param(
    [ValidateSet("start", "stop", "restart", "status", "install", "uninstall")]
    [string]$Action = "status",
    [string]$Workspace = (Split-Path -Parent $PSScriptRoot),
    [string]$DataRoot = $env:TREVOR_DATA_DIR,
    [int]$Heartbeat = 60,
    [int]$Evaluation = 900,
    [int]$NightlyHour = 3
)

$ErrorActionPreference = "Stop"
$TaskName = "Trevor Autonomy"
$RunKey = "HKCU:\Software\Microsoft\Windows\CurrentVersion\Run"
$RunValueName = "TrevorAutonomy"
$Root = (Resolve-Path -LiteralPath $Workspace).Path
if ([string]::IsNullOrWhiteSpace($DataRoot)) {
    $DataRoot = Join-Path $env:LOCALAPPDATA "Trevor"
}
$DataRoot = [System.IO.Path]::GetFullPath($DataRoot)
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Launcher = Join-Path $Root "tools\launch_detached.py"
$Daemon = Join-Path $Root "tools\agent_autonomy_daemon.py"
$RunRoot = Join-Path $DataRoot "run"
$LogRoot = Join-Path $DataRoot "logs"
$PidFile = Join-Path $RunRoot "autonomy-windows.pid"
$StdoutFile = Join-Path $LogRoot "autonomy.log"
$StderrFile = Join-Path $LogRoot "autonomy.error.log"

function Get-TrevorProcess {
    if (-not (Test-Path -LiteralPath $PidFile)) { return $null }
    $stored = (Get-Content -LiteralPath $PidFile -Raw).Trim()
    if ($stored -notmatch '^\d+$') { return $null }
    $candidate = Get-CimInstance Win32_Process -Filter "ProcessId = $stored" -ErrorAction SilentlyContinue
    if ($null -eq $candidate) { return $null }
    if ($candidate.CommandLine -notlike "*agent_autonomy_daemon.py*") { return $null }
    return $candidate
}

function Show-Status {
    $process = Get-TrevorProcess
    if ($null -eq $process) {
        Write-Host "[info] Trevor autonomy is stopped"
        return $false
    }
    Write-Host "[ok] Trevor autonomy is running pid=$($process.ProcessId)"
    return $true
}

function Start-TrevorAutonomy {
    if (Show-Status) { return }
    if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) {
        throw "Python runtime missing: $Python"
    }
    New-Item -ItemType Directory -Path $RunRoot, $LogRoot -Force | Out-Null
    $arguments = @(
        $Launcher,
        "--cwd", $Root,
        "--pidfile", $PidFile,
        "--stdout", $StdoutFile,
        "--stderr", $StderrFile,
        "--unset-env", "TREVOR_MEMORY_KEY_B64",
        "--env", "TREVOR_DATA_DIR=$DataRoot",
        "--env", "TREVOR_MEMORY_ENCRYPTION=required",
        "--env", "PYTHONUNBUFFERED=1",
        "--", $Python, "-u", $Daemon,
        "--heartbeat", [string]$Heartbeat,
        "--evaluation", [string]$Evaluation,
        "--nightly-hour", [string]$NightlyHour
    )
    $launcherProcess = Start-Process -FilePath $Python -ArgumentList $arguments -WindowStyle Hidden -PassThru
    if (-not $launcherProcess.WaitForExit(10000)) {
        throw "Autonomy launcher did not exit within 10 seconds"
    }
    if ($launcherProcess.ExitCode -ne 0) {
        throw "Autonomy launcher failed with exit code $($launcherProcess.ExitCode)"
    }
    Start-Sleep -Milliseconds 750
    if (-not (Show-Status)) {
        throw "Autonomy daemon exited during startup; inspect $StderrFile"
    }
}

function Stop-TrevorAutonomy {
    $process = Get-TrevorProcess
    if ($null -eq $process) {
        Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
        Write-Host "[info] Trevor autonomy is already stopped"
        return
    }
    Stop-Process -Id $process.ProcessId -ErrorAction Stop
    for ($attempt = 0; $attempt -lt 20; $attempt++) {
        if ($null -eq (Get-Process -Id $process.ProcessId -ErrorAction SilentlyContinue)) { break }
        Start-Sleep -Milliseconds 100
    }
    Remove-Item -LiteralPath $PidFile -Force -ErrorAction SilentlyContinue
    Write-Host "[ok] Trevor autonomy stopped"
}

function Install-TrevorTask {
    $manager = $MyInvocation.MyCommand.Path
    $taskArguments = "-NoProfile -ExecutionPolicy Bypass -File `"$manager`" -Action start -Workspace `"$Root`" -DataRoot `"$DataRoot`""
    $taskAction = New-ScheduledTaskAction -Execute "powershell.exe" -Argument $taskArguments
    $trigger = New-ScheduledTaskTrigger -AtLogOn
    $settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
    $user = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    $principal = New-ScheduledTaskPrincipal -UserId $user -LogonType Interactive -RunLevel Limited
    try {
        Register-ScheduledTask -TaskName $TaskName -Action $taskAction -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
        Remove-ItemProperty -Path $RunKey -Name $RunValueName -ErrorAction SilentlyContinue
        Write-Host "[ok] Scheduled task installed: $TaskName"
    } catch {
        # Some managed Windows editions deny Task Scheduler registration even
        # for the current user.  HKCU Run is a user-scoped, reversible fallback.
        New-Item -Path $RunKey -Force | Out-Null
        $runCommand = "powershell.exe $taskArguments"
        Set-ItemProperty -Path $RunKey -Name $RunValueName -Value $runCommand
        Write-Host "[warn] Scheduled Task unavailable; installed current-user logon fallback"
    }
}

switch ($Action) {
    "start" { Start-TrevorAutonomy }
    "stop" { Stop-TrevorAutonomy }
    "restart" { Stop-TrevorAutonomy; Start-TrevorAutonomy }
    "status" { if (-not (Show-Status)) { exit 1 } }
    "install" { Install-TrevorTask; Start-TrevorAutonomy }
    "uninstall" {
        Stop-TrevorAutonomy
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
        Remove-ItemProperty -Path $RunKey -Name $RunValueName -ErrorAction SilentlyContinue
        Write-Host "[ok] Trevor logon startup removed"
    }
}
