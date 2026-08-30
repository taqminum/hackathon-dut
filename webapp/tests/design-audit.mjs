/**
 * 设计与可用性审计：读取真实浏览器里的计算样式，验证包豪斯风格约束与布局健康度。
 * 需要先启动真实后端与 Vite。
 * 用法： node tests/design-audit.mjs [baseUrl]
 */
import { chromium } from 'playwright'

const BASE = process.argv[2] || 'http://localhost:5173'
const problems = []

function check(label, condition, detail = '') {
  if (condition) {
    console.log(`  ok   ${label}`)
  } else {
    console.log(`  FAIL ${label}${detail ? ` — ${detail}` : ''}`)
    problems.push(label)
  }
}

/** 相对亮度，用于对比度计算 */
function luminance([r, g, b]) {
  const channel = (value) => {
    const v = value / 255
    return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4
  }
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)
}

function contrast(fg, bg) {
  const a = luminance(fg)
  const b = luminance(bg)
  const [light, dark] = a > b ? [a, b] : [b, a]
  return (light + 0.05) / (dark + 0.05)
}

function parseRgb(value) {
  const match = String(value).match(/rgba?\(([^)]+)\)/)
  if (!match) return null
  const parts = match[1].split(',').map((n) => parseFloat(n))
  return [parts[0], parts[1], parts[2]]
}

const browser = await chromium.launch()

