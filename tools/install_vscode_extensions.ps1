param(
  [string]$Editor = "code",
  [string]$ExtensionsFile = ".vscode/extensions.json",
  [switch]$DryRun
)

$ErrorActionPreference = "Stop"

if (-not (Test-Path $ExtensionsFile)) {
  throw "Missing extensions file: $ExtensionsFile"
}

$data = Get-Content $ExtensionsFile -Raw | ConvertFrom-Json
$recommendations = @($data.recommendations)
$localExtensions = @("chengcheng-local.cursor-agent-sidebar")

foreach ($extensionId in $recommendations) {
  if ($localExtensions -contains $extensionId) {
    Write-Host "[skip-local] $extensionId -> install from cursor-agent-sidebar-extension VSIX"
    continue
  }

  if ($DryRun) {
    Write-Host "[dry-run] $Editor --install-extension $extensionId"
    continue
  }

  Write-Host "[install] $extensionId"
  & $Editor --install-extension $extensionId
  if ($LASTEXITCODE -ne 0) {
    throw "Failed to install extension: $extensionId"
  }
}

Write-Host "[ok] extension recommendations processed"
