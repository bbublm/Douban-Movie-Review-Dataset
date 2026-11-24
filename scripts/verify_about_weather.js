// /about 天气剧场：四态切换 + 视差 + 无报错
const puppeteer = require('puppeteer-core')
const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe'
const BASE = process.argv[2] || 'http://127.0.0.1:4173'
const OUT = '.workbuddy/screenshots'
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

;(async () => {
  const browser = await puppeteer.launch({
    executablePath: CHROME, headless: 'new', args: ['--no-sandbox'],
    defaultViewport: { width: 1440, height: 900 },
  })
  const page = await browser.newPage()
  const errors = []
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text().slice(0, 160)) })
  page.on('pageerror', (e) => errors.push('pageerror: ' + e.message.slice(0, 160)))

  const results = []
  const check = (n, ok, d = '') => { results.push(ok); console.log(`${ok ? 'PASS' : 'FAIL'}  ${n}${d ? '  — ' + d : ''}`) }

  await page.goto(BASE + '/about', { waitUntil: 'networkidle2', timeout: 60000 })
  await page.waitForSelector('.ws', { timeout: 15000 })
  await sleep(1200)

  const box = await page.$eval('.ws', (el) => {
    const r = el.getBoundingClientRect()
    return { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) }
  })
  check('天气剧场已渲染', box.w > 600 && box.h > 300, `${box.w}×${box.h}`)

  // 初始态
  const state = () => page.evaluate(() => ({
    sky: document.querySelector('.ws').dataset.sky,
    title: document.querySelector('.ws__title')?.innerText.replace(/\s+/g, ''),
    caption: document.querySelector('.ws__caption')?.innerText,
    kicker: document.querySelector('.ws__kicker')?.innerText,
    tab: document.querySelector('.ws__tab.is-on')?.innerText,
  }))
  const s0 = await state()
  check('初始=白天', s0.sky === 'day' && s0.tab === '晴', `${s0.sky}/${s0.tab}`)
  await page.screenshot({ path: `${OUT}/about-ws-day.png`, clip: { x: box.x, y: Math.max(0, box.y), width: box.w, height: box.h } })
  await page.screenshot({ path: `${OUT}/about-ws-day.png`, clip: { x: box.x, y: Math.max(0, box.y), width: box.w, height: box.h } })

  // 四态循环：点画面
  await page.mouse.click(box.x + box.w / 2, box.y + box.h / 2)
  await sleep(1100)
  const s1 = await state()
  check('点击 → 夜晚', s1.sky === 'night' && s1.tab === '夜', s1.caption)
  await page.screenshot({ path: `${OUT}/about-ws-night.png`, clip: { x: box.x, y: Math.max(0, box.y), width: box.w, height: box.h } })

  await page.mouse.click(box.x + box.w / 2, box.y + box.h / 2)
  await sleep(1100)
  const s2 = await state()
  check('点击 → 彩虹', s2.sky === 'rainbow' && s2.tab === '彩虹', s2.caption)
  await page.screenshot({ path: `${OUT}/about-ws-rainbow.png`, clip: { x: box.x, y: Math.max(0, box.y), width: box.w, height: box.h } })

  await page.mouse.click(box.x + box.w / 2, box.y + box.h / 2)
  await sleep(1100)
  const s3 = await state()
  check('点击 → 下雨', s3.sky === 'rain' && s3.tab === '雨', s3.caption)
  await page.screenshot({ path: `${OUT}/about-ws-rain.png`, clip: { x: box.x, y: Math.max(0, box.y), width: box.w, height: box.h } })

  await page.mouse.click(box.x + box.w / 2, box.y + box.h / 2)
  await sleep(1100)
  const s4 = await state()
  check('第四次点击回到白天', s4.sky === 'day', s4.sky)

  // 标签直达（点「彩虹」按钮不再触发画面切换）
  await page.click('.ws__tab:nth-child(3)')
  await sleep(900)
  const s5 = await state()
  check('标签直达彩虹且不叠加', s5.sky === 'rainbow', s5.sky)

  // 键盘
  await page.focus('.ws')
  await page.keyboard.press('ArrowRight')
  await sleep(900)
  const s6 = await state()
  check('键盘 → 切到下一态', s6.sky === 'rain', s6.sky)

  // 视差：鼠标左右移动后，各层 transform 应不同
  await page.mouse.move(box.x + 40, box.y + 40, { steps: 8 })
  await sleep(600)
  const tl = await page.evaluate(() => ({
    stage: getComputedStyle(document.querySelector('.ws__stage')).transform,
    bush: getComputedStyle(document.querySelector('.ws__bush--l1')).transform,
    cloud: getComputedStyle(document.querySelector('.ws__cloud--c1')).transform,
  }))
  await page.mouse.move(box.x + box.w - 40, box.y + box.h - 40, { steps: 8 })
  await sleep(600)
  const br = await page.evaluate(() => ({
    stage: getComputedStyle(document.querySelector('.ws__stage')).transform,
    bush: getComputedStyle(document.querySelector('.ws__bush--l1')).transform,
    cloud: getComputedStyle(document.querySelector('.ws__cloud--c1')).transform,
  }))
  check('鼠标位移产生视差（主体）', tl.stage !== br.stage)
  check('鼠标位移产生视差（前景灌木）', tl.bush !== br.bush)
  const diffLayers = tl.cloud !== br.cloud && tl.bush !== tl.stage
  check('不同深度位移量不同', diffLayers)

  // 颗粒数
  const fx = await page.evaluate(() => ({
    drops: document.querySelectorAll('.ws__drop').length,
    stars: document.querySelectorAll('.ws__star').length,
    flies: document.querySelectorAll('.ws__fly').length,
    confetti: document.querySelectorAll('.ws__confetti').length,
  }))
  check('四套氛围颗粒都在位', fx.drops >= 20 && fx.stars >= 20 && fx.flies >= 5 && fx.confetti >= 10, JSON.stringify(fx))

  // 页面没有横向溢出
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)
  check('无横向溢出', overflow <= 1, `溢出 ${overflow}px`)

  check('无控制台错误', errors.length === 0, errors.join(' | ').slice(0, 160))

  await page.evaluate(() => window.scrollTo(0, 0))
  await sleep(400)
  await page.screenshot({ path: `${OUT}/about-ws-page.png` })
  await browser.close()
  const ok = results.filter(Boolean).length
  console.log(`\n==== ${ok}/${results.length} 通过 ====`)
})()
