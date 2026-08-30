import { describe, it, expect, beforeEach } from 'vitest'
import { clearHistory, loadHistory, pushHistory } from '../src/utils/history.js'

describe('history store', () => {
  beforeEach(() => {
    clearHistory()
  })

  it('starts empty', () => {
    expect(loadHistory()).toEqual([])
  })

  it('stores the newest entry first', () => {
    pushHistory({ origin: 'A', destination: 'B', mode: '+5' })
    pushHistory({ origin: 'C', destination: 'D', mode: 'roam' })

    const history = loadHistory()
    expect(history).toHaveLength(2)
    expect(history[0].origin).toBe('C')
    expect(history[1].origin).toBe('A')
  })

  it('deduplicates identical queries', () => {
    pushHistory({ origin: 'A', destination: 'B', mode: '+5' })
    pushHistory({ origin: 'A', destination: 'B', mode: '+5' })

    expect(loadHistory()).toHaveLength(1)
  })

  it('deduplicates the same visible route saved once as names and once as coordinates', () => {
    pushHistory({
      origin: '121.5197,38.8856',
      destination: '121.5839,38.8816',
      originLabel: '大连理工大学',
      destinationLabel: '星海广场',
      mode: '+15',
    })
    pushHistory({
      origin: '大连理工大学',
      destination: '星海广场',
      originLabel: '大连理工大学',
      destinationLabel: '星海广场',
      mode: '+15',
    })

    const history = loadHistory()
    expect(history).toHaveLength(1)
    expect(history[0].origin).toBe('大连理工大学')
  })

  it('collapses visible duplicates already present in storage', () => {
    globalThis.localStorage.setItem(
      'serendipity.history.v1',
      JSON.stringify([
        {
          origin: '大连理工大学',
          destination: '星海广场',
          originLabel: '大连理工大学',
          destinationLabel: '星海广场',
          mode: '+15',
        },
        {
          origin: '121.5197,38.8856',
          destination: '121.5839,38.8816',
          originLabel: '大连理工大学',
          destinationLabel: '星海广场',
          mode: '+15',
        },
      ]),
    )

    expect(loadHistory()).toHaveLength(1)
  })

  it('keeps the same route under a different mode', () => {
    pushHistory({ origin: 'A', destination: 'B', mode: '+5' })
    pushHistory({ origin: 'A', destination: 'B', mode: '+15' })

    expect(loadHistory()).toHaveLength(2)
  })

  it('caps the list at five entries', () => {
    for (let i = 0; i < 8; i += 1) {
      pushHistory({ origin: `O${i}`, destination: `D${i}`, mode: '+5' })
    }

    const history = loadHistory()
    expect(history).toHaveLength(5)
    expect(history[0].origin).toBe('O7')
  })

  it('ignores entries without both endpoints', () => {
    pushHistory({ origin: 'A', mode: '+5' })
    expect(loadHistory()).toEqual([])
  })

  it('recovers from corrupted storage', () => {
    globalThis.localStorage.setItem('serendipity.history.v1', '{not json')
    expect(loadHistory()).toEqual([])
  })

  it('clears everything', () => {
    pushHistory({ origin: 'A', destination: 'B', mode: '+5' })
    expect(clearHistory()).toEqual([])
    expect(loadHistory()).toEqual([])
  })
})
