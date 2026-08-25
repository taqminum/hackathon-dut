const API_BASE = '/api'

export async function recommendRoute({ origin, destination, mode }) {
  const response = await fetch(`${API_BASE}/route/recommend`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ origin, destination, mode }),
  })

  if (!response.ok) {
    throw new Error('推荐接口请求失败')
  }

  return response.json()
}
