<script setup>
import { computed } from 'vue'
import { formatDistance, formatDuration, ordinal, toNumber } from '../utils/format.js'

/**
 * 分段步行指引。后端 route.steps 形如
 *   [{ instruction, road, distance, duration }]
 * 字段可能是字符串，缺失时只显示 instruction。
 */
const props = defineProps({
  steps: { type: Array, default: () => [] },
  collapsedCount: { type: Number, default: 4 },
})

const expanded = defineModel('expanded', { type: Boolean, default: false })

const normalized = computed(() =>
  (props.steps || [])
    .map((step) => ({
      instruction: String(step?.instruction || '').trim() || '继续沿推荐路线前进',
      road: String(step?.road || '').trim(),
      distance: toNumber(step?.distance),
      duration: toNumber(step?.duration),
    }))
    .filter((step) => step.instruction),
)

const visible = computed(() =>
  expanded.value ? normalized.value : normalized.value.slice(0, props.collapsedCount),
)

const hiddenCount = computed(() => Math.max(0, normalized.value.length - visible.value.length))
</script>

<template>
  <section v-if="normalized.length" class="steps bh-card">
    <div class="steps__head">
      <h3 class="steps__title">路线指引</h3>
      <span class="bh-mono steps__count">{{ normalized.length }} 段</span>
    </div>

    <ol class="steps__list">
      <li v-for="(step, index) in visible" :key="index" class="steps__item">
        <span class="bh-numeral steps__index" aria-hidden="true">{{ ordinal(index) }}</span>
        <div class="steps__body">
          <p class="steps__instruction">{{ step.instruction }}</p>
          <p class="steps__meta">
            <span v-if="step.road" class="steps__road">{{ step.road }}</span>
            <span v-if="step.distance !== null" class="bh-mono">{{ formatDistance(step.distance) }}</span>
            <span v-if="step.duration !== null" class="bh-mono">{{ formatDuration(step.duration) }}</span>
          </p>
        </div>
      </li>
    </ol>

    <button
      v-if="hiddenCount || expanded"
      type="button"
      class="bh-btn bh-btn--ghost steps__toggle"
      @click="expanded = !expanded"
    >
      {{ expanded ? '收起指引' : `展开其余 ${hiddenCount} 段` }}
    </button>
  </section>
</template>

<style scoped>
.steps {
  display: grid;
  gap: var(--bh-4);
}

.steps__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--bh-3);
  padding-bottom: var(--bh-2);
  border-bottom: var(--bh-line) solid var(--bh-ink);
}

.steps__title {
  font-size: var(--bh-text-lg);
}

.steps__count {
  font-size: var(--bh-text-xs);
  color: var(--bh-ink-soft);
}

.steps__list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: grid;
  gap: var(--bh-3);
}

.steps__item {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: var(--bh-3);
  align-items: start;
}

.steps__index {
  display: grid;
  place-items: center;
  width: 30px;
  height: 30px;
  font-size: var(--bh-text-sm);
  background: var(--bh-ink);
  color: var(--bh-paper);
}

.steps__body {
  display: grid;
  gap: 2px;
  min-width: 0;
}

.steps__instruction {
  font-size: var(--bh-text-sm);
  overflow-wrap: anywhere;
}

.steps__meta {
  display: flex;
  flex-wrap: wrap;
  gap: var(--bh-3);
  font-size: var(--bh-text-xs);
  color: var(--bh-ink-soft);
}

.steps__road {
  font-weight: 700;
}

.steps__toggle {
  justify-self: start;
}
</style>
