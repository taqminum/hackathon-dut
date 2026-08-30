# 交给干活 AI 的提示词（演示前最后一轮，全部完成）

> 用法：把下面「提示词正文」整段发给干活的 AI。附录是审查人的实测证据，
> 干活的 AI 可以读，但不要求它复述。

---

## 提示词正文（从这里开始整段复制）

你在完成大连「偶遇导航」黑客松项目的**最后一轮打磨**。截止时间临近，这一轮之后
就是验收，所以**所有任务必须一次性全部完成**，不要留「后续再说」。

### 环境与红线（先读，违反会导致返工或会话中断）

- 后端测试必须用虚拟环境，且必须在 `backend` 目录下跑：
  `cd backend` 然后 `.\.venv\Scripts\python.exe -m pytest -q`
  （从仓库根目录跑是 `no tests ran`，exit 5；系统 python 没装依赖）
- 前端在 Node 22 下：`cd webapp` 然后 `npm run test:run`
- **`npm run smoke` 和 `npm run audit:design` 不会自己起后端**，必须先另开一个
  终端跑 `node tests/mock-server.mjs 8000`，否则两个都卡在 `.result__title` 超时
- **永远不要跑 `nvm use`** —— 它改全局符号链接，claude 只装在 Node 20 下，会终止会话
- **永远不要打 `/api/route/recommend` 的真实 HTTP 接口**。`AMAP_KEY` 从
  `backend/.env` 读，`TestClient` 会真的调付费高德（返回 `source=amap`），
  shell 里设 `AMAP_KEY=` 覆盖不掉。要看兜底数据就在进程内直接调
  `_build_fallback_route(origin, destination, mode, waypoint)`
- 不要动 `backend/.env`。不要提交，不要推送，改完等人 review
- `mode` 只接受 `+5` / `+15` / `roam`，传 `walking` 是 422

### 当前基线（改之前先跑一遍确认对得上，对不上先说）

| 套件 | 命令 | 基线 |
|---|---|---|
| 后端 | `cd backend; .\.venv\Scripts\python.exe -m pytest -q` | 196 passed，约 10.8s |
| 前端单测 | `npm run test:run` | 85 passed (10 files) |
| smoke | `node tests/mock-server.mjs 8000` + `npm run smoke` | 46/46 |
| 设计审计 | 同上起 mock + `npm run audit:design` | 39/39 |
| 构建 | `npm run build` | 约 1.6s，`index-b0EyiSKI.js` + `index-C7Xh2Keh.css` |

**完成后这四套必须全绿，且计数只增不减。** 任何一条变红都算没做完。

### 工作纪律

1. **每一项都要自己看屏幕**，不要只看断言。这个项目已经出过两次「断言全绿、
   屏幕上是错的」：一次是灰虚线被压在路线底下看不见，一次是 mock 数据比真实
   数据漂亮所以掩盖了真后端的输出。截图验证是硬要求。
2. **mock 数据不等于真实数据**。`tests/mock-server.mjs` 手写了漂亮的 4 段路名，
   而真后端兜底只返回 1 段带经纬度的 step。**每改完一处，必须同时用两种数据源
   看一遍**：mock（`node tests/mock-server.mjs 8000`）和真后端兜底（在进程内调
   `_build_fallback_route` 造一个响应喂给前端，或者直接起 uvicorn 但只点演示按钮
   走兜底路径 —— 注意不要触发付费调用）。
3. 改完每一项都要**加断言钉住它**，否则下一轮会退化。已经出过一次「计划标了
   已完成、代码从没实现、没有测试拦」（见 T7）。
4. 涉及「两个图形叠在一起」的改动，断言要钉**相对顺序**而不只是存在性。
5. 临时脚本和截图用完删掉，不要留在工作区。

---

## 任务清单（T1–T9，全部要做完）

按下面顺序做。T1–T4 是验收人明确点出来的，优先级最高。

### T1 【最高】起点终点显示成经纬度，不是地名

**现象**：点「快速体验」进结果页，标题是
`121.5197,38.8856 → 121.5839,38.8816`。沿途亮点卡片下面也印着
`121.5432,38.8871` 这样的裸坐标。首页历史记录 `history__pair` 同样是坐标。

