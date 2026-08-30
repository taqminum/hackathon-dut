<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue'
import HomeView from './views/HomeView.vue'
import ResultView from './views/ResultView.vue'
import SiteHeader from './components/SiteHeader.vue'
import { DEFAULT_MODE } from './constants.js'
import { useApi } from './composables/useApi.js'

/**
 * 应用外壳。两个视图之间切换，不引入路由依赖（Hackathon 范围内够用）。
 */
const api = useApi()

const currentView = ref('home')
const selectedRoute = ref(null)
const mode = ref(DEFAULT_MODE)
const online = ref(null)
// R7：重新规划的进行态与错误。放在 App 层是因为发请求的是这一层 ——
// 结果页只负责显示，不再自己知道怎么重发。
const replanning = ref(false)
const replanError = ref('')
// 同一段行程里「重新规划」需要避开的 POI 累积清单。以队友/用户视角：
// 每次重算都要比上一次更陌生一点，否则第二次点按钮换来的还是同一家店。
const excludedPois = ref([])

/** T2：健康灯要反映真实状态，不能是开场点亮一次就永远亮着。
 * 演示中途后端被 Ctrl-C 掉是常事，那时灯还绿着，比没有灯更误导。 */
const HEALTH_INTERVAL = 15000
let healthTimer = null

function onRouteSelected(route) {
  if (!route) return
  // 新的起点/终点就是一趟新行程，上一轮的避让清单不能带过来
  excludedPois.value = []
  selectedRoute.value = route
  currentView.value = 'result'
  try {
    globalThis.scrollTo?.({ top: 0, behavior: 'smooth' })
  } catch {
    // jsdom / 部分 WebView 不实现 scrollTo，忽略即可
  }
}

function onBack() {
  currentView.value = 'home'
  selectedRoute.value = null
}

/** R7：「重新规划」。这个按钮过去 emit 的也是 `back`，于是和页头的「返回首页」
 * 完全同一个行为 —— 名字说的是「再算一次」，做的是「回首页」。
 *
 * 请求参数不需要另外提升到这里：`HomeView` 提交时就把 `request` 一起塞进了结果
 * （`emit('select', { ...result, request: payload })`），而 `selectedRoute` 本来就
 * 存在 App 层。所以起终点和模式一直都在手边，重发一次即可 —— 不必为此加 store，
 * 也不必用 `key` 强制重挂 HomeView（那会闪一下首页）。
 *
 * 保留 `request` 原样回填：里面的 originLabel / destinationLabel 是结果页标题的
 * 显示来源，用新响应覆盖掉的话标题会从地名退回坐标。
 *
 * S3：`nextMode` 让结果页能直接换模式重算。**新模式必须写回 `request`** ——
 * 只把它传给接口的话，用户切到 roam 之后再点一次「重新规划」会退回旧模式，
 * 而屏幕上的模式标签也还是旧的。地名照旧从 `request` 继承，不被新响应冲掉。
 */
async function onReplan(payload) {
  const request = selectedRoute.value?.request
  if (!request || replanning.value) return

  // 只接受合法模式串：模板里 @click 可能把事件对象传进来（和 HomeView.handleSubmit
  // 里同一个坑），那时候按「用当前模式重算」处理。
  const nextMode = typeof payload === 'string' ? payload : payload?.mode
  const nextPoiCount =
    Number(typeof payload === 'object' && payload !== null ? payload.poiCount : NaN) ||
    Number(request.poiCount) ||
    1
  const mode = typeof nextMode === 'string' && nextMode ? nextMode : request.mode
  const oldPois = Array.isArray(selectedRoute.value?.pois) ? selectedRoute.value.pois : []
  const exclude = mergeExcludedPois([...excludedPois.value, ...oldPois])

  replanning.value = true
  replanError.value = ''
  try {
    const result = await api.recommendRoute({
      origin: request.origin,
      destination: request.destination,
      mode,
      poiCount: nextPoiCount,
      city: request.city || '大连市',
      exclude,
    })
    if (!result?.route) {
      replanError.value = '这次没算出可用路线，起终点没变，可以再试一次'
      return
    }
    excludedPois.value = mergeExcludedPois([
      ...exclude,
      ...(Array.isArray(result.pois) ? result.pois : []),
    ])
    selectedRoute.value = { ...result, request: { ...request, mode, poiCount: nextPoiCount } }
  } catch (err) {
    // 中文兜底。err.message 在断网时是 `Failed to fetch`，上一轮已经修过一次
    // 裸英文透传，这里不能再退回去 —— useApi 会把已知错误翻好，剩下的兜底。
    replanError.value = err?.message || '重新规划失败，请稍后再试'
  } finally {
    replanning.value = false
  }
}

function mergeExcludedPois(items) {
  const seen = new Set()
  const merged = []
  for (const item of items) {
    if (!item || typeof item !== 'object') continue
    const name = String(item.name || '').trim()
    const location = String(item.navigation_location || item.location || '').trim()
    const key = `${name}|${location}`
    if (!key || seen.has(key)) continue
    seen.add(key)
    merged.push({
      name,
      location: location || '',
      navigation_location: String(item.navigation_location || '').trim(),
    })
  }
  return merged
}

async function refreshHealth() {
  const health = await api.checkHealth()
  online.value = !!health?.online
}

onMounted(() => {
  refreshHealth()
  // 页面被切到后台时浏览器会节流定时器，回到前台再补一次，
  // 免得切回来看到的是十几秒前的状态
  healthTimer = setInterval(refreshHealth, HEALTH_INTERVAL)
  globalThis.document?.addEventListener?.('visibilitychange', onVisibilityChange)
})

function onVisibilityChange() {
  if (globalThis.document?.visibilityState === 'visible') refreshHealth()
}

onBeforeUnmount(() => {
  if (healthTimer) clearInterval(healthTimer)
  healthTimer = null
  globalThis.document?.removeEventListener?.('visibilitychange', onVisibilityChange)
})
</script>

<template>
  <div class="app">
    <SiteHeader :online="online" :show-back="currentView === 'result'" @back="onBack" />

    <main class="app__main">
      <HomeView
        v-if="currentView === 'home'"
        v-model="mode"
        @select="onRouteSelected"
      />
      <ResultView
        v-else
        :result="selectedRoute"
        :replanning="replanning"
        :replan-error="replanError"
        @back="onBack"
        @replan="onReplan"
      />
    </main>

    <footer class="app__foot">
      <div class="bh-shell app__foot-inner">
        <span class="bh-label">偶遇导航 · 大工黑客松 S2</span>
        <span class="bh-label app__foot-note">地图数据 © OpenStreetMap</span>
      </div>
    </footer>
  </div>
</template>

<style scoped>
.app {
  display: flex;
  flex-direction: column;
  min-height: 100vh;
}

.app__main {
  flex: 1 1 auto;
}

.app__foot {
  border-top: var(--bh-line) solid var(--bh-ink);
  background: var(--bh-ink);
  color: var(--bh-paper);
}

.app__foot-inner {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--bh-3);
  padding-top: var(--bh-4);
  padding-bottom: var(--bh-4);
}

.app__foot-note {
  opacity: 0.7;
}
</style>
