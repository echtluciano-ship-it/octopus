param(
    [Parameter(Mandatory = $true)][string]$ManifestPath,
    [string]$GroupId = "120363000000000000@g.us",
    [string]$GroupName = "Tickets dataset TEST"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$values = @{}
Get-Content (Join-Path $Root ".env") | ForEach-Object {
    if ($_ -match '^([^#=]+)=(.*)$') { $values[$matches[1]] = $matches[2] }
}
$headers = @{
    "X-Octopus-Webhook-Token" = $values.TICKETS_WEBHOOK_TOKEN
    "Content-Type" = "application/json"
}
$manifest = Get-Content -Raw -LiteralPath $ManifestPath | ConvertFrom-Json
$receivedAt = if ($manifest.received_at -is [datetime]) {
    [DateTimeOffset]::new($manifest.received_at)
} else {
    [DateTimeOffset]::Parse(
        [string]$manifest.received_at,
        [Globalization.CultureInfo]::InvariantCulture,
        [Globalization.DateTimeStyles]::RoundtripKind
    )
}
$results = @()
foreach ($item in $manifest.files) {
    $path = [IO.Path]::GetFullPath((Join-Path (Split-Path -Parent $ManifestPath) $item.local_name))
    if (-not (Test-Path -LiteralPath $path)) { throw "Missing dataset file: $path" }
    $mime = if ($path.EndsWith(".pdf", [StringComparison]::OrdinalIgnoreCase)) {
        "application/pdf"
    } else {
        "image/jpeg"
    }
    $payload = @{
        event = "messages.upsert"
        instance = "octopus-tickets-test"
        data = @{
            key = @{
                remoteJid = $GroupId
                id = "DRIVE-$($item.drive_id)"
                participant = "dataset-erika@s.whatsapp.net"
            }
            pushName = "Erika - dataset TEST"
            messageTimestamp = $receivedAt.ToUnixTimeSeconds() + [int]$item.sequence
            source = @{
                system = "google_drive"
                document_id = $item.drive_id
                url = $item.drive_url
                batch = $manifest.dataset
            }
            message = @{
                documentMessage = @{
                    mimetype = $mime
                    fileName = $item.original_name
                }
                base64 = [Convert]::ToBase64String([IO.File]::ReadAllBytes($path))
            }
        }
    }
    $response = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/webhooks/evolution" `
        -Headers $headers -Body ($payload | ConvertTo-Json -Depth 10 -Compress)
    $results += [pscustomobject]@{
        sequence = $item.sequence
        drive_id = $item.drive_id
        original_name = $item.original_name
        document_id = $response.document_id
        duplicate = [bool]$response.duplicate
        idempotent_replay = [bool]$response.idempotent_replay
    }
}
$results | ConvertTo-Json -Depth 4
