// 大屏元素级高清特写（2x），用于排查文字重影
const puppeteer = require('puppeteer-core')
const path = require('path')
const fs = require('fs')
const OUT = 'C:\\Users\\16280\\Desktop\\movie-recommendation-system-main\\.workbuddy\\screenshots'
const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

;(async () => {
  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: 'new',
    args: ['--no-sandbox', '--disable-gpu'],
    defaultViewport: { width: 1440, height: 1000, deviceScaleFactor: 2 },
  })
  const page = await browser.newPage()
  await page.goto(process.argv[2] || 'http://localhost:8080/screen', { waitUntil: 'networkidle2', timeout: 60000 })
  await sleep(6000)

  const info = await page.evaluate(() => {
    const pick = (sel) => {
      const el = document.querySelector(sel)
      return el ? el.getBoundingClientRect().toJSON() : null
    }
    const rows = [...document.querySelectorAll('.story__row')].slice(0, 2)
    return {
      panelRect: pick('.story'),
      rowHTML: rows.map((r) => r.outerHTML.slice(0, 400)),
      rowCS: rows.map((r) => {
        const c = getComputedStyle(r)
        return { fs: c.fontSize, ff: c.fontFamily, ls: c.letterSpacing, transform: c.transform, animation: c.animationName }
      }),
      decadeCS: rows.map((r) => {
        const d = r.querySelector('.story__decade')
        if (!d) return null
        const c = getComputedStyle(d)
        return { fs: c.fontSize, ff: c.fontFamily, ls: c.letterSpacing, ws: c.wordSpacing, transform: c.transform }
      }),
    }
  })
  console.log(JSON.stringify(info, null, 1))

  const panel = await page.$('.story')
  if (panel) await panel.screenshot({ path: path.join(OUT, 'crop-story-2x.png') })
  const left = await page.$('.echo, .panel-left, .u-panel')
  if (left) await left.screenshot({ path: path.join(OUT, 'crop-left-2x.png') })
  await browser.close()
})()
