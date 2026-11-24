// 实拍两个参考站，供视觉分析用（一次性脚本）
const puppeteer = require('puppeteer-core')

const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe'
const OUT = 'C:/Users/16280/Desktop/movie-recommendation-system-main/.workbuddy/refshots'

const TARGETS = [
  { name: 'a24', url: 'https://a24.raviklaassens.com/', waits: [3500, 2500] },
  { name: 'itomdev', url: 'https://itomdev.com/', waits: [4000] },
]

;(async () => {
  const fs = require('fs')
  fs.mkdirSync(OUT, { recursive: true })
  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: 'new',
    args: ['--no-sandbox', '--disable-dev-shm-usage', '--window-size=1440,900'],
    defaultViewport: { width: 1440, height: 900 },
  })
  for (const t of TARGETS) {
    const page = await browser.newPage()
    try {
      await page.goto(t.url, { waitUntil: 'networkidle2', timeout: 45000 })
    } catch (e) {
      console.log(`${t.name}: goto warn ${e.message}`)
    }
    let shotIdx = 0
    for (const w of t.waits) {
      await new Promise((r) => setTimeout(r, w))
      const f = `${OUT}/${t.name}-${shotIdx}.png`
      await page.screenshot({ path: f })
      console.log(`saved ${f}`)
      shotIdx++
      // 第二张：往下滚一屏（a24 长页）
      if (shotIdx < t.waits.length || t.name === 'a24') {
        await page.evaluate(() => window.scrollBy(0, 700))
      }
    }
    // dump 首屏可见文字，辅助理解
    const text = await page.evaluate(() => document.body.innerText.slice(0, 600))
    console.log(`--- ${t.name} text ---\n${text}\n---`)
    await page.close()
  }
  await browser.close()
  console.log('done')
})()
