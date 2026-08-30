<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import L from '../utils/leaflet.js'
import { MAP_CENTER, MAP_ZOOM } from '../constants.js'
import { boundsOf, decodeRoutePolyline, poiLatLng } from '../utils/geo.js'

/**
 * 路线地图。
 * - 路线用双层线：黑色描边 + 彩色主线，贴合包豪斯硬边风格。
 * - 起终点与 POI 用方形 / 圆形标记。
 * - Leaflet 能力按需检测，缺失时静默跳过，保证测试与降级环境不报错。
 */
const props = defineProps({
  route: { type: Object, default: null },
  // P3-4：原本那条路。灰色虚线画在推荐路线下面，「换掉了什么」才看得见。
  // polyline 出后端时已是 WGS-84，直接用，别再转坐标系（会偏约 450 米）。
  baselineRoute: { type: Object, default: null },
  pois: { type: Array, default: () => [] },
  activePoiIndex: { type: Number, default: -1 },
  height: { type: String, default: '440px' },
})

const emit = defineEmits(['poi-click'])

const container = ref(null)
const failed = ref(false)
// T2「地图是死的」第一条：首帧瓦片还没到时，容器是一块纯灰底 —— 看起来像加载失败。
// tilesReady 由 tileLayer 的 load 事件驱动，之前没有人订阅它，所以骨架屏无从谈起。
const tilesReady = ref(false)
// tileerror 是瓦片 404 / 断网的真实信号。以前 failed 只在 L.map 抛异常时才为 true，
// 也就是说「底图一张都没下来」这种最常见的现场故障，界面上没有任何提示。
const tilesFailed = ref(false)

let map = null
let casingLayer = null
let routeLayer = null
const baselineLayers = []
const markers = []
let tileErrors = 0
/** 已经按这个形状取过视野了。POI 点击不改形状，就不该重新 fitBounds ——
 * 否则用户手动放大看某个路口，点一下亮点卡片视野就被拽回全程，地图像不听话。 */
let fittedSignature = ''

/** 基准虚线的两笔：深色描边打底 + 浅色芯，深蓝路线上和浅色底图上都读得出。
 * 两笔必须同 dashArray 同相位，否则芯会错位露出描边，看着像锯齿。 */
const BASELINE_STYLES = [
  { color: '#14100e', weight: 8, opacity: 1, dashArray: '7 9', lineCap: 'butt', lineJoin: 'miter' },
  { color: '#d9d3c9', weight: 4, opacity: 1, dashArray: '7 9', lineCap: 'butt', lineJoin: 'miter' },
]

function has(fn) {
  return typeof L?.[fn] === 'function'
}

function call(target, method, ...args) {
  if (target && typeof target[method] === 'function') return target[method](...args)
  return null
}

/** 用 divIcon 画方块 / 圆点；不支持 divIcon 时退回默认 marker */
function iconFor(kind, label) {
  if (!has('divIcon')) return null
  const size = kind === 'poi' ? 22 : 26
  return L.divIcon({
    className: `bh-pin bh-pin--${kind}`,
    html: `<span class="bh-pin__inner">${label ?? ''}</span>`,
    iconSize: [size, size],
    iconAnchor: [size / 2, size / 2],
  })
}

function addMarker(latlng, options, popupHtml, onClick) {
  if (!has('marker') || !map) return null
  const marker = L.marker(latlng, options)
  call(marker, 'addTo', map)
  if (popupHtml) call(marker, 'bindPopup', popupHtml)
  if (onClick) call(marker, 'on', 'click', onClick)
  markers.push(marker)
  return marker
}

function clearLayers() {
  if (!map) return
  markers.forEach((marker) => call(map, 'removeLayer', marker))
  markers.length = 0

  if (routeLayer) {
    call(map, 'removeLayer', routeLayer)
    routeLayer = null
  }
  if (casingLayer) {
    call(map, 'removeLayer', casingLayer)
    casingLayer = null
  }
  while (baselineLayers.length) {
    call(map, 'removeLayer', baselineLayers.pop())
  }
}

function escapeHtml(text) {
  return String(text ?? '').replace(/[&<>"']/g, (char) => {
    const map = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }
    return map[char]
  })
}

