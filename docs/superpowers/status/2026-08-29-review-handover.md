# 审查方接手文档（给接替代码审查工作的 AI）

> 配套文档：`2026-08-29-handover-3.md`（给干活方）、`2026-08-29-node-switch-guide.md`（给人）
> 基线提交：`44c8cd7`
> **这份文档是给「和用户一起做 review」的那个会话用的，不是给干活的会话用的。**
> 两个会话分开：一个改代码，一个审。别在同一个会话里做两件事 ——
> 审自己刚写的代码，会倾向于确认而不是挑战。

---

## 第一部分：给接手审查 AI 的提示词

把下面整段直接发给新会话。

```
你和我一起作为项目审查人，审查另一个 AI 提交的代码工作。你不写功能代码，
你的产出是判断：哪些声称是真的、哪些是假的、哪里还有没被发现的缺陷。

先读这三份文档：
1. docs/superpowers/status/2026-08-29-review-handover.md  ← 本文档，审查方法和已知陷阱
2. docs/superpowers/status/2026-08-29-handover-3.md        ← 干活方的任务清单，你审的就是这些
3. docs/superpowers/plans/2026-08-28-optimization-plan.md  ← 问题清单全貌

环境：
- 项目在 D:\claude\黑客松\hackathon-dut，Windows + PowerShell。
- 后端测试必须用虚拟环境：cd backend 然后 .venv\Scripts\python.exe -m pytest -q
  （系统 python 没装依赖）。当前基线 193 passed。
- 前端在 Node 22 下：cd webapp 然后 npm run test:run。当前 3 failed | 74 passed，
  那 3 条是已知待修的。Node 22.23.2 已经是 current，不要跑 nvm use ——
  它改全局符号链接而 claude 只装在 20 下，照做会当场终止你自己的会话。
- 改坏代码验证守卫时，读写文件一律用绝对路径。相对路径会拼到残留的 cwd 上，
  静默不写文件，然后你会看到一个假的「193 passed」并误判守卫失效。

核心纪律（前三轮靠这条抓出两个真 bug 和一处半修复）：
不要相信工作报告，实际跑一遍。报告说「修好了，N passed」就自己跑一次 pytest；
报告说「某个测试能防住回归」就把代码改坏，看它是否真的变红，然后按字节还原。
报告的数字对不上、或者你复现不出它声称的现象，先怀疑报告。

同时不要为了显得严格而挑刺。前三轮有两轮的报告是准确的，我确认之后就说准确了。
你的价值在于分辨，不在于总能找出问题。
```

---

## 第二部分：审查方法（这三轮实际用过的）

### 1. 先跑，再读

拿到报告第一件事是跑测试，不是读 diff。三轮里报告的数字（169 / 180 / 193）每次都对得上，
但这不是可以省略的理由 —— 数字对不上就意味着后面所有结论都不可信。

```powershell
cd backend; .venv\Scripts\python.exe -m pytest -q
cd ..\webapp; npm run test:run
```

### 2. 验证守卫测试真的会变红

这是三轮里最有效的一招。工作方声称「加了测试钉住这条」时，把被保护的代码改坏，
看测试是否真的失败，然后**按字节还原**。

实际做法（PowerShell，读字节而不是文本，避免编码和行尾被改）：

⚠️ **路径必须是绝对的**（这是第四轮踩过的坑，上一版这里写的是相对路径 `"app\models\preference.py"`，
照抄会静默不写文件，pytest 照样 193 passed，看起来像守卫失效）：

