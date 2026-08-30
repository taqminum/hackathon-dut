/**
 * 本地联调用的假后端，仅供前端开发 / 冒烟验证使用。
 * 契约与 backend/app/routes/api.py 保持一致：
 *   GET  /health                -> { status: "ok" }
 *   POST /api/route/recommend   -> { baseline_minutes, detour_minutes, score, pois, narrative, route }
 * 未定稿接口（place/suggest、trip/save 等）返回 404，用于验证前端降级路径。
 *
 * 用法： node tests/mock-server.mjs [port]
 */
import { createServer } from 'node:http'

const PORT = Number(process.argv[2] || 8000)

const SCENARIOS = {
  // key 必须与 webapp/src/constants.js 的 DEMO_SCENARIOS[0] 起终点逐字节相同，
  // 否则演示按钮会掉进下面的 FALLBACK，tests/smoke.mjs 依赖本场景的三条断言会失败。
  '121.5197,38.8856->121.5839,38.8816': {
    baseline_minutes: 21,
    // detour_minutes 与 score 都不再写死，由 derive() 从下面的两条路线算出来，
    // 见该函数的注释。以前写死的值和路线时长打架（route 1560s - baseline 1260s
    // 是 5 分钟，而 `5 * factor` 在 +15 下给出 10 分钟），
    // 于是同一屏上「额外时间 +10 分钟」和对比块的「+5 分钟」互相矛盾。
    narrative: '从大工沿海边走，你会先遇到一间社区咖啡，再顺着海景走到星海。',
    // R6：这两条刻意做成一「全」一「缺」。真实高德下 `extensions=all` 会带回
    // address / tel / opentime / photo，但**不保证每个 POI 都有** —— 小店常常
    // 只有地址没有电话，新录入的连营业时间都没有。两种都得在同一屏上不崩、
    // 不出现「暂无」占位，所以桩里必须同时存在，不能都给全。
    // photo 用 data URI：外链图在离线冒烟里必然加载失败，那就验不到「图渲染出来」。
    pois: [
      {
        name: '理工咖啡小铺',
        type: '餐饮',
        distance: '180',
        rating: 4.4,
        // 实测距本桩 polyline 11.1 米。原来是 121.5432,38.8871，距折线 313.7 米 ——
        // 超过后端 NEARBY_POI_METERS(150)，按真后端规则它根本不该出现在列表里。
        location: '121.5480,38.8841',
        // S2：卡片上「距路线约」读的是这个字段，不是高德的 distance（那是「距搜索
        // 采样点」）。桩里必须与 polyline 自洽，否则冒烟量出来的米数和显示的对不上。
        off_route_meters: 11.1,
        address: '大连市甘井子区凌工路 2 号理工大学西门南侧',
        tel: '0411-8470-9988',
        opentime: '07:30-21:00',
        // `#` 交给 encodeURIComponent 去转成 %23。这里先写成 %23 的话会被
        // 二次编码成 %2523，fill 变成非法值，图渲染成纯黑 —— 断言只看宽高，
        // 抓不到这个，是截图看出来的。
        photo:
          'data:image/svg+xml;utf8,' +
          encodeURIComponent(
            '<svg xmlns="http://www.w3.org/2000/svg" width="160" height="90"><rect width="160" height="90" fill="#134a8e"/><circle cx="80" cy="45" r="26" fill="#e4b73f"/></svg>',
          ),
      },
      // 只有基础五字段：详情区连「展开详情」都不该出现
      // 只有基础五字段 + 实测距离：详情区连「展开详情」都不该出现。
      // 42.6 米是量出来的（距折线），310 是高德口径的「距采样点」，两者故意不同 ——
      // 卡片显示前者，这条桩数据同时钉住「不回落到 distance」。
      {
        name: '海边散步道',
        type: '景点',
        distance: '310',
        rating: 4.6,
        location: '121.5702,38.8829',
        off_route_meters: 42.6,
      },
    ],
    route: {
      origin: '121.5197,38.8856',
      destination: '121.5839,38.8816',
      // R9：离线徽标的判据。演示场景走的是后端本地兜底，所以是 fallback。
      source: 'fallback',
      demo_mode: true,
      distance: 2620,
      duration: 1560,
      polyline:
        '121.5197,38.8856;121.5310,38.8878;121.5432,38.8871;121.5561,38.8845;121.5702,38.8829;121.5839,38.8816',
      steps: [
        { instruction: '沿凌工路向西步行', road: '凌工路', distance: '620', duration: '420' },
        { instruction: '右转进入中山路', road: '中山路', distance: '880', duration: '520' },
        { instruction: '沿海岸线继续前行', road: '滨海路', distance: '700', duration: '380' },
        { instruction: '到达星海广场', road: '星海广场', distance: '420', duration: '240' },
      ],
    },
    // P3-4：原本那条路，前端画成灰虚线。刻意比推荐路线直，
    // 这样对比图上「换掉了什么」看得出来。
    baseline_route: {
      origin: '121.5197,38.8856',
      destination: '121.5839,38.8816',
      source: 'fallback',
      demo_mode: true,
      distance: 2180,
      duration: 1260,
      polyline: '121.5197,38.8856;121.5480,38.8840;121.5839,38.8816',
      steps: [{ instruction: '沿最短路径步行', road: '主路', distance: '2180', duration: '1260' }],
    },
  },
}