/** 基准与推荐重合时不算「有对比」—— 降级出口两者是同一条，画上去只是一条
 * 被压住的虚线，图例却在说有对比。图例与实际画的线共用这一个判断，
 * 不会出现「图例有、线没有」。
 */
const hasBaselineComparison = computed(
  () =>
    decodeRoutePolyline(props.baselineRoute?.polyline).length > 0 &&
    props.baselineRoute?.polyline !== props.route?.polyline,
)
const hasNearbyPois = computed(() => props.pois.some((poi) => poi?.is_waypoint === false))

function renderRouteAndPois() {
  if (!map) return
  clearLayers()

  const latlngs = decodeRoutePolyline(props.route?.polyline)
  const baselineLatlngs = decodeRoutePolyline(props.baselineRoute?.polyline)
  const baselineDiffers = hasBaselineComparison.value

  if (latlngs.length && has('polyline')) {
    casingLayer = L.polyline(latlngs, {
      color: '#14100e',
      weight: 11,
      opacity: 1,
      lineCap: 'butt',
      lineJoin: 'miter',
    })
    call(casingLayer, 'addTo', map)

    routeLayer = L.polyline(latlngs, {
      color: '#22409a',
      weight: 5,
      opacity: 1,
      lineCap: 'butt',
      lineJoin: 'miter',
    })
    call(routeLayer, 'addTo', map)
  }

  // 基准画在推荐路线「上面」，不是下面。断网演示的基准就是推荐路线抽掉绕行点后
  // 的同一条走廊（三组场景实测 base_only=0，逐点重合），画在 11px 描边底下会被
  // 完全盖住 —— DOM 里虚线在、图例也在，但图上一根都看不见。这种假对比只有截图
  // 能发现，断言查不出来。盖在上面时蓝线从虚线间隙透出来，重合段和绕行段都读得出。
  // 两笔同相位虚线（深色描边 + 浅色芯）是为了在深蓝路线和浅色底图上都能读。
  if (baselineDiffers && has('polyline')) {
    for (const style of BASELINE_STYLES) {
      const layer = L.polyline(baselineLatlngs, style)
      call(layer, 'addTo', map)
      baselineLayers.push(layer)
    }
  }

  if (latlngs.length && has('polyline')) {
    // 视野要同时框住两条线，否则基准绕得更远时会被裁到视野外，
    // 对比图看起来像只有推荐路线那一条。
    //
    // T2：只有「线变了」才重新取视野。watch 是 deep 的，还盯着 pois 和
    // activePoiIndex —— 以前点一下亮点卡片就会重跑 fitBounds，把用户手动
    // 放大 / 拖动的视野拽回全程，操作感像地图不听话。签名相同就跳过。
    const signature = `${props.route?.polyline || ''}|${baselineDiffers ? props.baselineRoute?.polyline || '' : ''}`
    if (signature !== fittedSignature) {
      const bounds = boundsOf(baselineDiffers ? latlngs.concat(baselineLatlngs) : latlngs)
      if (bounds) call(map, 'fitBounds', bounds, { padding: [44, 44] })
      fittedSignature = signature
    }

    const start = latlngs[0]
    const end = latlngs[latlngs.length - 1]
    addMarker(start, { icon: iconFor('start', 'A'), title: '起点' }, '<b>起点</b>')
    addMarker(end, { icon: iconFor('end', 'B'), title: '终点' }, '<b>终点</b>')
  }

  let activeLatLng = null
  props.pois.forEach((poi, index) => {
    const latlng = poiLatLng(poi)
    if (!latlng) return

    const isActive = index === props.activePoiIndex
    const isWaypoint = poi?.is_waypoint !== false
    if (isActive) activeLatLng = latlng
    const popup = `<b>${escapeHtml(poi.name)}</b><br>${escapeHtml(poi.type)}`
    addMarker(
      latlng,
      {
        icon: iconFor(
          isActive
            ? isWaypoint
              ? 'waypoint-active'
              : 'poi-active'
            : isWaypoint
              ? 'waypoint'
              : 'poi',
          String(index + 1),
        ),
        title: poi.name || `亮点 ${index + 1}`,
      },
      popup,
      () => emit('poi-click', index),
    )
  })

  // T2：点亮点卡片必须在图上看得出来。标记本来就会换成红色放大款，
  // 但那个点可能正在视野外 —— 用户点了卡片，图上什么都没动。
  // panTo 只平移不改缩放，所以不会踩掉上面那条「别动用户的缩放」。
  if (activeLatLng) call(map, 'panTo', activeLatLng, { animate: true })
}

