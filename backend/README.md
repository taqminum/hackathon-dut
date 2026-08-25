# Backend

FastAPI 后端目录。

## 当前实现

- 已实现健康检查：`GET /health`
- 已实现推荐接口：`POST /api/route/recommend`
- 无高德 Key 时使用内置演示数据，方便本地直接演示。

## 快速开始

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## 测试

```bash
cd backend
python -m pytest
```

## 已知待确认项

- 高德 API Key 由谁保管与配置。
- LLM 现场是否提供，Key / 地址由谁配置。
