$ErrorActionPreference = "Stop"

$root = Split-Path -Parent $PSScriptRoot
$attachment = "/mail-packages/OCTOPUS_TICKETS_PRUEBA_20_2026-10-23.zip"

Push-Location $root
try {
    docker compose --profile gmail run --rm tickets-mailer `
        python -m service.migrate
    $queueOutput = docker compose --profile gmail run --rm tickets-mailer `
        python -m service.gmail_cli queue-erika-test $attachment
    $queueLine = $queueOutput | Where-Object { $_ -match '^\{' } | Select-Object -Last 1
    if (-not $queueLine) {
        throw "No se pudo obtener el ID de la accion de correo."
    }
    $action = $queueLine | ConvertFrom-Json
    docker compose --profile gmail run --rm tickets-mailer `
        python -m service.gmail_cli send $action.action_id
} finally {
    Pop-Location
}