const FALLBACK = {
  baseline_minutes: 16,
  narrative: '这条路线上有几个值得停留的小地方，适合慢慢走。',
  pois: [
    {
      name: '偶遇小店',
      type: '餐饮',
      distance: '120',
      rating: 4.2,
      location: '121.601,38.918',
      // 实测正好落在本桩 polyline 上
      off_route_meters: 0,
    },
  ],
  route: {
    demo_mode: false,
    distance: 1620,
    duration: 1130,
    polyline: '121.5950,38.9150;121.6010,38.9180;121.6070,38.9210',
    steps: [{ instruction: '按推荐路线行走', road: '主路', distance: '1620', duration: '1130' }],
  },
}

/** 后端 SerendipityScorer 的三个权重（backend/app/services/scorer.py）。 */
const TAG_WEIGHT = 3.0
const QUALITY_WEIGHT = 4.0
const DETOUR_PENALTY_PER_MINUTE = 0.2
/** 冷启动的标签填充比例（scorer.NEUTRAL_FILL）。假后端没有反馈历史，恒为中性。 */
const NEUTRAL_FILL = 0.7

/** 从场景自己的路线数据推出 detour_minutes 和 score，而不是写死。
 *
 * 两个理由：
 * 1. 写死的 detour 会和路线时长打架 —— 结果页的「额外时间」读 detour_minutes，
 *    而 T3 的对比块读两条路线的 duration 之差，两个数字必须是同一件事。
 * 2. 写死的 score 不满足 `质量 + 契合 - 绕行惩罚`，结果页 T4 的评分拆分
 *    会（正确地）判定这份数据不是这个公式算的，于是拆分那条理由不显示，
 *    演示时看不到「这分是怎么来的」。
 *
 * 真后端的 detour 来自高德两段拼接的时长差，这里用同一个定义：
 * 推荐路线时长 - 基准时长，clamp 到 0（对齐 calculate_detour）。
 */
function derive(base) {
  const routeSeconds = Number(base.route?.duration)
  const baselineSeconds = Number(base.baseline_route?.duration ?? base.baseline_minutes * 60)
  const detourMinutes = Math.max(0, Math.round((routeSeconds - baselineSeconds) / 60))

  // 打分只看被选中的那个 POI（真后端 _score_candidate 也是这样），rating / 5 是质量
  const rating = Number(base.pois?.[0]?.rating ?? 0)
  const quality = QUALITY_WEIGHT * Math.min(1, Math.max(0, rating / 5))
  const affinity = TAG_WEIGHT * NEUTRAL_FILL
  const penalty = DETOUR_PENALTY_PER_MINUTE * detourMinutes
  const score = Math.max(0, quality + affinity - penalty)

  return { detour_minutes: detourMinutes, score: Number(score.toFixed(2)) }
}

// T8-4：反馈闭环需要「这次推荐了哪些 POI」。真后端把它记在 `_recommendations`
// 里，用自增的 trip_id 索引（api.py 的 `_remember_recommendation`），这里同形。
const _recommended = new Map()
let _tripSeq = 0
function nextTripId() {
  _tripSeq += 1
  return _tripSeq
}

/** POI 的 type 串归并成粗类目。与后端 `tags_for_type` 同一套关键词，
 * 这样 mock 下看到的 learned 和真后端下看到的是同一批词。 */
const TAG_KEYWORDS = {
  咖啡: ['咖啡'],
  餐饮: ['餐饮', '餐厅', '美食', '小吃', '面'],
  景点: ['景点', '风景', '公园', '广场'],
  购物: ['购物', '商场', '超市'],
  文化: ['博物馆', '美术馆', '书店', '图书'],
}

function tagsForType(value) {
  const raw = String(value || '')
  const tags = []
  for (const [tag, keywords] of Object.entries(TAG_KEYWORDS)) {
    if (keywords.some((word) => raw.includes(word))) tags.push(tag)
  }
  return tags
}

// R3：联想桩数据。形状照高德 inputtips 的归一化结果（name / address / location），
// 坐标是大连市内的真实门店量级取值，只用于桩，不进 constants.js 的演示数据。
const SUGGEST_STUB = {
  麦当劳: [
    { name: '麦当劳(西安路店)', address: '沙河口区西安路 123 号', location: '121.5893,38.9142' },
    { name: '麦当劳(青泥洼桥店)', address: '中山区友好路 88 号', location: '121.6335,38.9187' },
    { name: '麦当劳(星海广场店)', address: '沙河口区中山路 588 号', location: '121.5871,38.8869' },
    { name: '麦当劳(大连理工店)', address: '甘井子区凌工路 2 号', location: '121.5307,38.8806' },
    { name: '麦当劳(东港店)', address: '中山区港兴路 6 号', location: '121.6702,38.9251' },
  ],
}

