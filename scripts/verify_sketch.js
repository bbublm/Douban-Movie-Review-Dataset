const puppeteer = require('puppeteer-core')
const fs = require('fs')
const path = require('path')
const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe'
const BASE = process.argv[2] || 'http://localhost:8080'
const OUT = path.resolve(__dirname, '..', '.workbuddy', 'screenshots')
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
let pass = 0, fail = 0
const check = (name, ok, extra = '') => {
  if (ok) { pass++; console.log('  ✓ ' + name + (extra ? ' — ' + extra : '')) }
  else { fail++; console.log('  ✗ ' + name + (extra ? ' — ' + extra : '')) }
}

;(async () => {
  fs.mkdirSync(OUT, { recursive: true })
  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--window-size=1600,1000'],
    defaultViewport: { width: 1600, height: 1000 },
  })
  const page = await browser.newPage()
  const errs = []
  page.on('console', (m) => { if (m.type() === 'error') errs.push(m.text()) })
  page.on('pageerror', (e) => errs.push('PAGEERROR ' + e.message))

  const rooms = [
    { key: 'box', sel: '.box-stage', shot: 'sketch_box' },
    { key: 'rank', sel: '.rank-room', shot: 'sketch_rank' },
    { key: 'flow', sel: '.flow-room', shot: 'sketch_flow' },
    { key: 'diverge', sel: '.diverge-room', shot: 'sketch_diverge' },
    { key: 'galaxy', sel: '.galaxy-float', shot: 'sketch_galaxy' },
  ]

  for (const r of rooms) {
    console.log(`\n=== 展厅 ${r.key} ===`)
    await page.goto(`${BASE}/screen?room=${r.key}`, { waitUntil: 'networkidle2', timeout: 60000 }).catch((e) => console.log('  goto err', e.message))
    await sleep(3500) // 等数据 + 1.7s 重扫兜底

    const top = await page.evaluate((sel) => {
      const room = document.querySelector(sel)
      if (!room) return { missing: true }
      const ovs = room.querySelectorAll('.sketch-ov')
      const drawn = room.querySelectorAll('.sketch-ov.is-drawn')
      return {
        missing: false,
        total: ovs.length,
        drawn: drawn.length,
        // 每条描边 dashoffset 应为 0（已画）或 > 0（未进视口，正常）
        paths: [...ovs].slice(0, 3).map((o) => o.querySelector('path')?.style.strokeDashoffset),
      }
    }, r.sel)
    if (top.missing) { check('房间根节点存在', false, '找不到 ' + r.sel); continue }
    check('注入了手绘描边（sketch-ov）', top.total > 0, `${top.total} 条`)
    check('首屏内描边已自我完成（is-drawn）', top.drawn > 0, `${top.drawn}/${top.total}`)

    // 滚到底触发全部揭示
    await page.evaluate(() => {
      const d = document.querySelector('.dashboard-container')
      if (d) d.scrollTop = d.scrollHeight
    })
    await sleep(2000)
    const bot = await page.evaluate((sel) => {
      const room = document.querySelector(sel)
      const ovs = room.querySelectorAll('.sketch-ov')
      const drawn = room.querySelectorAll('.sketch-ov.is-drawn')
      // 抽一条未画完的看 dashoffset 是否在减小
      const pend = [...ovs].find((o) => !o.classList.contains('is-drawn'))
      return { total: ovs.length, drawn: drawn.length, pending: !!pend }
    }, r.sel)

    if (r.key === 'box') {
      // 票房画廊：绳右端的相框要等横向漂移进视野才自我完成（itomdev 走廊同款交互）
      // 先回到顶部再连续滚轮漂移，把右端相框带进视野
      await page.evaluate(() => {
        const d = document.querySelector('.dashboard-container')
        if (d) d.scrollTop = 0
      })
      await sleep(300)
      const scene = await page.$('.bog__scene')
      if (scene) {
        for (let k = 0; k < 10; k++) {
          await scene.hover().catch(() => {})
          await page.mouse.wheel({ deltaY: 400 })
          await sleep(140)
        }
        await sleep(1500)
      }
      const drift = await page.evaluate((sel) => {
        const room = document.querySelector(sel)
        const frames = room.querySelectorAll('.bog__frame')
        const ovs = room.querySelectorAll('.sketch-ov')
        const drawn = room.querySelectorAll('.sketch-ov.is-drawn')
        return { frames: frames.length, total: ovs.length, drawn: drawn.length }
      }, r.sel)
      check('漂移画廊时右端相框逐帧自我完成', drift.drawn >= drift.total - 2,
        `漂移后 ${drift.drawn}/${drift.total}（相框 ${drift.frames}）`)
    } else {
      check('滚动后全部描边自我完成', bot.drawn === bot.total && bot.total > 0, `${bot.drawn}/${bot.total}`)
    }

    // 滚回中部截图
    await page.evaluate(() => {
      const d = document.querySelector('.dashboard-container')
      if (d) d.scrollTop = Math.floor(d.scrollHeight * 0.35)
    })
    await sleep(1600)
    await page.screenshot({ path: path.join(OUT, r.shot + '.png') })
  }

  console.log('\n=== 控制台 ===')
  check('全程 0 控制台错误', errs.length === 0, errs.slice(0, 5).join(' | '))
  console.log(`\n结果: ${pass} 通过 / ${fail} 失败`)
  await browser.close()
  process.exit(fail ? 1 : 0)
})()
