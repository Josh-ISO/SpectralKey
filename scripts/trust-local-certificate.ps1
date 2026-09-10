# Explicit one-time trust for this localhost-only, non-CA certificate.
$ErrorActionPreference = 'Stop'
$certPath = Join-Path (Split-Path -Parent $PSScriptRoot) '.tls/localhost.cer'
if (-not (Test-Path -LiteralPath $certPath)) { throw 'Run .venv\Scripts\python.exe scripts/setup_tls.py first.' }
$cert = [System.Security.Cryptography.X509Certificates.X509Certificate2]::new($certPath)
Write-Host "Trusting SpectralKey localhost certificate: $($cert.Thumbprint)"
Import-Certificate -FilePath $certPath -CertStoreLocation Cert:\CurrentUser\Root | Select-Object Subject,Thumbprint
