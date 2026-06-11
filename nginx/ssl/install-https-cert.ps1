$ErrorActionPreference = "Stop"

$certUrl = "http://112.5.137.43:15027/training-platform.crt"
$certPath = Join-Path $env:TEMP "training-platform-112.5.137.43-15027.crt"

Write-Host "Downloading training platform certificate..."
Invoke-WebRequest -Uri $certUrl -OutFile $certPath -UseBasicParsing

Write-Host "Installing certificate into CurrentUser Trusted Root..."
& certutil.exe -f -user -addstore Root $certPath
if ($LASTEXITCODE -ne 0) {
    throw "certutil failed with exit code $LASTEXITCODE"
}

Write-Host ""
Write-Host "Installed. Close all browser windows, then open: https://112.5.137.43:15027/"
Write-Host "If the browser still shows old status, clear site data for 112.5.137.43:15027 and open it again."
