// ============================================================
// 类型混搭页「天气舞台 + 海报扇」回归
//
// 覆盖 2026-10-21 这一轮踩过的坑：
//   1. 天气标签曾经被 .ws__overlay 的留白盖住 → 点不动（z-index 必须高于插槽层）
//   2. 拖拽海报之后浏览器仍派发一次 click（起落点不同 → 目标是公共祖先），
//      若不按位移过滤，拖一下就把天气也换了
//   3. 方向键属于海报扇，场景不能抢（舞台版 onKey 直接 return）
//   4. 场景高度要由扇子撑开，不能再写死 clamp，否则移动端空一大片
//
// 用法：node scripts/verify_mix_stage.js [baseUrl]
// 需要 NODE_PATH 指向 frontend/node_modules
// ============================================================
const puppeteer = require('puppeteer-core')

const BASE = process.argv[2] || 'http://localhost:8080'
const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe'
const OUT = '.workbuddy/screenshots'
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

let pass = 0
let fail = 0
function check(name, ok, detail = '') {
  if (ok) { pass++; console.log(`PASS  ${name}${detail ? '  — ' + detail : ''}`) }
  else { fail++; console.log(`FAIL  ${name}${detail ? '  — ' + detail : ''}`) }
}

async function pickGenres(page, labels) {
  await page.evaluate((ls) => {
    const tags = [...document.querySelectorAll('.mix-pool .gtag')]
    for (const l of ls) {
      const el = tags.find((t) => t.textContent.trim() === l)
      el && el.click()
    }
  }, labels)
  await page.waitForSelector('.ws', { timeout: 25000 })
  await sleep(2600)
}

const state = (page) => page.evaluate(() => ({
  sky: document.querySelector('.ws')?.dataset.sky,
  title: document.querySelector('.fan__title')?.textContent || '',
  on: document.querySelector('.ws__tab.is-on')?.textContent?.trim(),
}))