```powershell
$root = "D:\claude\黑客松\hackathon-dut"
$f = "$root\backend\app\models\preference.py"
$orig = [System.IO.File]::ReadAllBytes($f)
$t = [System.IO.File]::ReadAllText($f)
$mod = $t.Replace("正确的那行", "退回旧行为的那行")
[System.IO.File]::WriteAllText($f, $mod)
"patched: " + ($mod -ne $t)          # 必须 True —— 确认改坏这一步真的生效了
Set-Location "$root\backend"
& ".\.venv\Scripts\python.exe" -m pytest -q 2>&1 | Select-String "FAILED|passed|failed"
[System.IO.File]::WriteAllBytes($f, $orig)
if ([System.Linq.Enumerable]::SequenceEqual([byte[]]$orig, [byte[]][System.IO.File]::ReadAllBytes($f))) { "RESTORED OK" }
```

最后那行还原确认不能省。改的是演示要用的代码，还原失败比不验更糟。
`SequenceEqual` 那两个 `[byte[]]` 强转也别省 —— 不加会因为重载解析失败报错，
而报错时文件已经还原了，容易误以为还原失败而重复操作。

**已实测的守卫变红数字**，复现得出这些数字说明守卫还在：

| 改坏什么 | 期望结果 |
|---|---|
| 只改 `constants.js` 六个坐标之一 | 1 failed / 192 passed |
| 同时改 `constants.js` + `dalian.py`（假修复） | 3 failed / 190 passed |
| `preference.py` 退回实例 1（`specific + broad` 都记） | 4 failed / 189 passed |
| `preference.py` 退回实例 2（未知类型共用 `UNKNOWN_TAG`） | 5 failed / 188 passed |

**这一招抓到过什么**：第三轮工作方声称两条守卫「形状不同，缺一条就漏一个实例」。
我分别退回两种旧行为验证，得到 5 红和 4 红，确认了这个说法 —— 结构性守卫（按大类聚合）
抓不到实例 1，因为那个 bug 的所有标签都在同一个大类下。这不是能靠读代码看出来的。

### 3. 用探针脚本打表，而不是推理

判断一个数据变换对不对，写个临时脚本把真实输入喂进去打表。前三轮那个真 bug
就是这么找到的 —— 读代码只能看出「affinity 取平均」，打表才看出它让一次咖啡反馈
把海鲜和烧烤一起压到 -0.167。

```powershell
# 写 backend\_probe.py，跑完立刻删
& ".\.venv\Scripts\python.exe" _probe.py; Remove-Item _probe.py
```

用完删掉。第三轮我有一次忘了删，`git status` 里多出一个 `_p.py`。

### 4. 二进制产物不能靠读 diff

`webapp/dist/assets/*.js` 是 minify 过的单行文件，`git diff` 完全不可读。
审查它必须用「关键标记出现次数对比」：

```powershell
$old = Get-Content "webapp\dist\assets\index-旧.js" -Raw
$new = Get-Content "webapp\dist\assets\index-新.js" -Raw
foreach ($m in @("121.5839,38.8816","121.5854,38.9325","trip_id","/poi/")) {
  $a = ([regex]::Matches($old, [regex]::Escape($m))).Count
  $b = ([regex]::Matches($new, [regex]::Escape($m))).Count
  "{0,-22} 旧={1,-3} 新={2,-3} {3}" -f $m, $a, $b, $(if ($a -eq $b) {"OK"} else {"DIFF"})
}
```

要定位差异位置，逐字符找第一个分歧点再取上下文 —— 我就是这么发现手工 dist 里
残留 `/poi/${id}` 的（`fetchPoiDetail` 在源码里早删了，说明 dist 是旧源码产物）。

### 5. 跨模块的失败先怀疑环境，别急着下结论

见第四部分「我犯过的误判」。

---

## 第三部分：这个项目已知的 bug 模式

### 「共享桶」——已出现两个实例，都在 `preference.py`

一个标签被多个不相关的东西共用，于是对 A 的反馈污染了 B。

- **实例 1**：`餐饮服务;咖啡厅` 同时记「咖啡」和「餐饮」，父类目「餐饮」把
  海鲜、烧烤一起拖下去（各 -0.167）。修法：命中具体子类目就不记宽泛父类目。
