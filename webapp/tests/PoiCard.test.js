import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import PoiCard from '../src/components/PoiCard.vue'

/**
 * R6：卡片点击展开详情。这里钉三件事：
 *   1. 字段齐全时能展开、能收起，`aria-expanded` 跟着变
 *   2. 缺字段的行整行不渲染，一个字段都没有时连展开入口都不出现
 *   3. 点击**总是**发出 focus-poi（图上要 pan 过去），展开与否不影响它
 *
 * 后端 `_extract_text` 取不到时给的是**空串**，不是 undefined —— 桩数据里
 * 又可能直接省掉键。两种形态都当「没有」处理，所以两种都要测到。
 */
const BASE = {
  name: '理工咖啡小铺',
  type: '餐饮服务;咖啡厅',
  distance: '180',
  rating: 4.4,
  location: '121.5432,38.8871',
}

const RICH = {
  ...BASE,
  address: '大连市甘井子区凌工路 2 号',
  tel: '0411-8470-9988',
  opentime: '07:30-21:00',
  photo: 'https://example.invalid/a.jpg',
}

const mountCard = (poi, props = {}) => mount(PoiCard, { props: { poi, index: 0, ...props } })

describe('PoiCard 展开详情', () => {
  it('expands and collapses on click, tracking aria-expanded', async () => {
    const wrapper = mountCard(RICH)

    expect(wrapper.attributes('aria-expanded')).toBe('false')
    expect(wrapper.find('.poi__detail').exists()).toBe(false)

    await wrapper.trigger('click')
    expect(wrapper.attributes('aria-expanded')).toBe('true')
    const detail = wrapper.find('.poi__detail')
    expect(detail.exists()).toBe(true)
    expect(detail.text()).toContain('凌工路 2 号')
    expect(detail.text()).toContain('0411-8470-9988')
    expect(detail.text()).toContain('07:30-21:00')
    expect(detail.find('.poi__photo').attributes('src')).toBe(RICH.photo)

    // 收起后详情区必须真的从 DOM 消失，不是只改了个 class
    await wrapper.trigger('click')
    expect(wrapper.attributes('aria-expanded')).toBe('false')
    expect(wrapper.find('.poi__detail').exists()).toBe(false)
  })

  // role="button" 的卡片必须能不用鼠标操作，否则这个交互对键盘用户不存在
  it('expands with Enter and Space', async () => {
    const wrapper = mountCard(RICH)

    await wrapper.trigger('keydown', { key: 'Enter' })
    expect(wrapper.find('.poi__detail').exists()).toBe(true)

    await wrapper.trigger('keydown', { key: ' ' })
    expect(wrapper.find('.poi__detail').exists()).toBe(false)
  })

  // 一个字段都没有时不该许诺「展开详情」—— 点开一个空框比不让点更糟。
  // 兜底演示数据（DALIAN_POI_SCENARIOS）就是这种形态，所以这不是边角情况。
  it('offers no expansion when the poi has only the basic fields', async () => {
    const wrapper = mountCard(BASE)

    expect(wrapper.find('.poi__toggle').exists()).toBe(false)
    // 展不开的卡片不该暴露 aria-expanded：那会让读屏念出一个不存在的可展开区
    expect(wrapper.attributes('aria-expanded')).toBeUndefined()

    await wrapper.trigger('click')
    expect(wrapper.find('.poi__detail').exists()).toBe(false)
    // 但点击仍然要选中它（图上 pan 过去），展不开不等于点了没反应
    expect(wrapper.emitted('focus-poi')).toEqual([[0]])
  })

  // 缺失的行整行不渲染。后端给空串、桩里直接省键，两种都算「没有」。
  it('renders only the rows it actually has', async () => {
    const wrapper = mountCard({ ...BASE, address: '凌工路 2 号', tel: '', photo: '' })

    await wrapper.trigger('click')
    const detail = wrapper.find('.poi__detail')
    expect(detail.exists()).toBe(true)
    expect(detail.text()).toContain('凌工路 2 号')
    // 缺的三项都不该留下标签行或占位文案
    expect(detail.text()).not.toContain('电话')
    expect(detail.text()).not.toContain('营业时间')
    expect(detail.text()).not.toContain('暂无')
    expect(detail.find('.poi__photo').exists()).toBe(false)
    expect(wrapper.findAll('.poi__row-value')).toHaveLength(1)
  })

  // 只有照片、没有文字行时也要能展开：hasDetails 不能只看 details.length
  it('expands for a photo-only poi', async () => {
    const wrapper = mountCard({ ...BASE, photo: 'https://example.invalid/b.jpg' })

    expect(wrapper.find('.poi__toggle').exists()).toBe(true)
    await wrapper.trigger('click')
    expect(wrapper.find('.poi__photo').exists()).toBe(true)
    expect(wrapper.find('.poi__rows').exists()).toBe(false)
  })

  // ---------- S2：「距路线约 N 米」必须是到路线的距离 ----------

  // 卡片上那行字写的是「距路线约」，而 `distance` 是高德 place/around 回的
  // 「距搜索采样点」距离 —— 采样点按里程 25%/50%/75% 取，这个数字既不是距路线
  // 也不是距起点。实测出现过「真实 1.6 米显示 70、真实 24.2 米显示 7」的对调。
  it('prints the measured off-route distance, not the amap sample distance', () => {
    const wrapper = mountCard({ ...BASE, distance: '70', off_route_meters: 2 })

    expect(wrapper.find('.poi__distance').text()).toContain('2 米')
    // 旧字段的值不能出现在这一行里
    expect(wrapper.find('.poi__distance').text()).not.toContain('70')
  })

  // 后端算不出距离（折线退化）时字段就不在。此时**不能**退回显示 distance ——
  // 那等于把一个没有意义的数字重新标成「距路线约」，正是这条要修的缺陷。
  it('renders no distance row at all when the measurement is missing', () => {
    const wrapper = mountCard({ ...BASE, distance: '70' })

    expect(wrapper.find('.poi__distance').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('距路线约')
    expect(wrapper.text()).not.toContain('70')
  })

  // 第一张卡是路线真的经过的那个，其余只是在旁边。配合真实米数，用户自己
  // 就能看出 1 号是 2 米、2 号是 130 米。
  it('labels the first card as the waypoint and the rest as nearby', () => {
    const waypoint = mountCard({ ...BASE, off_route_meters: 2 }, { index: 0 })
    expect(waypoint.find('.poi__route-kind').text()).toBe('途经')

    const nearby = mountCard({ ...BASE, off_route_meters: 130 }, { index: 1 })
    expect(nearby.find('.poi__route-kind').text()).toBe('附近')
  })

  // 展开态是卡片自己的，和 active（图上高亮的是哪个）无关 ——
  // 两个混成一个状态的话，「点第二个亮点」会把第一个的详情连带收起。
  it('keeps expansion independent from the active highlight', async () => {
    const wrapper = mountCard(RICH, { active: false })

    await wrapper.trigger('click')
    expect(wrapper.find('.poi__detail').exists()).toBe(true)

    await wrapper.setProps({ active: true })
    expect(wrapper.find('.poi__detail').exists()).toBe(true)
    await wrapper.setProps({ active: false })
    expect(wrapper.find('.poi__detail').exists()).toBe(true)
  })
})
