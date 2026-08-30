<script setup>
import { computed, ref } from 'vue'
import MapView from '../components/MapView.vue'
import StatTile from '../components/StatTile.vue'
import ScoreMeter from '../components/ScoreMeter.vue'
import NarrativeBlock from '../components/NarrativeBlock.vue'
import PoiCard from '../components/PoiCard.vue'
import RouteSteps from '../components/RouteSteps.vue'
import StateBlock from '../components/StateBlock.vue'
import { DETOUR_BUDGET, EXPLORE_MODES, findMode, SCORE_MAX, SCORE_WEIGHTS } from '../constants.js'
import { useApi } from '../composables/useApi.js'
import {
  formatDetour,
  formatDistance,
  formatDuration,
  formatMinutes,
  formatScore,
  poiTypeLabel,
  toNumber,
} from '../utils/format.js'

/**
 * 结果页：关键指标、叙事、地图、沿途亮点、分段指引。
 * result 缺失或没有 route 时显示空结果态，不白屏。
 */
const props = defineProps({
  result: { type: Object, default: null },
  // R7：重新规划由 App 层发请求，这两个只是它的进行态与错误文案
  replanning: { type: Boolean, default: false },
  replanError: { type: String, default: '' },
})

// R7：`back` 是回首页，`replan` 是原地重算。这两个过去是同一个事件 ——
// 「重新规划」按钮 emit 的也是 `back`，于是它和页头的「返回首页」一模一样。
const emit = defineEmits(['back', 'replan'])

const api = useApi()

const activePoiIndex = ref(-1)
const saveState = ref('')
const feedbackState = ref('')
// T8-4：反馈的文字确认。选中态只说「你点了哪个」，这行说「后端真的学到了什么」
const feedbackNote = ref('')
const stepsExpanded = ref(false)

const route = computed(() => props.result?.route ?? null)
// P3-4：基准路线。老后端不返回这个字段时为 null，MapView 只画推荐那一条。
const baselineRoute = computed(() => props.result?.baseline_route ?? null)
const hasResult = computed(() => !!route.value)
const request = computed(() => props.result?.request ?? null)

// T1：标题优先显示地名，没有标签才退回坐标。标签只来自 request（前端组装的），
// route.origin 是后端回显的坐标，永远不会是地名。
const originLabel = computed(() => String(request.value?.originLabel || '').trim())
const destinationLabel = computed(() => String(request.value?.destinationLabel || '').trim())
const originText = computed(
  () => originLabel.value || request.value?.origin || route.value?.origin || '起点',
)
const destinationText = computed(
  () => destinationLabel.value || request.value?.destination || route.value?.destination || '终点',
)

const baselineMinutes = computed(() => formatMinutes(props.result?.baseline_minutes))
const detourMinutes = computed(() => formatDetour(props.result?.detour_minutes))
// T5：和 ScoreMeter 用同一个上界，否则「当前 7.2 分」会和条上的「7.0/7」互相打脸
const score = computed(() => formatScore(props.result?.score, SCORE_MAX))

/** S1(c)：绕行不足一分钟时，「额外时间」格改印**距离**增量。
 *
 * `detour_minutes` 为 0 是真实的 —— 兜底演示数据的真实绕行只有几十米，`round()`
 * 抹平到 0。但那让三个模式在这个格子上显示同一个 `+0`，正是用户说「三个模式
 * 没区别」时盯着的地方。距离增量是从两条折线量出来的，几何是真的、数字也是真的，
 * 而且三个模式各不相同。
 *
 * 不去伪造分钟数：把 0 显示成「+1 分钟」才是假数字。单位跟着值一起换，
 * 所以格子里不会出现「+13 分钟」这种把米读成分钟的错。
 */
const detourDistanceMeters = computed(() => {
  const base = toNumber(baselineRoute.value?.distance)
  const routed = toNumber(route.value?.distance)
  if (base === null || routed === null) return null
  const delta = Math.round(routed - base)
  return delta > 0 ? delta : null
})

/** 绕行为 0 且能算出距离增量时，格子改用距离。两个值必须一起换 ——
 * 只换数字不换单位就会印出「+13 分钟」。 */
