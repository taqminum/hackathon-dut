<script setup>
import { ref } from 'vue'
import ExploreModeSelector from '../components/ExploreModeSelector.vue'
import { recommendRoute } from '../api.js'

const origin = ref('')
const destination = ref('')
const mode = ref('+5')
const loading = ref(false)
const error = ref('')
const routes = ref([])

async function handleSubmit() {
  error.value = ''
  loading.value = true
  try {
    const data = await recommendRoute({ origin: origin.value, destination: destination.value, mode: mode.value })
    routes.value = data.routes || []
  } catch (err) {
    error.value = '获取路线失败，请稍后重试'
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <section class="home">
    <h1>偶遇导航</h1>
    <label>
      <span>起点</span>
      <input v-model="origin" placeholder="例如：大连理工大学" />
    </label>
    <label>
      <span>终点</span>
      <input v-model="destination" placeholder="例如：星海广场" />
    </label>
    <ExploreModeSelector v-model="mode" />
    <button :disabled="loading" @click="handleSubmit">生成偶遇路线</button>
    <p v-if="loading">正在寻找可控的意外…</p>
    <p v-if="error">{{ error }}</p>
    <ul v-if="routes.length">
      <li v-for="item in routes" :key="item.id">{{ item }}</li>
    </ul>
  </section>
</template>

<style scoped>
.home {
  display: grid;
  gap: 16px;
}
label {
  display: grid;
  gap: 6px;
}
input {
  padding: 10px;
  border-radius: 10px;
  border: 1px solid #d1d5db;
}
button {
  justify-self: start;
  padding: 10px 14px;
  border-radius: 10px;
  border: none;
  background: #111827;
  color: #fff;
}
</style>
