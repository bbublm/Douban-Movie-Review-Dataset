/* 用截图做像素分析：确认 WebGL 星系真的渲染出粒子（而非黑屏）。
   WebGL canvas 未开 preserveDrawingBuffer，drawImage 采样必然为空，只能走截图。 */
const { chromium } = require('playwright')
;(async () => {
  const b = await chromium.launch({
    channel: 'chrome',
    args: ['--use-gl=swiftshader', '--enable-unsafe-swiftshader'],
  })
  const p = await b.newPage({ viewport: { width: 1920, height: 1080 } })
  await p.goto('http://localhost:5173/screen', { waitUntil: 'networkidle', timeout: 60000 })
  await p.waitForTimeout(5000)
  const shot = await p.screenshot({ type: 'png' })
  const b64 = shot.toString('base64')

  const res = await p.evaluate(async (data) => {
    const img = new Image()
    img.src = 'data:image/png;base64,' + data
    await img.decode()
    const c = document.createElement('canvas')
    c.width = 960; c.height = 540
    const ctx = c.getContext('2d')
    ctx.drawImage(img, 0, 0, 960, 540)
    // 真正的中央 3D 可视区（避开左右面板：左 0-364px、右 1556-1920px；顶 64、底 940）
    // 截图缩放到 960x540，故坐标减半：x 300-700 → 原图 600-1400；y 60-450 → 原图 120-900
    const x0 = 300, y0 = 60, x1 = 700, y1 = 450
    const d = ctx.getImageData(x0, y0, x1 - x0, y1 - y0).data
    let lit = 0, warm = 0, cool = 0, maxB = 0, sum = 0
    for (let i = 0; i < d.length; i += 4) {
      const r = d[i], g = d[i + 1], bl = d[i + 2]
      const br = r + g + bl
      sum += br
      if (br > maxB) maxB = br
      if (br > 90) {
        lit++
        if (r > bl + 12) warm++        // 偏金
        else if (bl > r + 12) cool++   // 偏冷蓝
      }
    }
    const total = d.length / 4
    return {
      region: `${x1 - x0}x${y1 - y0}`,
      litRatio: +(lit / total).toFixed(4),
      warmPx: warm, coolPx: cool,
      maxBrightness: maxB,
      meanBrightness: +(sum / total / 3).toFixed(2),
    }
  }, b64)
  console.log(JSON.stringify(res, null, 1))
  await b.close()
})().catch((e) => { console.error('FAIL', e.message); process.exit(1) })
