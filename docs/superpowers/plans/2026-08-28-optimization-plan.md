# 偶遇导航优化清单与修改计划

> 基线提交：`18afd34`（2026-08-28 实测审查）
> 每条都附文件与行号；结论均来自本机实际运行，未经验证的项已单独标注。
> 相关文档：`docs/superpowers/plans/2026-08-25-serendipity-navigation.md`、`docs/superpowers/specs/demo-scenarios.md`
> 交接文档：`status/2026-08-28-handover-2.md`（最新）、`status/2026-08-28-handover.md`（第一轮）

---

## 执行状态（2026-08-28 第三轮更新，工作区未提交）

**P0、P1、P2 全部完成，P3 未开始。** 后端 193 passed。
第三轮只动后端 —— Node 仍是 v20.12.0，`webapp/dist` 的手工补丁与
`constants.js` 的六个演示坐标一个字节都没碰，所以坐标一致性与断网演示两条不变量不可能回退。
下面每条的状态在正文对应小节里也标了 `【已完成】/【未做】`。

| 分组 | 状态 |
|---|---|
| P0-1 路径穿越 | 已完成（`main.py:59` commonpath 校验 + `test_static_security.py`） |
| P0-2 偏离写死坐标 | 已完成（接高德真实数据，任意大连坐标可用） |
| P0-3 坐标错误 + 地名跑外省 | 已完成（`dalian.py` 单一数据源 + geocoder 城市偏置） |
| P0-4 折返线 | 已完成（两段拼接，`test_route_engine.py` 有单调性用例） |
| P0-5 五个接口 404 | 已完成（save/list/feedback/suggest 都在；`/poi/:id` **故意不做**，改删前端死函数） |
| P1-0 ~ P1-6 | 全部已完成 |
| P2-1 评分上限 | 已完成（ScoreMeter 与 `scoreToPercent` 都改成 7） |
| P2-2 标签匹配没实现 | 已完成（`scorer.py` 改收 `tag_affinity`；`PreferenceManager` 接进 `/api/feedback`，新增 `GET /api/preference`） |
| P2-3 `pois` 恒 1 个 | 已完成（沿选中路线 400 m 内按评分取 top-3） |
| P2-4 roam 无绕行上限 | 已完成（`roam` = 30 分钟，即 `+15` 的两倍） |
| P2-5 响应形状不一致 | 已完成（高德分支补齐 `origin`/`destination`/`demo_mode`，有同形断言） |
| P2-6 fallback 无转向指令 | 已完成（兜底路线现在有多段 steps） |
| P2-7 坐标缺失落到北京 | 已完成（改抛 `ValueError` → 404；有 AST 卫兵测试防止写死坐标回归） |
| P2-8 死代码清理 | 已完成（`_try_parse_coord`、`RecommendRequest`、`fetchPoiDetail`、`map-loader.js` 已删；`PreferenceManager` 按 P2-2 接活，不再是死类） |
| P3-1 ~ P3-8 | 全部未开始（无 vue-router、无 manifest、无定位） |

**本轮还额外做了（不在原清单里）**：
1. `webapp/dist` 手工按字节打了补丁（演示按钮坐标、评分条上限、绕行 0 的文案），
   因为 Node v20.12.0 跑不了 `npm run build`。**细节与风险见交接文档，这是当前最大的技术债。**
2. 删掉了 `poi_explorer.py` 的本地类型复筛 —— 它把所有 `风景名胜` 类 POI 都筛掉了。
3. `+5` 模式改成「预算内取最高分」，原来是取绕行最少，评分完全不参与。

## 审查基线：已确认可用的部分

改动前先明确不需要动的地方，避免误伤：

- 后端测试 36 passed / 0.28s（**审查时的数字；改造后是 193 passed**）。`status/2026-08-26.md` 记录的「test_main.py 卡死」在干净环境下不复现，
  根因是 `LLM_API_BASE` + `LLM_MODEL` 环境变量泄漏进测试进程后 `narrative.py:25-38` 会发真实 POST。
- `uvicorn app.main:app` 起来后 `/` 正常返回 `webapp/dist/index.html`，assets 200，`/health` 返回 `{"status":"ok"}`，CORS 预检通过。
- `webapp/dist/` 审查时确认为当前源码所构建（内容哈希文件名一致、md5 逐字节相同）。
  **改造后不再成立**：bundle 被手工按字节改过，见交接文档。
- 真实浏览器跑通首页 → 结果页：Leaflet 折线 + 3 个标记、四项指标、评分条、叙事、POI 卡片、分段指引全部渲染，无脚本报错。
- 前端降级设计正确：Leaflet 本体与 marker 图片均本地打包，只有瓦片走外网；`api.js` 用相对路径 `/api`，未写死 localhost。
- 加载 / 错误 / 空结果三态齐全，`withFallback` 让未定稿接口静默降级。

## 一、优化清单

### P0 演示前必须完成

按「评委不按脚本走就会踩到」排序。

#### P0-1 静态文件路径穿越（安全） 【已完成】

- 现象：`GET /../../.git/config` 返回 200 并泄漏内容；`/../../.claude/settings.local.json`、
  `/../../backend/requirements.txt` 同样可读；`N=4` 层可读到仓库外任意文件（实测 88 KB 命中）。
- 根因：`backend/app/main.py:56` 直接 `os.path.join(frontend_dist, full_path)` 拼用户路径，无归一化、无包含性校验。
  叠加 `main.py:29` 的 `allow_origins=["*"]` 与接口无鉴权，服务一旦不绑 localhost 就是任意文件读取。
- 改法：删掉手写 catch-all，改用 `app.mount("/", StaticFiles(directory=frontend_dist, html=True))`；
  若要保留 SPA 兜底逻辑，至少 `os.path.realpath` 后校验前缀是否仍在 `frontend_dist` 内。
  顺带清理：`main.py:9-23` 的 `FrontendFallbackMiddleware` 已被 `main.py:54` 的 catch-all 架空，属死代码；
  `frontend_dist`（`main.py:38`）定义在 `add_middleware` 之后，靠全局延迟解析才没坏，一并上移。
