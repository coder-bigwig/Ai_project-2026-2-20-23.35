#!/usr/bin/env bash
# Dev mode (macOS / Linux): backend services in Docker, React dev server on host.
# Mirrors start-dev.bat.

set -u
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
cd "$SCRIPT_DIR"

err()  { printf '\033[31m[dev]\033[0m %s\n' "$*"; }
info() { printf '[dev] %s\n' "$*"; }

press_any_key() {
    if [[ -t 0 ]]; then
        read -r -n 1 -s -p "Press any key to close... "
        echo
    fi
}

# Derive a docker-compose project name from the current directory (lowercase,
# strip illegal chars, force first char alpha-numeric).
derive_project_name() {
    local raw
    raw=$(basename "$PWD" | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9_-')
    raw=$(printf '%s' "$raw" | sed -E 's/^[_-]+//; s/[_-]+$//')
    if [[ -z "$raw" ]]; then
        raw=training
    fi
    if [[ ! "$raw" =~ ^[a-z0-9] ]]; then
        raw="p$raw"
    fi
    printf '%s' "$raw"
}

if [[ -z "${COMPOSE_PROJECT_NAME:-}" ]]; then
    COMPOSE_PROJECT_NAME=$(derive_project_name)
    export COMPOSE_PROJECT_NAME
fi

# Check Docker is up.
if ! docker info >/dev/null 2>&1; then
    err "Docker is not running or not installed. Start Docker Desktop first."
    press_any_key
    exit 1
fi

info "COMPOSE_PROJECT_NAME=$COMPOSE_PROJECT_NAME"
info "Starting backend services via docker compose..."
if ! docker compose up -d postgres redis experiment-manager ai-assistant; then
    err "Failed to start backend services."
    err "If this is first run, make sure Docker can pull base images, then run ./start.sh once."
    press_any_key
    exit 1
fi

info "Stopping project frontend/nginx services to avoid stale page on :8080 ..."
docker compose stop frontend nginx >/dev/null 2>&1 || true

info "Installing frontend dependencies if needed..."
if [[ ! -d "frontend/node_modules/react-scripts" ]]; then
    pushd frontend >/dev/null
    if ! npm install; then
        err "npm install failed."
        popd >/dev/null
        press_any_key
        exit 1
    fi
    popd >/dev/null
fi

# Trim spaces from SKIP_FRONTEND to match the .bat behaviour (`%SKIP_FRONTEND: =%`).
SKIP_FRONTEND_VAL=$(printf '%s' "${SKIP_FRONTEND:-}" | tr -d '[:space:]')
if [[ "${SKIP_FRONTEND_VAL}" == "1" ]]; then
    info "SKIP_FRONTEND=1, skip starting React dev server."
    info "Backend API: http://localhost:8001"
    exit 0
fi

# Find a free port starting at 3000 (cap at 3010 to avoid wandering).
choose_port() {
    local candidate=3000
    while (( candidate <= 3010 )); do
        if ! lsof -nP -iTCP:"$candidate" -sTCP:LISTEN >/dev/null 2>&1; then
            printf '%s' "$candidate"
            return 0
        fi
        candidate=$((candidate + 1))
    done
    printf '%s' "3000"  # give up and let CRA error if truly blocked
}

if [[ -z "${PORT:-}" ]]; then
    PORT=$(choose_port)
    export PORT
fi

if [[ "$PORT" == "3000" ]]; then
    info "Starting React dev server with hot reload on http://localhost:3000 ..."
else
    info "Port 3000 is busy, fallback to http://localhost:${PORT} ..."
fi

cd frontend
export REACT_APP_API_URL=http://localhost:8001
if ! npm start; then
    err "React dev server exited unexpectedly."
    press_any_key
    exit 1
fi
