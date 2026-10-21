$ErrorActionPreference = "Continue"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Runtime = Join-Path $Root "runtime"
New-Item -ItemType Directory -Force -Path $Runtime | Out-Null
$Log = Join-Path $Runtime "wsl-install.log"
$Status = Join-Path $Runtime "wsl-install.status"
Remove-Item -LiteralPath $Status -ErrorAction SilentlyContinue
& wsl.exe --install --no-distribution *>&1 | Tee-Object -FilePath $Log
$code = $LASTEXITCODE
[IO.File]::WriteAllText($Status, [string]$code, [Text.UTF8Encoding]::new($false))
exit $code
