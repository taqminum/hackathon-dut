/**
 * 冒烟脚本：用真实浏览器跑一遍首页 -> 结果页，并截图。
 * 需要先启动后端与 vite：
 *   node tests/mock-server.mjs 8000      # 桩（断言全绿的那一套）
 *   npx vite --port 5173
 * 用法： node tests/smoke.mjs [baseUrl] [outDir]
 *
 * 也能对着**真后端**跑（`uvicorn app.main:app --port 8000`）。这时有一批断言
 * 钉的是桩的固定数据（麦当劳 5 家门店、「理工咖啡小铺」、2.2/2.6 公里……），
 * 真后端没有 AMAP_KEY 时给不出来。这类检查记 SKIP 而不是 FAIL，更不能像以前
 * 那样直接抛 TimeoutError 把整轮打断 —— 一崩就看不到后面几十条真实断言，
 * 「对着真后端跑一遍」这件事等于做不了。
 *
 * 所以本文件里所有可能因数据缺失而抛的等待/取值都走下面的 `waitFor` /
 * `textOf`：它们返回布尔或空串，判断权交给调用处。
 */
import { chromium } from 'playwright'
import { mkdir } from 'node:fs/promises'

const BASE = process.argv[2] || 'http://localhost:5173'
const OUT = process.argv[3] || '/tmp/shots'

const problems = []
const skipped = []

function check(label, condition, detail = '') {
  if (condition) {
    console.log(`  ok   ${label}`)
  } else {
    console.log(`  FAIL ${label}${detail ? ` — ${detail}` : ''}`)
    problems.push(label)
  }
}

/** 数据前提不成立时用这个：不算失败，但必须印出来，否则「全部通过」会骗人。 */
function skip(label, why = '') {
  console.log(`  skip ${label}${why ? ` — ${why}` : ''}`)
  skipped.push(label)
}

/** 等元素出现，超时返回 false 而不是抛。 */
async function waitFor(page, selector, timeout = 5000) {
  try {
    await page.waitForSelector(selector, { timeout })
    return true
  } catch {
    return false
  }
}

