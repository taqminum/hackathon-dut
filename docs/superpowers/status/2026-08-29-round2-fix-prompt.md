# 第二轮验收整改提示词（R1–R9）

给工作 AI。用户已在真实页面上逐屏验收，提出九条。下面每一条我都已独立查证过根因，
写明了**文件与行号**、**为什么现在是这样**、以及**验收标准**。不要重新调查结论，
直接改；但每一条都要按「验收标准」自证。

---

## 红线（违反即回滚）

1. **不要动 `backend/.env`**。里面有真实高德 key（32 位，非占位符）。
2. **不要跑付费高德调用**。所有验证走 `AMAP_KEY=` 前缀屏蔽密钥的进程内调用或桩。
   已实测：`load_dotenv` 默认 `override=False`，所以
   `AMAP_KEY= ./.venv/Scripts/python.exe ...` 能可靠屏蔽密钥（`key present: False`）。
   这是唯一批准的自测方式。**不要**为了「看看真实效果」去打真接口。
3. **不要改 `webapp/src/constants.js` 里的 `DEMO_SCENARIOS` 坐标和 `DALIAN_LANDMARKS` 坐标**，
   也不要改 `backend/app/services/dalian.py` 里的 `polyline` 点位来让效果好看。
   R4 是唯一要动演示数据的一条，改法在那条里写死了，别自由发挥。
4. **不要跑 `nvm use`**（会切全局 symlink，直接杀掉会话）。Node 用当前环境。
5. **不要提交、不要推送**。改完等 review。
6. 后端测试必须用虚拟环境：`cd backend` 然后 `.venv\Scripts\python.exe -m pytest -q`。

## 当前基线（改之前的数字，必须不下降）

| 套件 | 命令 | 基线 |
|---|---|---|
| 后端 | `cd backend && .venv\Scripts\python.exe -m pytest -q` | 203 passed |
| 前端单测 | `cd webapp && npm run test:run` | 110 passed（10 文件）|
| 冒烟 | 先 `node tests/mock-server.mjs 8000`，再 `npm run smoke` | 100 ok / 0 FAIL |
| 设计审计 | `npm run audit:design` | 39 ok / 0 FAIL |

冒烟和设计审计**不会**自己起假后端，必须先手动起 `node tests/mock-server.mjs 8000`。

## 工作纪律

- 每条改完，**先破坏验证**：把你的修复改坏，确认有点名测试变红，再按字节还原
  （`cmp -s`，或 `[System.IO.File]::ReadAllBytes` + `SequenceEqual`）。没有变红的测试
  等于没有守卫，要补测试。
- 不允许「改断言让测试过去」。如果断言和实现冲突，说明哪个错了，写清楚再动。
- 有几条是布局/可见性问题，**断言绿不代表屏幕上对**。R1、R5、R8 必须截图自证。

---

## R1｜地图盖住顶部导航栏（确认，严重）

**现象**：向下滚动时 Leaflet 地图覆盖 sticky header，「返回首页」按钮被压在地图下面点不到。

**根因（已查实）**：
- `webapp/src/components/SiteHeader.vue:57` → `z-index: var(--bh-z-overlay)`
- `webapp/src/assets/tokens.css:67` → `--bh-z-overlay: 50`
- Leaflet 自己的 pane 从 **200** 起（tilePane 200 / overlayPane 400 / markerPane 600 /
  popupPane 700 / controlPane 800）。50 < 200，所以地图**永远**盖住 header。
  `MapView.vue:318` 的注释已经写明「Leaflet 的 pane 从 z-index 200 起」，说明这个事实
  当时就知道，只是 header 的层级没跟着抬。

**改法**：把 `--bh-z-overlay` 抬到 Leaflet 之上（建议 1000，给 popup/control 留足余量），
并确认 `--bh-z-dropdown: 30`（`PlaceInput` 的联想下拉）也在地图之上 —— 首页没有地图所以
现在没暴露，但 R3 加了下拉之后如果结果页也出现输入框就会重演。建议一起抬：
dropdown 900、overlay 1000。**不要**去调 Leaflet 内部 pane 的 z-index，改自己的层级。

**验收标准**：
- 结果页滚动到地图与 header 重叠处，header 完整可见，「返回首页」可点击。**截图自证**。
- 加一条前端断言：header 的 z-index 计算值 > 800。这条要能破坏验证（把 token 改回 50 应变红）。

---

## R2｜快速体验回填的是经纬度，应显示名称（确认）

