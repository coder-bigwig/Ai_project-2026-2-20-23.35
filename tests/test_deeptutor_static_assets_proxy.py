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

    for config_path in [
        ROOT / "nginx" / "nginx.conf",
        ROOT / "nginx" / "nginx.server.conf",
    ]:
        config = config_path.read_text(encoding="utf-8")
        assert "deeptutor:13782" in config
        for asset in required_assets:
            assert asset in config, f"{config_path} does not proxy /{asset}"
