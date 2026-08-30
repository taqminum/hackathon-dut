# Backend

FastAPI 后端目录。

## 当前实现

- 已实现健康检查：`GET /health`
- 已实现推荐接口：`POST /api/route/recommend`
- 地点联想、POI、步行路线使用高德 Web 服务真实数据，地名解析以高德为主并保留
  Nominatim 作为解析补充；前端底图使用 Leaflet + OpenStreetMap。
- 正式推荐必须配置 `AMAP_KEY`。未配置或高德调用失败时返回明确错误，不返回估算路线。
- 支持一次真实途经 1、2 或 3 个地点，多点路线由若干段高德步行结果拼接。

## 快速开始

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env             # 填入 AMAP_KEY
uvicorn app.main:app --reload
```

## 测试

```bash
cd backend
python -m pytest
```

真实全链路测试（会调用高德并消耗配额）：

```bash
RUN_LIVE_AMAP=1 AMAP_KEY=你的Key python -m pytest -q tests/test_amap_live.py
```

LLM 只用于可选的叙事润色；不配置时推荐理由仍由高德真实字段生成。
