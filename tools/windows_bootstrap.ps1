param(
    [string]$Workspace = ".",
    [string]$Python = "py -3.12",
    [switch]$InstallEditorExtensions,
    [switch]$RunHarmonyCheck
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path $Workspace
Set-Location $Root

Write-Host "== Windows Bootstrap =="
Write-Host "Workspace: $Root"

if (-not (Test-Path ".venv")) {
    Write-Host "[1/5] Creating .venv"
    Invoke-Expression "$Python -m venv .venv"
} else {
    Write-Host "[1/5] .venv already exists"
}

Write-Host "[2/5] Installing Python packages"
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

if (Test-Path "data") {
    $dataItem = Get-Item "data" -Force
    if (-not $dataItem.PSIsContainer -and -not $dataItem.Attributes.ToString().Contains("ReparsePoint")) {
        $backup = "data.file-backup.$((Get-Date).ToString('yyyyMMdd_HHmmss')).txt"
        Write-Host "[3/5] data is a plain file, moving to $backup"
        Move-Item -LiteralPath "data" -Destination $backup -Force
    } else {
        Write-Host "[3/5] data path already exists"
    }
}

if (-not (Test-Path "data_hdd_storage")) {
    Write-Host "[3/5] Creating data_hdd_storage"
    New-Item -ItemType Directory -Path "data_hdd_storage" | Out-Null
}

if (-not (Test-Path "data")) {
    Write-Host "[3/5] Creating data junction -> data_hdd_storage"
    cmd /c mklink /J data data_hdd_storage | Out-Host
    if (-not (Test-Path "data")) {
        Write-Host "[3/5] Junction creation failed (non-NTFS or permission). Runtime will use data_hdd_storage fallback."
    }
}

Write-Host "[4/5] Running health check"
.\.venv\Scripts\python.exe system_main.py health

$nodeCandidates = @()
try {
    $nodeCandidates = @(where.exe node 2>$null)
} catch {
    $nodeCandidates = @()
}
if ($nodeCandidates.Count -gt 1) {
    Write-Host "[4/5] Node multiple candidates detected (possible shadow):"
    $nodeCandidates | ForEach-Object { Write-Host "  - $_" }
}

$wingetNodeDir = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages\OpenJS.NodeJS.LTS_Microsoft.Winget.Source_8wekyb3d8bbwe"
$preferredN8n = Get-ChildItem -Path $wingetNodeDir -Filter "n8n.cmd" -Recurse -ErrorAction SilentlyContinue | Select-Object -First 1
if ($preferredN8n) {
    Write-Host "[4/5] Preferred n8n path:"
    Write-Host "  $($preferredN8n.FullName)"
}

if ($RunHarmonyCheck) {
    Write-Host "[4/5] Running harmony check"
    .\.venv\Scripts\python.exe tools\harmony_check.py --json-out reports\harmony_check_windows_latest.json
}

if ($InstallEditorExtensions) {
    Write-Host "[editor] Installing VS Code recommendations"
    .\.venv\Scripts\python.exe tools\install_vscode_extensions.py --editor code
    if (Get-Command cursor -ErrorAction SilentlyContinue) {
        Write-Host "[editor] Installing Cursor recommendations"
        .\.venv\Scripts\python.exe tools\install_vscode_extensions.py --editor cursor
    } else {
        Write-Host "[editor] Cursor CLI not found; skipping Cursor extension install"
    }
}

Write-Host "[5/5] Done"
Write-Host "Start web server with:"
Write-Host "  .\.venv\Scripts\python.exe system_main.py web --host 127.0.0.1 --port 5001"
Write-Host "Start n8n (CMD channel):"
Write-Host "  .\tools\start_n8n_windows.cmd"
if ($preferredN8n) {
    Write-Host "Or direct preferred n8n path via cmd:"
    Write-Host "  cmd /c `"$($preferredN8n.FullName)`" start"
}
