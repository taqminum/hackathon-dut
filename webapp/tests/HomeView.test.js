import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import HomeView from '../src/views/HomeView.vue'
import { API_KEY } from '../src/composables/useApi.js'

const RESULT = {
  baseline_minutes: 21,
  detour_minutes: 5,
  score: 6.4,
  pois: [{ name: '理工咖啡小铺', type: '餐饮', distance: '180', rating: 4.4, location: '121.6002,38.9218' }],
  narrative: '从大工沿海边走。',
  route: { polyline: '121.6068,38.9180;121.5854,38.9325', distance: 2100, duration: 1260 },
}

function makeApi(overrides = {}) {
  return {
    recommendRoute: vi.fn(async () => RESULT),
    suggestPlaces: vi.fn(async () => []),
    checkHealth: vi.fn(async () => ({ online: true })),
    saveTrip: vi.fn(async () => ({ ok: true })),
    sendFeedback: vi.fn(async () => ({ ok: true })),
    listTrips: vi.fn(async () => []),
    fetchPoiDetail: vi.fn(async () => null),
    ...overrides,
  }
}

function mountHome(api) {
  return mount(HomeView, {
    global: { provide: { [API_KEY]: api } },
  })
}

describe('HomeView', () => {
  beforeEach(() => {
    globalThis.localStorage?.clear?.()
  })

  it('renders the inputs, mode selector and demo shortcuts', () => {
    const wrapper = mountHome(makeApi())

    expect(wrapper.findAll('input')).toHaveLength(2)
    expect(wrapper.findAll('[role="radio"]')).toHaveLength(3)
    expect(wrapper.findAll('.demo')).toHaveLength(3)
  })

  it('keeps submit disabled until both places are filled', async () => {
    const wrapper = mountHome(makeApi())
    const submit = wrapper.find('button[type="submit"]')

    expect(submit.attributes('disabled')).toBeDefined()

    await wrapper.findAll('input')[0].setValue('大连理工大学')
    expect(submit.attributes('disabled')).toBeDefined()

    await wrapper.findAll('input')[1].setValue('星海广场')
    expect(submit.attributes('disabled')).toBeUndefined()
  })

  it('emits select with the recommended result', async () => {
    const api = makeApi()
    const wrapper = mountHome(api)

    await wrapper.findAll('input')[0].setValue('大连理工大学')
    await wrapper.findAll('input')[1].setValue('星海广场')
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    expect(api.recommendRoute).toHaveBeenCalledWith({
      origin: '大连理工大学',
      destination: '星海广场',
      mode: '+5',
    })

    const emitted = wrapper.emitted('select')
    expect(emitted).toHaveLength(1)
    expect(emitted[0][0].route.polyline).toBe(RESULT.route.polyline)
    expect(emitted[0][0].request.mode).toBe('+5')
  })

  it('shows the loading state while the request is pending', async () => {
    let resolve
    const api = makeApi({
      recommendRoute: vi.fn(() => new Promise((r) => { resolve = r })),
    })
    const wrapper = mountHome(api)

    await wrapper.findAll('input')[0].setValue('大连理工大学')
    await wrapper.findAll('input')[1].setValue('星海广场')
    wrapper.find('form').trigger('submit')
    await flushPromises()

    expect(wrapper.text()).toContain('正在寻找可控的意外')
    expect(wrapper.find('[aria-busy="true"]').exists()).toBe(true)

    resolve(RESULT)
    await flushPromises()

    expect(wrapper.text()).not.toContain('正在寻找可控的意外')
  })

  it('surfaces the backend error message on failure', async () => {
    const api = makeApi({
      recommendRoute: vi.fn(async () => {
        throw new Error('未找到可行路线')
      }),
    })
    const wrapper = mountHome(api)

    await wrapper.findAll('input')[0].setValue('起点')
    await wrapper.findAll('input')[1].setValue('终点')
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    expect(wrapper.find('[role="alert"]').text()).toContain('未找到可行路线')
    expect(wrapper.emitted('select')).toBeUndefined()
  })

  it('warns when the backend returns no route', async () => {
    const api = makeApi({ recommendRoute: vi.fn(async () => ({ route: null, pois: [] })) })
    const wrapper = mountHome(api)

    await wrapper.findAll('input')[0].setValue('起点')
    await wrapper.findAll('input')[1].setValue('终点')
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    expect(wrapper.find('[role="alert"]').text()).toContain('未找到推荐路线')
    expect(wrapper.emitted('select')).toBeUndefined()
  })

  it('submits a demo scenario with its own mode', async () => {
    const api = makeApi()
    const wrapper = mountHome(api)

    await wrapper.findAll('.demo')[0].trigger('click')
    await flushPromises()

    expect(api.recommendRoute).toHaveBeenCalledWith({
      origin: '121.6068,38.9180',
      destination: '121.5854,38.9325',
      mode: '+15',
    })
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual(['+15'])
  })

  it('swaps origin and destination', async () => {
    const wrapper = mountHome(makeApi())
    const inputs = wrapper.findAll('input')

    await inputs[0].setValue('A地')
    await inputs[1].setValue('B地')
    await wrapper.find('.home__swap').trigger('click')

    expect(wrapper.findAll('input')[0].element.value).toBe('B地')
    expect(wrapper.findAll('input')[1].element.value).toBe('A地')
  })
})
