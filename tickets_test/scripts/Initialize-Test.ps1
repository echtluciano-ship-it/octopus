param([switch]$Force)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$EnvPath = Join-Path $Root ".env"
$Runtime = Join-Path $Root "runtime"
New-Item -ItemType Directory -Force -Path (Join-Path $Runtime "exports") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $Runtime "certs") | Out-Null
$HostCaPath = Join-Path $Runtime "certs\host-proxy-ca.crt"
if (-not (Test-Path -LiteralPath $HostCaPath)) {
    New-Item -ItemType File -Path $HostCaPath | Out-Null
}
if ((Test-Path -LiteralPath $EnvPath) -and -not $Force) {
    Write-Host "TEST secrets already exist: $EnvPath"
    exit 0
}

function New-HexSecret([int]$Bytes) {
    $data = [byte[]]::new($Bytes)
    [System.Security.Cryptography.RandomNumberGenerator]::Fill($data)
    return [Convert]::ToHexString($data).ToLowerInvariant()
}

$lines = @(
    "POSTGRES_PASSWORD=$(New-HexSecret 24)"
    "EVOLUTION_API_KEY=$(New-HexSecret 32)"
    "EVOLUTION_INSTANCE_TOKEN=$(New-HexSecret 32)"
    "TICKETS_WEBHOOK_TOKEN=$(New-HexSecret 32)"
    "TICKETS_ACCEPT_ALL_TEST_GROUPS=true"
    "TICKETS_ALLOWED_GROUP_IDS="
    "TICKETS_GROUP_NAMES="
)
[IO.File]::WriteAllLines($EnvPath, $lines, [Text.UTF8Encoding]::new($false))
Write-Host "Generated isolated TEST secrets and runtime folders."
