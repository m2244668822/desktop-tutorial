param(
    [string]$HostAddress = "127.0.0.1",
    [int]$Port = 5001,
    [switch]$NoEnergyLite
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

$listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
if ($listener) {
    Write-Host "[main-web] already listening on $HostAddress`:$Port pid=$($listener.OwningProcess)"
    try {
        $status = Invoke-WebRequest -Uri "http://$HostAddress`:$Port/status" -UseBasicParsing -TimeoutSec 5
        Write-Host "[main-web] status $($status.StatusCode): $($status.Content)"
    } catch {
        Write-Host "[main-web] listener exists but status check failed: $($_.Exception.Message)"
    }
    exit 0
}

$candidates = @(
    (Join-Path $Root ".venv\Scripts\python.exe"),
    "C:\Users\pc\AppData\Roaming\uv\python\cpython-3.12-windows-x86_64-none\python.exe",
    "python"
)
$Python = $null
foreach ($candidate in $candidates) {
    if ($candidate -eq "python") {
        $cmd = Get-Command python -ErrorAction SilentlyContinue
        if ($cmd) { $Python = $cmd.Source; break }
    } elseif (Test-Path $candidate) {
        $Python = $candidate; break
    }
}
if (-not $Python) {
    throw "No usable Python runtime found for main web startup."
}

$args = @("system_main.py", "web", "--host", $HostAddress, "--port", [string]$Port, "--skip-health")
if (-not $NoEnergyLite) { $args += "--energy-lite" }

Write-Host "[main-web] root=$Root"
Write-Host "[main-web] python=$Python"
Write-Host "[main-web] utf8=$env:PYTHONUTF8 io=$env:PYTHONIOENCODING"
Push-Location $Root
try {
    & $Python @args
    exit $LASTEXITCODE
} finally {
    Pop-Location
}