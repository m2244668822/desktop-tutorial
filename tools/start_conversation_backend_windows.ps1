param(
    [string]$VaultRoot = "",
    [switch]$Once,
    [switch]$Diagnose,
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
$RuntimeRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

if (-not $VaultRoot) {
    $candidate = (Resolve-Path (Join-Path $RuntimeRoot "..\..") -ErrorAction SilentlyContinue)
    if ($candidate -and (Test-Path (Join-Path $candidate.Path "智能體"))) {
        $VaultRoot = $candidate.Path
    } else {
        $VaultRoot = $RuntimeRoot
    }
}
$VaultRoot = (Resolve-Path $VaultRoot).Path
$env:VAULT_WORKSPACE_ROOT = $VaultRoot
$env:WHITE_STUDIO_LOCAL_POLL_MS = $env:WHITE_STUDIO_LOCAL_POLL_MS ?? "3000"

$ServiceRoot = Join-Path $RuntimeRoot "services\inbox_executor"
$Node = Get-Command node -ErrorAction SilentlyContinue
if (-not $Node) {
    throw "BLOCKED node_unavailable: install/restore Node.js before starting the conversation backend."
}

Write-Host "[conversation-backend] runtime=$RuntimeRoot"
Write-Host "[conversation-backend] vault=$VaultRoot"
Write-Host "[conversation-backend] node=$($Node.Source)"

Push-Location $ServiceRoot
try {
    if (-not $SkipTests) {
        & $Node.Source ".\src\conversation_event_e2e.js"
        if ($LASTEXITCODE -ne 0) { throw "BLOCKED conversation_event_e2e_failed" }

        & $Node.Source ".\src\conversation_enqueue_e2e.js"
        if ($LASTEXITCODE -ne 0) { throw "BLOCKED conversation_enqueue_e2e_failed" }

        & $Node.Source ".\src\queue_e2e.js"
        if ($LASTEXITCODE -ne 0) { throw "BLOCKED queue_e2e_failed" }
    }

    & $Node.Source ".\src\local_runtime_probe.js"
    if ($LASTEXITCODE -ne 0) { throw "BLOCKED local_runtime_probe_failed" }

    if ($Diagnose) {
        Write-Host "[conversation-backend] diagnose complete; runner not started."
        exit 0
    }

    $args = @(".\src\local_queue_runner.js")
    if ($Once) { $args += "--once" }

    Write-Host "[conversation-backend] local queue runner starting."
    & $Node.Source @args
    exit $LASTEXITCODE
} finally {
    Pop-Location
}
