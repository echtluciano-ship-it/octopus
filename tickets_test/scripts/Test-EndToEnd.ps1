$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
Push-Location $Root
try {
    docker compose exec -T tickets-api python -m service.smoke
    if ($LASTEXITCODE -ne 0) { throw "Tickets end-to-end smoke test failed" }
    Invoke-RestMethod "http://127.0.0.1:8000/audit/reconciliation" | ConvertTo-Json
} finally {
    Pop-Location
}
