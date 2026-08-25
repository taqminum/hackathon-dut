import { vi } from 'vitest'

Object.defineProperty(globalThis, '__recommendApi', {
  get() {
    return this['__recommendApiValue']
  },
  set(value) {
    this['__recommendApiValue'] = value
  },
  configurable: true,
})

export const provideRecommendApi = (value) => {
  globalThis.__recommendApi = value
  return { __recommendApi: value }
}

export function cleanupRecommendApi() {
  globalThis.__recommendApi = null
}
