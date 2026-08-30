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

/** 探索评分满分。必须等于后端 `SerendipityScorer` 的可达上界
 * （TAG_WEIGHT 3.0 + QUALITY_WEIGHT 4.0 = 7.0，见 backend/app/services/scorer.py）。
 * ScoreMeter 的分母、进度条填充比例、ResultView 的「当前 X 分」共用这一个数，
 * 三处分别写死会出现「7.2/7」那类互相矛盾的读数。 */
export const SCORE_MAX = 7

/** T4：评分公式的三个权重，与 backend/app/services/scorer.py 的
 * `SerendipityScorer` 逐个对应（TAG_WEIGHT / QUALITY_WEIGHT /
 * DETOUR_PENALTY_PER_MINUTE）。结果页要把「这 6.6 分是怎么来的」拆开讲，
 * 就得知道后端是怎么加的。
 *
 * 这是一份**副本**，后端改权重这里不会自动跟着改。所以 ResultView 拆分前
 * 会先验算一遍：拆出来的三项加不回 `score` 就不显示拆分，只报总分 ——
 * 宁可少说一句，也不摆一组加不出总数的数字。
 */
export const SCORE_WEIGHTS = {
  tag: 3.0,
  quality: 4.0,
  detourPenaltyPerMinute: 0.2,
}

/** 各模式的绕行预算（分钟），与 backend/app/routes/api.py 的
 * `MAX_DETOUR_MINUTES` 一致。用来解释「多花的时间在不在你选的额度里」。 */
export const DETOUR_BUDGET = { '+5': 5, '+15': 15, roam: 30 }

export function findMode(value) {
  return EXPLORE_MODES.find((item) => item.value === value) || EXPLORE_MODES[0]
}

/** 与后端 DALIAN_SCENARIOS 对齐的三个演示场景。
 *
 * 坐标必须是 **WGS-84 4 位小数**，且与 backend/app/services/dalian.py 的
 * LANDMARKS 逐字节相同 —— 后端三张兜底表的 key 就是这些坐标串拼出来的，
 * 差一个单位（约 11 米）断网演示就命中不了兜底表，退化成「多花 0 分钟、
 * 0 个亮点、一条两点直线」。改这里必须同步改 dalian.py。
 */
export const DEMO_SCENARIOS = [
  {
    id: 'dut-xinghai',
    originLabel: '大连理工大学',
    destinationLabel: '星海广场',
    origin: '121.5197,38.8856',
    destination: '121.5839,38.8816',
    mode: '+15',
    color: 'red',
  },
  {
    id: 'donggang-laohutan',
    originLabel: '东港',
    destinationLabel: '老虎滩',
    origin: '121.6785,38.9287',
    destination: '121.6701,38.8783',
    mode: 'roam',
    color: 'blue',
  },
  {
    id: 'xianlu-fujiazhuang',
    originLabel: '西安路',
    destinationLabel: '傅家庄',
    origin: '121.5825,38.9136',
    destination: '121.6161,38.8658',
    mode: '+5',
    color: 'yellow',
  },
]

/** 常用地点，输入框无联想接口时作为快捷选择。
 * PlaceInput.choose() 优先回填 option.location，所以这里的坐标会直接
 * 变成请求参数，同样必须是 WGS-84。前六条与 dalian.py 对齐。
 */
export const DALIAN_LANDMARKS = [
  { name: '大连理工大学', location: '121.5197,38.8856' },
  { name: '星海广场', location: '121.5839,38.8816' },
  { name: '东港商务区', location: '121.6785,38.9287' },
  { name: '老虎滩海洋公园', location: '121.6701,38.8783' },
  { name: '西安路', location: '121.5825,38.9136' },
  { name: '傅家庄公园', location: '121.6161,38.8658' },
  { name: '大连火车站', location: '121.6271,38.9189' },
  { name: '中山广场', location: '121.6385,38.9198' },
]

/** 地图默认中心（大连） */
export const MAP_CENTER = { lng: 121.599, lat: 38.897 }
export const MAP_ZOOM = 12
