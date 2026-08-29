import { describe, it, expect, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import ResultView from '../src/views/ResultView.vue'
import { API_KEY } from '../src/composables/useApi.js'

vi.mock('../src/utils/leaflet.js', () => ({
  default: {
    map: vi.fn(() => ({
      setView: vi.fn().mockReturnThis(),
      removeLayer: vi.fn(),
      fitBounds: vi.fn().mockReturnThis(),
      remove: vi.fn(),
    })),
    tileLayer: vi.fn(() => ({ addTo: vi.fn().mockReturnThis() })),
    polyline: vi.fn(() => ({ addTo: vi.fn().mockReturnThis(), getBounds: vi.fn(() => []) })),
    marker: vi.fn(() => ({ addTo: vi.fn().mockReturnThis(), bindPopup: vi.fn(), on: vi.fn() })),
    divIcon: vi.fn((options) => options),
  },
}))

const RESULT = {
  baseline_minutes: 21,
  detour_minutes: 5,
  score: 6.4,
  narrative: '从大工沿海边走，你会先遇到一间社区咖啡。',
  pois: [
    { name: '理工咖啡小铺', type: '餐饮服务;咖啡厅', distance: '180', rating: 4.4, location: '121.6002,38.9218' },
    { name: '海边散步道', type: '景点', distance: '310', rating: 4.6, location: '121.5921,38.9289' },
  ],
  route: {
    polyline: '121.6068,38.9180;121.5854,38.9325',
    distance: 2340,
    duration: 1400,
    demo_mode: true,
    steps: [
      { instruction: '沿凌工路向西', road: '凌工路', distance: '600', duration: '420' },
      { instruction: '进入中山路', road: '中山路', distance: '900', duration: '520' },
      { instruction: '到达星海广场', road: '星海广场', distance: '840', duration: '460' },
    ],
  },
  request: { origin: '121.6068,38.9180', destination: '121.5854,38.9325', mode: '+15' },
}

function makeApi(overrides = {}) {
  return {
    saveTrip: vi.fn(async () => ({ ok: true })),
    sendFeedback: vi.fn(async () => ({ ok: true })),
    recommendRoute: vi.fn(),
    suggestPlaces: vi.fn(async () => []),
    checkHealth: vi.fn(async () => ({ online: true })),
    listTrips: vi.fn(async () => []),
    fetchPoiDetail: vi.fn(async () => null),
    ...overrides,
  }
}

function mountResult(result, api = makeApi()) {
  return mount(ResultView, {
    props: { result },
    global: { provide: { [API_KEY]: api } },
  })
}

describe('ResultView', () => {
  it('shows the key metrics, narrative and pois', () => {
    const wrapper = mountResult(RESULT)
    const text = wrapper.text()

    expect(text).toContain('21')
    expect(text).toContain('+5')
    expect(text).toContain('6.4')
    expect(text).toContain('2.3 公里')
    expect(text).toContain('从大工沿海边走')
    expect(text).toContain('理工咖啡小铺')
    expect(text).toContain('海边散步道')
    expect(wrapper.findAll('.poi')).toHaveLength(2)
  })

  it('computes the total as baseline plus detour', () => {
    const wrapper = mountResult(RESULT)
    expect(wrapper.text()).toContain('26')
  })

  it('flags built-in demo data', () => {
    const wrapper = mountResult(RESULT)
    expect(wrapper.text()).toContain('内置演示数据')
  })

  it('flags demo pois even when the route is real', () => {
    const wrapper = mountResult({
      ...RESULT,
      poi_demo_mode: true,
      route: { ...RESULT.route, demo_mode: false },
    })

    expect(wrapper.text()).toContain('沿途亮点来自内置演示数据')
    expect(wrapper.text()).toContain('路线本身仍为高德真实路线')
  })

  it('renders route steps and toggles the collapsed ones', async () => {
    const wrapper = mountResult(RESULT)
    expect(wrapper.text()).toContain('沿凌工路向西')
    expect(wrapper.findAll('.steps__item')).toHaveLength(3)

    const many = {
      ...RESULT,
      route: {
        ...RESULT.route,
        steps: Array.from({ length: 7 }, (_, i) => ({ instruction: `第 ${i + 1} 段`, road: '路' })),
      },
    }
    const big = mountResult(many)
    expect(big.findAll('.steps__item')).toHaveLength(4)

    await big.find('.steps__toggle').trigger('click')
    expect(big.findAll('.steps__item')).toHaveLength(7)
  })

  it('shows an empty state when there is no result', () => {
    const wrapper = mountResult(null)
    expect(wrapper.text()).toContain('还没有推荐结果')
    expect(wrapper.find('.poi').exists()).toBe(false)
  })

  it('emits back from the empty state action', async () => {
    const wrapper = mountResult(null)
    await wrapper.find('.state button').trigger('click')
    expect(wrapper.emitted('back')).toHaveLength(1)
  })

  it('shows an empty poi state but keeps the route visible', () => {
    const wrapper = mountResult({ ...RESULT, pois: [] })
    expect(wrapper.text()).toContain('这段路没有找到亮点')
    expect(wrapper.text()).toContain('从大工沿海边走')
  })

  it('falls back to placeholders when metrics are missing', () => {
    const wrapper = mountResult({ route: { polyline: '121.6,38.9;121.7,38.95' } })
    expect(wrapper.text()).toContain('--')
    expect(wrapper.text()).toContain('这条路线暂时没有额外说明')
  })

  it('toggles the active poi highlight', async () => {
    const wrapper = mountResult(RESULT)
    const first = wrapper.findAll('.poi')[0]

    await first.trigger('click')
    expect(wrapper.findAll('.poi')[0].classes()).toContain('poi--active')

    await wrapper.findAll('.poi')[0].trigger('click')
    expect(wrapper.findAll('.poi')[0].classes()).not.toContain('poi--active')
  })

  it('saves the trip and reports success', async () => {
    const api = makeApi()
    const wrapper = mountResult(RESULT, api)

    await wrapper.find('.bh-btn--accent').trigger('click')
    await flushPromises()

    expect(api.saveTrip).toHaveBeenCalledTimes(1)
    expect(api.saveTrip.mock.calls[0][0].mode).toBe('+15')
    expect(wrapper.text()).toContain('已收藏')
  })

  it('reports a failed save without throwing', async () => {
    const api = makeApi({ saveTrip: vi.fn(async () => ({ ok: false })) })
    const wrapper = mountResult(RESULT, api)

    await wrapper.find('.bh-btn--accent').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('收藏失败')
  })

  it('sends route feedback', async () => {
    const api = makeApi()
    const wrapper = mountResult(RESULT, api)

    const buttons = wrapper.findAll('.result__feedback button')
    await buttons[0].trigger('click')
    await flushPromises()

    expect(api.sendFeedback).toHaveBeenCalledWith({ tripId: null, liked: true, mode: '+15' })
  })

  it('emits back from the re-plan button', async () => {
    const wrapper = mountResult(RESULT)
    await wrapper.find('.result__back').trigger('click')
    expect(wrapper.emitted('back')).toHaveLength(1)
  })
})
