$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$values = @{}
Get-Content (Join-Path $Root ".env") | ForEach-Object {
    if ($_ -match '^([^#=]+)=(.*)$') { $values[$matches[1]] = $matches[2] }
}
$headers = @{ apikey = $values.EVOLUTION_API_KEY; "Content-Type" = "application/json" }
$body = @{
    instanceName = "octopus-tickets-test"
    qrcode = $true
    integration = "WHATSAPP-BAILEYS"
    token = $values.EVOLUTION_INSTANCE_TOKEN
    rejectCall = $true
    groupsIgnore = $false
    alwaysOnline = $false
    readMessages = $false
    readStatus = $false
    syncFullHistory = $false
    webhook = @{
        enabled = $true
        url = "http://tickets-api:8000/webhooks/evolution"
        byEvents = $false
        base64 = $true
        headers = @{ "X-Octopus-Webhook-Token" = $values.TICKETS_WEBHOOK_TOKEN }
        events = @("QRCODE_UPDATED", "CONNECTION_UPDATE", "MESSAGES_UPSERT")
    }
} | ConvertTo-Json -Depth 8

try {
    $response = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8080/instance/create" -Headers $headers -Body $body
} catch {
    if ($_.Exception.Response.StatusCode.value__ -ne 403) { throw }
    $response = Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:8080/instance/connect/octopus-tickets-test" -Headers $headers
}
$qr = $response.qrcode.base64
if (-not $qr) {
    $response = Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:8080/instance/connect/octopus-tickets-test" -Headers $headers
    $qr = $response.base64
    if (-not $qr) { $qr = $response.qrcode.base64 }
}
if (-not $qr) {
    $state = Invoke-RestMethod -Method Get -Uri "http://127.0.0.1:8080/instance/connectionState/octopus-tickets-test" -Headers $headers
    Write-Host "No QR returned. Current state: $($state | ConvertTo-Json -Compress)"
    exit 0
}
$encoded = $qr -replace '^data:image/[^;]+;base64,', ''
$runtime = Join-Path $Root "runtime"
New-Item -ItemType Directory -Force -Path $runtime | Out-Null
$path = Join-Path $runtime "whatsapp-test-qr.png"
[IO.File]::WriteAllBytes($path, [Convert]::FromBase64String($encoded))
Write-Host "QR ready: $path"
Start-Process -FilePath $path
