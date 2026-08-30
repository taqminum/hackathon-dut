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

/** 评分保留一位小数。
 * T5：max 传入时把显示值也 clamp 住。以前只有进度条 clamp（scoreToPercent），
 * 数字直接显示原值，于是越界数据会显示成 `7.2/7` —— 条填满了，数字却比分母大，
 * 自相矛盾。后端上界确实是 7.0，越界只可能来自假数据或以后改权重忘了同步，
 * 两种情况都不该让界面自我否定。 */
export function formatScore(value, max = null) {
  const num = toNumber(value)
  if (num === null) return '--'
  const capped = max === null ? num : Math.min(num, max)
  return Math.max(0, capped).toFixed(1)
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

/** 高德类型形如 "餐饮服务;咖啡厅;咖啡厅"，取最后一段更具体。
 * PoiCard 的标签和结果页的推荐理由都用它，两处必须叫同一个名字 ——
 * 卡片上写「咖啡厅」而理由里写「餐饮服务;咖啡厅;咖啡厅」会像是两个地方。 */
export function poiTypeLabel(value) {
  const raw = String(value || '').trim()
  if (!raw) return ''
  const parts = raw.split(/[;|]/).filter(Boolean)
  return parts.length ? parts[parts.length - 1] : raw
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
