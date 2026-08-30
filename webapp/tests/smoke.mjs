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

    // R1：地图盖住吸顶头部。根因是 `--bh-z-overlay` 只有 30，而 Leaflet 的 pane
    // 从 200 起、控件到 800 —— 页头怎么排都在瓦片下面。修法是把令牌抬到
    // 控件之上（overlay 1000 / dropdown 900），**不能**去压 Leaflet 的 pane：
    // 那会连带把标记压到瓦片底下。这里量的是实际计算值，不是令牌字面量。
    const zLayers = await page.evaluate(() => {
      const read = (selector) => {
        const el = document.querySelector(selector)
        if (!el) return null
        return Number(getComputedStyle(el).zIndex)
      }
      const root = getComputedStyle(document.documentElement)
      return {
        header: read('.head'),
        overlayToken: Number(root.getPropertyValue('--bh-z-overlay')),
        dropdownToken: Number(root.getPropertyValue('--bh-z-dropdown')),
      }
    })
    // 800 是 Leaflet 控件 pane（最高的那层）。页头必须严格高于它。
    check('吸顶头部层级高于 Leaflet 控件（800）', zLayers.header > 800, `header z-index=${zLayers.header}`)
    check('下拉层级高于 Leaflet 控件且低于头部', zLayers.dropdownToken > 800 && zLayers.dropdownToken < zLayers.overlayToken, `dropdown=${zLayers.dropdownToken} overlay=${zLayers.overlayToken}`)

    // R3：一个关键词返回多家门店时必须能选。桩里「麦当劳」有 5 家。
    await page.locator('input').first().fill('麦当劳')
    await page.waitForSelector('.place__option', { timeout: 5000 })
    const optionCount = await page.locator('.place__option').count()
    check('连锁店关键词给出多个候选', optionCount >= 3, `${optionCount} 条`)
    const optionNames = await page.locator('.place__option-name').allInnerTexts()
    check('候选门店互不相同', new Set(optionNames).size === optionNames.length, optionNames.join(' | '))
    check('候选带地址或坐标以便区分', (await page.locator('.place__option-address').count()) >= 3)
    await page.screenshot({ path: `${OUT}/${viewport.name}-suggest.png` })

    // 选第二个 —— 选完输入框里是门店名，坐标进隐藏状态（和 R2 一个机制）
    const pickedName = (await page.locator('.place__option-name').nth(1).innerText()).trim()
    await page.locator('.place__option').nth(1).click()
    await page.waitForTimeout(200)
    const pickedValue = await page.locator('input').first().inputValue()
    check('点候选后输入框填入门店名', pickedValue === pickedName, `${pickedValue} vs ${pickedName}`)
    check('选完候选列表收起', (await page.locator('.place__option').count()) === 0)

    // 无匹配时给可读提示，而且这条提示不是一个能点的假选项
    await page.locator('input').first().fill('这个地方根本不存在xyz')
    await page.waitForSelector('.place__empty', { timeout: 5000 })
    check('联想无结果时给出中文提示', (await page.locator('.place__empty').innerText()).includes('可直接输入地名或坐标'))
    check('空态提示不混进 listbox 选项', (await page.locator('.place__option').count()) === 0)
    check('空态提示不可点选', (await page.locator('.place__empty[role="status"]').count()) === 1)

    await page.locator('input').first().fill('')
    await page.waitForTimeout(150)

    // 走演示场景：大工 -> 星海广场（+15）
    await page.locator('.demo').first().click()
    await page.waitForSelector('.result__title', { timeout: 10000 })

    // T1：标题必须是地名。以前 applyScenario 把 DEMO_SCENARIOS 的
    // originLabel/destinationLabel 丢了，标题直接印「121.5197,38.8856」，
    // 验收人第一句话就是「起点终点显示的是坐标」。
    const titleText = await page.locator('.result__title').innerText()
    check('标题显示地名而非坐标', titleText.includes('大连理工大学') && titleText.includes('星海广场'), titleText)
    check('标题里没有经纬度', !/121\.5197|38\.8856/.test(titleText), titleText)

    check('结果页显示基准时长', (await page.getByText('基准时长').count()) > 0)
    check('结果页显示额外时间', (await page.getByText('额外时间').count()) > 0)
    check('叙事文案渲染', await page.getByText('从大工沿海边走').first().isVisible())
    check('沿途亮点卡片渲染', (await page.locator('.poi').count()) === 2)
    check('路线指引渲染', (await page.locator('.steps__item').count()) > 0)
    // R9：徽标判据从 demo_mode 换成 route.source === 'fallback'。桩的场景
    // 路线带 source: 'fallback'，所以这里必须有；amap 分支的负向断言在
    // tests/ResultView.test.js 里（桩没法同时是两种 source）。
    check('离线演示数据提示可见', await page.getByText('离线演示数据').isVisible())
    check('提示挂在专用类名上', (await page.locator('.result__demo-notice').count()) === 1)

    // R8：地图必须排在指标之前。用 compareDocumentPosition 量真实 DOM 顺序，
    // 不看 CSS —— flex/grid 的 order 能让视觉顺序和 DOM 顺序脱钩，
    // 而读屏和键盘走的是 DOM 顺序。
    const domOrder = await page.evaluate(() => {
      const pick = (selector) => document.querySelector(selector)
      const nodes = {
        title: pick('.result__title'),
        map: pick('.map__frame'),
        tiles: pick('.result__tiles'),
        meter: pick('.result__meter'),
        pois: pick('.result__pois'),
        steps: pick('.steps'),
        actions: pick('.result__actions'),
      }
      const missing = Object.entries(nodes)
        .filter(([, el]) => !el)
        .map(([key]) => key)
      if (missing.length) return { missing }

      // Node.DOCUMENT_POSITION_FOLLOWING === 4：a 在 b 之前
      const before = (a, b) => !!(nodes[a].compareDocumentPosition(nodes[b]) & 4)
      const seq = ['title', 'map', 'tiles', 'meter', 'pois', 'steps', 'actions']
      const broken = []
      for (let i = 0; i < seq.length - 1; i += 1) {
        if (!before(seq[i], seq[i + 1])) broken.push(`${seq[i]} !< ${seq[i + 1]}`)
      }
      return { missing: [], broken }
    })
    check('结果页七个区块都在', domOrder.missing.length === 0, `缺 ${domOrder.missing.join(',')}`)
    check(
      'DOM 顺序为 标题→地图→指标→评分→亮点→指引→操作',
      domOrder.missing.length === 0 && domOrder.broken.length === 0,
      domOrder.broken?.join(' / ') || '',
    )

    // R8 的真风险：Leaflet 在高度为 0 的容器里算出的 zoom 是错的。地图往上挪了，
    // 挪之后它到底还框不框得住两条线，只靠顺序断言看不出来 —— 量框内是否装下折线。
    // fitBounds 是异步的（等 invalidateSize + 缩放动画），刚 waitForSelector
    // 到标题时地图还在初始视野上 —— 那时量出来的是「线只占框的一小半」的假失败。
    await page.waitForSelector('.leaflet-overlay-pane path', { timeout: 10000 })
    await page.waitForTimeout(1500)
    const mapFraming = await page.evaluate(() => {
      const frame = document.querySelector('.map__frame')?.getBoundingClientRect()
      const paths = [...document.querySelectorAll('.leaflet-overlay-pane path')]
      if (!frame || !paths.length) return null
      const boxes = paths.map((p) => p.getBoundingClientRect())
      const left = Math.min(...boxes.map((b) => b.left))
      const right = Math.max(...boxes.map((b) => b.right))
      const top = Math.min(...boxes.map((b) => b.top))
      const bottom = Math.max(...boxes.map((b) => b.bottom))
      return {
        frameH: Math.round(frame.height),
        inside:
          left >= frame.left - 2 && right <= frame.right + 2 && top >= frame.top - 2 && bottom <= frame.bottom + 2,
        // 线要占掉框的一部分，不能缩成一个点（zoom 算错的典型表现）
        fill: Math.round(((right - left) / frame.width) * 100),
      }
    })
    check('地图容器高度不为 0', mapFraming && mapFraming.frameH > 100, `${mapFraming?.frameH}px`)
    check('折线完整落在地图框内', !!mapFraming?.inside, JSON.stringify(mapFraming))
    check('折线不是缩成一点（fitBounds 生效）', mapFraming && mapFraming.fill > 20, `占框宽 ${mapFraming?.fill}%`)

    // 地图瓦片来自外网，离线时允许失败，但容器必须存在
    check('地图容器存在', (await page.locator('.map-container').count()) === 1)
    const routeDrawn = await page.locator('.leaflet-overlay-pane path').count()
    check('路线折线已绘制', routeDrawn > 0, `找到 ${routeDrawn} 条`)

    // T2「地图和路线是死的」：底图必须真的出图。瓦片是外网资源，这里给足时间，
    // 拿不到就明确说是网络问题 —— 但那时界面上必须有「底图暂时下不来」的提示，
    // 而不是一块和加载中长得一样的灰。
    let tiles = 0
    for (let i = 0; i < 20 && tiles === 0; i += 1) {
      tiles = await page.locator('.leaflet-tile-pane img').count()
      if (tiles === 0) await page.waitForTimeout(500)
    }
    if (tiles > 0) {
      check('底图瓦片已加载', tiles > 0, `${tiles} 张`)
      // 骨架屏是等 tileLayer 的 load 事件（整屏瓦片都到位）才撤的，
      // 比「第一张 img 出现在 DOM 里」晚一点，所以这里要等而不是立刻断言
      let skeleton = 1
      for (let i = 0; i < 20 && skeleton > 0; i += 1) {
        skeleton = await page.locator('.map__skeleton').count()
        if (skeleton > 0) await page.waitForTimeout(300)
      }
      check('瓦片到位后骨架屏消失', skeleton === 0)
    } else {
      // 离线环境下也不能是「一块灰 + 没有任何说明」
      check(
        '瓦片下不来时给出可读提示',
        (await page.getByText('底图瓦片加载失败').count()) > 0 ||
          (await page.getByText('底图暂时下不来').count()) > 0,
        '瓦片 0 张且无提示',
      )
    }

    // 拖拽 / 缩放必须真的能用 —— 「死的」很大一部分是没人验证过交互。
    // 缩放层级从瓦片 URL 的 /{z}/ 读，比翻 Leaflet 内部字段稳。
    const readZoom = () =>
      page.evaluate(() => {
        const img = document.querySelector('.leaflet-tile-pane img')
        const match = img?.getAttribute('src')?.match(/\/(\d+)\/\d+\/\d+\.png/)
        return match ? Number(match[1]) : null
      })

    // fitBounds 的缩放动画期间新旧层级的瓦片同时在 DOM 里，这时读出来的 z 不稳。
    // 等到只剩一个层级再取基线，否则会出现「12 -> 15」这种假失败。
    const settleZoom = async () => {
      for (let i = 0; i < 20; i += 1) {
        const levels = await page.evaluate(
          () =>
            new Set(
              [...document.querySelectorAll('.leaflet-tile-pane img')]
                .map((img) => (img.getAttribute('src')?.match(/\/(\d+)\/\d+\/\d+\.png/) || [])[1])
                .filter(Boolean),
            ).size,
        )
        if (levels === 1) return
        await page.waitForTimeout(300)
      }
    }

    await settleZoom()
    const zoomBefore = await readZoom()
    await page.locator('.leaflet-control-zoom-in').click()
    await page.waitForTimeout(900)
    await settleZoom()
    const zoomAfter = await readZoom()
    if (zoomBefore === null) {
      check('缩放控件存在（离线无瓦片，跳过层级比对）', (await page.locator('.leaflet-control-zoom-in').count()) === 1)
    } else {
      check('点「+」后缩放层级真的变了', zoomAfter === zoomBefore + 1, `${zoomBefore} -> ${zoomAfter}`)
    }

    const box = await page.locator('.map-container').boundingBox()
    const beforeDrag = await page
      .locator('.leaflet-map-pane')
      .evaluate((n) => getComputedStyle(n).transform)
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
    await page.mouse.down()
    await page.mouse.move(box.x + box.width / 2 - 90, box.y + box.height / 2 - 60, { steps: 8 })
    await page.mouse.up()
    await page.waitForTimeout(400)
    const afterDrag = await page
      .locator('.leaflet-map-pane')
      .evaluate((n) => getComputedStyle(n).transform)
    check('地图可拖拽（pane 位移发生变化）', afterDrag !== beforeDrag, `${beforeDrag} -> ${afterDrag}`)

    // P3-4：基准路线同图对比。灰虚线靠 stroke-dasharray 区分，
    // 图例文案与虚线必须同时出现 —— 只有图例没有线就是假对比。
    // 虚线是描边 + 芯两笔，且必须画在推荐路线之后（DOM 里排在后面 = 盖在上面）。
    // 断网演示的基准与推荐逐点重合，画在底下会被完全盖住 —— 断言全绿而图上看不见。
    const paths = await page.locator('.leaflet-overlay-pane path').evaluateAll((nodes) =>
      nodes.map((n) => Boolean(n.getAttribute('stroke-dasharray'))),
    )
    const dashed = paths.filter(Boolean).length
    check('基准路线画成虚线（描边 + 芯两笔）', dashed === 2, `找到 ${dashed} 条虚线`)
    check(
      '基准虚线盖在推荐路线上面',
      dashed === 2 && paths.indexOf(true) > paths.lastIndexOf(false),
      `顺序: ${paths.map((d) => (d ? 'dash' : 'solid')).join(',')}`,
    )
    check('图例出现「原本路线」', (await page.getByText('原本路线').count()) > 0)
    const pins = await page.locator('.bh-pin').count()
    check('起终点与 POI 标记已绘制', pins >= 4, `找到 ${pins} 个`)

    // T3：两条线的距离 + 时长必须并排印出来。图上有两条线不等于「显示出区别」——
    // 没有数字，谁也说不出推荐比原本多绕了多少。mock 的基准是 2180 米 / 21 分钟，
    // 推荐是 2620 米 / 26 分钟。
    //
    // R5：这三条从 `.compare`（已删除的独立对比块）迁到指标格上。要求没变：
    // 基准的两个数、推荐的两个数、两个带符号的差值，六个都得在屏幕上。
    // 区别是现在原值贴在它对应的现值头上，不再是隔着半屏的另一块。
    const tileText = await page.locator('.result__tiles').innerText()
    check('指标格给出基准的距离和时长', /原\s*2\.2 公里/.test(tileText) && /原\s*21 分钟/.test(tileText), tileText.replace(/\n/g, ' | '))
    check('指标格给出推荐的距离和时长', /2\.6 公里/.test(tileText) && /26/.test(tileText), tileText.replace(/\n/g, ' | '))
    check('指标格给出带符号的差值', /\+440 米/.test(tileText) && /\+5 分钟/.test(tileText), tileText.replace(/\n/g, ' | '))

    // R5：原值必须和它自己的现值在同一个格子里，且小字在大字上面。
    // 光看整块文字过不了这一关 —— 两个数字都在 `.result__tiles` 里，
    // 但如果原值跑到了别的格子，屏幕上读出来就是「原 2.2 公里 / 26 分钟」。
    const pairing = await page.evaluate(() => {
      const out = []
      document.querySelectorAll('.result__tiles .tile').forEach((tile) => {
        const baseline = tile.querySelector('.tile__baseline')
        if (!baseline) return
        const number = tile.querySelector('.tile__number')
        out.push({
          label: tile.querySelector('.tile__label')?.textContent?.trim(),
          baseline: baseline.textContent.replace(/\s+/g, ' ').trim(),
          current: number?.textContent?.trim(),
          delta: tile.querySelector('.tile__delta')?.textContent?.trim() ?? '',
          // 小字在上：原值的 top 必须小于大号数字的 top
          stacked:
            !!number &&
            baseline.getBoundingClientRect().top < number.getBoundingClientRect().top,
        })
      })
      return out
    })
    const detail = pairing.map((p) => `${p.label}: ${p.baseline} -> ${p.current} ${p.delta}`).join(' | ')
    check('带原值的格子正好是距离和总计两个', pairing.length === 2, detail)
    check('每个格子的原值压在自己的现值上方', pairing.length === 2 && pairing.every((p) => p.stacked), detail)
    check(
      '距离的原值配距离、时长的原值配时长',
      pairing.some((p) => /2\.2 公里/.test(p.baseline) && p.current === '2.6 公里') &&
        pairing.some((p) => /21 分钟/.test(p.baseline) && p.current === '26'),
      detail,
    )

    // T4：「为什么推荐这条」必须真的回答为什么。三条理由分别是亮点、绕行代价、
    // 评分拆分；mock 的分数现在是按后端公式算出来的（derive()），
    // +15 下 4.4 分的 POI、绕行 5 分钟 -> 3.5 + 2.1 - 1.0 = 4.6。
    const reasonNodes = page.locator('.narrative__reason')
    const reasonCount = await reasonNodes.count()
    check('推荐理由是结构化的多条，不是一句叙事', reasonCount === 3, `${reasonCount} 条`)
    const reasonText = await page.locator('.narrative__reasons').innerText()
    check('理由点名了沿途亮点', /理工咖啡小铺/.test(reasonText) && /2 处亮点/.test(reasonText), reasonText.replace(/\n/g, ' | '))
    check('理由说清绕行代价和额度', /多花 5 分钟/.test(reasonText) && /15 分钟额度以内/.test(reasonText), reasonText.replace(/\n/g, ' | '))
    check(
      '评分拆分和总分自洽',
      /4\.6 \/ 7/.test(reasonText) && /亮点质量 3\.5/.test(reasonText) && /口味契合 2\.1/.test(reasonText) && /绕行扣 1\.0/.test(reasonText),
      reasonText.replace(/\n/g, ' | '),
    )
    // 叙事保留，但必须在理由下面收尾，不能顶掉理由
    const narrativeBox = await page.locator('.narrative').innerText()
    check(
      '叙事退到理由下方收尾',
      narrativeBox.indexOf('理工咖啡小铺') < narrativeBox.indexOf('从大工沿海边走'),
      narrativeBox.replace(/\n/g, ' | '),
    )
    check('评分条数值不超过满分', !/([89]|\d\d)\.\d\/7/.test(await page.locator('.meter__value').innerText()), await page.locator('.meter__value').innerText())

    await page.screenshot({ path: `${OUT}/${viewport.name}-result.png`, fullPage: true })
    await page.locator('.narrative').screenshot({ path: `${OUT}/${viewport.name}-reasons.png` })

    // T8-5：窄屏不许溢出。整页横向滚动条 = 有东西比视口宽。
    // 瓦片本来就靠 overflow:hidden 裁掉（Leaflet 的常规做法），不算溢出，
    // 所以按 documentElement.scrollWidth 判，而不是逐元素扫 boundingBox。
    const scrollW = await page.evaluate(() => document.documentElement.scrollWidth)
    check('页面没有横向溢出', scrollW <= viewport.width + 1, `scrollWidth ${scrollW} > ${viewport.width}`)

    // T8-5：指标卡片 / 对比块行 / 图例项 / 理由条各自不许两两重叠。
    // 这类缺陷断言抓不到（文字都在 DOM 里），只有几何比较能发现。
    const overlaps = await page.evaluate(() => {
      const groups = {
        指标卡片: '.result__tiles > *',
        // R5：`.compare__row` 已随独立对比块一起删除。原值 / 差值现在挤在
        // 指标格内部，格子的重叠检查（上面那条）连带覆盖了它们，
        // 但格子里三行小字自己也可能压到一起，所以单列一组。
        格内对比行: '.tile__baseline, .tile__delta',
        图例项: '.map__legend-item',
        理由条: '.narrative__reason',
      }
      const out = {}
      for (const [name, selector] of Object.entries(groups)) {
        const rects = [...document.querySelectorAll(selector)].map((n) => n.getBoundingClientRect())
        const hits = []
        for (let i = 0; i < rects.length; i += 1) {
          for (let j = i + 1; j < rects.length; j += 1) {
            const a = rects[i]
            const b = rects[j]
            const ox = Math.min(a.right, b.right) - Math.max(a.left, b.left)
            const oy = Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top)
            if (ox > 1 && oy > 1) hits.push(`${i}x${j}`)
          }
        }
        out[name] = { count: rects.length, hits }
      }
      return out
    })
    for (const [name, info] of Object.entries(overlaps)) {
      check(`${name}无重叠（${info.count} 个）`, info.count > 0 && info.hits.length === 0, info.hits.join(','))
    }

    // 未定稿接口：收藏会 404，界面应提示失败而不是崩溃
    await page.locator('.bh-btn--accent').click()
    await page.waitForTimeout(600)
    check('收藏接口缺失时提示失败而非崩溃', await page.getByText('收藏失败').isVisible())

    // T8-4：反馈的视觉确认必须对应真实结果。按钮变色只说明「你点了这个」，
    // 「后端真的学到了什么」得由文字说 —— 归因失败时写「已记住」是骗人。
    const likeButton = page.locator('.result__feedback button').first()
    await likeButton.click()
    await page.waitForTimeout(600)
    check('反馈按钮进入选中态', (await likeButton.getAttribute('aria-pressed')) === 'true')
    const feedbackNote = await page.locator('.result__feedback-note').innerText()
    // 钉的类目要跟着演示数据走：SCENARIOS[0] 的 POI type 是「餐饮」「景点」，
    // 归并后 learned = ['餐饮','景点']。这里钉「餐饮」而不是把 mock 的 type
    // 改成「咖啡厅」去迁就断言 —— 演示数据不为了让测试好过而改。
    check(
      '反馈给出文字确认并说明学到了什么',
      /已记住/.test(feedbackNote) && /餐饮/.test(feedbackNote) && /加权/.test(feedbackNote),
      feedbackNote,
    )
    await page.locator('.result__actions').screenshot({ path: `${OUT}/${viewport.name}-feedback.png` })

    // 点击亮点卡片高亮
    await page.locator('.poi').first().click()
    check('点击亮点后高亮', (await page.locator('.poi--active').count()) === 1)

    // T2：卡片变色不够 —— 图上也必须看得出来。标记换成放大款，并把该点平移到视野中央。
    // 以前只有卡片自己变，图上毫无反应，就是「地图是死的」。
    //
    // S0：第一个亮点是**途经点**（路线两段拼接真的穿过它），选中态是 waypoint-active；
    // 后面的是「附近亮点」，选中态才是 poi-active。断言分开写 —— 合成一条
    // `[class*="-active"]` 就又回到「不区分两种标记」的老样子了。
    check(
      '点途经点后图上标记进入 active 态',
      (await page.locator('.bh-pin--waypoint-active').count()) === 1,
    )
    const panned = await page.locator('.leaflet-map-pane').evaluate((n) => getComputedStyle(n).transform)
    await page.locator('.poi').nth(1).click()
    await page.waitForTimeout(600)
    const pannedAgain = await page
      .locator('.leaflet-map-pane')
      .evaluate((n) => getComputedStyle(n).transform)
    check('点另一个亮点后地图平移过去', pannedAgain !== panned, `${panned} -> ${pannedAgain}`)
    check('active 标记只有一个', (await page.locator('.bh-pin--poi-active').count()) === 1)
    // 选中第二个之后，第一个必须退回未选中的**途经点**款（而不是变成普通附近亮点）
    check('途经点标记始终与附近亮点不同款', (await page.locator('.bh-pin--waypoint').count()) === 1)

    // 取消选中，回到干净状态再继续后面的断言
    await page.locator('.poi').nth(1).click()
    await page.waitForTimeout(300)

    // R6：点击展开详情。桩里第一条 POI 字段齐全（地址 / 电话 / 营业时间 / 照片），
    // 第二条只有基础五字段 —— 后者不该出现「展开详情」，更不该点开一个空框。
    const rich = page.locator('.poi').first()
    const plain = page.locator('.poi').nth(1)

    // 上面 T2 的点击流程已经点过第一张卡片，它此刻是展开态。先收回去 ——
    // 从「未展开」开始，下面的展开 / 收起才各自验到一次真实的状态切换。
    if ((await rich.getAttribute('aria-expanded')) === 'true') {
      await rich.click()
      await page.waitForTimeout(250)
    }

    check('缺字段的亮点不提示展开', (await plain.locator('.poi__toggle').count()) === 0)
    check(
      '缺字段的亮点不暴露 aria-expanded',
      (await plain.getAttribute('aria-expanded')) === null,
      String(await plain.getAttribute('aria-expanded')),
    )
    check('字段齐全的亮点提示可展开', (await rich.locator('.poi__toggle').count()) === 1)
    check('未展开时 aria-expanded 为 false', (await rich.getAttribute('aria-expanded')) === 'false')

    await rich.click()
    await page.waitForTimeout(250)
    check('展开后 aria-expanded 为 true', (await rich.getAttribute('aria-expanded')) === 'true')
    const detailText = await rich.locator('.poi__detail').innerText()
    check(
      '详情区给出地址 / 电话 / 营业时间',
      /凌工路 2 号/.test(detailText) && /0411-8470-9988/.test(detailText) && /07:30-21:00/.test(detailText),
      detailText.replace(/\n/g, ' | '),
    )
    check('详情区不摆空占位', !/暂无|undefined|\[\]/.test(detailText), detailText.replace(/\n/g, ' | '))
    // 照片必须真的画出来（宽高非 0），不是一个加载失败的破图框
    const photoBox = await rich.locator('.poi__photo').boundingBox()
    check('详情区渲染照片', !!photoBox && photoBox.width > 10 && photoBox.height > 10, JSON.stringify(photoBox))
    await page.locator('.poi').first().screenshot({ path: `${OUT}/${viewport.name}-poi-expanded.png` })

    // 再点收起。展开态收起后详情区必须真的从 DOM 消失，不是只改了个 class
    await rich.click()
    await page.waitForTimeout(250)
    check('再点一次收起详情', (await rich.locator('.poi__detail').count()) === 0)
    check('收起后 aria-expanded 回到 false', (await rich.getAttribute('aria-expanded')) === 'false')

    // 键盘可达：Enter 展开、Space 收起。role=button 的卡片必须能不用鼠标操作
    await rich.focus()
    await page.keyboard.press('Enter')
    await page.waitForTimeout(250)
    check('Enter 可展开详情', (await rich.locator('.poi__detail').count()) === 1)
    await page.keyboard.press('Space')
    await page.waitForTimeout(250)
    check('Space 可收起详情', (await rich.locator('.poi__detail').count()) === 0)

    // 展开一次会连带把这张卡片选中（一次点击两件事），清掉再继续
    if ((await page.locator('.poi--active').count()) > 0) {
      await page.locator('.poi--active').first().click()
      await page.waitForTimeout(250)
    }

    // R7：「重新规划」和「返回首页」以前 emit 同一个事件，点前者会被踢回首页。
    // 现在前者原地重算：留在结果页，起终点和模式不变，指标重新出现。
    const beforeTitle = await page.locator('.result__title').innerText()
    const beforeMode = await page.locator('.result__mode').innerText()
    await page.locator('.result__replan').click()
    await page.waitForTimeout(1200)
    check('点重新规划后仍在结果页', (await page.locator('.result__title').count()) === 1)
    check('重新规划没跳回首页', (await page.locator('.home__form').count()) === 0)
    check('重新规划后起终点不变', (await page.locator('.result__title').innerText()) === beforeTitle, beforeTitle)
    check('重新规划后模式不变', (await page.locator('.result__mode').innerText()) === beforeMode, beforeMode)
    check('重新规划后指标仍在', (await page.locator('.tile').count()) === 4)
    check('重新规划没报错', (await page.locator('.result__replan-error').count()) === 0)
    check('重新规划按钮回到可用态', await page.locator('.result__replan').isEnabled())

    // R7：结果页头里不再摆第二个「返回首页」—— 吸顶页头已经有一个，
    // 而且滚到页面底部它还在，比结果页头里那个更好用。
    // S3：页头现在是「三个模式 + 重新规划」四个按钮，逐类点清比数总数更能说明问题。
    check('结果页头只有一个重新规划按钮', (await page.locator('.result__head .result__replan').count()) === 1)
    check('结果页头有三个模式按钮', (await page.locator('.result__head .result__mode-btn').count()) === 3)
    check('结果页头没有别的按钮', (await page.locator('.result__head button').count()) === 4)
    check('结果页头不重复摆返回首页', !(await page.locator('.result__head').innerText()).includes('返回首页'))

    await page.locator('.head__back').click()
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

    // T8-3：后端根本连不上时，fetch 抛的是 `TypeError: Failed to fetch`。
    // 以前这行英文被原样印在红条上，用户看不出是后端没起还是自己填错了。
    // 断言这两件事同时成立：换成了中文，且后端的中文 detail 没被这层翻译盖掉。
    await page.route('**/api/route/recommend', (r) => r.abort('connectionrefused'))
    await page.locator('input').first().fill('大连理工大学')
    await page.locator('input').nth(1).fill('星海广场')
    await page.locator('button[type="submit"]').click()
    await page.waitForTimeout(1200)
    const deadText = await page.locator('[role="alert"]').innerText()
    check('后端连不上时给出中文提示', /连不上后端服务/.test(deadText), deadText)
    check('提示里没有英文原文', !/failed to fetch/i.test(deadText), deadText)
    await page.locator('.home__form').screenshot({ path: `${OUT}/${viewport.name}-dead-backend.png` })
    await page.unroute('**/api/route/recommend')

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
