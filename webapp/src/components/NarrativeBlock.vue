<script setup>
import { computed } from 'vue'

/**
 * 推荐理由。
 *
 * T4：这个框原来只有一句叙事文案，回答不了「为什么是这条而不是别的」。
 * 现在结构化的理由（reasons，由 ResultView 从后端字段拼出）在上面，
 * 叙事文案退到下面收尾 —— 叙事是 LLM/兜底模板写的散文，作为氛围可以，
 * 但不能当成依据。
 *
 * degraded 为真时（没有亮点、评分为 0 的降级出口）只说实话，
 * 不列理由 —— 那时候本来就没有「为什么绕这一趟」可讲。
 */
const props = defineProps({
  narrative: { type: String, default: '' },
  modeLabel: { type: String, default: '' },
  reasons: { type: Array, default: () => [] },
  degradedNote: { type: String, default: '' },
})

const items = computed(() => props.reasons.map((item) => String(item || '').trim()).filter(Boolean))
const degraded = computed(() => !items.value.length)
const note = computed(
  () => String(props.degradedNote || '').trim() || '这次没有找到值得绕行的亮点，给出的是最快路线。',
)

const text = computed(() => {
  const raw = String(props.narrative || '').trim()
  // 有理由列表时叙事只是收尾，空着就不占位；降级时反而需要一句话把空白填上
  if (raw) return raw
  return degraded.value ? '' : '这条路线暂时没有额外说明，先按推荐路线走走看。'
})
</script>

<template>
  <section class="narrative bh-card">
    <div class="narrative__head">
      <span class="bh-label">为什么推荐这条</span>
      <span v-if="modeLabel" class="narrative__mode bh-mono">{{ modeLabel }}</span>
    </div>
    <div class="narrative__rule" aria-hidden="true">
      <span class="narrative__rule-seg narrative__rule-seg--red" />
      <span class="narrative__rule-seg narrative__rule-seg--yellow" />
      <span class="narrative__rule-seg narrative__rule-seg--blue" />
    </div>

    <ul v-if="!degraded" class="narrative__reasons">
      <li v-for="(item, index) in items" :key="index" class="narrative__reason">
        <span class="narrative__bullet" aria-hidden="true" />
        <span class="narrative__reason-text">{{ item }}</span>
      </li>
    </ul>
    <p v-else class="narrative__degraded">{{ note }}</p>

    <p v-if="text" class="narrative__text">{{ text }}</p>
  </section>
</template>

<style scoped>
.narrative {
  display: grid;
  gap: var(--bh-3);
}

.narrative__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--bh-3);
}

.narrative__mode {
  padding: 2px var(--bh-2);
  border: 2px solid var(--bh-ink);
  background: var(--bh-yellow);
  font-size: var(--bh-text-xs);
  font-weight: 700;
}

.narrative__rule {
  display: flex;
  height: var(--bh-line-thick);
}

.narrative__rule-seg {
  flex: 1 1 0;
}

.narrative__rule-seg--red {
  background: var(--bh-red);
  flex-grow: 3;
}
.narrative__rule-seg--yellow {
  background: var(--bh-yellow);
  flex-grow: 1;
}
.narrative__rule-seg--blue {
  background: var(--bh-blue);
  flex-grow: 2;
}

.narrative__reasons {
  display: grid;
  gap: var(--bh-2);
  margin: 0;
  padding: 0;
  list-style: none;
}

.narrative__reason {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: var(--bh-3);
  align-items: start;
}

/* 方块项目符号，和卡片的直角语言一致；圆点在这套里显得软 */
.narrative__bullet {
  width: 10px;
  height: 10px;
  margin-top: 7px;
  border: 2px solid var(--bh-ink);
  background: var(--bh-blue);
}

.narrative__reason-text {
  font-size: var(--bh-text-md);
  line-height: 1.55;
  font-weight: 600;
  overflow-wrap: anywhere;
}

.narrative__degraded {
  padding: var(--bh-3);
  border-left: var(--bh-line-thick) solid var(--bh-yellow);
  background: var(--bh-paper-2);
  font-size: var(--bh-text-md);
  line-height: 1.55;
  font-weight: 600;
  overflow-wrap: anywhere;
}

/* 叙事退居次要：比理由小一号、颜色轻一点，用一条上边线隔开 */
.narrative__text {
  padding-top: var(--bh-3);
  border-top: 2px solid var(--bh-ink);
  font-size: var(--bh-text-sm);
  line-height: 1.6;
  font-weight: 500;
  color: var(--bh-ink-soft);
  overflow-wrap: anywhere;
}
</style>
