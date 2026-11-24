/* Stage 3 体检：Flourish 式动态图表是否真的接上真实数据 + 依旧零滚动 */
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

  const shot = (n) => p.screenshot({ path: `${__dirname}/.stage3-${n}.png` })
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
      headerDark: !!h?.classList.contains('is-dark'),
      footerHidden: !ft || ft.offsetParent === null,
      headerH: h?.offsetHeight || 0,
      topBarTop: tb?.getBoundingClientRect().top || 0,
      navActive: document.querySelector('.app-nav__link.is-active')?.textContent?.trim() || null,
    }
  })

  // ---- 1. 星系视图 ----
  report.galaxy = await p.evaluate(() => {
    const de = document.documentElement
    return {
      scroll: [de.scrollHeight, de.clientHeight, de.scrollWidth, de.clientWidth],
      has3DCanvas: !!document.querySelector('.three-canvas-layer canvas'),
      // 标签栏常驻（用户 2026-10-19 反馈星系视图下看不到切换入口），
      // 但图表面板在星系视图下应隐藏
      tabsAlwaysVisible: document.querySelectorAll('.stage-tabs .stage-tab').length,
      stagePanelHidden: document.querySelector('.stage-panel')?.offsetParent === null,
    }
  })
  await shot('1-galaxy')

  // ---- 2. 条形竞赛 ----
  await p.click('button.stage-tab:has-text("竞赛")')
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
  await p.click('button.stage-tab:has-text("排名")')
  await p.waitForTimeout(2500)
  report.rank = {
    note: await p.evaluate(() => (document.querySelector('.bump__note')?.textContent || '')),
    chart: await sample2d('.bump__chart canvas'),
  }
  await shot('3-rank')

  // ---- 4. 桑基流向 ----
  await p.click('button.stage-tab:has-text("流向")')
  await p.waitForTimeout(2500)
  report.flow = {
    total: await p.evaluate(() => (document.querySelector('.flow__note')?.textContent || '')),
    chart: await sample2d('.flow__chart canvas'),
    sankeyPaths: await p.evaluate(() => document.querySelectorAll('.flow__chart canvas path').length),
  }
  await shot('4-flow')

  // ---- 5. 左翼词云 / 右翼口碑 ----
  await p.click('.left-panel .panel-tab:nth-child(2)')
  await p.waitForTimeout(1800)
  report.cloud = { chart: await sample2d('.wcloud__chart canvas') }
  await shot('5-cloud')

  await p.click('.right-panel .panel-tab:nth-child(2)')
  await p.waitForTimeout(1800)
  report.genreRank = await p.evaluate(() => ({
    rows: document.querySelectorAll('.grank__row').length,
    first: (document.querySelector('.grank__row')?.textContent || '').replace(/\s+/g, ' ').trim(),
  }))
  await shot('6-genrerank')

  // ---- 6. 自动轮播是否在跑（回星系后等 17s 应自动切到竞赛） ----
  await p.click('button.stage-tab:has-text("星系")')
  await p.waitForTimeout(17500)
  report.autoRotate = await p.evaluate(() => ({
    view: [...document.querySelectorAll('.stage-tab')].find((t) => t.classList.contains('is-on'))?.textContent?.trim(),
    stageVisible: document.querySelector('.stage-dock')?.offsetParent !== null,
  }))

  console.log(JSON.stringify(report, null, 1))
  console.log('ERRORS:', errs.length ? errs : 'none')
  await b.close()
})().catch((e) => { console.error('FAIL', e.message); process.exit(1) })
