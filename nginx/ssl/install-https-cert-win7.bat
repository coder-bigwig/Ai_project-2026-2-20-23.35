@echo off
setlocal
set CERT_URL=http://172.29.150.25/training-platform.crt
set CERT_FILE=%TEMP%\training-platform-172.29.150.25.crt

echo Downloading training platform certificate...
certutil -urlcache -f "%CERT_URL%" "%CERT_FILE%"
if errorlevel 1 goto fail

echo Installing certificate into CurrentUser Trusted Root...
certutil -f -user -addstore Root "%CERT_FILE%"
if errorlevel 1 goto fail

echo.
echo Certificate installed.
echo Close ALL browser windows, then open https://172.29.150.25/
echo If Chrome still shows unsafe, clear site data for 172.29.150.25 and open again.
echo.
pause
exit /b 0

:fail
echo.
echo Install failed. Right-click this BAT and choose Run as administrator, or ask the teacher to install the certificate manually.
echo.
pause
exit /b 1
