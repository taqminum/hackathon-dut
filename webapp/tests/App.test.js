import { describe, it, expect, vi } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import App from '../src/App.vue'
import HomeView from '../src/views/HomeView.vue'
import ResultView from '../src/views/ResultView.vue'
import { API_KEY } from '../src/composables/useApi.js'
import { DEMO_SCENARIOS } from '../src/constants.js'

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

describe('App', () => {
  it('renders result view after home emits select', async () => {
    const wrapper = mount(App, {
      global: {
        stubs: {
          ResultView: {
            template: `<div class="result-view">Result {{ result.label }}</div>`,
            props: ['result'],
          },
        },
      },
    })

    await wrapper.findComponent(HomeView).vm.$emit('select', { label: 'recommended' })
    await nextTick()

    expect(wrapper.text()).toContain('Result recommended')
    expect(wrapper.findComponent(ResultView).exists()).toBe(true)
  })

  it('keeps home view visible when home emits select without result', async () => {
    const wrapper = mount(App, {
      global: {
        stubs: {
          ResultView: {
            template: `<div class="result-view">Result {{ result?.label }}</div>`,
            props: ['result'],
          },
        },
      },
    })

    await wrapper.findComponent(HomeView).vm.$emit('select')
    await nextTick()

    expect(wrapper.text()).not.toContain('Result recommended')
    expect(wrapper.findComponent(HomeView).exists()).toBe(true)
    expect(wrapper.findComponent(ResultView).exists()).toBe(false)
  })

  // T2：健康灯必须反映真实状态。以前 onMounted 只查一次，演示中途后端挂掉，
  // 灯还是绿的 —— 比没有灯更误导人。
  it('keeps re-checking backend health and flips the lamp when it goes down', async () => {
    vi.useFakeTimers()
    try {
      let healthy = true
      const api = {
        recommendRoute: vi.fn(),
        suggestPlaces: vi.fn(async () => []),
        checkHealth: vi.fn(async () => ({ online: healthy })),
        saveTrip: vi.fn(async () => ({ ok: true })),
        sendFeedback: vi.fn(async () => ({ ok: true })),
        listTrips: vi.fn(async () => []),
      }

      const wrapper = mount(App, { global: { provide: { [API_KEY]: api } } })
      await flushPromises()
      expect(wrapper.text()).toContain('高德真实数据已连接')

      healthy = false
      await vi.advanceTimersByTimeAsync(16000)
      await flushPromises()

      expect(api.checkHealth.mock.calls.length).toBeGreaterThan(1)
      expect(wrapper.text()).toContain('真实数据未就绪')

      // 卸载后不能再查 —— 定时器泄漏会在测试里刷出无穷请求
      const callsAtUnmount = api.checkHealth.mock.calls.length
      wrapper.unmount()
      await vi.advanceTimersByTimeAsync(60000)
      expect(api.checkHealth.mock.calls.length).toBe(callsAtUnmount)
    } finally {
      vi.useRealTimers()
    }
  })

  // T1：地名要从演示场景一路活到结果页标题。这条用例故意不 stub ResultView ——
  // 断言分开写在 HomeView / ResultView 两侧都能各自绿掉，而 payload 少带一个字段
  // 就会重演「标题印经纬度」。链路上任何一环丢标签，这里就红。
  it('shows the demo scenario place names in the result title, not raw coordinates', async () => {
    const scenario = DEMO_SCENARIOS[0]
    const api = {
      recommendRoute: vi.fn(async () => ({
        baseline_minutes: 21,
        detour_minutes: 5,
        score: 6.4,
        pois: [],
        narrative: '沿海边走。',
        route: { polyline: '121.5197,38.8856;121.5839,38.8816', distance: 2100, duration: 1260 },
      })),
      suggestPlaces: vi.fn(async () => []),
      checkHealth: vi.fn(async () => ({ online: true })),
      saveTrip: vi.fn(async () => ({ ok: true })),
      sendFeedback: vi.fn(async () => ({ ok: true })),
      listTrips: vi.fn(async () => []),
    }

    const wrapper = mount(App, { global: { provide: { [API_KEY]: api } } })

    await wrapper.findAll('.demo')[0].trigger('click')
    await flushPromises()
    await nextTick()

    // 发出去的还是坐标：标签只影响显示，不能污染请求
    expect(api.recommendRoute).toHaveBeenCalledWith({
      origin: scenario.origin,
      destination: scenario.destination,
      mode: scenario.mode,
      poiCount: 1,
    })

    const title = wrapper.find('.result__title')
    expect(title.exists()).toBe(true)
    expect(title.text()).toContain('大连理工大学')
    expect(title.text()).toContain('星海广场')
    expect(title.text()).not.toContain('121.5197')
    expect(title.text()).not.toContain('38.8856')
  })

  // R7：整条链路。「重新规划」用同样的起终点和模式重发一次请求，人留在结果页，
  // 数字换成新的；标题还是地名（request 里的 label 不能被第二次响应冲掉）。
  it('re-plans in place with the same parameters and refreshes the metrics', async () => {
    const scenario = DEMO_SCENARIOS[0]
    const route = { polyline: '121.5197,38.8856;121.5839,38.8816', distance: 2100, duration: 1260 }
    const recommendRoute = vi
      .fn()
      .mockResolvedValueOnce({
        baseline_minutes: 21,
        detour_minutes: 5,
        score: 6.4,
        pois: [],
        narrative: '沿海边走。',
        route,
      })
      .mockResolvedValueOnce({
        baseline_minutes: 33,
        detour_minutes: 9,
        score: 7.1,
        pois: [],
        narrative: '换了一条。',
        route: { ...route, distance: 3400 },
      })

    const api = {
      recommendRoute,
      suggestPlaces: vi.fn(async () => []),
      checkHealth: vi.fn(async () => ({ online: true })),
      saveTrip: vi.fn(async () => ({ ok: true })),
      sendFeedback: vi.fn(async () => ({ ok: true })),
      listTrips: vi.fn(async () => []),
    }

    const wrapper = mount(App, { global: { provide: { [API_KEY]: api } } })
    await wrapper.findAll('.demo')[0].trigger('click')
    await flushPromises()
    await nextTick()

    expect(wrapper.text()).toContain('21')

    await wrapper.find('.result__replan').trigger('click')
    await flushPromises()
    await nextTick()

    // 同样的参数重发一次，一次都没多
    expect(recommendRoute).toHaveBeenCalledTimes(2)
    expect(recommendRoute.mock.calls[1][0]).toEqual({
      origin: scenario.origin,
      destination: scenario.destination,
      mode: scenario.mode,
      poiCount: 1,
    })

    // 没回首页
    expect(wrapper.findComponent(HomeView).exists()).toBe(false)
    expect(wrapper.find('.result__title').exists()).toBe(true)
    // 起终点和模式没变，地名还在
    expect(wrapper.find('.result__title').text()).toContain('大连理工大学')
    expect(wrapper.text()).toContain('+15')
    // 指标换了
    expect(wrapper.find('.result__tiles').text()).toContain('33')
    expect(wrapper.find('.result__tiles').text()).toContain('3.4')
  })

  // S3：结果页换模式。这条盯的是「新模式必须写回 request」——
  // 只把 mode 传给接口的话，切到 roam 之后再点一次「重新规划」会退回旧模式。
  // 破坏验证：把 App.onReplan 里 `request: { ...request, mode }` 改回 `request`
  // -> 第三次调用发出的会是 '+15'，这条变红。
  it('re-plans with the picked mode and remembers it for the next re-plan', async () => {
    const scenario = DEMO_SCENARIOS[0]
    const route = { polyline: '121.5197,38.8856;121.5839,38.8816', distance: 2100, duration: 1260 }
    const recommendRoute = vi.fn(async ({ mode }) => ({
      baseline_minutes: 21,
      detour_minutes: mode === 'roam' ? 9 : 5,
      score: 6.4,
      pois: [],
      narrative: `模式 ${mode}`,
      route,
    }))

    const api = {
      recommendRoute,
      suggestPlaces: vi.fn(async () => []),
      checkHealth: vi.fn(async () => ({ online: true })),
      saveTrip: vi.fn(async () => ({ ok: true })),
      sendFeedback: vi.fn(async () => ({ ok: true })),
      listTrips: vi.fn(async () => []),
    }

    const wrapper = mount(App, { global: { provide: { [API_KEY]: api } } })
    await wrapper.findAll('.demo')[0].trigger('click')
    await flushPromises()
    await nextTick()

    // 演示场景 1 是 +15
    expect(recommendRoute.mock.calls[0][0].mode).toBe(scenario.mode)

    // 点结果页上的「漫游」
    const roamButton = wrapper.findAll('.result__mode-btn')[2]
    await roamButton.trigger('click')
    await flushPromises()
    await nextTick()

    expect(recommendRoute.mock.calls[1][0]).toEqual({
      origin: scenario.origin,
      destination: scenario.destination,
      mode: 'roam',
      poiCount: 1,
    })
    // 留在结果页，标题地名没被第二次响应冲掉
    expect(wrapper.findComponent(HomeView).exists()).toBe(false)
    expect(wrapper.find('.result__title').text()).toContain('大连理工大学')
    // 模式标签跟着换了
    expect(wrapper.find('.result__mode').text()).toContain('漫游')

    // 关键：再点一次「重新规划」，发出的仍然是 roam 而不是退回 +15
    await wrapper.find('.result__replan').trigger('click')
    await flushPromises()

    expect(recommendRoute.mock.calls[2][0].mode).toBe('roam')
  })

  it('reports a failed re-plan in Chinese and keeps the previous result', async () => {
    const route = { polyline: '121.5197,38.8856;121.5839,38.8816', distance: 2100, duration: 1260 }
    const recommendRoute = vi
      .fn()
      .mockResolvedValueOnce({
        baseline_minutes: 21,
        detour_minutes: 5,
        score: 6.4,
        pois: [],
        narrative: '沿海边走。',
        route,
      })
      .mockRejectedValueOnce(new Error('后端没响应，请稍后再试'))

    const api = {
      recommendRoute,
      suggestPlaces: vi.fn(async () => []),
      checkHealth: vi.fn(async () => ({ online: true })),
      saveTrip: vi.fn(async () => ({ ok: true })),
      sendFeedback: vi.fn(async () => ({ ok: true })),
      listTrips: vi.fn(async () => []),
    }

    const wrapper = mount(App, { global: { provide: { [API_KEY]: api } } })
    await wrapper.findAll('.demo')[0].trigger('click')
    await flushPromises()
    await nextTick()

    await wrapper.find('.result__replan').trigger('click')
    await flushPromises()
    await nextTick()

    const notice = wrapper.find('.result__replan-error')
    expect(notice.exists()).toBe(true)
    expect(notice.text()).toContain('后端没响应')
    // 旧结果没被清掉，也没被踢回首页
    expect(wrapper.find('.result__tiles').text()).toContain('21')
    expect(wrapper.findComponent(HomeView).exists()).toBe(false)
  })

  it('goes home from the result page home button', async () => {
    const api = {
      recommendRoute: vi.fn(async () => ({
        baseline_minutes: 21,
        detour_minutes: 5,
        score: 6.4,
        pois: [],
        narrative: '沿海边走。',
        route: { polyline: '121.5197,38.8856;121.5839,38.8816', distance: 2100, duration: 1260 },
      })),
      suggestPlaces: vi.fn(async () => []),
      checkHealth: vi.fn(async () => ({ online: true })),
      saveTrip: vi.fn(async () => ({ ok: true })),
      sendFeedback: vi.fn(async () => ({ ok: true })),
      listTrips: vi.fn(async () => []),
    }

    const wrapper = mount(App, { global: { provide: { [API_KEY]: api } } })
    await wrapper.findAll('.demo')[0].trigger('click')
    await flushPromises()
    await nextTick()

    // R7：「返回首页」在吸顶页头里，滚到哪都点得到；结果页头里只留「重新规划」
    await wrapper.find('.head__back').trigger('click')
    await nextTick()

    expect(wrapper.findComponent(HomeView).exists()).toBe(true)
    expect(wrapper.find('.result__title').exists()).toBe(false)
  })
})