**现象**：见用户截图，起点框里是 `121.6785,38.9287`，终点框 `121.6701,38.8783`，
下面还有一行「坐标 121.6785,38.9287」。

**根因（已查实）**：`webapp/src/views/HomeView.vue:130-142` 的 `fillDemo` 把
`origin.value = newOrigin` 直接设成坐标串，`originLabel` 只是另一个变量。
输入框绑的是 `origin`（坐标），所以框里显示坐标。上一轮 T1 修的是**结果页标题**
（`ResultView` 用 `originLabel` 兜底），首页输入框没跟着修 —— 所以标题对了、输入框还是坐标。
`DEMO_SCENARIOS`（`constants.js:71-80`）本来就带 `originLabel: '大连理工大学'`。

**改法**：输入框显示地名，坐标作为提交值保留在旁边的状态里。也就是让
`origin.value` 存地名（`scenario.originLabel`），另存一个 `originCoord` 给 payload 用；
提交时优先用坐标。**不要**为了显示好看就把坐标丢掉 —— 后端对坐标串支持最好
（`PlaceInput.vue:118` 的注释已说明）。

注意 `applyHistory`（`HomeView.vue:154`）走同一个 `fillDemo`，一起生效，
历史记录项也要显示地名。

**验收标准**：
- 点任一快速体验，两个输入框显示中文地名，下方「坐标」小字仍显示坐标（可保留，作为佐证）。
- 提交后结果页标题仍是地名（不能把 T1 改回去）。
- 前端断言：`applyScenario` 后 `origin` 的显示值不匹配 `/^\d+\.\d+,\d+\.\d+$/`。

---

## R3｜起终点需要多结果筛选（部分已实现，缺的是数据源）

**现象**：搜「麦当劳」应列出多家门店供选择。

**已实现的部分（不要重写）**：`webapp/src/components/PlaceInput.vue` 已经是完整的
联想下拉组件 —— 远端 `suggestFn` + 本地 `DALIAN_LANDMARKS` 兜底
（`:42-49`）、260ms 防抖（`:64-79`）、乱序响应丢弃（`requestSeq`）、
键盘上下/回车/Esc（`:88-110`）、blur 延后关闭（`:113`）。
`HomeView.vue:165` 已接 `api.suggestPlaces`，`api.js:122` 已实现，
后端 `backend/app/routes/api.py:52` 已有 `INPUTTIPS_URL` 走高德 inputtips。

**真正的缺口**：链路是通的，但**没有 key 就返回空列表**（`api.py:474-476`），
本地兜底 `DALIAN_LANDMARKS` 只有那几个地标，里面没有麦当劳，所以搜「麦当劳」什么都没有。
换句话说这不是「没做」，是「没数据」。而且高德 inputtips **只返回地点提示**，
一个关键词多家门店是它的正常返回，链路本身满足需求。

**改法（二选一，我倾向前者）**：
- (a) 在有 key 的真实环境下这条已经成立，只需**补桩验证 + 空态文案**：
  `tests/mock-server.mjs` 加 `/api/place/suggest`，对「麦当劳」返回 5 条不同门店
  （名称带门店后缀、各自 location），冒烟里断言下拉出现 ≥3 条且可点选回填。
  同时在无 key / 空结果时，下拉给一条不可点的提示「联想不可用，可直接输入地名或坐标」，
  现在是静默空白，用户以为坏了。
- (b) 如果要在无 key 时也能搜到连锁店，得引第二数据源（Nominatim 已在
  `geocoder.py:98` 用过），但那超出「一次性改好」的范围，且 Nominatim 对中文 POI
  召回很差。**不建议**，除非 (a) 做完还有时间。

**验收标准**：
- 桩下搜「麦当劳」，下拉出现多条门店，点击回填该门店坐标并可提交。
- 无 key / 空结果时下拉显示提示文案，不是空白。
- 冒烟新增断言覆盖上面两点。

---

## R4｜三个模式输出「看起来一样」（确认，且比用户描述的更严重）

**现象**：用户感觉三个模式输出一样，原路线和推荐路线也没区别。

**根因（已查实，这是本轮最重要的一条）**：
我用进程内调用把三个模式全跑了一遍（`AMAP_KEY=` 屏蔽，无网络）：

```
scenario dut-xinghai（大连理工大学 → 星海广场）
  +5    score 5.38  detour 2   dist 7160   polyline sha1 02149d9a7214
  +15   score 4.78  detour 5   dist 7440   polyline sha1 02149d9a7214
  roam  score 4.18  detour 8   dist 7700   polyline sha1 02149d9a7214
```

