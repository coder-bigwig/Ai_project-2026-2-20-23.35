@echo off
setlocal

cd /d %~dp0
chcp 65001 >nul
set PYTHONUTF8=1

echo ========================================================
echo       JupyterHub Training Platform - One Click Start
echo ========================================================
echo.

REM Check Docker availability
docker info >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Docker is not running or not installed. Start Docker Desktop first.
    pause
    exit /b 1
)

echo [1/4] Build Docker images...
set "USE_NO_BUILD=0"
docker compose build
if errorlevel 1 (
    echo [WARN] Build failed. Falling back to start with --no-build.
    set "USE_NO_BUILD=1"
)

echo.
echo [2/4] Start services...
if "%USE_NO_BUILD%"=="1" (
    docker compose up -d --no-build
) else (
    docker compose up -d
)
if errorlevel 1 (
    echo [ERROR] Service startup failed.
    if "%USE_NO_BUILD%"=="1" (
        echo [TIP] --no-build was used. Make sure required images already exist locally.
    )
    pause
    exit /b 1
)

echo.
echo [3/4] Wait for services to initialize (~30s)...
timeout /t 30 /nobreak >nul

echo.
echo [4/4] Initialize database and seed data...
docker compose exec -T experiment-manager python init_db.py
if errorlevel 1 (
    echo [WARN] init_db.py failed. You can run it manually after startup.
)

echo.
echo ========================================================
echo                    Deployment Complete
echo ========================================================
echo.
echo Access URLs:
echo.
echo   - Unified Entry: http://localhost:8080
echo   - Experiment Manager API: http://localhost:8001/docs
echo   - AI Assistant API: http://localhost:8002/docs
echo   - Grafana: http://localhost:3001  (admin/admin)
echo.
echo Press any key to close...
pause >nul
