$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
if (-not (Test-Path -LiteralPath (Join-Path $Root ".env"))) {
    & (Join-Path $Root "scripts\Initialize-Test.ps1")
}
$HostCaPath = Join-Path $Root "runtime\certs\host-proxy-ca.crt"
$AvgRoot = Get-ChildItem Cert:\CurrentUser\Root, Cert:\LocalMachine\Root |
    Where-Object { $_.Subject -like "*AVG Web/Mail Shield Root*" } |
    Select-Object -First 1
if ($AvgRoot -and ((-not (Test-Path -LiteralPath $HostCaPath)) -or (Get-Item $HostCaPath).Length -eq 0)) {
    & (Join-Path $Root "scripts\Export-HostCA.ps1")
}
if (-not (Get-Command docker -ErrorAction SilentlyContinue)) {
    throw "Docker is not available in PATH. Install/start Docker Desktop first."
}
Push-Location $Root
try {
    docker compose up -d --build
    if ($LASTEXITCODE -ne 0) { throw "docker compose up failed" }
    docker compose ps
} finally {
    Pop-Location
}
