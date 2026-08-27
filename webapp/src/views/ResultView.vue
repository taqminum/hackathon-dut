<script setup>
import { computed, ref } from 'vue'
import MapView from '../components/MapView.vue'
import StatTile from '../components/StatTile.vue'
import ScoreMeter from '../components/ScoreMeter.vue'
import NarrativeBlock from '../components/NarrativeBlock.vue'
import PoiCard from '../components/PoiCard.vue'
import RouteSteps from '../components/RouteSteps.vue'
import StateBlock from '../components/StateBlock.vue'
import { findMode } from '../constants.js'
import { useApi } from '../composables/useApi.js'
import { formatDetour, formatDistance, formatMinutes, formatScore } from '../utils/format.js'

/**
 * 结果页：关键指标、叙事、地图、沿途亮点、分段指引。
 * result 缺失或没有 route 时显示空结果态，不白屏。
 */
const props = defineProps({
  result: { type: Object, default: null },
})

const emit = defineEmits(['back'])

const api = useApi()

const activePoiIndex = ref(-1)
const saveState = ref('')
const feedbackState = ref('')
const stepsExpanded = ref(false)

const route = computed(() => props.result?.route ?? null)
const hasResult = computed(() => !!route.value)
const request = computed(() => props.result?.request ?? null)

const baselineMinutes = computed(() => formatMinutes(props.result?.baseline_minutes))
const detourMinutes = computed(() => formatDetour(props.result?.detour_minutes))
const score = computed(() => formatScore(props.result?.score))
const narrative = computed(() => props.result?.narrative ?? '')
const pois = computed(() => (Array.isArray(props.result?.pois) ? props.result.pois : []))
const steps = computed(() => (Array.isArray(route.value?.steps) ? route.value.steps : []))

const modeInfo = computed(() => findMode(request.value?.mode))
const totalMinutes = computed(() => {
  const base = Number(props.result?.baseline_minutes)
  const detour = Number(props.result?.detour_minutes)
  if (!Number.isFinite(base)) return '--'
  return formatMinutes(base + (Number.isFinite(detour) ? detour : 0))
})
const distance = computed(() => formatDistance(route.value?.distance))
const isDemo = computed(() => route.value?.demo_mode === true)

function focusPoi(index) {
  activePoiIndex.value = activePoiIndex.value === index ? -1 : index
}

/** 收藏当前路线。接口未定稿，失败只提示，不阻塞 */
async function save() {
  saveState.value = 'saving'
  const response = await api.saveTrip({
    origin: request.value?.origin ?? route.value?.origin ?? '',
    destination: request.value?.destination ?? route.value?.destination ?? '',
    mode: request.value?.mode ?? modeInfo.value.value,
    baseline_minutes: props.result?.baseline_minutes ?? null,
    detour_minutes: props.result?.detour_minutes ?? null,
    score: props.result?.score ?? null,
    narrative: narrative.value,
    pois: pois.value,
    route: route.value,
  })
  saveState.value = response?.ok ? 'saved' : 'failed'
}

/** 路线反馈。接口未定稿，静默降级 */
async function feedback(liked) {
  feedbackState.value = liked ? 'liked' : 'disliked'
  await api.sendFeedback({
    tripId: props.result?.trip_id ?? null,
    liked,
    mode: request.value?.mode ?? modeInfo.value.value,
  })
}

const saveLabel = computed(() => {
  if (saveState.value === 'saving') return '收藏中…'
  if (saveState.value === 'saved') return '已收藏'
  if (saveState.value === 'failed') return '收藏失败，重试'
  return '收藏这条路线'
})
</script>

