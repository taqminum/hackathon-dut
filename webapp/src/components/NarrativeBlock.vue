<script setup>
import { computed } from 'vue'

/**
 * 探索叙事。后端 narrative 为纯文本（LLM 或本地兜底文案）。
 * 空文案时给出中性说明，不留空白区域。
 */
const props = defineProps({
  narrative: { type: String, default: '' },
  modeLabel: { type: String, default: '' },
})

const text = computed(() => {
  const raw = String(props.narrative || '').trim()
  return raw || '这条路线暂时没有额外说明，先按推荐路线走走看。'
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
    <p class="narrative__text">{{ text }}</p>
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

.narrative__text {
  font-size: var(--bh-text-lg);
  line-height: 1.6;
  font-weight: 500;
  overflow-wrap: anywhere;
}
</style>
