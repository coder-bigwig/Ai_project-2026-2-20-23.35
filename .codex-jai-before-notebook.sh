#!/bin/bash

_training_jai_finish() {
  return 0 2>/dev/null || exit 0
}

HOME_DIR="${HOME:-/home/jovyan}"
CONFIG_DIR="${HOME_DIR}/.local/share/jupyter/jupyter_ai"
CONFIG_FILE="${CONFIG_DIR}/config.json"

deepseek_base="${DEEPSEEK_BASE_URL:-https://api.deepseek.com}"
deepseek_model="${DEEPSEEK_MODEL:-deepseek-chat}"
openai_base="${OPENAI_API_BASE:-${OPENAI_BASE_URL:-}}"
effective_openai_api_key="${OPENAI_API_KEY:-${DEEPSEEK_API_KEY:-}}"

if [ -z "${openai_base}" ]; then
  case "${deepseek_base%/}" in
    */chat/completions)
      openai_base="${deepseek_base%/chat/completions}"
      ;;
    */v1)
      openai_base="${deepseek_base%/}"
      ;;
    *)
      openai_base="${deepseek_base%/}/v1"
      ;;
  esac
fi

provider_model_id="openai-chat-custom:${deepseek_model}"

mkdir -p "${CONFIG_DIR}"
export CONFIG_FILE PROVIDER_MODEL_ID="${provider_model_id}" OPENAI_BASE="${openai_base}" EFFECTIVE_OPENAI_API_KEY="${effective_openai_api_key}"
if [ -n "${effective_openai_api_key}" ]; then
  export HAS_OPENAI_API_KEY=1
else
  export HAS_OPENAI_API_KEY=0
fi
python - <<'PY2'
import json
import os
from pathlib import Path

config_file = Path(os.environ["CONFIG_FILE"])
provider_model_id = os.environ["PROVIDER_MODEL_ID"]
openai_base = os.environ["OPENAI_BASE"]
openai_api_key = os.environ.get("EFFECTIVE_OPENAI_API_KEY", "")
has_openai_api_key = os.environ.get("HAS_OPENAI_API_KEY") == "1"


def _normalize_payload(payload):
    payload = payload if isinstance(payload, dict) else {}
    payload.setdefault("model_provider_id", None)
    payload.setdefault("embeddings_provider_id", None)
    payload.setdefault("completions_model_provider_id", None)
    payload.setdefault("api_keys", {})
    payload.setdefault("send_with_shift_enter", False)
    payload.setdefault("fields", {})
    payload.setdefault("embeddings_fields", {})
    payload.setdefault("completions_fields", {})
    return payload


def _write(payload):
    config_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


existing = None
if config_file.exists():
    try:
        existing = json.loads(config_file.read_text(encoding="utf-8"))
    except Exception:
        existing = None

if not has_openai_api_key:
    if isinstance(existing, dict):
        payload = _normalize_payload(existing)
        current_model_id = payload.get("model_provider_id")
        if isinstance(current_model_id, str) and current_model_id.startswith("openai-chat-custom:"):
            payload["model_provider_id"] = None
            fields = payload.get("fields")
            if isinstance(fields, dict):
                fields.pop(current_model_id, None)
            api_keys = payload.get("api_keys")
            if isinstance(api_keys, dict):
                api_keys.pop("OPENAI_API_KEY", None)
            _write(payload)
    elif config_file.exists():
        _write(_normalize_payload({}))
    raise SystemExit(0)

if isinstance(existing, dict) and config_file.stat().st_size > 0:
    payload = _normalize_payload(existing)
    current_model_id = payload.get("model_provider_id")
    api_keys = payload.get("api_keys")
    if (
        isinstance(current_model_id, str)
        and current_model_id.startswith("openai-chat-custom:")
        and isinstance(api_keys, dict)
        and "OPENAI_API_KEY" not in api_keys
        and openai_api_key
    ):
        api_keys["OPENAI_API_KEY"] = openai_api_key
        _write(payload)
    raise SystemExit(0)

payload = {
    "model_provider_id": provider_model_id,
    "embeddings_provider_id": None,
    "completions_model_provider_id": None,
    "api_keys": {
        "OPENAI_API_KEY": openai_api_key,
    },
    "send_with_shift_enter": False,
    "fields": {
        provider_model_id: {
            "openai_api_base": openai_base,
        }
    },
    "embeddings_fields": {},
    "completions_fields": {},
}
_write(payload)
PY2
_training_jai_finish
