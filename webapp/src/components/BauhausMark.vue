<script setup>
/**
 * 品牌标记：圆 / 方 / 三角的包豪斯构成，纯 SVG，无外部资源。
 * size 控制边长，decorative 为 true 时对屏幕阅读器隐藏。
 */
defineProps({
  size: {
    type: Number,
    default: 48,
  },
  decorative: {
    type: Boolean,
    default: true,
  },
})
</script>

<template>
  <svg
    class="mark"
    :width="size"
    :height="size"
    viewBox="0 0 48 48"
    :aria-hidden="decorative ? 'true' : null"
    :role="decorative ? null : 'img'"
    focusable="false"
  >
    <title v-if="!decorative">偶遇导航</title>
    <rect x="1.5" y="1.5" width="45" height="45" fill="none" stroke="var(--bh-ink)" stroke-width="3" />
    <circle cx="17" cy="17" r="11" fill="var(--bh-red)" />
    <rect x="24" y="24" width="17" height="17" fill="var(--bh-blue)" />
    <path d="M7 41 L17 26 L27 41 Z" fill="var(--bh-yellow)" />
  </svg>
</template>

<style scoped>
.mark {
  flex: 0 0 auto;
}
</style>
