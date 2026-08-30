/**
 * 后端接口封装。
 *
 * 已由后端确定的接口：
 *   GET  /health
 *   POST /api/route/recommend  { origin, destination, mode } ->
 *        { baseline_minutes, detour_minutes, score, pois, narrative, route }
 *
 * 以下接口后端尚未定稿，前端按使用意图先写好请求；
 * 拿不到响应时统一降级，不阻塞主流程（见 withFallback）。
 *   GET  /api/place/suggest?keyword=&city=   地点联想
 *   POST /api/trip/save                      收藏路线
 *   GET  /api/trip/list                      收藏列表
 *   POST /api/feedback                       路线反馈（喜欢 / 不喜欢）
 */

const API_BASE = import.meta.env.VITE_API_BASE || '/api'
const DEFAULT_TIMEOUT = 60000

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

/**
 * T8-3：把「请求根本没走通」翻译成人话。
 *
 * `fetch` 连不上时抛的是 `TypeError: Failed to fetch`（超时被 AbortController
 * 掐断时是 `AbortError`），HomeView 直接把 `err.message` 印在红条上 ——
 * 屏幕上就是一行英文 `Failed to fetch`，用户不知道是后端没起、还是自己填错了。
 *
 * 只翻译**传输层**失败。HTTP 状态码带回来的 `detail` 是后端写给用户看的中文，
 * 必须原样透传 —— 把 404「未找到可行路线」说成「连不上后端」是更坏的谎。
 * 两重保障：调用点只在包住 `fetch` 的 try 里用它（`parse` 在 try 之外），
 * 且认不出的 error 一律原样返回，不套模板。
 */
function humanizeTransportError(error, fallbackMessage) {
  const name = error?.name || ''
  const message = String(error?.message || '')
  if (name === 'AbortError' || /aborted/i.test(message)) {
    return new Error('请求超时，后端没有在预期时间内响应，请稍后重试')
  }
  if (error instanceof TypeError || /failed to fetch|networkerror|load failed/i.test(message)) {
    return new Error('连不上后端服务，请确认后端已启动后重试')
  }
  return error instanceof Error ? error : new Error(message || fallbackMessage)
}

/** 统一解析响应，失败时抛出后端 detail 文案 */
async function parse(response, fallbackMessage) {
  if (!response.ok) {
    const errorBody = await response.json().catch(() => ({}))
    const error = new Error(errorBody.detail || fallbackMessage)
    error.status = response.status
    throw error
  }

  return response.json()
}

/** 未定稿接口的降级包装：失败就返回兜底值，不把异常抛给界面 */
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
export async function recommendRoute(
  { origin, destination, mode, poiCount = 1, city = '大连市', exclude = [] },
  client = globalThis.fetch,
) {
  let response
  try {
    const body = { origin, destination, mode, poi_count: poiCount, city }
    // 重新规划时后端用 exclude 避开上一轮选过的地点；首算不带这个字段，保持请求干净。
    if (Array.isArray(exclude) && exclude.length) body.exclude = exclude
    response = await withTimeout(client, buildUrl('/route/recommend'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
  } catch (error) {
    // 只包传输层失败。`parse` 在这个 try 之外，后端的中文 detail 不会经过这里。
    throw humanizeTransportError(error, '推荐接口请求失败')
  }

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
    return { online: data?.status === 'ok' && data?.ready !== false, detail: data }
  }, { online: false, detail: null })
}

/** 地点联想。后端未定稿，失败返回空数组，输入框退化为纯文本输入 */
export async function suggestPlaces({ keyword, city = '' }, client = globalThis.fetch) {
  if (!keyword || !keyword.trim()) return []

  const query = new URLSearchParams({ keyword: keyword.trim() })
  if (city) query.set('city', city)
  let response
  try {
    response = await withTimeout(
      client,
      `${buildUrl('/place/suggest')}?${query.toString()}`,
      { method: 'GET' },
      8000,
    )
  } catch (error) {
    throw humanizeTransportError(error, '地点联想失败')
  }
  const data = await parse(response, '地点联想失败')
  const list = Array.isArray(data) ? data : data?.suggestions || data?.tips || []
  return list
    .map((item) => ({
      id: item.id || '',
      name: item.name || item.title || '',
      address: item.address || item.district || '',
      location: item.location || item.coord || '',
    }))
    .filter((item) => item.name)
}

/** 收藏当前路线。后端未定稿，失败返回 { ok: false } 让界面提示稍后重试 */
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

/** 收藏列表。后端未定稿，失败返回空数组 */
export async function listTrips(client = globalThis.fetch) {
  return withFallback(async () => {
    const response = await withTimeout(client, buildUrl('/trip/list'), { method: 'GET' }, 8000)
    const data = await parse(response, '收藏列表获取失败')
    return Array.isArray(data) ? data : data?.trips || []
  }, [])
}

/** 路线反馈。后端未定稿，失败静默，不打断演示。
 *
 * T8-4：后端返回 `{ ok, learned: [...] }`，`learned` 是这次真正落到的类目
 * （归因失败时是空数组）。以前这里把它丢掉了，界面只能凭「按钮点过」变色 ——
 * 那和「学到了」不是一件事。原样带出来，让界面按真实结果说话。
 */
export async function sendFeedback({ tripId, liked, mode, comment = '' }, client = globalThis.fetch) {
  return withFallback(async () => {
    const response = await withTimeout(client, buildUrl('/feedback'), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ trip_id: tripId, liked, mode, comment }),
    })
    const data = await parse(response, '反馈提交失败')
    return { ok: true, learned: Array.isArray(data?.learned) ? data.learned : [] }
  }, { ok: false, learned: [] })
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
  saveTrip: (payload) => saveTrip(payload),
  listTrips: () => listTrips(),
  sendFeedback: (payload) => sendFeedback(payload),
}

export { buildUrl }
