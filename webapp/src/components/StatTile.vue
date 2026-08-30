<script setup>
/**
 * 数据方块：大号数字 + 单位 + 全大写标签。
 * 结果页顶部的三个关键指标（预计时长 / 额外时间 / 探索评分）用它。
 *
 * R5：`baseline` / `delta` 是「换掉了什么」并进来的两截。原来那是块独立的
 * 对比区，和上面四个指标格讲的是同一件事（基准 vs 推荐的距离与时长），
 * 于是同一屏上两处印同样的数字，验收人要在两个区之间来回对。现在小字原值
 * 压在大字现值上面（`原 6.9 公里` / `7.7 公里`），带符号的差值留在小字里。
 * 两个都为空时这个格子和以前完全一样 —— 没有对比就不摆对比。
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
  // 原值，已经带好单位（`6.9 公里` / `92 分钟`），前面的「原」由模板加
  baseline: { type: String, default: '' },
  // 带符号的差值，同样已经带好单位（`+780 米`）
  delta: { type: String, default: '' },
})
</script>

<template>
  <div :class="['tile', `tile--${color}`]">
    <span class="bh-label tile__label">{{ label }}</span>
    <!-- R5：原值在大字上方。删除线表示「这个数字被换掉了」，
         读屏靠 bh-sr 的「原本」把这层意思说出来，不指望删除线被念出来。 -->
    <span v-if="baseline" class="bh-mono tile__baseline">
      <span class="bh-sr">原本</span>
      <span aria-hidden="true">原 </span>
      <s class="tile__baseline-value">{{ baseline }}</s>
    </span>
    <span class="tile__value">
      <span class="bh-numeral tile__number">{{ value }}</span>
      <span v-if="unit" class="tile__unit">{{ unit }}</span>
    </span>
    <span v-if="delta" class="bh-mono tile__delta">{{ delta }}</span>
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

/* R5：原值与差值都用 currentColor。四个格子里有红底、蓝底、墨底白字，
   写死 --bh-red 之类的强调色在这些底上过不了 4.5:1（和 .tile__label
   的注释同一个坑）。层次交给字号，颜色一律继承。 */
.tile__baseline,
.tile__delta {
  font-size: var(--bh-text-xs);
  font-weight: 700;
  line-height: 1.2;
  color: inherit;
}

/* 删除线默认贴着基线太细，text-decoration-thickness 让它在小字上看得见 */
.tile__baseline-value {
  text-decoration-thickness: 2px;
}

/* 差值和大字之间不留 gap 的整格，读起来才是「7.7 公里，比原来多 780 米」
   这一件事，而不是两条并列的数据 */
.tile__delta {
  margin-top: calc(-1 * var(--bh-1));
}
</style>