**根因**（已定位，不用再查）：
- `webapp/src/constants.js:46` 的 `DEMO_SCENARIOS` **有** `originLabel` /
  `destinationLabel`（`大连理工大学` / `星海广场`），但 `HomeView.vue` 的
  `applyScenario()`（约 98 行）只把 `scenario.origin` / `scenario.destination`
  这两个坐标传给 `fillDemo()`，**标签被丢掉了**
- `HomeView.vue:70` 组装的 `payload` 只有 `{origin, destination, mode}`，
  `emit('select', {...result, request: payload})` 所以 `request` 里只有坐标
- `ResultView.vue:116,118` 直接渲染 `request?.origin || route?.origin`

**要做的**：
1. 让 `payload` 带上人类可读的标签（建议加 `originLabel` / `destinationLabel`
   两个字段，**不要**改 `origin` / `destination` 的值 —— 它们是发给后端的坐标，
   改了会破坏坐标不变量和 smoke）
2. 手输入时：如果用户输入的是地名（非坐标），标签就是用户输的原文；如果输入的
   是坐标，标签为空
3. `PlaceInput` 从 `DALIAN_LANDMARKS` 或 `/api/place/suggest` 选中某项时，
   把该项的 `name` 作为标签带出（现在 `choose()` 只回填 `location`）
4. `ResultView` 标题优先显示标签，没有标签才退回坐标：
   `originLabel || request?.origin || route?.origin || '起点'`
5. 首页历史记录同样优先显示标签（`history` 存的对象要一起带上标签）
6. 沿途亮点卡片底部那行裸坐标（`_result` 截图里 POI 卡片下方的
   `121.5432,38.8871`）：改成不显示，或显示成「距路线约 180 米」这类人能读的
   信息 —— 那个位置对用户没有任何意义

**断言**：新增前端测试钉住「点演示按钮后标题出现 `大连理工大学` 且不出现
`121.5197`」；smoke 里加一条同样的断言。

### T2 【最高】地图和路线是"死"的，前后端没配合好

**现象**：验收人的原话是「地图和路线是死的」。我实测到的具体问题：

1. **首屏地图瓦片可能来不及加载**就被看到（我第一张截图里地图是空白灰底，
   只有路线，第二张才有瓦片）。演示时如果网络慢，评委看到的就是空白灰块。
   → 加载中要有明确的占位/骨架状态，不要露出空白灰底；瓦片加载失败要有兜底提示
   （`MapView.vue` 已经有 `failed` ref，确认它真的会在瓦片 404 时置位并显示）
2. **地图不可交互的观感**：确认拖动/缩放正常工作，且 `fitBounds` 之后用户手动
   缩放不会被下一次 watch 重置回去（现在 `watch` 是 `deep: true` 且监听
   `props.pois`，反馈或高亮 POI 时可能触发重新 `fitBounds`，把用户的视野拽回去）
3. **点击沿途亮点卡片**应该在地图上高亮对应标记并平移过去（`activePoiIndex`
   这条链路已存在，`@poi-click="focusPoi"`），实测确认它真的有视觉反馈；
   没有的话补上（标记放大/换色/弹 popup 任一种）
4. **「后端已连接」那个状态灯**（右上角）要真的反映健康检查结果，而不是写死的。
   确认它在后端挂掉时变成断开状态

**断言**：加 smoke 断言「地图瓦片容器有 img 且数量 > 0」、「点第一个 POI 卡片后
该卡片进入 active 态」。

### T3 【最高】原路线 / 现路线的区别要说清楚

**现象**：验收人说「你路线要显示出区别啊，原路线怎么样的现有路线怎么样的」。

现在图上有两条线（蓝实线 = 推荐、黑白虚线 = 原本路线，图例也有），
**但图上没有任何文字说明这两条线各是多少距离、多少时间、差在哪**。指标卡片
只给了「基准时长 21 分钟 / 额外时间 +10 分钟 / 总计 31 分钟 / 全程距离 2.6 公里」——
「全程距离」是谁的距离？基准的还是推荐的？看不出来。

**要做的**：
1. 后端 `baseline_route` 已经带 `distance` / `duration`（P3-4 已落地），
   前端要把**两条线的距离和时长并排显示**，形成明确对比。建议做成一个对比块：
   ```
   原本路线   6.9 公里 · 21 分钟
   推荐路线   7.4 公里 · 31 分钟   (+0.5 公里 · +10 分钟)
   ```
