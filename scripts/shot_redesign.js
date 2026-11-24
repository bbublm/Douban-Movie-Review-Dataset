const puppeteer = require('puppeteer-core')
const fs = require('fs')
const path = require('path')
const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe'
const BASE = process.argv[2] || 'http://localhost:8080'
const OUT = path.resolve(__dirname, '..', '.workbuddy', 'screenshots')
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))

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
    { key: 'box', sel: '.box-stage' },
    { key: 'rank', sel: '.rank-room' },
    { key: 'flow', sel: '.flow-room' },
    { key: 'diverge', sel: '.diverge-room' },
  ]

  for (const r of rooms) {
    console.log(`\n=== ${r.key} ===`)
    await page.goto(`${BASE}/screen?room=${r.key}`, { waitUntil: 'networkidle2', timeout: 60000 }).catch((e) => console.log('goto err', e.message))
    await sleep(4200)

    const info = await page.evaluate((sel) => {
      const room = document.querySelector(sel)
      if (!room) return { missing: true }
      const hero = room.querySelector('.room-hero')
      const secs = [...room.querySelectorAll('.room-section')]
      const ovs = room.querySelectorAll('.sketch-ov')
      const drawn = room.querySelectorAll('.sketch-ov.is-drawn')
      const d = document.querySelector('.dashboard-container')
      const rr = (el) => { const b = el.getBoundingClientRect(); return { h: Math.round(b.height), top: Math.round(b.top) } }
      return {
        hero: hero ? rr(hero) : null,
        heroTitle: hero ? getComputedStyle(hero.querySelector('.rh__title')).fontSize : null,
        sections: secs.length,
        secNos: secs.map((s) => s.querySelector('.rs__no')?.textContent),
        sketch: `${drawn.length}/${ovs.length}`,
        roomH: Math.round(room.getBoundingClientRect().height),
        scrollH: d ? d.scrollHeight : 0,
        // 首屏可见的数据卡数量
        visibleCards: [...room.querySelectorAll('.float-card')].filter((c) => {
          const b = c.getBoundingClientRect()
          return b.top < window.innerHeight && b.bottom > 0
        }).length,
      }
    }, r.sel)
    console.log(JSON.stringify(info))

    await page.screenshot({ path: path.join(OUT, `redesign_${r.key}_top.png`) })

    // 滚到中段：看章节节奏 + 卡片层次
    await page.evaluate(() => {
      const d = document.querySelector('.dashboard-container')
      if (d) d.scrollTop = Math.floor(d.scrollHeight * 0.33)
    })
    await sleep(1800)
    await page.screenshot({ path: path.join(OUT, `redesign_${r.key}_mid.png`) })

    // 滚到底：确认所有内容都被揭示
    await page.evaluate(() => {
      const d = document.querySelector('.dashboard-container')
      if (d) d.scrollTop = d.scrollHeight
    })
    await sleep(1800)
    const tail = await page.evaluate((sel) => {
      const room = document.querySelector(sel)
      const hidden = [...room.querySelectorAll('.u-reveal')].filter((e) => getComputedStyle(e).opacity === '0')
      const settled = [...room.querySelectorAll('.u-reveal.is-settled')].length
      return { hiddenReveals: hidden.length, settled }
    }, r.sel)
    console.log('tail', JSON.stringify(tail))
  }

  console.log('\nCONSOLE ERRORS:', errs.length)
  errs.slice(0, 10).forEach((e) => console.log('  ', e))
  await browser.close()
})()
