# Backend

FastAPI 后端目录。

## 当前实现

- 已实现健康检查：`GET /health`
- 已实现推荐接口：`POST /api/route/recommend`
- 配置 `AMAP_KEY` 后，地名检索、步行路线和沿途 POI 均调用高德 Web 服务；前端地图使用 Leaflet + OpenStreetMap 展示。
- 未配置 `AMAP_KEY` 或高德请求失败时，降级使用内置大连演示场景与本地路线估算，方便直接演示。

## 快速开始

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --env-file .env
```

先把 `backend/.env` 里的 `AMAP_KEY` 填上，再启动后端。

## 测试

```bash
cd backend
python -m pytest
```

## 已知待确认项

- 高德 API Key 由谁保管与配置。
- LLM 现场是否提供，Key / 地址由谁配置。
