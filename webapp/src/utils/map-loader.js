export function loadAmapScript() {
  if (typeof window === 'undefined') {
    return Promise.resolve()
  }

  return new Promise((resolve, reject) => {
    if (window.AMap) {
      resolve()
      return
    }

    const script = document.createElement('script')
    script.src = 'https://webapi.amap.com/maps?v=2.0&key=YOUR_AMAP_KEY&plugin=AMap.PlaceSearch'
    script.onload = resolve
    script.onerror = () => reject(new Error('Failed to load AMap script'))
    document.head.appendChild(script)
  })
}
