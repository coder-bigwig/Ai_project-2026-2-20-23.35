import os
import re

import psycopg2


def _parse_accounts(raw: str, fallback: str) -> list:
    source = raw if raw is not None else fallback
    parts = [item.strip() for item in str(source).split(",")]
    return [item for item in parts if item]

# Base Config
c.JupyterHub.db_url = os.environ.get(
    "HUB_DB_URL", "postgresql://jupyterhub:changeme@postgres/jupyterhub"
)

# Optional: serve JupyterHub behind a path prefix (recommended for server deploy).
# Example: set `JUPYTERHUB_BASE_URL=/jupyter` and put Nginx proxy at `/jupyter/`.
def _normalize_base_url(value: str) -> str:
    base = (value or "/").strip()
    if not base.startswith("/"):
        base = f"/{base}"
    if not base.endswith("/"):
        base = f"{base}/"
    return base

base_url = _normalize_base_url(os.environ.get("JUPYTERHUB_BASE_URL", "/"))
c.JupyterHub.bind_url = f"http://0.0.0.0:8000{base_url}"


def _normalize_openai_compatible_base_url(value: str) -> str:
    raw = str(value or "").strip().rstrip("/")
    if not raw:
        return "https://api.deepseek.com/v1"
    if raw.endswith("/chat/completions"):
        return raw[: -len("/chat/completions")]
    if raw.endswith("/v1"):
        return raw
    return f"{raw}/v1"


def _default_jupyter_ai_shared_config() -> dict:
    deepseek_api_key = str(os.environ.get("DEEPSEEK_API_KEY", "") or "").strip()
    deepseek_base_url = str(os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com") or "").strip()
    deepseek_chat_model = str(os.environ.get("DEEPSEEK_MODEL", "deepseek-chat") or "").strip()
    deepseek_reasoner_model = str(os.environ.get("DEEPSEEK_REASONER_MODEL", "deepseek-reasoner") or "").strip()
    return {
        "api_key": deepseek_api_key,
        "base_url": (deepseek_base_url or "https://api.deepseek.com").rstrip("/"),
        "chat_model": deepseek_chat_model or "deepseek-chat",
        "reasoner_model": deepseek_reasoner_model or "deepseek-reasoner",
    }


def _pick_shared_config_value(raw: dict, *keys: str) -> str:
    if not isinstance(raw, dict):
        return ""
    for key in keys:
        if key in raw:
            return str(raw.get(key) or "").strip()
    return ""


def _load_jupyter_ai_shared_config() -> dict:
    payload = _default_jupyter_ai_shared_config()
    if not experiment_manager_db_url:
        return payload

    try:
        with psycopg2.connect(experiment_manager_db_url) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    f'SELECT value_json FROM "{experiment_manager_schema}"."app_kv_store" WHERE key = %s',
                    ("ai_shared_config",),
                )
                row = cursor.fetchone()
                shared = row[0] if row else None
                if isinstance(shared, dict):
                    # Keep explicit empty api_key so admin/teacher can disable Jupyter AI key centrally.
                    if ("api_key" in shared) or ("apiKey" in shared):
                        payload["api_key"] = _pick_shared_config_value(shared, "api_key", "apiKey")

                    base_url = _pick_shared_config_value(shared, "base_url", "baseUrl")
                    if base_url:
                        payload["base_url"] = base_url.rstrip("/")

                    chat_model = _pick_shared_config_value(shared, "chat_model", "chatModel", "model")
                    if chat_model:
                        payload["chat_model"] = chat_model

                    reasoner_model = _pick_shared_config_value(shared, "reasoner_model", "reasonerModel")
                    if reasoner_model:
                        payload["reasoner_model"] = reasoner_model
    except Exception as exc:
        print(f"[jupyter-ai] failed to load shared config from postgres: {exc}")

    return payload

# Auth - DummyAuthenticator (any username; optional shared password)
from jupyterhub.auth import DummyAuthenticator

c.JupyterHub.authenticator_class = DummyAuthenticator
dummy_password = os.environ.get("DUMMY_PASSWORD")
if dummy_password:
    c.DummyAuthenticator.password = dummy_password
admin_accounts = set(_parse_accounts(os.environ.get("ADMIN_ACCOUNTS"), "fit_admin"))
admin_accounts.update({"teacher1"})  # backward compatible legacy account
c.Authenticator.admin_users = admin_accounts
c.JupyterHub.admin_access = True

# Multi-tenant: each user gets a dedicated notebook container.
from dockerspawner import DockerSpawner

