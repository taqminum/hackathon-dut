import os

import pytest
from fastapi.testclient import TestClient

from app.main import app

# app.main 在导入时 load_dotenv()，所以本机 backend/.env 里的真实 AMAP_KEY /
# LLM_* 会渗进测试进程：用例会打真实网络请求，快则拿到与桩不一致的数据、
# 慢则挂在超时上（08-26 那次「测试卡死」就是这个根因）。
# 逐个用例清掉，需要的用例自己 monkeypatch.setenv / patch.dict 显式设回去。
ISOLATED_ENV_VARS = ("AMAP_KEY", "LLM_API_BASE", "LLM_API_KEY", "LLM_MODEL", "ALLOW_OFFLINE_FALLBACK")


@pytest.fixture(autouse=True)
def isolate_environment():
    # 显式真实验收必须穿过 backend/.env 中的 Web 服务 Key；普通回归仍隔离所有
    # 外部凭证，避免误消耗配额。两种模式由 RUN_LIVE_AMAP 明确区分。
    live_amap = os.getenv("RUN_LIVE_AMAP") == "1" and bool(os.getenv("AMAP_KEY"))
    isolated = ISOLATED_ENV_VARS if not live_amap else ("LLM_API_BASE", "LLM_API_KEY", "LLM_MODEL")
    saved = {name: os.environ.pop(name, None) for name in isolated}
    if not live_amap:
        # 旧的离线场景回归仍可显式测试，但生产环境默认没有这个开关，正式接口不会降级。
        os.environ["ALLOW_OFFLINE_FALLBACK"] = "1"
    try:
        yield
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value


@pytest.fixture(autouse=True)
def isolate_preferences():
    """偏好是进程内的模块级单例，会在用例之间泄漏。

    不隔离的话，一个用例点过「一般」就会压低后面所有用例里同类目 POI 的评分 ——
    表现为随机的、只在特定执行顺序下出现的失败。
    """
    from app.routes.api import preferences

    preferences.reset()
    yield
    preferences.reset()


@pytest.fixture
def client():
    return TestClient(app)
