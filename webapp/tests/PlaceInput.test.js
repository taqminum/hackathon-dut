import { describe, it, expect, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import PlaceInput from '../src/components/PlaceInput.vue'

function mountInput(props = {}) {
  return mount(PlaceInput, { props: { label: '起点', modelValue: '', ...props } })
}

describe('PlaceInput', () => {
  it('renders a labelled combobox', () => {
    const wrapper = mountInput({ badge: 'A', placeholder: '例如：大连理工大学' })
    const input = wrapper.find('input')

    expect(input.attributes('role')).toBe('combobox')
    expect(input.attributes('placeholder')).toBe('例如：大连理工大学')
    expect(wrapper.find('label').attributes('for')).toBe(input.attributes('id'))
    expect(wrapper.text()).toContain('A')
  })

  it('emits typed values', async () => {
    const wrapper = mountInput()
    await wrapper.find('input').setValue('星海')

    expect(wrapper.emitted('update:modelValue')).toEqual([['星海']])
  })

  it('does not invent local suggestions when there is no real suggest api', async () => {
    const wrapper = mountInput({ modelValue: '星海' })
    await wrapper.find('input').trigger('focus')

    expect(wrapper.findAll('[role="option"]')).toHaveLength(0)
    expect(wrapper.text()).toContain('高德没有找到匹配地点')
  })

  // R3：改过来了 —— 选中回填的是地名，坐标走 `pick`。
  // 原来这条断言把「输入框里显示经纬度」锁成了预期行为，和 R2 修的是同一个毛病。
  it('fills the place name when picking a landmark and hands the coordinate to the parent', async () => {
    const suggestion = { name: '星海广场', address: '沙河口区', location: '121.5839,38.8816' }
    const wrapper = mountInput({
      suggestFn: vi.fn(async () => [suggestion]),
    })
    await wrapper.setProps({ modelValue: '星海' })
    await new Promise((resolve) => setTimeout(resolve, 320))
    await flushPromises()
    await wrapper.find('input').trigger('focus')
    await wrapper.findAll('[role="option"]')[0].trigger('mousedown')

    expect(wrapper.emitted('update:modelValue')).toEqual([['星海广场']])
    // 坐标没丢，只是换了出口：上层从 pick 里取，存进 originCoord 提交时用
    expect(wrapper.emitted('pick')[0][0].name).toBe('星海广场')
    expect(wrapper.emitted('pick')[0][0].location).toBe('121.5839,38.8816')
  })

  it('uses remote suggestions when the api returns results', async () => {
    const suggestFn = vi.fn(async () => [
      { name: '远端结果', address: '中山区', location: '121.6,38.9' },
    ])
    const wrapper = mountInput({ suggestFn })

    await wrapper.setProps({ modelValue: '中山' })
    await new Promise((resolve) => setTimeout(resolve, 320))
    await flushPromises()
    await wrapper.find('input').trigger('focus')

    expect(suggestFn).toHaveBeenCalledWith({ keyword: '中山' })
    expect(wrapper.text()).toContain('远端结果')
  })

  it('shows the real suggestion error instead of local fake matches', async () => {
    const suggestFn = vi.fn(async () => {
      throw new Error('offline')
    })
    const wrapper = mountInput({ suggestFn })

    await wrapper.setProps({ modelValue: '星海' })
    await new Promise((resolve) => setTimeout(resolve, 320))
    await flushPromises()
    await wrapper.find('input').trigger('focus')

    expect(wrapper.findAll('[role="option"]')).toHaveLength(0)
    expect(wrapper.text()).toContain('offline')
  })

  it('skips the suggest call for coordinate input and shows the coordinate hint', async () => {
    const suggestFn = vi.fn(async () => [])
    const wrapper = mountInput({ suggestFn })

    await wrapper.setProps({ modelValue: '121.6068,38.9180' })
    await new Promise((resolve) => setTimeout(resolve, 320))
    await flushPromises()

    expect(suggestFn).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('坐标 121.6068,38.9180')
  })

  it('supports keyboard navigation and selection', async () => {
    const wrapper = mountInput({
      suggestFn: vi.fn(async () => [
        { name: '星海广场', address: '沙河口区', location: '121.5839,38.8816' },
      ]),
    })
    const input = wrapper.find('input')

    await wrapper.setProps({ modelValue: '星海' })
    await new Promise((resolve) => setTimeout(resolve, 320))
    await flushPromises()
    await input.trigger('focus')
    await input.trigger('keydown', { key: 'ArrowDown' })
    expect(wrapper.find('.place__option--active').exists()).toBe(true)

    await input.trigger('keydown', { key: 'Enter' })
    expect(wrapper.emitted('update:modelValue')).toEqual([['星海广场']])
    expect(wrapper.emitted('pick')[0][0].location).toBe('121.5839,38.8816')
  })

  it('closes the list on escape', async () => {
    const wrapper = mountInput({
      suggestFn: vi.fn(async () => [
        { name: '星海广场', address: '沙河口区', location: '121.5839,38.8816' },
      ]),
    })
    const input = wrapper.find('input')

    await wrapper.setProps({ modelValue: '星海' })
    await new Promise((resolve) => setTimeout(resolve, 320))
    await flushPromises()
    await input.trigger('focus')
    expect(wrapper.findAll('[role="option"]').length).toBeGreaterThan(0)

    await input.trigger('keydown', { key: 'Escape' })
    expect(wrapper.findAll('[role="option"]')).toHaveLength(0)
  })

  it('clears the value', async () => {
    const wrapper = mountInput({ modelValue: '星海广场' })
    await wrapper.find('.place__clear').trigger('click')

    expect(wrapper.emitted('update:modelValue')).toEqual([['']])
  })

  it('flags invalid input for assistive tech', () => {
    const wrapper = mountInput({ invalid: true })
    expect(wrapper.find('input').attributes('aria-invalid')).toBe('true')
  })
})
