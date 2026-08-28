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
    await expect(api.sendFeedback({ liked: true, mode: '+5' })).resolves.toEqual({ ok: false })
  })
})
