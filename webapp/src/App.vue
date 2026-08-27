<script setup>
import { onMounted, ref } from 'vue'
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

function onRouteSelected(route) {
  if (!route) return
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

onMounted(async () => {
  const health = await api.checkHealth()
  online.value = !!health?.online
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
      <ResultView v-else :result="selectedRoute" @back="onBack" />
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
