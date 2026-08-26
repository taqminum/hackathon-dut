<script setup>
/**
 * 数据方块：大号数字 + 单位 + 全大写标签。
 * 结果页顶部的三个关键指标（预计时长 / 额外时间 / 探索评分）用它。
 */
defineProps({
  label: { type: String, required: true },
  value: { type: [String, Number], default: '--' },
  unit: { type: String, default: '' },
  color: {
    type: String,
    default: 'ink',
    validator: (value) => ['ink', 'red', 'blue', 'yellow', 'paper'].includes(value),
  },
  hint: { type: String, default: '' },
})
</script>

<template>
  <div :class="['tile', `tile--${color}`]">
    <span class="bh-label tile__label">{{ label }}</span>
    <span class="tile__value">
      <span class="bh-numeral tile__number">{{ value }}</span>
      <span v-if="unit" class="tile__unit">{{ unit }}</span>
    </span>
    <span v-if="hint" class="tile__hint">{{ hint }}</span>
  </div>
</template>

<style scoped>
.tile {
  display: grid;
  gap: var(--bh-2);
  align-content: start;
  padding: var(--bh-4);
  border: var(--bh-line) solid var(--bh-ink);
  background: var(--bh-white);
  min-height: 118px;
}

.tile--red {
  background: var(--bh-red);
  color: var(--bh-white);
}

.tile--blue {
  background: var(--bh-blue);
  color: var(--bh-white);
}

.tile--yellow {
  background: var(--bh-yellow);
  color: var(--bh-ink);
}

.tile--ink {
  background: var(--bh-ink);
  color: var(--bh-paper);
}

.tile--paper {
  background: var(--bh-paper-2);
  color: var(--bh-ink);
}

/* 不用 opacity 做层次：11px 小字降透明度后，
   白字在红底上只有 3.77:1，低于 WCAG AA 的 4.5:1。
   层次改由字号与字重表达。 */
.tile__label {
  opacity: 1;
}

.tile__value {
  display: flex;
  align-items: baseline;
  gap: var(--bh-2);
}

.tile__number {
  font-size: var(--bh-text-2xl);
}

.tile__unit {
  font-size: var(--bh-text-sm);
  font-weight: 700;
  letter-spacing: var(--bh-track-label);
  text-transform: uppercase;
}

.tile__hint {
  font-size: var(--bh-text-xs);
  opacity: 1;
  line-height: 1.35;
}
</style>