- **实例 2**：所有认不出的类型共用一个「其它」桶，于是不喜欢一个度假场所会让
  药店、酒店、电影院一起沉底。修法：按 type 串的大类（第一段）单独成桶。

**为什么值得单独记**：实例 1 修好之后，实例 2 在同一个函数里又活了 24 小时，
因为当时的测试只覆盖了一种形状。**看到这类修复，一定要问「同一个形状还有别处吗」**。

现在有两条守卫，形状不同，缺一条就漏一个实例：
- `test_no_tag_is_a_shared_bucket_across_unrelated_categories`（按大类聚合，抓实例 2）
- `test_no_type_carries_both_a_specific_tag_and_a_broad_one`（抓实例 1）

有意的跨大类合并写在 `INTENTIONAL_CROSS_CATEGORY_TAGS = frozenset({"风景", "人文"})` 白名单里
（高德把景点分散在「风景名胜」和「旅游景点」两个大类；书店挂在「购物服务」下但
用户心里它和博物馆是一类）。往 `TAG_KEYWORDS` 加词时，新的共享桶会自动变红，
这两个有意的不会。

**位置更正（第四轮复验）**：这个白名单在 `backend/tests/test_preference.py:171`，
**不在** `preference.py` 里 —— 本文档上一版把它记在产品代码里，找不到会白花时间。
它是测试自己的常量，所以「哪些跨大类合并是有意的」这个判断属于测试，不属于实现。

### 「恒定值」—— 一维参数实际上从不变化

`scorer.score` 原来收 `matched_tags`，算 `len(matched_tags) * 3.0`，
而唯一的调用方永远传单元素列表 → 这一维恒等于 3.0，「标签匹配」完全没参与决策。
类似地 `pois` 曾经写死 `[chosen["poi"]]`，「沿途几个亮点」永远只有一个。

**审查时的检查点**：看到一个参数，去看调用方实际传什么。签名允许变化不等于真的变化。

### 「静默兜底掩盖错误」

- 坐标解析失败曾返回天安门坐标 → 用户拿到一条北京的路线，且不知道出错了
- 候选路线来自兜底数据、基准来自真实高德 → 算出一个看起来合理、实际编造的绕行
  （`_evaluate_candidate` 里有 `source` 一致性检查防这个）

**检查点**：看到 `except: pass`、默认值、fallback，问「出错时用户看得出来吗」。

---

## 第四部分：我犯过的误判（照抄这里的教训，别重犯）

### 把超时抖动误判成跨模块耦合

第三轮我退回一处偏好逻辑跑全量，看到 5 条失败，其中一条是
`test_poi_explorer::test_explore_pois_along_route_samples_three_points_of_polyline` ——
一个完全不 import 偏好模块的文件。我当时怀疑是跨模块耦合。

查下来不是：单独跑那条通过，之后连跑 5 轮全量都是 193 passed，该条从未再红。
`pytest.ini` 设了 `timeout = 20`，那次是满负载下的超时抖动。工作方报的 4 红是对的，
我多出来的那一条是环境噪声。

**教训**：跨模块的失败先验「单独跑是否通过」和「能否复现」，再下结论。
一次性的失败在满负载机器上很常见。这条测试在演示当天机器忙时可能再红一次，
先怀疑超时。

### 把控制台编码问题误当成文件损坏

我用 PowerShell 读 `pytest.ini` 时看到一堆乱码，差点以为文件坏了。
按字节读出来按 UTF-8 解码是完全正常的中文注释 —— 是控制台解码问题，不是文件问题。

**教训**：中文内容看起来乱码时，先按字节读出来分别用 UTF-8 和 GBK 解一次确认。

### 建议里带了会毁掉自己的命令

我一度建议「只差一条 `nvm use 22.23.2`」。但 `nvm use` 改的是全局符号链接，
而 claude 只装在 20 下 —— 照做会当场终止我自己所在的会话。我当时能跑通构建，
是因为绕开了 `nvm use`，直接用绝对路径调 22 的 node.exe。