**数字在变，折线的 sha1 三个模式完全相同**。也就是说：声称多走了 240 / 520 / 780 米，
但画在地图上的线一模一样。这不是「看起来像」，是**报告的距离和画出的几何不一致**。

再往下算，几何长度只有 5798 米，而声称距离 7160–7700，比值 1.235 / 1.283 / 1.328 ——
`distance` 根本不是从 polyline 量出来的。

代码位置：`backend/app/services/route_engine.py:290-296`

```python
if waypoint and scenario:
    effective_mode = mode or "+15"
    extra_distance = (scenario or {}).get("extra_distance") or {}
    extra_duration = (scenario or {}).get("extra_duration") or {}
    base_distance += extra_distance.get(effective_mode, 220)   # 数字加了
    base_duration += extra_duration.get(effective_mode, 120)
```

`dalian.py` 的 `extra_distance = {None: 0, '+5': 240, '+15': 520, 'roam': 780}`。
而折线部分（`:301-305`）只做了一件事：把 waypoint 这个**单点**插进
`scenario["polyline"]`（7 个点）里。三个模式的 waypoint 是同一个 POI，插入点也一样，
所以几何完全不变。

顺带解释了另外两个观感问题：
- 基准与推荐是**严格子序列**关系（`base_only=0, rec_only=1`），推荐只比基准多那一个点，
  最远分离 88 米（dut-xinghai）/ 510 米（donggang）—— 在 7 公里的图上几乎看不出来。
- 三个模式的 POI **完全相同**（都是同两家），所以「沿途亮点」也没变化。

**改法**：让几何和数字对上。绕行必须体现在折线上。具体做法：
在插入 waypoint 之后，按该模式的 `extra_distance` 把绕行段**真正撑开** ——
即在 waypoint 前后各插入若干中间点，使 `起点→waypoint→终点` 的几何长度
比基准几何长度多出 `extra_distance[mode] / 1.235`（1.235 是当前 distance/几何 的比例，
或者更干净的做法：直接让 `distance` 由几何长度乘固定系数算出，而不是查表加常数）。

我倾向后者，理由：查表加常数是数字与几何脱钩的根源，撑开几何再查表只是把两处凑齐，
下次改动又会脱钩。**建议 `distance` 一律 `round(几何长度 * 1.3)`**
（和 `:287` 无 scenario 分支的算法一致，那里本来就是 `route_distance * 1.3`），
`duration = distance / 1.35`。然后模式差异体现在「绕多远去接 POI」上：
`+5` 选最近的 POI，`roam` 允许更远的 POI，绕行幅度自然拉开。

这条会动 `dalian.py` 的 `extra_distance` / `extra_duration` 语义（可能整个删掉）。
**这是本轮唯一批准修改演示数据的地方**，因为它现在编码的是一个假数字。

**会变红的既有测试（预期，要一起改对，不是改断言迁就实现）**：
- `backend/tests/test_route_engine.py:68-69` 断言
  `distance == base_distance + extra_distance['+15']` —— 这两行正是把当前缺陷锁住的断言。
- `backend/tests/test_main.py:511` 断言
  `detour_minutes == round(extra_duration['+15'] / 60)`。

改这三行时必须在 commit message / 报告里写明「原断言锁定了数字与几何脱钩的缺陷」，
不能悄悄改掉。

**验收标准（硬性）**：
- 三个模式的 `route.polyline` sha1 **互不相同**。
- 每个模式 `abs(distance - 几何长度 * 1.3) / distance < 0.05`。
- 基准与推荐的最大分离 > 300 米（在图上肉眼可辨），且 `base_only > 0`
  （不再是严格子序列，两条线要真正分岔再合拢）。
- 三个模式的 POI 集合不完全相同（至少 roam 与 +5 不同）。
- 新增点名测试覆盖上述四点，且能破坏验证。

---

## R5｜「换掉了什么」框改为融入上方四个指标框（确认，采纳用户方案）

**现象**：见截图，四个指标框（基准时长 92 / 额外时间 +8 / 总计 100 / 推荐路线距离 7.7 公里）
下面又单独挂一个「换掉了什么」框，重复表达同一组数字。

**根因**：`ResultView.vue:325` 是 `result__tiles`（四个框），`:334` 是独立的
`compare` section。两处数据同源，视觉上割裂。