function send(res, status, body) {
  const payload = JSON.stringify(body)
  res.writeHead(status, {
    'Content-Type': 'application/json; charset=utf-8',
    'Access-Control-Allow-Origin': '*',
    'Access-Control-Allow-Headers': '*',
    'Access-Control-Allow-Methods': '*',
  })
  res.end(payload)
}

createServer((req, res) => {
  if (req.method === 'OPTIONS') {
    res.writeHead(204, {
      'Access-Control-Allow-Origin': '*',
      'Access-Control-Allow-Headers': '*',
      'Access-Control-Allow-Methods': '*',
    })
    res.end()
    return
  }

  const url = new URL(req.url, `http://localhost:${PORT}`)

  if (url.pathname === '/health') {
    send(res, 200, { status: 'ok' })
    return
  }

  if (url.pathname === '/api/route/recommend' && req.method === 'POST') {
    let raw = ''
    req.on('data', (chunk) => {
      raw += chunk
    })
    req.on('end', () => {
      let body = {}
      try {
        body = JSON.parse(raw || '{}')
      } catch {
        send(res, 400, { detail: '请求体解析失败' })
        return
      }

      const { origin, destination, mode } = body
      if (!origin || !destination) {
        send(res, 400, { detail: '缺少起点或终点' })
        return
      }

      if (String(origin).includes('无结果')) {
        send(res, 404, { detail: '未找到可行路线' })
        return
      }

      const key = `${origin}->${destination}`
      const base = SCENARIOS[key] || FALLBACK

      // 换模式要看得出区别，但区别必须体现在**路线**上而不是凭空改数字：
      // 场景里的 route 就是「愿意多花 15 分钟」那条，roam 允许绕得更远
      // （时长再拉 1.4 倍），+5 只肯顺手一绕（拉回到基准和它的中间）。
      // detour 和 score 随后由 derive() 从这条路线算出来，三者天然一致。
      const ratio = mode === 'roam' ? 1.4 : mode === '+5' ? 0.4 : 1
      // 距离和时长一起缩放。只缩时长会出现「多花 2 分钟却多走 440 米」这种
      // 对不上的读数 —— 对比块把两个数并排印出来，不一致会被一眼看到。
      const lerp = (baseline, full) => Math.round(baseline + (full - baseline) * ratio)
      const baselineSeconds = Number(base.baseline_route?.duration ?? base.baseline_minutes * 60)
      const baselineMeters = Number(base.baseline_route?.distance ?? base.route.distance)

      const route = {
        ...base.route,
        origin,
        destination,
        duration: lerp(baselineSeconds, Number(base.route.duration)),
        distance: lerp(baselineMeters, Number(base.route.distance)),
      }
      const shaped = { ...base, route }

      // T8-4：真后端会发 trip_id（反馈归因的凭据），前端反馈时原样回传。
      // 以前这里没有，界面永远走「没归因上」那一支，闭环在 mock 下看不见。
      const tripId = nextTripId()
      _recommended.set(tripId, shaped.pois || [])
      send(res, 200, { ...shaped, ...derive(shaped), trip_id: tripId })
    })
    return
  }

  // T8-4：反馈按 trip_id 归因到类目。真后端返回 `{ ok, learned: [...] }`，
  // 界面靠 learned 区分「已记住」和「没归因上」，所以这里必须照那个形状回。
  // 归因规则和后端 `tags_for_type` 同源：type 串里出现关键词就算落到那个类目。
  // 归因不上（没有 trip_id）时返回空 learned —— 那条「没能归因」的文案也要能看到。
  if (url.pathname === '/api/feedback' && req.method === 'POST') {
    let raw = ''
    req.on('data', (chunk) => {
      raw += chunk
    })
    req.on('end', () => {
      let body = {}
      try {
        body = JSON.parse(raw || '{}')
      } catch {
        send(res, 400, { detail: '请求体解析失败' })
        return
      }
      // 归因链和真后端一致：trip_id -> 那次推荐的 POI -> type 归并成粗类目。
      const pois = _recommended.get(Number(body.trip_id)) || []
      const learned = []
      for (const poi of pois) {
        for (const tag of tagsForType(poi?.type)) {
          if (!learned.includes(tag)) learned.push(tag)
        }
      }
      send(res, 200, { ok: true, learned })
    })
    return
  }

  // R3：地点联想。真后端走高德 inputtips，一个关键词返回多家门店是它的正常返回，
  // 但无 key 时返回空列表 —— 于是「链路是通的」这件事在桩下从来没被验证过。
  // 这里对连锁店关键词给多条不同门店（各自 location），空关键词或无匹配给空列表，
  // 让「多结果可选」和「空态提示」两条路径都能在冒烟里跑到。
  if (url.pathname === '/api/place/suggest' && req.method === 'GET') {
    const keyword = (url.searchParams.get('keyword') || '').trim()
    const stores = SUGGEST_STUB[keyword] || []
    send(res, 200, { suggestions: stores })
    return
  }

  // 未定稿接口（/api/trip/save 等）：故意返回 404，
  // 验证前端降级不报错。smoke 钉着「收藏失败」那条提示。
  send(res, 404, { detail: 'Not Found' })
}).listen(PORT, () => {
  console.log(`mock backend listening on http://localhost:${PORT}`)
})
