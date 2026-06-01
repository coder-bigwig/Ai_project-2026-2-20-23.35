#!/usr/bin/env bash
# Stop dev-mode backend containers (macOS / Linux). Mirrors stop-dev.bat.

set -u
SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)
cd "$SCRIPT_DIR"

info() { printf '[dev] %s\n' "$*"; }

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

info "COMPOSE_PROJECT_NAME=$COMPOSE_PROJECT_NAME"
info "Stopping dev backend containers..."
docker compose stop experiment-manager ai-assistant redis postgres >/dev/null 2>&1 || true

info "Optional: return to production gateway with:"
echo "       docker compose up -d frontend nginx"
info "Done."
