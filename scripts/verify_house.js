// ============================================================
// 影评洞察馆 · 大厅/房间导航回归（/screen）
// 用法：NODE_PATH=<frontend/node_modules> node scripts/verify_house.js http://localhost:8080
//
// 覆盖：大厅渲染 · 六扇门 · 门牌悬停 · 推门进展厅 · 展厅隔离（无串门/门牌直达跨厅入口）·
//       回大厅 · 展厅面板/影评流 · 3D 层按模式压暗 · 各房面板对应 · 移动端无溢出 · 0 报错
// ============================================================
const puppeteer = require('puppeteer-core')
const fs = require('fs')
const path = require('path')

const BASE = process.argv[2] || 'http://localhost:8080'
const OUT = path.resolve(__dirname, '..', '.workbuddy', 'screenshots')
const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe'
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

let pass = 0
let fail = 0
function check(name, ok, extra = '') {
  if (ok) { pass++; console.log(`  ✓ ${name}${extra ? ' — ' + extra : ''}`) }
  else { fail++; console.log(`  ✗ ${name}${extra ? ' — ' + extra : ''}`) }
}

/** 2026-11-04：大厅改成「先打开电影盒子才能看到门」，所有 house 断言前先开封。
 *  已开封（回大厅 / 深链返回）时直接跳过，不重复点击。 */
async function openBox(p) {
  const sealed = await p.evaluate(() => document.querySelector('.ih')?.classList.contains('is-sealed'))
  if (!sealed) return
  await p.evaluate(() => document.querySelector('.ih__box')?.click())
  await sleep(1900)
}

