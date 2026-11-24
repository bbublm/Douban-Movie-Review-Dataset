const puppeteer = require('puppeteer-core')
const fs = require('fs')
const path = require('path')
const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe'
const BASE = process.argv[2] || 'http://localhost:8080'
const OUT = path.resolve(__dirname, '..', '.workbuddy', 'screenshots')
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

;(async () => {
  fs.mkdirSync(OUT, { recursive: true })
  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--window-size=1600,1000'],
    defaultViewport: { width: 1600, height: 1000 },
  })
  const page = await browser.newPage()
  const errs = []
  page.on('console', (m) => { if (m.type() === 'error') errs.push(m.text()) })
  page.on('pageerror', (e) => errs.push('PAGEERROR ' + e.message))

  await page.goto(`${BASE}/screen?room=box`, { waitUntil: 'networkidle2', timeout: 60000 }).catch((e) => console.log('goto err', e.message))
  await sleep(4000)

  const info = await page.evaluate(() => {
    const q = (s) => document.querySelector(s)
    const out = {}
    const sel = ['.box-stage__gallery', '.box-stage__dock', '.box-stage__extras', '.box-stage__deep', '.room-hero', '.box-stage']
    for (const s of sel) {
      const el = q(s)
      if (!el) { out[s] = 'MISSING'; continue }
      const r = el.getBoundingClientRect()
      const cs = getComputedStyle(el)
      out[s] = {
        w: Math.round(r.width), h: Math.round(r.height),
        top: Math.round(r.top), bottom: Math.round(r.bottom),
        opacity: cs.opacity, display: cs.display, visibility: cs.visibility,
        children: el.children.length,
        cls: el.className,
        innerTextLen: (el.innerText || '').trim().length,
      }
    }
    // gallery inner
    const gal = q('.box-stage__gallery')
    if (gal) {
      out.gallery_detail = {
        frames: gal.querySelectorAll('.bog__frame, .bog-frame, [class*="frame"]').length,
        imgs: gal.querySelectorAll('img').length,
        anyChildHtml: gal.innerHTML.slice(0, 200),
      }
    }
    const dock = q('.box-stage__dock')
    if (dock) out.dock_inner = { rank: dock.querySelectorAll('.box-rank, [class*=rank]').length, trend: dock.querySelectorAll('canvas, svg').length }
    out.scrollHeight = document.querySelector('.dashboard-container')?.scrollHeight
    return out
  })
  console.log(JSON.stringify(info, null, 2))

  // viewport screenshot
  await page.screenshot({ path: path.join(OUT, 'inspect_box_top.png') })
  // scroll to gallery/dock
  await page.evaluate(() => { const d = document.querySelector('.box-stage__dock'); if (d) d.scrollIntoView() })
  await sleep(1500)
  await page.screenshot({ path: path.join(OUT, 'inspect_box_dock.png') })

  console.log('CONSOLE ERRORS:', errs.length)
  errs.slice(0, 20).forEach((e) => console.log('  ', e))
  await browser.close()
})()
