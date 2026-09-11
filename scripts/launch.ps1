$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$runtime = Join-Path $projectRoot '.venv/Scripts/python.exe'
$prototype = Join-Path $projectRoot 'backend/server.py'
$chrome = @(
    (Join-Path $env:ProgramFiles 'Google/Chrome/Application/chrome.exe'),
    (Join-Path ${env:ProgramFiles(x86)} 'Google/Chrome/Application/chrome.exe'),
    (Join-Path $env:LOCALAPPDATA 'Google/Chrome/Application/chrome.exe')
) | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $chrome) {
    $chromeCommand = Get-Command chrome.exe -ErrorAction SilentlyContinue
    if ($chromeCommand) { $chrome = $chromeCommand.Source }
}
if (-not $chrome) { throw 'Google Chrome was not found. Install Chrome to use this launcher.' }
if (-not (Test-Path -LiteralPath $runtime)) {
    throw 'Run python -m venv .venv, then .venv\Scripts\python.exe -m pip install -r requirements.txt in this #folder.'
}
# A virtual environment can exist before its dependencies have been installed.
& $runtime -c "import importlib.util, sys; sys.exit(0 if all(importlib.util.find_spec(name) for name in ('aiohttp', 'cryptography')) else 1)"
if ($LASTEXITCODE -ne 0) {
    Write-Host 'Installing SpectralKey Python dependencies...'
    & $runtime -m pip install -r (Join-Path $projectRoot 'requirements.txt')
    if ($LASTEXITCODE -ne 0) {
        throw 'Could not install dependencies. Check your internet connection and run .venv\Scripts\python.exe -m pip install -r requirements.txt from the project folder.'
    }
}
if (-not $env:SPECTRALKEY_TLS_CERT) {
    & $runtime (Join-Path $PSScriptRoot 'setup_tls.py')
    if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
    $certPath = Join-Path $projectRoot '.tls/localhost.cer'
    $cert = [System.Security.Cryptography.X509Certificates.X509Certificate2]::new($certPath)
    if (-not (Test-Path -LiteralPath "Cert:\CurrentUser\Root\$($cert.Thumbprint)")) {
        throw 'Trust the localhost certificate first: run .\scripts\trust-local-certificate.ps1. This enables HTTPS without browser certificate warnings.'
    }
}
& $runtime (Join-Path $PSScriptRoot 'launch_check.py')
$launchCheck = $LASTEXITCODE
if ($launchCheck -eq 10) {
    Start-Process -FilePath $chrome -ArgumentList 'https://localhost:8765'
    exit 0
}
if ($launchCheck -ne 0) { exit $launchCheck }
Write-Host 'Open https://localhost:8765 in your browser. Press Ctrl+C here to stop SpectralKey.'
& $runtime $prototype --browser $chrome
exit $LASTEXITCODE
