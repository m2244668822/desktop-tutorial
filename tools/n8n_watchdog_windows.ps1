param(
    [switch]$Once,
    [int]$IntervalSeconds = 60,
    [int]$Port = 5678
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$LogDir = Join-Path $Root "logs"
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
$OutLog = Join-Path $LogDir "n8n_windows.out.log"
$ErrLog = Join-Path $LogDir "n8n_windows.err.log"
$StateLog = Join-Path $LogDir "n8n_watchdog.log"

function Write-State([string]$Message) {
    $line = "{0} {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Add-Content -LiteralPath $StateLog -Value $line -Encoding UTF8
    Write-Output $line
}

function Test-N8nListening {
    try {
        $conn = Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue
        return [bool]$conn
    } catch {
        return $false
    }
}

function Start-N8n {
    $cmd = "set N8N_HOST=127.0.0.1&& set N8N_PORT=$Port&& n8n start 1>>`"$OutLog`" 2>>`"$ErrLog`""
    $proc = Start-Process -FilePath "cmd.exe" -ArgumentList @("/c", $cmd) -WorkingDirectory $Root -WindowStyle Hidden -PassThru
    Write-State "started n8n pid=$($proc.Id)"
}

function Ensure-N8n {
    if (Test-N8nListening) {
        Write-State "n8n already listening on port $Port"
        return
    }
    Write-State "n8n not listening on port $Port; starting"
    Start-N8n
    Start-Sleep -Seconds 8
    if (Test-N8nListening) {
        Write-State "n8n listening after start"
    } else {
        Write-State "n8n start requested but port $Port not listening yet"
    }
}

if ($Once) {
    Ensure-N8n
    exit 0
}

Write-State "watchdog loop started interval=${IntervalSeconds}s port=$Port"
while ($true) {
    Ensure-N8n
    Start-Sleep -Seconds ([Math]::Max(10, $IntervalSeconds))
}


