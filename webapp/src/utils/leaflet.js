import L from 'leaflet'
import markerIcon from 'leaflet/dist/images/marker-icon.png'
import markerIcon2x from 'leaflet/dist/images/marker-icon-2x.png'
import markerShadow from 'leaflet/dist/images/marker-shadow.png'

/**
 * Leaflet 默认图标在打包后会因相对路径失效，这里显式绑定资源。
 * MapView 主要使用 divIcon，此处只是兜底路径，保证退化时仍能看到标记。
 */
if (L?.Icon?.Default) {
  delete L.Icon.Default.prototype._getIconUrl
  L.Icon.Default.mergeOptions({
    iconUrl: markerIcon,
    iconRetinaUrl: markerIcon2x,
    shadowUrl: markerShadow,
  })
}

export default L
