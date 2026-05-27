param(
    [Parameter(Mandatory = $true)]
    [string]$SourceDir,
    [Parameter(Mandatory = $true)]
    [string]$DestDir,
    [switch]$MirrorDelete
)

$ErrorActionPreference = "Stop"

# CHANNEL_TAG: windows-sync
# PLATFORM: Windows (PowerShell + robocopy)
# COMPANION_MAC_CHANNEL: tools/sync_ssd_to_hdd.sh

$Source = (Resolve-Path -LiteralPath $SourceDir).Path
if (-not (Test-Path -LiteralPath $DestDir)) {
    New-Item -ItemType Directory -Path $DestDir | Out-Null
}
$Dest = (Resolve-Path -LiteralPath $DestDir).Path

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$reportDir = Join-Path $Source "reports"
New-Item -ItemType Directory -Path $reportDir -Force | Out-Null
$logFile = Join-Path $reportDir "storage_sync_windows_$stamp.log"
$caseJson = Join-Path $reportDir "case_collision_report_windows_$stamp.json"

function Log([string]$msg) {
    $msg | Tee-Object -FilePath $logFile -Append
}

$py = if (Test-Path ".venv\\Scripts\\python.exe") { ".venv\\Scripts\\python.exe" } else { "python" }

Log "== SSD -> HDD Sync (Windows channel) =="
Log "SOURCE: $Source"
Log "DEST  : $Dest"
Log ""

Log "[1/4] Scan case-insensitive collisions..."
try {
    & $py "tools/check_case_collisions.py" $Source --json-out $caseJson | Tee-Object -FilePath $logFile -Append
    Log "Case scan: finished"
} catch {
    Log "Case scan: skipped/failed ($($_.Exception.Message))"
}

$modeArg = if ($MirrorDelete) { "/MIR" } else { "/E" }
Log ""
Log "[2/4] Sync files with robocopy ($modeArg)..."
$robocopyArgs = @(
    $Source,
    $Dest,
    "*",
    $modeArg,
    "/COPY:DAT",
    "/DCOPY:DAT",
    "/R:2",
    "/W:1",
    "/FFT",
    "/XJ",
    "/XD", ".git", ".venv", ".venv312", "node_modules", "archive"
)
& robocopy @robocopyArgs | Tee-Object -FilePath $logFile -Append
$rc = $LASTEXITCODE
Log "robocopy_exit=$rc"
if ($rc -gt 7) {
    throw "Robocopy failed with exit code $rc"
}

Log ""
Log "[3/4] Dry-run verify..."
$dryArgs = @(
    $Source,
    $Dest,
    "*",
    "/L",
    $modeArg,
    "/COPY:DAT",
    "/DCOPY:DAT",
    "/R:0",
    "/W:0",
    "/FFT",
    "/XJ",
    "/XD", ".git", ".venv", ".venv312", "node_modules", "archive"
)
& robocopy @dryArgs | Tee-Object -FilePath $logFile -Append
$dryRc = $LASTEXITCODE
Log "dry_run_exit=$dryRc"

Log ""
Log "[4/4] Complete"
Log "Log  : $logFile"
Log "Case : $caseJson"