2. 「全程距离」这张卡要写清楚是推荐路线的距离（label 加限定词）
3. 图例的两个色块要和地图上的实际样式一致（现在虚线是深色描边 + 浅色芯两笔，
   图例已同步，确认改完还是一致的）
4. **注意**：兜底数据里两条线的岔开幅度本来就很小（7 公里全程最远分离
   89~523 米，基准是推荐的严格子序列）。**不要为了图好看去改演示数据的绕行幅度** ——
   那是产品决定。用文字和数字把区别讲清楚就够了

**断言**：前端测试钉住「同时渲染出基准和推荐两组距离/时长」、「基准与推荐相同时
不显示对比块」；smoke 加一条断言页面上同时出现两条线的距离数字。

### T4 【最高】「为什么推荐这条」那个框没写好

**现象**：那个框现在只有一句叙事（`从大工沿海边走，你会先遇到一间社区咖啡，
再顺着海景走到星海。`）加一个 `+15` 徽章。**它没有回答"为什么"** —— 没说
为什么是这条而不是别的，也没说评分是怎么来的。

**要做的**：
1. 把推荐**理由结构化**地说出来。后端已有的材料：`score`（探索评分）、
   `detour_minutes`（绕行代价）、`pois`（选中的亮点及其 `type`/`rating`/距离）、
   `baseline_minutes`。用这些拼出一段有依据的解释，例如：
   ```
   为什么推荐这条
   · 沿途多了 2 处亮点：理工咖啡小铺（餐饮 4.4）、海边散步道（景点 4.6）
   · 只多花 10 分钟，绕行代价在 +15 模式的预算内
   · 探索评分 7.0 / 7，其中 POI 质量贡献 4.0，标签契合 3.0，绕行扣 0.2
   ```
   评分的分解不必精确到内部实现，但**必须和 `score` 的实际数值自洽**
2. 保留那句叙事文案，放在结构化理由的**下方**作为收尾，不要删
3. 兜底/降级时（`chosen` 为空、`score` 为 0、没有 POI）这个框要说得诚实，
   不要硬凑理由 —— 例如「这次没有找到值得绕行的亮点，给出的是最快路线」

**断言**：前端测试钉住「有 POI 时理由里出现 POI 名称和绕行分钟数」、
「score 为 0 或无 POI 时显示降级文案且不出现虚假理由」。

### T5 探索评分显示成 `7.2/7`，超出自己的满分

**现象**：结果页评分条右上角是 `7.2/7`，评分条填满但数值超过分母。

**根因**：`ScoreMeter.vue:16` 的 `max` 默认 7，与后端 `scorer.py` 的
上界 7.0 一致（`TAG_WEIGHT 3.0 + QUALITY_WEIGHT 4.0`）。
`scoreToPercent`（`format.js:59`）会 clamp 到 100%，所以进度条没爆，
但数字直接显示了原值。**7.2 这个值来自 `tests/mock-server.mjs`**：
第 20 行 `score: 6.4` 加上第 131 行 `base.score + factor * 0.4`，
`+15` 模式 factor=2 → `6.4 + 0.8 = 7.2`。

**要做的**：
1. 改 `mock-server.mjs` 的基准分，使得三个模式加成后都 ≤ 7.0
   （例如 `score: 5.8`，factor 1/2/3 → 6.2 / 6.6 / 7.0）
2. 前端加一层防御：显示的数值也 clamp 到 `max`，即使后端给了越界值也不出现
   `7.2/7` 这种自相矛盾的显示
3. 真后端的 `score` 上界确实是 7.0（`round(chosen["score"], 2)`，
   `scorer.score()` 的三项加起来最大 3.0 + 4.0 = 7.0），所以这是 mock 数据的
   问题，不要去改 `scorer.py` 的权重

**断言**：前端测试钉住「score 给 9 时显示 7.0/7 而不是 9/7」；
后端加一条测试钉住 `scorer.score()` 在任何输入下不超过 7.0。

### T6 断网兜底的「路线指引」只有 1 段，且 `road` 显示经纬度

