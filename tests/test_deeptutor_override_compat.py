import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_main_override_does_not_require_solve_router_at_import_time() -> None:
    source = (ROOT / "deeptutor-overrides" / "main.py").read_text(encoding="utf-8")
    routers_import = re.search(
        r"from deeptutor\.api\.routers import \((?P<body>.*?)\)",
        source,
        flags=re.DOTALL,
    )

    assert routers_import is not None
    assert re.search(r"^\s*solve,?\s*$", routers_import.group("body"), flags=re.MULTILINE) is None


def test_main_override_does_not_mount_removed_routers() -> None:
    source = (ROOT / "deeptutor-overrides" / "main.py").read_text(encoding="utf-8")
    routers_import = re.search(
        r"from deeptutor\.api\.routers import \((?P<body>.*?)\)",
        source,
        flags=re.DOTALL,
    )

    assert routers_import is not None
    for removed_router in ["auth"]:
        assert (
            re.search(
                rf"^\s*{removed_router},?\s*$",
                routers_import.group("body"),
                flags=re.MULTILINE,
            )
            is None
        )
    assert "app.include_router(auth.router" not in source


def test_main_override_keeps_v140_settings_routers_without_user_auth() -> None:
    source = (ROOT / "deeptutor-overrides" / "main.py").read_text(encoding="utf-8")

    assert "capabilities_settings," in source
    assert "tools as tools_router" in source

    expected_mounts = {
        "capabilities_settings": 'prefix="/api/v1/capabilities"',
        "tools_router": 'prefix="/api/v1/tools"',
    }
    for router_name, prefix in expected_mounts.items():
        pattern = rf"app\.include_router\(\s*{router_name}\.router\b(?P<body>.*?)\)"
        match = re.search(pattern, source, flags=re.DOTALL)
        assert match is not None, f"{router_name} router is not mounted"
        assert prefix in match.group("body")
        assert "dependencies=_user_context" not in match.group("body")


def test_compose_files_do_not_force_deeptutor_global_auth() -> None:
    for compose_path in [ROOT / "docker-compose.yml", ROOT / "docker-compose.server.yml"]:
        compose = compose_path.read_text(encoding="utf-8")

        assert "./deeptutor-overrides/auth.py:/app/deeptutor/api/routers/auth.py:ro" not in compose
        assert "DEEPTUTOR_IGNORE_PROCESS_ENV_OVERRIDES" not in compose
        assert "DEEPTUTOR_FORCE_AUTH_ENABLED" not in compose


def test_compose_files_allow_pinning_deeptutor_image() -> None:
    for compose_path in [ROOT / "docker-compose.yml", ROOT / "docker-compose.server.yml"]:
        compose = compose_path.read_text(encoding="utf-8")

        assert (
            "image: ${DEEPTUTOR_IMAGE:-ghcr.io/hkuds/deeptutor@sha256:"
            "2a6861732eb0f2c93c1fb8ec3316d912aa6fde84aed61918cfc6bcfc426f4a61}"
        ) in compose


def test_main_override_uses_standard_logging() -> None:
    source = (ROOT / "deeptutor-overrides" / "main.py").read_text(encoding="utf-8")

    assert "from deeptutor.logging import get_logger" not in source
    assert 'logging.getLogger("deeptutor.api")' in source


def test_user_data_routers_apply_sso_user_context_without_global_auth() -> None:
    source = (ROOT / "deeptutor-overrides" / "main.py").read_text(encoding="utf-8")

    assert "from fastapi import Depends, FastAPI, HTTPException, Request" in source
    assert "from deeptutor.api.routers.auth import require_auth" not in source
    assert "token_from_http_request" in source
    assert "user_from_token" in source
    assert "set_current_user" in source
    assert "_user_context = [Depends(apply_sso_user_context)]" in source

    protected_routers = [
        "tutorbot",
        "knowledge",
        "co_writer",
        "notebook",
        "book",
        "memory",
        "sessions",
        "question_notebook",
    ]
    for router_name in protected_routers:
        pattern = rf"app\.include_router\(\s*{router_name}\.router\b(?P<body>.*?)\)"
        match = re.search(pattern, source, flags=re.DOTALL)
        assert match is not None, f"{router_name} router is not mounted"
        assert "dependencies=_user_context" in match.group("body"), (
            f"{router_name} router must apply SSO user context for per-user paths"
        )


def test_global_and_websocket_routers_do_not_gain_http_auth_dependency() -> None:
    source = (ROOT / "deeptutor-overrides" / "main.py").read_text(encoding="utf-8")

    unprotected_routers = [
        "dashboard",
        "capabilities_settings",
        "tools_router",
        "settings",
        "skills",
        "system",
        "plugins_api",
        "agent_config",
        "unified_ws",
    ]
    for router_name in unprotected_routers:
        pattern = rf"app\.include_router\(\s*{router_name}\.router\b(?P<body>.*?)\)"
        match = re.search(pattern, source, flags=re.DOTALL)
        assert match is not None, f"{router_name} router is not mounted"
        assert "dependencies=_user_context" not in match.group("body"), (
            f"{router_name} router should not be covered by the minimal user-data auth change"
        )


def test_settings_override_does_not_import_removed_model_selection_service() -> None:
    source = (ROOT / "deeptutor-overrides" / "settings.py").read_text(encoding="utf-8")

    assert "deeptutor.services.model_selection" not in source
    assert "list_llm_options" not in source
    assert '@router.get("/llm-options")' not in source


def test_sqlite_store_accepts_new_message_context_arguments() -> None:
    source = (ROOT / "deeptutor-overrides" / "sqlite_store.py").read_text(encoding="utf-8")

    assert "metadata: dict[str, Any] | None = None" in source
    assert "parent_message_id: int | None = None" in source
    assert "leaf_message_id: int | None = None" in source
