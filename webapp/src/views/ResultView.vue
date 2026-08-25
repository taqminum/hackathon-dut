<script setup>
import { computed } from 'vue'
import MapView from '../components/MapView.vue'

const props = defineProps({
  result: Object,
})

const emit = defineEmits(['back'])

const baselineMinutes = computed(() => props.result?.baseline_minutes ?? '-')
const detourMinutes = computed(() => props.result?.detour_minutes ?? '-')
const score = computed(() => props.result?.score ?? '-')
const narrative = computed(() => props.result?.narrative ?? '')
const pois = computed(() => props.result?.pois ?? [])
const route = computed(() => props.result?.route ?? null)
</script>

<template>
  <section class="result">
    <button type="button" class="back-button" @click="emit('back')">返回首页</button>
    <div class="summary">
      <div class="pill">预计 {{ baselineMinutes }} 分钟</div>
      <div class="pill">额外 +{{ detourMinutes }} 分钟</div>
      <div class="pill">探索评分 {{ score }}</div>
    </div>
    <p class="narrative">{{ narrative }}</p>
    <MapView :route="route" :pois="pois" />
    <div v-if="pois.length" class="pois">
      <h3>沿途亮点</h3>
      <ul>
        <li v-for="poi in pois" :key="poi.name">
          <strong>{{ poi.name }}</strong> - {{ poi.type }}（距离约 {{ poi.distance }} 米）
        </li>
      </ul>
    </div>
  </section>
</template>

<style scoped>
.result {
  display: grid;
  gap: 16px;
}
.summary {
  display: flex;
  gap: 10px;
  flex-wrap: wrap;
}
.pill {
  border: 1px solid #e5e7eb;
  background: #fff;
  padding: 8px 12px;
  border-radius: 999px;
}
.back-button {
  justify-self: start;
  border: none;
  background: #111827;
  color: #fff;
  padding: 10px 14px;
  border-radius: 10px;
}
.narrative {
  line-height: 1.6;
}
.pois ul {
  padding-left: 18px;
  display: grid;
  gap: 8px;
}
</style>