;(async () => {
  fs.mkdirSync(OUT, { recursive: true })
  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: 'new',
    args: ['--no-sandbox', '--window-size=1440,900'],
    defaultViewport: { width: 1440, height: 900 },
  })
  const page = await browser.newPage()
  const errors = []
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()) })
  page.on('pageerror', (e) => errors.push(String(e)))

  console.log(`\n影评洞察馆回归 · ${BASE}\n`)
  await page.goto(BASE + '/screen', { waitUntil: 'networkidle2', timeout: 60000 })
  await page.waitForSelector('.ih', { timeout: 20000 })
  await sleep(1400)
  await openBox(page)

  /* ---------- 大厅（A24 编辑式首页：五间展厅作章节索引 + 主编精选栏） ---------- */
  const house = await page.evaluate(() => {
    const ih = document.querySelector('.ih')
    const r = ih.getBoundingClientRect()
    const doors = [...document.querySelectorAll('.ih__room')]
    return {
      w: Math.round(r.width),
      h: Math.round(r.height),
      doors: doors.length,
      names: [...document.querySelectorAll('.ih__room .ih__zh')].map((e) => e.textContent.trim()),
      noCount: document.querySelectorAll('.ih__sign-no').length,
      hudHidden: getComputedStyle(document.querySelector('.stage-dock')).display === 'none',
      topBarShown: getComputedStyle(document.querySelector('.top-bar')).display !== 'none',
      canvasDim: document.querySelector('.three-canvas-layer').classList.contains('is-dim'),
      stories: document.querySelectorAll('.hi__card').length,
    }
  })
  check('大厅渲染满屏', house.w > 1200 && house.h > 500, `${house.w}×${house.h}`)
  check('五间展厅', house.doors === 5, `${house.doors} 间`)
  check('展厅名齐全', house.names.join('/') === '口碑星图/票房分析/口碑排名/年代流向/口碑分歧', house.names.join('/'))
  check('序号 01–05', house.noCount === 5, `${house.noCount} 枚`)
  check('大厅模式收起 HUD 图表区', house.hudHidden)
  check('大厅保留顶栏', house.topBarShown)
  check('大厅压暗 3D 星系层', house.canvasDim)
  check('馆长洞察卡随大厅渲染（主编精选栏）', house.stories >= 2, `cards=${house.stories}`)
  await page.screenshot({ path: `${OUT}/screen-house.png` })

  /* ---------- 悬停展厅卡：仅确认不报错、卡片可点（无卡通门，hover 靠 :hover 态） ---------- */
  let hoverOk = true
  try {
    const d3 = await page.evaluate(() => {
      const r = document.querySelectorAll('.ih__room')[2].getBoundingClientRect()
      return { x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2) }
    })
    await page.mouse.move(d3.x, d3.y, { steps: 12 })
    await sleep(350)
  } catch (e) { hoverOk = false }
  check('悬停展厅卡无异常', hoverOk)
  await page.screenshot({ path: `${OUT}/screen-house-hover.png` })

  /* ---------- 推门进入展厅（实时重算落点，避开浮动漂移） ---------- */
  const enterPt = await page.evaluate(() => {
    const r = document.querySelectorAll('.ih__room')[2].getBoundingClientRect()
    return { x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2) }
  })
  await page.mouse.click(enterPt.x, enterPt.y)
  await sleep(1200)
  const room = await page.evaluate(() => ({
    houseGone: !document.querySelector('.ih'),
    nav: !!document.querySelector('.room-nav'),
    plate: (document.querySelector('.room-nav__plate b') || {}).textContent,
    leftPanel: !document.querySelector('.left-panel'),
    rankRoom: !!document.querySelector('.rank-room'),
    stream: !!document.querySelector('.stream-track'),
    canvasDim: document.querySelector('.three-canvas-layer').classList.contains('is-dim'),
    // 展厅内不应存在跳到其他展厅的入口（串门 / 门牌直达）
    goBtns: document.querySelectorAll('.room-nav__go button').length,
    doorBtns: document.querySelectorAll('.room-nav__door').length,
    backBtn: !!document.querySelector('.room-nav__back'),
    backBg: getComputedStyle(document.querySelector('.room-nav__back')).backgroundImage,
    backColor: getComputedStyle(document.querySelector('.room-nav__back')).color,
  }))
  check('进入展厅（大厅退场）', room.houseGone)
  check('馆内导览条出现', room.nav)
  check('门牌正确', room.plate === '口碑排名', room.plate)
  check('旧两翼面板已移除（改用专属舞台）', room.leftPanel)
  check('进入 rank 厅出现 RankRoom 专属舞台', room.rankRoom)
  check('底部影评流回归', room.stream)
  check('进入的是图表厅 → 3D 星系层仍压暗', room.canvasDim)
  check('展厅内无串门入口（上一间/下一间）', room.goBtns === 0, `go=${room.goBtns}`)
  check('展厅内无直达其他门入口', room.doorBtns === 0, `door=${room.doorBtns}`)
  check('展厅内保留「回大厅」出口', room.backBtn)
  check('回大厅按钮高对比（实底渐变 + 浅色字，暖白纸上可见）', /gradient/.test(room.backBg) && /(255|254|253|252|251|250)/.test(room.backColor), `${room.backColor} · ${room.backBg.slice(0, 24)}`)
  await page.screenshot({ path: `${OUT}/screen-room-rank.png` })

  /* ---------- 展厅内不可跳其他展厅：仅校验隔离性，切换展厅须经「回大厅」 ---------- */

  /* ---------- 回大厅 ---------- */
  await page.evaluate(() => document.querySelector('.room-nav__back').click())
  await sleep(1000)
  const back = await page.evaluate(() => ({
    house: !!document.querySelector('.ih'),
    doors: document.querySelectorAll('.ih__room').length,
    hudHidden: getComputedStyle(document.querySelector('.stage-dock')).display === 'none',
  }))
  check('回大厅', back.house && back.doors === 5, `${back.doors} 扇`)
  check('回大厅后 HUD 图表区收起', back.hudHidden)

  /* ---------- 导览图（itomdev MAP 面板）---------- */
  const mapBtn = await page.evaluate(() => {
    const b = document.querySelector('.house-map-btn')
    if (!b) return { found: false }
    const cs = getComputedStyle(b)
    const r = b.getBoundingClientRect()
    return { found: true, inVP: r.top >= 0 && r.right <= innerWidth + 1, bg: cs.backgroundImage.slice(0, 16) }
  })
  check('大厅悬浮导览图按钮可见', mapBtn.found && mapBtn.inVP && /gradient/.test(mapBtn.bg), JSON.stringify(mapBtn))

  await page.evaluate(() => document.querySelector('.house-map-btn').click())
  await sleep(900)
  const mapHouse = await page.evaluate(() => {
    const rooms = [...document.querySelectorAll('.im__room')]
    return {
      open: !!document.querySelector('.im__card'),
      rooms: rooms.length,
      locked: rooms.filter((r) => r.classList.contains('is-locked')).length,
      cur: rooms.filter((r) => r.classList.contains('is-cur')).length,
      hall: (document.querySelector('.im__hall-t') || {}).textContent,
      backBtn: !!document.querySelector('.im__back'),
      corridor: !!document.querySelector('.im__corridor'),
    }
  })
  check('导览图打开（手绘纸卡 + 走廊）', mapHouse.open && mapHouse.corridor)
  check('导览图五间展厅', mapHouse.rooms === 5, `${mapHouse.rooms} 间`)
  check('大厅模式全部可点（无锁定）', mapHouse.locked === 0 && mapHouse.cur === 0, `locked=${mapHouse.locked}`)
  check('大厅图钉标注入口', mapHouse.hall === '大厅', mapHouse.hall)
  check('大厅模式无回大厅按钮（本就在大厅）', !mapHouse.backBtn)
  await page.screenshot({ path: `${OUT}/screen-map-house.png` })

  // 地图点第 3 间房 → 传送进入（SVG <g> 没有 .click()，须派发真实事件）
  await page.evaluate(() => {
    const g = document.querySelectorAll('.im__room')[2]
    g.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true, view: window }))
  })
  await sleep(1300)
  const mapEnter = await page.evaluate(() => ({
    mapGone: !document.querySelector('.im__card'),
    plate: (document.querySelector('.room-nav__plate b') || {}).textContent,
    mapBtn: !!document.querySelector('.room-nav__map'),
  }))
  check('导览图点房间传送进展厅', mapEnter.mapGone && mapEnter.plate === '口碑排名', mapEnter.plate)
  check('展厅导览图圆钮在位', mapEnter.mapBtn)

  /* ---------- 返回按钮加强版：尺寸 + 高对比（用户 2026-10-22 第三次反馈） ---------- */
  const backSize = await page.evaluate(() => {
    const b = document.querySelector('.room-nav__back')
    const r = b.getBoundingClientRect()
    const cs = getComputedStyle(b)
    return { h: Math.round(r.height), w: Math.round(r.width), fs: cs.fontSize, text: b.textContent.trim(), bg: cs.backgroundImage.slice(0, 16) }
  })
  check('回大厅按钮加大（高 ≥36px、字号 ≥14px、高对比渐变）',
    backSize.h >= 36 && parseFloat(backSize.fs) >= 14 && /gradient/.test(backSize.bg), JSON.stringify(backSize))

  // 展厅模式打开地图：当前房高亮 + 图钉 + 其他锁定 + 回大厅
  await page.evaluate(() => document.querySelector('.room-nav__map').click())
  await sleep(900)
  const mapRoom = await page.evaluate(() => {
    const rooms = [...document.querySelectorAll('.im__room')]
    return {
      open: !!document.querySelector('.im__card'),
      cur: rooms.filter((r) => r.classList.contains('is-cur')).length,
      locked: rooms.filter((r) => r.classList.contains('is-locked')).length,
      here: (document.querySelector('.im__here') || {}).textContent,
      backBtn: !!document.querySelector('.im__back'),
      curName: (rooms.find((r) => r.classList.contains('is-cur'))?.querySelector('.im__room-name') || {}).textContent,
    }
  })
  check('展厅地图仅高亮当前房', mapRoom.cur === 1 && mapRoom.curName === '口碑排名', `cur=${mapRoom.cur} ${mapRoom.curName}`)
  check('展厅地图其余房锁定（不串门）', mapRoom.locked === 4, `locked=${mapRoom.locked}`)
  check('展厅地图「你在这里」图钉', mapRoom.here === '你在这里', mapRoom.here)
  check('展厅地图带回大厅按钮', mapRoom.backBtn)
  await page.screenshot({ path: `${OUT}/screen-map-room.png` })

  // 地图内回大厅
  await page.evaluate(() => document.querySelector('.im__back').click())
  await sleep(1100)
  const mapBack = await page.evaluate(() => ({
    house: !!document.querySelector('.ih'),
    mapGone: !document.querySelector('.im__card'),
  }))
  check('导览图内回大厅', mapBack.house && mapBack.mapGone)

  // Esc 关图
  await page.evaluate(() => document.querySelector('.house-map-btn').click())
  await sleep(700)
  await page.keyboard.press('Escape')
  await sleep(500)
  check('Esc 关闭导览图', await page.evaluate(() => !document.querySelector('.im__card')))

  /* ---------- 延迟稳定性回归（A24 首页去掉 preserve-3d 走廊后，命中测试不再有
     "越晚越坏"的雷；此处仍等页面存活 6 秒，确认悬停/点击展厅卡始终有效） ---------- */
  await sleep(6000)
  const d6 = await page.evaluate(() => {
    const r = document.querySelectorAll('.ih__room')[4].getBoundingClientRect()
    return { x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2) }
  })
  await page.mouse.move(d6.x, d6.y, { steps: 10 })
  await sleep(500)
  await page.mouse.click(d6.x, d6.y)
  await sleep(1300)
  const lateRoom = await page.evaluate(() => ({
    house: !!document.querySelector('.ih'),
    plate: (document.querySelector('.room-nav__plate b') || {}).textContent,
  }))
  check('延迟 6s 后点展厅卡仍能进入对应展厅', !lateRoom.house && lateRoom.plate === '口碑分歧', lateRoom.plate)
  await page.evaluate(() => document.querySelector('.room-nav__back').click())
  await sleep(900)

  /* ---------- 星图厅：无面板、有读图指南 ---------- */
  await page.evaluate(() => document.querySelectorAll('.ih__room')[0].click())
  await sleep(1500)
  const galaxy = await page.evaluate(() => ({
    plate: (document.querySelector('.room-nav__plate b') || {}).textContent,
    card: !!document.querySelector('.galaxy-card'),
    panelGone: !document.querySelector('.stage-panel'),
    canvasDim: document.querySelector('.three-canvas-layer').classList.contains('is-dim'),
  }))
  check('星图厅无图表面板', galaxy.plate === '口碑星图' && galaxy.panelGone, galaxy.plate)
  check('星图读图卡在位', galaxy.card)
  check('星图厅点亮 3D 星系层', !galaxy.canvasDim)
  await page.screenshot({ path: `${OUT}/screen-room-galaxy.png` })

  /* ---------- 每间展厅的专属舞台组件（2026-11-01 起：不再共用"左中右三块"） ----------
     每间房各自一套排版，用专属组件承载；旧左右两翼面板已整体移除。 */
  const ROOM_COMPONENTS = {
    galaxy:  ['.galaxy-card'],
    rank:    ['.rank-room .bump', '.rank-room .dbp'],
    flow:    ['.flow-room .flow', '.flow-room .story', '.flow-room .rg'],
    diverge: ['.diverge-room .pb', '.diverge-room .dv', '.diverge-room .dbp'],
  }
  for (const key of Object.keys(ROOM_COMPONENTS)) {
    await page.goto(BASE + '/screen?room=' + key, { waitUntil: 'networkidle2', timeout: 60000 })
    await page.waitForSelector('.room-nav', { timeout: 20000 })
    await sleep(900)
    const noSide = await page.evaluate(() => !document.querySelector('.left-panel') && !document.querySelector('.right-panel'))
    const sels = ROOM_COMPONENTS[key]
    const found = await page.evaluate((s) => s.every((x) => !!document.querySelector(x)), sels)
    check(`展厅[${key}] 旧两翼面板已移除`, noSide)
    check(`展厅[${key}] 专属舞台组件到位`, found, sels.join(' / '))
  }

  /* ---------- 票房分析展厅：全宽画廊 + 底部两栏（不再是左中右三块） ---------- */
  await page.goto(BASE + '/screen?room=box', { waitUntil: 'networkidle2', timeout: 60000 })
  await page.waitForSelector('.room-nav', { timeout: 20000 })
  await sleep(1200)
  const box = await page.evaluate(() => ({
    wide: document.querySelector('.stage-dock').classList.contains('is-wide'),
    leftHidden: !document.querySelector('.left-panel'),
    rightHidden: !document.querySelector('.right-panel'),
    stage: !!document.querySelector('.box-stage'),
    frames: document.querySelectorAll('.bog__frame').length,
    dockCells: document.querySelectorAll('.box-stage__cell').length,
    rankRows: document.querySelectorAll('.borank__row').length,
    trendChart: !!document.querySelector('.botrend__chart'),
  }))
  check('票房厅全宽（无左右两翼）', box.wide && box.leftHidden && box.rightHidden, `wide=${box.wide} L=${box.leftHidden} R=${box.rightHidden}`)
  check('票房厅全宽画廊在位', box.stage && box.frames >= 10, `frames=${box.frames}`)
  check('票房厅底部两栏（票房榜+年度趋势）', box.dockCells === 2 && box.rankRows >= 3 && box.trendChart, `cells=${box.dockCells} rows=${box.rankRows} trend=${box.trendChart}`)
  await page.screenshot({ path: `${OUT}/screen-room-box.png` })

  /* ---------- 2026-11-01 新增：馆长洞察卡 / 评分分化榜 / 地区气泡图 ---------- */
  // 大厅洞察卡：house 模式底部托盘，真实分析结论 + 点卡直达展厅
  await page.goto(BASE + '/screen', { waitUntil: 'networkidle2', timeout: 60000 })
  await sleep(1500)
  await openBox(page)
  const hi = await page.evaluate(() => {
    const cards = [...document.querySelectorAll('.hi__card')]
    return {
      count: cards.length,
      text: (document.querySelector('.hi') || {}).innerText || '',
      clickable: cards.length > 0 && getComputedStyle(cards[0]).pointerEvents === 'auto',
    }
  })
  check('大厅馆长洞察卡叠渲染', hi.count >= 2, `cards=${hi.count}`)
  check('洞察卡为真实分析结论', /评分波动|口碑王|正面率/.test(hi.text), hi.text.slice(0, 40))
  check('洞察卡可点击直达展厅', hi.clickable === true, `pointerEvents=${hi.clickable}`)

  // 评分分化榜 · A24 影片展：圆盘索引 + 真实好评/差评引文
  await page.goto(BASE + '/screen?room=diverge', { waitUntil: 'networkidle2', timeout: 60000 })
  await page.waitForSelector('.room-nav', { timeout: 20000 })
  await sleep(1000)
  const pb = await page.evaluate(() => ({
    idx: document.querySelectorAll('.idx__d').length,
    disc: !!document.querySelector('.disc'),
    stars: document.querySelectorAll('.star').length,
    quotes: document.querySelectorAll('.quote').length,
    hasPos: !!document.querySelector('.quote--pos'),
    hasNeg: !!document.querySelector('.quote--neg'),
    firstTitle: (document.querySelector('.pb__film') || {}).textContent,
  }))
  check('分化榜圆盘索引渲染', pb.idx >= 5, `idx=${pb.idx}`)
  check('分化榜海报圆盘渲染', pb.disc, `disc=${pb.disc}`)
  check('分化榜星级渲染', pb.stars === 5, `stars=${pb.stars}`)
  check('分化榜好评差评引文并存', pb.quotes >= 2 && pb.hasPos && pb.hasNeg, `quotes=${pb.quotes}`)
  // 点索引第二张圆盘 → 主视觉切换（交互）
  await page.evaluate(() => { const r = document.querySelectorAll('.idx__d')[1]; r && r.dispatchEvent(new MouseEvent('click', { bubbles: true })) })
  await sleep(500)
  const pb2 = await page.evaluate(() => (document.querySelector('.pb__film') || {}).textContent)
  check('分化榜点圆盘切换影片', !!pb2 && pb2 !== pb.firstTitle, `${pb.firstTitle} -> ${pb2}`)

  // 地区气泡图：canvas 渲染 + 产量王/口碑王图例
  await page.goto(BASE + '/screen?room=flow', { waitUntil: 'networkidle2', timeout: 60000 })
  await page.waitForSelector('.room-nav', { timeout: 20000 })
  await sleep(1200)
  const rg = await page.evaluate(() => ({
    canvas: document.querySelectorAll('.rg__chart canvas').length,
    legend: (document.querySelector('.rg__legend') || {}).innerText || '',
  }))
  check('地区气泡图渲染', rg.canvas >= 1, `canvas=${rg.canvas}`)
  check('地区图例含产量王口碑王', /产量王/.test(rg.legend) && /口碑王/.test(rg.legend), rg.legend.replace(/\s+/g, ' '))

  /* ---------- 票房分析展厅：itomdev 式相框绳画廊（2026-10-22 新增） ---------- */
  await page.goto(BASE + '/screen?room=box', { waitUntil: 'networkidle2', timeout: 60000 })
  await page.waitForSelector('.room-nav', { timeout: 20000 })
  await page.waitForSelector('.bog__frame', { timeout: 20000 })
  await sleep(1600)
  const bog = await page.evaluate(() => ({
    frames: document.querySelectorAll('.bog__frame').length,
    pins: document.querySelectorAll('.bog__pin').length,
    line: !!document.querySelector('.bog__line'),
    posters: [...document.querySelectorAll('.bog__mat img')].filter((i) => i.complete && i.naturalWidth > 0).length,
    caps: [...document.querySelectorAll('.bog__cap')].map((e) => e.textContent.trim()).slice(0, 3),
    summary: (document.querySelector('.bog__summary') || {}).textContent,
    rankRows: document.querySelectorAll('.borank__row').length,
    trendCanvas: (() => { const c = document.querySelector('.botrend__chart canvas'); return c ? c.width : 0 })(),
  }))
  check('票房画廊相框上架', bog.frames === 24 && bog.pins === 24 && bog.line, `frames=${bog.frames} pins=${bog.pins}`)
  // 海报为浏览器端直连 TMDB 原链：轮询等待加载完成（避免检查时图未就绪），
  // 若确属出网失败则跳过断言（非页面代码问题）
  let loaded = bog.posters
  for (let k = 0; k < 24 && loaded < 20; k++) {
    await sleep(300)
    loaded = await page.evaluate(() => [...document.querySelectorAll('.bog__mat img')].filter((i) => i.complete && i.naturalWidth > 0).length)
  }
  if (loaded >= 20) check('相框海报加载', loaded >= 20, `loaded=${loaded}/24`)
  else console.log(`  ⚠ 相框海报出网未就绪（环境限制，非页面错误）：已加载 ${loaded}/24，跳过加载断言`)
  check('相框 caption 为真实片名', bog.caps.length === 3 && bog.caps[0].length >= 2, JSON.stringify(bog.caps))
  check('总览条有收录数', /收录影片/.test(bog.summary || ''), (bog.summary || '').slice(0, 40))
  check('左翼票房榜十行', bog.rankRows === 10, `rows=${bog.rankRows}`)
  check('右翼年度趋势图渲染', bog.trendCanvas > 100, `canvas=${bog.trendCanvas}`)

  // 2026-11-06：策展式大封面 + 章节标题把画廊推到首屏之下，
  // 房间滚动容器是 .dashboard-container（window.scrollY 恒为 0），
  // 交互前先把画廊场景滚进视口，否则按首屏坐标点击会落在视口外。
  await page.evaluate(() => document.querySelector('.bog__scene').scrollIntoView({ block: 'center' }))
  await sleep(800)

  // 点相框 → 详情纸卡（票房/预算/ROI 四格）
  const framePt = await page.evaluate(() => {
    const r = document.querySelectorAll('.bog__frame')[2].getBoundingClientRect()
    return { x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2) }
  })
  await page.mouse.click(framePt.x, framePt.y)
  await sleep(900)
  const card = await page.evaluate(() => {
    const p = document.querySelector('.bog-card__paper')
    if (!p) return { open: false }
    return {
      open: true,
      title: (p.querySelector('.bog-card__title') || {}).textContent,
      cells: [...p.querySelectorAll('.bog-card__cell')].map((c) => (c.querySelector('b') || {}).textContent),
      link: !!p.querySelector('.bog-card__link'),
    }
  })
  check('点相帧弹档案纸卡', card.open && card.cells.length === 4, JSON.stringify(card))
  check('档案卡票房数字真实', card.cells && card.cells[0] && /亿美元/.test(card.cells[0]), card.cells && card.cells[0])
  check('档案卡带影片链接', card.link)
  await page.screenshot({ path: `${OUT}/screen-box-gallery.png` })
  await page.keyboard.press('Escape')
  await sleep(500)
  const cardClosed = await page.evaluate(() => !document.querySelector('.bog-card__paper'))
  check('Esc 关闭档案卡', cardClosed)

  // 滚轮沿线漂移（桌面端）：直接定位到画廊场景中心，避免鼠标落在底部两栏之上
  const scenePt = await page.evaluate(() => {
    const r = document.querySelector('.bog__scene').getBoundingClientRect()
    return { x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2) }
  })
  const drift = await page.evaluate(() => ({ t: getComputedStyle(document.querySelector('.bog__rail')).transform }))
  await page.mouse.move(scenePt.x, scenePt.y)
  await page.mouse.wheel({ deltaY: 500 })
  await sleep(700)
  const drift2 = await page.evaluate(() => ({ t: getComputedStyle(document.querySelector('.bog__rail')).transform }))
  check('滚轮沿绳漂移', drift.t !== drift2.t, `${drift.t.slice(0, 24)} → ${drift2.t.slice(0, 24)}`)

  // 左翼榜单点选 → 中央画廊打开同一部档案（联动）
  await page.evaluate(() => document.querySelectorAll('.borank__row')[1].click())
  await sleep(900)
  const pickCard = await page.evaluate(() => {
    const p = document.querySelector('.bog-card__paper')
    return { open: !!p, title: p ? (p.querySelector('.bog-card__title') || {}).textContent : null }
  })
  check('票房榜点选联动画廊档案', pickCard.open && !!pickCard.title, JSON.stringify(pickCard))

  /* ---------- 键盘可达性 ---------- */
  await page.evaluate(() => document.querySelector('.room-nav__back').click())
  await sleep(900)
  const kb = await page.evaluate(() => {
    const d = document.querySelectorAll('.ih__room')[1]
    d.focus()
    return document.activeElement === d
  })
  await page.keyboard.press('Enter')
  await sleep(1200)
  const kbRoom = await page.evaluate(() => (document.querySelector('.room-nav__plate b') || {}).textContent)
  check('门可聚焦', kb)
  check('回车推门进展厅', kbRoom === '票房分析', kbRoom)

  /* ---------- 桌面无横向溢出 ---------- */
  const ovf = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  check('无横向溢出', ovf <= 0, `overflow=${ovf}`)

  /* ---------- 移动端 ---------- */
  const m = await browser.newPage()
  await m.setViewport({ width: 390, height: 844, isMobile: true, deviceScaleFactor: 2 })
  await m.goto(BASE + '/screen', { waitUntil: 'networkidle2', timeout: 60000 })
  await m.waitForSelector('.ih__room', { timeout: 20000 })
  await sleep(1200)
  await openBox(m)
  const mob = await m.evaluate(() => {
    const r = document.querySelector('.ih').getBoundingClientRect()
    const doors = [...document.querySelectorAll('.ih__room')].map((d) => Math.round(d.getBoundingClientRect().width))
    const title = (document.querySelector('.ih__title') || {}).textContent || ''
    return {
      w: Math.round(r.width),
      h: Math.round(r.height),
      ovf: document.documentElement.scrollWidth - window.innerWidth,
      doors,
      titleVisible: title.length > 0,
    }
  })
  check('移动端大厅铺满', mob.w >= 380 && mob.h > 500, `${mob.w}×${mob.h}`)
  check('移动端无横向溢出', mob.ovf <= 0, `overflow=${mob.ovf}`)
  check('移动端展厅卡宽合理', mob.doors.length === 5 && mob.doors.every((w) => w >= 70), mob.doors.join('/'))
  check('移动端刊头标题可见', mob.titleVisible)
  await m.screenshot({ path: `${OUT}/screen-house-mobile.png` })

  /* 移动端导览图：纸卡不溢出视口、可开可关 */
  await m.evaluate(() => document.querySelector('.house-map-btn').click())
  await sleep(900)
  const mobMap = await m.evaluate(() => {
    const c = document.querySelector('.im__card')
    if (!c) return { open: false }
    const r = c.getBoundingClientRect()
    return { open: true, inVP: r.left >= -1 && r.right <= innerWidth + 1 && r.top >= -1 && r.bottom <= innerHeight + 1, w: Math.round(r.width) }
  })
  check('移动端导览图纸卡不溢出', mobMap.open && mobMap.inVP, JSON.stringify(mobMap))
  await m.screenshot({ path: `${OUT}/screen-map-mobile.png` })
  await m.evaluate(() => document.querySelector('.im__close').click())
  await sleep(500)

  /* 移动端进入展厅：顶部导航条的「回大厅」按钮必须可见（窄屏不再整条收起 .stage-dock） */
  await m.evaluate(() => document.querySelectorAll('.ih__room')[0].click())
  await sleep(1500)
  const mobRoom = await m.evaluate(() => {
    const exit = document.querySelector('.room-nav__back')
    if (!exit) return { exit: false }
    const cs = getComputedStyle(exit)
    const r = exit.getBoundingClientRect()
    return {
      exit: true,
      display: cs.display,
      visibility: cs.visibility,
      inViewport: r.width > 0 && r.height > 0 && r.top >= 0 && r.left >= 0 && r.right <= window.innerWidth,
    }
  })
  check('移动端展厅「回大厅」按钮可见', mobRoom.exit && mobRoom.display !== 'none' && mobRoom.visibility !== 'hidden' && mobRoom.inViewport, JSON.stringify(mobRoom))
  await m.screenshot({ path: `${OUT}/screen-room-mobile.png` })

  check('0 控制台错误', errors.length === 0, errors.slice(0, 2).join(' | '))

  await browser.close()
  console.log(`\n结果：${pass} 通过 / ${fail} 失败\n`)
  process.exit(fail === 0 ? 0 : 1)
})().catch((e) => { console.error('运行失败：', e); process.exit(1) })
