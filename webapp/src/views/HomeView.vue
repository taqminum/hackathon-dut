<script setup>
import { computed, onMounted, ref } from 'vue'
import ExploreModeSelector from '../components/ExploreModeSelector.vue'
import PlaceInput from '../components/PlaceInput.vue'
import StateBlock from '../components/StateBlock.vue'
import { DEFAULT_MODE, DEMO_SCENARIOS, findMode } from '../constants.js'
import { useApi } from '../composables/useApi.js'
import { loadHistory, pushHistory, clearHistory } from '../utils/history.js'

/**
 * 首页：输入起终点、选择探索程度、提交推荐。
 * 对外仍然通过 emit('select', result) 把结果交给上层切换到结果页。
 */
const props = defineProps({
  modelValue: { type: String, default: DEFAULT_MODE },
})

const emit = defineEmits(['update:modelValue', 'select'])

const api = useApi()

const mode = computed({
  get: () => props.modelValue || DEFAULT_MODE,
  set: (value) => emit('update:modelValue', value),
})

const origin = ref('')
const destination = ref('')
const loading = ref(false)
const error = ref('')
const touched = ref(false)
const history = ref([])

const canSubmit = computed(
  () => !loading.value && !!origin.value.trim() && !!destination.value.trim(),
)

const originInvalid = computed(() => touched.value && !origin.value.trim())
const destinationInvalid = computed(() => touched.value && !destination.value.trim())

function swap() {
  const previous = origin.value
  origin.value = destination.value
  destination.value = previous
}

/**
 * 提交推荐请求。
 * modeOverride：演示场景 / 历史记录点击时，模式与请求同一帧发生。
 * mode 是基于 props.modelValue 的 computed，写入后要等父组件回传才生效，
 * 所以这里显式接收模式，避免用到上一次的值。
 */
async function handleSubmit(modeOverride) {
  touched.value = true
  error.value = ''

  if (!origin.value.trim() || !destination.value.trim()) {
    error.value = '请先填写起点和终点'
    return
  }

  try {
    await Promise.resolve()
    loading.value = true

    // 只接受字符串，防止表单 submit 事件对象被当成 mode 传进来
    const override = typeof modeOverride === 'string' ? modeOverride : ''

    const payload = {
      origin: origin.value.trim(),
      destination: destination.value.trim(),
      mode: override || mode.value,
    }

    const result = await api.recommendRoute(payload)

    if (!result?.route) {
      error.value = '未找到推荐路线，请调整起终点后重试'
      return
    }

    history.value = pushHistory({ ...payload })
    emit('select', { ...result, request: payload })
  } catch (err) {
    error.value = err?.message || '获取路线失败，请稍后重试'
  } finally {
    loading.value = false
  }
}

function fillDemo(newOrigin, newDestination, newMode) {
  origin.value = newOrigin
  destination.value = newDestination
  mode.value = newMode
  return handleSubmit(newMode)
}

function applyScenario(scenario) {
  return fillDemo(scenario.origin, scenario.destination, scenario.mode)
}

function applyHistory(item) {
  return fillDemo(item.origin, item.destination, item.mode || mode.value)
}

function removeHistory() {
  history.value = clearHistory()
}

const suggest = (payload) => api.suggestPlaces(payload)

onMounted(() => {
  history.value = loadHistory()
})

defineExpose({ handleSubmit, fillDemo })
</script>