- 负责人：成员 B ／ 预估 20 分钟

#### P0-2 偏离 3 组写死坐标，核心卖点消失 【已完成】

- 现象（实测）：

  | 输入 | 绕行 | 评分 | POI | polyline |
  | --- | --- | --- | --- | --- |
  | 演示坐标（精确） | +5 分钟 | 5.68 | 1 个 | 6 点 |
  | 同一对坐标平移 0.002 度 | 0 分钟 | 0 | 0 个 | 2 点直线 |
  | 打字「大连理工大学→星海广场」 | 0 分钟 | 0 | 0 个 | 2 点直线 |
  | 任意大连坐标对 / 北京坐标对 | 0 分钟 | 0 | 0 个 | 2 点直线 |

- 根因：无高德 Key 时 `backend/app/services/poi_explorer.py:55-56` 只对 `DALIAN_POI_SCENARIOS` 的 3 个坐标 key 返回兜底 POI，
  其余一律空列表 → 走 `backend/app/routes/api.py:120-129` 的空分支，返回 `pois: []`、`score: 0`、通用文案、两点直线。
- 影响：评委自己输入地点时，看到的是「多花 0 分钟、0 个亮点、一条直线」的普通导航，产品叙事当场失效。这是最要紧的一条。
- 改法（**2026-08-28 已改为高德方案，原造假数据方案作废**）：高德 Key 已配置并验证可用，
  真实沿线采样即可覆盖任意起终点，不需要再编店名。落地靠 P1-0（两段拼接）+ P1-1（截断并发）
  + P1-2（沿线采样）+ P1-3（评分字段与质量门槛）四条，本条不再需要独立改动。
- 实测依据：大工 → 星海沿线采到 60 个真实 POI，筛出的候选带真实评分与真实绕行代价 ——

  ```
  高寿参鸡汤(康派国际公寓店)    4.5 分   多花 0.7 分钟
  金家故乡汤饭馆(康派店)        4.4 分   多花 0.7 分钟
  满炖(大连数码广场店)          3.9 分   多花 0.9 分钟
  ```

  「只多花 40 秒，能路过一家 4.5 分的参鸡汤店」这句话有说服力，而「理工咖啡小铺」没有，
  因为它不存在。
- 原方案（沿 polyline 撒点、按坐标哈希编店名）**仅在放弃高德 Key 时才需要**，作为备选保留。
- 兜底表不删：断网时仍退回三组脚本场景（见 P0-3 的坐标校正）。
- 负责人：成员 B ／ 预估 0（并入 P1-0 到 P1-3）

#### P0-3 地标坐标错误 + 地名解析跑到外省 【已完成】

- 现象（实测，Nominatim 加「大连」后缀后仍如此）：

  ```
  大连理工大学    写死 121.6068,38.9180   实际 121.5199,38.8856   偏  8.3 km
  星海广场        写死 121.5854,38.9325   实际 121.5830,38.8814   偏  5.7 km
  东港商务区      写死 121.6281,38.9329   实际 118.4703,39.0559   偏 273 km（唐山）
  老虎滩海洋公园  写死 121.6542,38.9337   实际 无结果
  西安路          写死 121.5899,38.9148   实际 121.5823,38.9090   偏  0.9 km
  傅家庄公园      写死 121.6075,38.9094   实际 121.6183,38.8646   偏  5.1 km
  ```

  不加后缀直接搜更糟：老虎滩 → 175.9578,-38.0035（新西兰），星海广场 → 91.7963,29.4822（西藏）。

- 根因有两处，互相独立：
  1. `webapp/src/constants.js:71-80` 的 `DALIAN_LANDMARKS` 与 `backend/app/services/route_engine.py:8-48`
     的 `DALIAN_SCENARIOS` 里写死的坐标本身就偏了 5-8 公里，不是真实位置。
  2. `backend/app/services/geocoder.py:22-27` 调 Nominatim 只传 `q/format/limit`，
     没有 `countrycodes=cn`、没有 `viewbox` 大连框、没有城市偏置。
- 附带风险：Nominatim 限 1 req/s，`api.py:39-40` 每次请求要打 2 次，无缓存无重试；
  被限流后 `geocoder.py:33` 转 ValueError → `api.py:41-42` → 用户看到 404「未找到可行路线」。
- 改法：
  - 校正 `constants.js` 与 `route_engine.py` 里的 6 个地标坐标（以及依赖它们的 3 组 scenario key 和 polyline）。
  - `geocoder.py` 加 `countrycodes=cn` + `viewbox=121.45,39.05,121.80,38.80` + `bounded=1`，并对 query 自动补「大连」。
  - 加一层进程内 dict 缓存（key 为原始输入字符串），避免同一地名反复打 Nominatim。
- 注意：改 scenario key 会同时影响 `poi_explorer.py:59-72` 与 `narrative.py:5-21` 的三张表，
  这三处 key 必须同步改，否则演示场景会掉进兜底分支。改完务必重跑 3 组场景。
- 负责人：成员 B（后端）+ 成员 A（`constants.js`）／ 预估 1 小时

#### P0-4 `+15` 与 `roam` 的地图路线画成折返线 【已完成】

- 现象：按「距终点距离」逐点核算，两个最想展示的模式都在 p3 反向远离终点：

  ```
  场景 1 +15  ：p3 远离终点 416 米
  场景 2 roam ：p3 远离终点 501 米
  场景 3 +5   ：0 米（POI 恰好靠前，侥幸正常）
  ```

- 根因：`backend/app/services/route_engine.py:135` 把途经点固定插到 `scenario_points` 索引 2，
  不判断它实际落在路径哪一段。
