/**
 * 冒烟脚本：用真实浏览器跑一遍首页 -> 结果页，并截图。
 * 需要先启动 mock 后端与 vite：
 *   node tests/mock-server.mjs 8000
 *   npx vite --port 5173
 * 用法： node tests/smoke.mjs [baseUrl] [outDir]
 */
import { chromium } from 'playwright'
import { mkdir } from 'node:fs/promises'

const BASE = process.argv[2] || 'http://localhost:5173'
const OUT = process.argv[3] || '/tmp/shots'

const problems = []

function check(label, condition, detail = '') {
  if (condition) {
    console.log(`  ok   ${label}`)
  } else {
    console.log(`  FAIL ${label}${detail ? ` — ${detail}` : ''}`)
    problems.push(label)
  }
}

const browser = await chromium.launch()

try {
  await mkdir(OUT, { recursive: true })

  for (const viewport of [
    { name: 'desktop', width: 1280, height: 900 },
    { name: 'mobile', width: 390, height: 844 },
  ]) {
    console.log(`\n[${viewport.name}]`)
    const page = await browser.newPage({
      viewport: { width: viewport.width, height: viewport.height },
    })

    const consoleErrors = []
    page.on('console', (msg) => {
      if (msg.type() === 'error') consoleErrors.push(msg.text())
    })
    page.on('pageerror', (err) => consoleErrors.push(String(err)))

    await page.goto(BASE, { waitUntil: 'networkidle' })

    check('页面标题正确', (await page.title()).includes('偶遇导航'))
    check('后端连通状态显示已连接', await page.getByText('后端已连接').isVisible())
    check('三个模式按钮渲染', (await page.getByRole('radio').count()) === 3)
    check('三个演示场景渲染', (await page.locator('.demo').count()) === 3)

    const submit = page.locator('button[type="submit"]')
    check('空表单时提交按钮禁用', await submit.isDisabled())

    await page.screenshot({ path: `${OUT}/${viewport.name}-home.png`, fullPage: true })

    // 走演示场景：大工 -> 星海广场（+15）
    await page.locator('.demo').first().click()
    await page.waitForSelector('.result__title', { timeout: 10000 })

    check('结果页显示基准时长', (await page.getByText('基准时长').count()) > 0)
    check('结果页显示额外时间', (await page.getByText('额外时间').count()) > 0)
    check('叙事文案渲染', await page.getByText('从大工沿海边走').first().isVisible())
    check('沿途亮点卡片渲染', (await page.locator('.poi').count()) === 2)
    check('路线指引渲染', (await page.locator('.steps__item').count()) > 0)
    check('演示数据提示可见', await page.getByText('内置演示数据').isVisible())

    // 地图瓦片来自外网，离线时允许失败，但容器必须存在
    check('地图容器存在', (await page.locator('.map-container').count()) === 1)
    const routeDrawn = await page.locator('.leaflet-overlay-pane path').count()
    check('路线折线已绘制', routeDrawn > 0, `找到 ${routeDrawn} 条`)
    const pins = await page.locator('.bh-pin').count()
    check('起终点与 POI 标记已绘制', pins >= 4, `找到 ${pins} 个`)

    await page.screenshot({ path: `${OUT}/${viewport.name}-result.png`, fullPage: true })

    // 未实现接口：收藏会 501，界面应提示失败而不是崩溃
    await page.locator('.bh-btn--accent').click()
    await page.waitForTimeout(600)
    check('收藏接口缺失时提示失败而非崩溃', await page.getByText('收藏失败').isVisible())

    // 点击亮点卡片高亮
    await page.locator('.poi').first().click()
    check('点击亮点后高亮', (await page.locator('.poi--active').count()) === 1)

    await page.locator('.result__back').click()
    await page.waitForSelector('.home__form', { timeout: 5000 })
    check('可返回首页', (await page.locator('.home__form').count()) === 1)
    check('返回后出现最近查询', (await page.locator('.history__item').count()) > 0)

    // 错误态：mock 后端对含“无结果”的起点返回 404
    await page.locator('input').first().fill('无结果起点')
    await page.locator('input').nth(1).fill('某个终点')
    await page.locator('button[type="submit"]').click()
    await page.waitForSelector('[role="alert"]', { timeout: 8000 })
    check('后端错误文案透传', (await page.locator('[role="alert"]').innerText()).includes('未找到可行路线'))

    await page.screenshot({ path: `${OUT}/${viewport.name}-error.png`, fullPage: true })

    const realErrors = consoleErrors.filter(
      (text) => !/tile\.openstreetmap|ERR_|net::|Failed to load resource/i.test(text),
    )
    check('无脚本报错', realErrors.length === 0, realErrors.join(' | '))

    await page.close()
  }
} finally {
  await browser.close()
}

console.log(problems.length ? `\n失败 ${problems.length} 项` : '\n全部通过')
process.exit(problems.length ? 1 : 0)
