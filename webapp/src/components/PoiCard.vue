<script setup>
import { computed, ref } from 'vue'
import { colorForIndex, formatDistance, ordinal, poiTypeLabel, toNumber } from '../utils/format.js'

/**
 * 沿途亮点卡片。后端 POI 字段可能缺失（name / type / off_route_meters / rating / location），
 * 这里逐字段兜底，缺就不显示对应行，不显示 undefined。
 *
 * R6：卡片可就地展开一块详情区（地址 / 电话 / 营业时间 / 照片）。这四个字段来自
 * 高德 `extensions=all`，兜底演示数据里没有 —— 那时候详情区一行都不渲染，
 * 也不摆「暂无」占位（堆一屏「暂无」比不展开更糟）。
 */
const props = defineProps({
  poi: { type: Object, required: true },
  index: { type: Number, default: 0 },
  active: { type: Boolean, default: false },
})

const emit = defineEmits(['focus-poi'])

const color = computed(() => colorForIndex(props.index))
const name = computed(() => props.poi?.name || '未命名地点')
const type = computed(() => poiTypeLabel(props.poi?.type))
const offRouteMeters = computed(() => {
  const num = toNumber(props.poi?.off_route_meters)
  return num === null ? '' : formatDistance(num)
})
const rating = computed(() => {
  const num = toNumber(props.poi?.rating)
  if (num === null || num <= 0) return null
  return num.toFixed(1)
})
const stars = computed(() => {
  const num = toNumber(props.poi?.rating)
  if (num === null) return 0
  return Math.max(0, Math.min(5, Math.round(num)))
})

/** R6：展开态是卡片自己的事，和 `active`（图上高亮的是哪个）无关 ——
 * 点一下要同时做两件事：图上 pan 过去，卡片展开。两个状态混成一个的话，
 * 「点第二个亮点」会把第一个的详情连带收起，读起来像详情丢了。 */
const expanded = ref(false)

/** R6：四个扩展字段，空串一律当不存在。后端取不到时给的就是空串（见
 * `_extract_text`），不是 undefined —— 两种都要挡住，桩数据里也可能直接省掉键。 */
const text = (value) => String(value ?? '').trim()
const address = computed(() => text(props.poi?.address))
const tel = computed(() => text(props.poi?.tel))
const opentime = computed(() => text(props.poi?.opentime))
const photo = computed(() => text(props.poi?.photo))

/** 详情行。一行都凑不出来时整个详情区不渲染，连「收起」的箭头都不出现 ——
 * 让用户点开一个空框，比不让点更糟。 */
const details = computed(() =>
  [
    { key: 'address', label: '地址', value: address.value },
    { key: 'tel', label: '电话', value: tel.value },
    { key: 'opentime', label: '营业时间', value: opentime.value },
  ].filter((row) => row.value),
)

const hasDetails = computed(() => details.value.length > 0 || !!photo.value)

/** 一次点击两件事：让图上 pan 到这个点（emit 出去，ResultView 转给 MapView），
 * 顺手把详情切换开。没有详情可展时只做前者。 */
function activate() {
  emit('focus-poi', props.index)
  if (hasDetails.value) expanded.value = !expanded.value
}
</script>

<template>
  <article
    :class="['poi', `poi--${color}`, { 'poi--active': active, 'poi--expanded': expanded }]"
    tabindex="0"
    role="button"
    :aria-pressed="active ? 'true' : 'false'"
    :aria-expanded="hasDetails ? String(expanded) : undefined"
    @click="activate"
    @keydown.enter.prevent="activate"
    @keydown.space.prevent="activate"
  >
    <span class="bh-numeral poi__index" aria-hidden="true">{{ ordinal(index) }}</span>

    <div class="poi__body">
      <h4 class="poi__name">{{ name }}</h4>
      <div class="poi__meta">
        <span class="poi__route-kind">{{ index === 0 ? '途经' : '附近' }}</span>
        <span v-if="type" class="poi__tag">{{ type }}</span>
        <span v-if="offRouteMeters" class="bh-mono poi__distance">距路线约 {{ offRouteMeters }}</span>
      </div>

      <div v-if="rating" class="poi__rating">
        <span class="poi__stars" aria-hidden="true">
          <i
            v-for="n in 5"
            :key="n"
            :class="['poi__star', { 'poi__star--on': n <= stars }]"
          />
        </span>
        <span class="bh-mono poi__score">{{ rating }}</span>
        <span class="bh-sr">评分 {{ rating }} 分，满分 5 分</span>
      </div>

      <!-- T1：这里原来印裸坐标（如 121.5432,38.8871）。那个位置对用户没有意义，
           「距路线约 X 米」已经在上面的 meta 行里了。坐标仍然通过 location
           传给 MapView 画标记，只是不再显示。 -->

      <!-- R6：有详情才提示可展开。一个字段都没有时这行不出现 ——
           许诺一个点开是空的框，比不许诺更糟。 -->
      <p v-if="hasDetails" class="poi__toggle" aria-hidden="true">
        <span class="poi__toggle-mark">{{ expanded ? '−' : '+' }}</span>
        {{ expanded ? '收起详情' : '展开详情' }}
      </p>

      <div v-if="hasDetails && expanded" class="poi__detail">
        <!-- 照片来自高德，跨域直连；加载失败就把它自己藏掉，不留一个破图框 -->
        <img
          v-if="photo"
          class="poi__photo"
          :src="photo"
          :alt="`${name} 的照片`"
          loading="lazy"
          referrerpolicy="no-referrer"
          @error="($event) => ($event.target.style.display = 'none')"
        />
        <dl v-if="details.length" class="poi__rows">
          <template v-for="row in details" :key="row.key">
            <dt class="bh-label poi__row-label">{{ row.label }}</dt>
            <dd :class="['poi__row-value', { 'bh-mono': row.key === 'tel' }]">{{ row.value }}</dd>
          </template>
        </dl>
      </div>
    </div>
  </article>