- 影响：地图是结果页主视觉，折返线一眼可见，而且正好出现在 `+15`/`roam` 两个卖点模式上。
- 改法：把固定 `waypoint_index = 2` 改成「找与途经点距离最近的线段，插到该线段之后」——
  遍历相邻点对，取点到线段距离最小的那一段。已有 `_haversine_meters`（`route_engine.py:168`）可复用。
- 负责人：成员 B ／ 预估 40 分钟

#### P0-5 前端已在调的 5 个接口全部不存在 【已完成】

- 现象（浏览器实测到的真实请求）：

  | 接口 | 实际返回 | 用户可见后果 |
  | --- | --- | --- |
  | `GET /api/place/suggest` | 404（打字时每个输入框各打 1 次） | 无，静默降级为本地地标过滤 |
  | `GET /api/poi/:id` | 404 | 无 |
  | `GET /api/trip/list` | 404 | 无（前端从未调用，死代码） |
  | `POST /api/trip/save` | 405 | **UI 显示「收藏失败，重试」** |
  | `POST /api/feedback` | 405 | 点了没有任何反应 |

- 根因：后端只实现了 `/api/route/recommend`（`backend/app/routes/api.py:25`）；
  前端 `webapp/src/api.js:11-15` 声明了 5 个，靠 `api.js:57-63` 的 `withFallback` 兜住。
- 改法（二选一，演示前必须做掉其中一个）：
  - 方案 A（推荐）：后端补两个最小实现，进程内存存储即可 —— `POST /api/trip/save` 返回 `{ok: true, id}`、
    `POST /api/feedback` 返回 `{ok: true}`。约 30 行，顺带为 P1-4 的偏好闭环打基础。
  - 方案 B（保底）：前端先隐藏「收藏这条路线」与反馈按钮，别让评委看见失败态。
- 另需清理：`api.js:145` 的 `listTrips` 与 `api.js:117` 的 `fetchPoiDetail` 从未被任何 UI 调用，属死代码。
- 负责人：成员 B（方案 A）／ 成员 A（方案 B）／ 预估 40 分钟

### P1 一旦配上高德 Key 或网络变差就会出问题

这一组在「无 Key 纯离线」演示路径上不会触发，但只要现场决定配 Key，就会立刻暴露。

#### P1-0 步行 API 不支持 `waypoint`，参数被静默忽略（已用真 Key 确认） 【已完成】

**这条是配 Key 后最先炸的地方，必须和 P1-1 一起做。**

- 实测证据（2026-08-28，真 Key，大工 → 星海）：

  ```
  无 waypoint  6920 m
  带 waypoint  6920 m   ← 完全一致，参数无效
  ```

- 根因：`backend/app/services/route_engine.py:59` 给步行接口传 `params["waypoint"]`，
  但高德只有**驾车** API 支持途经点，步行 API 直接忽略该参数。
- 为什么现在没暴露：无 Key 时走 `_build_fallback_route`，它自己处理 waypoint。
  **配上 Key 后** `api.py:82-87` 的候选循环会拿到与基准完全相同的路线 →
  `calculate_detour` 恒为 0 → 所有候选零代价 → 打分与「可控的意外」全部失效。
- 改法：改成**两段拼接** —— `起点→POI` 加 `POI→终点`，distance/duration 相加，
  steps 与 polyline 拼接。拆一个 `_walk_leg(origin, destination)` 出来复用。
  同时删掉 `route_engine.py:59` 那行无效的 waypoint 参数。
- 实测两段拼接可行：

  ```
  基准        6920 m / 5536 s / 278 折线点 / 13 段指令
  两段拼接    6897 m / 5517 s / 280 折线点 / 18 段指令
  ```

  折线沿真实街道、转向指令连续、绕行真实。
- **新增副作用要处理**：两段拼接偶尔比基准更短（高德路径规划本身有非确定性），
  实测出现过 `-0.3 分钟`。界面会显示「多花 -0.3 分钟」，必须 clamp 到 0。
- 代价：每个候选从 1 次调用变成 2 次，所以 P1-1 的候选截断由「优化」升级为「必须」。
- 负责人：成员 B ／ 预估 1 小时

#### P1-1 N+1 串行外部调用，实测约 53 秒（两段拼接后约 100 秒） 【已完成】

- 现象：`backend/app/routes/api.py:82-87` 对每个 POI 各调一次路径规划，全部串行。
- 实测单次高德步行调用**平均 4.84 秒**（6 次串行 = 29.0 秒），比原先估算慢得多：

  | 结构 | 调用次数 | 预计耗时 |
  | --- | --- | --- |
  | 现在（10 个 POI，N+1） | 11 次 | 约 53 秒 |
  | 两段拼接后（10 个 POI） | 21 次 | 约 100 秒 |
  | 截断到 3 个 + 并发 | 7-10 次 | 约 5-8 秒 |

  而前端 20 秒就 abort（`webapp/src/api.js:19`）—— 不截断就是**必然失败**，不是「可能慢」。
- 改法：三步，必须全做 ——
  1. 候选 POI 按 rating 降序截断到前 **3** 个再进循环。
  2. `concurrent.futures.ThreadPoolExecutor(max_workers=3)` 并发（`requests` 是阻塞 IO，线程池够用）。
  3. 总预算超时：整个 recommend 超过 8 秒就返回当前已算出的最优候选。
- 配额核算：按截断到 3 个算，一次查询吃 7-10 次高德调用。
  演示前反复测试很容易上千次，**先去控制台确认日配额**；紧张就把截断改成 2 个。
- 负责人：成员 B ／ 预估 1 小时

#### P1-2 POI 只在路径中点方圆 300 米采一个圈 【已完成】

- 现象：函数名叫 `explore_pois_along_route`，但 `backend/app/services/poi_explorer.py:14-23`
  只取起终点中点作为唯一圆心，并没有沿线采样。
