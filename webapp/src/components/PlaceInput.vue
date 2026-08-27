<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { DALIAN_LANDMARKS } from '../constants.js'
import { isCoordString } from '../utils/geo.js'

/**
 * 地点输入框。
 * 后端 /api/place/suggest 未定稿：有响应就用远端联想，无响应退化为本地常用地点过滤。
 * 值本身透传给后端（坐标串或地名皆可），不做强校验，避免挡住演示。
 */
const props = defineProps({
  modelValue: { type: String, default: '' },
  label: { type: String, required: true },
  placeholder: { type: String, default: '' },
  badge: { type: String, default: '' },
  badgeColor: {
    type: String,
    default: 'ink',
    validator: (value) => ['ink', 'red', 'blue', 'yellow'].includes(value),
  },
  disabled: { type: Boolean, default: false },
  invalid: { type: Boolean, default: false },
  suggestFn: { type: Function, default: null },
})

const emit = defineEmits(['update:modelValue', 'pick'])

const inputId = `place-${Math.random().toString(36).slice(2, 8)}`
const open = ref(false)
const activeIndex = ref(-1)
const remote = ref([])
const loading = ref(false)
let debounceTimer = null
let requestSeq = 0

const value = computed({
  get: () => props.modelValue,
  set: (next) => emit('update:modelValue', next),
})

const isCoord = computed(() => isCoordString(props.modelValue))

/** 本地兜底：按关键词过滤常用地点，空关键词时给全部 */
const localMatches = computed(() => {
  const keyword = props.modelValue.trim()
  if (!keyword) return DALIAN_LANDMARKS
  if (isCoord.value) return []
  return DALIAN_LANDMARKS.filter((item) => item.name.includes(keyword))
})

const options = computed(() => (remote.value.length ? remote.value : localMatches.value))

watch(
  () => props.modelValue,
  (next) => {
    activeIndex.value = -1
    if (!props.suggestFn || isCoordString(next) || !next.trim()) {
      remote.value = []
      return
    }
    scheduleSuggest(next.trim())
  },
)

function scheduleSuggest(keyword) {
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(async () => {
    const seq = ++requestSeq
    loading.value = true
    try {
      const result = await props.suggestFn({ keyword })
      // 丢弃过期响应，避免快速输入时结果错位
      if (seq !== requestSeq) return
      remote.value = Array.isArray(result) ? result.slice(0, 6) : []
    } catch {
      if (seq === requestSeq) remote.value = []
    } finally {
      if (seq === requestSeq) loading.value = false
    }
  }, 260)
}

function choose(option) {
  // 有坐标优先回填坐标，后端对坐标串支持最好
  const next = option.location || option.name
  emit('update:modelValue', next)
  emit('pick', option)
  open.value = false
  activeIndex.value = -1
}

function onKeydown(event) {
  if (!options.value.length) return

  if (event.key === 'ArrowDown') {
    event.preventDefault()
    open.value = true
    activeIndex.value = (activeIndex.value + 1) % options.value.length
  } else if (event.key === 'ArrowUp') {
    event.preventDefault()
    open.value = true
    activeIndex.value =
      activeIndex.value <= 0 ? options.value.length - 1 : activeIndex.value - 1
  } else if (event.key === 'Enter' && open.value && activeIndex.value >= 0) {
    event.preventDefault()
    choose(options.value[activeIndex.value])
  } else if (event.key === 'Escape') {
    open.value = false
    activeIndex.value = -1
  }
}

function onBlur() {
  // 延后关闭，保证点击选项的 mousedown 能先落地
  nextTick(() => {
    setTimeout(() => {
      open.value = false
      activeIndex.value = -1
    }, 120)
  })
}

function clear() {
  emit('update:modelValue', '')
  remote.value = []
  open.value = false
}

onBeforeUnmount(() => {
  if (debounceTimer) clearTimeout(debounceTimer)
})
</script>

