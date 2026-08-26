<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
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
  pois: { type: Array, default: () => [] },
  activePoiIndex: { type: Number, default: -1 },
  height: { type: String, default: '440px' },
})

const emit = defineEmits(['poi-click'])

const container = ref(null)
const failed = ref(false)

let map = null
let casingLayer = null
let routeLayer = null
const markers = []

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
}

function escapeHtml(text) {
  return String(text ?? '').replace(/[&<>"']/g, (char) => {
    const map = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }
    return map[char]
  })
}

function renderRouteAndPois() {
  if (!map) return
  clearLayers()

  const latlngs = decodeRoutePolyline(props.route?.polyline)

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

    const bounds = boundsOf(latlngs)
    if (bounds) call(map, 'fitBounds', bounds, { padding: [44, 44] })

    const start = latlngs[0]
    const end = latlngs[latlngs.length - 1]
    addMarker(start, { icon: iconFor('start', 'A'), title: '起点' }, '<b>起点</b>')
    addMarker(end, { icon: iconFor('end', 'B'), title: '终点' }, '<b>终点</b>')
  }

  props.pois.forEach((poi, index) => {
    const latlng = poiLatLng(poi)
    if (!latlng) return

    const isActive = index === props.activePoiIndex
    const popup = `<b>${escapeHtml(poi.name)}</b><br>${escapeHtml(poi.type)}`
    addMarker(
      latlng,
      {
        icon: iconFor(isActive ? 'poi-active' : 'poi', String(index + 1)),
        title: poi.name || `亮点 ${index + 1}`,
      },
      popup,
      () => emit('poi-click', index),
    )
  })
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
  () => [props.route, props.pois, props.activePoiIndex],
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
    <div
      ref="container"
      class="map-container"
      :style="{ height }"
      role="application"
      aria-label="推荐路线地图"
    ></div>
    <p v-if="failed" class="map__fallback bh-notice bh-notice--warn">
      地图加载失败，可继续查看下方路线信息。
    </p>
    <div class="map__legend">
      <span class="map__legend-item"><i class="map__key map__key--route" />推荐路线</span>
      <span class="map__legend-item"><i class="map__key map__key--start" />起点 / 终点</span>
      <span class="map__legend-item"><i class="map__key map__key--poi" />沿途亮点</span>
    </div>
  </div>
</template>

<style scoped>
.map {
  display: grid;
  gap: var(--bh-2);
}

.map-container {
  width: 100%;
  border: var(--bh-line) solid var(--bh-ink);
  box-shadow: var(--bh-shadow-sm);
  background: var(--bh-paper-2);
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

.map__key--start {
  background: var(--bh-ink);
}

.map__key--poi {
  border-radius: 50%;
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

.bh-pin--poi-active {
  border-radius: 50%;
  background: var(--bh-red);
  color: var(--bh-white);
  transform: scale(1.2);
}
</style>