- 实测差距（2026-08-28，真 Key，大工 → 星海）：

  ```
  只取中点 radius=300              → 20 个 POI（现在的做法）
  沿线 25%/50%/75% 各 radius=400   → 合计 60 个，去重后仍 60 个
  ```

  真实沿线采样能拿到 3 倍候选，这直接决定了 P0-2 能否用真实数据兑现。
- 改法：按基准 polyline 取 25% / 50% / 75% 三个点分别查询，按 name 去重合并。
  与 P1-1 的线程池一起并发，增量成本很低。
- 负责人：成员 B ／ 预估 40 分钟

#### P1-3 高德评分字段读错（已用真 Key 确认） 【已完成】

- `backend/app/services/poi_explorer.py:46` 读顶层 `rating`，而高德 v3 `place/around`
  **不存在这个顶层字段**，评分在 `biz_ext.rating`。真 Key 下每个 POI 的 `poi_quality` 恒为 0，
  `scorer.py:1-6` 退化成 `3.0 - 0.2 × 绕行`，评分失去区分度。
- 实测证据（2026-08-28，真 Key）：

  ```
  喜鼎海胆水饺   顶层 rating 存在? False   biz_ext.rating = '4.8'
  福禧快餐店     顶层 rating 存在? False   biz_ext.rating = '3.6'
  星巴克臻选     顶层 rating 存在? False   biz_ext.rating = '4.6'
  ```

- 改法：读 `poi.get("biz_ext", {}).get("rating")`，保留顶层 `rating` 作兼容回退。
  **两个解析陷阱**：值是字符串（`'4.8'`）需转 float；`biz_ext.cost` 无数据时返回
  空数组 `[]` 而非 null，直接 `float()` 会抛异常。
- 同时要加**质量门槛**：实测筛出的候选里混进了评分 1.6 的农产品销售商行与烟酒商店，
  推荐用户「偶遇一家烟酒店」叙事就垮了。建议 rating ≥ 3.5 并按 type 关键词排除
  烟酒、便利店、超市、农产品销售。
- 负责人：成员 B ／ 预估 30 分钟

#### P1-3b 类别名问题不存在（原判断已作废） 【已完成】

原先认为 `api.py:66` 的 `types` 里「景点」不是高德合法类别名。**实测推翻**：
`餐饮|景点|购物` 与 `餐饮服务|风景名胜|购物服务` 都返回 20 个 POI，高德接受模糊匹配；
且旧过滤词 `['餐饮','景点','购物']` 对新类别名命中 20/20，
因为高德返回的 type 是 `餐饮服务;中餐厅;特色/地方风味餐厅` 这种带分号的串，`in` 判断成立。
**本条无需改动。**

#### P1-4 坐标系混用，开 Key 后折线整体偏移 【已完成】

- 现象：高德返回 GCJ-02，Nominatim 与 Leaflet 的 OSM 瓦片是 WGS-84，代码里没有任何转换。
- 实测偏移量（2026-08-28，用高德自己的 `/v3/assistant/coordinate/convert`，`coordsys=gps`）：

  ```
  星海广场附近   WGS84 121.5830,38.8814  →  GCJ02 121.587945,38.882156   偏移 436 米
  大连理工大学   WGS84 121.5199,38.8856  →  GCJ02 121.525010,38.886478   偏移 453 米
  ```

- **不转换的话，配上 Key 反而比现在更糟** —— 所有路线整体偏离街道约 450 米，
  而不只是现在这样三条演示路线画错位置。
- 改法：新建 `backend/app/services/coord.py`，实现 `gcj02_to_wgs84` 与 `wgs84_to_gcj02`
  （标准算法约 25 行）。策略是**对外统一 WGS-84（前端、兜底表），对高德统一 GCJ-02**：
  在 `route_engine.py` / `poi_explorer.py` 的请求入口和响应出口各转一次。
  polyline 要逐点转。
- **这一步必须排在所有路线改动之前**，否则改完看地图还是偏的，分不清是哪个问题造成的。
- 负责人：成员 B ／ 预估 40 分钟

#### P1-5 LLM 那条路接不上任何商业接口，且能把主接口打成 500 【已完成】

- `backend/app/services/narrative.py:31-38` 不带 Authorization 头，也没有对应环境变量；
  payload 是 Ollama 风格 `{model, prompt, stream}`，但 `narrative.py:42-47` 优先按 OpenAI 的
  `choices[0].message.content` 解析。结论：只能接 Ollama 的 `/api/generate`，接不上任何 OpenAI 兼容服务
  （后者要 `messages` 数组 + Bearer token）。
- `generate_narrative` 在 `api.py:121` 与 `api.py:131` 两处**没有 try/except 包裹**；
  `narrative.py:43-47` 遇到 JSON 合法但结构异常的响应（如 `{"choices": ["text"]}`）会抛 AttributeError，
  而 `narrative.py:51` 只捞 `TimeoutError` 与 `requests.RequestException`，捞不住 → 主接口 500。
- 改法：
  - `narrative.py` 改成标准 OpenAI 兼容格式（`messages` + `Authorization: Bearer`），
    加 `LLM_API_KEY` 环境变量；保留 Ollama 分支作为兼容。
  - `narrative.py:51` 的 except 补上 `Exception`，或在 `api.py` 两处调用点各加 try/except 兜到默认文案。
  - 顺带修测试隔离：`backend/tests/conftest.py:1-8` 加一个 autouse fixture 清掉
    `LLM_API_BASE`/`LLM_MODEL`/`AMAP_KEY`，避免本地环境变量泄漏进测试（就是 08-26 那个「卡死」的根因）。
- 负责人：成员 B ／ 预估 50 分钟

#### P1-6 地图瓦片依赖公网 【已完成】