<template>
  <section class="home">
    <div class="bh-shell home__inner">
      <div class="home__hero">
        <p class="bh-label home__kicker">可控的意外</p>
        <h1 class="home__title">
          <span class="home__title-line">去同一个</span>
          <span class="home__title-line home__title-line--accent">目的地</span>
          <span class="home__title-line">换一条路</span>
        </h1>
        <p class="home__lede">
          输入起点和终点，选一个愿意多花的时间。我们在这个预算内，
          挑一条更值得走的路，并告诉你为什么。
        </p>
        <div class="home__hero-shapes" aria-hidden="true">
          <span class="shape shape--circle" />
          <span class="shape shape--square" />
          <span class="shape shape--tri" />
        </div>
      </div>

      <form class="home__form bh-card" novalidate @submit.prevent="handleSubmit">
        <div class="home__pair">
          <PlaceInput
            v-model="origin"
            label="起点"
            badge="A"
            badge-color="ink"
            placeholder="例如：大连理工大学"
            :disabled="loading"
            :invalid="originInvalid"
            :suggest-fn="suggest"
          />
          <button
            type="button"
            class="home__swap"
            aria-label="交换起点和终点"
            :disabled="loading"
            @click="swap"
          >
            ⇅
          </button>
          <PlaceInput
            v-model="destination"
            label="终点"
            badge="B"
            badge-color="blue"
            placeholder="例如：星海广场"
            :disabled="loading"
            :invalid="destinationInvalid"
            :suggest-fn="suggest"
          />
        </div>

        <ExploreModeSelector v-model="mode" :disabled="loading" />

        <button type="submit" class="bh-btn bh-btn--primary bh-btn--lg bh-btn--block" :disabled="!canSubmit">
          {{ loading ? '正在规划…' : '生成偶遇路线' }}
        </button>

        <StateBlock
          v-if="loading"
          variant="loading"
          title="正在寻找可控的意外…"
          message="正在比较候选路线、计算绕行成本并挑选沿途亮点。"
        />
        <p v-else-if="error" class="bh-notice bh-notice--error" role="alert">{{ error }}</p>
      </form>

      <section class="home__section">
        <h2 class="home__section-title">快速体验</h2>
        <div class="demo-scenarios">
          <button
            v-for="scenario in DEMO_SCENARIOS"
            :key="scenario.id"
            type="button"
            :class="['demo', `demo--${scenario.color}`]"
            :disabled="loading"
            @click="applyScenario(scenario)"
          >
            <span class="demo__route">
              {{ scenario.originLabel }}
              <span class="demo__arrow" aria-hidden="true">→</span>
              {{ scenario.destinationLabel }}
            </span>
            <span class="bh-mono demo__mode">{{ findMode(scenario.mode).label }}</span>
          </button>
        </div>
      </section>

      <section v-if="history.length" class="home__section">
        <div class="home__section-head">
          <h2 class="home__section-title">最近查询</h2>
          <button type="button" class="bh-btn bh-btn--ghost home__clear" @click="removeHistory">
            清空
          </button>
        </div>
        <ul class="history">
          <li v-for="item in history" :key="`${item.origin}-${item.destination}-${item.mode}`">
            <button type="button" class="history__item" :disabled="loading" @click="applyHistory(item)">
              <span class="bh-mono history__pair">{{ item.origin }} → {{ item.destination }}</span>
              <span class="history__mode">{{ findMode(item.mode).label }}</span>
            </button>
          </li>
        </ul>
      </section>
    </div>
  </section>
</template>

<style scoped>
.home__inner {
  display: grid;
  gap: var(--bh-6);
  padding-top: var(--bh-6);
  padding-bottom: var(--bh-8);
}

/* ---------- Hero ---------- */

.home__hero {
  position: relative;
  display: grid;
  gap: var(--bh-3);
  padding: var(--bh-5) 0 var(--bh-4);
  border-bottom: var(--bh-line-thick) solid var(--bh-ink);
}

.home__kicker {
  color: var(--bh-red);
}

.home__title {
  display: grid;
  font-size: var(--bh-text-3xl);
  max-width: 16ch;
}

.home__title-line--accent {
  color: var(--bh-blue);
}

.home__lede {
  max-width: 52ch;
  font-size: var(--bh-text-md);
  color: var(--bh-ink-soft);
}

.home__hero-shapes {
  position: absolute;
  top: var(--bh-4);
  right: 0;
  display: flex;
  align-items: flex-end;
  gap: var(--bh-3);
}

