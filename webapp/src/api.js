/**
 * 后端接口封装。
 *
 * 已实现的接口：
 *   GET  /health
 *   GET  /api/place/suggest?keyword=&city=   地点联想
 *   POST /api/route/recommend  { origin, destination, mode } ->
 *        { baseline_minutes, detour_minutes, score, pois, narrative, route }
 *
 * 以下接口后端已声明但尚未实现（统一返回 501），前端按使用意图先写好请求；
 * 拿不到响应时统一降级，不阻塞主流程（见 withFallback）。
 *   GET  /api/poi/:id                        POI 详情
 *   POST /api/trip/save                      收藏路线
 *   GET  /api/trip/list                      收藏列表
 *   POST /api/feedback                       路线反馈（喜欢 / 不喜欢）
 */

const API_BASE = import.meta.env.VITE_API_BASE || '/api'
const DEFAULT_TIMEOUT = 20000

function base() {
  return API_BASE.replace(/\/$/, '')
}

function buildUrl(path = '/route/recommend') {
  const suffix = path.startsWith('/') ? path : `/${path}`
  return `${base()}${suffix}`
}

/** 带超时的 fetch，避免现场网络卡死时界面一直转圈 */
function withTimeout(client, url, options = {}, timeout = DEFAULT_TIMEOUT) {
  if (typeof AbortController === 'undefined') {
    return client(url, options)
  }

  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeout)

  return Promise.resolve(client(url, { ...options, signal: controller.signal })).finally(
    () => clearTimeout(timer),
  )
}

/** 统一解析响应，失败时抛出后端 detail 文案 */
async function parse(response, fallbackMessage) {
  if (!response.ok) {
    const errorBody = await response.json().catch(() => ({}))
    const detail = errorBody.detail
    const message = typeof detail === 'string' ? detail : detail?.message || fallbackMessage
    const error = new Error(message)
    error.status = response.status
    error.detail = detail
    throw error
  }

  return response.json()
}

/** 未实现或可选接口的降级包装：失败就返回兜底值，不把异常抛给界面 */
async function withFallback(promiseFactory, fallbackValue) {
  try {
    return await promiseFactory()
  } catch {
    return fallbackValue
  }
}

/**
 * 推荐路线。core 接口，失败必须抛出，让界面显示错误态。
 */
export async function recommendRoute({ origin, destination, mode }, client = globalThis.fetch) {
  const response = await withTimeout(client, buildUrl('/route/recommend'), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ origin, destination, mode }),
  })

  return parse(response, '推荐接口请求失败')
}

/** 服务健康检查，用于首页显示后端连通状态 */
export async function checkHealth(client = globalThis.fetch) {
  return withFallback(async () => {
    const response = await withTimeout(
      client,
      `${base().replace(/\/api$/, '')}/health`,
      { method: 'GET' },
      5000,
    )
    const data = await parse(response, '健康检查失败')
    return { online: data?.status === 'ok', detail: data }
  }, { online: false, detail: null })
}

/** 地点联想。已实现接口；失败仍返回空数组，输入框退化为纯文本输入 */
export async function suggestPlaces({ keyword, city = '大连' }, client = globalThis.fetch) {
  if (!keyword || !keyword.trim()) return []

  return withFallback(async () => {
    const query = new URLSearchParams({ keyword: keyword.trim(), city })
    const response = await withTimeout(
      client,
      `${buildUrl('/place/suggest')}?${query.toString()}`,
      { method: 'GET' },
      6000,
    )
    const data = await parse(response, '地点联想失败')
    const list = Array.isArray(data) ? data : data?.suggestions || data?.tips || []
    return list
      .map((item) => ({
        name: item.name || item.title || '',
        address: item.address || item.district || '',
        location: item.location || item.coord || '',
        type: item.type || '',
        coordinate_system: item.coordinate_system || '',
        confidence: typeof item.confidence === 'number' ? item.confidence : null,
      }))
      .filter((item) => item.name)
  }, [])
}

/** POI 详情。后端尚未实现（501），失败返回 null，界面只展示列表里已有的字段 */
export async function fetchPoiDetail(poiId, client = globalThis.fetch) {
  if (!poiId) return null

  return withFallback(async () => {
    const response = await withTimeout(
      client,
      buildUrl(`/poi/${encodeURIComponent(poiId)}`),
      { method: 'GET' },
      8000,
    )
    return parse(response, 'POI 详情获取失败')
  }, null)
}

/** 收藏当前路线。后端尚未实现（501），失败返回 { ok: false } 让界面提示稍后重试 */
export async function saveTrip(payload, client = globalThis.fetch) {
  return withFallback(async () => {
    const response = await withTimeout(client, buildUrl('/trip/save'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })
    const data = await parse(response, '收藏失败')
    return { ok: true, ...data }
  }, { ok: false })
}

/** 收藏列表。后端尚未实现（501），失败返回空数组 */
export async function listTrips(client = globalThis.fetch) {
  return withFallback(async () => {
    const response = await withTimeout(client, buildUrl('/trip/list'), { method: 'GET' }, 8000)
    const data = await parse(response, '收藏列表获取失败')
    return Array.isArray(data) ? data : data?.trips || []
  }, [])
}

/** 路线反馈。后端尚未实现（501），失败静默，不打断演示 */
export async function sendFeedback({ tripId, liked, mode, comment = '' }, client = globalThis.fetch) {
  return withFallback(async () => {
    const response = await withTimeout(client, buildUrl('/feedback'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ trip_id: tripId, liked, mode, comment }),
    })
    await parse(response, '反馈提交失败')
    return { ok: true }
  }, { ok: false })
}

/**
 * 注入自定义 fetch 的工厂，便于测试与本地 mock。
 */
export function createRecommendApi(client = globalThis.fetch) {
  return {
    buildUrl,
    recommendRoute: (payload) => recommendRoute(payload, client),
    checkHealth: () => checkHealth(client),
    suggestPlaces: (payload) => suggestPlaces(payload, client),
    fetchPoiDetail: (poiId) => fetchPoiDetail(poiId, client),
    saveTrip: (payload) => saveTrip(payload, client),
    listTrips: () => listTrips(client),
    sendFeedback: (payload) => sendFeedback(payload, client),
  }
}

/** 默认 api 实例，界面通过 provide/inject 或直接引用使用 */
export const defaultApi = {
  buildUrl,
  recommendRoute: (payload) => recommendRoute(payload),
  checkHealth: () => checkHealth(),
  suggestPlaces: (payload) => suggestPlaces(payload),
  fetchPoiDetail: (poiId) => fetchPoiDetail(poiId),
  saveTrip: (payload) => saveTrip(payload),
  listTrips: () => listTrips(),
  sendFeedback: (payload) => sendFeedback(payload),
}

export { buildUrl }
