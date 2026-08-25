import { describe, it, expect } from 'vitest'
import { recommendRoute } from '../src/api.js'

describe('recommendRoute', () => {
  it('returns routes from api', async () => {
    global.fetch = async () => ({
      ok: true,
      json: async () => ({ routes: [{ id: 1 }] }),
    })
    const result = await recommendRoute({ origin: 'a', destination: 'b', mode: '+5' })
    expect(result.routes[0].id).toBe(1)
  })
})
