// 审查用：拍大厅 + 五间展厅的整页截图（fullPage），供布局审查
const puppeteer = require('puppeteer-core')
const path = require('path')
const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe'
const BASE = process.argv[2] || 'http://localhost:8080'
const OUT = path.resolve(__dirname, '..', '.workbuddy', 'screenshots')
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

;(async () => {
  const browser = await puppeteer.launch({
    executablePath: CHROME, headless: 'new',
    args: ['--hide-scrollbars', '--no-sandbox', '--disable-dev-shm-usage'],
    defaultViewport: { width: 1440, height: 900 },
  })
  const page = await browser.newPage()
  const errs = []
  page.on('console', (m) => { if (m.type() === 'error') errs.push(m.text().slice(0, 120)) })
  page.on('pageerror', (e) => errs.push('PAGEERROR ' + e.message.slice(0, 120)))

  // 大厅：先开封再拍
  await page.goto(`${BASE}/screen`, { waitUntil: 'networkidle2', timeout: 45000 })
  await sleep(1200)
  await page.evaluate(() => document.querySelector('.ih__box')?.click())
  await sleep(2600)
  await page.screenshot({ path: `${OUT}/review-house.png` })

  for (const room of ['galaxy', 'box', 'rank', 'flow', 'diverge']) {
    await page.goto(`${BASE}/screen?room=${room}`, { waitUntil: 'networkidle2', timeout: 45000 })
    await sleep(2200)
    // 逐屏下滚触发 .u-reveal 滚动揭示（is-in 常驻不回退），再回顶等过渡完成后整页拍，
    // 否则首屏以下的揭示板块在 fullPage 截图里仍是初始透明态
    await page.evaluate(async () => {
      const h = document.documentElement.scrollHeight
      for (let y = 0; y <= h; y += 500) { window.scrollTo(0, y); await new Promise((r) => setTimeout(r, 90)) }
      window.scrollTo(0, 0)
    })
    await sleep(900)
    await page.screenshot({ path: `${OUT}/review-${room}.png`, fullPage: true })
    console.log(`shot review-${room}.png`)
  }
  if (errs.length) { console.log('console errors:'); errs.slice(0, 6).forEach((e) => console.log(' -', e)) }
  else console.log('0 console errors')
  await browser.close()
})().catch((e) => { console.error('FATAL', e); process.exit(1) })
