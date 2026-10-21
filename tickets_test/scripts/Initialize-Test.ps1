param([switch]$Force)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$EnvPath = Join-Path $Root ".env"
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
    "MINIO_ROOT_USER=octopus-test"
    "MINIO_ROOT_PASSWORD=$(New-HexSecret 32)"
    "TICKETS_ACCEPT_ALL_TEST_GROUPS=true"
    "TICKETS_ALLOWED_GROUP_IDS="
)
[IO.File]::WriteAllLines($EnvPath, $lines, [Text.UTF8Encoding]::new($false))
New-Item -ItemType Directory -Force -Path (Join-Path $Root "runtime\exports") | Out-Null
Write-Host "Generated isolated TEST secrets and runtime folders."