- 现象：`webapp/src/components/MapView.vue:143` 写死 `https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png`。
- 已验证的好消息：断网**不会白屏**。Leaflet 库本体与 marker 图片都本地打包
  （`main.js:1`、`utils/leaflet.js:2-4`），`failed` 标志只在 `L.map()` 抛异常时置位（`MapView.vue:151-155`），
  瓦片 404 属图片加载失败不触发它。结果是灰底上仍正常绘制折线 + A/B/POI 标记，图例、指标、叙事照常。
  属于「能看懂但不好看」，而不是「演示中断」。
- 改法（可选，按现场网络决定）：把 3 组演示场景覆盖范围的瓦片预下载到 `webapp/public/tiles/`，
  瓦片 URL 改成本地路径 + OSM 作为 fallback。或者更省事：准备一张地图截图作为口头兜底。
- 负责人：成员 A ／ 预估 1 小时（预下载）或 0（只备截图）

### P2 逻辑与体验缺陷（对台上影响小，但会被追问）

#### P2-1 评分上限是 7.0，UI 按 /10 显示 【已完成】

- `backend/app/services/scorer.py:2-6`：`tag_bonus = len(matched_tags) * 3.0`，
  而 `api.py:105` 传的 `matched_tags` 恒为单元素列表 → tag_bonus 恒为 3.0；
  `quality_bonus = poi_quality * 4.0` 上限 4.0。合计最高 7.0。
- 前端 `webapp/src/components/ScoreMeter.vue:10` 的 `max` 默认 10，评分条永远填不过 70%。
- 改法：要么把 scorer 的权重调成满分 10，要么把 ScoreMeter 的 max 改成 7。前者更好解释。

#### P2-2 标签匹配实际没有实现 【已完成】

- `api.py:105` 传 `matched_tags=[poi.get("type", "")]`，永远是单元素，`tag_bonus` 是常数。
  也就是说打分里的「标签匹配」这一维完全没生效，而且没有任何用户偏好入口。
- 关联赛题：本项目对应 03 开放原子赛道「制造一点意外」。目前有反馈按钮、有 `PreferenceManager`
  （`backend/app/models/preference.py:1-16`，**全文件无人 import，死代码**），
  但没有偏好落地与「下次帮你换一条」的闭环。这是叙事上最容易被追问、也最值钱的补充。
- 改法（加分项，时间够再做）：把 P0-5 的 `/api/feedback` 接进 `PreferenceManager`，
  记录用户对 POI 类型的偏好，在 `scorer.score` 里让 `matched_tags` 真正参与计算。

#### P2-3 `pois` 恒定只返回 1 个 【已完成】

- `api.py:136` 写死 `"pois": [chosen["poi"]]`，而兜底数据里每组场景明明有 2 个 POI
  （`poi_explorer.py:59-72`）。「沿途几个亮点」的说法给不出来。
- 改法：返回 top-N 候选（N=2-3），前端 `ResultView.vue` 已支持列表渲染，改动集中在后端。

#### P2-4 `roam` 模式没有绕行上限 【已完成】

- `api.py:15` 的 `MAX_DETOUR_MINUTES` 只有 `+5` 与 `+15`，
  `api.py:96-98` 取到 `None` 就完全不过滤。产品定位是「可控的意外」，roam 无上限与这个说法冲突。
- 改法：给 roam 设一个 30 分钟上限，或明确改成「按评分选最优、不设硬上限」并在 UI 文案里说清。

#### P2-5 响应形状在两条路径下不一致 【已完成】

- 走高德真实路径时 `route` 字典来自 `route_engine.py:84-91`，只有 `distance/duration/steps/polyline`，
  **没有** `origin`/`destination`/`demo_mode`；只有 fallback 路径（`route_engine.py:143-158`）才带这三个字段。
- 影响：`ResultView.vue:119-121` 依赖 `route.demo_mode` 判断是否显示「内置演示数据」提示，
  真 Key 下该字段缺失（undefined 恰好为假，所以不报错，但属于隐性依赖）。
- 改法：在 `route_engine.py` 的高德分支里补齐这三个字段，保证两条路径同形。

#### P2-6 fallback 路线没有任何转向指令 【已完成】

- `route_engine.py:149-156` 的 steps 只有一条「按推荐路线行走」。
  结果页的「路线指引」区块在演示时永远只有 1 段，`RouteSteps.vue` 的折叠/展开能力用不上。
- 改法：按 polyline 相邻点生成分段，每段用方位角推「向东北走约 X 米」这类文案。

#### P2-7 坐标缺失时默认落到北京 【已完成】

- `route_engine.py:162-163`：`_parse_lng_lat` 收到空值时返回 `116.407526,39.90403`（天安门）。
  这是个静默的错误默认值，出问题时很难排查。
- 改法：改成抛 ValueError，让 `api.py:51-52` 转成 404，而不是给出一条北京的路线。

#### P2-8 死代码清理 【已完成】

已删除：

- `backend/app/routes/api.py`：`RecommendRequest`（接口实际用 `Body(..., embed=True)`）。
- `backend/app/services/route_engine.py`：`_try_parse_coord`。
- `webapp/src/utils/map-loader.js`：整个文件。含占位 `YOUR_AMAP_KEY`，全项目无 import，
  确认未进 dist（`webapi.amap.com` 在产物中出现 0 次），删掉免得评委翻代码时看到高德占位 Key。
- `webapp/src/api.js` 的 `fetchPoiDetail`：全项目无 UI 调用。连带删了 `api.test.js` 的用例和
  `HomeView.test.js` / `ResultView.test.js` 里的两个桩。**没有**补后端 `/api/poi/:id` ——
  删掉调用方比为死函数造接口对。

有意保留：

- `backend/app/models/preference.py` 的 `PreferenceManager`：**确实是死类**（无 import、无测试），
  但它正好是 P2-2 那个闭环的现成载体。要么按 P2-2 把它接进 `/api/feedback`，要么一并删掉，
  别让它就这么挂着。
