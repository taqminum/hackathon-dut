"""静态文件托管的越界防护。

实测过的漏洞：`GET /../../.git/config` 曾返回 200 并泄漏仓库配置。
根因是 catch-all 路由直接 os.path.join 拼路径，没有归一化。
"""

import os

import pytest

from app.main import FRONTEND_DIST, _safe_static_file

TRAVERSAL_PATHS = (
    "/../../.git/config",
    "/../.git/config",
    "/..%2f..%2f.git%2fconfig",
    "/%2e%2e/%2e%2e/.git/config",
    r"/..\..\.git\config",
    "/static/../../../.git/config",
    "/../backend/.env",
    "/../../backend/.env",
    "/../requirements.txt",
    "/assets/../../../.git/config",
)

LEAK_MARKERS = ("[core]", "repositoryformatversion", "AMAP_KEY", "fastapi==")


@pytest.mark.parametrize("path", TRAVERSAL_PATHS)
def test_traversal_attempts_never_leak_files_outside_dist(client, path):
    response = client.get(path)

    assert response.status_code in (200, 404)
    for marker in LEAK_MARKERS:
        assert marker not in response.text


@pytest.mark.parametrize(
    "relative",
    ["../../.git/config", r"..\..\.git\config", "../backend/.env", "../requirements.txt"],
)
def test_safe_static_file_rejects_paths_outside_dist(relative):
    assert _safe_static_file(relative) is None


def test_safe_static_file_serves_real_asset_inside_dist():
    index = os.path.join(FRONTEND_DIST, "index.html")
    if not os.path.isfile(index):
        pytest.skip("webapp/dist 未构建")

    resolved = _safe_static_file("index.html")

    assert resolved is not None
    assert os.path.realpath(resolved) == os.path.realpath(index)


def test_safe_static_file_rejects_empty_and_directory_paths():
    assert _safe_static_file("") is None
    assert _safe_static_file("/") is None
    # 目录不是文件，不能当静态资源返回
    assert _safe_static_file("assets") is None


def test_spa_route_still_falls_back_to_index(client):
    response = client.get("/history")

    assert response.status_code == 200
    assert "<" in response.text[:200]


def test_dead_frontend_fallback_middleware_is_gone():
    """catch-all 路由已经承担了 SPA 兜底，中间件是死代码。"""
    import app.main as main

    assert not hasattr(main, "FrontendFallbackMiddleware")
