@echo off
setlocal

cd /d %~dp0

if "%COMPOSE_PROJECT_NAME%"=="" (
  for /f %%I in ('powershell -NoProfile -Command "$n = Split-Path -Leaf (Get-Location); $n = $n.ToLower() -replace '[^a-z0-9_-]',''; $n = $n.Trim('-','_'); if ([string]::IsNullOrWhiteSpace($n)) { $n = 'training' }; if ($n -notmatch '^[a-z0-9]') { $n = 'p' + $n }; Write-Output $n"') do set "COMPOSE_PROJECT_NAME=%%I"
)
if "%COMPOSE_PROJECT_NAME%"=="" set "COMPOSE_PROJECT_NAME=training"

echo [dev] COMPOSE_PROJECT_NAME=%COMPOSE_PROJECT_NAME%
echo [dev] Stopping dev backend containers...
docker compose stop experiment-manager ai-assistant redis postgres >nul 2>&1

echo [dev] Optional: return to production gateway with:
echo        docker compose up -d frontend nginx
echo [dev] Done.

