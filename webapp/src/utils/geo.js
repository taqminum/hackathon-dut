import { decodeAmapPolyline } from './polyline.js'

const COORD_RE = /^\s*-?\d{1,3}(\.\d+)?\s*,\s*-?\d{1,2}(\.\d+)?\s*$/

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
export function decodeRoutePolyline(polyline) {
  if (!polyline || typeof polyline !== 'string') return []

  if (polyline.includes(';') || polyline.includes(',')) {
    return polyline
      .split(';')
      .map((chunk) => chunk.trim())
      .filter(Boolean)
      .map((chunk) => chunk.split(',').map((part) => Number(part)))
      .filter(([lng, lat]) => Number.isFinite(lng) && Number.isFinite(lat))
      .map(([lng, lat]) => [lat, lng])
  }

  try {
    return decodeAmapPolyline(polyline)
      .filter(([lng, lat]) => Number.isFinite(lng) && Number.isFinite(lat))
      .map(([lng, lat]) => [lat, lng])
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
  // 后端用 navigation_location（POI 的可到达入口）规划途经路线。标记也必须使用
  // 同一个点，否则视觉上会像路线没有经过第二站。
  const point = parseCoord(String(poi?.navigation_location ?? poi?.location ?? ''))
  return point ? [point.lat, point.lng] : null
}
