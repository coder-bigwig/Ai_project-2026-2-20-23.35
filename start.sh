#!/usr/bin/env bash
# JupyterHub Training Platform - One Click Start (macOS / Linux)
# Mirrors start.bat for non-Windows hosts.

set -u
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
cd "$SCRIPT_DIR"

cyan()  { printf '\033[36m%s\033[0m\n' "$*"; }
green() { printf '\033[32m%s\033[0m\n' "$*"; }
red()   { printf '\033[31m%s\033[0m\n' "$*"; }
warn()  { printf '\033[33m[WARN]\033[0m %s\n' "$*"; }
info()  { printf '[INFO] %s\n' "$*"; }

press_any_key() {
    if [[ -t 0 ]]; then
        read -r -n 1 -s -p "Press any key to close... "
        echo
    fi
}

cyan "========================================================"
cyan "      JupyterHub Training Platform - One Click Start"
cyan "========================================================"
echo

# 1) Docker daemon must be reachable.
if ! docker info >/dev/null 2>&1; then
    red "[ERROR] Docker is not running or not installed. Start Docker Desktop first."
    press_any_key
    exit 1
fi

# 2) Build images. If build fails, fall back to --no-build (assumes images present).
info "[1/4] Build Docker images..."
USE_NO_BUILD=0
if ! docker compose build; then
    warn "Build failed. Falling back to start with --no-build."
    USE_NO_BUILD=1
fi
echo

# 3) Start the stack.
info "[2/4] Start services..."
if [[ "$USE_NO_BUILD" == "1" ]]; then
    if ! docker compose up -d --no-build; then
        red "[ERROR] Service startup failed."
        warn "--no-build was used. Make sure required images already exist locally."
        press_any_key
        exit 1
    fi
else
    if ! docker compose up -d; then
        red "[ERROR] Service startup failed."
        press_any_key
        exit 1
    fi
fi
echo

# 4) Give services a moment to come up before db init.
info "[3/4] Wait for services to initialize (~30s)..."
sleep 30
echo

# 5) Seed the database. Failure is non-fatal — user can retry.
info "[4/4] Initialize database and seed data..."
if ! docker compose exec -T experiment-manager python init_db.py; then
    warn "init_db.py failed. You can run it manually after startup:"
    echo "      docker compose exec -T experiment-manager python init_db.py"
fi
echo

cyan "========================================================"
green "                    Deployment Complete"
cyan "========================================================"
echo
echo "Access URLs:"
echo
echo "  - Unified Entry: http://localhost:8080"
echo "  - Experiment Manager API: http://localhost:8001/docs"
echo "  - AI Assistant API: http://localhost:8002/docs"
echo "  - Grafana: http://localhost:3001  (admin/admin)"
echo
press_any_key
