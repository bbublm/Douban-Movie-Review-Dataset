// /mix 海报扇：可视化 + 交互回归
const puppeteer = require('puppeteer-core')

const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe'
const BASE = process.argv[2] || 'http://127.0.0.1:5173'
const OUT = '.workbuddy/screenshots'
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

;(async () => {
  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: 'new',
    args: ['--no-sandbox'],
    defaultViewport: { width: 1440, height: 900 },
  })
  const page = await browser.newPage()
  const errors = []
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text().slice(0, 180)) })
  page.on('pageerror', (e) => errors.push('pageerror: ' + e.message.slice(0, 180)))

  const results = []
  const check = (n, ok, d = '') => {
    results.push(ok)
    console.log(`${ok ? 'PASS' : 'FAIL'}  ${n}${d ? '  — ' + d : ''}`)
  }

  await page.goto(`${BASE}/mix`, { waitUntil: 'networkidle2', timeout: 60000 })
  await page.waitForSelector('.gtag', { timeout: 20000 })

  // 选两个类型（科幻 + 动作）
  const tags = await page.$$eval('.gtag', (els) => els.map((e) => ({ t: e.textContent.trim(), x: e.getBoundingClientRect().x + e.getBoundingClientRect().width / 2, y: e.getBoundingClientRect().y + e.getBoundingClientRect().height / 2 })))
  for (const want of ['科幻', '动作']) {
    const t = tags.find((x) => x.t === want)
    if (t) { await page.mouse.click(t.x, t.y); await sleep(220) }
  }
  await page.waitForSelector('.fan', { timeout: 20000 })
  await sleep(1800)

  const box = await page.$eval('.fan', (el) => {
    const r = el.getBoundingClientRect()
    return { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) }
  })
  await page.screenshot({ path: `${OUT}/mix-fan-0.png`, clip: { x: box.x - 8, y: Math.max(0, box.y - 8), width: box.w + 16, height: Math.min(box.h + 16, 900 - Math.max(0, box.y - 8)) } })
  await page.screenshot({ path: `${OUT}/mix-fan-page.png` })

  check('海报扇已渲染', box.w > 600 && box.h > 400, `${box.w}×${box.h}`)

  const cards = await page.$$eval('.fan__card', (els) => els.map((e) => {
    const s = getComputedStyle(e)
    return { t: s.transform, f: s.filter, o: s.opacity, w: Math.round(e.getBoundingClientRect().width) }
  }))
  check('海报数量', cards.length >= 2, `${cards.length} 张`)
  // 中间那张应为清晰、无模糊，两侧有 blur
  const blurred = cards.filter((c) => /blur\(/.test(c.f)).length
  check('两侧产生景深虚化', blurred >= 2, `${blurred} 张带 blur`)
  const center = cards.find((c) => !/blur\(/.test(c.f) && c.o === '1')
  check('中间片清晰且不透明', !!center, center ? `宽 ${center.w}px` : '无')

  // ---- 计数与标题联动 ----
  const snap = () => page.evaluate(() => ({
    count: document.querySelector('.fan__count b')?.textContent?.trim(),
    total: document.querySelector('.fan__count')?.textContent?.replace(/\s+/g, ' ').trim(),
    title: document.querySelector('.fan__title')?.textContent?.trim(),
    x: document.querySelector('.fan__card.is-active')?.getBoundingClientRect().x,
  }))
  const s0 = await snap()

  // 点击「下一张」
  await page.click('.fan__arrow[aria-label="下一张"]')
  await sleep(900)
  const s1 = await snap()
  check('点箭头换片（计数 +1）', s0.count !== s1.count, `${s0.count} → ${s1.count}`)
  check('片名跟着换', s0.title !== s1.title, `${s0.title} → ${s1.title}`)

  // ---- 拖拽 ----
  // 注意：点箭头可能触发滚动，拖拽起点必须用「当下」重新量的几何，不能用前面的旧 box
  const box2 = await page.$eval('.fan', (el) => {
    const r = el.getBoundingClientRect()
    return { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) }
  })
  const cx = box2.x + box2.w / 2
  const cy = box2.y + Math.min(220, box2.h * 0.42)
  const before = await snap()
  await page.mouse.move(cx + 240, cy)
  await page.mouse.down()
  for (let i = 1; i <= 14; i++) { await page.mouse.move(cx + 240 - i * 24, cy); await sleep(14) }
  await sleep(120)
  const midX = await page.evaluate(() => document.querySelector('.fan__card.is-active')?.getBoundingClientRect().x)
  await page.mouse.up()
  await sleep(1000)
  const after = await snap()
  check('拖拽中卡片跟手位移', Math.abs(midX - before.x) > 40, `x ${Math.round(before.x)} → ${Math.round(midX)}`)
  check('拖拽后换片', after.count !== before.count, `${before.count} → ${after.count}`)
  await page.screenshot({ path: `${OUT}/mix-fan-drag.png`, clip: { x: box.x - 8, y: Math.max(0, box.y - 8), width: box.w + 16, height: Math.min(box.h + 16, 900) } })

  // 拖完不应误跳详情
  check('拖拽不误跳详情', page.url().includes('/mix'), page.url())

  // ---- 网格切换 ----
  await page.evaluate(() => {
    const b = [...document.querySelectorAll('.view-toggle__btn')].find((x) => x.textContent.includes('网格'))
    b?.click()
  })
  await sleep(600)
  const gridCount = await page.$$eval('.mixcard', (e) => e.length)
  check('切到网格视图', gridCount > 0, `${gridCount} 张卡片`)
  await page.screenshot({ path: `${OUT}/mix-grid.png` })

  await page.evaluate(() => {
    const b = [...document.querySelectorAll('.view-toggle__btn')].find((x) => x.textContent.includes('海报扇'))
    b?.click()
  })
  await sleep(600)
  check('切回海报扇', await page.$('.fan') !== null)

  // 海报代理偶发 502 是部署环境限制（容器直连豆瓣图床被拦），图有占位兜底，不计页面错误
  const realErrors = errors.filter((e) => !e.includes('favicon') && !/502/.test(e))
  check('全程无控制台错误', realErrors.length === 0, realErrors.slice(0, 2).join(' | '))

  console.log(`\n==== ${results.filter(Boolean).length}/${results.length} 通过 ====`)
  await browser.close()
  process.exit(results.every(Boolean) ? 0 : 1)
})().catch((e) => { console.error('FAIL', e.message); process.exit(1) })
