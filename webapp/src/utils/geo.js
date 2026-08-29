import { decodeAmapPolyline } from './polyline.js'

const COORD_RE = /^\s*-?\d{1,3}(\.\d+)?\s*,\s*-?\d{1,2}(\.\d+)?\s*$/
const PI = Math.PI
const AXIS = 6378245.0
const OFFSET = 0.00669342162296594323

/** 判断输入是否是 "lng,lat" 形式的坐标串 */
export function isCoordString(value) {
  return typeof value === 'string' && COORD_RE.test(value)
}

/** "121.6068,38.9180" -> { lng, lat }；非法返回 null */
export function parseCoord(value) {
  if (!isCoordString(value)) return null
  const [lng, lat] = String(value)
    .split(',')
    .map((part) => Number(part.trim()))
  if (!Number.isFinite(lng) || !Number.isFinite(lat)) return null
  if (Math.abs(lng) > 180 || Math.abs(lat) > 90) return null
  return { lng, lat }
}

/**
 * 把后端返回的 polyline 解析为 Leaflet 需要的 [lat, lng] 数组。
 * 同时支持两种格式：
 *  - 高德明文串 "lng,lat;lng,lat"
 *  - 高德/Google 编码折线（无分号且含非坐标字符时按编码串处理）
 */
export function decodeRoutePolyline(polyline, options = {}) {
  if (!polyline || typeof polyline !== 'string') return []
  const toLeafletLatLng = ([lng, lat]) => {
    const point = normalizeForMap({ lng, lat }, options.coordinateSystem)
    return [point.lat, point.lng]
  }

  if (polyline.includes(';') || polyline.includes(',')) {
    return polyline
      .split(';')
      .map((chunk) => chunk.trim())
      .filter(Boolean)
      .map((chunk) => chunk.split(',').map((part) => Number(part)))
      .filter(([lng, lat]) => Number.isFinite(lng) && Number.isFinite(lat))
      .map(toLeafletLatLng)
  }

  try {
    return decodeAmapPolyline(polyline)
      .filter(([lng, lat]) => Number.isFinite(lng) && Number.isFinite(lat))
      .map(toLeafletLatLng)
  } catch {
    return []
  }
}

/** 从 [lat,lng] 数组算出 [[南,西],[北,东]] 包围盒 */
export function boundsOf(latlngs) {
  if (!Array.isArray(latlngs) || latlngs.length === 0) return null
  let south = Infinity
  let west = Infinity
  let north = -Infinity
  let east = -Infinity

  latlngs.forEach(([lat, lng]) => {
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) return
    south = Math.min(south, lat)
    north = Math.max(north, lat)
    west = Math.min(west, lng)
    east = Math.max(east, lng)
  })

  if (!Number.isFinite(south) || !Number.isFinite(west)) return null
  return [
    [south, west],
    [north, east],
  ]
}

/** POI 的 location 字段 -> [lat, lng]；用于打点 */
export function poiLatLng(poi) {
  const point = parseCoord(String(poi?.location ?? ''))
  const mapPoint = normalizeForMap(point, poi?.coordinate_system)
  return mapPoint ? [mapPoint.lat, mapPoint.lng] : null
}

export function normalizeForMap(point, coordinateSystem = 'wgs84') {
  if (!point) return null
  if (String(coordinateSystem).toLowerCase() !== 'gcj02') return point
  return gcj02ToWgs84(point)
}

function gcj02ToWgs84({ lng, lat }) {
  if (outOfChina(lng, lat)) return { lng, lat }

  const dLat = transformLat(lng - 105.0, lat - 35.0)
  const dLng = transformLng(lng - 105.0, lat - 35.0)
  const radLat = (lat / 180.0) * PI
  let magic = Math.sin(radLat)
  magic = 1 - OFFSET * magic * magic
  const sqrtMagic = Math.sqrt(magic)
  const mgLat = lat + (dLat * 180.0) / (((AXIS * (1 - OFFSET)) / (magic * sqrtMagic)) * PI)
  const mgLng = lng + (dLng * 180.0) / ((AXIS / sqrtMagic) * Math.cos(radLat) * PI)

  return {
    lng: lng * 2 - mgLng,
    lat: lat * 2 - mgLat,
  }
}

function outOfChina(lng, lat) {
  return lng < 72.004 || lng > 137.8347 || lat < 0.8293 || lat > 55.8271
}

function transformLat(x, y) {
  let ret = -100.0 + 2.0 * x + 3.0 * y + 0.2 * y * y + 0.1 * x * y + 0.2 * Math.sqrt(Math.abs(x))
  ret += ((20.0 * Math.sin(6.0 * x * PI) + 20.0 * Math.sin(2.0 * x * PI)) * 2.0) / 3.0
  ret += ((20.0 * Math.sin(y * PI) + 40.0 * Math.sin((y / 3.0) * PI)) * 2.0) / 3.0
  ret += ((160.0 * Math.sin((y / 12.0) * PI) + 320 * Math.sin((y * PI) / 30.0)) * 2.0) / 3.0
  return ret
}

function transformLng(x, y) {
  let ret = 300.0 + x + 2.0 * y + 0.1 * x * x + 0.1 * x * y + 0.1 * Math.sqrt(Math.abs(x))
  ret += ((20.0 * Math.sin(6.0 * x * PI) + 20.0 * Math.sin(2.0 * x * PI)) * 2.0) / 3.0
  ret += ((20.0 * Math.sin(x * PI) + 40.0 * Math.sin((x / 3.0) * PI)) * 2.0) / 3.0
  ret += ((150.0 * Math.sin((x / 12.0) * PI) + 300.0 * Math.sin((x / 30.0) * PI)) * 2.0) / 3.0
  return ret
}
