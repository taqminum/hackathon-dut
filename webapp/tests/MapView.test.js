import { describe, it, expect, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import MapView from '../src/components/MapView.vue'

vi.mock('../src/utils/leaflet.js', () => ({
  default: {
    map: vi.fn(() => ({
      setView: vi.fn().mockReturnThis(),
      addLayer: vi.fn().mockReturnThis(),
      removeLayer: vi.fn(),
      fitBounds: vi.fn().mockReturnThis(),
      remove: vi.fn(),
    })),
    tileLayer: vi.fn(() => ({ addTo: vi.fn().mockReturnThis() })),
    polyline: vi.fn(() => ({ addTo: vi.fn().mockReturnThis(), getBounds: vi.fn(() => []) })),
    marker: vi.fn(() => ({ addTo: vi.fn().mockReturnThis(), bindPopup: vi.fn() })),
  },
}))

describe('MapView', () => {
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
})
