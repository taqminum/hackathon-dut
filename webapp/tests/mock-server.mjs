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
  '121.6068,38.9180->121.5854,38.9325': {
    baseline_minutes: 21,
    detour_minutes: 5,
    score: 6.4,
    narrative: '从大工沿海边走，你会先遇到一间社区咖啡，再顺着海景走到星海。',
    pois: [
      { name: '理工咖啡小铺', type: '餐饮', distance: '180', rating: 4.4, location: '121.6002,38.9218' },
      { name: '海边散步道', type: '景点', distance: '310', rating: 4.6, location: '121.5921,38.9289' },
    ],
    route: {
      origin: '121.6068,38.9180',
      destination: '121.5854,38.9325',
      demo_mode: true,
      distance: 2620,
      duration: 1560,
      polyline:
        '121.6068,38.9180;121.6014,38.9222;121.6002,38.9218;121.5958,38.9265;121.5914,38.9292;121.5854,38.9325',
      steps: [
        { instruction: '沿凌工路向西步行', road: '凌工路', distance: '620', duration: '420' },
        { instruction: '右转进入中山路', road: '中山路', distance: '880', duration: '520' },
        { instruction: '沿海岸线继续前行', road: '滨海路', distance: '700', duration: '380' },
        { instruction: '到达星海广场', road: '星海广场', distance: '420', duration: '240' },
      ],
    },
  },
}

const FALLBACK = {
  baseline_minutes: 16,
  detour_minutes: 3,
  score: 5.2,
  narrative: '这条路线上有几个值得停留的小地方，适合慢慢走。',
  pois: [{ name: '偶遇小店', type: '餐饮', distance: '120', rating: 4.2, location: '121.601,38.918' }],
  route: {
    demo_mode: false,
    distance: 1620,
    duration: 1130,
    polyline: '121.5950,38.9150;121.6010,38.9180;121.6070,38.9210',
    steps: [{ instruction: '按推荐路线行走', road: '主路', distance: '1620', duration: '1130' }],
  },
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
      const factor = mode === 'roam' ? 3 : mode === '+15' ? 2 : 1

      send(res, 200, {
        ...base,
        detour_minutes: base.detour_minutes * factor,
        score: Number((base.score + factor * 0.4).toFixed(2)),
        route: { ...base.route, origin, destination },
      })
    })
    return
  }

  // 未定稿接口：故意返回 404，验证前端降级不报错
  send(res, 404, { detail: 'Not Found' })
}).listen(PORT, () => {
  console.log(`mock backend listening on http://localhost:${PORT}`)
})