<template>
  <section class="result">
    <div class="bh-shell result__inner">
      <StateBlock
        v-if="!hasResult"
        variant="empty"
        title="还没有推荐结果"
        message="返回首页填写起点和终点，或直接试试三个演示场景。"
        action-label="回到首页"
        @action="emit('back')"
      />

      <template v-else>
        <div class="result__head">
          <div class="result__head-text">
            <p class="bh-label result__kicker">推荐路线</p>
            <h1 class="result__title">
              <span class="bh-mono result__from">{{ request?.origin || route?.origin || '起点' }}</span>
              <span class="result__arrow" aria-hidden="true">→</span>
              <span class="bh-mono result__to">{{ request?.destination || route?.destination || '终点' }}</span>
            </h1>
            <p class="result__mode">
              模式 <strong>{{ modeInfo.label }}</strong> · {{ modeInfo.title }}
            </p>
          </div>
          <button type="button" class="bh-btn result__back" @click="emit('back')">重新规划</button>
        </div>

        <p v-if="isDemo" class="bh-notice bh-notice--warn">
          当前展示内置演示数据（未配置高德 Key），指标与路线为预置场景。
        </p>

        <div class="result__tiles">
          <StatTile label="基准时长" :value="baselineMinutes" unit="分钟" color="ink" hint="最快路线预计用时" />
          <StatTile label="额外时间" :value="detourMinutes" unit="分钟" color="red" hint="为探索多花的时间" />
          <StatTile label="总计" :value="totalMinutes" unit="分钟" color="paper" hint="基准加绕行" />
          <StatTile label="全程距离" :value="distance" color="blue" hint="推荐路线长度" />
        </div>

        <div class="result__meter bh-card bh-card--flat">
          <ScoreMeter :score="props.result?.score" />
          <p class="result__meter-note">
            评分越高代表沿途探索价值越大，同时已扣除绕行时间的代价。当前 {{ score }} 分。
          </p>
        </div>

        <NarrativeBlock :narrative="narrative" :mode-label="modeInfo.label" />

        <MapView
          :route="route"
          :pois="pois"
          :active-poi-index="activePoiIndex"
          @poi-click="focusPoi"
        />

        <section class="result__pois">
          <div class="result__section-head">
            <h2 class="result__section-title">沿途亮点</h2>
            <span class="bh-mono result__section-count">{{ pois.length }} 处</span>
          </div>

          <div v-if="pois.length" class="result__poi-list">
            <PoiCard
              v-for="(poi, index) in pois"
              :key="`${poi.name || 'poi'}-${index}`"
              :poi="poi"
              :index="index"
              :active="index === activePoiIndex"
              @focus-poi="focusPoi"
            />
          </div>
          <StateBlock
            v-else
            variant="empty"
            title="这段路没有找到亮点"
            message="可以换一个探索程度，或者调整起终点再试一次。"
            action-label="换个模式再试"
            @action="emit('back')"
          />
        </section>

        <RouteSteps v-model:expanded="stepsExpanded" :steps="steps" />

        <div class="result__actions">
          <button
            type="button"
            class="bh-btn bh-btn--accent"
            :disabled="saveState === 'saving' || saveState === 'saved'"
            @click="save"
          >
            {{ saveLabel }}
          </button>
          <div class="result__feedback">
            <span class="bh-label">这条路线怎么样</span>
            <button
              type="button"
              class="bh-btn"
              :class="{ 'bh-btn--primary': feedbackState === 'liked' }"
              @click="feedback(true)"
            >
              还不错
            </button>
            <button
              type="button"
              class="bh-btn"
              :class="{ 'bh-btn--danger': feedbackState === 'disliked' }"
              @click="feedback(false)"
            >
              一般
            </button>
          </div>
        </div>
      </template>
    </div>
  </section>
</template>

<style scoped>
.result__inner {
  display: grid;
  gap: var(--bh-5);
  padding-top: var(--bh-6);
  padding-bottom: var(--bh-8);
}

.result__head {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: var(--bh-4);
  padding-bottom: var(--bh-3);
  border-bottom: var(--bh-line-thick) solid var(--bh-ink);
}

.result__head-text {
  display: grid;
  gap: var(--bh-2);
  min-width: 0;
}

.result__kicker {
  color: var(--bh-red);
}

.result__title {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--bh-2) var(--bh-3);
  font-size: var(--bh-text-xl);
  text-transform: none;
}

.result__from,
.result__to {
  overflow-wrap: anywhere;
}

.result__to {
  color: var(--bh-blue);
}

.result__arrow {
  color: var(--bh-ink-soft);
}

.result__mode {
  font-size: var(--bh-text-sm);
  color: var(--bh-ink-soft);
}

.result__back {
  flex: 0 0 auto;
}

/* ---------- 指标 ---------- */

.result__tiles {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(160px, 1fr));
  gap: var(--bh-3);
}

.result__meter {
  display: grid;
  gap: var(--bh-3);
}

.result__meter-note {
  font-size: var(--bh-text-sm);
  color: var(--bh-ink-soft);
}

/* ---------- 亮点 ---------- */

.result__pois {
  display: grid;
  gap: var(--bh-3);
}

.result__section-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--bh-3);
}

.result__section-title {
  font-size: var(--bh-text-md);
  letter-spacing: var(--bh-track-label);
}

.result__section-count {
  font-size: var(--bh-text-xs);
  color: var(--bh-ink-soft);
}

.result__poi-list {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  gap: var(--bh-3);
}

/* ---------- 底部操作 ---------- */

.result__actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: var(--bh-4);
  padding-top: var(--bh-4);
  border-top: var(--bh-line) solid var(--bh-ink);
}

.result__feedback {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--bh-2);
}

@media (max-width: 720px) {
  .result__head {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
