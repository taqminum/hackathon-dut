import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount } from '@vue/test-utils'
import MapView from '../src/components/MapView.vue'
import L from '../src/utils/leaflet.js'

vi.mock('../src/utils/leaflet.js', () => ({
  default: {
    map: vi.fn(() => ({
      setView: vi.fn().mockReturnThis(),
      addLayer: vi.fn().mockReturnThis(),
      removeLayer: vi.fn(),
      fitBounds: vi.fn().mockReturnThis(),
      panTo: vi.fn().mockReturnThis(),
      remove: vi.fn(),
    })),
    tileLayer: vi.fn(() => ({ addTo: vi.fn().mockReturnThis(), on: vi.fn().mockReturnThis() })),
    polyline: vi.fn(() => ({ addTo: vi.fn().mockReturnThis(), getBounds: vi.fn(() => []) })),
    marker: vi.fn(() => ({ addTo: vi.fn().mockReturnThis(), bindPopup: vi.fn(), on: vi.fn() })),
    divIcon: vi.fn((options) => options),
  },
}))

/** 造一个 map 桩并让下一次 L.map() 返回它，用于断言 fitBounds / panTo 的调用。 */
function stubMap() {
  const map = {
    setView: vi.fn(),
    removeLayer: vi.fn(),
    fitBounds: vi.fn(),
    panTo: vi.fn(),
    remove: vi.fn(),
  }
  L.map.mockReturnValueOnce(map)
  return map
}

/** 取 tileLayer 上注册的某个事件回调，用于模拟瓦片 load / tileerror。 */
function tileHandler(event) {
  const tiles = L.tileLayer.mock.results[0]?.value
  const entry = tiles?.on.mock.calls.find(([name]) => name === event)
  return entry?.[1]
}

/** 取所有 L.polyline 调用的样式参数，用于判断画了几条线、各是什么样式 */
function polylineCalls() {
  return L.polyline.mock.calls.map(([latlngs, options]) => ({ latlngs, options: options ?? {} }))
}

const RECOMMENDED = '121.5197,38.8856;121.5310,38.8878;121.5839,38.8816'
const BASELINE = '121.5197,38.8856;121.5839,38.8816'

