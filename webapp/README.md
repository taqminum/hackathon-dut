# WebApp

网页端目录。Vue 3 + Vite + Leaflet，采用包豪斯风格设计（三原色、硬边、粗描边、实心投影）。

## 快速开始

```bash
cd webapp
npm install
npm run dev          # http://localhost:5173
```

开发时 `/api` 与 `/health` 都会代理到 `http://localhost:8000`。
后端未启动也能打开页面，顶栏会显示“后端未连接”。

## 构建

```bash
npm run build        # 输出到 dist/，由后端同源托管
npm run preview      # 预览构建产物（同样代理 /api 与 /health）
```

## 测试

```bash
npm run test:run     # 单元测试 / 组件测试（vitest）
```

浏览器级验证只连接真实后端：先启动 `backend` 的 Uvicorn 和 `npm run dev`，再运行
`npm run audit:design -- http://localhost:5173`。没有高德 Key 或真实后端不可用时，
不以假数据替代。

## 目录结构

```
src/
  api.js                 接口封装与降级
  constants.js           探索模式、演示场景、常用地点
  composables/useApi.js  api 注入（便于测试替换）
  assets/tokens.css      设计令牌（颜色、间距、字号、投影）
  assets/main.css        全局样式与通用类（.bh-*）
  components/            展示组件
  views/                 首页与结果页
  utils/                 坐标、格式化、历史记录
tests/
  *.test.js              vitest 用例
  design-audit.mjs       设计与可访问性审计
```

## 接口约定

已由后端实现：

- `GET /health` → `{ status }`
- `POST /api/route/recommend`，参数 `origin`、`destination`、`mode`（`+5` / `+15` / `roam`），
  返回 `baseline_minutes`、`detour_minutes`、`score`、`pois`、`narrative`、`route`。
  起终点支持 `经度,纬度` 字符串或地名，坐标形式与后端演示数据匹配度最好。

以下接口后端尚未定稿，前端已按使用意图写好请求，拿不到响应时静默降级，不阻塞主流程：

| 接口 | 用途 | 降级行为 |
| --- | --- | --- |
| `GET /api/place/suggest?keyword=&city=` | 地点联想 | 退化为本地常用地点过滤 |
| `GET /api/poi/:id` | POI 详情 | 只展示列表已有字段 |
| `POST /api/trip/save` | 收藏路线 | 提示收藏失败，可重试 |
| `GET /api/trip/list` | 收藏列表 | 视为空列表 |
| `POST /api/feedback` | 路线反馈 | 静默忽略 |

接口地址可用 `VITE_API_BASE` 覆盖，默认 `/api`。

## 已覆盖的状态

- 加载态：提交后显示骨架条与说明文案。
- 错误态：透传后端 `detail` 文案，网络异常显示统一提示。
- 空结果：`route` 缺失、`pois` 为空时分别有对应提示与下一步操作。
- 演示数据：后端未配置高德 Key 时，结果页顶部标注“内置演示数据”。
- 地图降级：Leaflet 初始化失败时显示提示，不影响其余信息展示。
