// ============================================================
// Hero 光盘展台交互回归
//
// 验证：
//   1. 原「影评速览 / 影片年代分布」区块已移除
//   2. 左右箭头能换片
//   3. 圆点能直达指定影片
//   4. 键盘 ← → 能换片
//   5. 拖拽能旋转光盘并切片（松手不回弹、不误跳详情页）
//   6. 全程 0 控制台错误
//
// 用法：node scripts/verify_hero_discs.js [baseUrl]
// ============================================================
const puppeteer = require('puppeteer-core')

const BASE = process.argv[2] || 'http://localhost:8080'
const CHROME = process.env.CHROME_PATH || 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

let pass = 0
let fail = 0
function check(name, ok, extra = '') {
  if (ok) { pass++; console.log(`  PASS  ${name}${extra ? ' — ' + extra : ''}`) }
  else { fail++; console.log(`  FAIL  ${name}${extra ? ' — ' + extra : ''}`) }
}

;(async () => {
  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: 'new',
    args: ['--no-sandbox', '--disable-gpu', '--font-render-hinting=none'],
    defaultViewport: { width: 1440, height: 950 },
  })
  const page = await browser.newPage()
  const errors = []
  page.on('pageerror', (e) => errors.push('pageerror: ' + e.message))
  page.on('console', (m) => { if (m.type() === 'error') errors.push('console: ' + m.text()) })

  await page.goto(BASE + '/', { waitUntil: 'networkidle2', timeout: 60000 })
  await page.waitForSelector('.hd .cd', { timeout: 20000 })
  await sleep(1200)

  const title = () => page.$eval('.hd__cap-title', (el) => el.textContent.trim())
  const activeDot = () => page.$$eval('.hd__dot', (els) => els.findIndex((e) => e.classList.contains('is-on')))
  const cdTransform = () => page.$eval('.cd', (el) => {
    const t = getComputedStyle(el).transform
    if (!t || t === 'none') return 0
    const m = t.match(/matrix\(([^)]+)\)/) || t.match(/matrix3d\(([^)]+)\)/)
    if (!m) return 0
    const v = m[1].split(',').map(Number)
    if (t.startsWith('matrix3d')) return Math.round((Math.atan2(v[1], v[0]) * 180) / Math.PI)
    return Math.round((Math.atan2(v[1], v[0]) * 180) / Math.PI)
  })

  console.log('\n[1] 首页区块')
  const removed = await page.evaluate(() => {
    const txt = document.body.innerText
    return {
      grid: !!document.querySelector('.home__grid'),
      reviews: txt.includes('影评速览'),
      decades: txt.includes('影片年代分布'),
      keep: ['大家都在看', '院线热映', '怪兽合影'].filter((s) => txt.includes(s)),
    }
  })
  check('「影评速览」已移除', !removed.reviews)
  check('「影片年代分布」已移除', !removed.decades)
  check('.home__grid 容器已移除', !removed.grid)
  check('其余区块保留', removed.keep.length === 3, removed.keep.join(' / '))

  console.log('\n[2] 箭头换片')
  const t0 = await title()
  const d0 = await activeDot()
  await page.click('.hd__arrow[aria-label="下一张"]')
  await sleep(700)
  const t1 = await title()
  const d1 = await activeDot()
  check('点击「下一张」片名变化', t0 !== t1, `${t0} → ${t1}`)
  check('圆点索引 +1', d1 === (d0 + 1) % 12, `${d0} → ${d1}`)

  await page.click('.hd__arrow[aria-label="上一张"]')
  await sleep(700)
  const t1c = await title()
  const d1c = await activeDot()
  check('点击「上一张」回到原片', t1c === t0, `${t1} → ${t1c}（idx ${d1} → ${d1c}）`)

  console.log('\n[3] 圆点直达')
  const targetIdx = 6
  const targetLabel = await page.$$eval('.hd__dot', (els, i) => els[i].getAttribute('aria-label'), targetIdx)
  await page.$$eval('.hd__dot', (els, i) => els[i].click(), targetIdx)
  await sleep(600)
  const dotNow = await activeDot()
  const titleNow = await title()
  check('点击第 7 个圆点切换到位', dotNow === targetIdx, `idx=${dotNow}`)
  check('片名与目标一致', targetLabel.includes(titleNow), `${targetLabel} vs ${titleNow}`)

  console.log('\n[4] 键盘 ← →')
  await page.focus('.cd')
  await sleep(150)
  const tk0 = await title()
  await page.keyboard.press('ArrowRight')
  await sleep(500)
  const tk1 = await title()
  check('ArrowRight 切下一张', tk1 !== tk0, `${tk0} → ${tk1}`)
  await page.keyboard.press('ArrowLeft')
  await sleep(500)
  const tk2 = await title()
  check('ArrowLeft 切回上一张', tk2 === tk0, `${tk1} → ${tk2}`)

  console.log('\n[5] 拖拽旋转')
  const box = await page.$eval('.cd', (el) => {
    const r = el.getBoundingClientRect()
    return { x: r.x, y: r.y, w: r.width, h: r.height }
  })
  const cx = box.x + box.w / 2
  const cy = box.y + box.h / 2
  const R = box.w * 0.34
  const urlBefore = page.url()
  const rad = (deg) => (deg * Math.PI) / 180

  const before = await title()
  const transformBefore = await cdTransform()

  await page.mouse.move(cx + R * Math.cos(rad(0)), cy + R * Math.sin(rad(0)))
  await page.mouse.down()
  for (let a = 10; a <= 170; a += 10) {
    await page.mouse.move(cx + R * Math.cos(rad(a)), cy + R * Math.sin(rad(a)))
    await sleep(12)
  }
  const draggingClass = await page.$eval('.cd', (el) => el.classList.contains('is-dragging'))
  const transformDuring = await cdTransform()
  await page.mouse.up()
  // 松手后有 1s 的落位过渡（拖拽角度 + 换片推进），等过渡跑完再测最终角度
  await sleep(1500)

  const after = await title()
  const transformAfter = await cdTransform()
  check('拖拽中进入拖拽态', draggingClass)
  check('拖拽中盘面随指针旋转', transformDuring !== transformBefore, `${transformBefore}° → ${transformDuring}°`)
  check('松手后切换了一张', after !== before, `${before} → ${after}`)
  check(
    '松手后角度不回弹',
    Math.abs(transformAfter - transformDuring) < 300 && Math.abs(transformAfter - transformBefore) > 10,
    `${transformBefore}° → 拖拽中 ${transformDuring}° → 落位 ${transformAfter}°`,
  )
  check('拖拽不误跳详情页', page.url() === urlBefore)

  console.log('\n[6] 悬停暂停 / 点击跳转')
  await page.mouse.move(cx, cy)
  await sleep(300)
  const tHover = await title()
  await sleep(3000)
  const tHover2 = await title()
  check('鼠标悬停期间不自动换片', tHover === tHover2, `${tHover}`)
  await page.mouse.move(40, 40)
  await sleep(2600)
  const tAuto = await title()
  check('移开鼠标后自动换片恢复', tAuto !== tHover2, `${tHover2} → ${tAuto}`)

  // 点击盘面（不拖动）应进详情页
  const clickBox = await page.$eval('.cd', (el) => {
    const r = el.getBoundingClientRect()
    return { x: r.x + r.width / 2, y: r.y + r.height / 2 }
  })
  await page.mouse.click(clickBox.x, clickBox.y)
  await sleep(900)
  check('点击盘面进入影片详情', /\/movie\//.test(page.url()), page.url())
  await page.goBack({ waitUntil: 'networkidle2' })
  await sleep(800)

  await page.screenshot({ path: '.workbuddy/screenshots/hero-interactive.png' })
  check('全程 0 控制台错误', errors.length === 0, errors.slice(0, 3).join(' | '))

  console.log(`\n结果：${pass} 通过 / ${fail} 失败`)
  await browser.close()
  process.exit(fail ? 1 : 0)
})().catch((e) => {
  console.error('脚本异常：', e)
  process.exit(2)
})
