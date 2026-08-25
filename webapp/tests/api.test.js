import { describe, it, expect } from 'vitest'
import { createRecommendApi } from '../src/api.js'
 
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
})
