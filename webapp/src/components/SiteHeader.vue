<script setup>
import BauhausMark from './BauhausMark.vue'

/**
 * 顶部标题栏。右侧显示后端连通状态（来自 /health），断连时为红色。
 */
defineProps({
  online: { type: Boolean, default: null },
  showBack: { type: Boolean, default: false },
})

const emit = defineEmits(['back'])
</script>

<template>
  <header class="head">
    <div class="bh-shell head__inner">
      <div class="head__brand">
        <BauhausMark :size="42" :decorative="false" />
        <div class="head__titles">
          <span class="head__title">偶遇导航</span>
          <span class="bh-label head__sub">Serendipity Navigation</span>
        </div>
      </div>

      <div class="head__right">
        <button
          v-if="showBack"
          type="button"
          class="bh-btn bh-btn--ghost head__back"
          @click="emit('back')"
        >
          返回首页
        </button>
        <span
          v-if="online !== null"
          :class="['head__status', online ? 'head__status--on' : 'head__status--off']"
        >
          <i class="head__dot" aria-hidden="true" />
          {{ online ? '后端已连接' : '后端未连接' }}
        </span>
      </div>
    </div>
    <div class="head__stripe" aria-hidden="true">
      <span class="head__stripe-seg head__stripe-seg--red" />
      <span class="head__stripe-seg head__stripe-seg--yellow" />
      <span class="head__stripe-seg head__stripe-seg--blue" />
      <span class="head__stripe-seg head__stripe-seg--ink" />
    </div>
  </header>
</template>

<style scoped>
.head {
  position: sticky;
  top: 0;
  z-index: var(--bh-z-overlay);
  background: var(--bh-paper);
  border-bottom: var(--bh-line) solid var(--bh-ink);
}

.head__inner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--bh-4);
  padding-top: var(--bh-3);
  padding-bottom: var(--bh-3);
}

.head__brand {
  display: flex;
  align-items: center;
  gap: var(--bh-3);
  min-width: 0;
}

.head__titles {
  display: grid;
}

.head__title {
  font-size: var(--bh-text-lg);
  font-weight: 800;
  letter-spacing: var(--bh-track-title);
  text-transform: uppercase;
  line-height: 1.1;
}

.head__sub {
  color: var(--bh-ink-soft);
  font-size: 10px;
}

.head__right {
  display: flex;
  align-items: center;
  gap: var(--bh-3);
}

.head__status {
  display: inline-flex;
  align-items: center;
  gap: var(--bh-2);
  padding: var(--bh-1) var(--bh-2);
  border: 2px solid var(--bh-ink);
  font-size: var(--bh-text-xs);
  font-weight: 700;
  letter-spacing: var(--bh-track-label);
  text-transform: uppercase;
  white-space: nowrap;
}

.head__dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  background: currentColor;
}

.head__status--on {
  background: var(--bh-blue);
  color: var(--bh-white);
}

.head__status--off {
  background: var(--bh-red);
  color: var(--bh-white);
}

.head__stripe {
  display: flex;
  height: var(--bh-line-thick);
}

.head__stripe-seg {
  flex: 1 1 0;
}

.head__stripe-seg--red {
  background: var(--bh-red);
  flex-grow: 4;
}
.head__stripe-seg--yellow {
  background: var(--bh-yellow);
  flex-grow: 2;
}
.head__stripe-seg--blue {
  background: var(--bh-blue);
  flex-grow: 3;
}
.head__stripe-seg--ink {
  background: var(--bh-ink);
  flex-grow: 1;
}

@media (max-width: 720px) {
  .head__sub {
    display: none;
  }

  .head__status {
    font-size: 10px;
  }
}
</style>