const detourTile = computed(() => {
  const showDistance = detourMinutes.value === '0' && detourDistanceMeters.value !== null
  if (!showDistance) {
    return {
      value: detourMinutes.value,
      unit: '分钟',
      hint: detourMinutes.value === '0' ? '几乎不耽误，顺路就到' : '为探索多花的时间',
    }
  }
  return {
    value: `+${detourDistanceMeters.value}`,
    unit: '米',
    hint: '不足一分钟，按多走的距离算',
  }
})
const narrative = computed(() => props.result?.narrative ?? '')
const pois = computed(() => (Array.isArray(props.result?.pois) ? props.result.pois : []))
const steps = computed(() => (Array.isArray(route.value?.steps) ? route.value.steps : []))

const modeInfo = computed(() => findMode(request.value?.mode))

/** S3：结果页上的模式切换。评委在同一条路线上连点三个模式，就能看出
 * 「探索程度」这个旋钮到底改变了什么 —— 这是 S1 那些几何差异最直观的展示方式。
 *
 * 复用 `EXPLORE_MODES`（和首页同一份数据），不新造一套视觉：同一个概念在两个页面
 * 长得不一样，用户会以为是两回事。当前模式来自 `request.mode`，切换后由 App 层
 * 写回 `request`，所以高亮跟着响应走，不需要本地再存一份状态（存了就会和
 * 「请求失败、模式没真的换」不一致）。
 */
const exploreModes = EXPLORE_MODES

/** T4：把评分拆回三项。后端 `SerendipityScorer.score` 是
 * `标签契合 + 亮点质量 - 绕行惩罚`，其中亮点质量和绕行惩罚都能从响应里
 * 直接算出来（选中 POI 的 rating、detour_minutes），剩下的就是标签契合。
 *
 * 反推出来的值必须落在权重允许的区间内、且三项能加回 `score`，否则返回 null：
 * 后端改了权重、或者总分被 `max(0, ...)` 截断过的时候，摆一组加不出总数的
 * 数字比不摆更糟。SCORE_WEIGHTS 是副本，这个验算就是它和后端脱钩的报警器。
 */
const scoreBreakdown = computed(() => {
  const total = toNumber(props.result?.score)
  if (total === null || total <= 0) return null

  const rating = toNumber(pois.value[0]?.rating)
  const detour = toNumber(props.result?.detour_minutes)
  if (rating === null || rating <= 0 || detour === null) return null

  // 全部换算成「一位小数」这个单位再算，屏幕上印出来的四个数字才真的加得起来。
  // 先按真值取整到 0.1，再让契合度吃掉舍入误差 —— 它本来就是反推出来的那一项。
  const round1 = (value) => Math.round(value * 10) / 10
  // 和 score / ScoreMeter 用同一个上界（T5），否则拆分里的总分会跟评分条对不上
  const totalShown = round1(Math.min(total, SCORE_MAX))
  const quality = round1(SCORE_WEIGHTS.quality * Math.min(1, Math.max(0, rating / 5)))
  const penalty = round1(SCORE_WEIGHTS.detourPenaltyPerMinute * Math.max(0, detour))
  const affinity = round1(totalShown - quality + penalty)

  // 反推值落在 [0, TAG_WEIGHT] 之外说明这份数据不是这个公式算出来的
  // （后端换了权重，或者分数是别处硬写的），那就不摆拆分。
  if (affinity < 0 || affinity > SCORE_WEIGHTS.tag) return null
  // 舍入之后仍然加不回总分（0.05 边界上可能差 0.1），同样不摆
  if (Math.abs(round1(quality + affinity - penalty) - totalShown) > 1e-9) return null

  return {
    total: totalShown.toFixed(1),
    quality: quality.toFixed(1),
    affinity: affinity.toFixed(1),
    penalty: penalty.toFixed(1),
  }
})

/** 一条 POI 的展示名：`理工咖啡小铺（咖啡厅 4.4 分）`，缺字段就少一段。 */
function describePoi(poi) {
  const name = poi?.name || '未命名地点'
  const rating = toNumber(poi?.rating)
  const detail = [poiTypeLabel(poi?.type), rating !== null && rating > 0 ? `${rating.toFixed(1)} 分` : '']
    .filter(Boolean)
    .join(' ')
  return detail ? `${name}（${detail}）` : name
}

