<script setup>
/**
 * 通用状态块：加载 / 空结果 / 错误 三态复用同一构成。
 * 加载态用骨架条，其余用几何图形 + 文案 + 可选操作。
 */
defineProps({
  variant: {
    type: String,
    default: 'empty',
    validator: (value) => ['loading', 'empty', 'error'].includes(value),
  },
  title: { type: String, default: '' },
  message: { type: String, default: '' },
  actionLabel: { type: String, default: '' },
})

const emit = defineEmits(['action'])
</script>

<template>
  <div
    :class="['state', `state--${variant}`]"
    :role="variant === 'error' ? 'alert' : 'status'"
    :aria-busy="variant === 'loading' ? 'true' : 'false'"
  >
    <template v-if="variant === 'loading'">
      <div class="state__bars">
        <span class="bh-skeleton state__bar state__bar--a" />
        <span class="bh-skeleton state__bar state__bar--b" />
        <span class="bh-skeleton state__bar state__bar--c" />
      </div>
      <p class="state__title">{{ title || '正在寻找可控的意外…' }}</p>
      <p v-if="message" class="state__message">{{ message }}</p>
    </template>

    <template v-else>
      <div class="state__glyph" aria-hidden="true">
        <span v-if="variant === 'error'" class="glyph glyph--cross" />
        <span v-else class="glyph glyph--circle" />
      </div>
      <p class="state__title">{{ title || (variant === 'error' ? '出了点问题' : '还没有结果') }}</p>
      <p v-if="message" class="state__message">{{ message }}</p>
      <button
        v-if="actionLabel"
        type="button"
        class="bh-btn"
        :class="variant === 'error' ? 'bh-btn--danger' : 'bh-btn--primary'"
        @click="emit('action')"
      >
        {{ actionLabel }}
      </button>
    </template>
  </div>
</template>

<style scoped>
.state {
  display: grid;
  justify-items: start;
  gap: var(--bh-3);
  padding: var(--bh-5);
  border: var(--bh-line) solid var(--bh-ink);
  background: var(--bh-white);
}

.state--error {
  border-color: var(--bh-red);
  box-shadow: var(--bh-shadow-red);
}

.state__title {
  font-size: var(--bh-text-lg);
  font-weight: 800;
  text-transform: uppercase;
  letter-spacing: var(--bh-track-title);
}

.state__message {
  font-size: var(--bh-text-sm);
  color: var(--bh-ink-soft);
  max-width: 46ch;
}

.state__bars {
  display: grid;
  gap: var(--bh-2);
  width: 100%;
}

.state__bar {
  height: 18px;
}

.state__bar--a {
  width: 100%;
}
.state__bar--b {
  width: 72%;
}
.state__bar--c {
  width: 44%;
}

.state__glyph {
  display: flex;
}

.glyph {
  display: block;
  width: 34px;
  height: 34px;
}

.glyph--circle {
  border-radius: 50%;
  background: var(--bh-yellow);
  border: var(--bh-line) solid var(--bh-ink);
}

.glyph--cross {
  position: relative;
  background: var(--bh-red);
  border: var(--bh-line) solid var(--bh-ink);
}

.glyph--cross::before,
.glyph--cross::after {
  content: '';
  position: absolute;
  top: 50%;
  left: 15%;
  width: 70%;
  height: 3px;
  background: var(--bh-white);
}

.glyph--cross::before {
  transform: translateY(-50%) rotate(45deg);
}

.glyph--cross::after {
  transform: translateY(-50%) rotate(-45deg);
}
</style>
