/**
 * 最近查询记录，存 localStorage。
 * 只做演示便利，读写全部包 try/catch：隐私模式或 SSR 下不能因此崩溃。
 */

const STORAGE_KEY = 'serendipity.history.v1'
const MAX_ITEMS = 5

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
    return parsed
      .filter((item) => item && typeof item.origin === 'string' && typeof item.destination === 'string')
      .slice(0, MAX_ITEMS)
  } catch {
    return []
  }
}

export function pushHistory(entry) {
  const store = storage()
  const current = loadHistory()

  if (!entry?.origin || !entry?.destination) return current

  const deduped = current.filter(
    (item) =>
      !(
        item.origin === entry.origin &&
        item.destination === entry.destination &&
        item.mode === entry.mode
      ),
  )

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
