from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_nginx_proxies_deeptutor_root_static_images() -> None:
    required_assets = {
        "favicon-16x16\\.png",
        "favicon-32x32\\.png",
        "apple-touch-icon\\.png",
        "logo-ver2\\.png",
        "logo\\.png",
        "logo_black\\.png",
        "banner\\.png",
    }

    for config_path in [ROOT / "nginx" / "nginx.conf"]:
        config = config_path.read_text(encoding="utf-8")
        assert "deeptutor:13782" in config
        for asset in required_assets:
            assert asset in config, f"{config_path} does not proxy /{asset}"

    server_config_path = ROOT / "nginx" / "nginx.server.conf"
    server_config = server_config_path.read_text(encoding="utf-8")
    assert "deeptutor:3782" in server_config
    for asset in required_assets:
        assert asset in server_config, f"{server_config_path} does not proxy /{asset}"


def test_server_deeptutor_proxy_uses_current_container_ports() -> None:
    compose = (ROOT / "docker-compose.server.yml").read_text(encoding="utf-8")
    nginx = (ROOT / "nginx" / "nginx.server.conf").read_text(encoding="utf-8")

    assert '${DEEPTUTOR_BACKEND_PORT:-18101}:8001' in compose
    assert '${DEEPTUTOR_FRONTEND_PORT:-13782}:3782' in compose
    assert "BACKEND_PORT: 8001" in compose
    assert "FRONTEND_PORT: 3782" in compose
    assert "http://localhost:8001/" in compose
    assert "deeptutor:8001" in nginx
    assert "deeptutor:3782" in nginx
