<script setup>
const props = defineProps({
  modelValue: {
    type: String,
    default: '+5',
  },
})

const emit = defineEmits(['update:modelValue'])

const modes = [
  { value: '+5', label: '+5' },
  { value: '+15', label: '+15' },
  { value: 'roam', label: '漫游' },
]
</script>

<template>
  <div class="mode-selector">
    <button
      v-for="item in modes"
      :key="item.value"
      :class="['mode-button', { active: modelValue === item.value }]"
      type="button"
      @click="emit('update:modelValue', item.value)"
    >
      {{ item.label }}
    </button>
  </div>
</template>

<style scoped>
.mode-selector {
  display: inline-flex;
  gap: 8px;
}
.mode-button {
  border: 1px solid #d1d5db;
  background: #fff;
  color: #111827;
  padding: 8px 12px;
  border-radius: 999px;
}
.mode-button.active {
  background: #111827;
  color: #fff;
  border-color: #111827;
}
</style>
