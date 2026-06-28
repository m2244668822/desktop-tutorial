param(
    [switch]$Once,
    [int]$IntervalSeconds = 60,
    [int]$Port = 5678,
    [int]$StartupWaitSeconds = 180,
    [int]$LogRotateMB = 25
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$LogDir = Join-Path $Root "logs"
$RotatedLogDir = Join-Path $LogDir "rotated"
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
New-Item -ItemType Directory -Path $RotatedLogDir -Force | Out-Null

$OutLog = Join-Path $LogDir "n8n_windows.out.log"
$ErrLog = Join-Path $LogDir "n8n_windows.err.log"
$StateLog = Join-Path $LogDir "n8n_watchdog.log"

function Write-State([string]$Message) {
    $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Add-Content -LiteralPath $StateLog -Value $line -Encoding UTF8
    Write-Output $line
}

function Rotate-LogIfLarge([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) {
        return
    }
    $item = Get-Item -LiteralPath $Path -ErrorAction SilentlyContinue
    if (-not $item -or $item.Length -lt ($LogRotateMB * 1MB)) {
        return
    }
    $stamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $target = Join-Path $RotatedLogDir ("{0}.{1}.log" -f $item.BaseName, $stamp)
    Move-Item -LiteralPath $Path -Destination $target -Force
    New-Item -ItemType File -Path $Path -Force | Out-Null
    Write-State "rotated log=$($item.Name) sizeMB=$([math]::Round($item.Length / 1MB, 2)) to=$target"
}

function Get-N8nProcesses {
    Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object {
            $cmd = [string]$_.CommandLine
            $cmd -match "node_modules\\n8n\\bin\\n8n|n8n start" -and
            $cmd -notmatch "n8n_watchdog_windows\.ps1"
        }
}

function Test-N8nListening {
    try {
        $conn = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
        return [bool]$conn
    } catch {
        return $false
    }
}

function Wait-N8nListening([int]$Seconds) {
    $deadline = (Get-Date).AddSeconds([Math]::Max(5, $Seconds))
    while ((Get-Date) -lt $deadline) {
        if (Test-N8nListening) {
            return $true
        }
        Start-Sleep -Seconds 3
    }
    return (Test-N8nListening)
}

function Start-N8n {
    Rotate-LogIfLarge $OutLog
    Rotate-LogIfLarge $ErrLog

    $cmdParts = @(
        "set N8N_HOST=127.0.0.1",
        "set N8N_PORT=$Port",
        "set N8N_DIAGNOSTICS_ENABLED=false",
        "set N8N_VERSION_NOTIFICATIONS_ENABLED=false",
        "set N8N_TEMPLATES_ENABLED=false",
        "set N8N_PERSONALIZATION_ENABLED=false",
        "set N8N_PUBLIC_API_DISABLED=true",
        "set N8N_HIRING_BANNER_ENABLED=false",
        "set SKIP_STATISTICS_EVENTS=true",
        "set EXTERNAL_FRONTEND_HOOKS_URLS=",
        "n8n start 1>>`"$OutLog`" 2>>`"$ErrLog`""
    )
    $cmd = $cmdParts -join "&& "
    $proc = Start-Process -FilePath "cmd.exe" -ArgumentList @("/c", $cmd) -WorkingDirectory $Root -WindowStyle Hidden -PassThru
    Write-State "started n8n cmd_pid=$($proc.Id) startup_wait=${StartupWaitSeconds}s telemetry=disabled"
}

function Ensure-N8n {
    if (Test-N8nListening) {
        Write-State "n8n already listening on port $Port"
        return
    }

    $existing = @(Get-N8nProcesses)
    if ($existing.Count -gt 0) {
        $ids = ($existing | Select-Object -ExpandProperty ProcessId) -join ","
        Write-State "n8n process exists but port $Port is not listening yet; waiting pids=$ids"
        if (Wait-N8nListening $StartupWaitSeconds) {
            Write-State "n8n listening after wait"
            return
        }
        Write-State "existing n8n process did not expose port $Port within ${StartupWaitSeconds}s"
    }

    Write-State "n8n not listening on port $Port; starting"
    Start-N8n
    if (Wait-N8nListening $StartupWaitSeconds) {
        Write-State "n8n listening after start"
    } else {
        Write-State "n8n start requested but port $Port still not listening after ${StartupWaitSeconds}s"
    }
}

if ($Once) {
    Ensure-N8n
    exit 0
}

Write-State "watchdog loop started interval=${IntervalSeconds}s port=$Port startup_wait=${StartupWaitSeconds}s"
while ($true) {
    Ensure-N8n
    Start-Sleep -Seconds ([Math]::Max(10, $IntervalSeconds))
}