def _resolve_network_name() -> str:
    configured = str(os.environ.get("DOCKER_NETWORK_NAME", "")).strip()
    if configured:
        return configured

    try:
        import docker

        current_container = str(os.environ.get("HOSTNAME", "")).strip()
        if current_container:
            client = docker.from_env()
            container = client.containers.get(current_container)
            attached_networks = list(
                (container.attrs.get("NetworkSettings", {}).get("Networks", {}) or {}).keys()
            )
            if attached_networks:
                for attached_name in attached_networks:
                    if attached_name.endswith("training-network"):
                        return attached_name
                return attached_networks[0]
    except Exception as exc:
        print(f"[network] failed to auto-detect compose network: {exc}")

    return "training-network"


network_name = _resolve_network_name()


def _resolve_compose_project_name(resolved_network_name: str) -> str:
    configured = str(os.environ.get("COMPOSE_PROJECT_NAME", "")).strip()
    if configured:
        return configured

    suffix = "_training-network"
    if resolved_network_name.endswith(suffix):
        prefix = resolved_network_name[: -len(suffix)]
        if prefix:
            return prefix
    return ""


compose_project_name = _resolve_compose_project_name(network_name)
notebook_image = os.environ.get("DOCKER_NOTEBOOK_IMAGE", "training-lab:latest")
experiment_manager_db_url = os.environ.get("EXPERIMENT_MANAGER_DATABASE_URL", os.environ.get("HUB_DB_URL", ""))
experiment_manager_schema = str(os.environ.get("POSTGRES_SCHEMA", "experiment_manager") or "experiment_manager").strip()
if not re.match(r"^[A-Za-z_][A-Za-z0-9_]*$", experiment_manager_schema):
    experiment_manager_schema = "experiment_manager"
teacher_accounts = set(
    _parse_accounts(
        os.environ.get("TEACHER_ACCOUNTS"),
        "teacher_001,teacher_002,teacher_003,teacher_004,teacher_005",
    )
)
admin_accounts = set(c.Authenticator.admin_users or set())
enable_storage_limit = str(os.environ.get("ENABLE_DOCKER_STORAGE_LIMIT", "0")).strip() == "1"
serverapp_websocket_url = str(os.environ.get("SERVERAPP_WEBSOCKET_URL", "")).strip()
enable_code_server = str(os.environ.get("ENABLE_CODE_SERVER", "1") or "").strip().lower() not in {"0", "false", "no", "off"}
code_server_port = str(os.environ.get("CODE_SERVER_PORT", "13337") or "13337").strip() or "13337"

default_role_limits = {
    "student": {"cpu_limit": 2.0, "memory_limit": "8G", "storage_limit": "2G"},
    "teacher": {"cpu_limit": 2.0, "memory_limit": "8G", "storage_limit": "2G"},
    "admin": {"cpu_limit": 4.0, "memory_limit": "8G", "storage_limit": "20G"},
}
_SIZE_LIMIT_PATTERN = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([kmgt]?b?)?\s*$", re.IGNORECASE)


def _default_size_unit(default_value):
    match = _SIZE_LIMIT_PATTERN.match(str(default_value or "").strip())
    if not match:
        return "B"
    unit_raw = (match.group(2) or "").upper()
    if unit_raw in {"K", "KB"}:
        return "K"
    if unit_raw in {"M", "MB"}:
        return "M"
    if unit_raw in {"G", "GB"}:
        return "G"
    if unit_raw in {"T", "TB"}:
        return "T"
    return "B"


def _normalize_size_limit(value, default_value):
    raw = str(value or "").strip()
    if not raw:
        return default_value

    match = _SIZE_LIMIT_PATTERN.match(raw)
    if not match:
        return default_value

    number = float(match.group(1))
    if number <= 0:
        return default_value

    default_unit = _default_size_unit(default_value)
    unit_raw = (match.group(2) or "").upper()
    if unit_raw == "":
        unit = default_unit
    elif unit_raw == "B":
        # Backward compatibility: convert legacy values like "8B" to role-default units.
        unit = default_unit if default_unit != "B" else "B"
    elif unit_raw in {"K", "KB"}:
        unit = "K"
    elif unit_raw in {"M", "MB"}:
        unit = "M"
    elif unit_raw in {"G", "GB"}:
        unit = "G"
    elif unit_raw in {"T", "TB"}:
        unit = "T"
    else:
        unit = "B"

    if number.is_integer():
        number_text = str(int(number))
    else:
        number_text = str(round(number, 3)).rstrip("0").rstrip(".")
    if unit == "B":
        return number_text
    return f"{number_text}{unit}"


