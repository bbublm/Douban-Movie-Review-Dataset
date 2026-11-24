// 电影盒子 · 风格回归截图脚本（puppeteer-core 驱动本机 Chrome）。
// 目的：把「对齐原系统风格」后的四个关键画面截出来人工比对 ——
// 首页检索横幅、登录玻璃卡、洞察页统计卡、已登录顶导航。
// 用法：NODE_PATH=<workspace> node scripts/shot_style_check.js [baseUrl]

const puppeteer = require('puppeteer-core')
const path = require('path')

const BASE = process.argv[2] || 'http://127.0.0.1:5173'
const SHOT_DIR = 'C:\\Users\\16280\\Desktop\\movie-recommendation-system-main\\.workbuddy\\screenshots'
const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'

async function shot(page, name) {
  const file = path.join(SHOT_DIR, name)
  await page.screenshot({ path: file, fullPage: false })
  console.log('  [shot] ' + name)
}

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
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()) })
  page.on('pageerror', (e) => errors.push(String(e)))

  // 1. 首页（未登录）
  await page.goto(BASE + '/', { waitUntil: 'networkidle2', timeout: 30000 })
  await sleep(1200)
  await shot(page, 'style-01-home.png')

  // 2. 登录页
  await page.goto(BASE + '/login', { waitUntil: 'networkidle2', timeout: 30000 })
  await sleep(900)
  await shot(page, 'style-02-login.png')

  // 3. 洞察页
  await page.goto(BASE + '/insights', { waitUntil: 'networkidle2', timeout: 40000 })
  await sleep(2500)
  await shot(page, 'style-03-insights.png')

  // 4. 已登录首页（顶导航用户区 + 菜单）
  const user = 'style' + (Date.now() % 100000)
  await page.goto(BASE + '/login', { waitUntil: 'networkidle2' })
  await sleep(600)
  // 走注册：填第二张卡
  const cards = await page.$$('.auth-card')
  const regCard = cards[1]
  const inputs = await regCard.$$('input')
  await inputs[0].type(user)
  await inputs[1].type('影迷小元')
  await inputs[2].type('style-pass-1')
  await (await regCard.$('button[type=submit]')).click()
  await sleep(2500)
  await shot(page, 'style-04-home-loggedin.png')

  // 展开用户菜单
  const trigger = await page.$('.user-area__trigger')
  if (trigger) { await trigger.click(); await sleep(400) }
  await shot(page, 'style-05-usermenu.png')

  console.log(errors.length ? '  [控制台错误] ' + errors.join(' | ') : '  [OK] 无控制台错误')
  await browser.close()
})().catch((e) => { console.error('FAILED: ' + e.message); process.exit(1) })
