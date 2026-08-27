import { inject } from 'vue'
import { createRecommendApi, defaultApi } from '../api.js'

export const API_KEY = Symbol('recommendApi')

/**
 * 取得 api 实例。
 * 优先级：provide 注入 > globalThis.__recommendApi（测试 / 本地 mock）> 默认 fetch 实现。
 * 组件只依赖这个 composable，方便单测替换。
 */
export function useApi() {
  const injected = inject(API_KEY, null)
  if (injected) return injected

  // 旧测试使用 '__recommendApi' 字符串键注入，这里保持兼容
  const legacy = inject('__recommendApi', null)
  if (legacy) return { ...defaultApi, ...legacy }

  const globalClient = globalThis.__recommendApi
  if (typeof globalClient === 'function') {
    return createRecommendApi(globalClient)
  }
  if (globalClient && typeof globalClient === 'object') {
    return { ...defaultApi, ...globalClient }
  }

  return defaultApi
}
