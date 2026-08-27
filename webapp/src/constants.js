/**
 * 探索模式与演示场景。
 * mode 取值必须与后端 route_engine / narrative 中的 key 一致：'+5' | '+15' | 'roam'
 */

export const EXPLORE_MODES = [
  {
    value: '+5',
    label: '+5',
    title: '顺手一绕',
    caption: '最多多花 5 分钟',
    description: '在几乎不耽误行程的前提下，挑一个顺路的小惊喜。',
    color: 'blue',
  },
  {
    value: '+15',
    label: '+15',
    title: '值得一趟',
    caption: '愿意多花 15 分钟',
    description: '为一处更好的风景或小店，接受一段明显的绕行。',
    color: 'red',
  },
  {
    value: 'roam',
    label: '漫游',
    title: '随便走走',
    caption: '不赶时间',
    description: '把最短路径放一边，优先探索价值高的路线。',
    color: 'yellow',
  },
]

export const DEFAULT_MODE = '+5'

export function findMode(value) {
  return EXPLORE_MODES.find((item) => item.value === value) || EXPLORE_MODES[0]
}

/** 与后端 DALIAN_SCENARIOS 对齐的三个演示场景 */
export const DEMO_SCENARIOS = [
  {
    id: 'dut-xinghai',
    originLabel: '大连理工大学',
    destinationLabel: '星海广场',
    origin: '121.6068,38.9180',
    destination: '121.5854,38.9325',
    mode: '+15',
    color: 'red',
  },
  {
    id: 'donggang-laohutan',
    originLabel: '东港',
    destinationLabel: '老虎滩',
    origin: '121.6281,38.9329',
    destination: '121.6542,38.9337',
    mode: 'roam',
    color: 'blue',
  },
  {
    id: 'xianlu-fujiazhuang',
    originLabel: '西安路',
    destinationLabel: '傅家庄',
    origin: '121.5899,38.9148',
    destination: '121.6075,38.9094',
    mode: '+5',
    color: 'yellow',
  },
]

/** 常用地点，输入框无联想接口时作为快捷选择 */
export const DALIAN_LANDMARKS = [
  { name: '大连理工大学', location: '121.6068,38.9180' },
  { name: '星海广场', location: '121.5854,38.9325' },
  { name: '东港商务区', location: '121.6281,38.9329' },
  { name: '老虎滩海洋公园', location: '121.6542,38.9337' },
  { name: '西安路', location: '121.5899,38.9148' },
  { name: '傅家庄公园', location: '121.6075,38.9094' },
  { name: '大连火车站', location: '121.6349,38.9223' },
  { name: '中山广场', location: '121.6428,38.9186' },
]

/** 地图默认中心（大连） */
export const MAP_CENTER = { lng: 121.601, lat: 38.918 }
export const MAP_ZOOM = 12
