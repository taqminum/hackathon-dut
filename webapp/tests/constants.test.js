import { describe, expect, it } from 'vitest'
import { DALIAN_LANDMARKS, DEMO_SCENARIOS } from '../src/constants.js'

describe('Dalian demo coordinates', () => {
  it('uses concrete Donggang and Laohutan landmarks for the coastal demo route', () => {
    const demo = DEMO_SCENARIOS.find((item) => item.id === 'donggang-laohutan')

    expect(demo).toMatchObject({
      originLabel: '东港音乐喷泉广场',
      destinationLabel: '老虎滩海洋公园',
      origin: '121.675287,38.930747',
      destination: '121.674648,38.878386',
    })
  })

  it('keeps quick-pick landmarks aligned with the demo route coordinates', () => {
    expect(DALIAN_LANDMARKS).toEqual(
      expect.arrayContaining([
        { name: '东港音乐喷泉广场', location: '121.675287,38.930747' },
        { name: '老虎滩海洋公园', location: '121.674648,38.878386' },
      ]),
    )
  })
})
