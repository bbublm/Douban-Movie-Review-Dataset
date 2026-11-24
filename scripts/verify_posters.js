// 海报渲染校验：截图看不出「图片到底有没有加载成功」，
// 所以直接读 <img> 的 naturalWidth —— 只有真正下载并解码成功才 > 0。
// 用法：node scripts/verify_posters.js
const puppeteer = require('puppeteer-core')

const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe'
const BASE = 'http://127.0.0.1:5173'

async function run() {
  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: 'new',
    args: ['--no-sandbox', '--disable-dev-shm-usage'],
  })
  const page = await browser.newPage()
  await page.setViewport({ width: 1440, height: 900 })

  const errors = []
  page.on('requestfailed', (r) => errors.push(`${r.url()} (${r.failure()?.errorText})`))
  page.on('response', (r) => {
    if (r.status() >= 400) errors.push(`HTTP ${r.status()} ${r.url()}`)
  })

  async function check(url, label, maxWaitMs = 20000) {
    await page.goto(url, { waitUntil: 'networkidle2', timeout: 30000 })
    // 轮询等待：图片解码成功 naturalWidth>0。并发取图较慢，最多等 maxWaitMs。
    const deadline = Date.now() + maxWaitMs
    let stat = { total: 0, loaded: 0, broken: [] }
    while (Date.now() < deadline) {
      await new Promise((r) => setTimeout(r, 1500))
      stat = await page.evaluate(() => {
        const imgs = Array.from(document.querySelectorAll('img'))
        const withSrc = imgs.filter((i) => i.src && i.src !== location.href)
        // ★ lazy 图片在视口外是「还没加载」，complete=false —— 不能算裂图，
        //   只有 complete=true 且 naturalWidth=0 才是真的加载失败。
        return {
          total: imgs.length,
          loaded: withSrc.filter((i) => i.naturalWidth > 0).length,
          pending: withSrc.filter((i) => !i.complete).length,
          broken: withSrc.filter((i) => i.complete && i.naturalWidth === 0)
            .map((i) => i.src.slice(0, 90)),
        }
      })
      // 页面还没渲染出图片（数据加载中）时继续等，不能立即退出
      if (stat.total > 0 && stat.loaded + stat.broken >= stat.total) break
    }
    const ok = stat.loaded > 0 && stat.broken.length === 0
    console.log(`  ${ok ? '✅' : '⚠ '} ${label}: ${stat.loaded}/${stat.total} 张加载成功` +
      (stat.pending ? `（${stat.pending} 张 lazy 待加载）` : ''))
    if (stat.broken.length) stat.broken.slice(0, 5).forEach((b) => console.log(`       裂图: ${b}`))
    return ok
  }

  console.log('\n=== 海报渲染校验 ===')
  const r1 = await check(`${BASE}/`, '首页（热门 + 影评速览）')
  const r2 = await check(`${BASE}/search?q=hero`, '检索结果页')

  console.log('\n=== 失败请求 / 4xx ===')
  if (errors.length) {
    Array.from(new Set(errors)).slice(0, 10).forEach((e) => console.log('  -', e))
  } else {
    console.log('  无')
  }

  await browser.close()
  console.log(`\n结果：${[r1, r2].filter(Boolean).length}/2 页图片全部就绪\n`)
}

run().catch((e) => {
  console.error('运行失败：', e.message)
  process.exit(1)
})