**现象**（真后端兜底数据下，mock 看不到）：「路线指引」区块显示
```
01  按推荐路线行走
    121.5197,38.8856   7.4 公里   1 小时 37 分钟
```
`road` 字段的位置上印了一串经纬度。

**根因**：`backend/app/services/route_engine.py:318-325`，
`_build_fallback_route` 的 `steps` 是硬编码单元素列表，
`"road": origin` 直接把起点坐标塞进了路名字段。
`RouteSteps.vue:48` 无条件渲染 `step.road`（非空即显示）。

**要做的**：
1. 按 polyline 相邻点生成**分段 steps**：用方位角（`atan2`）推方向词
   （向东北/向南 等）+ 该段距离，拼成「向东北走约 620 米」这类文案。
   `_haversine_meters` 已存在可直接用
2. `road` 字段：**不要再塞坐标**。要么留空（`RouteSteps` 的 `v-if` 会自动隐掉），
   要么填有意义的内容。留空是可接受的
3. 每段的 `distance` / `duration` 按该段实际长度分摊，**总和必须等于**
   路线的 `distance` / `duration`（现在整条路的值是 7440 / 5836）
4. `RouteSteps.vue` 的 `collapsedCount: 4` 折叠交互现在因为只有 1 段永远不出现，
   改完之后确认折叠/展开按钮真的能用

**断言**：后端加测试钉住「兜底路线 steps 数量 > 1」、「每个 step 的 `road`
不是坐标格式（不含逗号分隔的两个浮点数）」、「各段 distance 之和等于总
distance」。前端加一条钉住折叠按钮在 steps > collapsedCount 时出现。

### T7 `optimization-plan.md` 把 P2-6 标成【已完成】但从没实现

T6 就是 P2-6 那个缺口。`docs/superpowers/plans/2026-08-28-optimization-plan.md`
**三处**标了已完成，全是错的：
- 第 30 行汇总表：「已完成（兜底路线现在有多段 steps）」
- 第 359 行小节标题：`#### P2-6 fallback 路线没有任何转向指令 【已完成】`
- 第 543 行排期表：划掉并标已完成

（验证方式：`git log --all -S"向东北"` 和 `-S"_bearing"` 都是空的）

**要做的**：T6 做完之后，这三处的状态才名副其实 —— 确认三处都指向真实实现，
不要只改一处。如果 T6 有任何部分没做完，对应的状态要老实写成未完成。

### T8 自己再扫一遍这几个已知薄弱点

下面几条我看到了但没深挖，你逐条确认并修掉真问题：

1. **降级路径的诚实性**：`api.py:137` 那个 `chosen` 为空的出口返回
   `score: 0, pois: [], detour_minutes: 0`。前端在这种情况下的显示要自洽 ——
   评分条 0 分、没有亮点卡片、理由框说实话（见 T4 第 3 点）、
   地图不画虚线（`baseline_route == route`，`hasBaselineComparison` 已处理）
2. **`/api/place/suggest` 无 Key 时返回 `{"suggestions": []}`**
   （`api.py:472`）。前端 `PlaceInput` 会退化为本地 `DALIAN_LANDMARKS` 过滤 ——
   确认这个退化路径真的能用，并且用户看不出报错
3. **首页手输入地名**（不是坐标、不是从下拉选的）走
   `resolve_location` → 无 Key 时走 Nominatim。确认失败时前端有可读的错误提示，
   不是静默空白
4. **反馈按钮**（「还不错」/「一般」）点完要有明确的视觉确认，
   且确认它真的改变了后续推荐（`trip_id` 闭环已实现）
5. **移动端视口**：smoke 跑两个视口，确认窄屏下指标卡片、对比块、
   图例都不溢出不重叠
6. 控制台不能有 error。改完在两个数据源下各看一遍控制台

### T9 收尾

1. 四套测试全绿，且计数只增不减（196 / 85 / 46 / 39 起步）
2. `npm run build` 重新构建 `dist`，并确认 `dist/index.html` 引用的
   文件名和实际产物一致
3. 临时脚本、截图、日志从工作区清掉（`git status` 干净，只剩预期的改动）
4. **不要提交，不要推送**
5. 报告里写清楚：每一项做了什么、用什么命令验证的、**四套测试的实际数字**、
   哪些地方你截图看过。如果有任何一项没做完，明确说是哪一项和为什么 ——
   不要把没做完的说成做完了