- `webapp/src/api.js` 的 `listTrips`：`/api/trip/list` 后端已实现，留着无害。

### P3 前端体验与工程卫生

#### P3-1 无路由，结果页无法分享或刷新保留 【未做】

- 全项目**没有 vue-router**（package.json、package-lock.json、node_modules 三处均无）。
  `App.vue:14` 用 `currentView = ref('home')` 做单文件视图切换，`App.vue:10-11` 注释写明「Hackathon 范围内够用」。
- 副作用：URL 从不变化 → 浏览器后退键不可用、结果页无法分享、刷新丢失结果、无深链接。
- 改法：加 vue-router 并把起终点与模式放进 query string（`?from=...&to=...&mode=+15`）。
  这一条同时解决「无分享功能」——有了 URL 就能复制链接。

#### P3-2 缺少地图选点与「我的位置」定位 【未做】

- 全项目无 `geolocation` 调用；`MapView.vue:56` 只有 marker 点击，没有 `map.on('click')`。
- 原计划文档（`plans/2026-08-25...md:4,45`）明确把「地图选点」列为暂不支持，属已知取舍。
  但这是「导航产品」最容易被追问的交互缺失，评委若想自己试就只能打字或点 3 个预设按钮。
- 改法：`map.on('click')` 回填最近的输入框 + 一个「我的位置」按钮调 `navigator.geolocation`。

#### P3-3 点 POI 不移动地图 【未做】

- 卡片 ↔ 地图联动已实现（双向），但只换图标颜色。
  全项目除初始化外无 `panTo`/`flyTo`/`setView`（`MapView.vue:140` 仅一处）。POI 在视野外时点了像没反应。
- 改法：`focusPoi` 里补一个 `map.panTo(latlng)`。

#### P3-4 无多候选路线对比 【未做】

- 后端只回单个 `route`，前端也只渲染一条（`ResultView.vue:31`）。
  而产品卖点是「换一条路」，缺少「基准路线 vs 推荐路线」同图对比，说服力打折。
- 改法：后端在响应里额外返回 `baseline_route`，前端用虚线／灰色描边同图绘制。
  这一条是**叙事上最值钱的加分项**，如果 P0 提前做完，优先做它。

#### P3-5 PWA 完全缺失 【未做】

- 无 manifest、无 service worker、无图标、无 `webapp/public/` 目录，连 favicon 都没有
  （`/favicon.ico` 实测返回的是 index.html，734 字节）。不可离线、不可安装。
- 关联：原计划里的「Android App 壳打包」（`plans/2026-08-25...md:82`）至今未开始，
  且 `team.md` 里「Tauri 壳还是 WebView APK / PWABuilder」这条待确认项从 08-25 挂到现在。
  若走 PWABuilder 路线，manifest 是前置条件。
- 改法：加 `webapp/public/manifest.webmanifest` + 512/192 图标 + favicon，`index.html` 补 link 标签。

#### P3-6 移动端细节 【未做】

- `100vh` 用于 `App.vue:67` 与 `main.css:58`，移动浏览器地址栏收起/展开会导致高度跳动 → 宜换 `dvh`。
- 地图固定 440px（`MapView.vue:17`）在小屏偏高。
- 输入框无 `inputmode` / `enterkeyhint`。
- 无手势与触摸专属交互（下拉刷新、卡片滑动、底部抽屉）。
- 好消息：响应式基础扎实 —— 720px 断点 5 处，design-audit 已验证 390/768/1280 无横向溢出、按钮 ≥32px。

#### P3-7 无障碍补强点 【未做】

- combobox 缺 `aria-controls` / `aria-activedescendant`（`PlaceInput.vue:150,170`），屏读器听不到高亮项。
- **全项目无 `aria-live`**（浏览器实测确认为 0），异步出结果时不播报。
- 无「跳至主内容」链接；视图切换后焦点不转移。
- 好消息：基础已达标 —— 标签绑定、`aria-invalid`、combobox/listbox/radiogroup/meter 语义、
  `:focus-visible`、`.bh-sr`、`prefers-reduced-motion` 均已实现，
  且 `design-audit.mjs` 39 项全通过（含 WCAG AA 对比度实算）。

#### P3-8 工程环境与文档 【未做】

- **本机 `D:\software\Python` 完全没装后端依赖**（fastapi/uvicorn/pytest/httpx/requests-mock 全缺）。
  且 PyPI 直连 SSL 握手失败，需走清华镜像 `-i https://pypi.tuna.tsinghua.edu.cn/simple`。
- **Node v20.12.0 低于 vite/vitest 要求的 `^20.19.0 || >=22.12.0`**，
  导致 `npm run build` 与完整 vitest 在本机跑不通。
  dist 已是最新，不改前端代码可以不管；**要改前端就必须先升 Node 到 20.19+ 或 22.12+**。
- `backend/requirements.txt` 缺 `pytest-timeout`（`testing.md` 与团队习惯里用到了 `--timeout` 参数）。
- 无 `pytest.ini` / `pyproject.toml`，无 `.env.example`。
- `docs/superpowers/specs/blockers.md` 是**空文件**，而 `team.md:219` 指定它作为阻塞跟踪载体。
- `status/2026-08-26.md:4` 把 `test_get_candidate_routes_uses_fallback_when_amap_missing`
  归到 `tests/test_main.py`，实际它一直在 `tests/test_route_engine.py:35`（git 历史两个提交上均如此）。
- 全线无重试无缓存。

## 二、修改计划

### 阶段划分与前置条件

阶段 0 是其余阶段的前提，必须先做。阶段 1 让产品跑在真实数据上；阶段 2 补质量门槛、断网兜底与安全洞；
阶段 3 是加分项。高德 Key 已配置并验证，原「配不配 Key」的决策点已关闭。