**教训**：给出会改变全局环境的命令前，先想它对当前运行环境有什么影响。

---

## 第五部分：不变量（改任何东西都不能破坏）

| 不变量 | 守卫测试 | 破坏后的症状 |
|---|---|---|
| `constants.js` 六个演示坐标 == `dalian.py` 的 `LANDMARKS`，逐字节 | 单边改动：`test_frontend_constants_match_backend_landmarks`；两边同改：另三条，见本节下方更正 | 断网演示静默退化成「0 分钟、0 亮点、两点直线」，台上很难当场发现 |
| 评分上限 7.0 == `ScoreMeter.vue` / `format.js::scoreToPercent` | `test_scorer.py::test_score_upper_bound_stays_seven` | 评分条永远填不满或爆表 |
| 断网演示 9 组（三场景 × 三模式）全部命中兜底表 | `test_dalian_scenarios.py::test_offline_demo_nine_combinations`（参数化） | 演示当天断网就没有准备好的路线 |
| 候选与基准必须同源（都真实或都兜底） | `_evaluate_candidate` 里的 `source` 检查 | 显示一个编造的绕行分钟数 |

**审查前端改动时特别注意第一条**：那六个坐标不能为了让前端测试变绿而改。
正确方向是改测试里的旧坐标（`121.5854,38.9325` 是星海广场偏 5.7 km 的旧值）。
如果工作方改的是 `constants.js`，后端会立刻变红。

**更正（第四轮实测）**：上一版接着写「但如果它同时改了 `dalian.py` 让两边一致，
测试会绿而演示会坏 —— 这是本项目最危险的一种假修复」。**这个判断偏保守，实测不成立。**

我按字节改坏两边跑了全量，得到 `3 failed / 190 passed`。挡住它的是这三条：

- `test_dalian_scenarios.py::test_scenario_polyline_endpoints_match_landmarks`
- `test_narrative.py::test_handwritten_demo_narrative_wins_over_template`
- `test_route_engine.py::test_get_candidate_routes_reverses_demo_polyline_for_reverse_trip`

而表格里点名的 `test_frontend_constants_match_backend_landmarks` **在这种情况下是绿的** ——
它只断言「每个后端坐标在前端源码里出现过」，从不反向检查前端有没有多出别的坐标。
它能抓的是单边改动：只改 `constants.js` → `1 failed / 192 passed`。

**审查时的实际做法**：动过坐标就看那三条，别只看被点名的那条。
这条「最危险的假修复」现在有结构性防护，不需要每轮人工盯 —— 省下的注意力
留给真正没有守卫的地方（比如 `webapp/tests/mock-server.mjs` 的旧坐标 key，
它不在任何测试的覆盖范围内，第四轮才发现）。

---

## 第六部分：当前待审查的具体工作

干活方接下来会做三件事（详见 `handover-3.md` 第三部分），审查要点：

### 1. 修 3 条前端测试（实际是 4 个文件）

- 期望结果：`npm run test:run` → 77 passed
- **必查**：改的是 `webapp/tests/` 里的旧坐标，不是 `constants.js`。
  用 `git diff -- webapp/src/constants.js` 确认它没被动过。
- **必查**：后端仍 193 passed（坐标一致性测试会读 `constants.js`）
- **必查（第四轮新增）**：`tests/mock-server.mjs` 的表 key 也改了。
  这个文件不在 vitest 覆盖范围内，所以 77 passed **不能**证明它改对了。
  验法：`git diff -- webapp/tests/mock-server.mjs` 应该看到第 15 行的 key、
  第 25/26 行的 `route.origin`/`destination`、第 31 行 polyline 首尾点都换了新坐标。
  详见第八部分。
- **必查（第四轮新增）**：工作方真的跑了 `npm run smoke`，且报的是实际数字。
  只报 `test:run` 的 77 passed 就宣布完成，是不完整的 —— smoke 有三条断言依赖
  `mock-server.mjs` 的场景表。它若报「smoke 40/40」而没先装 chromium，数字是编的。
