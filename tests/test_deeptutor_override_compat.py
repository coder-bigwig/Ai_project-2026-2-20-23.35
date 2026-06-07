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
    for removed_router in ["auth", "tools"]:
        assert (
            re.search(
                rf"^\s*{removed_router},?\s*$",
                routers_import.group("body"),
                flags=re.MULTILINE,
            )
            is None
        )
    assert "app.include_router(auth.router" not in source
    assert "app.include_router(tools.router" not in source


def test_compose_files_do_not_mount_removed_auth_override() -> None:
    for compose_path in [ROOT / "docker-compose.yml", ROOT / "docker-compose.server.yml"]:
        compose = compose_path.read_text(encoding="utf-8")

        assert "./deeptutor-overrides/auth.py:/app/deeptutor/api/routers/auth.py:ro" not in compose


def test_main_override_uses_standard_logging() -> None:
    source = (ROOT / "deeptutor-overrides" / "main.py").read_text(encoding="utf-8")

    assert "from deeptutor.logging import get_logger" not in source
    assert 'logging.getLogger("deeptutor.api")' in source


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
