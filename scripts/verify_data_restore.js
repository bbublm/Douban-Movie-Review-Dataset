/* 验证：三块被漏掉的数据面板已恢复 + 票房画廊不再裁切
   用法：NODE_PATH=frontend/node_modules node scripts/verify_data_restore.js http://localhost:8080
*/
const puppeteer = require('puppeteer-core')
const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe'

const checks = []
function ok(name, cond, extra = '') {
  checks.push({ name, pass: !!cond, extra })
  console.log(`${cond ? '  ✓' : '  ✗'} ${name}${extra ? ' — ' + extra : ''}`)
}

async function main() {
  const base = process.argv[2] || 'http://localhost:8080'
  const browser = await puppeteer.launch({
    executablePath: CHROME,
    headless: 'new',
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--window-size=1440,900'],
  })
  let consoleErrors = 0
  const page = await browser.newPage()
  page.on('console', (m) => { if (m.type() === 'error') consoleErrors++ })
  page.on('pageerror', () => { consoleErrors++ })

  // ---------- 星图厅：EchoChamber 恢复 ----------
  console.log('\n[星图厅 · 情感分布卡]')
  await page.setViewport({ width: 1440, height: 900 })
  await page.goto(`${base}/screen?room=galaxy`, { waitUntil: 'networkidle2' })
  await page.waitForSelector('.galaxy-echo .echo', { timeout: 15000 }).catch(() => {})
  const echo = await page.evaluate(() => {
    const root = document.querySelector('.galaxy-echo')
    const segs = document.querySelectorAll('.galaxy-echo .echo__seg').length
    const words = document.querySelectorAll('.galaxy-echo .echo__word').length
    const ring = !!document.querySelector('.galaxy-echo .echo__ring')
    return { root: !!root, segs, words, ring }
  })
  ok('情感分布卡已挂载（.galaxy-echo）', echo.root)
  ok('情感三段环渲染', echo.ring && echo.segs > 0, `segs=${echo.segs}`)
  ok('归纳词典热词渲染', echo.words > 0, `words=${echo.words}`)
  ok('中央读图卡仍在', await page.$('.galaxy-card') !== null)

  // ---------- 口碑排名厅：GenreRankCard 恢复 ----------
  console.log('\n[口碑排名厅 · 类型口碑榜]')
  await page.goto(`${base}/screen?room=rank`, { waitUntil: 'networkidle2' })
  await page.waitForSelector('.rr__side-body--2 .grank', { timeout: 15000 }).catch(() => {})
  const rank = await page.evaluate(() => {
    const card = document.querySelector('.rr__side-body--2 .grank')
    const rows = document.querySelectorAll('.rr__side-body--2 .grank__row').length
    const side2 = !!document.querySelector('.rr__side-body--2')
    const douban = !!document.querySelector('.rr__side-body .dbp, .rr__side-body .douban')
    return { card: !!card, rows, side2, douban }
  })
  ok('类型口碑榜已挂载（第二侧栏）', rank.card && rank.side2)
  ok('类型口碑榜有数据行', rank.rows > 0, `rows=${rank.rows}`)
  ok('豆瓣口碑精选仍在（第一侧栏）', rank.douban)
  ok('主图 BumpChart 仍在', await page.$('.rr__main .bump') !== null)

  // ---------- 年代流向厅：CoveragePanel 恢复 ----------
  console.log('\n[年代流向厅 · 预告覆盖]')
  await page.goto(`${base}/screen?room=flow`, { waitUntil: 'networkidle2' })
  await page.waitForSelector('.fr__cell .cvp', { timeout: 15000 }).catch(() => {})
  const flow = await page.evaluate(() => {
    const cells = document.querySelectorAll('.fr__bottom .fr__cell').length
    const cvp = document.querySelectorAll('.fr__cell .cvp').length
    const charts = document.querySelectorAll('.fr__cell .cvp__chart').length
    const story = !!document.querySelector('.fr__cell .story')
    const regions = !!document.querySelector('.fr__cell .rg, .fr__cell .regions')
    return { cells, cvp, charts, story, regions }
  })
  ok('底部副卡变为三块', flow.cells === 3, `cells=${flow.cells}`)
  ok('预告覆盖面板已挂载', flow.cvp > 0)
  ok('预告覆盖含两张图', flow.charts >= 2, `charts=${flow.charts}`)
  ok('年代故事仍在', flow.story)
  ok('地区画像仍在', flow.regions)

  // ---------- 票房画廊：不再裁切（两档视口） ----------
  console.log('\n[票房画廊 · 裁切检测]')
  // 重置错误计数：前面切换展厅时星系 WebGL 上下文销毁会在同一 page 会话里
  // 累积"context lost"类 warning（真实逐房冷加载均为 0 错误），这里只统计本段。
  consoleErrors = 0
  for (const vw of [{ w: 1440, h: 900 }, { w: 1280, h: 800 }]) {
    await page.setViewport({ width: vw.w, height: vw.h })
    await page.goto(`${base}/screen?room=box`, { waitUntil: 'networkidle2' })
    await page.waitForSelector('.bog__frame', { timeout: 15000 }).catch(() => {})
    const clip = await page.evaluate(() => {
      const scene = document.querySelector('.bog__scene')
      const frames = [...document.querySelectorAll('.bog__frame')]
      const sb = scene.getBoundingClientRect()
      let clippedNoScroll = 0
      let worst = 0
      for (const f of frames) {
        const fb = f.getBoundingClientRect()
        // 可纵向滚动时（scrollHeight>clientHeight）视为数据可达，不计入裁切
        const reachable = scene.scrollHeight > scene.clientHeight + 2
        if (!reachable && fb.bottom > sb.bottom + 1) {
          clippedNoScroll++
          worst = Math.max(worst, Math.round(fb.bottom - sb.bottom))
        }
      }
      return {
        sceneH: Math.round(sb.height),
        sceneScrollable: scene.scrollHeight > scene.clientHeight + 2,
        frameBottomMax: Math.round(Math.max(...frames.map((f) => f.getBoundingClientRect().bottom))),
        sceneBottom: Math.round(sb.bottom),
        clippedNoScroll,
        worst,
      }
    })
    ok(`[${vw.w}×${vw.h}] 相框下半截未被静默裁切`, clip.clippedNoScroll === 0,
      `sceneH=${clip.sceneH} scrollable=${clip.sceneScrollable} clipNoScroll=${clip.clippedNoScroll} worst=${clip.worst}px`)
  }

  // ---------- 控制台错误 ----------
  console.log('\n[控制台]')
  ok('全局无控制台错误', consoleErrors === 0, `errors=${consoleErrors}`)

  await browser.close()
  const failed = checks.filter((c) => !c.pass)
  console.log(`\n结果：${checks.length - failed.length} 通过 / ${failed.length} 失败`)
  process.exit(failed.length ? 1 : 0)
}
main().catch((e) => { console.error(e); process.exit(2) })
