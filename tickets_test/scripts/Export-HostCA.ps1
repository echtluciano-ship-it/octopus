param(
    [string]$SubjectPattern = "AVG Web/Mail Shield Root",
    [string]$OutputPath = ""
)

$ErrorActionPreference = "Stop"

if (-not $OutputPath) {
    $OutputPath = Join-Path $PSScriptRoot "..\runtime\certs\host-proxy-ca.crt"
}

$certificate = Get-ChildItem Cert:\CurrentUser\Root, Cert:\LocalMachine\Root |
    Where-Object { $_.Subject -like "*$SubjectPattern*" } |
    Sort-Object NotAfter -Descending |
    Select-Object -First 1

if (-not $certificate) {
    throw "No se encontro un certificado raiz que coincida con '$SubjectPattern'."
}

$bytes = $certificate.Export(
    [System.Security.Cryptography.X509Certificates.X509ContentType]::Cert
)
$base64 = [Convert]::ToBase64String($bytes, [Base64FormattingOptions]::InsertLineBreaks)
$pem = "-----BEGIN CERTIFICATE-----`r`n$base64`r`n-----END CERTIFICATE-----`r`n"

$parent = Split-Path -Parent $OutputPath
New-Item -ItemType Directory -Force -Path $parent | Out-Null
[IO.File]::WriteAllText($OutputPath, $pem, [Text.Encoding]::ASCII)

Write-Host "Certificado publico exportado a $OutputPath"
Write-Host "Thumbprint: $($certificate.Thumbprint)"