---

## 提示词正文结束

---

# 附录：审查人的实测证据（干活的 AI 可参考，验收人用来对账）

以下每条都是我 2026-08-29 亲手跑出来的，不是读代码推断的。

## A. 起终点显示坐标（T1）

用 playwright 点第一个 `.demo` 后读 DOM：
```
RESULT TITLE : 121.5197,38.8856 → 121.5839,38.8816
```
`constants.js:46` 的 `DEMO_SCENARIOS[0]` 确实有
`originLabel: '大连理工大学'` / `destinationLabel: '星海广场'`，
但 `HomeView.vue` 的 `applyScenario()` 只传了 `scenario.origin` /
`scenario.destination` / `scenario.mode` 三个字段给 `fillDemo()`。
标签在源头就被丢弃了，不是渲染问题。

## B. 评分 7.2/7（T5）

截图显示 `7.2/7`。溯源：
- `ScoreMeter.vue:16` `max: { type: Number, default: 7 }`
- `format.js:59` `scoreToPercent` clamp 到 100，所以条填满但数字越界
- `mock-server.mjs:20` `score: 6.4`，`:131` `base.score + factor * 0.4`，
  `+15` 的 factor 是 2 → 7.2
- 真后端上界是 7.0：`scorer.py` `TAG_WEIGHT 3.0 + QUALITY_WEIGHT 4.0`，
  `api.py:154` `round(chosen["score"], 2)`

所以这是 mock 数据越界 + 前端不设防两个原因叠加。

## C. 兜底 steps 只有 1 段且 road 是坐标（T6）

进程内直调（**没有走 HTTP，没有触发付费高德**）：
```python
from app.services.route_engine import _build_fallback_route
_build_fallback_route('121.5197,38.8856','121.5839,38.8816','+15','121.539956,38.887705')['steps']
# [{"instruction": "按推荐路线行走", "road": "121.5197,38.8856",
#   "distance": "7440", "duration": "5836"}]
```
把这个真实响应喂给前端后截图，「路线指引」区块显示：
```
01  按推荐路线行走
    121.5197,38.8856   7.4 公里   1 小时 37 分钟
```

**为什么 46 条 smoke 断言看不到这个**：`mock-server.mjs` 手写了 4 段带真路名的
steps（我实测 mock 下是
`["沿凌工路向西步行","右转进入中山路","沿海岸线继续前行","到达星海广场"]`，
road 是 `["凌工路","中山路","滨海路","星海广场"]`）。
**mock 数据比真实数据漂亮，所以自动化检查永远看不见这个缺陷。**

## D. P2-6 状态是假的（T7）

```
optimization-plan.md:30  | P2-6 fallback 无转向指令 | 已完成（兜底路线现在有多段 steps） |
optimization-plan.md:359 #### P2-6 fallback 路线没有任何转向指令 【已完成】
optimization-plan.md:543 | ~~7~~ **已完成** | P2-6 fallback 生成分段转向指令 | ...
```
`git log --all -S"向东北" -- backend` → 空
`git log --all -S"_bearing" -- backend` → 空
三组场景实测 `steps=1`。

## E. 两条线的岔开幅度（T3 第 4 点的依据）

进程内调 `_build_fallback_route`，三组场景 × 各 2 个演示 POI 作绕行点，共六组：
- 全部 `base_only=0, rec_only=1` —— **基准是推荐的严格子序列**
- 推荐相对基准的最远偏离：89 / 521 / 513 / 523 / 194 / 488 米（7 公里全程）
- 距离：基准 6920 / 7322 / 7361 米，推荐 7440 / 7942 / 7821 米

这解释了为什么「灰虚线画在 11px 描边底下 = 完全不可见」不是夸张，
也说明「看不出换了路」是兜底数据的既有形状，不是渲染 bug。

## F. 已验证为真的既有工作（不要动，也不要重做）

