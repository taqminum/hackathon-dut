import { describe, it, expect, vi } from 'vitest'
import { createRecommendApi } from '../src/api.js'

function ok(body) {
  return { ok: true, json: async () => body }
}

function fail(status, detail) {
  return { ok: false, status, json: async () => (detail ? { detail } : {}) }
}

describe('recommendRoute', () => {
  it('returns routes from api', async () => {
    const api = createRecommendApi(async () => ({
      ok: true,
      json: async () => ({ baseline_minutes: 12, detour_minutes: 7, score: 6.5, pois: [], narrative: 'ok', route: { polyline: '0,0' } }),
    }))

    const result = await api.recommendRoute({ origin: 'a', destination: 'b', mode: '+5' })
    expect(result.baseline_minutes).toBe(12)
    expect(result.route.polyline).toBe('0,0')
  })

  it('posts origin, destination and mode as json', async () => {
    const client = vi.fn(async () => ok({ route: {} }))
    const api = createRecommendApi(client)

    await api.recommendRoute({ origin: '大连理工大学', destination: '星海广场', mode: '+15' })

    const [url, options] = client.mock.calls[0]
    expect(url).toBe('/api/route/recommend')
    expect(options.method).toBe('POST')
    expect(options.headers['Content-Type']).toBe('application/json')
    expect(JSON.parse(options.body)).toEqual({
      origin: '大连理工大学',
      destination: '星海广场',
      mode: '+15',
    })
  })

  it('throws the backend detail message', async () => {
    const api = createRecommendApi(async () => fail(404, '未找到可行路线'))
    await expect(api.recommendRoute({ origin: 'a', destination: 'b' })).rejects.toThrow(
      '未找到可行路线',
    )
  })

  it('throws a generic message when there is no detail', async () => {
    const api = createRecommendApi(async () => fail(500))
    await expect(api.recommendRoute({ origin: 'a', destination: 'b' })).rejects.toThrow(
      '推荐接口请求失败',
    )
  })

  // T8-3：后端没起时 fetch 抛的是 `TypeError: Failed to fetch`，HomeView 会把
  // err.message 原样印在红条上 —— 屏幕上就是一行英文，用户看不出是后端没起。
  it('translates a dead backend into a readable chinese message', async () => {
    const api = createRecommendApi(async () => {
      throw new TypeError('Failed to fetch')
    })
    await expect(api.recommendRoute({ origin: 'a', destination: 'b' })).rejects.toThrow(
      '连不上后端服务',
    )
  })

  it('translates a timeout abort into a readable chinese message', async () => {
    const api = createRecommendApi(async () => {
      const error = new Error('This operation was aborted')
      error.name = 'AbortError'
      throw error
    })
    await expect(api.recommendRoute({ origin: 'a', destination: 'b' })).rejects.toThrow(
      '请求超时',
    )
  })

  // 翻译只能包传输层。后端的中文 detail 是写给用户看的，被盖成
  // 「连不上后端服务」就等于把 404「未找到可行路线」说成了网络故障。
  it('never overwrites a backend detail with the transport wording', async () => {
    const api = createRecommendApi(async () => fail(404, '未找到可行路线'))
    await expect(api.recommendRoute({ origin: 'a', destination: 'b' })).rejects.toThrow(
      '未找到可行路线',
    )
  })
})

describe('checkHealth', () => {
  it('reports online when the backend answers ok', async () => {
    const api = createRecommendApi(async () => ok({ status: 'ok' }))
    await expect(api.checkHealth()).resolves.toEqual({
      online: true,
      detail: { status: 'ok' },
    })
  })

  it('reports offline instead of throwing', async () => {
    const api = createRecommendApi(async () => {
      throw new Error('network down')
    })
    await expect(api.checkHealth()).resolves.toEqual({ online: false, detail: null })
  })
})

describe('suggestPlaces', () => {
  it('skips the request for blank keywords', async () => {
    const client = vi.fn()
    const api = createRecommendApi(client)

    await expect(api.suggestPlaces({ keyword: '  ' })).resolves.toEqual([])
    expect(client).not.toHaveBeenCalled()
  })

  it('normalises suggestion payloads', async () => {
    const api = createRecommendApi(async () =>
      ok({ suggestions: [{ name: '星海广场', district: '沙河口区', location: '121.5854,38.9325' }] }),
    )

    await expect(api.suggestPlaces({ keyword: '星海' })).resolves.toEqual([
      { name: '星海广场', address: '沙河口区', location: '121.5854,38.9325' },
    ])
  })

  it('degrades to an empty list on failure', async () => {
    const api = createRecommendApi(async () => fail(500))
    await expect(api.suggestPlaces({ keyword: '星海' })).resolves.toEqual([])
  })
})

describe('optional endpoints', () => {
  it('marks saveTrip ok on success and not-ok on failure', async () => {
    const good = createRecommendApi(async () => ok({ trip_id: 'abc' }))
    await expect(good.saveTrip({ mode: '+5' })).resolves.toEqual({ ok: true, trip_id: 'abc' })

    const bad = createRecommendApi(async () => fail(501))
    await expect(bad.saveTrip({ mode: '+5' })).resolves.toEqual({ ok: false })
  })

  it('returns an empty trip list when the endpoint is missing', async () => {
    const api = createRecommendApi(async () => fail(404))
    await expect(api.listTrips()).resolves.toEqual([])
  })

  it('never throws from sendFeedback', async () => {
    const api = createRecommendApi(async () => {
      throw new Error('offline')
    })
    // learned 恒为数组：界面按 learned.length 说话，undefined 会让它走到
    // 「已记住」那一支去（`Array.isArray` 挡了一层，但两边都保持数组更省心）
    await expect(api.sendFeedback({ liked: true, mode: '+5' })).resolves.toEqual({
      ok: false,
      learned: [],
    })
  })

  // T8-4：后端 `/api/feedback` 返回的 `learned` 是「这次真的落到哪些类目」，
  // 界面全靠它区分「已记住」和「没归因上」。丢掉这个字段等于让界面开始猜。
  it('carries the learned categories through from the feedback endpoint', async () => {
    const api = createRecommendApi(async () => ok({ ok: true, learned: ['咖啡', '餐饮'] }))
    await expect(api.sendFeedback({ tripId: 4, liked: true, mode: '+15' })).resolves.toEqual({
      ok: true,
      learned: ['咖啡', '餐饮'],
    })
  })

  it('reports nothing learned when the backend attributed nothing', async () => {
    const api = createRecommendApi(async () => ok({ ok: true, learned: [] }))
    await expect(api.sendFeedback({ liked: false })).resolves.toEqual({ ok: true, learned: [] })
  })
})
