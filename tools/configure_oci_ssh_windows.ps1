param(
  [string]$HostName = "",
  [string]$User = "opc",
  [string]$Alias = "oci-agent",
  [string]$KeyPath = "",
  [string]$EnvFile = ".env.oci",
  [switch]$TestConnection,
  [switch]$Force
)

$ErrorActionPreference = "Stop"

function Write-Step {
  param([string]$Message)
  Write-Host ""
  Write-Host "== $Message =="
}

function Test-UsableIpOrHost {
  param([string]$Value)
  if ([string]::IsNullOrWhiteSpace($Value)) {
    return $false
  }
  $blocked = @("你的IP", "your-ip", "YOUR_IP", "x.x.x.x", "0.0.0.0")
  return -not ($blocked -contains $Value.Trim())
}

function Read-EnvFile {
  param([string]$Path)
  $values = @{}
  if (-not (Test-Path $Path)) {
    return $values
  }
  Get-Content $Path | ForEach-Object {
    $line = $_.Trim()
    if ($line -eq "" -or $line.StartsWith("#") -or -not $line.Contains("=")) {
      return
    }
    $parts = $line.Split("=", 2)
    $values[$parts[0].Trim()] = $parts[1].Trim().Trim('"').Trim("'")
  }
  return $values
}

function Find-OciPrivateKey {
  $candidates = New-Object System.Collections.Generic.List[string]

  if ($env:OCI_KEY_PATH) {
    $candidates.Add($env:OCI_KEY_PATH)
  }

  $searchRoots = @(
    [Environment]::GetFolderPath("Desktop"),
    [Environment]::GetFolderPath("MyDocuments"),
    (Join-Path $HOME "Downloads"),
    (Join-Path $HOME ".ssh")
  ) | Where-Object { $_ -and (Test-Path $_) }

  foreach ($root in $searchRoots) {
    Get-ChildItem -Path $root -File -ErrorAction SilentlyContinue |
      Where-Object {
        $_.Name -match "(ssh-key|oci|oracle|opc|id_rsa|id_ed25519)" -and
        $_.Extension -in @(".key", ".pem", "")
      } |
      Sort-Object LastWriteTime -Descending |
      ForEach-Object { $candidates.Add($_.FullName) }
  }

  foreach ($candidate in $candidates) {
    if ($candidate -and (Test-Path $candidate)) {
      return (Resolve-Path $candidate).Path
    }
  }

  return ""
}

function Protect-PrivateKey {
  param([string]$Path)

  if (-not (Test-Path $Path)) {
    throw "找不到私鑰檔案：$Path"
  }

  $resolved = (Resolve-Path $Path).Path
  $userName = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name

  Write-Host "修正 Windows 私鑰 ACL：$resolved"
  & icacls $resolved /inheritance:r | Out-Null
  & icacls $resolved /grant:r "${userName}:R" | Out-Null
  & icacls $resolved /remove "Users" "Authenticated Users" "Everyone" 2>$null | Out-Null

  return $resolved
}

function Update-SshConfig {
  param(
    [string]$Alias,
    [string]$HostName,
    [string]$User,
    [string]$KeyPath
  )

  $sshDir = Join-Path $HOME ".ssh"
  $configPath = Join-Path $sshDir "config"
  New-Item -ItemType Directory -Force -Path $sshDir | Out-Null

  $escapedKey = $KeyPath.Replace("\", "/")
  $block = @"
Host $Alias
  HostName $HostName
  User $User
  IdentityFile $escapedKey
  IdentitiesOnly yes
  ServerAliveInterval 10
  ServerAliveCountMax 2
  StrictHostKeyChecking accept-new
"@

  $existing = ""
  if (Test-Path $configPath) {
    $existing = Get-Content $configPath -Raw
  }

  $pattern = "(?ms)^Host\s+$([regex]::Escape($Alias))\s+.*?(?=^Host\s+|\z)"
  if ($existing -match $pattern) {
    if (-not $Force) {
      Write-Host "SSH config 已有 Host $Alias，使用 -Force 可覆蓋。"
      return $configPath
    }
    $updated = [regex]::Replace($existing, $pattern, $block + "`r`n")
  } else {
    $updated = ($existing.TrimEnd() + "`r`n`r`n" + $block + "`r`n").TrimStart()
  }

  Set-Content -Path $configPath -Value $updated -Encoding UTF8
  return $configPath
}

function Write-OciEnvFile {
  param(
    [string]$Path,
    [string]$Alias,
    [string]$HostName,
    [string]$User,
    [string]$KeyPath
  )

  $content = @"
OCI_USER=$User
OCI_IP=$HostName
OCI_HOST_ALIAS=$Alias
OCI_KEY_PATH=$KeyPath
OCI_REMOTE_DIR=/home/$User/agent_system
OCI_LOCAL_DIR=.
OCI_SSH_STRICT_HOST_KEY_CHECKING=accept-new
OCI_VERIFY_AFTER_SYNC=1
"@
  Set-Content -Path $Path -Value $content -Encoding UTF8
}

Write-Step "讀取現有 OCI 設定"
$envValues = Read-EnvFile $EnvFile

if (-not (Test-UsableIpOrHost $HostName)) {
  if (Test-UsableIpOrHost $env:OCI_IP) {
    $HostName = $env:OCI_IP
  } elseif (Test-UsableIpOrHost $envValues["OCI_IP"]) {
    $HostName = $envValues["OCI_IP"]
  } else {
    $HostName = Read-Host "請輸入 Oracle/OCI 伺服器 Public IP 或 DNS"
  }
}

if (-not (Test-UsableIpOrHost $HostName)) {
  throw "OCI HostName/IP 仍是預設值或空值，請填入真正的 Public IP，例如：.\tools\configure_oci_ssh_windows.ps1 -HostName 123.123.123.123"
}

if ([string]::IsNullOrWhiteSpace($KeyPath)) {
  if ($env:OCI_KEY_PATH -and (Test-Path $env:OCI_KEY_PATH)) {
    $KeyPath = $env:OCI_KEY_PATH
  } elseif ($envValues["OCI_KEY_PATH"] -and (Test-Path $envValues["OCI_KEY_PATH"])) {
    $KeyPath = $envValues["OCI_KEY_PATH"]
  } else {
    $KeyPath = Find-OciPrivateKey
  }
}

if ([string]::IsNullOrWhiteSpace($KeyPath) -or -not (Test-Path $KeyPath)) {
  throw "找不到 Oracle/OCI 私鑰。請把 .key/.pem 放到桌面、下載、文件或 ~/.ssh，或用 -KeyPath 指定。"
}

Write-Step "修正私鑰權限"
$resolvedKey = Protect-PrivateKey $KeyPath

Write-Step "建立 SSH Host Alias"
$configPath = Update-SshConfig -Alias $Alias -HostName $HostName -User $User -KeyPath $resolvedKey
Write-Host "SSH config：$configPath"

Write-Step "寫入專案 .env.oci"
Write-OciEnvFile -Path $EnvFile -Alias $Alias -HostName $HostName -User $User -KeyPath $resolvedKey
Write-Host "OCI env：$((Resolve-Path $EnvFile).Path)"

Write-Step "完成"
Write-Host "之後在 Windows 可直接使用："
Write-Host "  ssh $Alias"
Write-Host "或明確測試："
Write-Host "  ssh -v $Alias"

if ($TestConnection) {
  Write-Step "測試 SSH 連線"
  & ssh $Alias "echo OCI_OK && hostname && whoami"
}
