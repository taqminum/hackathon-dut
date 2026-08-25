# Serendipity Navigation（偶遇导航）完整开发方案

> 先做可演示的网页版；后续再尝试打包为 App 壳。核心体验是“可控的意外”。
> iOS 暂不推进；起终点暂不支持地图选点，可作为后续补充。

## 当前进展

- 后端已实现 `/health` 与 `/api/route/recommend`；无高德 Key 时使用内置演示数据。
- 前端已实现首页、模式切换、结果页、地图展示、Loading / Error / 空结果提示。
- 前端构建与单测已通过。
- 已准备 3 组大连演示场景。

## 文档索引

- 开发方案：`docs/superpowers/plans/2026-08-25-serendipity-navigation.md`
- 团队分工：`docs/superpowers/specs/team.md`
- 测试方案：`docs/superpowers/specs/testing.md`
- 演示脚本：`docs/superpowers/specs/demo-scenarios.md`
- 阻塞跟踪：`docs/superpowers/specs/blockers.md`
- 当前进展：`docs/superpowers/status/2026-08-25.md`

## 项目目标与成功标准

### 目标
- 用户可以输入起点、终点、探索模式。
- 系统在可接受绕行成本内，推荐更有探索价值的路线。
- 路线不只是“最快到达”，还要有推荐叙事和沿途可探索点。

### Hackathon 成功标准
- 可输入 A->B 并生成推荐结果。
- 详情页能展示额外时间、探索叙事、POI 列表。
- 网络/API 异常时有降级展示，不直接崩溃。
- 至少可演示 3 个大连本地场景。
- 网页版现场可用；后续可尝试打包为 App 壳。

### MVP 不做
- 不做账号、支付、社交分享。
- 不做长期云端用户记忆体系。
- 不做全国深度 POI 运营。

## 产品与边界

- 路线目标：不是纯最短路径，而是“可解释的轻微绕行”。
- 探索程度：提供 `+5`、`+15`、`roam` 等模式。
- 输入约束：起终点暂不支持地图选点，优先保证文本框可用。
- 输出约束：优先展示额外时间、探索叙事、POI 和路线。
- 降级要求：高德/LLM 异常时仍可演示，不阻塞主流程。

## 三路分工

### 成员 A：前端负责人
- `webapp/src/views/HomeView.vue`：输入页与提交逻辑
- `webapp/src/views/ResultView.vue`：结果页与状态展示
- `webapp/src/components/ExploreModeSelector.vue`：模式切换
- `webapp/src/components/MapView.vue`：地图渲染与路线展示
- `webapp/src/api.js`：接口封装
- 前端测试、异常态、空结果、加载态

### 成员 B：后端负责人
- `backend/app/main.py`：服务入口与 CORS
- `backend/app/routes/api.py`：推荐接口
- `backend/app/services/route_engine.py`：候选路线生成
- `backend/app/services/detour_calculator.py`：额外时间计算
- `backend/app/services/poi_explorer.py`：POI 搜索
- `backend/app/services/scorer.py`：规则打分
- `backend/app/services/narrative.py`：叙事生成与降级
- 后端单测、接口测试、异常测试

### 成员 C：项目/演示/文档负责人
- `docs/superpowers/plans/2026-08-25-serendipity-navigation.md`：计划维护
- `docs/superpowers/specs/team.md`：分工与规则
- `docs/superpowers/specs/testing.md`：测试方案
- `README.md`、`backend/README.md`、`webapp/README.md`：运行说明
- 演示脚本、场景数据、备用方案、现场问题记录

## 技术选型

- 网页版主方案：Vue 3 + Vite + Leaflet + FastAPI
- 地图：OpenStreetMap / Leaflet 作为当前可运行基础；高德地图 JS API 作为后续接入选项
- 后端：FastAPI + Uvicorn
- AI：规则打分 + OpenAI 兼容 LLM 叙事 + 失败降级
- App 壳：Android 优先，后续按需要尝试 WebView 壳；iOS 暂不推进

## 接口设计

- `GET /health`：服务健康检查
- `POST /api/route/recommend`：推荐接口，参数为 `origin`、`destination`、`mode`

返回字段：
- `baseline_minutes`
- `detour_minutes`
- `score`
- `pois`
- `narrative`
- `route`

## 测试流程

### 后端测试
- 服务健康检查
- 推荐接口返回字段
- 候选路线与兜底数据
- 绕行时间计算
- POI 搜索与过滤
- 打分逻辑
- LLM 成功与失败降级

### 前端测试
- 首页可渲染
- 模式切换
- 网络异常提示
- 结果页展示关键信息
- 空结果提示

### 手动验证
- 输入大连本地 A->B 可生成结果
- 切换探索模式时有反馈
- 断网或 API 失败有降级展示
- 地图与路线可正常渲染

### 演示场景验证
- 大连理工大学 -> 星海广场（`+15`）
- 东港 -> 老虎滩（`roam`）
- 西安路 -> 傅家庄（`+5`）

## 待确认项

### 需要尽快确认
- 高德 API Key 由谁保管和配置。
- LLM 现场是否提供，若提供由谁配置 Key。
- Android App 壳打包方式：更倾向 Tauri 壳，还是简单的 WebView APK / PWABuilder。
- 演示网络环境，是否需要准备离线演示数据。

### 暂时接受不确定性
- 开发者环境不一致：先保证至少 1 台机器可完整启动前后端并演示。
- 安装说明不统一：有手册就直接参照安装，无手册就按 Python 3.11 + Node 18/20 继续推进。
