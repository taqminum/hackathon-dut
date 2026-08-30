import { describe, it, expect, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import ResultView from '../src/views/ResultView.vue'
import { API_KEY } from '../src/composables/useApi.js'
import { EXPLORE_MODES } from '../src/constants.js'

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

// score 必须满足后端 SerendipityScorer 的公式，否则 T4 的评分拆分会（正确地）
// 判定这份数据不是那个公式算的：
//   质量 4.0 * (4.4/5) = 3.52，契合 3.0 * 0.7 = 2.1，绕行扣 0.2 * 5 = 1.0
//   -> 3.52 + 2.1 - 1.0 = 4.62
const RESULT = {
  baseline_minutes: 21,
  detour_minutes: 5,
  score: 4.62,
  narrative: '从大工沿海边走，你会先遇到一间社区咖啡。',
  pois: [
    { name: '理工咖啡小铺', type: '餐饮服务;咖啡厅', distance: '180', rating: 4.4, location: '121.6002,38.9218' },
    { name: '海边散步道', type: '景点', distance: '310', rating: 4.6, location: '121.5921,38.9289' },
  ],
  route: {
    polyline: '121.6068,38.9180;121.5854,38.9325',
    distance: 2340,
    duration: 1400,
    // R9：离线徽标看的是 source，不是 demo_mode。两个都留着 ——
    // demo_mode 仍是后端字段，只是不再是徽标的判据。
    source: 'fallback',
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
    expect(text).toContain('4.6')
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

  // R9：徽标的判据是 route.source === 'fallback'。两个分支都要断言，
  // 否则「永远显示」和「永远不显示」都能过。
  it('flags offline demo data when the route came from the local fallback', () => {
    const wrapper = mountResult(RESULT)
    expect(wrapper.text()).toContain('离线演示数据')
    expect(wrapper.find('.result__demo-notice').exists()).toBe(true)
  })

  it('does not flag offline data when the route came from amap', () => {
    const wrapper = mountResult({
      ...RESULT,
      // demo_mode 故意留 true：如果实现还在看 demo_mode，这条会红。
      route: { ...RESULT.route, source: 'amap' },
    })

    expect(wrapper.text()).not.toContain('离线演示数据')
    expect(wrapper.find('.result__demo-notice').exists()).toBe(false)
  })

  it('flags offline data for an ad-hoc fallback route that is not a preset scenario', () => {
    // 没配 Key 时随便输坐标走的也是本地兜底，后端那时 demo_mode 是 false。
    // 旧判据在这种情况下一句提示都没有，这条就是为它加的。
    const wrapper = mountResult({
      ...RESULT,
      route: { ...RESULT.route, source: 'fallback', demo_mode: false },
    })

    expect(wrapper.text()).toContain('离线演示数据')
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

  // T6：兜底路线以前只有 1 段（route_engine 硬编码单元素 steps），折叠按钮
  // 因此永远不出现，这个交互从来没被人看到过。现在兜底会给 6 段，
  // 按钮必须真的出现、真的能收起来 —— 而 3 段时不该出现。
  it('shows the collapse toggle only when there are more steps than the collapsed count', async () => {
    const short = mountResult(RESULT)
    expect(short.findAll('.steps__item')).toHaveLength(3)
    expect(short.find('.steps__toggle').exists()).toBe(false)

    // 后端兜底真实给出的段数（大工 -> 星海：折线 7 点 -> 6 段）
    const fallback = {
      ...RESULT,
      route: {
        ...RESULT.route,
        steps: [
          { instruction: '从起点向东走约 1389 米', road: '', distance: '1389', duration: '1111' },
          { instruction: '继续向东走约 1370 米', road: '', distance: '1370', duration: '1096' },
          { instruction: '继续向东走约 916 米', road: '', distance: '916', duration: '733' },
          { instruction: '继续向东南走约 1103 米', road: '', distance: '1103', duration: '882' },
          { instruction: '继续向东走约 1055 米', road: '', distance: '1055', duration: '845' },
          { instruction: '向东走约 1087 米后到达终点', road: '', distance: '1087', duration: '869' },
        ],
      },
    }
    const wrapper = mountResult(fallback)

    expect(wrapper.find('.steps__count').text()).toBe('6 段')
    expect(wrapper.findAll('.steps__item')).toHaveLength(4)
    const toggle = wrapper.find('.steps__toggle')
    expect(toggle.text()).toBe('展开其余 2 段')

    await toggle.trigger('click')
    expect(wrapper.findAll('.steps__item')).toHaveLength(6)
    expect(wrapper.find('.steps__toggle').text()).toBe('收起指引')

    await wrapper.find('.steps__toggle').trigger('click')
    expect(wrapper.findAll('.steps__item')).toHaveLength(4)

    // road 为空时那一行整个隐掉，不能留一个空的路名占位
    expect(wrapper.find('.steps__road').exists()).toBe(false)
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
    // T4：一个亮点都没有的时候理由框说实话，而不是「暂时没有额外说明」那种
    // 听起来像功能坏了的占位
    expect(wrapper.text()).toContain('没有找到值得绕行的亮点')
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

  // T8-4：视觉确认必须对应真实结果。按钮变色只说明「你点了这个」，
  // 「后端真的学到了什么」得由文字说 —— 否则归因失败时界面在骗人。
  it('says what the feedback actually taught the backend', async () => {
    const api = makeApi({
      sendFeedback: vi.fn(async () => ({ ok: true, learned: ['咖啡', '餐饮'] })),
    })
    const wrapper = mountResult({ ...RESULT, trip_id: 12 }, api)

    await wrapper.findAll('.result__feedback button')[0].trigger('click')
    await flushPromises()

    expect(api.sendFeedback).toHaveBeenCalledWith({ tripId: 12, liked: true, mode: '+15' })
    const note = wrapper.find('.result__feedback-note')
    expect(note.exists()).toBe(true)
    expect(note.text()).toContain('已记住')
    expect(note.text()).toContain('咖啡')
    expect(note.text()).toContain('加权')
  })

  it('says the opinion will lower the weight when the route was disliked', async () => {
    const api = makeApi({
      sendFeedback: vi.fn(async () => ({ ok: true, learned: ['咖啡'] })),
    })
    const wrapper = mountResult({ ...RESULT, trip_id: 3 }, api)

    await wrapper.findAll('.result__feedback button')[1].trigger('click')
    await flushPromises()

    expect(wrapper.find('.result__feedback-note').text()).toContain('降权')
  })

  // 后端 200 但 learned 为空 = 没归因上，后续推荐不会变。这时候写「已记住」是骗人。
  it('admits when the feedback could not be attributed to any category', async () => {
    const api = makeApi({
      sendFeedback: vi.fn(async () => ({ ok: true, learned: [] })),
    })
    const wrapper = mountResult(RESULT, api)

    await wrapper.findAll('.result__feedback button')[0].trigger('click')
    await flushPromises()

    const text = wrapper.find('.result__feedback-note').text()
    expect(text).toContain('没能归因')
    expect(text).not.toContain('已记住')
  })

  it('says the feedback never left when the endpoint is missing', async () => {
    const api = makeApi({ sendFeedback: vi.fn(async () => ({ ok: false, learned: [] })) })
    const wrapper = mountResult(RESULT, api)

    await wrapper.findAll('.result__feedback button')[1].trigger('click')
    await flushPromises()

    expect(wrapper.find('.result__feedback-note').text()).toContain('没送出去')
  })

  // R7：这两个按钮过去 emit 的是同一个 `back`，于是「重新规划」把人踢回首页。
  // 现在分成两个事件，下面两条各盯一个 —— 把 replan 改回 emit('back')
  // 会让第一条红（收不到 replan），第二条仍然绿，所以两条都得在。
  it('emits replan from the re-plan button and stays on the result page', async () => {
    const wrapper = mountResult(RESULT)
    await wrapper.find('.result__replan').trigger('click')

    expect(wrapper.emitted('replan')).toHaveLength(1)
    expect(wrapper.emitted('back')).toBeUndefined()
    // 还在结果页：标题和指标都还在
    expect(wrapper.find('.result__title').exists()).toBe(true)
    expect(wrapper.findAll('.tile')).toHaveLength(4)
  })

  // R7：结果页头里没有第二个「返回首页」。「返回首页」在吸顶页头（SiteHeader）里，
  // 它的 back 走的是 App 层，链路断言在 tests/App.test.js。这里钉住的是
  // 结果页自己不再摆第二个「返回首页」—— 摆了就是同一个动作出现两遍。
  //
  // S3：页头现在还有三个模式按钮，所以断言从「只有一个按钮」改成
  // 「只有一个 replan 按钮 + 三个模式按钮，且没有返回首页」。放松成
  // 「不含返回首页」是不够的：那样再摆一个「重新规划」也能过。
  it('does not duplicate the home button that the sticky header already has', () => {
    const wrapper = mountResult(RESULT)

    expect(wrapper.findAll('.result__head .result__replan')).toHaveLength(1)
    expect(wrapper.findAll('.result__head .result__mode-btn')).toHaveLength(3)
    // 页头里的按钮就是这四个，没有别的
    expect(wrapper.findAll('.result__head button')).toHaveLength(4)
    expect(wrapper.find('.result__head').text()).not.toContain('返回首页')
  })

  // ---------- S1(c)：绕行不足一分钟时「额外时间」格改印距离 ----------

  it('shows the distance delta when the detour rounds down to zero minutes', () => {
    // 兜底演示数据的真实绕行只有几十米，round() 抹平成 0 —— 三个模式在这个格子上
    // 都显示 +0，正是用户说「三个模式没区别」时盯着的地方。距离增量是从两条折线
    // 量出来的，三个模式各不相同。
    const wrapper = mountResult({
      ...RESULT,
      detour_minutes: 0,
      route: { ...RESULT.route, distance: 2353 },
      baseline_route: { polyline: '121.6068,38.9180;121.5854,38.9325', distance: 2340 },
    })

    const tile = wrapper
      .findAll('.tile')
      .find((t) => t.find('.tile__label').text() === '额外时间')

    expect(tile.find('.tile__number').text()).toBe('+13')
    // 单位必须跟着换，否则印出来是「+13 分钟」
    expect(tile.find('.tile__unit').text()).toBe('米')
    expect(tile.text()).toContain('不足一分钟')
  })

  it('keeps minutes when the detour is a real minute or more', () => {
    // 有真实分钟数时不该改用距离 —— 那是把更精确的信息换成更粗的。
    const wrapper = mountResult({
      ...RESULT,
      detour_minutes: 5,
      route: { ...RESULT.route, distance: 2900 },
      baseline_route: { polyline: '121.6068,38.9180;121.5854,38.9325', distance: 2340 },
    })

    const tile = wrapper
      .findAll('.tile')
      .find((t) => t.find('.tile__label').text() === '额外时间')

    expect(tile.find('.tile__number').text()).toBe('+5')
    expect(tile.find('.tile__unit').text()).toBe('分钟')
  })

  it('falls back to plain zero minutes when the distance delta is unknowable', () => {
    // 没有 baseline_route（老后端、或降级出口两条线相同）时算不出增量。
    // 此时保留原来的 +0 分钟，不能印一个编出来的距离。
    const wrapper = mountResult({ ...RESULT, detour_minutes: 0 })

    const tile = wrapper
      .findAll('.tile')
      .find((t) => t.find('.tile__label').text() === '额外时间')

    expect(tile.find('.tile__number').text()).toBe('0')
    expect(tile.find('.tile__unit').text()).toBe('分钟')
    expect(tile.text()).toContain('几乎不耽误')
  })

  // ---------- S3：结果页换模式 ----------

  it('emits replan with the picked mode and highlights the current one', async () => {
    // 评委在同一条路线上连点三个模式看差异 —— 这是 S1 那些几何差异的展示入口。
    const wrapper = mountResult(RESULT)
    const buttons = wrapper.findAll('.result__mode-btn')

    expect(buttons).toHaveLength(3)
    // 当前是 +15（RESULT.request.mode），高亮必须跟着 request 走
    const active = buttons.filter((b) => b.classes().includes('result__mode-btn--active'))
    expect(active).toHaveLength(1)
    expect(active[0].text()).toContain('+15')
    expect(active[0].attributes('aria-checked')).toBe('true')

    // 点 roam：事件必须带上那个模式，否则 App 层只能按旧模式重算
    await buttons[2].trigger('click')
    expect(wrapper.emitted('replan')).toEqual([['roam']])
    // 不回首页
    expect(wrapper.emitted('back')).toBeUndefined()
  })

  it('reuses the home mode vocabulary instead of inventing a second one', () => {
    // 同一个概念在两个页面长得不一样，用户会以为是两回事。三个 label 必须来自
    // EXPLORE_MODES（首页那份），不是结果页自己写死的字符串。
    const wrapper = mountResult(RESULT)
    const labels = wrapper.findAll('.result__mode-btn').map((b) => b.text().trim())

    expect(labels).toEqual(EXPLORE_MODES.map((m) => m.label))
  })

  it('locks the mode buttons while a re-plan is in flight', async () => {
    const wrapper = mount(ResultView, {
      props: { result: RESULT, replanning: true },
      global: { provide: { [API_KEY]: makeApi() } },
    })

    const buttons = wrapper.findAll('.result__mode-btn')
    buttons.forEach((button) => expect(button.attributes('disabled')).toBeDefined())

    await buttons[0].trigger('click')
    expect(wrapper.emitted('replan')).toBeUndefined()
  })

  it('locks the re-plan button and says so while the request is in flight', async () => {
    const wrapper = mount(ResultView, {
      props: { result: RESULT, replanning: true },
      global: { provide: { [API_KEY]: makeApi() } },
    })

    const button = wrapper.find('.result__replan')
    expect(button.attributes('disabled')).toBeDefined()
    expect(button.text()).toContain('重新规划中')

    await button.trigger('click')
    expect(wrapper.emitted('replan')).toBeUndefined()
  })

  it('shows the re-plan failure as a Chinese alert', () => {
    const wrapper = mount(ResultView, {
      props: { result: RESULT, replanError: '重新规划失败，请稍后再试' },
      global: { provide: { [API_KEY]: makeApi() } },
    })

    const notice = wrapper.find('.result__replan-error')
    expect(notice.exists()).toBe(true)
    expect(notice.attributes('role')).toBe('alert')
    expect(notice.text()).toContain('重新规划失败')
    // 上一轮修过的裸英文，别再退回去
    expect(wrapper.text()).not.toContain('Failed to fetch')
  })

  // R8：地图排在指标之前。断言用 DOM 顺序，不看视觉 —— 视觉靠截图。
  it('puts the map above the metrics and below the title', () => {
    const wrapper = mountResult(RESULT)
    const html = wrapper.html()

    const title = html.indexOf('result__title')
    const map = html.indexOf('map__frame')
    const tiles = html.indexOf('result__tiles')
    const meter = html.indexOf('result__meter')
    const pois = html.indexOf('result__pois')

    expect(title).toBeGreaterThanOrEqual(0)
    expect(map).toBeGreaterThanOrEqual(0)
    expect(title).toBeLessThan(map)
    expect(map).toBeLessThan(tiles)
    expect(tiles).toBeLessThan(meter)
    expect(meter).toBeLessThan(pois)
  })

  it('passes the backend baseline_route through to the map', () => {
    // P3-4 的接缝：MapView 的用例是直接挂载组件的，覆盖不到这里。
    // 这条 prop 一旦漏掉，灰虚线就静默消失 —— 不报错、不白屏，只是对比没了。
    const wrapper = mountResult({
      ...RESULT,
      baseline_route: { polyline: '121.6068,38.9180;121.5900,38.9250;121.5854,38.9325' },
    })

    const map = wrapper.findComponent({ name: 'MapView' })
    expect(map.props('baselineRoute')).toEqual({
      polyline: '121.6068,38.9180;121.5900,38.9250;121.5854,38.9325',
    })
    expect(wrapper.text()).toContain('原本路线')
  })

  it('renders without a comparison when the backend omits baseline_route', () => {
    const wrapper = mountResult(RESULT)

    expect(wrapper.findComponent({ name: 'MapView' }).props('baselineRoute')).toBe(null)
    expect(wrapper.text()).not.toContain('原本路线')
    expect(wrapper.find('.map-container').exists()).toBe(true)
  })

  // T3：图上两条线是「有区别」，但只有把两组距离 + 时长并排印出来，验收人才看得到
  // 区别是多少。这条钉住四个数字都在，且差值带符号。
  //
  // R5：断言从 `.compare` 迁到指标格上 —— 独立对比块已并进四个格子，
  // 但「四个数字都在、差值带符号」这个要求一条都没放松：原值现在是格子里的
  // `.tile__baseline`，现值是同一个格子的 `.tile__number`，差值是 `.tile__delta`。
  it('prints distance and duration for both routes with the delta', () => {
    const wrapper = mountResult({
      ...RESULT,
      baseline_route: {
        // 与推荐不同的走法：polyline 相同就视为「没有对比」，见下一条用例
        polyline: '121.6068,38.9180;121.5960,38.9260;121.5854,38.9325',
        distance: 2100,
        duration: 1200,
      },
    })

    // 带对比的是「总计」（时长）和「推荐路线距离」两格，基准时长格印的就是原值本身
    const tiles = wrapper.findAll('.tile').filter((tile) => tile.find('.tile__baseline').exists())
    expect(tiles).toHaveLength(2)

    const byLabel = (label) =>
      wrapper.findAll('.tile').find((tile) => tile.find('.tile__label').text() === label)

    const durationTile = byLabel('总计')
    expect(durationTile.find('.tile__baseline').text()).toContain('20 分钟')
    expect(durationTile.find('.tile__number').text()).toBe('26')
    // 推荐比基准多 200 秒，符号必须是「+」，不然读起来像绕行反而更近
    expect(durationTile.find('.tile__delta').text()).toContain('+3 分钟')

    const distanceTile = byLabel('推荐路线距离')
    expect(distanceTile.find('.tile__baseline').text()).toContain('2.1 公里')
    expect(distanceTile.find('.tile__number').text()).toBe('2.3 公里')
    // 推荐比基准多 240 米，同样必须带「+」
    expect(distanceTile.find('.tile__delta').text()).toContain('+240 米')

    // R5 的要点是「原值和现值在同一个格子里上下叠」，不是又分成两处。
    // 原值必须排在现值前面（小字在上、大字在下）。
    const html = distanceTile.html()
    expect(html.indexOf('tile__baseline')).toBeLessThan(html.indexOf('tile__number'))
  })

  // T3：降级出口把 route 原样塞进 baseline_route，两条线完全一样。
  // 这时候摆一个「原本 X · 推荐 X」的对比块是假对比，必须整块不显示 ——
  // 判据要和 MapView 的虚线判据一致，否则会出现「有对比块但图上没虚线」。
  //
  // R5：并进指标格之后这条更要守住 —— 格子是常在的，只有原值那一行会消失。
  // 「没有对比」现在等于「四个格子都只有大字」。
  it('hides the comparison block when the baseline is the same route', () => {
    const wrapper = mountResult({
      ...RESULT,
      baseline_route: { ...RESULT.route },
    })

    expect(wrapper.find('.compare').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('换掉了什么')
    // 四个格子都在，但一个原值 / 差值都没有
    expect(wrapper.findAll('.tile')).toHaveLength(4)
    expect(wrapper.find('.tile__baseline').exists()).toBe(false)
    expect(wrapper.find('.tile__delta').exists()).toBe(false)
  })

  // R5：hasComparison 只要求距离或时长之一算得出来。基准只有距离时，
  // 时长格不能印出「原 --」—— 那是把「算不出来」当成一个数字摆在屏幕上。
  it('leaves a tile plain when that half of the baseline is missing', () => {
    const wrapper = mountResult({
      ...RESULT,
      baseline_route: {
        polyline: '121.6068,38.9180;121.5960,38.9260;121.5854,38.9325',
        distance: 2100,
      },
    })

    const byLabel = (label) =>
      wrapper.findAll('.tile').find((tile) => tile.find('.tile__label').text() === label)

    expect(byLabel('推荐路线距离').find('.tile__baseline').text()).toContain('2.1 公里')
    expect(byLabel('总计').find('.tile__baseline').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('原 --')
  })

  // T5：后端可达上界是 7.0（TAG 3.0 + QUALITY 4.0），但真实数据里出现过 7.2，
  // 于是页面印出「7.2/7」。数字和分母必须同一个上界。
  it('never shows a score above the meter maximum', () => {
    const wrapper = mountResult({ ...RESULT, score: 9 })

    expect(wrapper.find('.meter__value').text()).toBe('7.0/7')
    expect(wrapper.text()).toContain('当前 7.0 分')
    expect(wrapper.text()).not.toContain('9.0')
  })

  // T4：「为什么推荐这条」原来只有一句叙事，回答不了「为什么是这条」。
  // 理由必须点名亮点、说清多花了几分钟、并把评分拆开。
  it('explains the recommendation with pois, detour and a score breakdown', () => {
    const wrapper = mountResult(RESULT)
    const reasons = wrapper.findAll('.narrative__reason').map((node) => node.text())

    expect(reasons).toHaveLength(3)
    // 亮点要点名，而且类型取最后一段（"餐饮服务;咖啡厅" -> "咖啡厅"），
    // 和 PoiCard 上的标签一致，否则看起来像两个不同的地方
    expect(reasons[0]).toContain('2 处亮点')
    expect(reasons[0]).toContain('理工咖啡小铺（咖啡厅 4.4 分）')
    expect(reasons[0]).toContain('海边散步道（景点 4.6 分）')
    expect(reasons[0]).not.toContain('餐饮服务')
    // 绕行代价要放进用户选的额度里说，光说「多花 5 分钟」看不出贵不贵
    expect(reasons[1]).toContain('原本 21 分钟')
    expect(reasons[1]).toContain('多花 5 分钟')
    expect(reasons[1]).toContain('15 分钟额度以内')
    // 拆分必须和 score 自洽：3.5 + 2.1 - 1.0 = 4.6
    expect(reasons[2]).toContain('4.6 / 7')
    expect(reasons[2]).toContain('亮点质量 3.5')
    expect(reasons[2]).toContain('口味契合 2.1')
    expect(reasons[2]).toContain('绕行扣 1.0')
    // 叙事保留，但退到理由下面收尾
    expect(wrapper.find('.narrative__text').text()).toContain('从大工沿海边走')
  })

  // T4：拆分是从 SCORE_WEIGHTS（后端权重的副本）反推的。数据不满足那个公式时
  // （后端改了权重、或者分数是别处硬写的）必须整条不显示 ——
  // 摆一组加不回总分的数字比不摆更糟。
  it('drops the score breakdown when the numbers do not add up', () => {
    // 质量 3.52 + 绕行扣 1.0 意味着契合度要 3.88，超过 TAG_WEIGHT 3.0
    const wrapper = mountResult({ ...RESULT, score: 6.4 })
    const reasons = wrapper.findAll('.narrative__reason').map((node) => node.text())

    expect(reasons).toHaveLength(3)
    expect(reasons[2]).toContain('探索评分 6.4 / 7')
    expect(reasons[2]).not.toContain('亮点质量')
    expect(reasons[2]).not.toContain('口味契合')
  })

  // T4：降级出口（没有亮点、评分 0）不许硬凑理由。
  it('tells the truth instead of inventing reasons when the route is degraded', () => {
    const wrapper = mountResult({
      ...RESULT,
      score: 0,
      detour_minutes: 0,
      pois: [],
      narrative: '',
    })

    expect(wrapper.findAll('.narrative__reason')).toHaveLength(0)
    const note = wrapper.find('.narrative__degraded')
    expect(note.exists()).toBe(true)
    expect(note.text()).toContain('没有找到值得绕行的亮点')
    expect(note.text()).toContain('最快路线')
    // 没有亮点就不该出现任何「沿途多了 N 处亮点」「探索评分 X」这类说法
    const text = wrapper.text()
    expect(text).not.toContain('处亮点')
    expect(text).not.toContain('探索评分 0')
  })

  // T4：绕了路却没有亮点是最需要说实话的一格 —— 多出来的时间没有任何价值支撑。
  it('admits when a detour bought nothing', () => {
    const wrapper = mountResult({ ...RESULT, score: 0, detour_minutes: 6, pois: [] })

    const note = wrapper.find('.narrative__degraded').text()
    expect(note).toContain('没有匹配到值得绕行的亮点')
    expect(note).toContain('6 分钟')
    expect(wrapper.findAll('.narrative__reason')).toHaveLength(0)
  })
})
