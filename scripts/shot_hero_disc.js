// Hero 光盘展台实拍 + 断言（线上 8080，真数据）
const puppeteer = require('puppeteer-core')
const path = require('path')
const fs = require('fs')
const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
const OUT = 'C:\\Users\\16280\\Desktop\\movie-recommendation-system-main\\.workbuddy\\screenshots'
fs.mkdirSync(OUT, { recursive: true })
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const BASE = process.argv[2] || 'http://localhost:8080'

;(async () => {
  const b = await puppeteer.launch({
    executablePath: CHROME, headless: 'new', args: ['--no-sandbox', '--disable-gpu'],
  })
  const out = {}
  for (const w of [1440, 1280, 1024]) {
    const p = await b.newPage()
    await p.setViewport({ width: w, height: 900 })
    const errs = []
    p.on('console', (m) => { if (m.type() === 'error') errs.push(m.text().slice(0, 150)) })
    p.on('pageerror', (e) => errs.push('PAGEERROR: ' + String(e).slice(0, 150)))
    await p.goto(BASE, { waitUntil: 'networkidle2', timeout: 60000 })
    await p.waitForSelector('.hero', { timeout: 30000 })
    await sleep(2500)
    const m = await p.evaluate(() => {
      const r = (sel) => {
        const el = document.querySelector(sel)
        if (!el) return null
        const b = el.getBoundingClientRect()
        return { x: Math.round(b.x), y: Math.round(b.y), w: Math.round(b.width), h: Math.round(b.height), right: Math.round(b.right), bottom: Math.round(b.bottom) }
      }
      const searchRow = document.querySelector('.hero__searchrow')
      const disc = document.querySelector('.cd')
      const btn = [...(searchRow?.children || [])].map((c) => {
        const b = c.getBoundingClientRect()
        return { cls: c.className.split(' ')[0], right: Math.round(b.right) }
      })
      const dw = document.querySelector('.dw')
      return {
        docH: document.documentElement.scrollHeight,
        screens: +(document.documentElement.scrollHeight / innerHeight).toFixed(1),
        hero: r('.hero'), disc: r('.cd'), cap: r('.hd__cap'),
        lastHeroBtnRight: Math.max(...btn.map((x) => x.right)),
        gap: disc ? Math.round(disc.getBoundingClientRect().x - Math.max(...btn.map((x) => x.right))) : null,
        discVisible: !!disc && getComputedStyle(document.querySelector('.hd')).display !== 'none',
        capText: document.querySelector('.hd__cap')?.innerText.replace(/\n/g, ' | '),
        oldWallPresent: !!dw,
        firstBlockTop: r('.home__body'),
      }
    })
    out[w] = { ...m, errs }
    if (w === 1440) {
      await p.screenshot({ path: path.join(OUT, 'hero-disc-1440.png'), clip: { x: 0, y: 0, width: 1440, height: 460 } })
      // 等自动换片一次，拍第二张，确认会换
      await sleep(6000)
      const after = await p.evaluate(() => ({
        cap: document.querySelector('.hd__cap')?.innerText.replace(/\n/g, ' | '),
        transform: getComputedStyle(document.querySelector('.cd')).transform,
      }))
      out.autoSwitch = after
      await p.screenshot({ path: path.join(OUT, 'hero-disc-1440-b.png'), clip: { x: 0, y: 0, width: 1440, height: 460 } })
      // 整页（确认原首页内容紧随其后）
      await p.screenshot({ path: path.join(OUT, 'home-full.png'), fullPage: true })
    }
    await p.close()
  }
  console.log(JSON.stringify(out, null, 1))
  await b.close()
})()
