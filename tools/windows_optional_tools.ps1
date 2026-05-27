param(
    [switch]$InstallCursor,
    [switch]$InstallDocker
)

$ErrorActionPreference = "Stop"

function Has-Cmd($name) {
    return [bool](Get-Command $name -ErrorAction SilentlyContinue)
}

Write-Host "== Windows Optional Tools Check =="
Write-Host "Cursor CLI found: $([bool](Has-Cmd 'cursor'))"
Write-Host "Docker CLI found: $([bool](Has-Cmd 'docker'))"

if (-not (Has-Cmd 'winget')) {
    Write-Host "winget not found. Please install App Installer from Microsoft Store first."
    exit 1
}

if ($InstallCursor) {
    Write-Host "Installing Cursor..."
    winget install --id Cursor.Cursor -e --accept-package-agreements --accept-source-agreements
}

if ($InstallDocker) {
    Write-Host "Installing Docker Desktop..."
    winget install --id Docker.DockerDesktop -e --accept-package-agreements --accept-source-agreements
}

Write-Host "Done."