- **不该改的**：`api.test.js`、`geo.test.js`、`ResultView.test.js` 里也有旧坐标，
  但那些是任意夹具、不断言真实坐标。工作方顺手改了它们不算错，但要问清动机 ——
  分不清「必须改」和「顺手改」的人，下一次可能会顺手改 `constants.js`。

### 2. 重新构建 `webapp/dist`

这一步风险最高，因为产出的是演示当天要用的产物，而 diff 不可读。

- **必查**：用第二部分第 4 条的标记对比法，确认新坐标在、旧坐标不在、`trip_id` 有 2 处
- **必查**：`dist/index.html` 引用的 bundle 文件名与实际文件一致（构建后文件名会变）
- **省事的验法（第四轮用过）**：不必等工作方构建，也不必碰 `dist` ——
  自己 `npx vite build --outDir $env:TEMP\xxx --emptyOutDir` 构建一份到临时目录，
  再和 committed dist 做标记对比。实测新产物是 `index-fml4M2Q9.js`、311 毫秒。
  已知的正常差异只有两处：JS 的 `/poi/`（1→0）和 CSS 的 scoped 哈希
  （`ba39787b`→`ab0d40c6`）。**出现第三处差异就要查。**
- **必查**：起 `uvicorn app.main:app`，删掉 `.env` 里的 `AMAP_KEY` 或拔网线，
  浏览器跑一遍三组断网演示，确认三组都有折线、亮点、文案
- **恢复路径**：`git checkout 44c8cd7 -- webapp/dist`（我验证过这个提交里的 dist
  含新坐标 1 次、旧坐标 0 次，恢复是安全的）

### 3. P3-4 基准路线 vs 推荐路线同图对比

- 后端只需在响应里多带 `baseline_route`（`baseline` 变量已存在，在 `api.py:110`）
- **必查**：`baseline` 的 polyline 已经是 WGS-84（`route_engine.py:165` 出口转过），
  前端不能再转一次 —— 转两次会偏移约 450 米
- **必查**：`route` 和 `baseline_route` 两条响应形状是否一致（P2-5 修过这类问题）
- **必查（第四轮新增）**：`recommend_route` 有**两个** return 出口 ——
  `api.py:137`（`_choose_candidate` 没选出候选时的降级返回）和 `api.py:150`（正常返回）。
  `baseline_route` 必须两处都加。只加正常出口的话响应形状变成条件式的，
  前端拿不到就静默不画灰虚线、也不报错，表现为「有时有对比有时没有」——
  这正是 P2-5 那一类隐性依赖。**读 diff 时直接看这两行附近，别只看正常路径。**
- **必查**：有没有一条测试断言两个出口的响应同形。只测正常路径的话，
  降级路径的形状回归不会被任何测试抓住。

---

## 第七部分：还没有人验过的东西

诚实记录，别当成已经没问题：

- **前端 74 条通过的测试我没有逐条读过**。只确认了 3 条失败的根因。
- **真实浏览器端到端从未在 Node 22 构建的产物上跑过**。手工 dist 在浏览器里
  验过（前几轮），真实构建的产物没有。
- **付费高德调用从第二轮之后就没再跑过**。P1-3/P1-4 的实测数据来自第一轮，
  是可信的，但之后的改动没有再打真实接口验证。演示前应该真打一次。
- ~~**`npm run smoke`（40 项）和 `npm run audit:design`（39 项）从未在 Node 22 下跑过**~~
  → 第四轮已查明这条不只是「没跑过」，而是**现在跑必然红 3 条**，见下。

---

## 第八部分：第四轮审查的新发现（2026-08-29）

### 已确认的缺陷：`mock-server.mjs` 的旧坐标 key（未修）

