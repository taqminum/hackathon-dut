import { describe, it, expect } from 'vitest'
import { flushPromises } from '@vue/test-utils'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import App from '../src/App.vue'
import HomeView from '../src/views/HomeView.vue'
import ResultView from '../src/views/ResultView.vue'
 
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
})
