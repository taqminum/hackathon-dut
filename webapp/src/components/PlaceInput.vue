<script setup>
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { isCoordString } from '../utils/geo.js'

/**
 * 地点输入框。
 * 联想项只展示后端从高德取得的真实地点；服务失败时明确报错，不混入本地假结果。
 * 值本身仍可透传给后端（坐标串或地名皆可），让用户在联想失败时直接提交。
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
const suggestError = ref('')
let debounceTimer = null
let requestSeq = 0

const value = computed({
  get: () => props.modelValue,
  set: (next) => emit('update:modelValue', next),
})

const isCoord = computed(() => isCoordString(props.modelValue))

const options = computed(() => remote.value)

/**
 * R3：一条都联想不出来时说句话，别给一片空白。
 *
 * 高德没有返回匹配项时，下拉不能一片空白。这一行告诉用户仍可直接提交地名。
 *
 * 三种情况不提示：正在联想（loading 有自己的文案）、输入是坐标串
 * （下面 foot 已经显示「坐标 …」）、关键词为空。
 */
const emptyHint = computed(() => {
  if (loading.value || isCoord.value) return ''
  if (!props.modelValue.trim()) return ''
  if (options.value.length) return ''
  return suggestError.value || '高德没有找到匹配地点，可直接输入完整地名或坐标'
})

watch(
  () => props.modelValue,
  (next) => {
    activeIndex.value = -1
    if (!props.suggestFn || isCoordString(next) || !next.trim()) {
      remote.value = []
      suggestError.value = ''
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
    suggestError.value = ''
    try {
      const result = await props.suggestFn({ keyword })
      // 丢弃过期响应，避免快速输入时结果错位
      if (seq !== requestSeq) return
      remote.value = Array.isArray(result) ? result.slice(0, 6) : []
    } catch (error) {
      if (seq === requestSeq) {
        remote.value = []
        suggestError.value = error?.message || '真实地点联想暂不可用'
      }
    } finally {
      if (seq === requestSeq) loading.value = false
    }
  }, 260)
}

function choose(option) {
  // R3：回填**地名**，坐标由 `pick` 带出去交给上层存。
  //
  // 原来这里回填的是 option.location，于是从下拉里选「麦当劳(青泥洼桥店)」之后
  // 输入框里躺着 `121.6335,38.9187` —— 和 R2 修掉的一键体验是同一个毛病，
  // 只是走的另一条路径。上层（HomeView.onOriginPick）拿 option.location
  // 存进 originCoord，提交时优先用它，所以「发坐标」这件事没有退步。
  const next = option.name || option.location
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
        @input="open = true"
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

      <!-- R3：空态提示。role="status" 是因为它不可点选，放进 listbox 里
           当成一个 option 会让读屏念出一个选不了的选项。 -->
      <p v-if="open && (suggestError || emptyHint)" class="place__empty" role="status" aria-live="polite">
        {{ suggestError || emptyHint }}
      </p>

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

/* R3：空态提示。和下拉同一个位置、同一个层级，视觉上占掉那块空白。 */
.place__empty {
  position: absolute;
  z-index: var(--bh-z-dropdown);
  top: calc(100% + 4px);
  left: 0;
  right: 0;
  padding: var(--bh-2) var(--bh-3);
  background: var(--bh-paper-2);
  border: var(--bh-line) solid var(--bh-ink);
  border-left: var(--bh-line-thick) solid var(--bh-yellow);
  font-size: var(--bh-text-xs);
  color: var(--bh-ink);
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
