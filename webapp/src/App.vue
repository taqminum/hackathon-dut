<script setup>
import { ref } from 'vue'
import HomeView from './views/HomeView.vue'

const currentView = ref('home')
const selectedRoute = ref(null)

function onRouteSelected(route) {
  selectedRoute.value = route
  currentView.value = 'result'
}

function onBack() {
  currentView.value = 'home'
  selectedRoute.value = null
}
</script>

<template>
  <main>
    <HomeView v-if="currentView === 'home'" @select="onRouteSelected" />
    <section v-else>
      <button class="back-button" type="button" @click="onBack">返回首页</button>
      <p>推荐结果页占位：{{ selectedRoute }}</p>
    </section>
  </main>
</template>

<style scoped>
.back-button {
  border: none;
  background: #111827;
  color: #fff;
  padding: 10px 14px;
  border-radius: 10px;
}
</style>
