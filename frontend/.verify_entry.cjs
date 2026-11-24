const { chromium } = require('playwright')
;(async () => {
  const b = await chromium.launch({ channel: 'chrome', args: ['--disable-gpu'] })
  const p = await b.newPage({ viewport: { width: 1600, height: 900 } })
  const errs = []
  p.on('pageerror', (e) => errs.push(e.message.slice(0, 120)))
  await p.goto('http://localhost:5173/analytics', { waitUntil: 'networkidle', timeout: 60000 })
  await p.waitForTimeout(1500)
  const r = await p.evaluate(() => ({
    entry: !!document.querySelector('.screen-entry'),
    oldPanel: !!document.querySelector('.dspanel'),
  }))
  await p.locator('.screen-entry').scrollIntoViewIfNeeded()
  await p.waitForTimeout(600)
  await p.locator('.screen-entry').click()
  await p.waitForTimeout(1200)
  const url = p.url()
  console.log(JSON.stringify({ ...r, afterClickUrl: url, errs: errs.length ? errs : 'none' }))
  await b.close()
})().catch((e) => { console.error('FAIL', e.message); process.exit(1) })
