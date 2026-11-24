// 电影盒子 · 功能清单改造后的页面截图（puppeteer-core 驱动本机 Chrome）。
// 覆盖：首页 / 检索 / 混搭器 / 分析大屏 / 电影详情 / 登录 / 盲盒
// 用法：NODE_PATH=<workspace> node scripts/shot_pages.js [baseUrl]

const puppeteer = require('puppeteer-core')
const path = require('path')

const BASE = process.argv[2] || 'http://127.0.0.1:5173'
const SHOT_DIR = 'C:\\Users\\16280\\Desktop\\movie-recommendation-system-main\\.workbuddy\\screenshots'
const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'

const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

async function shot(page, name) {
  await page.screenshot({ path: path.join(SHOT_DIR, name) })
  console.log('  [shot] ' + name)
}

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

  const go = async (url, wait = 1800) => {
    await page.goto(BASE + url, { waitUntil: 'networkidle2', timeout: 40000 }).catch(() => {})
    await sleep(wait)
  }

  await go('/', 2500)
  await shot(page, 'pg-01-home.png')

  await go('/search?q=', 2500)
  await shot(page, 'pg-02-search.png')

  await go('/mix', 1500)
  await shot(page, 'pg-03-mix.png')

  await go('/analytics', 3500)
  await shot(page, 'pg-04-analytics.png')

  await go('/login', 1500)
  await shot(page, 'pg-05-login.png')

  // 盲盒：从导航栏唤起
  await go('/', 2000)
  const boxBtn = await page.$('.app-header .btn-box')
  if (boxBtn) {
    await boxBtn.click()
    await sleep(2600)
    await shot(page, 'pg-06-blindbox.png')
  } else {
    console.log('  [WARN] 没找到导航盲盒按钮')
  }

  // 详情页：从热门卡片进
  await go('/', 2200)
  const card = await page.$('.hcard')
  if (card) {
    await card.click()
    await sleep(2500)
    await shot(page, 'pg-07-movie.png')
    console.log('  [info] 当前 URL：' + page.url())
  } else {
    console.log('  [WARN] 首页没有热门卡片')
  }

  console.log(errors.length ? '  [控制台错误] ' + errors.slice(0, 6).join(' | ') : '  [OK] 无控制台错误')
  await browser.close()
})().catch((e) => { console.error('FAILED: ' + e.message); process.exit(1) })