def _normalize_quota(raw, role):
    role_key = role if role in default_role_limits else "student"
    base = default_role_limits[role_key]
    source = raw if isinstance(raw, dict) else {}

    try:
        cpu_limit = float(source.get("cpu_limit", base["cpu_limit"]))
    except Exception:
        cpu_limit = float(base["cpu_limit"])
    cpu_limit = max(0.1, min(cpu_limit, 128.0))

    memory_limit = _normalize_size_limit(source.get("memory_limit"), base["memory_limit"])
    storage_limit = _normalize_size_limit(source.get("storage_limit"), base["storage_limit"])
    return {
        "cpu_limit": cpu_limit,
        "memory_limit": memory_limit,
        "storage_limit": storage_limit,
    }


def _infer_role(username: str) -> str:
    user = str(username or "").strip()
    if user in admin_accounts:
        return "admin"
    if user in teacher_accounts:
        return "teacher"
    return "student"


def _apply_jupyter_ai_environment(environment: dict) -> dict:
    env = dict(environment or {})

    # Pull dynamic config from experiment_manager.app_kv_store(ai_shared_config),
    # so admin/teacher "AI功能" settings and Jupyter AI use one source of truth.
    shared = _load_jupyter_ai_shared_config()
    deepseek_api_key = str(shared.get("api_key") or "").strip()
    deepseek_base_url = str(shared.get("base_url") or "").strip() or "https://api.deepseek.com"
    deepseek_model = str(shared.get("chat_model") or "").strip() or "deepseek-chat"
    deepseek_reasoner_model = str(shared.get("reasoner_model") or "").strip() or "deepseek-reasoner"
    openai_base = _normalize_openai_compatible_base_url(deepseek_base_url)

    if deepseek_api_key:
        env["DEEPSEEK_API_KEY"] = deepseek_api_key
        # Jupyter AI 3.x (LiteLLM/OpenAI-compatible providers) recognizes OPENAI_API_KEY.
        env["OPENAI_API_KEY"] = deepseek_api_key
    else:
        env.pop("DEEPSEEK_API_KEY", None)
        env.pop("OPENAI_API_KEY", None)
    if deepseek_base_url:
        env["DEEPSEEK_BASE_URL"] = deepseek_base_url
        # Provide both aliases to maximize compatibility across provider backends.
        env["OPENAI_BASE_URL"] = openai_base
        env["OPENAI_API_BASE"] = openai_base
    if deepseek_model:
        env["DEEPSEEK_MODEL"] = deepseek_model
        # Hint value for onboarding docs / custom scripts if needed.
        env["TRAINING_JUPYTER_AI_DEFAULT_MODEL"] = f"deepseek/{deepseek_model}"
    if deepseek_reasoner_model:
        env["DEEPSEEK_REASONER_MODEL"] = deepseek_reasoner_model
        env["TRAINING_JUPYTER_AI_REASONER_MODEL"] = f"deepseek/{deepseek_reasoner_model}"

    return env


def _load_resource_policy():
    payload = {"defaults": dict(default_role_limits), "overrides": {}}
    if not experiment_manager_db_url:
        return payload

    try:
        with psycopg2.connect(experiment_manager_db_url) as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    f'SELECT value_json FROM \"{experiment_manager_schema}\".\"app_kv_store\" WHERE key = %s',
                    ("resource_policy",),
                )
                row = cursor.fetchone()
                data = row[0] if row else {}
                if isinstance(data, dict):
                    payload.update(data)
    except Exception as exc:
        print(f"[resource-policy] failed to load policy from postgres: {exc}")
    return payload


def _effective_quota(username: str):
    role = _infer_role(username)
    policy = _load_resource_policy()
    defaults = policy.get("defaults", {})
    base = _normalize_quota(defaults.get(role), role)
    overrides = policy.get("overrides", {})
    if isinstance(overrides, dict):
        custom = overrides.get(username)
        if isinstance(custom, dict):
            return _normalize_quota(custom, role)
    return base


async def _apply_user_resource_limits(spawner):
    username = str(getattr(getattr(spawner, "user", None), "name", "") or "")
    quota = _effective_quota(username)
    role = _infer_role(username)

    spawner.cpu_limit = float(quota["cpu_limit"])
    spawner.mem_limit = quota["memory_limit"]

    extra_host_config = dict(spawner.extra_host_config or {})
    extra_host_config["network_mode"] = network_name
    if enable_storage_limit:
        storage_opt = dict(extra_host_config.get("storage_opt") or {})
        storage_opt["size"] = quota["storage_limit"]
        extra_host_config["storage_opt"] = storage_opt
    spawner.extra_host_config = extra_host_config

    environment = dict(spawner.environment or {})
    environment["TRAINING_USER_ROLE"] = role
    environment["TRAINING_CPU_LIMIT"] = str(quota["cpu_limit"])
    environment["TRAINING_MEMORY_LIMIT"] = quota["memory_limit"]
    environment["TRAINING_STORAGE_LIMIT"] = quota["storage_limit"]
    environment["ENABLE_CODE_SERVER"] = "1" if enable_code_server else "0"
    environment["CODE_SERVER_PORT"] = code_server_port
    spawner.environment = _apply_jupyter_ai_environment(environment)