上一轮的三项指派任务我独立复核过，全部为真：
- 四个坐标过期文件已修，`mock-server.mjs` 的 key 已对齐
- `dist` 已重建且**可复现**（我重建后 JS/CSS/HTML 三个文件 `cmp` 逐字节相同）
- P3-4 后端两个出口（`api.py:147` 和 `api.py:163`）都带了 `baseline_route`
- 灰虚线叠放顺序缺陷已修，改坏验证通过（还原成旧顺序 → `2 failed | 83 passed`，
  按字节恢复后 85 passed）

上一轮那个「断言全绿但图上看不见」的发现是对的，`MapView.test.js` 原来那条
「基准必须先加」的断言确实把 bug 锁住了。**这一轮不要退回旧顺序。**

## G. mock-server key 的回归代价

改坏 `mock-server.mjs` 的场景 key 后实测：每个视口挂 **7** 条断言
（叙事文案、亮点卡片、演示数据提示、起终点与 POI 标记、虚线两笔、
虚线盖在上面、图例「原本路线」），两个视口共 14 条 FAIL，`ok` 从 46 掉到 32。
**任何改 `constants.js` 演示坐标的动作都必须同步这个文件。**

## H. 按字节还原的正确写法（改坏验证时用）

用**绝对路径**。用相对路径会解析到残留 cwd 下，文件根本没写而测试照样绿，
会得出「守卫失效」的错误结论（我踩过）：
```powershell
$root = "D:\claude\黑客松\hackathon-dut"; $f = "$root\webapp\src\components\MapView.vue"
$orig = [System.IO.File]::ReadAllBytes($f); [System.IO.File]::WriteAllBytes("$env:TEMP\x.bak", $orig)
# ...改坏...
$mod = [System.IO.File]::ReadAllBytes($f)
"patched: " + (-not [System.Linq.Enumerable]::SequenceEqual([byte[]]$mod, [byte[]]$orig))  # 必须 True
# ...跑测试...
[System.IO.File]::WriteAllBytes($f, $orig)
"restored: " + [System.Linq.Enumerable]::SequenceEqual([byte[]]([System.IO.File]::ReadAllBytes($f)), [byte[]]$orig)
```
`SequenceEqual` 两个参数都要显式 `[byte[]]` 转换，否则重载解析失败并在
**文件已恢复之后**抛异常，容易误判「还原失败」。

PowerShell 控制台会把中文显示成乱码（`Get-Content`、`Select-String` 都会），
那是解码不是文件损坏 —— 用 Bash 的 `grep` 或 python 加
`sys.stdout.reconfigure(encoding='utf-8')` 复核。

## I. 我自己犯的错，记下来避免重复

我第一次验证重合度时用 `TestClient` 打了 `/api/route/recommend`，
返回 `source=amap` —— **真的调了付费高德**。以为在 shell 里设 `AMAP_KEY=`
能覆盖，结果又打了 4 次，key 是从 `backend/.env` 读的，环境变量盖不掉。
**要看兜底数据就在进程内直调 `_build_fallback_route`。**

## J. 验收清单（验收人用）

按这个顺序看，每条都是能用眼睛判断的：

- [ ] 点「快速体验」→ 标题是「大连理工大学 → 星海广场」，不是经纬度
- [ ] POI 卡片下方没有裸坐标
- [ ] 首页历史记录是地名
- [ ] 地图瓦片加载完成前有占位，不露空白灰底
- [ ] 点沿途亮点卡片 → 地图上有可见的高亮反馈
- [ ] 手动缩放地图后，点反馈按钮不会把视野拽回去
- [ ] 页面上能同时看到「原本路线 X 公里 · X 分钟」和「推荐路线 Y 公里 · Y 分钟」
- [ ] 「全程距离」这张卡写清了是推荐路线的
- [ ] 「为什么推荐这条」框里有 POI 名称、绕行分钟数、评分依据，不只是一句叙事
- [ ] 评分显示不超过分母（不出现 `7.2/7`）
- [ ] 断网兜底下「路线指引」有多段，且没有任何一段显示经纬度
- [ ] 折叠/展开按钮能用
- [ ] 窄屏下不溢出不重叠
- [ ] 控制台无 error（mock 和真后端兜底两种数据源各看一遍）
- [ ] 四套测试：后端 ≥196、前端 ≥85、smoke ≥46、audit 39
- [ ] `git status` 干净（无临时文件），未提交未推送
- [ ] `optimization-plan.md` 里 P2-6 三处状态与实际一致
