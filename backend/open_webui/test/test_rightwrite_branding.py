import re
from pathlib import Path


def test_backend_default_brand_is_rightwrite_without_upstream_suffix():
    env_source = Path("backend/open_webui/env.py").read_text(encoding="utf-8")

    # 引号风格/getenv vs environ.get 会随格式化与上游合并变化,只断言语义
    assert re.search(
        r"""WEBUI_NAME = os\.(?:environ\.get|getenv)\(\s*['"]WEBUI_NAME['"],\s*['"]RightWrite['"]\s*\)""",
        env_source,
    )
    assert 'WEBUI_NAME += " (Open WebUI)"' not in env_source