</template>

<style scoped>
.poi {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: var(--bh-4);
  align-items: start;
  padding: var(--bh-4);
  border: var(--bh-line) solid var(--bh-ink);
  background: var(--bh-white);
  cursor: pointer;
  transition: transform var(--bh-transition), box-shadow var(--bh-transition);
}

.poi:hover,
.poi--active {
  transform: translate(-3px, -3px);
  box-shadow: var(--bh-shadow-sm);
}

.poi__index {
  display: grid;
  place-items: center;
  width: 46px;
  height: 46px;
  font-size: var(--bh-text-lg);
  border: var(--bh-line) solid var(--bh-ink);
}

.poi--red .poi__index {
  background: var(--bh-red);
  color: var(--bh-white);
}
.poi--blue .poi__index {
  background: var(--bh-blue);
  color: var(--bh-white);
}
.poi--yellow .poi__index {
  background: var(--bh-yellow);
  color: var(--bh-ink);
}

.poi--active {
  border-width: var(--bh-line);
  outline: 3px solid var(--bh-ink);
  outline-offset: -6px;
}

.poi__body {
  display: grid;
  gap: var(--bh-2);
  min-width: 0;
}

.poi__name {
  font-size: var(--bh-text-lg);
  overflow-wrap: anywhere;
}

.poi__meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--bh-2) var(--bh-3);
}

.poi__tag {
  padding: 2px var(--bh-2);
  border: 2px solid var(--bh-ink);
  background: var(--bh-paper-2);
  font-size: var(--bh-text-xs);
  font-weight: 700;
  letter-spacing: var(--bh-track-label);
  text-transform: uppercase;
}

.poi__route-kind {
  padding: 2px var(--bh-2);
  border: 2px solid var(--bh-ink);
  background: var(--bh-red);
  color: var(--bh-white);
  font-size: var(--bh-text-xs);
  font-weight: 700;
}

.poi__distance {
  font-size: var(--bh-text-xs);
  color: var(--bh-ink-soft);
}

.poi__rating {
  display: flex;
  align-items: center;
  gap: var(--bh-2);
}

.poi__stars {
  display: inline-flex;
  gap: 3px;
}

.poi__star {
  width: 11px;
  height: 11px;
  border: 2px solid var(--bh-ink);
  background: var(--bh-white);
}

.poi__star--on {
  background: var(--bh-yellow);
}

.poi__score {
  font-size: var(--bh-text-sm);
  font-weight: 700;
}

/* ---------- R6 展开详情 ---------- */

.poi__toggle {
  display: flex;
  align-items: center;
  gap: var(--bh-2);
  font-size: var(--bh-text-xs);
  font-weight: 700;
  letter-spacing: var(--bh-track-label);
  text-transform: uppercase;
  color: var(--bh-ink-soft);
}

/* 加减号用方块框住，和卡片的硬边风格一致（圆形箭头在这套设计里是外来物） */
.poi__toggle-mark {
  display: grid;
  place-items: center;
  width: 16px;
  height: 16px;
  border: 2px solid var(--bh-ink);
  background: var(--bh-paper-2);
  color: var(--bh-ink);
  font-size: var(--bh-text-xs);
  line-height: 1;
}

.poi__detail {
  display: grid;
  gap: var(--bh-3);
  margin-top: var(--bh-1);
  padding-top: var(--bh-3);
  border-top: var(--bh-line) solid var(--bh-ink);
}

/* 照片按容器宽度铺满、限高裁切。不设 aspect-ratio：高德返回的图比例不一，
   写死比例会把竖图拉变形。 */
.poi__photo {
  display: block;
  width: 100%;
  max-height: 160px;
  object-fit: cover;
  border: 2px solid var(--bh-ink);
  background: var(--bh-paper-2);
}

/* 标签一列、值一列。值那列 minmax(0, 1fr) 而不是 1fr —— 长地址在 grid 里
   不加 minmax(0,…) 会把卡片撑破（窄屏上会触发 smoke 的横向溢出检查）。 */
.poi__rows {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: var(--bh-2) var(--bh-3);
  margin: 0;
}

.poi__row-label {
  color: var(--bh-ink-soft);
  white-space: nowrap;
}

.poi__row-value {
  margin: 0;
  font-size: var(--bh-text-sm);
  overflow-wrap: anywhere;
}
</style>
