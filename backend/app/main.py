import os

from dotenv import load_dotenv

# 必须在导入 app.routes / app.services 之前完成，服务层用 os.getenv 读取 AMAP_KEY。
# 显式指向 backend/.env，避免工作目录不是 backend/ 时找不到文件。
load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from app.routes import api

# 提到 add_middleware 之前定义：静态目录是路由的输入，不该在中间件注册之后才出现。
FRONTEND_DIST = os.path.realpath(
    os.path.join(os.path.dirname(__file__), "..", "..", "webapp", "dist")
)
# 这些前缀属于后端，不能掉进 SPA 兜底，否则拼错的接口名会返回 index.html，
# 前端拿到一段 HTML 再去 JSON.parse，报的错和真实原因完全无关。
API_PREFIXES = ("api", "assets")

app = FastAPI(title="Serendipity Navigation")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api.router, prefix="/api")


@app.get("/health")
def health():
    return {"status": "ok"}


def _safe_static_file(relative_path: str) -> str | None:
    """把 URL 路径映射到 dist 里的真实文件，越界返回 None。

    只做前缀字符串检查是不够的：`..` 段、Windows 反斜杠、以及 dist 内指向外部的
    符号链接都能绕过。所以先 realpath 归一化（解析掉 `..` 和链接），
    再用 commonpath 判断是否仍在 dist 之内。
    """
    if not relative_path:
        return None

    # 反斜杠在 Windows 上是路径分隔符，先统一成 `/` 再按段处理，
    # 否则 `..\..\.git\config` 会被当成一个普通文件名放过。
    normalized = relative_path.replace("\\", "/").lstrip("/")
    if not normalized:
        return None

    candidate = os.path.realpath(os.path.join(FRONTEND_DIST, normalized))

    try:
        if os.path.commonpath([candidate, FRONTEND_DIST]) != FRONTEND_DIST:
            return None
    except ValueError:
        # 不同盘符（Windows）时 commonpath 会抛 ValueError —— 那必然是越界。
        return None

    return candidate if os.path.isfile(candidate) else None


def _index_response():
    index_path = os.path.join(FRONTEND_DIST, "index.html")
    if os.path.isfile(index_path):
        return FileResponse(index_path)
    return {"status": "frontend not built"}


@app.get("/")
async def serve_index():
    return _index_response()


@app.get("/{full_path:path}")
async def serve_frontend(full_path: str):
    file_path = _safe_static_file(full_path)
    if file_path:
        return FileResponse(file_path)

    head = full_path.replace("\\", "/").lstrip("/").split("/", 1)[0]
    if head in API_PREFIXES:
        raise HTTPException(status_code=404, detail="Not Found")

    return _index_response()
