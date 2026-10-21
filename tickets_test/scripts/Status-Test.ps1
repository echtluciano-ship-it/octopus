$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Push-Location $Root
try {
    docker compose ps
    Write-Host "`nReconciliation:"
    Invoke-RestMethod "http://127.0.0.1:8000/audit/reconciliation" | ConvertTo-Json
} finally {
    Pop-Location
}