`webapp/tests/mock-server.mjs:15` 的 `SCENARIOS` 表 key 仍是 P0-3 校正前的旧坐标
`121.6068,38.9180->121.5854,38.9325`，而 `constants.js` 演示场景 1 现在发的是
`121.5197,38.8856->121.5839,38.8816` → 这张表**从 UI 完全命中不了**。

用第二部分第 3 条的探针手法实测（起真实 mock 服务打表，不是读代码）：

```
新坐标（演示按钮实际发的）→ pois=1, demo_mode=False, 通用文案   ← 掉进 FALLBACK
旧坐标（表里存的）        → pois=2, demo_mode=True,  「从大工沿海边走…」
```

`tests/smoke.mjs` 点第一个 `.demo` 后断言三件只有场景表才给得出的东西 ——
第 63 行 `从大工沿海边走`、第 64 行 `.poi` 数量 `=== 2`、第 66 行 `内置演示数据`。
**这三条必然失败**，而它以「40/40 通过」的身份挂在演示前最终回归清单里。

**为什么三轮没人发现**：它和「dist 比源码旧」是同一个根因 —— 一整类文件
（构建产物、smoke 用的假后端）因为 Node 跑不起来而长期没有任何验证。
vitest 也覆盖不到 `mock-server.mjs`，所以 `npm run test:run` 全绿也发现不了。

**审查含义**：`npm run test:run` 变绿**不能**作为「前端修好了」的判据。
工作方声称修完 3 条前端测试时，要追问它有没有真的跑 smoke。

### 这一轮确认为真的声称

不是每轮都得找出问题。这一轮的基线数字全部核实：

| 声称 | 实测 |
|---|---|
| 后端 193 passed | 193 passed / 10.75 秒 |
| 前端 3 failed \| 74 passed | 完全一致，三条同一个根因 |
| 两条共享桶守卫互不冗余 | 4 红 / 5 红，与第三轮数字吻合 |
| P3-4 的 `baseline` 变量已存在 | `api.py:110` |
| `baseline` 的 polyline 已是 WGS-84 | `route_engine.py:165` |
| Node 22 构建通过、文件名会变 | 311 毫秒，`index-fml4M2Q9.js`，与预测完全一致 |
| committed dist 含新坐标、评分上限 7 | 六坐标各 2 处、`trip_id` 2 处、`=7){…n/t*100}` 在 |

### 两处描述不准（结论不变，细节要更正）

1. **dist 与源码的差异不只 192 字节**：JS 侧确实只差 `/poi/`，但 **CSS 也不同** ——
   scoped 样式哈希 `ba39787b` → `ab0d40c6`，因为手工补丁之后 `ScoreMeter.vue` 源码改过，
   而手工改 bundle 改不到 scope id。不影响演示，但这是 dist 落后于源码的独立佐证。
2. **P3-4 有两个 return 出口**：`api.py:137`（无候选降级）和 `api.py:150`（正常）。
   `baseline_route` 只加一处会让响应形状变成条件式的，重演 P2-5。审查时两处都要看。

### 慢测试那条有量化支撑了

`test_poi_explorer.py::test_explore_pois_along_route_samples_three_points_of_polyline`
单独跑 3 次，每次 **0.43 秒，超时阈值 20 秒 —— 46 倍余量**。
这个比例支持第四部分「超时抖动」的判断，可以放心不改。

### 给下一个审查方的一条操作提醒

第二部分第 2 条那段改坏验证的脚本，**必须用绝对路径**。我照抄它的相对路径版本时，
`$f = "app\models\preference.py"` 拼到了残留的 `webapp` cwd 上 → 文件从未被写入，
pytest 照样输出 `193 passed`，看起来像「守卫失效了」。差点据此下错结论。
改成 `$root` 开头的绝对路径后，同一个实验立刻得到预期的 4 红。

**教训**：改坏验证得到「全绿」时，先确认改坏这一步真的生效了（打印替换命中次数），
再考虑「守卫是不是假的」。