function initMap() {
  if (!container.value || map) return

  try {
    map = L.map(container.value, { zoomControl: true, attributionControl: true })
    call(map, 'setView', [MAP_CENTER.lat, MAP_CENTER.lng], MAP_ZOOM)

    if (has('tileLayer')) {
      const tiles = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; OpenStreetMap contributors',
        maxZoom: 19,
      })
      // T2：订阅瓦片事件，界面才能区分「正在加载」「加载完」「下不来」。
      // 以前一个都没订阅，三种状态在屏幕上长得一模一样（一块灰）。
      //
      // 成功信号必须用 tileload（单张加载成功），不能用 load。Leaflet 的 load 是
      // 「这一批都处理完了」，出错的瓦片也算处理完 —— 实测把瓦片全 abort 掉，
      // load 照样触发，于是骨架撤了、错误提示也不出，屏幕上又变回一块灰。
      call(tiles, 'on', 'tileload', () => {
        tilesReady.value = true
        tilesFailed.value = false
      })
      call(tiles, 'on', 'tileerror', () => {
        tileErrors += 1
        // 单张瓦片偶尔失败很常见（OSM 限流），不该马上报错。
        // 连续几张都下不来才算底图真的没了。
        if (tileErrors >= 4 && !tilesReady.value) tilesFailed.value = true
      })
      call(tiles, 'addTo', map)
    }

    renderRouteAndPois()
  } catch {
    // 地图初始化失败（离线 / 无 WebGL / 容器异常）时退化为提示块
    failed.value = true
    map = null
  }
}

onMounted(initMap)

watch(
  () => [props.route, props.baselineRoute, props.pois, props.activePoiIndex],
  () => renderRouteAndPois(),
  { deep: true },
)

onBeforeUnmount(() => {
  clearLayers()
  if (map) {
    call(map, 'remove')
    map = null
  }
})
</script>

<template>
  <div class="map">
    <div class="map__frame" :style="{ height }">
      <div
        ref="container"
        class="map-container"
        role="application"
        aria-label="推荐路线地图"
      ></div>
      <!-- T2：首帧瓦片未到时铺一层网格骨架，不要留一块纯灰 —— 纯灰看起来像坏了。
           pointer-events: none，拖拽缩放照样能用；网格垫在 Leaflet 各 pane 之下，
           所以瓦片下不来时路线和标记仍然读得出（见 map-tiles-blocked 截图）。
           「加载中」的字牌只在真的还在加载时出现：下不来时下面那条黄条已经说清了，
           两处都说反而会被路线压住、互相打架。 -->
      <div v-if="!tilesReady && !failed" class="map__skeleton" aria-hidden="true">
        <div class="map__skeleton-grid" />
        <span v-if="!tilesFailed" class="bh-label map__skeleton-text">底图加载中</span>
      </div>
    </div>
    <p v-if="failed" class="map__fallback bh-notice bh-notice--warn">
      地图加载失败，可继续查看下方路线信息。
    </p>
    <!-- 瓦片下不来时路线仍然画得出（SVG 不依赖底图），所以措辞是「只有底图没了」 -->
    <p v-else-if="tilesFailed" class="map__fallback bh-notice bh-notice--warn">
      底图瓦片加载失败（网络受限），路线与标记仍可查看。
    </p>
    <div class="map__legend">
      <span class="map__legend-item"><i class="map__key map__key--route" />推荐路线</span>
      <span v-if="hasBaselineComparison" class="map__legend-item">
        <i class="map__key map__key--baseline" />原本路线
      </span>
      <span class="map__legend-item"><i class="map__key map__key--start" />起点 / 终点</span>
      <span class="map__legend-item"><i class="map__key map__key--waypoint" />途经点</span>
      <span v-if="hasNearbyPois" class="map__legend-item"><i class="map__key map__key--poi" />附近亮点</span>
    </div>
  </div>
