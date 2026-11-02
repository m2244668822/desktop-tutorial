param(
    [string]$WorkflowPath = "automation/n8n/trevor-training-evaluation.json",
    [int]$ImportTimeoutSeconds = 30,
    [int]$N8nPort = 5678
)

$ErrorActionPreference = "Stop"
$env:N8N_USER_MANAGEMENT_DISABLED = "true"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$Workflow = (Resolve-Path (Join-Path $Root $WorkflowPath)).Path
$PythonCandidates = @(
    $env:TREVOR_PYTHON,
    (Join-Path $Root ".venv\Scripts\python.exe"),
    (Join-Path (Split-Path $Root -Parent) "城城城程式-Trevor\.venv\Scripts\python.exe")
) | Where-Object { $_ -and (Test-Path -LiteralPath $_) }
$Python = $PythonCandidates | Select-Object -First 1
if (-not $Python) {
    $pythonCommand = Get-Command python -ErrorAction SilentlyContinue
    if ($pythonCommand) { $Python = $pythonCommand.Source }
}
$Validator = Join-Path $Root "tools\validate_n8n_training_workflow.py"
$Starter = Join-Path $Root "tools\start_n8n_windows.ps1"

if (-not (Test-Path -LiteralPath $Workflow)) { throw "workflow_not_found=$Workflow" }
if (-not (Test-Path -LiteralPath $Python)) { throw "python_not_found=$Python" }

& $Python $Validator --workflow $Workflow
if ($LASTEXITCODE -ne 0) { throw "workflow_validator_failed" }

$health = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$N8nPort/healthz" -TimeoutSec 8
if ([int]$health.StatusCode -ne 200) { throw "n8n_healthz_not_ready=$($health.StatusCode)" }

$powershell = (Get-Process -Id $PID).Path
$arguments = @(
    "-NoProfile",
    "-ExecutionPolicy", "Bypass",
    "-File", $Starter,
    "import:workflow",
    "--input=$Workflow"
)
$importProcess = Start-Process -FilePath $powershell -ArgumentList $arguments -WorkingDirectory $Root -PassThru -WindowStyle Hidden
if (-not $importProcess.WaitForExit([Math]::Max(5, $ImportTimeoutSeconds) * 1000)) {
    try { taskkill.exe /PID $importProcess.Id /T /F | Out-Null } catch { }
    throw "n8n_import_timeout_seconds=$ImportTimeoutSeconds"
}
if ($importProcess.ExitCode -ne 0) { throw "n8n_import_failed_exit=$($importProcess.ExitCode)" }

Write-Output (ConvertTo-Json @{ ok = $true; workflow = $Workflow; healthz = $health.StatusCode; import_exit = $importProcess.ExitCode } -Compress)
