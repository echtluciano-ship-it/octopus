$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$credentials = Join-Path $root "runtime\gmail\credentials.json"

if (-not (Test-Path $credentials)) {
    throw "Falta $credentials. Descarga ahi el cliente OAuth de tipo Desktop de Google Cloud."
}

Push-Location $root
try {
    docker compose --profile gmail build tickets-mailer
    docker compose --profile gmail run --rm --service-ports tickets-mailer `
        python -m service.gmail_auth
} finally {
    Pop-Location
}
