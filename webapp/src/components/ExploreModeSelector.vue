<script setup>
import { EXPLORE_MODES, DEFAULT_MODE } from '../constants.js'

/**
 * 探索模式切换。三个模式对应三原色，选中态用实心块 + 位移投影。
 * 对外契约保持 v-model:modelValue，取值 '+5' | '+15' | 'roam'。
 */
const props = defineProps({
  modelValue: {
    type: String,
    default: DEFAULT_MODE,
  },
  disabled: {
    type: Boolean,
    default: false,
  },
})

const emit = defineEmits(['update:modelValue'])

const modes = EXPLORE_MODES

function select(value) {
  if (props.disabled || value === props.modelValue) return
  emit('update:modelValue', value)
}
</script>

<template>
  <div class="mode">
    <span id="mode-legend" class="bh-label mode__legend">探索程度</span>
    <div class="mode-selector" role="radiogroup" aria-labelledby="mode-legend">
      <button
        v-for="item in modes"
        :key="item.value"
        type="button"
        role="radio"
        :aria-checked="modelValue === item.value ? 'true' : 'false'"
        :disabled="disabled"
        :class="[
          'mode-button',
          `mode-button--${item.color}`,
          { active: modelValue === item.value },
        ]"
        @click="select(item.value)"
      >
        <span class="bh-numeral mode-button__label">{{ item.label }}</span>
        <span class="mode-button__title">{{ item.title }}</span>
        <span class="mode-button__caption">{{ item.caption }}</span>
      </button>
    </div>
    <p class="mode__hint">
      {{ modes.find((item) => item.value === modelValue)?.description }}
    </p>
  </div>
</template>

<style scoped>
.mode {
  display: grid;
  gap: var(--bh-2);
}

.mode-selector {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: var(--bh-3);
}

.mode-button {
  display: grid;
  gap: var(--bh-1);
  justify-items: start;
  text-align: left;
  padding: var(--bh-3) var(--bh-4);
  border: var(--bh-line) solid var(--bh-ink);
  border-radius: 0;
  background: var(--bh-white);
  color: var(--bh-ink);
  transition: transform var(--bh-transition), box-shadow var(--bh-transition),
    background-color var(--bh-transition), color var(--bh-transition);
}

.mode-button:hover:not(:disabled):not(.active) {
  transform: translate(-2px, -2px);
  box-shadow: var(--bh-shadow-sm);
}

.mode-button:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.mode-button__label {
  font-size: var(--bh-text-xl);
}

.mode-button__title {
  font-size: var(--bh-text-sm);
  font-weight: 700;
  letter-spacing: var(--bh-track-label);
  text-transform: uppercase;
}

.mode-button__caption {
  font-size: var(--bh-text-xs);
  color: var(--bh-ink-soft);
}

.mode-button.active {
  box-shadow: var(--bh-shadow-sm);
  transform: translate(-2px, -2px);
}

.mode-button--blue.active {
  background: var(--bh-blue);
  color: var(--bh-white);
}

.mode-button--red.active {
  background: var(--bh-red);
  color: var(--bh-white);
}

.mode-button--yellow.active {
  background: var(--bh-yellow);
  color: var(--bh-ink);
}

.mode-button.active .mode-button__caption {
  color: inherit;
  opacity: 0.85;
}

.mode__hint {
  font-size: var(--bh-text-sm);
  color: var(--bh-ink-soft);
  min-height: 1.5em;
}

@media (max-width: 720px) {
  .mode-selector {
    grid-template-columns: 1fr;
  }

  .mode-button {
    grid-template-columns: auto 1fr;
    grid-template-areas: 'label title' 'label caption';
    column-gap: var(--bh-3);
    align-items: center;
  }

  .mode-button__label {
    grid-area: label;
  }
  .mode-button__title {
    grid-area: title;
  }
  .mode-button__caption {
    grid-area: caption;
  }
}
</style>
