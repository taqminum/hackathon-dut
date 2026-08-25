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
</script>

