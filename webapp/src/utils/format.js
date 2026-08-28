/**
 * 展示层格式化工具。后端字段可能是字符串、数字或缺失，这里统一兜底。
 */

export function toNumber(value) {
  if (typeof value === 'number') return Number.isFinite(value) ? value : null
  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number(value)
    return Number.isFinite(parsed) ? parsed : null
  }
  return null
}

/** 分钟：12 -> "12"，缺失 -> "--" */
export function formatMinutes(value) {
  const num = toNumber(value)
  if (num === null) return '--'
  return String(Math.max(0, Math.round(num)))
}

/** 绕行分钟带符号：0 -> "+0"，7 -> "+7" */
export function formatDetour(value) {
  const num = toNumber(value)
  if (num === null) return '--'
  const rounded = Math.round(num)
  return rounded > 0 ? `+${rounded}` : String(rounded)
}

/** 米 -> "1.2 公里" / "320 米" */
export function formatDistance(value) {
  const num = toNumber(value)
  if (num === null) return '--'
  if (num >= 1000) return `${(num / 1000).toFixed(1)} 公里`
  return `${Math.round(num)} 米`
}

/** 评分保留一位小数 */
export function formatScore(value) {
  const num = toNumber(value)
  if (num === null) return '--'
  return num.toFixed(1)
}

/** 秒 -> "21 分钟" / "1 小时 5 分钟" */
export function formatDuration(seconds) {
  const num = toNumber(seconds)
  if (num === null) return '--'
  const minutes = Math.max(0, Math.round(num / 60))
  if (minutes < 60) return `${minutes} 分钟`
  const hours = Math.floor(minutes / 60)
  const rest = minutes % 60
  return rest ? `${hours} 小时 ${rest} 分钟` : `${hours} 小时`
}

/** 评分映射为 0~100 的进度百分比。
 * 默认 max 与 ScoreMeter 一致（后端 scorer 的可达上界 7.0，见 ScoreMeter.vue）。
 * ScoreMeter 总是显式传 props.max，这个默认值只影响别的调用方 ——
 * 留着 10 会让下一个人拿到「最好的结果也只填到 70%」的进度条。 */
export function scoreToPercent(value, max = 7) {
  const num = toNumber(value)
  if (num === null) return 0
  return Math.min(100, Math.max(0, Math.round((num / max) * 100)))
}

/** 三原色循环，用于列表条目上色 */
const CYCLE = ['red', 'blue', 'yellow']

export function colorForIndex(index) {
  const safe = Number.isFinite(index) ? Math.abs(Math.trunc(index)) : 0
  return CYCLE[safe % CYCLE.length]
}

/** 两位数序号：1 -> "01" */
export function ordinal(index) {
  const safe = Number.isFinite(index) ? Math.trunc(index) : 0
  return String(safe + 1).padStart(2, '0')
}