/** T4：结构化的推荐理由。这个框以前只有一句叙事，回答不了「为什么是这条」。
 * 每条都必须有后端字段支撑，凑不出来的那条就不出现 —— 宁可少说一条，
 * 也不写「风景更好」这种没有依据的话。
 */
const reasons = computed(() => {
  // 一个亮点都没有就没有「为什么值得绕这一趟」可讲。此时整个列表让位给
  // degradedNote 说实话，而不是留一条「多花 0 分钟」在那里充数 ——
  // 那读起来像给一条没有理由的路线找了个理由。
  if (!pois.value.length) return []

  const list = []
  const named = pois.value.slice(0, 3).map(describePoi).join('、')
  list.push(`沿途多了 ${pois.value.length} 处亮点：${named}`)

  const detour = toNumber(props.result?.detour_minutes)
  if (detour !== null) {
    const budget = DETOUR_BUDGET[request.value?.mode ?? modeInfo.value.value]
    const rounded = Math.max(0, Math.round(detour))
    const base = baselineMinutes.value === '--' ? '' : `原本 ${baselineMinutes.value} 分钟，`
    if (rounded === 0) {
      list.push(`${base}这条几乎不用绕，探索是顺路捡的`)
    } else if (budget === undefined) {
      list.push(`${base}为这些亮点多花 ${rounded} 分钟`)
    } else if (rounded <= budget) {
      list.push(`${base}多花 ${rounded} 分钟，在「${modeInfo.value.label}」的 ${budget} 分钟额度以内`)
    } else {
      // 后端 budget 校验应当拦住这种情况，真出现了也照实说，不含糊过去
      list.push(`${base}多花 ${rounded} 分钟，已经超出「${modeInfo.value.label}」的 ${budget} 分钟额度`)
    }
  }

  const breakdown = scoreBreakdown.value
  if (breakdown) {
    list.push(
      `探索评分 ${breakdown.total} / ${SCORE_MAX}：亮点质量 ${breakdown.quality}，` +
        `口味契合 ${breakdown.affinity}，绕行扣 ${breakdown.penalty}`,
    )
  } else if (score.value !== '--' && Number(score.value) > 0) {
    list.push(`探索评分 ${score.value} / ${SCORE_MAX}，已扣除绕行时间的代价`)
  }

  return list
})

/** 降级时说实话。没有亮点就没有「为什么绕这一趟」可讲，不许硬凑。 */
const degradedNote = computed(() => {
  if (pois.value.length) return ''
  const detour = toNumber(props.result?.detour_minutes)
  if (detour !== null && Math.round(detour) > 0) {
    return `这次没有匹配到值得绕行的亮点，下面这条只是可行路线，多出的 ${Math.round(detour)} 分钟没有探索价值支撑。`
  }
  return '这次没有找到值得绕行的亮点，给出的是最快路线。'
})

const totalMinutes = computed(() => {
  const base = Number(props.result?.baseline_minutes)
  const detour = Number(props.result?.detour_minutes)
  if (!Number.isFinite(base)) return '--'
  return formatMinutes(base + (Number.isFinite(detour) ? detour : 0))
})
const distance = computed(() => formatDistance(route.value?.distance))
/** R9：判据从 `demo_mode` 换成 `source`。
 *
 * `demo_mode` 是后端的 `scenario is not None` —— 只有命中三个预置场景才为真。
 * 没配 Key 时输入任意坐标走的也是本地兜底（`source === 'fallback'`），
 * 那种情况 `demo_mode` 是 false，于是页面一句提示都没有，用户会把
 * 「按 1.3 倍系数估出来的直线距离」当成真实步行路线。
 *
 * 判 `source` 才覆盖全部兜底出口。amap 分支的 `source` 是 `'amap'`，不显示。 */
const isDemo = computed(() => route.value?.source === 'fallback')

/** T3：两条线并排对比。验收人的原话是「你路线要显示出区别啊」——
 * 图上有两条线，但没有任何文字说明各是多少距离、多少时间、差在哪。
 *
 * 基准与推荐是同一条时（后端降级出口 `baseline_route == route`）不显示：
 * 那时候「对比」是 0 对 0，摆出来是假的。判据与 MapView 的
 * `hasBaselineComparison` 一致 —— polyline 相同就不算有对比，
 * 这样「图上有虚线」和「有对比块」永远同时成立或同时不成立。
 */
