/* Stage 4 体检：用户可读性改造 + 3D 地球回归 + 浅色化 + 中文影评流
   检查项：
    0. 站点导航常驻（原系统棕渐变，浅色态）/ 页脚隐藏（保留导航的大屏）
    0b. 浅色化：令牌/文字/背景亮度断言（用户"整个页面改成浅色的"）
    1. 口碑星图：零滚动 + 3D 画布 + 标签常驻 + 读图图例 + 悬停解读卡
    2-4. 类型竞赛 / 口碑排名 / 年代流向（Flourish 图表接真实数据）
    5. 取景地图（3D 地球：globe.gl 画布 + 图例 HUD + 单层大气）
    6. 左右面板小切换 + 自动轮播
    7. 底部中文影评流（lang=zh · 带片名 · 95s 减速）
*/
const { chromium } = require('playwright')
;(async () => {
  const b = await chromium.launch({
    channel: 'chrome',
    args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader', '--disable-gpu-sandbox'],
  })
  const p = await b.newPage({ viewport: { width: 1920, height: 1080 } })
  const errs = []
  p.on('console', (m) => { if (m.type() === 'error') errs.push(m.text().slice(0, 200)) })
  p.on('pageerror', (e) => errs.push('PAGEERROR: ' + e.message.slice(0, 200)))
  await p.goto('http://localhost:5173/screen', { waitUntil: 'networkidle', timeout: 60000 })
  await p.waitForTimeout(5000)

  const shot = (n) => p.screenshot({ path: `${__dirname}/.stage4-${n}.png` })
  /* 普通 2D canvas（ECharts）可以 drawImage 采样；WebGL 的不行，只数尺寸 */
  const sample2d = (sel) => p.evaluate((s) => {
    const c = document.querySelector(s)
    if (!c) return null
    try {
      const c2 = document.createElement('canvas')
      c2.width = 200; c2.height = 120
      const cx = c2.getContext('2d')
      cx.drawImage(c, 0, 0, 200, 120)
      const d = cx.getImageData(0, 0, 200, 120).data
      let lit = 0
      for (let i = 0; i < d.length; i += 4) if (d[i] + d[i + 1] + d[i + 2] > 60) lit++
      return { size: `${c.width}x${c.height}`, lit }
    } catch (e) { return 'ERR ' + e.message }
  }, sel)

  const report = {}

  // ---- 0. 站点导航栏是否常驻（用户要求：点击影评洞察不跳转、保留导航） ----
  report.chrome = await p.evaluate(() => {
    const h = document.querySelector('.app-header')
    const tb = document.querySelector('.top-bar')
    const ft = document.querySelector('.app-footer')
    return {
      headerVisible: !!h && h.offsetParent !== null,
      // 浅色化后导航回归原系统棕渐变（isDark 恒 false）
      headerLight: !!h && !h.classList.contains('is-dark'),
      footerHidden: !ft || ft.offsetParent === null,
      headerH: h?.offsetHeight || 0,
      topBarTop: tb?.getBoundingClientRect().top || 0,
      navActive: document.querySelector('.app-nav__link.is-active')?.textContent?.trim() || null,
    }
  })

  // ---- 0b. 浅色化断言（用户 2026-10-19："整个这个页面还是改成浅色的"） ----
  report.light = await p.evaluate(() => {
    const cs = getComputedStyle(document.documentElement)
    const luma = (rgbStr) => {
      const m = rgbStr.match(/[\d.]+/g)
      if (!m) return null
      const [r, g, b] = m.slice(0, 3).map(Number)
      return Math.round(0.2126 * r + 0.7152 * g + 0.0722 * b)
    }
    const titleEl = document.querySelector('.hud-title__zh') || document.querySelector('.top-bar')
    return {
      uVoid: cs.getPropertyValue('--u-void').trim(),           // 应为暖白 #F6F1E6
      uText: cs.getPropertyValue('--u-text').trim(),           // 应为深咖 #3A2E20
      bgHasNebula: (getComputedStyle(document.querySelector('.dashboard-container')).backgroundImage || '').includes('radial-gradient'),
      titleLuma: titleEl ? luma(getComputedStyle(titleEl).color) : null,  // 标题应为暗色（<128）
    }
  })

  // ---- 1. 口碑星图 ----
  report.galaxy = await p.evaluate(() => {
    const de = document.documentElement
    return {
      scroll: [de.scrollHeight, de.clientHeight, de.scrollWidth, de.clientWidth],
      has3DCanvas: !!document.querySelector('.three-canvas-layer canvas'),
      // 标签栏常驻（5 个视图），图表面板在星系视图下应隐藏
      tabsAlwaysVisible: document.querySelectorAll('.stage-tabs .stage-tab').length,
      stagePanelHidden: document.querySelector('.stage-panel')?.offsetParent === null,
    }
  })

  // ---- 1b. 读图图例（用户反馈"看不懂星系在表达什么" → 常驻指南） ----
  report.galaxy.legend = await p.evaluate(() => {
    const el = document.querySelector('.galaxy-legend')
    return {
      visible: !!el && el.offsetParent !== null,
      stats: (el?.querySelector('.galaxy-legend__stats')?.textContent || '').replace(/\s+/g, ' ').trim(),
    }
  })
  await shot('1-galaxy')

  // ---- 1c. 悬停解读卡：星系中央区域网格采样，命中至少一次即通过 ----
  let tipHits = 0
  let tipSample = null
  for (const [dx, dy] of [[0, 0], [-70, -40], [70, -40], [-70, 40], [70, 40], [0, -80], [0, 80], [-120, 0], [120, 0]]) {
    await p.mouse.move(960 + dx, 540 + dy)
    await p.waitForTimeout(140)
    const t = await p.evaluate(() => {
      const el = document.querySelector('.galaxy-tip')
      return el ? (el.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 90) : null
    })
    if (t) { tipHits++; if (!tipSample) tipSample = t }
  }
  report.galaxy.tipHits = tipHits
  report.galaxy.tipSample = tipSample
  // 移出画布应收起
  await p.mouse.move(40, 300)
  await p.waitForTimeout(200)
  report.galaxy.tipHiddenOnLeave = await p.evaluate(() => !document.querySelector('.galaxy-tip'))

  // ---- 2. 类型竞赛 ----
  await p.click('button.stage-tab:has-text("类型竞赛")')
  await p.waitForTimeout(2500)
  report.race = {
    era: await p.evaluate(() => (document.querySelector('.race__era-num')?.textContent || '')),
    dots: await p.evaluate(() => document.querySelectorAll('.race__dot').length),
    activeDot: await p.evaluate(() => document.querySelector('.race__dot.is-on .race__dot-num')?.textContent || null),
    chart: await sample2d('.race__chart canvas'),
    dimmed: await p.evaluate(() => document.querySelector('.three-canvas-layer').classList.contains('is-dim')),
    axisLabels: await p.evaluate(() => document.querySelectorAll('.race__chart canvas').length),
  }
  await shot('2-race')

  // ---- 3. 口碑排名 ----
  await p.click('button.stage-tab:has-text("口碑排名")')
  await p.waitForTimeout(2500)
  report.rank = {
    note: await p.evaluate(() => (document.querySelector('.bump__note')?.textContent || '')),
    chart: await sample2d('.bump__chart canvas'),
  }
  await shot('3-rank')

  // ---- 4. 年代流向 ----
  await p.click('button.stage-tab:has-text("年代流向")')
  await p.waitForTimeout(2500)
  report.flow = {
    total: await p.evaluate(() => (document.querySelector('.flow__note')?.textContent || '')),
    chart: await sample2d('.flow__chart canvas'),
    sankeyPaths: await p.evaluate(() => document.querySelectorAll('.flow__chart canvas path').length),
  }
  await shot('4-flow')

  // ---- 5. 取景地图（3D 地球回归：globe.gl 懒加载 chunk + 1.4MB 贴图预载） ----
  await p.click('button.stage-tab:has-text("取景地图")')
  await p.waitForTimeout(9000)
  report.globe = await p.evaluate(() => {
    const gs = document.querySelector('.globe-stage')
    const c = gs?.querySelector('canvas')
    const hud = document.querySelector('.globe-hud')
    return {
      hasCanvas: !!c,
      canvasSize: c ? `${c.width}x${c.height}` : null,
      hudVisible: !!hud && hud.offsetParent !== null,
      hudText: (hud?.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 60),
    }
  })
  await shot('5-globe')

  // ---- 6. 左翼词云 / 右翼口碑 ----
  await p.click('.left-panel .panel-tab:nth-child(2)')
  await p.waitForTimeout(1800)
  report.cloud = { chart: await sample2d('.wcloud__chart canvas') }
  await shot('6-cloud')

  await p.click('.right-panel .panel-tab:nth-child(2)')
  await p.waitForTimeout(4000) // 等 RollingNumber 跑完再取分（中途取到的是动画中间值）
  report.genreRank = await p.evaluate(() => ({
    rows: document.querySelectorAll('.grank__row').length,
    // 读 RollingNumber 的 span（行 textContent 会把分数和"82 部"拼成假异常）
    scores: [...document.querySelectorAll('.grank__score .sp-num')].map((s) => s.textContent.trim()),
    firstName: (document.querySelector('.grank__name')?.textContent || '').trim(),
  }))
  await shot('7-genrerank')

  // ---- 7. 底部中文影评流（用户：太快 + 要中文） ----
  report.stream = await p.evaluate(() => {
    const track = document.querySelector('.stream-track')
    const chips = [...document.querySelectorAll('.stream-chip')]
    const first = chips[0]
    const cjk = (t) => (t.match(/[\u4e00-\u9fff]/g) || []).length
    const dur = parseFloat(getComputedStyle(track).animationDuration) || 95
    return {
      chipCount: chips.length,
      animDuration: getComputedStyle(track).animationDuration,
      pxPerSec: Math.round((track.scrollWidth / 2) / dur),   // 恒速断言：应 ≤ ~90
      firstText: (first?.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 60),
      firstCjk: first ? cjk(first.textContent) : 0,
      hasTitle: !!first?.querySelector('.stream-chip__title'),
      hasTag: !!first?.querySelector('.stream-chip__tag'),
      headText: (document.querySelector('.bottom-bar__head')?.textContent || '').replace(/\s+/g, ' ').trim(),
    }
  })

  // ---- 7. 自动轮播是否在跑（回星图后移开鼠标[悬停暂停是设计行为]，等 17s 应自动切到类型竞赛） ----
  await p.click('button.stage-tab:has-text("口碑星图")')
  await p.mouse.move(960, 500) // 移到画布空白区：避开 HUD，解除悬停暂停
  await p.waitForTimeout(17500)
  report.autoRotate = await p.evaluate(() => ({
    view: [...document.querySelectorAll('.stage-tab')].find((t) => t.classList.contains('is-on'))?.textContent?.trim(),
    stageVisible: document.querySelector('.stage-dock')?.offsetParent !== null,
  }))

  console.log(JSON.stringify(report, null, 1))
  console.log('ERRORS:', errs.length ? errs : 'none')
  await b.close()
})().catch((e) => { console.error('FAIL', e.message); process.exit(1) })