**改法（按用户明确指定的样式）**：删掉独立的「换掉了什么」框，把对比并入指标框内部 ——
在「推荐路线距离」框里用**小字显示原值、大字显示现值**，例如
`原 6.9 公里`（小字）/ `7.7 公里`（大字）。时长同理：`原 92 分钟`（小字）/ `100 分钟`（大字）。

保留的信息不能丢：带符号差值（`+780 米 · +8 分钟`）要还在，可以放在大字旁边的小字里。
`hasComparison` 为假时（降级分支，推荐==基准）不显示小字原值，只显示大字。

注意 `ResultView.vue` 里那个拒绝显示不自洽数字的 `scoreBreakdown` 逻辑（返回 null
而不是显示假数字）—— 保持这个原则，对比小字也一样：数字对不上就不显示，不要瞎凑。

**验收标准**：
- 独立的「换掉了什么」框不再存在，四个指标框内出现小字原值。**截图自证**。
- 既有覆盖「换掉了什么」的前端断言和冒烟断言要跟着改到新结构上，
  **不能只是删掉断言了事** —— 对比信息仍然必须被断言覆盖。
- 降级分支（推荐==基准）下不显示小字原值，也不崩。

---

## R6｜沿途亮点卡片点击展开详情（可做，但高德数据有限）

**现象**：用户希望点击 POI 卡片展开看详情。

**已查实的数据边界**：后端返回给前端的 POI 只有 5 个字段：
`name / type / distance / rating / location`（`poi_explorer.py:186-195`）。
而高德 `place/around` 请求参数里**没有传 `extensions=all`**（`:151-159`），
所以营业时间、电话、照片、地址这些字段现在根本没取回来。
`extensions=all` 是免费参数，不额外计费（同一次请求），但会让响应变大。

**改法**：
1. `poi_explorer.py:151` 的 params 加 `"extensions": "all"`，
   `_normalize_amap_poi` 多带出 `address` / `tel` / `photos[0].url` / `opentime`
   （字段缺失时给空，**不要**编造）。注意 `_extract_rating` 的注释已经踩过
   「空数组不是 null，`float([])` 会抛」的坑，新字段同样要防这个 —— 高德无数据时
   给的是 `[]` 而不是 `null`。
2. 前端 POI 卡片点击展开（宽度撑开或就地展开一块详情区），显示已有字段 + 新字段。
   没有的字段整行不渲染，不要显示「暂无」堆位置。
3. `location` 已经是 WGS-84（后端转过），点击时可以顺便让地图 pan 到该点并高亮对应
   marker —— 这个交互比展开文字更有价值，成本也低。

**用户说「如果高德 api 做不到就忽略」**：能做到，`extensions=all` 就是为此存在的。
但如果 `extensions=all` 在桩环境下没法验证（mock-server 要跟着补字段），
优先保证 (2)(3) 在现有 5 个字段上可用，(1) 作为增强。

**验收标准**：
- 点击 POI 卡片展开详情，再点收起。**截图自证**。
- 桩数据里给一个「字段齐全」和一个「只有基础字段」的 POI，两者都不崩、不显示空占位。
- 点击卡片时地图 pan 到该 POI。
- 键盘可达（Enter/Space 展开），`aria-expanded` 正确 —— 项目本来就在做无障碍。

---

## R7｜「重新规划」和「返回首页」行为相同（确认）

**根因（已查实）**：两个按钮 emit 同一个事件。
- `SiteHeader.vue:31` → `@click="emit('back')"` → 「返回首页」
- `ResultView.vue:318` → `@click="emit('back')"` → 「重新规划」
- `App.vue:66,74` 两处都接到 `onBack`，`currentView.value = 'home'`

所以「重新规划」名不副实，它就是返回首页。

**改法**：
- 「返回首页」保持现状（清空回首页）。
- 「重新规划」应当**保留起终点和模式，重新发一次请求**，停在结果页，
  不回首页。`HomeView.vue:171` 已经 `defineExpose({ handleSubmit, fillDemo })`，
  但 `App.vue` 在 result 视图下并没有挂载 `HomeView`（`v-else`），
  所以拿不到那个实例 —— 需要把请求参数提到 `App.vue` 层（或一个 store），
  两个视图共用。这是这条的主要工作量，别用 `key` 强制重挂 HomeView 绕过去，
  那会闪一下首页。
- 重新规划期间要有 loading 态，失败时红条给中文提示（上一轮已修过
  `Failed to fetch` 裸英文，别再退回去）。