<template>
  <div class="place bh-field">
    <label class="place__label" :for="inputId">
      <span v-if="badge" :class="['place__badge', `place__badge--${badgeColor}`]" aria-hidden="true">
        {{ badge }}
      </span>
      <span class="bh-label">{{ label }}</span>
    </label>

    <div class="place__control">
      <input
        :id="inputId"
        v-model="value"
        class="bh-input place__input"
        type="text"
        autocomplete="off"
        role="combobox"
        aria-autocomplete="list"
        :aria-expanded="open ? 'true' : 'false'"
        :aria-invalid="invalid ? 'true' : 'false'"
        :placeholder="placeholder"
        :disabled="disabled"
        @focus="open = true"
        @blur="onBlur"
        @keydown="onKeydown"
      />
      <button
        v-if="value && !disabled"
        type="button"
        class="place__clear"
        aria-label="清空输入"
        @click="clear"
      >
        ×
      </button>

      <ul v-if="open && options.length" class="place__list" role="listbox">
        <li
          v-for="(option, index) in options"
          :key="`${option.name}-${option.location || index}`"
          class="place__option"
          :class="{ 'place__option--active': index === activeIndex }"
          role="option"
          :aria-selected="index === activeIndex ? 'true' : 'false'"
          @mousedown.prevent="choose(option)"
          @mouseenter="activeIndex = index"
        >
          <span class="place__option-name">{{ option.name }}</span>
          <span v-if="option.address" class="place__option-address">{{ option.address }}</span>
          <span v-else-if="option.location" class="bh-mono place__option-address">
            {{ option.location }}
          </span>
        </li>
      </ul>
    </div>

    <p class="place__foot">
      <span v-if="loading" class="bh-label">联想中…</span>
      <span v-else-if="isCoord" class="bh-mono place__coord">坐标 {{ modelValue }}</span>
      <span v-else class="place__tip">支持地名或 经度,纬度</span>
    </p>
  </div>
</template>

<style scoped>
.place__label {
  display: flex;
  align-items: center;
  gap: var(--bh-2);
}

.place__badge {
  display: grid;
  place-items: center;
  width: 24px;
  height: 24px;
  border: var(--bh-line) solid var(--bh-ink);
  font-family: var(--bh-font-mono);
  font-size: var(--bh-text-xs);
  font-weight: 700;
  background: var(--bh-white);
}

.place__badge--red {
  background: var(--bh-red);
  color: var(--bh-white);
}
.place__badge--blue {
  background: var(--bh-blue);
  color: var(--bh-white);
}
.place__badge--yellow {
  background: var(--bh-yellow);
  color: var(--bh-ink);
}
.place__badge--ink {
  background: var(--bh-ink);
  color: var(--bh-paper);
}

.place__control {
  position: relative;
}

.place__input {
  padding-right: var(--bh-7);
}

.place__clear {
  position: absolute;
  top: 50%;
  right: var(--bh-2);
  transform: translateY(-50%);
  width: 30px;
  height: 30px;
  display: grid;
  place-items: center;
  border: var(--bh-line) solid var(--bh-ink);
  background: var(--bh-paper-2);
  font-size: var(--bh-text-md);
  line-height: 1;
}

.place__clear:hover {
  background: var(--bh-yellow);
}

.place__list {
  position: absolute;
  z-index: var(--bh-z-dropdown);
  top: calc(100% + 4px);
  left: 0;
  right: 0;
  margin: 0;
  padding: 0;
  list-style: none;
  max-height: 232px;
  overflow-y: auto;
  background: var(--bh-white);
  border: var(--bh-line) solid var(--bh-ink);
  box-shadow: var(--bh-shadow-sm);
}

.place__option {
  display: grid;
  gap: 2px;
  padding: var(--bh-2) var(--bh-3);
  border-bottom: 1px solid var(--bh-paper-2);
  cursor: pointer;
}

.place__option:last-child {
  border-bottom: none;
}

.place__option--active {
  background: var(--bh-yellow);
}

.place__option-name {
  font-size: var(--bh-text-sm);
  font-weight: 700;
}

.place__option-address {
  font-size: var(--bh-text-xs);
  color: var(--bh-ink-soft);
}

.place__foot {
  min-height: 1.2em;
  font-size: var(--bh-text-xs);
  color: var(--bh-ink-soft);
}

.place__coord {
  letter-spacing: 0.02em;
}
</style>
