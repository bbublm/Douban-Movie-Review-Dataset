// Hero 光盘交互形态实拍：静止 / 悬停 / 拖拽中 / 整页
const puppeteer = require('puppeteer-core')

const BASE = process.argv[2] || 'http://localhost:8080'
const CHROME = process.env.CHROME_PATH || 'C:/Program Files/Google/Chrome/Application/chrome.exe'
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
const OUT = '.workbuddy/screenshots'

;(async () => {
  const b = await puppeteer.launch({
    executablePath: CHROME,
    headless: 'new',
    args: ['--no-sandbox', '--font-render-hinting=none'],
    defaultViewport: { width: 1440, height: 950 },
  })
  const p = await b.newPage()
  await p.goto(BASE + '/', { waitUntil: 'networkidle2', timeout: 60000 })
  await p.waitForSelector('.hd .cd', { timeout: 20000 })
  await sleep(1500)

  const r = await p.$eval('.cd', (el) => {
    const b = el.getBoundingClientRect()
    return { cx: b.x + b.width / 2, cy: b.y + b.height / 2, w: el.clientWidth }
  })

  // 1) 静止态：鼠标移远，等过渡结束
  await p.mouse.move(30, 700)
  await sleep(1400)
  await p.screenshot({ path: `${OUT}/hero-idle.png`, clip: { x: 0, y: 0, width: 1440, height: 470 } })

  // 2) 悬停态：提示浮现 + 指针微倾
  await p.mouse.move(r.cx + r.w * 0.3, r.cy - r.w * 0.2)
  await sleep(700)
  const hintOpacity = await p.$eval('.hd__hint', (el) => getComputedStyle(el).opacity)
  await p.screenshot({ path: `${OUT}/hero-hover.png`, clip: { x: 0, y: 0, width: 1440, height: 470 } })

  // 3) 拖拽态：盘随手转、光标抓取、松手后吸附回正
  const rad = (d) => (d * Math.PI) / 180
  const R = r.w * 0.34
  await p.mouse.move(r.cx + R, r.cy)
  await p.mouse.down()
  for (let a = 8; a <= 110; a += 8) {
    await p.mouse.move(r.cx + R * Math.cos(rad(a)), r.cy + R * Math.sin(rad(a)))
    await sleep(14)
  }
  await p.screenshot({ path: `${OUT}/hero-drag.png`, clip: { x: 0, y: 0, width: 1440, height: 470 } })
  const duringAngle = await p.$eval('.cd', (el) => getComputedStyle(el).transform)
  await p.mouse.up()
  await sleep(1600)
  const settled = await p.evaluate(() => {
    const el = document.querySelector('.cd')
    const m = getComputedStyle(el).transform.match(/matrix\(([^)]+)\)/)
    const deg = m ? (Math.atan2(Number(m[1].split(',')[1]), Number(m[1].split(',')[0])) * 180) / Math.PI : 0
    // 归一到 0..360，整圈吸附后应接近 0（海报正立）
    const norm = ((deg % 360) + 360) % 360
    const distance = Math.min(norm, 360 - norm)
    return { deg: Math.round(deg), distanceFromUpright: Math.round(distance) }
  })
  await p.screenshot({ path: `${OUT}/hero-settled.png`, clip: { x: 0, y: 0, width: 1440, height: 470 } })

  await p.mouse.move(20, 900)
  await sleep(300)
  await p.screenshot({ path: `${OUT}/home-full.png`, fullPage: true })

  console.log(JSON.stringify({
    hintOpacity,
    duringAngle,
    settled,
    upright: settled.distanceFromUpright < 3,
  }, null, 1))
  await b.close()
})().catch((e) => { console.error(e); process.exit(1) })