**验收标准**：
- 点「重新规划」，URL/视图不回首页，起终点和模式不变，指标数字刷新。
- 点「返回首页」，回到首页且输入框保留上次内容（或明确清空，二选一，行为一致即可）。
- 前端断言分别覆盖两个按钮的不同行为，且能破坏验证
  （把「重新规划」改回 `emit('back')` 应变红）。

---

## R8｜结果页布局顺序（确认，按用户指定顺序）

**现状顺序**（`ResultView.vue`）：
标题 `:306` → 四指标 `:325` → 换掉了什么 `:334` → 评分 `:362` →
**地图 `:377`** → 沿途亮点 `:385` → 操作/反馈 `:413`

另外「为什么推荐这条」块（用户截图里在地图上方）也在地图之前。

**用户要的顺序**：标题（推荐路线 起点→终点 / 模式）→ **地图** → 改变（指标 + 对比）
→ 路线详情。

**改法**：把 `MapView` 提到紧接标题之后，其余块顺次下移。
配合 R5，「改变」就是那四个融合了原值小字的指标框。
「为什么推荐这条」和评分块放在指标之后、路线指引之前。

**注意**：MapView 挂载时机变了，`fitBounds` 可能在容器还没有高度时执行 ——
Leaflet 在 `display:none` 或零高度容器里 `fitBounds` 会算出错误的 zoom。
移动之后必须确认地图初始视野正确（`invalidateSize()` 时机）。这是移动地图最容易踩的坑，
截图确认，别只看断言。

**验收标准**：
- DOM 顺序：标题 → 地图 → 指标 → 理由/评分 → 沿途亮点 → 路线指引 → 操作。
- 地图初始视野把两条线都框进去（不是缩到世界级别，也不是贴死在角落）。**截图自证**。
- 冒烟里加一条 DOM 顺序断言（地图元素的 `compareDocumentPosition` 在指标之前）。

---

## R9｜「为什么还没内置高德 API」（用户认知偏差，需解释而非修改）

**事实（已查实）**：高德**已经完整接入**，不是没做：
- 步行路径：`route_engine.py:123` `_request_amap_walking`，含 GCJ-02 转换、
  重试（`:173`）、限流（`:30 throttle_amap`）、两段拼接走 waypoint（`:238`，
  因为高德步行接口**不支持** waypoint，实测带与不带距离完全一致，见 `:126` 注释）
- POI 搜索：`poi_explorer.py:12` `place/around`
- 地理编码：`geocoder.py:26` `geocode/geo`，无 key 时退 Nominatim
- 地点联想：`api.py:52` `assistant/inputtips`
- `backend/.env` 里 `AMAP_KEY` 是真实的 32 位 key，不是占位符

**你现在看到的是兜底效果，因为我给你启动后端时用 `AMAP_KEY=` 屏蔽了密钥**，
目的是避免验收点击产生付费调用。屏蔽后：路径走 `_build_fallback_route`
（`route_engine.py:113,270`），POI 和联想返回空/桩数据。

所以 R9 **不需要改代码**。但有两件相关的事该做：
1. 无 key 时前端应当明确告知「当前为离线演示数据」，而不是让用户以为这就是高德结果。
   现在只有地图瓦片失败时有提示（`MapView.vue:283`），路径降级是静默的。
   后端 `route.source` 已经区分了 `amap` / `fallback`，前端拿得到，加个角标即可。
2. R4 修好之后，兜底路线的几何才配得上「演示」二字。现在兜底几何是直线连点，
   7 个点连出来的折线（`dalian.py` 的 `polyline`）已经比直线好，但绕行是假的。

**验收标准**：
- 前端在 `route.source === 'fallback'` 时显示「离线演示数据」角标，
  `'amap'` 时不显示。断言覆盖两个分支。
- 不要为了让角标消失去改 `source` 的取值。

---

## 交付要求

改完给一份报告，逐条对应 R1–R9，每条写：
- 改了哪些文件哪些行
- 破坏验证做了什么、哪条测试变红、还原是否字节一致
- 四套数字（不低于基线：203 / 110 / 100 ok / 39 ok）
- R1 / R5 / R6 / R8 的截图（这四条断言覆盖不了可见性）
- R4 的四条硬性指标实测值
- 如果某条判断我写错了，直接说，附证据。别为了对齐提示词去改一个本来对的实现。

已知会变红、且**应当**跟着改的既有断言，只有 R4 那三行
（`test_route_engine.py:68-69`、`test_main.py:511`）和 R5 的对比断言。
除此之外任何变红都要先当成回归查，不要顺手改断言。
