# 偶遇导航测试方案

> 本文件用于统一后端、前端、演示与回归验证。先跑自动化，再做 3 组大连场景手动验证。

## 文档索引

- 开发计划：`docs/superpowers/plans/2026-08-25-serendipity-navigation.md`
- 团队分工：`docs/superpowers/specs/team.md`
- 演示脚本：`docs/superpowers/specs/demo-scenarios.md`
- 阻塞跟踪：`docs/superpowers/specs/blockers.md`

## 当前验证状态（2026-08-25）

- 后端单测：`python -m pytest` 已通过。
- 前端构建：`npm run build` 已通过。
- 前端单测：`npx vitest run` 已通过。
- 接口连通：`GET /health` 返回 `200 ok`。

## 一、自动化测试

### 后端

```bash
cd backend
python -m pytest
```

### 前端

```bash
cd webapp
npm test
```

### 验收标准

- 后端单测通过。
- 前端构建成功。
- 前端单测全绿。

## 二、接口冒烟测试

### 环境启动

```bash
# 后端
cd backend
uvicorn app.main:app --reload

# 前端
cd webapp
npm run dev
```

### 健康检查

```bash
curl http://localhost:8000/health
```

### 推荐接口

```bash
curl -X POST http://localhost:8000/api/route/recommend \
  -H "Content-Type: application/json" \
  -d '{"origin":"121.6068,38.9180","destination":"121.5854,38.9325","mode":"+15"}'
```

### 验收标准

- `/health` 返回 `{"status":"ok"}`。
- `/api/route/recommend` 在正确参数下返回 JSON，且包含 `baseline_minutes`、`detour_minutes`、`score`、`pois`、`narrative`、`route`。
- 无参数或非法参数时前端可展示错误提示，服务端返回合理状态码。

## 三、手动演示验证（3 组大连场景）

### 场景 1

- 模式：`+15`
- 场景：大连理工大学 -> 星海广场
- 验收：能看到结果页、额外时间、探索叙事和至少 1 个 POI。

### 场景 2

- 模式：`roam`
- 场景：东港 -> 老虎滩
- 验收：探索评分更高，结果页展示更明显的“漫游/探索”叙事。

### 场景 3

- 模式：`+5`
- 场景：西安路 -> 傅家庄
- 验收：轻微绕行，仍可展示更短的额外时间与候选亮点。

## 四、异常态验证

### 无高德 Key

- 预期：仍能展示内置演示结果，不白屏。

### 无 LLM Key

- 预期：仍能展示 fallback 叙事，不阻塞主流程。

### 网络异常 / 后端异常

- 预期：前端显示 Error 态，可重试或切换离线展示。

### 空结果

- 预期：前端显示空结果提示，不展示空白地图。

## 五、回归检查清单

- 本地重新 `npm run build`。
- 本地重新 `python -m pytest`。
- 演示前重新跑 3 组场景。
- 确认 README 可复现启动步骤。
- 确认 `docs/superpowers` 已同步最新进展。

## 六、测试分工

- 成员 A：负责前端单测、页面交互验证、地图渲染检查。
- 成员 B：负责后端单测、接口测试、异常降级验证。
- 成员 C：负责测试清单维护、演示场景复现、现场问题记录。
