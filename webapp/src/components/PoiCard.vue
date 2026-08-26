<script setup>
import { computed } from 'vue'
import { colorForIndex, formatDistance, ordinal, toNumber } from '../utils/format.js'

/**
 * 沿途亮点卡片。后端 POI 字段可能缺失（name / type / distance / rating / location），
 * 这里逐字段兜底，缺就不显示对应行，不显示 undefined。
 */
const props = defineProps({
  poi: { type: Object, required: true },
  index: { type: Number, default: 0 },
  active: { type: Boolean, default: false },
})

const emit = defineEmits(['focus-poi'])

const color = computed(() => colorForIndex(props.index))
const name = computed(() => props.poi?.name || '未命名地点')
const type = computed(() => {
  const raw = String(props.poi?.type || '').trim()
  if (!raw) return ''
  // 高德类型形如 "餐饮服务;咖啡厅;咖啡厅"，取最后一段更具体
  const parts = raw.split(/[;|]/).filter(Boolean)
  return parts.length ? parts[parts.length - 1] : raw
})
const distance = computed(() => {
  const num = toNumber(props.poi?.distance)
  return num === null ? '' : formatDistance(num)
})
const rating = computed(() => {
  const num = toNumber(props.poi?.rating)
  if (num === null || num <= 0) return null
  return num.toFixed(1)
})
const stars = computed(() => {
  const num = toNumber(props.poi?.rating)
  if (num === null) return 0
  return Math.max(0, Math.min(5, Math.round(num)))
})
const location = computed(() => props.poi?.location || '')
</script>

<template>
  <article
    :class="['poi', `poi--${color}`, { 'poi--active': active }]"
    tabindex="0"
    role="button"
    :aria-pressed="active ? 'true' : 'false'"
    @click="emit('focus-poi', index)"
    @keydown.enter.prevent="emit('focus-poi', index)"
    @keydown.space.prevent="emit('focus-poi', index)"
  >
    <span class="bh-numeral poi__index" aria-hidden="true">{{ ordinal(index) }}</span>

    <div class="poi__body">
      <h4 class="poi__name">{{ name }}</h4>
      <div class="poi__meta">
        <span v-if="type" class="poi__tag">{{ type }}</span>
        <span v-if="distance" class="bh-mono poi__distance">距路线约 {{ distance }}</span>
      </div>

      <div v-if="rating" class="poi__rating">
        <span class="poi__stars" aria-hidden="true">
          <i
            v-for="n in 5"
            :key="n"
            :class="['poi__star', { 'poi__star--on': n <= stars }]"
          />
        </span>
        <span class="bh-mono poi__score">{{ rating }}</span>
        <span class="bh-sr">评分 {{ rating }} 分，满分 5 分</span>
      </div>

      <p v-if="location" class="bh-mono poi__coord">{{ location }}</p>
    </div>
  </article>
</template>

<style scoped>
.poi {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: var(--bh-4);
  align-items: start;
  padding: var(--bh-4);
  border: var(--bh-line) solid var(--bh-ink);
  background: var(--bh-white);
  cursor: pointer;
  transition: transform var(--bh-transition), box-shadow var(--bh-transition);
}

.poi:hover,
.poi--active {
  transform: translate(-3px, -3px);
  box-shadow: var(--bh-shadow-sm);
}

.poi__index {
  display: grid;
  place-items: center;
  width: 46px;
  height: 46px;
  font-size: var(--bh-text-lg);
  border: var(--bh-line) solid var(--bh-ink);
}

.poi--red .poi__index {
  background: var(--bh-red);
  color: var(--bh-white);
}
.poi--blue .poi__index {
  background: var(--bh-blue);
  color: var(--bh-white);
}
.poi--yellow .poi__index {
  background: var(--bh-yellow);
  color: var(--bh-ink);
}

.poi--active {
  border-width: var(--bh-line);
  outline: 3px solid var(--bh-ink);
  outline-offset: -6px;
}

.poi__body {
  display: grid;
  gap: var(--bh-2);
  min-width: 0;
}

.poi__name {
  font-size: var(--bh-text-lg);
  overflow-wrap: anywhere;
}

.poi__meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--bh-2) var(--bh-3);
}

.poi__tag {
  padding: 2px var(--bh-2);
  border: 2px solid var(--bh-ink);
  background: var(--bh-paper-2);
  font-size: var(--bh-text-xs);
  font-weight: 700;
  letter-spacing: var(--bh-track-label);
  text-transform: uppercase;
}

.poi__distance,
.poi__coord {
  font-size: var(--bh-text-xs);
  color: var(--bh-ink-soft);
}

.poi__rating {
  display: flex;
  align-items: center;
  gap: var(--bh-2);
}

.poi__stars {
  display: inline-flex;
  gap: 3px;
}

.poi__star {
  width: 11px;
  height: 11px;
  border: 2px solid var(--bh-ink);
  background: var(--bh-white);
}

.poi__star--on {
  background: var(--bh-yellow);
}

.poi__score {
  font-size: var(--bh-text-sm);
  font-weight: 700;
}
</style>
