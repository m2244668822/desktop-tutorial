param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$N8nArgs
)

$ErrorActionPreference = "Stop"

function Resolve-N8nCommand {
    $command = Get-Command "n8n.cmd" -ErrorAction SilentlyContinue
    if ($command -and (Test-Path -LiteralPath $command.Source)) {
        return $command.Source
    }

    $wingetRoot = Join-Path $env:LOCALAPPDATA "Microsoft\WinGet\Packages"
    if (Test-Path -LiteralPath $wingetRoot) {
        $candidate = Get-ChildItem -LiteralPath $wingetRoot -Directory -Filter "OpenJS.NodeJS.LTS*" -ErrorAction SilentlyContinue |
            Sort-Object LastWriteTime -Descending |
            ForEach-Object {
                Get-ChildItem -LiteralPath $_.FullName -File -Filter "n8n.cmd" -Recurse -ErrorAction SilentlyContinue
            } |
            Select-Object -First 1
        if ($candidate) {
            return $candidate.FullName
        }
    }

    throw "n8n.cmd not found; install Node.js and n8n first"
}

$N8nCommand = Resolve-N8nCommand
$quotedN8n = '"' + $N8nCommand + '"'

if ($N8nArgs.Count -gt 0) {
    $joined = $N8nArgs -join " "
    cmd /c "set N8N_HOST=127.0.0.1&& set N8N_PORT=5678&& set N8N_DIAGNOSTICS_ENABLED=false&& set N8N_VERSION_NOTIFICATIONS_ENABLED=false&& set N8N_TEMPLATES_ENABLED=false&& set N8N_PERSONALIZATION_ENABLED=false&& set N8N_PUBLIC_API_DISABLED=true&& set N8N_HIRING_BANNER_ENABLED=false&& set N8N_DISABLED_MODULES=mcp-registry&& set N8N_UNVERIFIED_PACKAGES_ENABLED=false&& set N8N_RUNNERS_TASK_TIMEOUT=60&& set N8N_COMPRESSION_NODE_MAX_DECOMPRESSED_SIZE_BYTES=268435456&& set N8N_COMPRESSION_NODE_MAX_ZIP_ENTRIES=1000&& set SKIP_STATISTICS_EVENTS=true&& set EXTERNAL_FRONTEND_HOOKS_URLS=&& $quotedN8n $joined"
} else {
    cmd /c "set N8N_HOST=127.0.0.1&& set N8N_PORT=5678&& set N8N_DIAGNOSTICS_ENABLED=false&& set N8N_VERSION_NOTIFICATIONS_ENABLED=false&& set N8N_TEMPLATES_ENABLED=false&& set N8N_PERSONALIZATION_ENABLED=false&& set N8N_PUBLIC_API_DISABLED=true&& set N8N_HIRING_BANNER_ENABLED=false&& set N8N_DISABLED_MODULES=mcp-registry&& set N8N_UNVERIFIED_PACKAGES_ENABLED=false&& set N8N_RUNNERS_TASK_TIMEOUT=60&& set N8N_COMPRESSION_NODE_MAX_DECOMPRESSED_SIZE_BYTES=268435456&& set N8N_COMPRESSION_NODE_MAX_ZIP_ENTRIES=1000&& set SKIP_STATISTICS_EVENTS=true&& set EXTERNAL_FRONTEND_HOOKS_URLS=&& $quotedN8n start"
}
