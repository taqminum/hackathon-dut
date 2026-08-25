# Serendipity Navigation（偶遇导航）完整开发方案

> 目标：先做可演示的网页版，再尝试打包成 App；核心体验是“可控的意外”。
>
> 城市：大连
> 文档路径：`docs/superpowers/plans/2026-08-25-serendipity-navigation.md`

---

## 一、项目目标与成功标准

### 1.1 目标
- 用户可以输入起点、终点、探索模式。
- 系统在可接受绕行成本内，推荐更有探索价值的路线。
- 路线不只是“最快到达”，还要有推荐叙事和沿途可探索点。

### 1.2 Hackathon 成功标准
- 可输入 A->B 并生成推荐结果。
- 详情页能展示额外时间、探索叙事、POI 列表。
- 网络/API 异常时有降级展示，不直接崩溃。
- 至少可演示 3 个大连本地场景。
- 网页版现场可用；后续可尝试打包为 App 壳。

### 1.3 MVP 不做
- 不做账号、支付、社交分享。
- 不做长期云端用户记忆体系。
- 不做全国深度 POI 运营。

---

## 二、技术选型

### 2.1 网页版主方案
- 前端：HTML + Tailwind CSS + Vue 3 + Vite
- 地图：高德地图 JS API
- 后端：FastAPI + Uvicorn
- AI：规则打分 + OpenAI 兼容 LLM 叙事 + 失败降级

### 2.2 App 壳方案
- Android：Capacitor / Cordova WebView 壳
- iOS：Capacitor 壳，视现场设备与账号情况再确认是否真机上架
- 路线：优先 APK；IPA 作为“能装就装”的后续选项

### 2.3 推荐原因
- 网页版开发最快、现场最稳、调试最方便。
- App 壳只做“包装展示”，不重写功能，风险最低。
- 适合 Hackathon 的“先演示、再补形态”节奏。

---

## 三、系统架构

```
用户输入（起点/终点/模式）
      ↓
Vue 3 网页
      ↓
FastAPI 后端
      ↓
  ├─> 高德 Web 服务 API（路线/POI/地理编码）
  ├─> 规则引擎（绕行成本 + 探索价值）
  └─> LLM（叙事生成，可选 + 降级）
      ↓
返回推荐结果
      ↓
地图展示 + 路线详情
      ↓
可选：Capacitor 包装为 App
```

---

## 四、模块设计

### 4.1 前端模块
- `HomeView`：输入起点、终点、探索模式
- `ResultView`：展示推荐路线、额外时间、叙事、POI
- `MapView`：加载高德地图、绘制路线与标注
- `ApiService`：封装 `/api/route/recommend` 调用
- `ErrorView/LoadingView`：异常态与加载态

### 4.2 后端模块
- `main.py`：FastAPI 入口、CORS、健康检查
- `api.py`：推荐接口
- `route_engine.py`：高德路径规划候选路线
- `detour_calculator.py`：额外时间计算
- `poi_explorer.py`：沿途 POI 搜索
- `scorer.py`：规则打分
- `narrative.py`：LLM 叙事 + 降级文案

### 4.3 数据流
用户输入 -> 前端 -> 后端 -> 高德 API -> 候选路线 -> 沿途 POI -> 规则打分 -> LLM 叙事 -> 返回推荐 -> 前端地图展示

---

## 五、详细测试方案

### 5.1 测试分层
- 后端单元测试
- 后端接口测试
- 前端单元测试
- 前端组件测试
- 手动端到端演示测试
- App 壳安装测试

### 5.2 后端测试用例

#### 用例 1：服务健康检查
- 输入：访问 `/health`
- 预期：返回 `{"status":"ok"}`

#### 用例 2：候选路线解析正确
- 输入：固定起终点
- 预期：返回列表且包含 `distance`、`duration` 等关键字段

#### 用例 3：绕行时间计算正确
- 输入：baseline=600，candidate=900
- 预期：额外时间为 300 秒，且不小于 0

#### 用例 4：POI 搜索与过滤
- 输入：固定位置、类型、半径
- 预期：返回 POI 名称、类型、距离等，类型在范围内

#### 用例 5：打分逻辑稳定
- 输入：不同 detour、tags、quality
- 预期：可比较分数，无 NaN、无异常崩溃