/** 取文本，元素不存在时返回空串 —— 让断言去判空，而不是让脚本崩掉。 */
async function textOf(locator) {
  try {
    if ((await locator.count()) === 0) return ''
    return await locator.first().innerText()
  } catch {
    return ''
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
    //
    // 真后端没有 AMAP_KEY 时 /api/place/suggest 回空列表，「麦当劳」也不在本地
    // 地标词典里 —— 于是一条候选都不会有。这不是缺陷（空态提示才是那时的正确
    // 表现），所以这里改成「有候选就验多选，没候选就验空态并 SKIP 多选」。
    // 以前这行直接 waitForSelector('.place__option') 抛 TimeoutError，
    // 整个脚本在第 8 条断言上崩掉，后面几十条真实检查一条都跑不到。
    await page.locator('input').first().fill('麦当劳')
    const hasSuggestions = await waitFor(page, '.place__option', 5000)

    if (hasSuggestions) {
      const optionCount = await page.locator('.place__option').count()
      check('连锁店关键词给出多个候选', optionCount >= 3, `${optionCount} 条`)
      const optionNames = await page.locator('.place__option-name').allInnerTexts()
      check('候选门店互不相同', new Set(optionNames).size === optionNames.length, optionNames.join(' | '))
      check('候选带地址或坐标以便区分', (await page.locator('.place__option-address').count()) >= 3)
      await page.screenshot({ path: `${OUT}/${viewport.name}-suggest.png` })

      // 选第二个 —— 选完输入框里是门店名，坐标进隐藏状态（和 R2 一个机制）
      const pickedName = (await textOf(page.locator('.place__option-name').nth(1))).trim()
      await page.locator('.place__option').nth(1).click()
      await page.waitForTimeout(200)
      const pickedValue = await page.locator('input').first().inputValue()
      check('点候选后输入框填入门店名', pickedValue === pickedName, `${pickedValue} vs ${pickedName}`)
      check('选完候选列表收起', (await page.locator('.place__option').count()) === 0)
    } else {
      skip('连锁店关键词给出多个候选', '联想返回空（真后端无 AMAP_KEY）')
      skip('点候选后输入框填入门店名', '没有候选可点')
      // 但这时**必须**有可读的空态提示，不能是一个什么都不显示的输入框。
      check('联想为空时仍给出空态提示', await waitFor(page, '.place__empty', 3000))
      await page.screenshot({ path: `${OUT}/${viewport.name}-suggest.png` })
    }

    // 无匹配时给可读提示，而且这条提示不是一个能点的假选项
    await page.locator('input').first().fill('这个地方根本不存在xyz')
    check('联想无结果时出现空态提示', await waitFor(page, '.place__empty', 5000))
    check(
      '联想无结果时给出中文提示',
      (await textOf(page.locator('.place__empty'))).includes('可直接输入地名或坐标'),
      await textOf(page.locator('.place__empty')),
    )
    check('空态提示不混进 listbox 选项', (await page.locator('.place__option').count()) === 0)
    check('空态提示不可点选', (await page.locator('.place__empty[role="status"]').count()) === 1)

    await page.locator('input').first().fill('')
    await page.waitForTimeout(150)

    // 走演示场景：大工 -> 星海广场（+15）
    await page.locator('.demo').first().click()
    const gotResult = await waitFor(page, '.result__title', 20000)
    if (!gotResult) {
      // 请求挂了就没有后面任何东西可量。把接口报的话印出来 —— 这比一屏
      // TimeoutError 堆栈有用得多。
      check(
        '演示场景能出结果页',
        false,
        (await textOf(page.locator('[role="alert"]'))) || '既没有结果页也没有错误提示',
      )
      await page.screenshot({ path: `${OUT}/${viewport.name}-no-result.png`, fullPage: true })
      await page.close()
      continue
    }

    // T1：标题必须是地名。以前 applyScenario 把 DEMO_SCENARIOS 的
    // originLabel/destinationLabel 丢了，标题直接印「121.5197,38.8856」，
    // 验收人第一句话就是「起点终点显示的是坐标」。
    const titleText = await page.locator('.result__title').innerText()
    check('标题显示地名而非坐标', titleText.includes('大连理工大学') && titleText.includes('星海广场'), titleText)
    check('标题里没有经纬度', !/121\.5197|38\.8856/.test(titleText), titleText)

    check('结果页显示基准时长', (await page.getByText('基准时长').count()) > 0)
    // 绕行不足一分钟时这一格换成「额外路程 + 米」（真后端的兜底数据就是这种），
    // 所以两个 label 认一个就行 —— 但必须**只**出现一个，单位对不上的组合
    // 由 tests/ResultView.test.js 那条配对断言守着。
    const detourLabels = await page.locator('.tile__label').allInnerTexts()
    const detourShown = detourLabels.filter((t) => ['额外时间', '额外路程'].includes(t.trim()))
    check('结果页显示绕行代价格（时间或路程）', detourShown.length === 1, detourLabels.join(' | '))
    check('叙事文案渲染', (await textOf(page.locator('.narrative'))).length > 0)
    // 真后端在没有 AMAP_KEY 时靠兜底数据，POI 条数由 dalian 场景表决定；
    // 桩固定给 2 条。这里只要求「至少有一条亮点」，条数细节归 vitest 管。
    const poiCount = await page.locator('.poi').count()
    check('沿途亮点卡片渲染', poiCount > 0, `${poiCount} 张`)
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
    //
    // 判据不能是「`.leaflet-tile-pane img` 有几个节点」。Leaflet 一发请求就把
    // <img> 插进 DOM 了，请求失败它照样留在那儿 —— 于是网络受限时数出 18 张
    // 「已加载」，接着断言骨架屏该撤，而骨架屏正确地留着（提示也正确地显示了
    // 「底图瓦片加载失败（网络受限）」），报出一条假 FAIL。实测本机 18 张全是
    // naturalWidth === 0。所以按**解码成功**的张数判，这才是「出图了」。
    let decoded = 0
    for (let i = 0; i < 20 && decoded === 0; i += 1) {
      decoded = await page.evaluate(
        () =>
          [...document.querySelectorAll('.leaflet-tile-pane img')].filter(
            (img) => img.complete && img.naturalWidth > 0,
          ).length,
      )
      if (decoded === 0) await page.waitForTimeout(500)
    }
    if (decoded > 0) {
      check('底图瓦片已加载', decoded > 0, `${decoded} 张`)
      // 骨架屏等 tileload（有瓦片真的出图）才撤，比 <img> 进 DOM 晚，所以要等。
      let skeleton = 1
      for (let i = 0; i < 20 && skeleton > 0; i += 1) {
        skeleton = await page.locator('.map__skeleton').count()
        if (skeleton > 0) await page.waitForTimeout(300)
      }
      check('瓦片到位后骨架屏消失', skeleton === 0)
    } else {
      // 离线环境下也不能是「一块灰 + 没有任何说明」
      const nodes = await page.locator('.leaflet-tile-pane img').count()
      skip('底图瓦片已加载', `${nodes} 个 img 节点但一张都没解码成功（网络受限）`)
      check(
        '瓦片下不来时给出可读提示',
        (await page.getByText('底图瓦片加载失败').count()) > 0 ||
          (await page.getByText('底图暂时下不来').count()) > 0,
        `img 节点 ${nodes} 个，解码 0 张，且无提示`,
      )
      // 这时骨架屏**应该**留着（它是「还没出图」的视觉表达），但必须同时有文字说明，
      // 否则就是一块和加载中无法区分的灰 —— 上面那条已经守住了文字。
    }

    // 拖拽 / 缩放必须真的能用 —— 「死的」很大一部分是没人验证过交互。
    // 缩放层级从瓦片 URL 读：兼容 /z/x/y.png（OSM / ESRI）与高德的 x=..&y=..&z=..。
    const readZoom = () =>
      page.evaluate(() => {
        const img = document.querySelector('.leaflet-tile-pane img')
        const src = img?.getAttribute('src') || ''
        const slash = src.match(/\/(\d+)\/\d+\/\d+\.png/)
        if (slash) return Number(slash[1])
        const query = src.match(/[?&]z=(\d+)/)
        return query ? Number(query[1]) : null
      })

    // fitBounds 的缩放动画期间新旧层级的瓦片同时在 DOM 里，这时读出来的 z 不稳。
    // 等到只剩一个层级再取基线，否则会出现「12 -> 15」这种假失败。
    const settleZoom = async () => {
      for (let i = 0; i < 20; i += 1) {
        const levels = await page.evaluate(() => {
          const zoomOf = (src) => {
            if (!src) return null
            const slash = src.match(/\/(\d+)\/\d+\/\d+\.png/)
            if (slash) return Number(slash[1])
            const query = src.match(/[?&]z=(\d+)/)
            return query ? Number(query[1]) : null
          }
          return new Set(
            [...document.querySelectorAll('.leaflet-tile-pane img')]
              .map((img) => zoomOf(img.getAttribute('src')))
              .filter((z) => z !== null),
          ).size
        })
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

    // 下面一批断言钉的是 mock-server.mjs 的固定数据（2.2/2.6 公里、
    // 「理工咖啡小铺」、4.6 分的拆分……）。真后端算出来的是另一套数字，
    // 拿这些正则去套只会得到一串无意义的 FAIL，掩盖真正的问题。
    //
    // 判据用桩独有的 POI 名，而不是「有没有 AMAP_KEY」之类的环境猜测：
    // 屏幕上写着「理工咖啡小铺」就说明这一屏确实是桩的数据。
    const usingStub = /理工咖啡小铺/.test(await textOf(page.locator('.result__pois')))
    if (!usingStub) {
      console.log('  ——  非桩数据（真后端），以下钉死固定数字的断言记 skip')
    }

    // T3：两条线的距离 + 时长必须并排印出来。图上有两条线不等于「显示出区别」——
    // 没有数字，谁也说不出推荐比原本多绕了多少。mock 的基准是 2180 米 / 21 分钟，
    // 推荐是 2620 米 / 26 分钟。
    //
    // R5：这三条从 `.compare`（已删除的独立对比块）迁到指标格上。要求没变：
    // 基准的两个数、推荐的两个数、两个带符号的差值，六个都得在屏幕上。
    // 区别是现在原值贴在它对应的现值头上，不再是隔着半屏的另一块。
    const tileText = await page.locator('.result__tiles').innerText()
    if (usingStub) {
      check('指标格给出基准的距离和时长', /原\s*2\.2 公里/.test(tileText) && /原\s*21 分钟/.test(tileText), tileText.replace(/\n/g, ' | '))
      check('指标格给出推荐的距离和时长', /2\.6 公里/.test(tileText) && /26/.test(tileText), tileText.replace(/\n/g, ' | '))
      check('指标格给出带符号的差值', /\+440 米/.test(tileText) && /\+5 分钟/.test(tileText), tileText.replace(/\n/g, ' | '))
    } else {
      // 数字不钉，但「基准 / 推荐 / 差值三件事都印出来了」这个结构必须成立。
      check('指标格给出基准值（原 …）', /原\s*[\d.]+/.test(tileText), tileText.replace(/\n/g, ' | '))
      check('指标格给出带符号的差值', /[+-]\d/.test(tileText), tileText.replace(/\n/g, ' | '))
      check('指标格四个格子都在', (await page.locator('.result__tiles .tile').count()) === 4)
      skip('指标格给出桩的固定距离和时长', '真后端数字不同')
    }

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
    if (usingStub) {
      check(
        '距离的原值配距离、时长的原值配时长',
        pairing.some((p) => /2\.2 公里/.test(p.baseline) && p.current === '2.6 公里') &&
          pairing.some((p) => /21 分钟/.test(p.baseline) && p.current === '26'),
        detail,
      )
    } else {
      // 数字换了，配对规则没换：带「公里/米」的原值必须配距离格，带「分钟」的配时长格。
      // 这条才是 R5 真正要守的东西，和具体数值无关。
      check(
        '距离的原值配距离、时长的原值配时长',
        pairing.length === 2 &&
          pairing.every((p) =>
            /公里|米/.test(p.baseline)
              ? /公里|米/.test(p.current || '')
              : !/公里|米/.test(p.current || ''),
          ),
        detail,
      )
    }

    // T4：「为什么推荐这条」必须真的回答为什么。三条理由分别是亮点、绕行代价、
    // 评分拆分；mock 的分数现在是按后端公式算出来的（derive()），
    // +15 下 4.4 分的 POI、绕行 5 分钟 -> 3.5 + 2.1 - 1.0 = 4.6。
    const reasonNodes = page.locator('.narrative__reason')
    const reasonCount = await reasonNodes.count()
    check('推荐理由是结构化的多条，不是一句叙事', reasonCount === 3, `${reasonCount} 条`)
    const reasonText = await textOf(page.locator('.narrative__reasons'))
    if (usingStub) {
      check('理由点名了沿途亮点', /理工咖啡小铺/.test(reasonText) && /2 处亮点/.test(reasonText), reasonText.replace(/\n/g, ' | '))
      check('理由说清绕行代价和额度', /多花 5 分钟/.test(reasonText) && /15 分钟额度以内/.test(reasonText), reasonText.replace(/\n/g, ' | '))
      check(
        '评分拆分和总分自洽',
        /4\.6 \/ 7/.test(reasonText) && /亮点质量 3\.5/.test(reasonText) && /口味契合 2\.1/.test(reasonText) && /绕行扣 1\.0/.test(reasonText),
        reasonText.replace(/\n/g, ' | '),
      )
    } else {
      // 换成结构断言：理由必须点到具体亮点名（不是「若干处」）、说清额度、给出拆分。
      // 亮点名从卡片标题取，理由里必须真的出现它 —— 这才是「回答了为什么」。
      const firstPoi = (await textOf(page.locator('.poi__name'))).trim()
      check('理由点名了沿途亮点', !!firstPoi && reasonText.includes(firstPoi), `${firstPoi} | ${reasonText.replace(/\n/g, ' ')}`)
      // 绕行代价有两种说法，取决于这次到底绕没绕：绕了要说清花了多少、在多少额度内；
      // 没绕（兜底数据常见）说的是「几乎不用绕，探索是顺路捡的」。两种都算讲清楚了，
      // 只钉「额度」会把后一种判成缺陷 —— 那句话本身没问题。
      check(
        '理由说清绕行代价',
        /额度/.test(reasonText) || /不用绕|顺路/.test(reasonText),
        reasonText.replace(/\n/g, ' | '),
      )
      check(
        '评分拆分三项齐全',
        /亮点质量/.test(reasonText) && /口味契合/.test(reasonText) && /绕行扣/.test(reasonText),
        reasonText.replace(/\n/g, ' | '),
      )
      skip('评分拆分对上桩的 4.6 分', '真后端分数不同')
    }
    // 叙事保留，但必须在理由下面收尾，不能顶掉理由
    const narrativeBox = await textOf(page.locator('.narrative'))
    if (usingStub) {
      check(
        '叙事退到理由下方收尾',
        narrativeBox.indexOf('理工咖啡小铺') < narrativeBox.indexOf('从大工沿海边走'),
        narrativeBox.replace(/\n/g, ' | '),
      )
    } else {
      // 不认具体文案，量 DOM 顺序：理由块必须排在叙事段落之前。
      const reasonsBeforeText = await page.evaluate(() => {
        const reasons = document.querySelector('.narrative__reasons')
        const text = document.querySelector('.narrative__text, .narrative p')
        if (!reasons || !text) return null
        return !!(reasons.compareDocumentPosition(text) & 4)
      })
      check(
        '叙事退到理由下方收尾',
        reasonsBeforeText !== false,
        `reasons 在叙事之前=${reasonsBeforeText}`,
      )
    }
    const meterText = await textOf(page.locator('.meter__value'))
    check('评分条数值不超过满分', !/([89]|\d\d)\.\d\/7/.test(meterText), meterText)

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

    // 收藏：桩故意 404（验前端降级不崩），真后端 round3 真的实现了 /api/trip/save。
    // 两种结果都可接受，不可接受的是「点了没反应」—— 所以断言「出现了某种回执」，
    // 再按内容分流。
    await page.locator('.bh-btn--accent').click()
    await page.waitForTimeout(800)
    const saveNote = (await textOf(page.locator('.result__actions'))) || ''
    if (/收藏失败/.test(saveNote)) {
      check('收藏接口缺失时提示失败而非崩溃', true)
    } else {
      check('收藏成功后给出回执', /已收藏|收藏成功/.test(saveNote), saveNote.replace(/\n/g, ' | '))
    }

    // T8-4：反馈的视觉确认必须对应真实结果。按钮变色只说明「你点了这个」，
    // 「后端真的学到了什么」得由文字说 —— 归因失败时写「已记住」是骗人。
    const likeButton = page.locator('.result__feedback button').first()
    await likeButton.click()
    await page.waitForTimeout(800)
    check('反馈按钮进入选中态', (await likeButton.getAttribute('aria-pressed')) === 'true')
    const feedbackNote = await textOf(page.locator('.result__feedback-note'))
    // 钉的类目要跟着演示数据走：SCENARIOS[0] 的 POI type 是「餐饮」「景点」，
    // 归并后 learned = ['餐饮','景点']。这里钉「餐饮」而不是把 mock 的 type
    // 改成「咖啡厅」去迁就断言 —— 演示数据不为了让测试好过而改。
    if (usingStub) {
      check(
        '反馈给出文字确认并说明学到了什么',
        /已记住/.test(feedbackNote) && /餐饮/.test(feedbackNote) && /加权/.test(feedbackNote),
        feedbackNote,
      )
    } else {
      // 真后端的类目由它自己的 POI type 决定，钉不了具体词。但「归因成功就说学到
      // 了什么、归因失败就别说已记住」这条不能松 —— 那正是 T8-4 要防的骗人文案。
      check('反馈给出文字回执', feedbackNote.trim().length > 0, feedbackNote)
      check(
        '文字回执与归因结果一致（说已记住就得点出类目）',
        !/已记住/.test(feedbackNote) || /加权/.test(feedbackNote),
        feedbackNote,
      )
    }
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

    // 第二张卡片只在有两个以上亮点时才存在。真后端的兜底数据可能只给一个，
    // 那时 nth(1).click() 会等到超时抛错 —— 整轮又断在这里。
    if (poiCount > 1) {
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
    } else {
      skip('点另一个亮点后地图平移过去', `只有 ${poiCount} 个亮点`)
      skip('途经点标记始终与附近亮点不同款', `只有 ${poiCount} 个亮点`)
      await page.locator('.poi').first().click()
      await page.waitForTimeout(300)
    }

    // R6：点击展开详情。桩里第一条 POI 字段齐全（地址 / 电话 / 营业时间 / 照片），
    // 第二条只有基础五字段 —— 后者不该出现「展开详情」，更不该点开一个空框。
    //
    // 真后端的 POI 字段由高德 / 兜底数据决定，哪张卡片齐全不确定。所以这里不再
    // 假定「第一张齐全、第二张不齐」，而是按 `.poi__toggle` 在场与否分组：
    // 有 toggle 的验展开链路，没 toggle 的验它确实不暴露 aria-expanded。
    // 一张齐全的都没有时整组 skip —— 那是数据缺失，不是缺陷。
    const rich = page.locator('.poi:has(.poi__toggle)').first()
    const plain = page.locator('.poi:not(:has(.poi__toggle))').first()
    const richCount = await page.locator('.poi:has(.poi__toggle)').count()
    const plainCount = await page.locator('.poi:not(:has(.poi__toggle))').count()

    if (plainCount > 0) {
      check('缺字段的亮点不提示展开', (await plain.locator('.poi__toggle').count()) === 0)
      check(
        '缺字段的亮点不暴露 aria-expanded',
        (await plain.getAttribute('aria-expanded')) === null,
        String(await plain.getAttribute('aria-expanded')),
      )
    } else {
      skip('缺字段的亮点不提示展开', '本轮所有亮点字段都齐全')
    }

    if (richCount === 0) {
      skip('字段齐全的亮点提示可展开', '本轮没有字段齐全的亮点')
      skip('详情区给出地址 / 电话 / 营业时间', '本轮没有字段齐全的亮点')
      skip('Enter / Space 展开收起详情', '本轮没有字段齐全的亮点')
    } else {
      // 上面 T2 的点击流程可能已经把它展开了。先收回去 —— 从「未展开」开始，
      // 下面的展开 / 收起才各自验到一次真实的状态切换。
      if ((await rich.getAttribute('aria-expanded')) === 'true') {
        await rich.click()
        await page.waitForTimeout(250)
      }

      check('字段齐全的亮点提示可展开', (await rich.locator('.poi__toggle').count()) === 1)
      check('未展开时 aria-expanded 为 false', (await rich.getAttribute('aria-expanded')) === 'false')

      await rich.click()
      await page.waitForTimeout(250)
      check('展开后 aria-expanded 为 true', (await rich.getAttribute('aria-expanded')) === 'true')
      const detailText = await textOf(rich.locator('.poi__detail'))
      if (usingStub) {
        check(
          '详情区给出地址 / 电话 / 营业时间',
          /凌工路 2 号/.test(detailText) && /0411-8470-9988/.test(detailText) && /07:30-21:00/.test(detailText),
          detailText.replace(/\n/g, ' | '),
        )
      } else {
        // 字段值不钉，但展开了就必须真的有内容 —— 点开一个空框是 R6 要防的事。
        check('展开后详情区有内容', detailText.trim().length > 0, detailText.replace(/\n/g, ' | '))
      }
      check('详情区不摆空占位', !/暂无|undefined|\[\]/.test(detailText), detailText.replace(/\n/g, ' | '))
      // 照片必须真的画出来（宽高非 0），不是一个加载失败的破图框
      if ((await rich.locator('.poi__photo').count()) > 0) {
        const photoBox = await rich.locator('.poi__photo').boundingBox()
        check('详情区渲染照片', !!photoBox && photoBox.width > 10 && photoBox.height > 10, JSON.stringify(photoBox))
      } else {
        skip('详情区渲染照片', '这条亮点没有照片字段')
      }
      await rich.screenshot({ path: `${OUT}/${viewport.name}-poi-expanded.png` })

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
    }

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
    check('可返回首页', await waitFor(page, '.home__form', 5000))
    check('返回后出现最近查询', (await page.locator('.history__item').count()) > 0)

    // 错误态：桩对含「无结果」的起点返回 404。真后端会拿它去做地理编码，
    // 认不出同样是 404「未找到可行路线」—— 两边的文案一致，所以这条不用分流。
    // 唯一的区别是真后端要打一次 Nominatim，慢一些，超时给足。
    await page.locator('input').first().fill('无结果起点')
    await page.locator('input').nth(1).fill('某个终点')
    await page.locator('button[type="submit"]').click()
    const gotAlert = await waitFor(page, '[role="alert"]', 20000)
    check('查不到时给出错误提示', gotAlert)
    check(
      '后端错误文案透传',
      (await textOf(page.locator('[role="alert"]'))).includes('未找到可行路线'),
      await textOf(page.locator('[role="alert"]')),
    )

    await page.screenshot({ path: `${OUT}/${viewport.name}-error.png`, fullPage: true })

    // T8-3：后端根本连不上时，fetch 抛的是 `TypeError: Failed to fetch`。
    // 以前这行英文被原样印在红条上，用户看不出是后端没起还是自己填错了。
    // 断言这两件事同时成立：换成了中文，且后端的中文 detail 没被这层翻译盖掉。
    await page.route('**/api/route/recommend', (r) => r.abort('connectionrefused'))
    await page.locator('input').first().fill('大连理工大学')
    await page.locator('input').nth(1).fill('星海广场')
    await page.locator('button[type="submit"]').click()
    await page.waitForTimeout(1500)
    const deadText = await textOf(page.locator('[role="alert"]'))
    check('后端连不上时给出中文提示', /连不上后端服务/.test(deadText), deadText)
    check('提示里没有英文原文', !/failed to fetch/i.test(deadText), deadText)
    await page.locator('.home__form').screenshot({ path: `${OUT}/${viewport.name}-dead-backend.png` })
    await page.unroute('**/api/route/recommend')

    const realErrors = consoleErrors.filter(
      (text) => !/tile\.openstreetmap|is\.autonavi|arcgisonline|ERR_|net::|Failed to load resource/i.test(text),
    )
    check('无脚本报错', realErrors.length === 0, realErrors.join(' | '))

    await page.close()
  }
} finally {
  await browser.close()
}

// SKIP 必须印在结尾，否则「全部通过」会把「一半断言根本没跑」说成成功 ——
// 那比 FAIL 更危险：看到绿色就不会再去查了。
if (skipped.length) {
  console.log(`\n跳过 ${skipped.length} 项（数据前提不成立）:`)
  for (const label of [...new Set(skipped)]) console.log(`  - ${label}`)
}
console.log(problems.length ? `\n失败 ${problems.length} 项` : '\n全部通过')
process.exit(problems.length ? 1 : 0)
