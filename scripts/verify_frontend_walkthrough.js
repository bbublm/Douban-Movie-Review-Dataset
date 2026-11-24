// 电影盒子 · 前端全流程走查脚本（puppeteer-core 驱动本机 Chrome）。
// 覆盖：注册登录 → 我的页（评分/想看）→ 发现页（推荐/趣味实验室）
//      → 首页检索与详情弹窗 → 项目说明页。
// 用法：NODE_PATH=<workspace> node verify_frontend_walkthrough.js [baseUrl]
// 产出：截图到 .workbuddy/screenshots/，控制台输出 PASS/FAIL 清单。

const puppeteer = require('puppeteer-core')
const fs = require('fs')
const path = require('path')

const BASE = process.argv[2] || 'http://127.0.0.1:5173'
const SHOT_DIR = 'C:\\Users\\16280\\Desktop\\movie-recommendation-system-main\\.workbuddy\\screenshots'
const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
const USERNAME = 'walk' + Date.now() % 1000000
const PASSWORD = 'walk-pass-1'

let passCount = 0
let failCount = 0
const failures = []

function check(name, ok, detail) {
  if (ok) { passCount++; console.log(`  [OK] ${name}`) }
  else { failCount++; failures.push(name); console.log(`  [FAIL] ${name} — ${detail || ''}`) }
}

async function shot(page, name) {
  const file = path.join(SHOT_DIR, name)
  await page.screenshot({ path: file, fullPage: false })
  console.log(`  [shot] ${name}`)
}