.shape {
  display: block;
  border: var(--bh-line) solid var(--bh-ink);
}

.shape--circle {
  width: 52px;
  height: 52px;
  border-radius: 50%;
  background: var(--bh-red);
}

.shape--square {
  width: 44px;
  height: 44px;
  background: var(--bh-blue);
}

.shape--tri {
  width: 0;
  height: 0;
  border: none;
  border-left: 26px solid transparent;
  border-right: 26px solid transparent;
  border-bottom: 46px solid var(--bh-yellow);
}

/* ---------- 表单 ---------- */

.home__form {
  display: grid;
  gap: var(--bh-5);
}

.home__pair {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  gap: var(--bh-3);
  align-items: start;
}

.home__swap {
  margin-top: 26px;
  width: 44px;
  height: 44px;
  border: var(--bh-line) solid var(--bh-ink);
  background: var(--bh-yellow);
  font-size: var(--bh-text-lg);
  line-height: 1;
  box-shadow: var(--bh-shadow-sm);
  transition: transform var(--bh-transition);
}

.home__swap:hover:not(:disabled) {
  transform: translate(-2px, -2px);
}

.home__swap:disabled {
  background: var(--bh-paper-2);
  box-shadow: none;
}

/* ---------- 分区 ---------- */

.home__section {
  display: grid;
  gap: var(--bh-3);
}

.home__section-head {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: var(--bh-3);
}

.home__section-title {
  font-size: var(--bh-text-md);
  letter-spacing: var(--bh-track-label);
}

.home__clear {
  padding: var(--bh-1) var(--bh-3);
  font-size: var(--bh-text-xs);
}

/* ---------- 演示场景 ---------- */

.demo-scenarios {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: var(--bh-3);
}

.demo {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--bh-3);
  padding: var(--bh-4);
  border: var(--bh-line) solid var(--bh-ink);
  background: var(--bh-white);
  text-align: left;
  box-shadow: var(--bh-shadow-sm);
  transition: transform var(--bh-transition), box-shadow var(--bh-transition);
}

.demo:hover:not(:disabled) {
  transform: translate(-3px, -3px);
  box-shadow: var(--bh-shadow);
}

.demo:disabled {
  opacity: 0.55;
  box-shadow: none;
}

.demo--red {
  border-left: var(--bh-line-thick) solid var(--bh-red);
}
.demo--blue {
  border-left: var(--bh-line-thick) solid var(--bh-blue);
}
.demo--yellow {
  border-left: var(--bh-line-thick) solid var(--bh-yellow);
}

.demo__route {
  font-size: var(--bh-text-sm);
  font-weight: 700;
}

.demo__arrow {
  color: var(--bh-ink-soft);
  padding: 0 2px;
}

.demo__mode {
  padding: 2px var(--bh-2);
  border: 2px solid var(--bh-ink);
  background: var(--bh-paper-2);
  font-size: var(--bh-text-xs);
  font-weight: 700;
  white-space: nowrap;
}

/* ---------- 历史 ---------- */

.history {
  margin: 0;
  padding: 0;
  list-style: none;
  display: grid;
  gap: var(--bh-2);
}

.history__item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--bh-3);
  width: 100%;
  padding: var(--bh-2) var(--bh-3);
  border: 2px solid var(--bh-ink);
  background: var(--bh-white);
  text-align: left;
}

.history__item:hover:not(:disabled) {
  background: var(--bh-yellow);
}

.history__pair {
  font-size: var(--bh-text-xs);
  overflow-wrap: anywhere;
}

.history__mode {
  font-size: var(--bh-text-xs);
  font-weight: 700;
  letter-spacing: var(--bh-track-label);
  text-transform: uppercase;
  white-space: nowrap;
}

@media (max-width: 720px) {
  .home__hero-shapes {
    position: static;
    justify-content: flex-start;
  }

  .home__pair {
    grid-template-columns: 1fr;
  }

  .home__swap {
    margin-top: 0;
    justify-self: end;
  }
}
</style>