#### 用例 6：LLM 成功与失败降级
- 输入：正常调用 LLM
- 预期：返回叙事
- 异常输入：超时或 key 缺失
- 预期：返回降级文案，不抛 500

#### 用例 7：推荐接口返回完整字段
- 输入：前端请求参数
- 预期：返回 `baseline_minutes`、`detour_minutes`、`score`、`pois`、`narrative`

### 5.3 前端测试用例

#### 用例 1：主页可渲染
- 输入：访问首页
- 预期：起终点输入框、模式按钮可见

#### 用例 2：模式切换正常
- 输入：点击 +5 / +15 / 漫游
- 预期：选中状态或请求参数正确变化

#### 用例 3：网络异常提示
- 输入：Mock 接口返回失败
- 预期：页面显示错误提示，不白屏

#### 用例 4：结果页展示关键信息
- 输入：接口返回推荐结果
- 预期：能看到推荐叙事、额外时间、POI 列表

### 5.4 手动演示测试清单
- 大连本地 A->B 可生成结果
- 切换探索模式时有反馈
- 断网或 API 失败有降级展示
- 地图与路线可正常渲染
- App 壳可打开网页并展示完整页面

### 5.5 App 壳测试用例
- 输入：安装 APK
- 预期：可打开 App、进入首页
- 输入：App 内网络访问
- 预期：可访问后端接口并展示结果
- 异常：后端未开
- 预期：App 显示错误提示，不闪退

---

## 六、开发与验证节奏

### 6.1 阶段划分

#### 阶段 1：后端骨架 + 高德基础调用
- 完成 FastAPI 健康检查
- 完成路线候选与 POI 基础查询
- 完成后端测试用例 1~4

#### 阶段 2：推荐逻辑与叙事
- 完成绕行计算、规则打分、LLM 叙事与降级
- 完成后端测试用例 5~7
- 至少 1 条推荐接口可跑通

#### 阶段 3：Vue 网页版基础流程
- 完成首页、模式选择、结果页、地图展示
- 完成前端测试用例 1~4
- 前后端联调可跑通

#### 阶段 4：演示收尾 + App 壳
- 补充加载态、错误态、降级文案
- 3 组大连场景验证
- 尝试打包 Android App 壳并安装测试

---

## 七、接口设计

### 7.1 推荐接口
- 路径：`POST /api/route/recommend`
- 请求字段：
  - `origin`: string
  - `destination`: string
  - `mode`: string
- 返回字段：
  - `baseline_minutes`: number
  - `detour_minutes`: number
  - `score`: number
  - `pois`: array
  - `narrative`: string

### 7.2 健康检查
- 路径：`GET /health`
- 返回：`{"status":"ok"}`

---

## 八、容错与降级

### 8.1 高德 API
- 失败时返回兜底路线或友好提示
- 前端展示“暂时无法规划路线”

### 8.2 LLM
- 超时或 key 缺失时返回静态模板
- 不阻塞推荐主流程

### 8.3 网络
- 客户端显示“网络不佳，请稍后重试”
- 演示时可保留最近一次成功结果

---

## 九、网页版目录结构建议

```
G:\hackathon-dut\
├── backend\
│   ├── app\
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── models\
│   │   │   └── preference.py
│   │   ├── services\
│   │   │   ├── route_engine.py
│   │   │   ├── detour_calculator.py
│   │   │   ├── poi_explorer.py
│   │   │   ├── scorer.py
│   │   │   └── narrative.py
│   │   └── routes\
│   │       └── api.py
│   ├── tests\
│   │   ├── __init__.py
│   │   ├── conftest.py
│   │   ├── test_main.py
│   │   ├── test_route_engine.py
│   │   ├── test_detour_calculator.py
│   │   ├── test_poi_explorer.py
│   │   ├── test_scorer.py
│   │   └── test_narrative.py
│   └── requirements.txt
└── webapp\
    ├── index.html
    ├── package.json
    ├── vite.config.js
    ├── src\
    │   ├── main.js
    │   ├── App.vue
    │   ├── api.js
    │   ├── views\
    │   │   ├── HomeView.vue
    │   │   └── ResultView.vue
    │   ├── components\
    │   │   └── ExploreModeSelector.vue
    │   └── utils\
    │       └── map-loader.js
    └── tests\
        ├── api.test.js
        └── App.test.js
```

---

## 十、网页版核心页面设计