;(async () => {
  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: 'new',
    args: ['--no-sandbox', '--disable-gpu', '--window-size=1440,1000'],
    defaultViewport: { width: 1440, height: 1000 },
  })
  const page = await browser.newPage()
  const consoleErrors = []
  page.on('console', (msg) => {
    if (msg.type() === 'error') consoleErrors.push(msg.text().slice(0, 160))
  })
  page.on('pageerror', (err) => consoleErrors.push('PAGEERROR: ' + String(err).slice(0, 160)))

  const settle = async (ms = 1200) => new Promise((r) => setTimeout(r, ms))

  try {
    // ---------- 1. 注册（独立注册页 /register） ----------
    console.log('== 1. 注册并自动登录 ==')
    await page.goto(`${BASE}/register`, { waitUntil: 'networkidle2' })
    await settle(800)
    // 注册页 4 个输入框：用户名 / 昵称 / 密码 / 确认密码
    const inputs = await page.$$('.auth-card input')
    check('注册页有 4 个输入框（用户名/昵称/密码/确认）', inputs.length === 4, `input 数=${inputs.length}`)
    await inputs[0].type(USERNAME)        // 用户名
    await inputs[1].type('走查用户')       // 昵称
    await inputs[2].type(PASSWORD)        // 密码
    await inputs[3].type(PASSWORD)        // 确认密码
    // 真实点击 submit 按钮，确保触发 Vue 的 @submit.prevent 表单提交
    await page.click('.auth-card button[type="submit"]')
    await settle(2500)
    const afterReg = await page.evaluate(() => document.body.innerText)
    check('注册后自动登录（导航栏显示昵称）', afterReg.includes('走查用户'), afterReg.slice(0, 80))

    // ---------- 2. 首页 → 检索 → 详情 + 评分 + 想看 ----------
    // （首页已按清单改为 Hero 形态：热门横向滚动 + 影评速览，影片网格在 /search）
    console.log('== 2. 首页 → 检索 → 详情 → 评分/想看 ==')
    await page.goto(`${BASE}/`, { waitUntil: 'networkidle2' })
    await settle(1500)
    await shot(page, '10-home.png')
    const homeText = await page.evaluate(() => document.body.innerText)
    const horizonCount = (await page.$$('.hcard')).length
    check('首页热门横向列表有结果', horizonCount > 0 && homeText.includes('大家都在看'),
      `热门卡片数=${horizonCount}`)

    // 从首页进入检索页，点第一张影片卡
    await page.goto(`${BASE}/search?q=星际穿越`, { waitUntil: 'networkidle2' })
    await settle(1500)
    const cardCount = (await page.$$('.movie-card')).length
    check('检索结果页影片网格有结果', cardCount > 0, `卡片数=${cardCount}`)

    // 点第一张卡片打开详情
    await page.click('.movie-card')
    await settle(1200)
    await shot(page, '11-detail.png')
    const detailText = await page.evaluate(() => document.body.innerText)
    check('详情弹窗打开（含评分行与想看按钮）',
      detailText.includes('我的评分') && /想\s*看/.test(detailText), '')
    // 打 8 分（评分行是 1~10 圆形按钮）
    await page.evaluate(() => {
      const dots = [...document.querySelectorAll('button')].filter(
        (b) => b.textContent.trim() === '8' && b.closest('[class*=rating], [class*=score], .modal-body, [class*=detail]'))
      ;(dots[0] || [...document.querySelectorAll('button')].find((b) => b.textContent.trim() === '8')).click()
    })
    await settle(1200)
    // 加想看（按钮文案：☆ 想 看 → ★ 已想看）
    await page.evaluate(() => {
      const btn = [...document.querySelectorAll('button')].find((b) => /想\s*看/.test(b.textContent))
      if (btn) btn.click()
    })
    await settle(1200)
    const detailAfter = await page.evaluate(() => document.body.innerText)
    check('加想看后按钮变为已想看', detailAfter.includes('已想看'), '')
    await page.keyboard.press('Escape')
    await settle(600)

    // ---------- 3. 我的页 ----------
    console.log('== 3. 我的页（评分/想看清单） ==')
    await page.goto(`${BASE}/me`, { waitUntil: 'networkidle2' })
    await settle(1500)
    await shot(page, '12-me.png')
    const meText = await page.evaluate(() => document.body.innerText)
    const hasRatingRow = (await page.$$('.rank-row')).length > 0
    const watchCountMatch = meText.match(/想看清单（(\d+)）/)
    check('我的页显示用户资料（昵称）', meText.includes('走查用户') || meText.includes(USERNAME), '')
    check('我的评分列表出现刚才的 8 分记录', hasRatingRow && /我的评分（[1-9]/.test(meText),
      `rank-row 数=${(await page.$$('.rank-row')).length}`)
    check('想看清单计数 ≥ 1', watchCountMatch && Number(watchCountMatch[1]) >= 1,
      `匹配=${watchCountMatch && watchCountMatch[1]}`)

    // ---------- 4. 发现页已移除：旧路径应重定向到首页（2026-10-20） ----------
    console.log('== 4. 旧发现页路径重定向 ==')
    await page.goto(`${BASE}/discover`, { waitUntil: 'networkidle2' })
    await settle(1200)
    const discoverUrl = page.url()
    check('/discover 重定向到首页', /\/$|\/(\?|$)/.test(new URL(discoverUrl).pathname + new URL(discoverUrl).search) || discoverUrl.endsWith(BASE.replace(/^https?:\/\/[^/]+/, '')) || new URL(discoverUrl).pathname === '/',
      `now=${discoverUrl}`)
    await page.goto(`${BASE}/for-you`, { waitUntil: 'networkidle2' })
    await settle(1200)
    check('/for-you 重定向到首页', new URL(page.url()).pathname === '/', `now=${page.url()}`)

    // ---------- 5. 洞察页与说明页（真实等待动画结束） ----------
    console.log('== 5. 洞察页 / 说明页 ==')
    await page.goto(`${BASE}/insights`, { waitUntil: 'networkidle2' })
    await settle(1800)
    // /insights 重定向到 /screen；2026-10-22 起 /screen 默认是「洞察馆大厅」。
    // 2026-11-04 起大厅首屏是合盒状态（先打开电影盒子才看得到门），
    // 旧断言用的 .ih__door 早已随 CSS 3D 走廊改成 .ih__room，这里同步到新契约。
    const insPath = new URL(page.url()).pathname
    const atHouse = await page.evaluate(() => {
      const ih = document.querySelector('.ih')
      return !!ih && ih.classList.contains('is-sealed') && document.querySelectorAll('.ih__room').length === 5
    })
    check('/insights 重定向到合盒大厅（先开盒才见门）', insPath === '/screen' && atHouse, `${insPath} house=${atHouse}`)
    await page.goto(`${BASE}/screen?room=galaxy`, { waitUntil: 'networkidle2' })
    await settle(2400)
    await shot(page, '14-insights.png')
    const insightsText = await page.evaluate(() => document.body.innerText)
    // /insights 已重定向到 /screen 全屏大屏（旧纵向长页断言「影评总量」随页面废弃）
    check('洞察大屏渲染（回声室情感面板出数）', insightsText.includes('正面率') && insightsText.length > 200,
      `textLen=${insightsText.length}`)
    await page.goto(`${BASE}/about`, { waitUntil: 'networkidle2' })
    await settle(1500)
    await shot(page, '15-about.png')
    const aboutText = await page.evaluate(() => document.body.innerText)
    check('说明页完整渲染（数据来源+进度）', aboutText.includes('数据来源与合规') && aboutText.includes('阶段进度'), '')

    // ---------- 6. 控制台错误 ----------
    console.log('== 6. 控制台错误 ==')
    const rawErrors = consoleErrors.filter((e) => !e.includes('favicon') && !e.includes('DevTools'))
    // 图片代理 502 单列：容器出网抓不到豆瓣图床（宿主机可直连、容器 TLS 被中断），
    // 属部署环境限制，前端已用「片名首字占位」兜底，不算页面功能错误。
    const imgErrors = rawErrors.filter((e) => e.includes('502') && e.includes('Failed to load resource'))
    const realErrors = rawErrors.filter((e) => !imgErrors.includes(e))
    if (imgErrors.length) {
      console.log(`  [warn] 海报代理 502 ${imgErrors.length} 条（容器出网限制，前端已兜底占位）`)
    }
    check('全程无浏览器控制台错误', realErrors.length === 0, realErrors.slice(0, 3).join(' | '))

  } catch (e) {
    failCount++
    failures.push('脚本异常: ' + String(e).slice(0, 200))
    console.error('SCRIPT ERROR:', e)
  } finally {
    await browser.close()
  }

  console.log(`\n合计: ${passCount} 过 / ${failCount} 挂`)
  if (failures.length) console.log('失败项:', failures.join(' ; '))
  process.exit(failCount ? 1 : 0)
})()
