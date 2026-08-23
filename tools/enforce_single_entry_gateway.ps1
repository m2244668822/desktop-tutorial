param(
    [string]$HostAddress = "127.0.0.1",
    [int]$WebPort = 5001,
    [int]$N8nPort = 5678,
    [int]$WatchdogIntervalSeconds = 60
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$StartWebScript = Join-Path $Root "tools\start_main_web_windows.ps1"
$N8nWatchdogScript = Join-Path $Root "tools\n8n_watchdog_windows.ps1"

function Get-Listener([int]$Port) {
    try {
        return Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue | Select-Object -First 1
    } catch {
        return $null
    }
}

function Get-ProcessCommandLine([int]$ProcessId) {
    try {
        $proc = Get-CimInstance Win32_Process -Filter "ProcessId=$ProcessId"
        return [string]$proc.CommandLine
    } catch {
        return ""
    }
}

function Ensure-MainWeb {
    $listener = Get-Listener -Port $WebPort
    if ($listener) {
        $cmd = Get-ProcessCommandLine -ProcessId $listener.OwningProcess
        $isExpected = $cmd -match "desktop_chat_app.py|system_main.py"
        if (-not $isExpected) {
            Write-Warning "[gateway] port $WebPort is occupied by unexpected process pid=$($listener.OwningProcess)"
            Write-Warning "[gateway] command line: $cmd"
            return
        }
        Write-Output "[gateway] main web already listening on $HostAddress`:$WebPort pid=$($listener.OwningProcess)"
        return
    }

    if (-not (Test-Path $StartWebScript)) {
        throw "start_main_web_windows.ps1 not found: $StartWebScript"
    }
    Write-Output "[gateway] main web is down, starting single-entry service on $HostAddress`:$WebPort"
    Start-Process powershell -ArgumentList @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", "`"$StartWebScript`"",
        "-HostAddress", $HostAddress,
        "-Port", [string]$WebPort
    ) -WorkingDirectory $Root -WindowStyle Hidden | Out-Null
}

function Ensure-N8nWatchdog {
    $listener = Get-Listener -Port $N8nPort
    if ($listener) {
        Write-Output "[n8n] already listening on $N8nPort pid=$($listener.OwningProcess)"
        return
    }
    if (-not (Test-Path $N8nWatchdogScript)) {
        throw "n8n_watchdog_windows.ps1 not found: $N8nWatchdogScript"
    }
    Write-Output "[n8n] service is down, starting watchdog loop on port $N8nPort"
    Start-Process powershell -ArgumentList @(
        "-NoProfile",
        "-ExecutionPolicy", "Bypass",
        "-File", "`"$N8nWatchdogScript`"",
        "-IntervalSeconds", [string]$WatchdogIntervalSeconds,
        "-Port", [string]$N8nPort
    ) -WorkingDirectory $Root -WindowStyle Hidden | Out-Null
}

function Check-GatewayPolicy {
    try {
        $url = "http://$HostAddress`:$WebPort/api/gateway/policy"
        $resp = Invoke-WebRequest -UseBasicParsing -Uri $url -TimeoutSec 4
        Write-Output "[gateway] policy endpoint $($resp.StatusCode): $($resp.Content)"
    } catch {
        Write-Warning "[gateway] policy endpoint check failed: $($_.Exception.Message)"
    }
}

Write-Output "[bootstrap] enforcing single-entry gateway mode"
Ensure-MainWeb
Start-Sleep -Seconds 2
Check-GatewayPolicy
Ensure-N8nWatchdog

$web = Get-Listener -Port $WebPort
$n8n = Get-Listener -Port $N8nPort
Write-Output "[summary] web_port=$WebPort listening=$([bool]$web) n8n_port=$N8nPort listening=$([bool]$n8n)"