#### 阶段 0：环境就绪（成员 B + 成员 A，约 30 分钟，可并行）

无论改哪一条，先把「能验证」这件事解决掉，否则改完无法确认。

1. 成员 B 建后端虚拟环境并装依赖：

   ```bash
   cd backend
   python -m venv .venv
   .venv\Scripts\activate
   pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
   pip install -i https://pypi.tuna.tsinghua.edu.cn/simple pytest-timeout
   python -m pytest -q          # 期望 36 passed
   ```

   顺手把 `pytest-timeout` 加进 `requirements.txt`。

2. 成员 A 升级 Node 到 20.19+ 或 22.12+，然后：

   ```bash
   cd webapp
   npm install
   npm run build       # 当前 Node 版本下会失败，升级后应通过
   npm run test:run
   ```

   **只有需要改前端代码时才必须做这一步**；不改前端则 dist 已是最新，可跳过。

3. 两人各自确认基线：后端 36 passed、前端构建通过。基线不绿就先修基线，别叠加新改动。

#### 阶段 1：接入高德真实数据（约 3.5 小时）

**决策已定（2026-08-28）：配高德 Key。** Key 已申请为 Web 服务类型、写入 `backend/.env`、
四个接口实测可用、数字签名未开启。原「配不配 Key」这个从 08-25 挂到现在的待确认项已关闭。

这一阶段的四步**有强依赖，顺序不能乱**：

| 序号 | 任务 | 预估 | 为什么必须在此位置 |
| --- | --- | --- | --- |
| 1 | 加 dotenv 加载（`main.py` + `requirements.txt`） | 10 min | 不做这步 `os.getenv("AMAP_KEY")` 读不到文件，后面全都验不了 |
| 2 | P1-4 坐标系转换（新建 `coord.py`） | 40 min | 不先做，改完看地图仍偏 450 米，分不清是哪个问题 |
| 3 | P1-0 两段拼接替代 waypoint | 1 h | 需在 2 之后（polyline 转换点已就位） |
| 4 | P1-1 候选截断到 3 个 + 线程池并发 + 8 秒总预算 | 1 h | **必须与 3 同批**，否则第 3 步让接口变成 100 秒 |

做完这四步，任意起终点都能拿到真实路线（278 个折线点、13 段真实转向指令）与真实 POI，
「制造一点意外」这个卖点第一次建立在真数据上。

#### 阶段 2：质量与兜底（约 3 小时）

| 序号 | 任务 | 预估 | 说明 |
| --- | --- | --- | --- |
| 5 | P1-3 读 `biz_ext.rating` + rating ≥ 3.5 门槛 + 类别排除 | 30 min | 不做则所有评分为 0，且会推荐烟酒店 |
| 6 | P1-2 沿线 25%/50%/75% 三点采样 | 40 min | 候选从 20 个变 60 个，可与第 4 步的线程池合并 |
| 7 | P0-3 校正四份兜底表 + P0-4 途经点按最近线段插入 | 1 h | **最大风险点**，断网保险，四处必须同步 |
| 8 | P0-1 路径穿越 + P0-5 补两接口 + P1-5 异常兜底与测试隔离 + 叙事模板 + 搜索联想 | 1.5 h | 安全与卫生，可分批 |

第 7 步的坐标定稿值已由高德地理编码给出（见 `status/2026-08-28-handover.md`），不需要再查。
第 8 步里的「搜索联想」是个顺带收获：Key 含 `/v3/assistant/inputtips`，
可以真正实现前端一直在调但 404 的 `GET /api/place/suggest`。

完整的分步实施说明、每步验证方法、以及全部实测数据，见
**`docs/superpowers/status/2026-08-28-handover.md` 的「八步改造」一节** ——
那份文档是给接手者的操作手册，本文档是问题清单。

#### 阶段 3：加分项（时间够再做，按性价比排序）

有富余时间就从上往下做，做一条算一条，互相不依赖：

| 优先 | 任务 | 负责人 | 预估 | 理由 |
| --- | --- | --- | --- | --- |
| 1 | P3-4 基准路线 vs 推荐路线同图对比 | A + B | 1.5 h | 叙事上最值钱，直接强化「换一条路」的卖点 |
| ~~2~~ **已完成** | P2-2 反馈 → 偏好 → 打分闭环 | B | 2 h | 对齐赛题「制造一点意外」，也让 `PreferenceManager` 不再是死代码 |
| ~~3~~ **已完成** | P2-3 返回 top-N 个 POI | B | 30 min | 「沿途几个亮点」的说法才立得住 |
| 4 | P3-1 加 vue-router，起终点进 query | A | 1.5 h | 顺带解决分享功能 |
| ~~5~~ **已完成** | P2-1 评分满分对齐（7 vs 10） | B 或 A | 15 min | 一行改动，评分条不再永远填不满 |
| 6 | P3-3 点 POI 时 `panTo` | A | 15 min | 一行改动，联动手感明显变好 |
| ~~7~~ **已完成** | P2-6 fallback 生成分段转向指令 | B | 1 h | 让「路线指引」区块不再只有 1 段 |
| 8 | P3-2 地图选点 + 我的位置 | A | 1.5 h | 评委最容易追问的交互缺失 |
| 9 | P3-7 补 `aria-live` + combobox 关联属性 | A | 40 min | 无障碍从「基础达标」到「完整」 |
| 10 | P3-5 PWA manifest + 图标 | A | 1 h | 若走 PWABuilder 打 APK，这是前置 |
| 11 | P3-6 `100vh` → `dvh`、地图高度自适应 | A | 30 min | 移动端演示更稳 |
| 12 | P1-6 预下载演示范围瓦片 | A | 1 h | 只在现场网络确认很差时才值得做 |
| ~~13~~ **已完成** | P2-5 / P2-7 / P2-8 卫生清理 | B | 40 min | 评委翻代码时更好看 |

