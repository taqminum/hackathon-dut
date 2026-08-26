import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import ExploreModeSelector from '../src/components/ExploreModeSelector.vue'

function mountSelector(props = {}) {
  return mount(ExploreModeSelector, { props: { modelValue: '+5', ...props } })
}

describe('ExploreModeSelector', () => {
  it('renders the three explore modes as a radio group', () => {
    const wrapper = mountSelector()
    const radios = wrapper.findAll('[role="radio"]')

    expect(wrapper.find('[role="radiogroup"]').exists()).toBe(true)
    expect(radios).toHaveLength(3)
    expect(wrapper.text()).toContain('+5')
    expect(wrapper.text()).toContain('+15')
    expect(wrapper.text()).toContain('漫游')
  })

  it('marks the selected mode with aria-checked and the active class', () => {
    const wrapper = mountSelector({ modelValue: '+15' })
    const radios = wrapper.findAll('[role="radio"]')

    expect(radios[0].attributes('aria-checked')).toBe('false')
    expect(radios[1].attributes('aria-checked')).toBe('true')
    expect(radios[1].classes()).toContain('active')
  })

  it('emits the new mode value on click', async () => {
    const wrapper = mountSelector()
    await wrapper.findAll('[role="radio"]')[2].trigger('click')

    expect(wrapper.emitted('update:modelValue')).toEqual([['roam']])
  })

  it('does not re-emit when clicking the already selected mode', async () => {
    const wrapper = mountSelector({ modelValue: 'roam' })
    await wrapper.findAll('[role="radio"]')[2].trigger('click')

    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
  })

  it('ignores clicks while disabled', async () => {
    const wrapper = mountSelector({ disabled: true })
    await wrapper.findAll('[role="radio"]')[1].trigger('click')

    expect(wrapper.emitted('update:modelValue')).toBeUndefined()
  })

  it('describes the selected mode', () => {
    const wrapper = mountSelector({ modelValue: 'roam' })
    expect(wrapper.find('.mode__hint').text()).toContain('把最短路径放一边')
  })
})