c.JupyterHub.spawner_class = DockerSpawner

# Hub listens inside its container; other containers reach it via service name.
c.JupyterHub.hub_ip = "0.0.0.0"
c.JupyterHub.hub_connect_ip = os.environ.get("HUB_CONNECT_IP", "jupyterhub")

c.DockerSpawner.image = notebook_image
c.DockerSpawner.network_name = network_name
c.DockerSpawner.use_internal_ip = True
c.DockerSpawner.extra_host_config = {"network_mode": network_name}
c.Spawner.pre_spawn_hook = _apply_user_resource_limits
c.Spawner.start_timeout = int(os.environ.get("JUPYTERHUB_SPAWNER_START_TIMEOUT", "180"))
c.Spawner.http_timeout = int(os.environ.get("JUPYTERHUB_SPAWNER_HTTP_TIMEOUT", "180"))

# Persist per-user work directory via a dedicated docker volume.
if compose_project_name:
    user_workspace_volume = f"{compose_project_name}_user-{{username}}"
    course_materials_volume = f"{compose_project_name}_course-materials"
    shared_datasets_volume = f"{compose_project_name}_shared-datasets"
else:
    user_workspace_volume = "training-user-{username}"
    course_materials_volume = "training-course-materials"
    shared_datasets_volume = "training-shared-datasets"

c.DockerSpawner.remove = True
c.DockerSpawner.volumes = {
    user_workspace_volume: {"bind": "/home/jovyan/work", "mode": "rw"},
    # Shared read-only materials.
    course_materials_volume: {"bind": "/home/jovyan/course", "mode": "ro"},
    shared_datasets_volume: {"bind": "/home/jovyan/datasets", "mode": "ro"},
}

# Root includes work + course + datasets. Land on work by default.
c.DockerSpawner.notebook_dir = "/home/jovyan"
c.Spawner.default_url = "/lab/tree/work"

# Allow embedding JupyterLab in the portal iframe (different port => relax CSP).
c.Spawner.args = [
    "--ServerApp.allow_origin=*",
    # JupyterLab kernel channels uses WebSockets, which performs strict origin checks.
    # When running behind reverse proxies, the Host header reaching the single-user server
    # may differ from the browser Origin. Allow all origins for teaching-platform embeds.
    "--ServerApp.allow_origin_pat=.*",
    "--ServerApp.disable_check_xsrf=True",
    '--ServerApp.tornado_settings={"headers":{"Content-Security-Policy":"frame-ancestors *","Access-Control-Allow-Origin":"*"}}',
]
if serverapp_websocket_url:
    c.Spawner.args.append(f"--ServerApp.websocket_url={serverapp_websocket_url}")

# Default: Hub home
c.JupyterHub.default_url = "/hub/home"

# Service token for the training platform backend to manage user servers.
service_token = os.environ.get("EXPERIMENT_MANAGER_API_TOKEN", "").strip()
if service_token:
    service_name = "experiment-manager"
    c.JupyterHub.services = [
        {
            "name": service_name,
            "api_token": service_token,
        }
    ]
    c.JupyterHub.load_roles = [
        {
            "name": "experiment-manager-service-role",
            "description": "Allow the backend to manage Hub users, servers, and short-lived user tokens.",
            "services": [service_name],
            "scopes": [
                "admin:users",
                "admin:servers",
                "tokens",
            ],
        }
    ]

# Logs
c.JupyterHub.log_level = "INFO"
c.Spawner.debug = False
# Allow Prometheus to scrape /hub/metrics without Hub auth.
c.JupyterHub.authenticate_prometheus = False

# Allow embedding Hub pages as well (login page shown inside iframe on first access).
c.JupyterHub.tornado_settings = {
    "headers": {
        "Content-Security-Policy": "frame-ancestors 'self' http://localhost:8080 *",
        "Access-Control-Allow-Origin": "*",
    },
    # Respect X-Forwarded-* headers when running behind Nginx / TLS termination.
    "xheaders": True,
}
