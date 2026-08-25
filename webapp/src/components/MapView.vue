<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import L from '../utils/leaflet.js'

const props = defineProps({
  route: {
    type: Object,
    default: null,
  },
  pois: {
    type: Array,
    default: () => [],
  },
})

const container = ref(null)
let map = null
let routeLayer = null
const poiMarkers = []

function initMap() {
  if (!container.value || map) return

  map = L.map(container.value).setView([38.918, 121.601], 12)
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    attribution: '&copy; OpenStreetMap contributors',
  }).addTo(map)

  renderRouteAndPois()
}

function renderRouteAndPois() {
  if (!map) return

  if (routeLayer) {
    map.removeLayer(routeLayer)
    routeLayer = null
  }

  poiMarkers.forEach((marker) => map.removeLayer(marker))
  poiMarkers.length = 0

  const polyline = props.route?.polyline
  if (polyline) {
    const latlngs = polyline
      .split(';')
      .map((point) => point.split(','))
      .filter(([lng, lat]) => lng && lat)
      .map(([lng, lat]) => [Number(lat), Number(lng)])

    if (latlngs.length) {
      routeLayer = L.polyline(latlngs, { color: '#2563eb', weight: 5, opacity: 0.9 }).addTo(map)
      map.fitBounds(routeLayer.getBounds(), { padding: [40, 40] })
    }
  }

  props.pois.forEach((poi) => {
    const [lng, lat] = String(poi.location || '').split(',').map(Number)
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) return

    const marker = L.marker([lat, lng]).addTo(map)
    marker.bindPopup(`<b>${poi.name}</b><br>${poi.type}`)
    poiMarkers.push(marker)
  })
}

onMounted(() => {
  initMap()
})

watch(
  () => [props.route, props.pois],
  () => {
    renderRouteAndPois()
  }
)

onBeforeUnmount(() => {
  poiMarkers.forEach((marker) => {
    if (map) map.removeLayer(marker)
  })
  poiMarkers.length = 0

  if (routeLayer && map) map.removeLayer(routeLayer)
  routeLayer = null

  if (map) {
    map.remove()
    map = null
  }
})
</script>

<template>
  <div ref="container" class="map-container"></div>
</template>

<style scoped>
.map-container {
  height: 420px;
  width: 100%;
  border-radius: 12px;
  overflow: hidden;
  border: 1px solid #e5e7eb;
}
</style>
