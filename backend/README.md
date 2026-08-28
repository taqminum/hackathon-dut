# Backend

FastAPI 后端目录。

## 当前实现

- 已实现健康检查：`GET /health`
- 已实现推荐接口：`POST /api/route/recommend`
- 地名使用 OpenStreetMap Nominatim 解析，前端地图使用 Leaflet + OpenStreetMap。
- 无需高德 Key；未配置时使用内置场景和本地路线估算，方便直接演示。
- `AMAP_KEY` 仅保留为可选兼容配置，默认流程不会调用高德接口。

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