;(async () => {
  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: 'new',
    args: ['--no-sandbox', '--force-device-scale-factor=1'],
    defaultViewport: { width: 1440, height: 980 },
  })
  const page = await browser.newPage()
  const errs = []
  page.on('console', (m) => { if (m.type() === 'error') errs.push(m.text().slice(0, 120)) })
  page.on('pageerror', (e) => errs.push('PAGEERROR ' + e.message.slice(0, 120)))

  await page.goto(BASE + '/mix', { waitUntil: 'networkidle2', timeout: 60000 })
  await sleep(700)
  await pickGenres(page, ['悬疑', '科幻'])

  // 1. 结构
  const geo = await page.evaluate(() => {
    const ws = document.querySelector('.ws')
    const fan = document.querySelector('.fan')
    const r = ws.getBoundingClientRect()
    const f = fan.getBoundingClientRect()
    return {
      wsH: Math.round(r.height), wsW: Math.round(r.width),
      fanH: Math.round(f.height),
      inside: ws.contains(fan),
      bare: fan.classList.contains('fan--bare'),
      cards: document.querySelectorAll('.fan__card').length,
      tabs: document.querySelectorAll('.ws__tab').length,
      stars: document.querySelectorAll('.ws__star').length,
      drops: document.querySelectorAll('.ws__drop').length,
    }
  })
  check('海报扇已放进天气场景', geo.inside && geo.bare, `${geo.wsW}×${geo.wsH}`)
  check('场景高度由扇子撑开', geo.wsH >= geo.fanH && geo.wsH - geo.fanH < 140, `场景 ${geo.wsH} / 扇子 ${geo.fanH}`)
  check('四个天气标签在位', geo.tabs === 4, `${geo.tabs} 个`)
  check('结果卡片已渲染', geo.cards >= 3, `${geo.cards} 张`)

  // 2. 标签切换（曾经被插槽层盖住点不到）
  const tabs = await page.$$('.ws__tab')
  const s0 = await state(page)
  await tabs[1].click(); await sleep(1200)
  const s1 = await state(page)
  check('点「夜」切到夜晚', s1.sky === 'night' && s1.on === '夜', `${s0.sky} → ${s1.sky}`)

  // 3. 四态截图（顺带确认每种状态都能落到 data-sky）
  for (const [i, key] of [[0, 'day'], [1, 'night'], [2, 'rainbow'], [3, 'rain']]) {
    await tabs[i].click(); await sleep(1300)
    const st = await state(page)
    check(`「${['晴', '夜', '彩虹', '雨'][i]}」状态生效`, st.sky === key, st.sky)
    await page.evaluate(() => document.querySelector('.ws').scrollIntoView({ block: 'center' }))
    await sleep(350)
    await page.screenshot({ path: `${OUT}/mix-stage-${key}.png` })
  }
  await tabs[0].click(); await sleep(1000)

  // 4. 拖拽：换片，但不能顺手换天气
  const box = await page.evaluate(() => {
    const r = document.querySelector('.fan__stage').getBoundingClientRect()
    const s = document.querySelector('.ws').getBoundingClientRect()
    return {
      cx: Math.round(r.left + r.width / 2), cy: Math.round(r.top + r.height / 2),
      sx: Math.round(s.left + 26), sy: Math.round(s.top + 46),
    }
  })
  const dragBefore = await state(page)
  await page.mouse.move(box.cx, box.cy)
  await page.mouse.down()
  for (let i = 1; i <= 12; i++) { await page.mouse.move(box.cx - i * 22, box.cy, { steps: 1 }); await sleep(16) }
  await page.mouse.up()
  await sleep(1000)
  const dragAfter = await state(page)
  check('拖拽换片', dragBefore.title !== dragAfter.title, `${dragBefore.title} → ${dragAfter.title}`)
  check('拖拽不会误切天气', dragBefore.sky === dragAfter.sky, `${dragBefore.sky} → ${dragAfter.sky}`)

  // 5. 点空白换天气（海报扇遮不住的天空区域）
  const skyBefore = await state(page)
  await page.mouse.click(box.sx, box.sy)
  await sleep(900)
  const skyAfter = await state(page)
  check('点空白处换天气', skyBefore.sky !== skyAfter.sky, `${skyBefore.sky} → ${skyAfter.sky}`)

  // 6. 方向键只归海报扇
  await page.evaluate(() => document.querySelector('.fan').focus())
  const keyBefore = await state(page)
  await page.keyboard.press('ArrowRight')
  await sleep(700)
  const keyAfter = await state(page)
  check('方向键翻片', keyBefore.title !== keyAfter.title, `${keyBefore.title} → ${keyAfter.title}`)
  check('方向键不换天气', keyBefore.sky === keyAfter.sky, `${keyBefore.sky} → ${keyAfter.sky}`)

  // 7. 网格视图仍可用
  await page.evaluate(() => {
    const btns = [...document.querySelectorAll('.view-toggle__btn')]
    btns.find((b) => b.textContent.trim() === '网格')?.click()
  })
  await sleep(600)
  const grid = await page.evaluate(() => ({
    cards: document.querySelectorAll('.mixcard').length,
    ws: !!document.querySelector('.ws'),
  }))
  check('切到网格视图', grid.cards >= 3 && !grid.ws, `${grid.cards} 张卡片`)

  // 8. 移动端
  const m = await browser.newPage()
  await m.setViewport({ width: 390, height: 844, isMobile: true, deviceScaleFactor: 2 })
  await m.goto(BASE + '/mix', { waitUntil: 'networkidle2', timeout: 60000 })
  await sleep(700)
  await pickGenres(m, ['悬疑', '科幻'])
  const mg = await m.evaluate(() => {
    const ws = document.querySelector('.ws').getBoundingClientRect()
    const ctrl = document.querySelector('.ws__ctrl').getBoundingClientRect()
    const info = document.querySelector('.fan__info').getBoundingClientRect()
    return {
      w: Math.round(ws.width), h: Math.round(ws.height),
      overflow: document.documentElement.scrollWidth - window.innerWidth,
      ctrlInside: ctrl.bottom <= ws.bottom + 1,
      infoAboveCtrl: info.bottom <= ctrl.top + 1,
    }
  })
  check('移动端无横向溢出', mg.overflow <= 0, `溢出 ${mg.overflow}px`)
  check('移动端场景不塌', mg.h >= 430, `${mg.w}×${mg.h}`)
  check('标签不压住片名块', mg.infoAboveCtrl && mg.ctrlInside, `场景内 ${mg.ctrlInside}`)
  await m.evaluate(() => document.querySelector('.ws').scrollIntoView({ block: 'center' }))
  await sleep(500)
  await m.screenshot({ path: `${OUT}/mix-stage-mobile.png` })

  // 图片代理 502 单列：容器出网抓不到 TMDB/豆瓣图床（宿主机可直连、容器被拦），
  // 属部署环境限制，前端已用占位卡面兜底，不算页面功能错误
  const img502 = errs.filter((e) => e.includes('502'))
  const real = errs.filter((e) => !img502.includes(e))
  if (img502.length) console.log(`  [warn] 海报代理 502 ${img502.length} 条（容器出网限制，前端已兜底占位）`)
  check('全程无控制台错误', real.length === 0, real.slice(0, 2).join(' | '))

  console.log(`\n==== ${pass}/${pass + fail} 通过 ====`)
  await browser.close()
  process.exit(fail ? 1 : 0)
})()