**如果只能做一条**：做 P3-4（基准 vs 推荐对比）。它是唯一能直接放大产品卖点的改动。
上表里的 P2 条目已全部完成，剩下的都是 P3 前端项 —— 而前端受 Node v20.12.0 阻塞，
动之前先读交接文档里关于 `webapp/dist` 手工补丁的那一节。

### 验收清单

每个阶段做完，按对应清单逐条核对再往下走。

#### 阶段 0

- [ ] `cd backend && python -m pytest -q` → 全绿（改造后基线 193 passed，原文写的 36 已过时）
- [ ] （若需改前端）`cd webapp && npm run build` 通过
- [ ] （若需改前端）`npm run test:run` 全绿

#### 阶段 1

- [ ] 代码确实读到了 Key（后端日志出现高德请求，或临时 `print(bool(os.getenv("AMAP_KEY")))` 为 True）
- [ ] 折线在地图上贴合街道（整体偏移 300 米以上说明坐标转换未生效）
- [ ] 拿真实 WGS-84 坐标请求，返回 polyline 首点仍约等于输入值（转过去再转回来）
- [ ] `route_engine.py:59` 那行无效的 `waypoint` 参数已删除
- [ ] 返回的 polyline 点数远大于 6（真实路径 200+ 点），steps 段数大于 1
- [ ] `detour_minutes >= 0`（两段拼接的负绕行已 clamp）
- [ ] **任意**一对大连坐标（不在写死表里）也能拿到 POI ≥ 1、绕行 > 0、评分 > 0
- [ ] 单次 recommend 端到端 < 8 秒（`curl -w "%{time_total}"`，前端 20 秒 abort）
- [ ] `python -m pytest -q` 仍全绿
- [ ] 浏览器控制台无报错

#### 阶段 2

- [ ] POI 评分不再全为 0，且返回的候选 rating ≥ 3.5
- [ ] 候选名字里不出现「烟酒」「便利」「超市」「农产品」
- [ ] 沿线采样后 POI 数量明显多于只取中点（实测 60 vs 20）
- [ ] 三组脚本场景仍 `demo_mode: true`、绕行 > 0、POI 非空（四张兜底表未漏改）
- [ ] `+15` / `roam` 的 polyline 无反向折返
- [ ] `curl "http://localhost:8000/../../.git/config"` 不返回 git 配置内容
- [ ] 点「收藏这条路线」不显示「收藏失败」
- [ ] 拔网线模拟外部服务不可用 → 仍返回兜底结果，不 500
- [ ] `LLM_API_BASE=http://10.255.255.1:9/x LLM_MODEL=demo python -m pytest -q` 仍 36 passed
      （验证 conftest 的 env 隔离 fixture 生效）

#### 演示前最终回归

- [ ] 后端 `python -m pytest -q` 全绿
- [ ] 前端 `npm run build` + `npm run test:run` 全绿
- [ ] `npm run smoke` 40/40、`npm run audit:design` 39/39
      （需先 `node node_modules/playwright/cli.js install chromium`）
- [ ] 从 `webapp/dist` 重新构建并提交，确认后端托管的是最新产物
- [ ] 三组脚本场景 + 至少 2 组即兴输入，各跑一遍完整流程
- [ ] 断开外网跑一次：地图灰底但折线、标记、指标、叙事仍完整
- [ ] 手机浏览器开一次（同一 Wi-Fi 访问本机 IP），确认无横向溢出、按钮可点

### 风险与注意事项

- **P0-3 是牵连面最大的一条改动。** `route_engine.py:8-48`、`poi_explorer.py:59-72`、
  `narrative.py:5-21` 三张表共用同一套坐标 key，`webapp/src/constants.js` 里还有第四份。
  改之前先把定稿坐标表写在一处，四个地方同步替换，改完立刻重跑三组场景 —— 漏掉任何一处，
  演示场景会静默掉进兜底分支，表现为「绕行 0 分钟、0 个亮点」，和 P0-2 的症状一模一样，很难区分。
- **不要在演示当天升 Node。** 若要改前端，提前一天升级并跑通构建。
- **dist 必须与源码同步提交。** 后端直接托管 `webapp/dist`，改了 `src` 忘了 build 等于改动没生效。
  目前 dist 已确认是最新的，别让它落后。
- **P1-3 与 P1-4 无法在无 Key 环境验证**，属推断。配 Key 后要实际打一次响应确认，别当成已修好。
- **改动边界遵守 `team.md:102-106`**：成员 A 改 `webapp/`，成员 B 改 `backend/`。
  本计划里 P0-3 需要两人同改坐标表，是唯一的跨界项，提前约定好谁先提交。
- **`blockers.md` 目前是空文件。** 阶段 1 开始后，每条卡住超过 30 分钟的问题都往里记
  （描述、负责人、影响、状态），别只在群里说。

### 时间估算汇总

| 阶段 | 内容 | 预估 | 是否必做 |
| --- | --- | --- | --- |
| 阶段 0 | 环境就绪（建 venv、装依赖） | 30 min | 必做 |
| 阶段 1 | 接入高德真实数据（第 1-4 步） | 3.5 h | 必做 |
| 阶段 2 | 质量与兜底（第 5-8 步） | 3 h | 必做 |
| 阶段 3 | 加分项 13 项全做 | 约 12 h | 选做 |

**最小可交付路径**：阶段 0 + 阶段 1 = 约 4 小时。做完这四步，任意起终点都能拿到
真实路线与真实 POI，核心卖点第一次建立在真数据上。

**推荐路径**：阶段 0 + 阶段 1 + 阶段 2 = 约 7 小时。补上质量门槛、断网兜底与安全洞。

**如果阶段 3 只能做一条**：做 P3-4（基准路线 vs 推荐路线同图对比）——
它是唯一直接放大「换一条路」这个卖点的改动。
