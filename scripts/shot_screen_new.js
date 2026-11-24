// 实拍 /screen 三块新内容（一次性验证脚本）
const puppeteer = require('puppeteer-core')
const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe'
const OUT = 'C:/Users/16280/Desktop/movie-recommendation-system-main/.workbuddy/refshots'
const BASE = 'http://localhost:8080'

const SHOTS = [
  { name: 'screen-house', url: `${BASE}/screen`, wait: 5200 },
  { name: 'screen-diverge', url: `${BASE}/screen?room=diverge`, wait: 3800 },
  { name: 'screen-flow', url: `${BASE}/screen?room=flow`, wait: 3800 },
]

;(async () => {
  const fs = require('fs')
  fs.mkdirSync(OUT, { recursive: true })
  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: 'new',
    args: ['--no-sandbox', '--disable-dev-shm-usage', '--window-size=1440,900', '--force-device-scale-factor=1'],
    defaultViewport: { width: 1440, height: 900 },
  })
  const errors = []
  for (const s of SHOTS) {
    const page = await browser.newPage()
    page.on('console', (m) => { if (m.type() === 'error') errors.push(`${s.name}: ${m.text()}`) })
    page.on('pageerror', (e) => errors.push(`${s.name}: ${e.message}`))
    await page.goto(s.url, { waitUntil: 'networkidle2', timeout: 40000 }).catch(() => {})
    await new Promise((r) => setTimeout(r, s.wait))
    await page.screenshot({ path: `${OUT}/${s.name}.png` })
    console.log(`saved ${s.name}.png`)
    await page.close()
  }
  await browser.close()
  console.log('console errors:', errors.length ? errors.join('\n') : '(none)')
  console.log('done')
})()
