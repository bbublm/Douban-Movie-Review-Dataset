// 线上站点实拍（不做任何接口拦截，验证真实后端+真实数据）
// 用法：NODE_PATH=<frontend/node_modules> node scripts/shot_live_home.js http://localhost:8080
const puppeteer = require('puppeteer-core')
const path = require('path')
const fs = require('fs')

const BASE = process.argv[2] || 'http://localhost:8080'
const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
const OUT = 'C:\\Users\\16280\\Desktop\\movie-recommendation-system-main\\.workbuddy\\screenshots'
fs.mkdirSync(OUT, { recursive: true })
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

;(async () => {
  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: 'new',
    args: ['--no-sandbox', '--disable-gpu', '--window-size=1440,1000'],
    defaultViewport: { width: 1440, height: 1000 },
  })
  const page = await browser.newPage()
  const errors = []
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text().slice(0, 200)) })
  page.on('pageerror', (e) => errors.push('PAGEERROR: ' + String(e).slice(0, 200)))

  const t0 = Date.now()
  await page.goto(BASE, { waitUntil: 'networkidle2', timeout: 60000 })
  await page.waitForSelector('.dw', { timeout: 30000 })
  await sleep(1200)

  // 1) 首页首屏
  await page.screenshot({ path: path.join(OUT, 'live-home-01.png') })

  // 2) 滚到唱片墙并推进
  await page.evaluate(() => {
    const el = document.querySelector('.dw')
    window.scrollTo(0, el.getBoundingClientRect().top + window.scrollY)
  })
  await sleep(1200)
  await page.screenshot({ path: path.join(OUT, 'live-home-02.png') })
  const d1 = await page.evaluate(() => ({
    discs: document.querySelectorAll('.dw__item').length,
    count: document.querySelector('.dw__count')?.textContent.replace(/\s+/g, ' ').trim(),
    firstTitle: document.querySelector('.dw__name')?.textContent.trim(),
    hasPoster: !!document.querySelector('.dw__poster img')?.getAttribute('src'),
  }))

  await page.evaluate(() => window.scrollBy(0, 1400))
  await sleep(1300)
  await page.screenshot({ path: path.join(OUT, 'live-home-03.png') })
  const d2 = await page.evaluate(() => ({
    transform: getComputedStyle(document.querySelector('.dw__track')).transform,
    count: document.querySelector('.dw__count')?.textContent.replace(/\s+/g, ' ').trim(),
    progress: document.querySelector('.dw__bar i')?.style.width,
  }))

  // 3) 继续滚，确认能脱离 pin、后面区块还在
  await page.evaluate(() => window.scrollBy(0, 5600))
  await sleep(1100)
  await page.screenshot({ path: path.join(OUT, 'live-home-04.png') })
  const after = await page.evaluate(() => ({
    dwPosition: getComputedStyle(document.querySelector('.dw')).position,
    hasNowPlaying: document.body.innerText.includes('院线热映'),
    hasReviews: document.body.innerText.includes('影评'),
  }))

  // 4) 检索页（真实后端）
  await page.goto(BASE + '/search?q=' + encodeURIComponent('科幻'), { waitUntil: 'networkidle2', timeout: 60000 })
  await sleep(2200)
  await page.screenshot({ path: path.join(OUT, 'live-search.png') })
  const s = await page.evaluate(() => ({
    cards: document.querySelectorAll('.movie-card, .result-card, .mcard').length,
    text: (document.body.innerText.match(/找到|共\s*\d+|条结果/) || ['无'])[0],
    facets: document.querySelectorAll('.facet-group').length,
  }))

  // 5) 影评洞察大屏
  await page.goto(BASE + '/screen', { waitUntil: 'networkidle2', timeout: 60000 })
  await sleep(4500)
  await page.screenshot({ path: path.join(OUT, 'live-screen.png') })
  const sc = await page.evaluate(() => ({
    canvas: document.querySelectorAll('canvas').length,
    charts: document.querySelectorAll('[_echarts_instance_]').length,
    tabs: document.querySelectorAll('.stage-tab, .u-tab').length,
  }))

  console.log('load(ms):', Date.now() - t0)
  console.log('disc  :', JSON.stringify(d1))
  console.log('scroll:', JSON.stringify(d2))
  console.log('after :', JSON.stringify(after))
  console.log('search:', JSON.stringify(s))
  console.log('screen:', JSON.stringify(sc))
  console.log('console errors:', errors.length ? errors : 'none')
  await browser.close()
})()
