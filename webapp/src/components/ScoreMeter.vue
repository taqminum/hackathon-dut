<script setup>
import { computed } from 'vue'
import { formatScore, scoreToPercent } from '../utils/format.js'

/**
 * 探索评分条：分段方格填充，避免使用渐变或圆角，保持构成主义质感。
 */
const props = defineProps({
  score: { type: [Number, String], default: null },
  max: { type: Number, default: 10 },
  segments: { type: Number, default: 10 },
})

const percent = computed(() => scoreToPercent(props.score, props.max))
const filled = computed(() => Math.round((percent.value / 100) * props.segments))
const display = computed(() => formatScore(props.score))
</script>

<template>
  <div class="meter">
    <div class="meter__head">
      <span class="bh-label">探索评分</span>
      <span class="bh-numeral meter__value">{{ display }}<span class="meter__max">/{{ max }}</span></span>
    </div>
    <div
      class="meter__track"
      role="meter"
      :aria-valuenow="percent"
      aria-valuemin="0"
      aria-valuemax="100"
      :aria-label="`探索评分 ${display}，满分 ${max}`"
    >
      <span
        v-for="index in segments"
        :key="index"
        :class="['meter__cell', { 'meter__cell--on': index <= filled }]"
      />
    </div>
  </div>
</template>

<style scoped>
.meter {
  display: grid;
  gap: var(--bh-2);
}

.meter__head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--bh-3);
}

.meter__value {
  font-size: var(--bh-text-lg);
}

.meter__max {
  font-size: var(--bh-text-xs);
  opacity: 0.6;
}

.meter__track {
  display: flex;
  gap: 3px;
  border: var(--bh-line) solid var(--bh-ink);
  padding: 3px;
  background: var(--bh-white);
}

.meter__cell {
  flex: 1 1 0;
  height: 18px;
  background: var(--bh-paper-2);
}

.meter__cell--on {
  background: var(--bh-blue);
}

.meter__cell--on:nth-child(3n + 2) {
  background: var(--bh-red);
}

.meter__cell--on:nth-child(3n) {
  background: var(--bh-yellow);
}
</style>
