param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$N8nArgs
)

$ErrorActionPreference = "Stop"

if ($N8nArgs.Count -gt 0) {
    $joined = $N8nArgs -join " "
    cmd /c "set N8N_HOST=127.0.0.1&& set N8N_PORT=5678&& n8n $joined"
} else {
    cmd /c "set N8N_HOST=127.0.0.1&& set N8N_PORT=5678&& n8n start"
}