const hasComparison = computed(() => {
  const base = baselineRoute.value
  if (!base) return false
  if (base.polyline && route.value?.polyline && base.polyline === route.value.polyline) return false
  return toNumber(base.distance) !== null || toNumber(base.duration) !== null
})

/** 差值：正数才加「+」。距离用米算再格式化，避免「7.4 - 6.9 = 0.5」的显示误差。 */
const comparison = computed(() => {
  const baseDistance = toNumber(baselineRoute.value?.distance)
  const baseDuration = toNumber(baselineRoute.value?.duration)
  const routeDistance = toNumber(route.value?.distance)
  const routeDuration = toNumber(route.value?.duration)

  const deltaDistance =
    baseDistance !== null && routeDistance !== null ? routeDistance - baseDistance : null
  const deltaDuration =
    baseDuration !== null && routeDuration !== null ? routeDuration - baseDuration : null

  return {
    baselineDistance: formatDistance(baseDistance),
    baselineDuration: formatDuration(baseDuration),
    routeDistance: formatDistance(routeDistance),
    routeDuration: formatDuration(routeDuration),
    deltaDistance:
      deltaDistance === null
        ? ''
        : `${deltaDistance > 0 ? '+' : deltaDistance < 0 ? '-' : ''}${formatDistance(Math.abs(deltaDistance))}`,
    deltaDuration:
      deltaDuration === null
        ? ''
        : `${deltaDuration > 0 ? '+' : deltaDuration < 0 ? '-' : ''}${formatDuration(Math.abs(deltaDuration))}`,
  }
})

/** R5：喂给两个指标格的原值 + 差值。距离进「推荐路线距离」，时长进「总计」——
 * 这两个格子印的正好就是推荐路线的距离与总时长，原值贴在它们自己头上，
 * 才是「同一个数字被换掉了」。基准时长格不带原值：它印的就是原值本身。
 *
 * hasComparison 为假（没有 baseline_route，或降级出口把两条线做成同一条）时
 * 一律返回空串，格子回到只有大字的样子 —— 判据仍然和 MapView 的虚线共用一个，
 * 「图上有虚线」和「格子里有原值」永远同时成立。
 */
const tileCompare = computed(() => {
  const blank = { baseline: '', delta: '' }
  if (!hasComparison.value) return { distance: blank, duration: blank }

  // hasComparison 只要求距离或时长**之一**能算出来，所以两截各自还要挡一次：
  // formatDistance(null) 返回 '--'，直接印出去就是「原 --」，那比不印更糟。
  const pick = (baseline, delta) =>
    baseline && baseline !== '--' ? { baseline, delta } : blank

  return {
    distance: pick(comparison.value.baselineDistance, comparison.value.deltaDistance),
    duration: pick(comparison.value.baselineDuration, comparison.value.deltaDuration),
  }
})

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

/** T8-4：路线反馈。要点是「视觉确认」必须对应**真实结果**，不能只表示按钮被点过。
 *
 * 后端 `POST /api/feedback` 返回 `{ ok, learned: [...] }`。`learned` 里是这次
 * 落到的粗类目，空数组说明没归因上（没有 trip_id，或 id 已被淘汰）—— 那时候
 * 后续推荐不会有任何变化，写「已记住」就是骗人。三种结局分别有自己的文案：
 *   learned 非空  -> 「已记住：咖啡…，下次这类会加权 / 降权」
 *   ok 但没学到    -> 「已收到，但这次没能归因到具体类型」
 *   接口挂了       -> 「反馈没送出去」
 * 选中态（按钮变色）只表示「你选的是这个」，是不是学到了由下面那行文字说。
 */
