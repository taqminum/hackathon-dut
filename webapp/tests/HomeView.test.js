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
      origin: '121.5197,38.8856',
      destination: '121.5839,38.8816',
      mode: '+15',
    })
    expect(wrapper.emitted('update:modelValue')?.[0]).toEqual(['+15'])
  })

  // R2：一键体验过去把坐标灌回输入框，用户看到的是「121.5197,38.8856」。
  // 现在输入框显示地名，坐标退到隐藏状态里，提交的还是坐标（上一条已经验了）。
  it('shows place names in the inputs after a demo scenario, not raw coordinates', async () => {
    const api = makeApi()
    const wrapper = mountHome(api)

    await wrapper.findAll('.demo')[0].trigger('click')
    await flushPromises()

    const [origin, destination] = wrapper.findAll('input').map((input) => input.element.value)
    const COORD = /^\d+\.\d+,\d+\.\d+$/

    expect(origin).not.toMatch(COORD)
    expect(destination).not.toMatch(COORD)
    // 而且不能是空的 —— 「不显示坐标」不能靠什么都不显示来达成
    expect(origin.length).toBeGreaterThan(0)
    expect(destination.length).toBeGreaterThan(0)
  })

  // R3：从下拉里选门店 —— 框里是店名，发出去的是店的坐标。
  // 这条盯的是 PlaceInput.choose 与 onOriginPick 的配合：choose 只回填地名，
  // 坐标靠 pick 事件传给 HomeView 存进 originCoord。任何一头漏了，
  // 要么框里印经纬度，要么发给后端的是「麦当劳(青泥洼桥店)」。
  it('submits the picked store coordinate while showing its name', async () => {
    const api = makeApi({
      suggestPlaces: vi.fn(async () => [
        { name: '麦当劳(青泥洼桥店)', address: '中山区友好路 88 号', location: '121.6335,38.9187' },
        { name: '麦当劳(西安路店)', address: '沙河口区西安路 123 号', location: '121.5893,38.9142' },
      ]),
    })
    const wrapper = mountHome(api)
    const inputs = wrapper.findAll('input')

    await inputs[0].setValue('麦当劳')
    await new Promise((resolve) => setTimeout(resolve, 320))
    await flushPromises()
    await inputs[0].trigger('focus')

    const options = wrapper.findAll('[role="option"]')
    expect(options.length).toBeGreaterThanOrEqual(2)

    await options[0].trigger('mousedown')
    await flushPromises()

    // 框里是店名，不是坐标
    expect(wrapper.findAll('input')[0].element.value).toBe('麦当劳(青泥洼桥店)')

    await wrapper.findAll('input')[1].setValue('121.5839,38.8816')
    await wrapper.find('form').trigger('submit')
    await flushPromises()

    // 发出去的是选中门店的坐标
    expect(api.recommendRoute).toHaveBeenCalledWith(
      expect.objectContaining({ origin: '121.6335,38.9187', destination: '121.5839,38.8816' }),
    )
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