describe('MapView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders a map container and handles props without crashing', async () => {
    const wrapper = mount(MapView, {
      props: {
        route: { polyline: '0,0;0.001,0.001;0.002,0.002' },
        pois: [{ name: '偶遇小店', type: '餐饮', location: '0.001,0.001' }],
      },
    })

    expect(wrapper.find('.map-container').exists()).toBe(true)
    await wrapper.find('.map-container').trigger('leaflet:create')
    expect(wrapper.find('.map-container').exists()).toBe(true)
  })

  it('draws the baseline as a dashed line under the recommended route', () => {
    // P3-4：产品卖点是「换一条路」，图上只有推荐那一条就看不出换掉了什么。
    mount(MapView, {
      props: {
        route: { polyline: RECOMMENDED },
        baselineRoute: { polyline: BASELINE },
      },
    })

    const dashed = polylineCalls().filter((call) => call.options.dashArray)
    // 描边 + 芯两笔，同相位
    expect(dashed).toHaveLength(2)
    // 基准只有两个点，推荐有三个 —— 确认虚线画的是基准而不是推荐
    dashed.forEach((call) => expect(call.latlngs).toHaveLength(2))
    expect(new Set(dashed.map((call) => call.options.dashArray)).size).toBe(1)

    // 叠放顺序：基准必须画在推荐路线「之后」，也就是盖在上面。
    // 断网演示的基准与推荐逐点重合（实测 base_only=0），画在 11px 描边底下会被
    // 完全盖住 —— DOM 里虚线在、图例也在，图上却一根都看不见。
    const calls = polylineCalls()
    const lastSolid = calls.findLastIndex((call) => !call.options.dashArray)
    const firstDashed = calls.findIndex((call) => call.options.dashArray)
    expect(firstDashed).toBeGreaterThan(lastSolid)
  })

  it('draws the baseline on top even when it fully overlaps the recommendation', () => {
    // 断网演示的真实形状：推荐路线就是基准抽掉绕行点后的同一条走廊，
    // 三组场景实测基准的点全部落在推荐上（base_only=0）。这种情况下叠放顺序
    // 是「看得见 / 看不见」的唯一区别，所以单独钉一条。
    const baseline = '121.5197,38.8856;121.5839,38.8816'
    const recommended = '121.5197,38.8856;121.5310,38.8878;121.5839,38.8816'
    mount(MapView, {
      props: { route: { polyline: recommended }, baselineRoute: { polyline: baseline } },
    })

    const calls = polylineCalls()
    // 基准的每一笔都在推荐的每一笔之后
    const solidIdx = calls.flatMap((call, i) => (call.options.dashArray ? [] : [i]))
    const dashedIdx = calls.flatMap((call, i) => (call.options.dashArray ? [i] : []))
    expect(dashedIdx).toHaveLength(2)
    expect(Math.min(...dashedIdx)).toBeGreaterThan(Math.max(...solidIdx))
  })

  it('shows the baseline legend entry only when a comparison is drawn', () => {
    const withBaseline = mount(MapView, {
      props: { route: { polyline: RECOMMENDED }, baselineRoute: { polyline: BASELINE } },
    })
    expect(withBaseline.text()).toContain('原本路线')

    const withoutBaseline = mount(MapView, { props: { route: { polyline: RECOMMENDED } } })
    expect(withoutBaseline.text()).not.toContain('原本路线')
  })

  // ---------- S0：途经点与附近亮点必须是两种标记 ----------

  /** 取 POI 标记的 divIcon className（不含起点/终点那两个）。divIcon 桩把 options
   *  原样返回，所以 marker 的第二个参数里 icon.className 就是我们拼的那串。 */
  function markerClassNames() {
    return L.marker.mock.calls
      .map(([, options]) => options?.icon?.className || '')
      .filter((name) => /bh-pin--(waypoint|poi)/.test(name))
  }

  const TWO_POIS = [
    // 第一个是候选路线真的穿过的途经点
    { name: '路上那家店', type: '餐饮', location: '121.5310,38.8878', off_route_meters: 2, is_waypoint: true },
    // 第二个只是在旁边
    { name: '旁边那家店', type: '餐饮', location: '121.5561,38.8845', off_route_meters: 130, is_waypoint: false },
  ]

  it('draws the waypoint with a different marker than the nearby highlights', () => {
    // 用户截图的结论是「途经点不在地图路线上面」，而三个标记同款同色、编号连续，
    // 图例只有一项「沿途亮点」—— 图上没有任何东西告诉他哪个是路线真的经过的。
    mount(MapView, { props: { route: { polyline: RECOMMENDED }, pois: TWO_POIS } })

    const names = markerClassNames()
    expect(names).toHaveLength(2)
    expect(names[0]).toContain('bh-pin--waypoint')
    expect(names[1]).toContain('bh-pin--poi')
    // 关键：两者不能是同一个 className，否则「区分开」只是文档里的说法
    expect(names[0]).not.toBe(names[1])
  })

  it('keeps the waypoint distinct from a nearby highlight even when selected', () => {
    // active 只该叠加「选中」这层意思，不该把途经点降级成普通亮点 ——
    // 合并成一个 poi-active 的话，选中第一个之后图上就分不出它是途经点了。
    const asWaypoint = mount(MapView, {
      props: { route: { polyline: RECOMMENDED }, pois: TWO_POIS, activePoiIndex: 0 },
    })
    expect(markerClassNames()[0]).toContain('bh-pin--waypoint-active')
    asWaypoint.unmount()

    vi.clearAllMocks()
    mount(MapView, {
      props: { route: { polyline: RECOMMENDED }, pois: TWO_POIS, activePoiIndex: 1 },
    })
    const names = markerClassNames()
    // 选中第二个时，第一个退回未选中的途经点款，不是 poi
    expect(names[0]).toContain('bh-pin--waypoint')
    expect(names[0]).not.toContain('bh-pin--poi')
    expect(names[1]).toContain('bh-pin--poi-active')
  })

  it('splits the legend into waypoint and nearby entries', () => {
    // 图例只写「沿途亮点」时，130 米外那个标记也被这四个字背书了。
    const wrapper = mount(MapView, {
      props: { route: { polyline: RECOMMENDED }, pois: TWO_POIS },
    })

    expect(wrapper.text()).toContain('途经点')
    expect(wrapper.text()).toContain('附近亮点')
    expect(wrapper.find('.map__key--waypoint').exists()).toBe(true)
    expect(wrapper.find('.map__key--poi').exists()).toBe(true)
    // 老图例那一项不能还在 —— 留着就是同一件事有两种说法
    expect(wrapper.text()).not.toContain('沿途亮点')
  })

  it('skips the baseline when it is identical to the recommended route', () => {
    // 后端降级出口（选不出候选）会把同一条路线同时当基准和推荐返回。
    // 画上去只是一条被压住的虚线，而图例在说「有对比」—— 假对比比没有更糟。
    const wrapper = mount(MapView, {
      props: {
        route: { polyline: RECOMMENDED },
        baselineRoute: { polyline: RECOMMENDED },
      },
    })

    expect(polylineCalls().filter((call) => call.options.dashArray)).toHaveLength(0)
    expect(wrapper.text()).not.toContain('原本路线')
  })

  it('fits the viewport around both routes', () => {
    // 基准绕得更远时若只按推荐路线取视野，基准会被裁到视野外，
    // 对比图看起来像只有一条线。
    const map = stubMap()

    mount(MapView, {
      props: {
        route: { polyline: '121.5197,38.8856;121.5839,38.8816' },
        // 基准往北绕到 38.95，必须落在 fitBounds 的范围里
        baselineRoute: { polyline: '121.5197,38.8856;121.5500,38.9500;121.5839,38.8816' },
      },
    })

    expect(map.fitBounds).toHaveBeenCalled()
    // boundsOf 返回 [[south, west], [north, east]]，fitBounds(bounds, options)
    const [bounds] = map.fitBounds.mock.calls[0]
    const [[south], [north]] = bounds
    expect(north).toBeCloseTo(38.95, 4)
    expect(south).toBeCloseTo(38.8816, 4)
  })

  it('tolerates a missing baseline route', () => {
    // 老后端不返回 baseline_route 时必须照常画推荐路线，不能白屏
    for (const baselineRoute of [null, undefined, {}, { polyline: '' }]) {
      vi.clearAllMocks()
      const wrapper = mount(MapView, {
        props: { route: { polyline: RECOMMENDED }, baselineRoute },
      })

      expect(wrapper.find('.map-container').exists()).toBe(true)
      expect(polylineCalls().filter((call) => call.options.dashArray)).toHaveLength(0)
      // 推荐路线仍然画了（描边 + 主线两条实线）
      expect(polylineCalls().filter((call) => !call.options.dashArray)).toHaveLength(2)
      expect(wrapper.text()).not.toContain('原本路线')
    }
  })

  // ---------- T2：地图不能是死的 ----------

  it('covers the map with a skeleton until the first tiles land', async () => {
    // 首帧瓦片还没到时，容器是一块纯灰底 —— 和「加载失败」长得一模一样。
    const wrapper = mount(MapView, { props: { route: { polyline: RECOMMENDED } } })

    expect(wrapper.find('.map__skeleton').exists()).toBe(true)
    expect(wrapper.text()).toContain('底图加载中')

    tileHandler('tileload')?.()
    await wrapper.vm.$nextTick()

    expect(wrapper.find('.map__skeleton').exists()).toBe(false)
  })

  it('does not treat the batch load event as tiles having arrived', () => {
    // Leaflet 的 `load` 是「这一批处理完了」，出错的瓦片也算处理完。实测把瓦片
    // 全部 abort 掉，`load` 照样触发 —— 用它撤骨架，断网时屏幕又变回一块灰，
    // 而且错误提示也不出（骨架和提示是互斥的两条 v-if）。所以只认 tileload。
    const wrapper = mount(MapView, { props: { route: { polyline: RECOMMENDED } } })
    const events = L.tileLayer.mock.results[0].value.on.mock.calls.map(([name]) => name)

    expect(events).toContain('tileload')
    expect(events).not.toContain('load')
    expect(wrapper.find('.map__skeleton').exists()).toBe(true)
  })

  it('drops the loading badge once the tiles are known to be unavailable', async () => {
    // 骨架的网格底要留着（否则又是一块纯灰），但「底图加载中」的字牌不能留 ——
    // 它印在路线上方会被线压住，而且下面那条黄条已经把情况说清了。
    const wrapper = mount(MapView, { props: { route: { polyline: RECOMMENDED } } })
    expect(wrapper.find('.map__skeleton-text').exists()).toBe(true)

    const onError = tileHandler('tileerror')
    for (let i = 0; i < 5; i += 1) onError?.()
    await wrapper.vm.$nextTick()

    expect(wrapper.find('.map__skeleton-grid').exists()).toBe(true)
    expect(wrapper.find('.map__skeleton-text').exists()).toBe(false)
  })

  it('says so when the tiles cannot be fetched, but keeps the route', async () => {
    // 现场网络受限时瓦片全 404。以前 failed 只在 L.map 抛异常时才为 true，
    // 于是「底图一张都没下来」在界面上没有任何提示，看着就是「地图是死的」。
    const wrapper = mount(MapView, { props: { route: { polyline: RECOMMENDED } } })
    const onError = tileHandler('tileerror')

    // 偶发单张失败不该报错（OSM 会限流）
    onError?.()
    await wrapper.vm.$nextTick()
    expect(wrapper.text()).not.toContain('底图瓦片加载失败')

    for (let i = 0; i < 4; i += 1) onError?.()
    await wrapper.vm.$nextTick()

    expect(wrapper.text()).toContain('底图瓦片加载失败')
    // 路线是 SVG，不依赖底图，必须照样画出来
    expect(polylineCalls().filter((call) => !call.options.dashArray)).toHaveLength(2)
    expect(wrapper.find('.map-container').exists()).toBe(true)
  })

  it('starts with AMap tiles and switches to ESRI after a full failure', async () => {
    // OSM 在部分网络（尤其大陆）会整体超时。主源必须是国内可达的高德栅格瓦片，
    // 而且连续失败后要自动换下一个源，不能停在「加载中」或一片灰。
    const wrapper = mount(MapView, { props: { route: { polyline: RECOMMENDED } } })

    const [primaryUrl, primaryOptions] = L.tileLayer.mock.calls[0]
    expect(primaryUrl).toContain('is.autonavi.com')
    expect(primaryOptions.subdomains).toEqual(['1', '2', '3', '4'])

    const onError = tileHandler('tileerror')
    for (let i = 0; i < 6; i += 1) onError?.()
    await wrapper.vm.$nextTick()

    expect(L.tileLayer.mock.calls[1][0]).toContain('arcgisonline.com')
    // 换源是一次新的尝试，界面回到「加载中」而不是挂着上一源的失败提示
    expect(wrapper.find('.map__skeleton-text').exists()).toBe(true)
  })

  it('pans to the active poi without refitting the viewport', async () => {
    // 用户手动放大看某个路口，点一下亮点卡片 —— 以前 deep watch 会重跑
    // fitBounds，把视野拽回全程，地图像不听话。平移可以，改缩放不行。
    const map = stubMap()
    const pois = [
      { name: '咖啡', type: '餐饮', location: '121.5310,38.8878' },
      { name: '散步道', type: '景点', location: '121.5561,38.8845' },
    ]
    const wrapper = mount(MapView, {
      props: { route: { polyline: RECOMMENDED }, pois, activePoiIndex: -1 },
    })

    expect(map.fitBounds).toHaveBeenCalledTimes(1)
    expect(map.panTo).not.toHaveBeenCalled()

    await wrapper.setProps({ activePoiIndex: 1 })

    expect(map.panTo).toHaveBeenCalledTimes(1)
    expect(map.panTo.mock.calls[0][0]).toEqual([38.8845, 121.5561])
    // 关键：视野没有被重新取过
    expect(map.fitBounds).toHaveBeenCalledTimes(1)
  })

  it('refits the viewport when the route itself changes', async () => {
    // 上一条的跳过逻辑不能过头：换了一条路线还沿用旧视野，新路线会跑出屏幕。
    const map = stubMap()
    const wrapper = mount(MapView, { props: { route: { polyline: RECOMMENDED } } })

    expect(map.fitBounds).toHaveBeenCalledTimes(1)

    await wrapper.setProps({ route: { polyline: '121.6785,38.9287;121.6701,38.8783' } })

    expect(map.fitBounds).toHaveBeenCalledTimes(2)
  })
})