async function feedback(liked) {
  feedbackState.value = liked ? 'liked' : 'disliked'
  feedbackNote.value = '提交中…'
  const response = await api.sendFeedback({
    tripId: props.result?.trip_id ?? null,
    liked,
    mode: request.value?.mode ?? modeInfo.value.value,
  })

  if (!response?.ok) {
    feedbackNote.value = '反馈没送出去，稍后可以再点一次'
    return
  }

  const learned = Array.isArray(response.learned) ? response.learned.filter(Boolean) : []
  if (!learned.length) {
    feedbackNote.value = '已收到，但这次没能归因到具体类型，后续推荐不会改变'
    return
  }

  feedbackNote.value = `已记住：${learned.slice(0, 3).join('、')}，之后这类亮点会${
    liked ? '加权' : '降权'
  }`
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
              <span class="result__from" :class="{ 'bh-mono': !originLabel }">{{ originText }}</span>
              <span class="result__arrow" aria-hidden="true">→</span>
              <span class="result__to" :class="{ 'bh-mono': !destinationLabel }">{{ destinationText }}</span>
            </h1>
            <p class="result__mode">
              模式 <strong>{{ modeInfo.label }}</strong> · {{ modeInfo.title }}
            </p>
          </div>
          <!-- R7：这里只放「重新规划」—— 它用当前起终点和模式原地重算，留在结果页。
               「返回首页」在吸顶页头里（SiteHeader 的 showBack），滚到页面底部也还在，
               比这里再摆一个更有用；两处都摆就是同一个动作出现两遍。
               S3：旁边加三个模式，点一下就以该模式原地重算。 -->
          <div class="result__head-actions">
            <div
              class="result__modes"
              role="radiogroup"
              aria-label="换一个探索程度重新规划"
            >
              <button
                v-for="item in exploreModes"
                :key="item.value"
                type="button"
                role="radio"
                :aria-checked="modeInfo.value === item.value ? 'true' : 'false'"
                :disabled="replanning"
                :title="`${item.title} · ${item.caption}`"
                :class="[
                  'result__mode-btn',
                  `result__mode-btn--${item.color}`,
                  { 'result__mode-btn--active': modeInfo.value === item.value },
                ]"
                @click="emit('replan', item.value)"
              >
                <span class="bh-numeral">{{ item.label }}</span>
              </button>
            </div>
            <button
              type="button"
              class="bh-btn bh-btn--primary result__replan"
              :disabled="replanning"
              @click="emit('replan')"
            >
              {{ replanning ? '重新规划中…' : '重新规划' }}
            </button>
          </div>
        </div>

        <!-- R7：失败给中文，不把 `Failed to fetch` 直接摔在用户脸上 -->
        <p v-if="replanError" class="bh-notice bh-notice--error result__replan-error" role="alert">
          {{ replanError }}
        </p>

        <p v-if="isDemo" class="bh-notice bh-notice--warn result__demo-notice">
          当前展示离线演示数据（未接入高德实时路网），距离与时长为本地估算。
        </p>

        <!-- R8：地图提到指标前面。先看路线长什么样，再看它花多少时间 ——
             原来地图排在评分和叙事之后，第一屏全是数字。
             移动后必须确认 Leaflet 还能框住两条线：容器在挂载时高度不为 0，
             MapView 自己在 route 变化后调 invalidateSize + fitBounds。 -->
        <MapView
          :route="route"
          :baseline-route="baselineRoute"
          :pois="pois"
          :active-poi-index="activePoiIndex"
          @poi-click="focusPoi"
        />

        <!-- R5：「换掉了什么」并进指标格。原来它是下面一块独立的对比区，
             和这四个格子讲的是同一件事，同一屏印两遍同样的数字。现在原值是
             小字压在大字上面（`原 6.9 公里` / `7.7 公里`），差值也在小字里。
             hasComparison 为假时 baseline/delta 全是空串，格子回到原样。 -->
        <div class="result__tiles">
          <StatTile
            label="基准时长"
            :value="baselineMinutes"
            unit="分钟"
            color="ink"
            hint="最快路线预计用时"
          />
          <StatTile
            label="额外时间"
            :value="detourTile.value"
            :unit="detourTile.unit"
            color="red"
            :hint="detourTile.hint"
          />
          <StatTile
            label="总计"
            :value="totalMinutes"
            unit="分钟"
            color="paper"
            hint="基准加绕行"
            :baseline="tileCompare.duration.baseline"
            :delta="tileCompare.duration.delta"
          />
          <!-- T3：label 写清是谁的距离。原来只写「全程距离」，看不出是基准的还是推荐的 -->
          <StatTile
            label="推荐路线距离"
            :value="distance"
            color="blue"
            hint="含绕行的全程长度"
            :baseline="tileCompare.distance.baseline"
            :delta="tileCompare.distance.delta"
          />
        </div>

        <div class="result__meter bh-card bh-card--flat">
          <ScoreMeter :score="props.result?.score" />
          <p class="result__meter-note">
            评分越高代表沿途探索价值越大，同时已扣除绕行时间的代价。当前 {{ score }} 分。
          </p>
        </div>

        <!-- T4：结构化理由在上，叙事文案在下收尾 -->
        <NarrativeBlock
          :narrative="narrative"
          :mode-label="modeInfo.label"
          :reasons="reasons"
          :degraded-note="degradedNote"
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
              :aria-pressed="feedbackState === 'liked' ? 'true' : 'false'"
              @click="feedback(true)"
            >
              还不错
            </button>
            <button
              type="button"
              class="bh-btn"
              :class="{ 'bh-btn--danger': feedbackState === 'disliked' }"
              :aria-pressed="feedbackState === 'disliked' ? 'true' : 'false'"
              @click="feedback(false)"
            >
              一般
            </button>
            <!-- T8-4：文字确认。aria-live 让读屏也能听到，不只是按钮变色 -->
            <p v-if="feedbackNote" class="result__feedback-note" role="status" aria-live="polite">
              {{ feedbackNote }}
            </p>
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

