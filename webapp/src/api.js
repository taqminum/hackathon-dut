const API_BASE = import.meta.env.VITE_API_BASE || '/api'

function buildUrl() {
  const base = API_BASE.replace(/\/$/, '')
  return `${base}/route/recommend`
}

export async function recommendRoute({ origin, destination, mode }) {
  const response = await fetch(`${API_BASE.replace(/\/$/, '')}/route/recommend`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ origin, destination, mode }),
  })

  if (!response.ok) {
    const errorBody = await response.json().catch(() => ({}))
    throw new Error(errorBody.detail || '推荐接口请求失败')
  }

  return response.json()
}

export function createRecommendApi(client = globalThis.fetch) {
  const original = recommendRoute

  async function recommendRouteWithClient(payload) {
    const response = await client(buildUrl(), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    })

    if (!response.ok) {
      const errorBody = await response.json().catch(() => ({}))
      throw new Error(errorBody.detail || '推荐接口请求失败')
    }

    return response.json()
  }

  return { recommendRoute: recommendRouteWithClient, buildUrl }
}
