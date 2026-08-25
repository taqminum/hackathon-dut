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
    <button type="button" :disabled="loading || !origin.trim() || !destination.trim()" @click="handleSubmit">
    生成偶遇路线
    </button>
    <p v-if="loading">正在寻找可控的意外…</p>
    <p v-else-if="error">{{ error }}</p>

    <div class="demo-scenarios">
      <span class="demo-title">快速体验：</span>
      <button type="button" @click="fillDemo('121.6068,38.9180', '121.5854,38.9325', '+15')">
        大工 -> 星海广场（+15）
      </button>
      <button type="button" @click="fillDemo('121.6281,38.9329', '121.6542,38.9337', 'roam')">
        东港 -> 老虎滩（roam）
      </button>
      <button type="button" @click="fillDemo('121.5899,38.9148', '121.6075,38.9094', '+5')">
        西安路 -> 傅家庄（+5）
      </button>
    </div>
  </section>
</template>

<script setup>
import ExploreModeSelector from '../components/ExploreModeSelector.vue'
import { inject, ref, computed } from 'vue'
import { recommendRoute, createRecommendApi } from '../api.js'

const props = defineProps({
  modelValue: {
    type: String,
    default: '+5',
  },
})

const emit = defineEmits(['update:modelValue', 'select'])

const mode = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value),
})

const origin = ref('')
const destination = ref('')
const loading = ref(false)
const error = ref('')

const api = inject(
  '__recommendApi',
  import.meta.env.DEV
    ? createRecommendApi(globalThis.__recommendApi || globalThis.fetch)
    : { recommendRoute },
)

async function handleSubmit() {
  error.value = ''
  try {
    await Promise.resolve()
    loading.value = true

    const result = await api.recommendRoute({
      origin: origin.value,
      destination: destination.value,
      mode: mode.value,
    })

    if (!result?.route) {
      error.value = '未找到推荐路线，请调整起终点后重试'
      return
    }

    emit('select', result)
  } catch (err) {
    error.value = '获取路线失败，请稍后重试'
  } finally {
    loading.value = false
  }
}

function fillDemo(newOrigin, newDestination, newMode) {
  origin.value = newOrigin
  destination.value = newDestination
  mode.value = newMode
  handleSubmit()
}
</script>

<style scoped>
.demo-scenarios {
  display: grid;
  gap: 8px;
  margin-top: 12px;
}
.demo-title {
  color: #374151;
}
.demo-scenarios button {
  justify-self: start;
}
</style>

