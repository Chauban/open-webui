from pathlib import Path


def test_backend_default_brand_is_rightwrite_without_upstream_suffix():
    env_source = Path("backend/open_webui/env.py").read_text(encoding="utf-8")

    assert 'WEBUI_NAME = os.environ.get("WEBUI_NAME", "RightWrite")' in env_source
    assert 'WEBUI_NAME += " (Open WebUI)"' not in env_source
