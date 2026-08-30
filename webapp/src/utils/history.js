/**
 * 最近查询记录，存 localStorage。
 * 只做演示便利，读写全部包 try/catch：隐私模式或 SSR 下不能因此崩溃。
 */

const STORAGE_KEY = 'serendipity.history.v1'
const MAX_ITEMS = 5

function normalize(value) {
  return String(value ?? '').trim().toLocaleLowerCase('zh-CN')
}

/** 同一路线可能来自两条入口：手输时 origin/destination 是地名，快速体验或
 * 下拉选择时它们是坐标、地名放在 *Label。界面最后都显示地名，所以去重也要
 * 按同一套可见身份判断；否则用户会看到两条文字完全相同的历史记录。 */
function entryKey(entry) {
  const origin = normalize(entry?.originLabel || entry?.origin)
  const destination = normalize(entry?.destinationLabel || entry?.destination)
  return `${origin}\u0000${destination}\u0000${normalize(entry?.mode)}`
}

function dedupe(items) {
  const seen = new Set()
  return items.filter((item) => {
    const key = entryKey(item)
    if (seen.has(key)) return false
    seen.add(key)
    return true
  })
}

function storage() {
  try {
    if (typeof globalThis.localStorage === 'undefined') return null
    return globalThis.localStorage
  } catch {
    return null
  }
}

export function loadHistory() {
  const store = storage()
  if (!store) return []

  try {
    const raw = store.getItem(STORAGE_KEY)
    if (!raw) return []
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return dedupe(
      parsed.filter(
        (item) =>
          item && typeof item.origin === 'string' && typeof item.destination === 'string',
      ),
    ).slice(0, MAX_ITEMS)
  } catch {
    return []
  }
}

export function pushHistory(entry) {
  const store = storage()
  const current = loadHistory()

  if (!entry?.origin || !entry?.destination) return current

  const key = entryKey(entry)
  const deduped = current.filter((item) => entryKey(item) !== key)

  const next = [{ ...entry, at: Date.now() }, ...deduped].slice(0, MAX_ITEMS)

  if (store) {
    try {
      store.setItem(STORAGE_KEY, JSON.stringify(next))
    } catch {
      // 写入失败（配额 / 隐私模式）忽略，内存里的结果照常返回
    }
  }

  return next
}

export function clearHistory() {
  const store = storage()
  if (store) {
    try {
      store.removeItem(STORAGE_KEY)
    } catch {
      // 忽略
    }
  }
  return []
}
