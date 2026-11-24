// ============================================================
// 影评洞察馆 · 高级分析 + 走廊静态真实海报 回归
// 用法：NODE_PATH=<frontend/node_modules> node scripts/verify_advanced_insights.js http://localhost:8080
// ------------------------------------------------------------
// 覆盖（2026-11-04 用户最新红线）：
//   A. 走廊海报「挂在哪里就在哪里显示」——WebGL 挂画直贴真实海报，
//      没有 DOM 悬停命中区、没有悬停预览卡，鼠标移上去也不会弹卡。
//   B. 数据必须真分析出来：四个新接口返回 Pearson / 回归 / lift /
//      四分位 / 三层流向等「现算」结果，而不是把原始字段直接摆出来。
//   C. 五间展厅各挂一张不同形式的分析图，canvas 真渲染、结论文案非空。
//   D. 全流程 0 控制台错误 / 0 pageerror。
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

async function api(p) {
  const r = await fetch(`${BASE}/api/v1/insights/${p}`)
  if (!r.ok) throw new Error(`${p} HTTP ${r.status}`)
  return r.json()
}

;(async () => {
  fs.mkdirSync(OUT, { recursive: true })

  // ---------- B. 后端真实分析接口 ----------
  console.log('\n=== 真实分析接口（不能是硬编码 / 现成字段直摆） ===')
  const hp = await api('hall-posters')
  check('走廊片单 14 部且全部带海报代理地址', hp.items.length >= 14
    && hp.items.every((m) => m.poster_url && m.poster_url.includes('/api/v1/img')),
    `${hp.items.length} 部`)
  check('片单是按类型聚合选出的代表片（口碑 / 票房角色 + 分析 note）',
    hp.items.every((m) => m.role && m.genre && m.note),
    hp.items.slice(0, 2).map((m) => `${m.title}/${m.role}`).join('，'))
  check('片单去重（14 个挂位挂 14 部不同的片）',
    new Set(hp.items.map((m) => m.movie_id)).size === hp.items.length)

  const kg = await api('knowledge-graph')
  check('知识图谱节点 ≥30、显著共现边 ≥40', kg.nodes.length >= 30 && kg.links.length >= 40,
    `${kg.total_movies} 部片 / ${kg.nodes.length} 节点 / ${kg.links.length} 边`)
  check('每条边都带现算的 lift（>1 才算正相关）',
    kg.links.every((e) => typeof e.lift === 'number' && e.lift > 1.02),
    `最强 ${Math.max(...kg.links.map((e) => e.lift)).toFixed(2)}×`)
  check('节点含类型 / 导演 / 演员三类实体',
    new Set(kg.nodes.map((n) => n.kind)).size >= 3)

  const co = await api('correlations')
  check('相关矩阵是 5×5 且由 Pearson 现算（对角线 1、对称、非全同）',
    co.matrix.length === 5 && co.matrix.every((r) => r.length === 5)
    && co.matrix.every((r, i) => Math.abs(r[i] - 1) < 1e-6)
    && co.matrix.every((r, i) => r.every((v, j) => Math.abs(v - co.matrix[j][i]) < 1e-6))
    && new Set(co.matrix.flat().map((v) => v.toFixed(3))).size >= 8,
    `${co.sample_size} 部样本 / ${new Set(co.matrix.flat().map((v) => v.toFixed(3))).size} 个不同 r`)
  check('预算→票房最小二乘回归有斜率与 R²（不是把散点直接摆上去）',
    co.regression && co.regression.r2 > 0 && co.regression.slope > 0,
    `r²=${co.regression?.r2}, slope=${co.regression?.slope}`)
  check('ROI 箱线是四分位五数概括，类型画像含命中率',
    co.roi_by_genre.length >= 5
    && ['min', 'q1', 'median', 'q3', 'max'].every((k) => k in co.roi_by_genre[0])
    && co.profiles.every((p) => typeof p.hit_rate === 'number'),
    `${co.roi_by_genre.length} 类型箱线 / ${co.profiles.length} 类型画像`)

  const fl = await api('flows')
  check('三层桑基年代层跨类型共享（不再碎成 56 个节点）',
    fl.nodes.length <= 24 && fl.links.length >= 30,
    `${fl.nodes.length} 节点 / ${fl.links.length} 边 / ${fl.heat.length} 热力格`)
  check('年代×类型口碑热力含真实均分', fl.heat.length >= 20
    && fl.heat.every((h) => typeof h.avg_rating === 'number' && h.movies > 0))

  // 上游图床偶发 502：代理须降级成 200 占位图，不能把 5xx 甩给浏览器
  const badImg = await fetch(`${BASE}/api/v1/img?url=` + encodeURIComponent(
    'https://image.tmdb.org/t/p/w500/definitely-not-exist-xyz.jpg'))
  check('海报上游不可用时降级为 200 占位 SVG（不产生控制台 5xx）',
    badImg.status === 200 && (badImg.headers.get('content-type') || '').includes('svg'),
    `${badImg.status} ${badImg.headers.get('content-type')}`)
  const evil = await fetch(`${BASE}/api/v1/img?url=` + encodeURIComponent('https://evil.example.com/a.jpg'))
  check('降级不放松域名白名单（非白名单仍 400）', evil.status === 400, String(evil.status))

  // ---------- 浏览器 ----------
  const browser = await puppeteer.launch({
    executablePath: CHROME, headless: 'new',
    args: ['--hide-scrollbars', '--no-sandbox', '--disable-dev-shm-usage'],
    defaultViewport: { width: 1440, height: 900 },
  })
  const page = await browser.newPage()
  const errs = []
  const httpErrors = []
  page.on('console', (m) => { if (m.type() === 'error') errs.push(m.text().slice(0, 160)) })
  page.on('pageerror', (e) => errs.push('PAGEERROR ' + e.message.slice(0, 160)))
  page.on('response', (r) => { if (r.status() >= 400) httpErrors.push(`HTTP ${r.status()} ${r.url().slice(0, 130)}`) })

  console.log('\n=== A. 走廊静态真实海报（无悬停弹卡） ===')
  await page.goto(`${BASE}/screen`, { waitUntil: 'networkidle2', timeout: 45000 })
  await sleep(1200)
  await page.evaluate(() => document.querySelector('.ih__box')?.click())
  await sleep(2600)

  const hall = await page.evaluate(() => {
    const c = document.querySelector('.ih__gl')
    return {
      bound: Number(c?.dataset.posterBound || 0),
      slots: Number(c?.dataset.posterSlots || 0),
      real: Number(c?.dataset.posterReal || 0),
      posters: Number(c?.dataset.posters || 0),
      hits: document.querySelectorAll('.ih__poster-hit').length,
      cards: document.querySelectorAll('.ih__poster-card').length,
      doors: document.querySelectorAll('.ih__room:not(.is-hidden)').length,
    }
  })
  check('14 个挂位绑定了真实片单', hall.bound >= 14 && hall.slots === 14 && hall.posters >= 14,
    `bound=${hall.bound}, slots=${hall.slots}`)
  check('真实海报贴图已挂上 WebGL 挂画（非手绘占位）', hall.real >= 8,
    `${hall.real}/14 张真实海报加载成功`)
  check('悬停命中层 / 预览卡已从 DOM 彻底移除', hall.hits === 0 && hall.cards === 0,
    `hit=${hall.hits}, card=${hall.cards}`)
  check('开封后五扇门仍全部可见（移除海报层没伤到门）', hall.doors === 5, String(hall.doors))

  // 鼠标扫过挂画所在的左右两侧，必须不弹出任何卡片
  for (const [x, y] of [[250, 300], [1180, 320], [330, 480], [1100, 520]]) {
    await page.mouse.move(x, y)
    await sleep(140)
  }
  const afterHover = await page.evaluate(() => ({
    cards: document.querySelectorAll('.ih__poster-card').length,
    hits: document.querySelectorAll('.ih__poster-hit').length,
  }))
  check('鼠标扫过挂画不弹海报（用户明确取消的交互）',
    afterHover.cards === 0 && afterHover.hits === 0)
  await page.screenshot({ path: `${OUT}/advanced-hall-posters.png` })

  // ---------- C. 五间展厅各一种高级分析图 ----------
  console.log('\n=== C. 五间展厅高级分析图（结论先行 + 真 canvas） ===')
  const ROOMS = [
    ['galaxy', '口碑星图', '知识图谱'],
    ['box', '票房分析', '相关矩阵'],
    ['rank', '口碑排名', '类型雷达'],
    ['flow', '年代流向', '三层流向'],
    ['diverge', '口碑分歧', 'ROI 箱线'],
  ]
  for (const [key, zh, label] of ROOMS) {
    await page.goto(`${BASE}/screen?room=${key}`, { waitUntil: 'networkidle2', timeout: 45000 })
    await sleep(2100)
    const st = await page.evaluate(() => {
      const ac = document.querySelector('.ac')
      if (!ac) return { ac: 0 }
      const cs = [...ac.querySelectorAll('canvas')]
      const r = ac.getBoundingClientRect()
      return {
        ac: 1,
        title: ac.querySelector('.ac__title')?.textContent.trim() || '',
        kicker: ac.querySelector('.ac__kicker')?.textContent.trim() || '',
        note: ac.querySelector('.ac__note')?.textContent.trim() || '',
        tabs: ac.querySelectorAll('.ac__tab').length,
        canvas: cs.length,
        minCanvas: Math.min(...cs.map((c) => Math.min(c.width, c.height)), 0),
        w: Math.round(r.width), h: Math.round(r.height),
        pageH: document.documentElement.scrollHeight,
        back: !!document.querySelector('.room-nav__back'),
      }
    })
    check(`${zh}：分析卡 + ${label} canvas 真渲染`,
      st.ac === 1 && st.canvas >= 1 && st.w > 300 && st.h > 150,
      `${st.w}×${st.h}, canvas=${st.canvas}, pageH=${st.pageH}`)
    check(`${zh}：结论 note 非空、不是把字段名摆上去`,
      st.note.length >= 8 && !/^(sample|data|items)/i.test(st.note),
      st.note.slice(0, 46))
    check(`${zh}：回大厅出口仍在（窄屏红线）`, st.back)
    // 长页滚到分析卡本身再实拍，避免只截到展厅顶部的主图
    await page.evaluate(() => document.querySelector('.ac')?.scrollIntoView({ block: 'center' }))
    await sleep(500)
    await page.screenshot({ path: `${OUT}/advanced-${key}.png` })
  }

  // 放大交互 + 切换 tab（真的可交互，不是静态截图）
  await page.goto(`${BASE}/screen?room=box`, { waitUntil: 'networkidle2', timeout: 45000 })
  await sleep(1700)
  await page.evaluate(() => document.querySelector('.ac__expand')?.click())
  await sleep(700)
  const expanded = await page.evaluate(() => !!document.querySelector('.ac.is-expanded'))
  check('票房分析卡可放大成全屏纸面', expanded)
  await page.keyboard.press('Escape')
  await sleep(400)
  check('Esc 可收起放大态', await page.evaluate(() => !document.querySelector('.ac.is-expanded')))

  console.log('\n=== D. 控制台 ===')
  if (errs.length) errs.slice(0, 8).forEach((e) => console.log('  - ' + e))
  if (httpErrors.length) Array.from(new Set(httpErrors)).slice(0, 12).forEach((e) => console.log('  ! ' + e))
  check('0 控制台错误 / 0 pageerror', errs.length === 0, `${errs.length} 条`)

  await browser.close()
  console.log(`\n结果：${pass} 通过 / ${fail} 失败\n`)
  process.exit(fail ? 1 : 0)
})().catch((e) => {
  console.error('运行失败：', e)
  process.exit(1)
})
