#!/bin/bash

(
set -eu

HOME_DIR="${HOME:-/home/jovyan}"
WORK_DIR="${HOME_DIR}/work"
CODE_SERVER_BASE="${WORK_DIR}/.code-server"
USER_DATA_DIR="${CODE_SERVER_BASE}/user-data"
EXTENSIONS_DIR="${CODE_SERVER_BASE}/extensions"
SETTINGS_FILE="${USER_DATA_DIR}/User/settings.json"
DEFAULT_SETTINGS_FILE="${CODE_SERVER_DEFAULT_SETTINGS_FILE:-/opt/code-server/default-user-settings.json}"
SEED_DIR="${CODE_SERVER_EXTENSION_SEED_DIR:-/opt/code-server/extensions-seed}"

mkdir -p \
  "${USER_DATA_DIR}/User" \
  "${EXTENSIONS_DIR}" \
  "${WORK_DIR}/.config" \
  "${WORK_DIR}/.local/share" \
  "${WORK_DIR}/.m2/repository"

if [ -d "${SEED_DIR}" ]; then
  for extension in "${SEED_DIR}"/*; do
    [ -d "${extension}" ] || continue
    target="${EXTENSIONS_DIR}/$(basename "${extension}")"
    if [ ! -e "${target}" ]; then
      cp -R "${extension}" "${target}"
    fi
  done
fi

export DEFAULT_SETTINGS_FILE SETTINGS_FILE
python - <<'PY'
import json
import os
from pathlib import Path

default_path = Path(os.environ["DEFAULT_SETTINGS_FILE"])
settings_path = Path(os.environ["SETTINGS_FILE"])

defaults = {}
if default_path.is_file():
    try:
        defaults = json.loads(default_path.read_text(encoding="utf-8"))
    except Exception:
        defaults = {}
if not isinstance(defaults, dict):
    defaults = {}

current = {}
if settings_path.is_file():
    try:
        current = json.loads(settings_path.read_text(encoding="utf-8"))
    except Exception:
        current = {}
if not isinstance(current, dict):
    current = {}

updated = False
for key, value in defaults.items():
    if key not in current:
        current[key] = value
        updated = True

if updated or not settings_path.exists():
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(current, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY
)