/* R7：宽度锁住。文案在「重新规划」和「重新规划中…」之间切换，
   不锁的话进行态一来按钮变宽，右边界跟着抽动一下。 */
.result__replan {
  flex: 0 0 auto;
  min-width: 7.5rem;
}

.result__replan[disabled] {
  cursor: progress;
}

/* ---------- S3 模式切换 ---------- */

.result__head-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--bh-3);
}

.result__modes {
  display: flex;
  gap: var(--bh-2);
}

/* 方块按钮，和首页那套模式卡同一个语言（硬边、无圆角、选中态位移投影），
   只是结果页地方窄，压成只有 label 的小方块。 */
.result__mode-btn {
  display: grid;
  place-items: center;
  min-width: 3.25rem;
  padding: var(--bh-2) var(--bh-3);
  border: var(--bh-line) solid var(--bh-ink);
  border-radius: 0;
  background: var(--bh-white);
  color: var(--bh-ink);
  font-size: var(--bh-text-sm);
  transition: transform var(--bh-transition), box-shadow var(--bh-transition),
    background-color var(--bh-transition), color var(--bh-transition);
}

.result__mode-btn:hover:not(:disabled):not(.result__mode-btn--active) {
  transform: translate(-2px, -2px);
  box-shadow: var(--bh-shadow-sm);
}

.result__mode-btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.result__mode-btn--active {
  transform: translate(-2px, -2px);
  box-shadow: var(--bh-shadow-sm);
}

.result__mode-btn--blue.result__mode-btn--active {
  background: var(--bh-blue);
  color: var(--bh-white);
}

.result__mode-btn--red.result__mode-btn--active {
  background: var(--bh-red);
  color: var(--bh-white);
}

.result__mode-btn--yellow.result__mode-btn--active {
  background: var(--bh-yellow);
  color: var(--bh-ink);
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

/* R5：这里原本有 `.compare*` 一整套样式（独立对比块的标题、两行色块图例、
   数值与差值）。那块已并进指标格，色块图例的职责由地图自己的 `.map__legend`
   承担 —— 图上的线和图例本来就在同一个组件里，不需要在别处再复刻一份线型。 */

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

/* T8-4：确认文案。占满整行（flex-basis 100%）换到按钮下方，
   免得挤在按钮旁边把两个按钮推出对齐线 —— 窄屏上尤其明显。 */
.result__feedback-note {
  flex: 1 0 100%;
  padding: var(--bh-1) var(--bh-2);
  border-left: var(--bh-line-thick) solid var(--bh-yellow);
  background: var(--bh-paper-2);
  font-size: var(--bh-text-xs);
  color: var(--bh-ink);
  overflow-wrap: anywhere;
}

@media (max-width: 720px) {
  .result__head {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>
