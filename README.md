# 偶遇导航 · Serendipity Navigation

> 去同一个目的地，换一条路。

一个基于高德真实数据的步行路线推荐应用。你给出任意可解析的起点、终点，和一个
「愿意多花多少时间」的预算，它在这个预算内挑一条更值得走的路 —— 按你的选择
真实途经 1、2 或 3 个值得停留的地方 —— 并把
「为什么是这条」摊开讲清楚。

和常规导航的区别在于目标函数：常规导航求最快，这里求「在你给的时间预算内，探索价值最高」。

## 界面

### 首页：填起终点，选探索程度

![首页](docs/images/home.png)

### 结果页：路线、指标、亮点、理由

![结果页](docs/images/result.png)

## 功能

**三档探索程度**　`+5` 顺手一绕 / `+15` 值得一趟 / `漫游` 随便走走。三档的差别不只是
绕行上限，还包括「愿意为一个地方偏离主路多远」—— 同一条路线换个档位，选中的地方和
走的路都会变。结果页可以就地切换档位反复对比。

**同图对比**　推荐路线（蓝实线）和原本的最快路线（灰虚线）画在一张图上，换掉了什么一眼看得见。

**多地点绕行**　用户可一次选择绕 1、2 或 3 个地方。系统先在高德步行基准路线周围建立
自适应搜索走廊，用真实 POI 分类、评分、类别多样性、偏离距离和用户偏好初筛，再按路线
前后顺序把入选地点作为分段终点，逐段调用高德步行规划并拼成完整路线。图上的每张地点卡
都是路线真实经过的途经点，不拿“附近但没经过”的地点凑数。

**探索评分**　7 分制，由亮点质量、口味契合度、绕行代价三项加减得出，结果页把这三项拆开显示。
凑不出自洽的拆分时只报总分，不摆一组加不出总数的数字。

**推荐理由**　用高德返回的真实字段说话：地点名称、分类、地址、评分（缺失时明确写暂无评分）、
电话、营业时间、照片，以及它原本偏离路线多远、多花的时间是否在额度内。没有可核实地点时
接口明确失败，不生成假的推荐理由。

**反馈闭环**　对路线点「还不错」或「一般」，系统按亮点类型记住偏好，影响后续推荐的打分。
界面会告诉你这次到底学到了什么类目 —— 没归因上也照实说。

**全国地点联想**　输入框直接使用高德 Inputtips，不再锁定大连；也接受 `经度,纬度` 直接输入。
高德不可用时页面明确报错，不把本地演示地点伪装成联想结果。

**真实数据门禁**　正式推荐必须同时拿到高德路线与高德 POI。没有 Key、Key 失效、限流或网络失败时
返回明确错误；内置数据只保留给隔离的单元回归，生产流程默认无法启用。

## 技术栈

| 层 | 选型 |
|---|---|
| 后端 | FastAPI + Python 3.11 |
| 前端 | Vue 3 + Vite |
| 地图 | Leaflet + OpenStreetMap 瓦片 |
| 数据 | 高德 Web 服务（步行路径 / POI / 地理编码 / 输入提示） |

坐标系约定：对外统一 WGS-84（前端、内置数据），对高德统一 GCJ-02，转换只在出入口各做一次。

## 启动

### 1. 后端

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate      # macOS / Linux
pip install -r requirements.txt
uvicorn app.main:app --reload
```

后端起在 `http://localhost:8000`，并同源托管 `webapp/dist` 里已构建好的前端。
未配置高德 Key 时健康接口会返回 `ready: false`，真实推荐不会启动。

### 2. 配置高德（必需）

复制 `backend/.env.example` 为 `backend/.env`，填入 Web 服务 Key：

```
AMAP_KEY=你的高德 Web 服务 Key
```

重启后端即生效。Key 从[高德开放平台](https://lbs.amap.com/)申请，必须选「Web 服务」类型。

### 3. 前端开发模式（改前端代码时用）

```bash
cd webapp
npm install
npm run dev
```

前端起在 `http://localhost:5173`，接口自动代理到 8000 端口的后端，改代码热更新。
需要 Node 22.12 以上（仓库里有 `.nvmrc`）。

改完前端要让后端托管的版本也更新，重新构建一次：

```bash
npm run build
```

### 4. 快速上手

打开页面，点首页底部「快速体验」里任意一个卡片（大连理工大学 → 星海广场 / 东港 → 老虎滩 /
西安路 → 傅家庄），直接看结果。到了结果页可以点右上角三个档位反复对比。

## 测试

```bash
# 后端
cd backend
.venv\Scripts\python.exe -m pytest -q

# 前端单元测试
cd webapp
npm run test:run

# 真实高德全链路（不使用 mock；会消耗 API 配额）
cd backend
RUN_LIVE_AMAP=1 AMAP_KEY=你的Key .venv/bin/python -m pytest -q tests/test_amap_live.py
```

## 目录

```
backend/          FastAPI 后端
  app/routes/     接口层
  app/services/   路径规划、POI、评分、叙事、坐标转换
  app/models/     用户偏好
  tests/          pytest
webapp/           Vue 3 前端
  src/views/      首页、结果页
  src/components/ 地图、指标块、亮点卡片、评分条等
  tests/          vitest 组件与交互回归
docs/             计划、分工、进展记录
```

## 数据来源

地图数据 © [OpenStreetMap](https://www.openstreetmap.org/copyright) contributors，
路径与 POI 数据来自[高德开放平台](https://lbs.amap.com/)。
