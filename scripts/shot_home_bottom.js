const puppeteer = require('puppeteer-core')
const path = require('path')

const BASE = process.argv[2] || 'http://localhost:8080'
const SHOT_DIR = 'C:\\Users\\16280\\Desktop\\movie-recommendation-system-main\\.workbuddy\\screenshots'
const CHROME = 'C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe'

;(async () => {
  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: 'new',
    args: ['--no-sandbox', '--disable-gpu', '--window-size=1440,1000'],
    defaultViewport: { width: 1440, height: 1000 },
  })
  const page = await browser.newPage()
  await page.goto(BASE + '/', { waitUntil: 'networkidle0' })
  // Scroll to the very bottom
  await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight))
  await new Promise(r => setTimeout(r, 500))
  await page.screenshot({ path: path.join(SHOT_DIR, 'pg-01-home-bottom.png') })
  console.log('[shot] pg-01-home-bottom.png')
  await browser.close()
})()
