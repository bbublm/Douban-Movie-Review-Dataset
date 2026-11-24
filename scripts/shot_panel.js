const puppeteer = require('puppeteer-core')
;(async () => {
  const b = await puppeteer.launch({
    executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
    headless: 'new', args: ['--no-sandbox'], defaultViewport: { width: 1440, height: 920 },
  })
  const p = await b.newPage()
  p.on('pageerror', (e) => console.log('PAGEERROR:', e.message))
  p.on('console', (m) => { if (m.type() === 'error') console.log('CONSOLE:', m.text()) })
  await p.goto('http://localhost:8080/screen?room=diverge', { waitUntil: 'networkidle2', timeout: 40000 }).catch(() => {})
  await new Promise((r) => setTimeout(r, 2500))
  // 截右侧面板（顶部）
  const clip = await p.evaluate(() => {
    const el = document.querySelector('.right-panel')
    if (!el) return null
    const r = el.getBoundingClientRect()
    return { x: r.x, y: r.y, width: r.width, height: r.height }
  })
  if (clip) {
    await p.screenshot({ path: 'scripts/../.workbuddy/refshots/panel-top.png', clip })
    // 滚动内部 .pb__scroll 到底，看引文
    await p.evaluate(() => {
      const s = document.querySelector('.pb__scroll')
      if (s) s.scrollTop = s.scrollHeight
    })
    await new Promise((r) => setTimeout(r, 600))
    await p.screenshot({ path: 'scripts/../.workbuddy/refshots/panel-bottom.png', clip })
    console.log('panel clip:', JSON.stringify(clip))
  } else {
    console.log('NO .right-panel found')
  }
  await b.close()
  console.log('done')
})()
