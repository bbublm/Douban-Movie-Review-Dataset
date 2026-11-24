// ============================================================
// 院线热映 · 站内采集档案 回归
// 用法：NODE_PATH=<frontend/node_modules> node scripts/verify_nowplaying_internal.js http://localhost:8080
// ------------------------------------------------------------
// 用户红线（2026-11-04）：「点击首页院线热映的影片不应该是跳转到豆瓣页面，
// 我这要爬虫，不是要跳转」——卡片必须进站内详情页，读爬虫已落库的 ES 文档。
// 覆盖：
//   A. 后端详情接口按 _id 读真实采集文档、库内同名匹配是真检索、坏 id 404
//   B. 首页 10 张卡片全部站内链接，无任何豆瓣外链 / target=_blank
//   C. 详情页真实字段、双源评分对照、库内关联、同榜互跳、0 控制台错误
// ============================================================
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
const norm = (s) => String(s || '').replace(/[\s:：·・\-—_,，.。!！?？'"“”‘’()（）\[\]【】《》]/g, '').toLowerCase()

async function api(p) {
  const r = await fetch(`${BASE}/api/v1/douban/${p}`)
  if (!r.ok) throw new Error(`${p} HTTP ${r.status}`)
  return r.json()
}

;(async () => {
  fs.mkdirSync(OUT, { recursive: true })

  // ---------- A. 后端真实采集档案 ----------
  console.log('\n=== A. 站内采集档案接口 ===')
  const list = await api('nowplaying')
  check('榜单来自已采集索引（非空且带采集时间）',
    list.count > 0 && list.items.length === list.count && !!list.collected_at,
    `${list.count} 条 / ${list.collected_at?.slice(0, 10)}`)

  const first = list.items[0]
  const d = await api(`nowplaying/${encodeURIComponent(first.douban_id)}`)
  check('详情按 id 读同一条采集文档', d.douban_id === first.douban_id && d.title === first.title,
    `《${d.title}》`)
  check('详情带爬虫落库字段（评分/票数/导演/主演/片长/来源）',
    typeof d.douban_rating === 'number' && d.douban_votes > 0
    && Array.isArray(d.region) && Array.isArray(d.director) && Array.isArray(d.actors)
    && !!d.duration && !!d.source && !!d.collected_at,
    `★${d.douban_rating} · ${d.douban_votes} 人 · ${d.duration}`)
  check('海报地址已改写为站内代理', !d.poster || d.poster.includes('/api/v1/img'))

  // 找一条库内确实有同名影片的档案，验证匹配是真检索、不是硬编码
  let withMatch = null
  for (const m of list.items.slice(0, 15)) {
    const one = await api(`nowplaying/${encodeURIComponent(m.douban_id)}`)
    if (one.library_match) { withMatch = one; break }
  }
  check('库内关联是真实同名检索（片名一致 + movie_id 存在）',
    !!withMatch && !!withMatch.library_match.movie_id
    && norm(withMatch.library_match.title) === norm(withMatch.title),
    withMatch ? `${withMatch.title} → ${withMatch.library_match.movie_id}` : '无匹配')

  let notFound = 0
  try { await api('nowplaying/definitely-not-exist-999') } catch (e) { notFound = Number(String(e.message).match(/HTTP (\d+)/)?.[1] || 0) }
  check('不存在的档案返回 404（不兜底伪造数据）', notFound === 404, `HTTP ${notFound}`)

  // ---------- B/C. 浏览器：首页链接 + 详情页 ----------
  const browser = await puppeteer.launch({
    executablePath: CHROME, headless: 'new',
    args: ['--hide-scrollbars', '--no-sandbox', '--disable-dev-shm-usage'],
    defaultViewport: { width: 1440, height: 900 },
  })
  const page = await browser.newPage()
  const errs = []
  page.on('console', (m) => { if (m.type() === 'error') errs.push(m.text().slice(0, 160)) })
  page.on('pageerror', (e) => errs.push('PAGEERROR ' + e.message.slice(0, 160)))

  console.log('\n=== B. 首页卡片：一律站内，不外链 ===')
  await page.goto(`${BASE}/`, { waitUntil: 'networkidle2', timeout: 45000 })
  await page.waitForSelector('.npc', { timeout: 15000 })
  const cards = await page.$$eval('.npc', (els) => els.map((a) => ({
    tag: a.tagName, href: a.getAttribute('href'), target: a.getAttribute('target'),
    text: a.querySelector('.npc__title')?.textContent?.trim() || '',
    mask: a.querySelector('.npc__mask')?.textContent?.trim() || '',
  })))
  check('首页院线热映 10 张卡片', cards.length === 10, `${cards.length} 张`)
  check('全部指向站内 /nowplaying/:id', cards.every((c) => c.href && c.href.startsWith('/nowplaying/')))
  check('没有一个外链 / 新窗口跳转', cards.every((c) => !c.target && !/^https?:/.test(c.href || '')))
  check('卡片 hover 文案明确「查看采集档案」', cards.every((c) => c.mask.includes('采集档案')))
  const extLinks = await page.$$eval('a[href]', (els) => els.map((a) => a.getAttribute('href'))
    .filter((h) => /douban\.com|doubanio\.com/i.test(h || '')))
  check('首页源码里没有任何豆瓣站点链接', extLinks.length === 0, `${extLinks.length} 个`)
  await page.screenshot({ path: `${OUT}/nowplaying-home.png`, fullPage: false })

  console.log('\n=== C. 点击进站内详情页 ===')
  await page.click('.npc')
  await page.waitForFunction(() => location.pathname.startsWith('/nowplaying/'), { timeout: 15000 })
  await page.waitForSelector('.npv__hero', { timeout: 15000 })
  const pathAfter = await page.evaluate(() => location.pathname)
  const pageCount = (await browser.pages()).length
  check('点卡片后 URL 变为站内详情，不打开新标签',
    pathAfter.startsWith('/nowplaying/') && pageCount <= 2,
    `${pathAfter} / ${pageCount} 个标签`)
  const view = await page.evaluate(() => ({
    title: document.querySelector('.npv__title')?.textContent?.trim() || '',
    score: document.querySelector('.npv__score b')?.textContent?.trim() || '',
    facts: [...document.querySelectorAll('.npv__facts dt')].map((e) => e.textContent.trim()),
    cards: [...document.querySelectorAll('.npv__card-h')].map((e) => e.textContent.trim()),
    collected: document.querySelector('.npv__kv b')?.textContent?.trim() || '',
    ops: [...document.querySelectorAll('.npv__ops a')].map((a) => a.getAttribute('href')),
    ext: [...document.querySelectorAll('a[href]')].map((a) => a.getAttribute('href'))
      .filter((h) => /^https?:/.test(h || '')),
    peers: document.querySelectorAll('.npv__peers-block .npc').length,
  }))
  check('详情页标题与采集评分真实渲染', view.title.length > 0 && /^\★\s?[\d.]+/.test(view.score),
    `《${view.title}》 ${view.score}`)
  check('爬虫字段逐项展示（年份/地区/片长/导演/主演）',
    ['上映年份', '制片地区', '片长', '导演', '主演'].every((k) => view.facts.includes(k)))
  check('采集档案卡带真实采集时间', /\d{4}/.test(view.collected), view.collected)
  check('操作按钮全部站内（片库/洞察/回榜）',
    view.ops.length >= 3 && view.ops.every((h) => h && h.startsWith('/')))
  check('详情页零外部链接', view.ext.length === 0, `${view.ext.length} 个`)
  check('同榜影片也是站内互跳卡片', view.peers > 0, `${view.peers} 张`)
  await page.screenshot({ path: `${OUT}/nowplaying-detail.png`, fullPage: false })

  // 深链到有库内匹配的档案：验证双源评分对照是真算的
  if (withMatch) {
    await page.goto(`${BASE}/nowplaying/${encodeURIComponent(withMatch.douban_id)}`, { waitUntil: 'networkidle2' })
    await page.waitForSelector('.npv__duo', { timeout: 15000 })
    const duo = await page.evaluate(() => ({
      texts: [...document.querySelectorAll('.npv__duo b')].map((e) => e.textContent.trim()),
      note: document.querySelector('.npv__duo-note')?.textContent?.trim() || '',
      toMovie: [...document.querySelectorAll('.npv__ops a')].map((a) => a.getAttribute('href'))
        .find((h) => h && h.startsWith('/movie/')),
    }))
    const expect = [withMatch.douban_rating.toFixed(1), withMatch.library_match.rating.toFixed(1)]
    check('双源评分对照数字来自接口真实值',
      duo.texts.length === 2 && duo.texts[0] === expect[0] && duo.texts[1] === expect[1],
      duo.texts.join(' vs '))
    check('对照结论文案自动生成（含差值）', /相差/.test(duo.note) && /\d/.test(duo.note), duo.note.slice(0, 44))
    check('一键进库内影片档案', duo.toMovie === `/movie/${withMatch.library_match.movie_id}`, duo.toMovie || '—')
    await page.screenshot({ path: `${OUT}/nowplaying-duo.png`, fullPage: false })
  }

  // 同榜互跳：点第一张 peer 卡片，URL 与标题都要换
  if (view.peers > 0) {
    await page.goto(`${BASE}/nowplaying/${encodeURIComponent(first.douban_id)}`, { waitUntil: 'networkidle2' })
    await page.waitForSelector('.npv__peers-block .npc', { timeout: 15000 })
    const before = await page.evaluate(() => location.pathname)
    await page.click('.npv__peers-block .npc')
    await page.waitForFunction((p) => location.pathname !== p, { timeout: 15000 }, before)
    await sleep(600)
    const after = await page.evaluate(() => ({
      path: location.pathname,
      title: document.querySelector('.npv__title')?.textContent?.trim() || '',
    }))
    check('同榜卡片站内互跳并重新读档', after.path !== before && after.title.length > 0,
      `${before} → ${after.path}《${after.title}》`)
  }

  // 影片详情页也不再有豆瓣外链
  await page.goto(`${BASE}/movie/${encodeURIComponent(withMatch ? withMatch.library_match.movie_id : 'tt7131870')}`,
    { waitUntil: 'networkidle2' })
  const movieExt = await page.$$eval('a[href]', (els) => els.map((a) => a.getAttribute('href'))
    .filter((h) => /douban\.com/i.test(h || '')))
  check('影片详情页不再出现豆瓣外链', movieExt.length === 0, `${movieExt.length} 个`)

  console.log('\n=== D. 控制台 ===')
  if (errs.length) errs.slice(0, 8).forEach((e) => console.log('  - ' + e))
  check('0 控制台错误 / 0 pageerror', errs.length === 0, `${errs.length} 条`)

  await browser.close()
  console.log(`\n结果：${pass} 通过 / ${fail} 失败`)
  process.exit(fail ? 1 : 0)
})().catch((e) => { console.error('FATAL', e); process.exit(1) })
