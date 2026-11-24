/* Stage 2 体检：3D 星系是否真的渲染 + 面板真实数据 + 依旧零滚动 */
const { chromium } = require('playwright')
;(async () => {
  const b = await chromium.launch({
    channel: 'chrome',
    args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader', '--disable-gpu-sandbox'],
  })
  const p = await b.newPage({ viewport: { width: 1920, height: 1080 } })
  const errs = []
  p.on('console', (m) => { if (m.type() === 'error') errs.push(m.text().slice(0, 200)) })
  p.on('pageerror', (e) => errs.push('PAGEERROR: ' + e.message.slice(0, 200)))
  await p.goto('http://localhost:5173/screen', { waitUntil: 'networkidle', timeout: 60000 })
  await p.waitForTimeout(4500)

  const m = await p.evaluate(() => {
    const de = document.documentElement
    const q = (s) => document.querySelector(s)
    const txt = (s) => (q(s)?.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 60)
    const canvas = q('.three-canvas-layer canvas')
    // 采样画布中心区域，判断是否真的画出了东西（非纯黑）
    let painted = null
    if (canvas) {
      try {
        const c2 = document.createElement('canvas')
        c2.width = 240; c2.height = 135
        const cx = c2.getContext('2d')
        cx.drawImage(canvas, 0, 0, 240, 135)
        const d = cx.getImageData(0, 0, 240, 135).data
        let lit = 0
        for (let i = 0; i < d.length; i += 4) if (d[i] + d[i + 1] + d[i + 2] > 60) lit++
        painted = { pixelsLit: lit, of: d.length / 4 }
      } catch (e) { painted = 'ERR ' + e.message }
    }
    return {
      scrollH: de.scrollHeight, clientH: de.clientHeight,
      scrollW: de.scrollWidth, clientW: de.clientWidth,
      hasCanvas: !!canvas,
      canvasSize: canvas ? `${canvas.width}x${canvas.height}` : null,
      painted,
      topNumbers: txt('.top-bar__meta'),
      positiveRate: txt('.echo__value'),
      lexiconRows: document.querySelectorAll('.echo__word').length,
      timelineRows: document.querySelectorAll('.story__row').length,
      timelineFirst: txt('.story__row'),
      lede: txt('.story__lede'),
      streamChips: document.querySelectorAll('.stream-chip').length,
      ringSegs: document.querySelectorAll('.echo__seg').length,
      ringDash: q('.echo__seg')?.style.strokeDasharray || null,
    }
  })
  console.log(JSON.stringify(m, null, 1))
  console.log('ERRORS:', errs.length ? errs : 'none')
  await p.screenshot({ path: __dirname + '/.screen-shot.png' })
  await b.close()
})().catch((e) => { console.error('FAIL', e.message); process.exit(1) })
