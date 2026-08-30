import { describe, it, expect } from 'vitest'
import {
  colorForIndex,
  formatDetour,
  formatDistance,
  formatDuration,
  formatMinutes,
  formatScore,
  ordinal,
  scoreToPercent,
  toNumber,
} from '../src/utils/format.js'

describe('format utils', () => {
  it('parses numbers from strings and rejects garbage', () => {
    expect(toNumber('12')).toBe(12)
    expect(toNumber(12.5)).toBe(12.5)
    expect(toNumber('abc')).toBe(null)
    expect(toNumber('')).toBe(null)
    expect(toNumber(undefined)).toBe(null)
    expect(toNumber(NaN)).toBe(null)
  })

  it('formats minutes with fallback', () => {
    expect(formatMinutes(21)).toBe('21')
    expect(formatMinutes('21.4')).toBe('21')
    expect(formatMinutes(null)).toBe('--')
  })

  it('formats detour with explicit plus sign', () => {
    expect(formatDetour(7)).toBe('+7')
    expect(formatDetour(0)).toBe('0')
    expect(formatDetour(undefined)).toBe('--')
  })

  it('formats distance in meters and kilometers', () => {
    expect(formatDistance(320)).toBe('320 米')
    expect(formatDistance(2100)).toBe('2.1 公里')
    expect(formatDistance(null)).toBe('--')
  })

  it('formats duration from seconds', () => {
    expect(formatDuration(1260)).toBe('21 分钟')
    expect(formatDuration(3900)).toBe('1 小时 5 分钟')
    expect(formatDuration(7200)).toBe('2 小时')
    expect(formatDuration('bad')).toBe('--')
  })

  it('formats score to one decimal', () => {
    expect(formatScore(6.5)).toBe('6.5')
    expect(formatScore('7')).toBe('7.0')
    expect(formatScore(null)).toBe('--')
    // T5：传了 max 就必须 clamp，否则界面会印出「7.2/7」
    expect(formatScore(7.2, 7)).toBe('7.0')
    expect(formatScore(6.4, 7)).toBe('6.4')
    expect(formatScore(-1, 7)).toBe('0.0')
    // 不传 max 保持原值，别的调用方不受影响
    expect(formatScore(9)).toBe('9.0')
  })

  it('maps score to a clamped percentage', () => {
    expect(scoreToPercent(5, 10)).toBe(50)
    expect(scoreToPercent(20, 10)).toBe(100)
    expect(scoreToPercent(-3, 10)).toBe(0)
    expect(scoreToPercent(null)).toBe(0)
  })

  // 原来所有用例都显式传 max，默认值没人钉住，于是它悄悄停在 10，
  // 而 ScoreMeter 已经改成 7 —— 满分路线只能填到 70%。这里钉住默认值。
  it('defaults max to the scorer reachable ceiling', () => {
    expect(scoreToPercent(7)).toBe(100)
    expect(scoreToPercent(3.5)).toBe(50)
  })

  it('cycles through the three primary colors', () => {
    expect(colorForIndex(0)).toBe('red')
    expect(colorForIndex(1)).toBe('blue')
    expect(colorForIndex(2)).toBe('yellow')
    expect(colorForIndex(3)).toBe('red')
  })

  it('pads ordinals to two digits', () => {
    expect(ordinal(0)).toBe('01')
    expect(ordinal(11)).toBe('12')
  })
})