</template>

<style scoped>
.map {
  display: grid;
  gap: var(--bh-2);
}

/* 骨架要盖在地图上，所以外面套一层定位容器；边框和投影留在这一层，
   免得骨架把边框压住 */
.map__frame {
  position: relative;
  width: 100%;
  border: var(--bh-line) solid var(--bh-ink);
  box-shadow: var(--bh-shadow-sm);
  background: var(--bh-paper-2);
}

.map-container {
  width: 100%;
  height: 100%;
  background: var(--bh-paper-2);
}

/* 垫在 Leaflet 之下（Leaflet 的 pane 从 z-index 200 起），这样瓦片没来时
   看到的是网格底，而路线、标记、缩放控件都照常压在上面。
   盖在上面会把线和标记糊掉 —— 断网演示时那才是真的「地图是死的」。 */
.map__skeleton {
  position: absolute;
  inset: 0;
  z-index: 1;
  display: grid;
  place-items: center;
  /* 不吃事件：骨架还在的时候地图也能拖能缩 */
  pointer-events: none;
  background: var(--bh-paper-2);
}

/* 用底图网格暗示「这里是地图」，比一块纯灰读得懂 */
.map__skeleton-grid {
  position: absolute;
  inset: 0;
  opacity: 0.55;
  background-image:
    repeating-linear-gradient(0deg, var(--bh-ink) 0 1px, transparent 1px 48px),
    repeating-linear-gradient(90deg, var(--bh-ink) 0 1px, transparent 1px 48px);
}

.map__skeleton-text {
  position: relative;
  padding: var(--bh-2) var(--bh-3);
  border: 2px solid var(--bh-ink);
  background: var(--bh-white);
  color: var(--bh-ink);
}

.map__legend {
  display: flex;
  flex-wrap: wrap;
  gap: var(--bh-4);
  font-size: var(--bh-text-xs);
  font-weight: 700;
  letter-spacing: var(--bh-track-label);
  text-transform: uppercase;
  color: var(--bh-ink-soft);
}

.map__legend-item {
  display: inline-flex;
  align-items: center;
  gap: var(--bh-2);
}

.map__key {
  display: inline-block;
  width: 16px;
  height: 16px;
  border: 2px solid var(--bh-ink);
}

.map__key--route {
  height: 6px;
  background: var(--bh-blue);
}

/* 与地图上的虚线同色同形（深色描边 + 浅色芯），图例才读得懂 */
.map__key--baseline {
  height: 8px;
  border: 0;
  background:
    repeating-linear-gradient(90deg, #d9d3c9 0 7px, transparent 7px 16px) center / 100% 4px
      no-repeat,
    repeating-linear-gradient(90deg, #14100e 0 7px, transparent 7px 16px) center / 100% 8px
      no-repeat;
}

.map__key--start {
  background: var(--bh-ink);
}

.map__key--poi {
  border-radius: 50%;
  background: var(--bh-yellow);
}

.map__key--waypoint {
  background: var(--bh-red);
}
</style>

<style>
/* 非 scoped：Leaflet 的 divIcon 挂在地图 pane 上，作用域样式无法命中 */
.bh-pin {
  display: grid;
  place-items: center;
  border: 3px solid var(--bh-ink);
  background: var(--bh-white);
  font-family: var(--bh-font-mono);
  font-size: 11px;
  font-weight: 700;
  color: var(--bh-ink);
  box-shadow: 3px 3px 0 rgba(20, 16, 14, 0.9);
}

.bh-pin--start {
  background: var(--bh-ink);
  color: var(--bh-paper);
}

.bh-pin--end {
  background: var(--bh-blue);
  color: var(--bh-white);
}

.bh-pin--poi {
  border-radius: 50%;
  background: var(--bh-yellow);
}

.bh-pin--waypoint {
  background: var(--bh-red);
  color: var(--bh-white);
}

.bh-pin--poi-active {
  border-radius: 50%;
  background: var(--bh-red);
  color: var(--bh-white);
  transform: scale(1.2);
}

.bh-pin--waypoint-active {
  background: var(--bh-red);
  color: var(--bh-white);
  transform: scale(1.2);
}
</style>