### 10.1 首页
- 起点输入框
- 终点输入框
- 探索模式选择：+5 / +15 / 漫游
- “生成偶遇路线”按钮
- 加载态与错误提示

### 10.2 结果页
- 地图区域：展示路线与沿途 POI
- 推荐叙事
- 额外时间、探索价值
- POI 列表
- 返回首页

### 10.3 交互要求
- 中文文案，风格偏向“探索叙事”
- 空结果提示
- 异常结果提示
- 移动端浏览器可正常使用

---

## 十一、App 壳方案

### 11.1 Android
- 用 Capacitor 包装网页版
- 生成 APK
- 保留网页全部能力，只加原生壳

### 11.2 iOS
- 同样使用 Capacitor
- 受设备/证书限制，优先保证 Android APK
- iOS 作为“若现场可行则展示”

### 11.3 App 壳测试重点
- 能否正常打开首页
- 网络请求是否可用
- 地图与结果页是否正常渲染
- 异常态是否正常提示

---

## 十二、关键测试命令

### 后端
```bash
cd backend
python -m pytest tests/test_main.py -v
python -m pytest tests/test_route_engine.py -v
python -m pytest tests/test_detour_calculator.py -v
python -m pytest tests/test_poi_explorer.py -v
python -m pytest tests/test_scorer.py -v
python -m pytest tests/test_narrative.py -v
python -m pytest -v
```

### 前端
```bash
cd webapp
npm install
npm run dev
npm run test
```

### App 壳
```bash
# 初始化示例
npm init -y
npm install @capacitor/core @capacitor/cli
npm install -D @capacitor/android @capacitor/ios
npx cap init SerendipityNavigation com.example.serendipity SerendipityNavigation
npx cap add android
npx cap add ios

# 构建后同步
npm run build
npx cap sync
npx cap open android
```

---

## 十三、执行顺序建议

### 任务 1：后端骨架与健康检查
- 创建 FastAPI 项目
- 实现 `/health`
- 完成健康检查用例

### 任务 2：路线与绕行计算
- 接入高德路径规划
- 实现候选路线解析
- 完成绕行计算与测试

### 任务 3：POI 搜索
- 接入高德 POI
- 实现类型/距离过滤
- 完成 POI 测试

### 任务 4：规则打分与叙事
- 实现打分逻辑
- 实现 LLM 叙事与降级
- 完成后端核心测试

### 任务 5：Vue 基础页面与 API 联调
- 搭建 Vite + Vue 项目
- 实现首页、结果页、模式选择
- 完成后端/前端联调

### 任务 6：地图展示与错误处理
- 接入高德地图 JS API
- 绘制路线与 POI
- 增加加载态与错误态

### 任务 7：演示验证
- 大连本地 3 组场景验证
- 断网/API 异常验证
- 录制演示

### 任务 8：App 壳尝试
- 用 Capacitor 包装网页版
- 尝试构建 Android APK
- 做 App 壳基础安装与展示测试

---

## 十四、测试检查清单

### 后端
- [ ] `/health` 正常
- [ ] 路线查询返回格式正确
- [ ] 绕行时间计算正确
- [ ] POI 搜索可过滤
- [ ] 打分逻辑稳定
- [ ] LLM 失败有降级
- [ ] `/api/route/recommend` 返回完整字段

### 前端
- [ ] 首页可输入并提交
- [ ] 模式切换正常
- [ ] 结果页可展示推荐内容
- [ ] 地图可加载
- [ ] 错误态与加载态正常
- [ ] 断网可降级

### App 壳
- [ ] APK 可安装
- [ ] 首页可打开
- [ ] 结果页可展示
- [ ] 异常情况不闪退

---

## 十五、已知假设

- 高德地图 API key 可用。
- LLM API key 可选；没有就使用降级文案。
- 演示环境可联网，优先保证网页版可演示。
- App 壳优先保证 Android；iOS 视现场情况尝试。

---

## 十六、已确认的实施限制

- 本阶段**暂不考虑 iOS**。
- 起终点输入**暂不支持地图选点**，可作为后续补充。
- **开发者打包环境尚未确认**，因此 App 壳仅作为后续尝试项；网页版仍是当前主要交付物。

> 如需，我会继续把以上限制转化为更保守的实现计划，例如把 Capacitor 相关步骤改为“条件执行”。