try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } })
  await page.goto(BASE, { waitUntil: 'networkidle' })

  console.log('\n[包豪斯风格约束]')

  // 硬边：不允许出现圆角（圆形装饰件与地图控件除外）
  const radii = await page.evaluate(() => {
    const allowed = ['bh-dot', 'shape--circle', 'poi__star', 'head__dot', 'bh-pin--poi', 'meter__cell']
    const bad = []
    document.querySelectorAll('button, input, .bh-card, .tile, .demo, .poi, .bh-notice').forEach((el) => {
      if (allowed.some((cls) => el.classList.contains(cls))) return
      const radius = getComputedStyle(el).borderRadius
      if (radius && radius !== '0px') bad.push(`${el.className}:${radius}`)
    })
    return bad
  })
  check('无圆角（硬边）', radii.length === 0, radii.slice(0, 4).join(', '))

  // 粗描边：卡片与按钮都应有可见边框
  const borders = await page.evaluate(() => {
    const bad = []
    document.querySelectorAll('.bh-card, .tile, .demo, .bh-btn').forEach((el) => {
      const width = parseFloat(getComputedStyle(el).borderTopWidth)
      if (!Number.isFinite(width) || width < 2) bad.push(`${el.className}:${width}px`)
    })
    return bad
  })
  check('描边不低于 2px', borders.length === 0, borders.slice(0, 4).join(', '))

  // 三原色确实用上了
  const palette = await page.evaluate(() => {
    const root = getComputedStyle(document.documentElement)
    return {
      red: root.getPropertyValue('--bh-red').trim(),
      blue: root.getPropertyValue('--bh-blue').trim(),
      yellow: root.getPropertyValue('--bh-yellow').trim(),
    }
  })
  check('三原色令牌已定义', !!(palette.red && palette.blue && palette.yellow), JSON.stringify(palette))

  console.log('\n[布局健康度]')

  for (const [name, width] of [['桌面', 1280], ['平板', 768], ['手机', 390]]) {
    await page.setViewportSize({ width, height: 900 })
    await page.waitForTimeout(250)
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    )
    check(`${name}宽度无横向溢出`, overflow <= 1, `溢出 ${overflow}px`)
  }

  await page.setViewportSize({ width: 390, height: 844 })
  await page.waitForTimeout(250)

  // 触摸目标尺寸
  const smallTargets = await page.evaluate(() => {
    const bad = []
    document.querySelectorAll('button').forEach((el) => {
      const rect = el.getBoundingClientRect()
      if (rect.width === 0 && rect.height === 0) return
      if (rect.height < 32) bad.push(`${el.className || el.tagName}:${Math.round(rect.height)}px`)
    })
    return bad
  })
  check('手机端按钮高度不低于 32px', smallTargets.length === 0, smallTargets.slice(0, 4).join(', '))

  console.log('\n[可访问性]')

  await page.setViewportSize({ width: 1280, height: 900 })
  await page.waitForTimeout(200)

  // 正文对比度
  const samples = await page.evaluate(() => {
    const picks = ['.home__lede', '.mode__hint', '.demo__route', '.home__section-title']
    return picks
      .map((selector) => {
        const el = document.querySelector(selector)
        if (!el) return null
        const style = getComputedStyle(el)
        let node = el
        let background = 'rgba(0, 0, 0, 0)'
        while (node && background === 'rgba(0, 0, 0, 0)') {
          background = getComputedStyle(node).backgroundColor
          node = node.parentElement
        }
        return { selector, color: style.color, background, size: style.fontSize }
      })
      .filter(Boolean)
  })

  samples.forEach((sample) => {
    const fg = parseRgb(sample.color)
    const bg = parseRgb(sample.background)
    if (!fg || !bg) return
    const ratio = contrast(fg, bg)
    const size = parseFloat(sample.size)
    const threshold = size >= 18.66 ? 3 : 4.5
    check(
      `${sample.selector} 对比度达标`,
      ratio >= threshold,
      `${ratio.toFixed(2)}:1（需 ${threshold}:1，${size}px）`,
    )
  })

  // 表单标签绑定
  const unlabelled = await page.evaluate(() => {
    const bad = []
    document.querySelectorAll('input').forEach((el) => {
      const id = el.getAttribute('id')
      const hasLabel = id && document.querySelector(`label[for="${id}"]`)
      if (!hasLabel && !el.getAttribute('aria-label')) bad.push(el.outerHTML.slice(0, 60))
    })
    return bad
  })
  check('所有输入框都有关联标签', unlabelled.length === 0, unlabelled.join(' | '))

  // 图标按钮有可读名称
  const namelessButtons = await page.evaluate(() => {
    const bad = []
    document.querySelectorAll('button').forEach((el) => {
      const text = (el.textContent || '').trim()
      if (!text && !el.getAttribute('aria-label')) bad.push(el.className)
    })
    return bad
  })
  check('图标按钮有无障碍名称', namelessButtons.length === 0, namelessButtons.join(', '))

  // 键盘焦点可见
  await page.keyboard.press('Tab')
  await page.keyboard.press('Tab')
  const focusVisible = await page.evaluate(() => {
    const el = document.activeElement
    if (!el || el === document.body) return false
    const style = getComputedStyle(el)
    return style.outlineStyle !== 'none' || style.boxShadow !== 'none'
  })
  check('键盘焦点有可见指示', focusVisible)

  // 语言与标题层级
  check('文档语言为中文', (await page.getAttribute('html', 'lang')) === 'zh-CN')
  check('存在唯一 h1', (await page.locator('h1').count()) === 1)

  // 深色底上的小字：页脚与顶栏状态徽标同样容易因 opacity 掉到 AA 以下
  const darkSurfaces = await page.evaluate(() => {
    const picks = ['.app__foot-note', '.app__foot-inner .bh-label', '.head__status', '.demo__mode']
    return picks
      .map((selector) => {
        const el = document.querySelector(selector)
        if (!el) return null
        const style = getComputedStyle(el)
        let node = el
        let background = 'rgba(0, 0, 0, 0)'
        while (node && background === 'rgba(0, 0, 0, 0)') {
          background = getComputedStyle(node).backgroundColor
          node = node.parentElement
        }
        return {
          selector,
          color: style.color,
          background,
          size: style.fontSize,
          opacity: style.opacity,
        }
      })
      .filter(Boolean)
  })

  darkSurfaces.forEach((sample) => {
    const fg = parseRgb(sample.color)
    const bg = parseRgb(sample.background)
    if (!fg || !bg) return
    const alpha = parseFloat(sample.opacity)
    const effective = fg.map((channel, i) =>
      channel * (Number.isFinite(alpha) ? alpha : 1) + bg[i] * (1 - (Number.isFinite(alpha) ? alpha : 1)),
    )
    const ratio = contrast(effective, bg)
    check(
      `${sample.selector} 对比度达标`,
      ratio >= 4.5,
      `${ratio.toFixed(2)}:1（需 4.5:1，${sample.size}，opacity ${sample.opacity}）`,
    )
  })

  console.log('\n[结果页]')

  await page.locator('.demo').first().click()
  await page.waitForSelector('.result__title', { timeout: 10000 })

  // 彩色实心块上的文字对比度：红/蓝底白字是最容易不达标的地方
  const tiles = await page.evaluate(() => {
    const out = []
    document.querySelectorAll('.tile').forEach((el) => {
      const style = getComputedStyle(el)
      const label = el.querySelector('.tile__label')
      const number = el.querySelector('.tile__number')
      const hint = el.querySelector('.tile__hint')
      out.push({
        cls: el.className,
        background: style.backgroundColor,
        labelColor: label ? getComputedStyle(label).color : null,
        labelSize: label ? getComputedStyle(label).fontSize : null,
        labelOpacity: label ? getComputedStyle(label).opacity : '1',
        numberColor: number ? getComputedStyle(number).color : null,
        numberSize: number ? getComputedStyle(number).fontSize : null,
        hintColor: hint ? getComputedStyle(hint).color : null,
        hintSize: hint ? getComputedStyle(hint).fontSize : null,
        hintOpacity: hint ? getComputedStyle(hint).opacity : '1',
      })
    })
    return out
  })

  /** 半透明文字按 opacity 与底色混合后再算对比度 */
  function blend(fg, bg, opacity) {
    const alpha = Number.isFinite(parseFloat(opacity)) ? parseFloat(opacity) : 1
    return fg.map((channel, i) => channel * alpha + bg[i] * (1 - alpha))
  }

  tiles.forEach((tile) => {
    const bg = parseRgb(tile.background)
    if (!bg) return
    const name = tile.cls.replace('tile tile--', '')

    ;[
      ['标签', tile.labelColor, tile.labelSize, tile.labelOpacity],
      ['数字', tile.numberColor, tile.numberSize, '1'],
      ['说明', tile.hintColor, tile.hintSize, tile.hintOpacity],
    ].forEach(([part, color, size, opacity]) => {
      if (!color) return
      const fg = parseRgb(color)
      if (!fg) return
      const effective = blend(fg, bg, opacity)
      const px = parseFloat(size)
      const bold = part !== '说明'
      // WCAG 大字标准：>=24px，或 >=18.66px 且加粗
      const isLarge = px >= 24 || (px >= 18.66 && bold)
      const threshold = isLarge ? 3 : 4.5
      const ratio = contrast(effective, bg)
      check(
        `指标块 ${name} 的${part}对比度达标`,
        ratio >= threshold,
        `${ratio.toFixed(2)}:1（需 ${threshold}:1，${px}px）`,
      )
    })
  })

  // 亮点卡片序号块（彩色底 + 文字）
  const poiIndexes = await page.evaluate(() => {
    const out = []
    document.querySelectorAll('.poi__index').forEach((el) => {
      const style = getComputedStyle(el)
      out.push({
        cls: el.parentElement.className,
        color: style.color,
        background: style.backgroundColor,
        size: style.fontSize,
      })
    })
    return out
  })

  poiIndexes.forEach((item) => {
    const fg = parseRgb(item.color)
    const bg = parseRgb(item.background)
    if (!fg || !bg) return
    const ratio = contrast(fg, bg)
    check(
      `亮点序号（${item.cls.replace('poi poi--', '')}）对比度达标`,
      ratio >= 3,
      `${ratio.toFixed(2)}:1（需 3:1，${item.size}）`,
    )
  })

  // 结果页布局
  for (const [name, width] of [['桌面', 1280], ['手机', 390]]) {
    await page.setViewportSize({ width, height: 900 })
    await page.waitForTimeout(300)
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
    )
    check(`结果页${name}无横向溢出`, overflow <= 1, `溢出 ${overflow}px`)
  }

  await page.setViewportSize({ width: 1280, height: 900 })
  await page.waitForTimeout(200)
  check('结果页存在唯一 h1', (await page.locator('h1').count()) === 1)
  check('评分条暴露 meter 语义', (await page.locator('[role="meter"]').count()) === 1)
  check('地图有无障碍名称', !!(await page.getAttribute('.map-container', 'aria-label')))

  await page.close()
} finally {
  await browser.close()
}

console.log(problems.length ? `\n失败 ${problems.length} 项` : '\n全部通过')
process.exit(problems.length ? 1 : 0)
