// ============================================================
// 影评洞察馆 · 大厅 3D 深度层次回归
// 用法：NODE_PATH=<frontend/node_modules> node scripts/verify_depth.js http://localhost:8080
// ------------------------------------------------------------
// 覆盖：合盒首屏（看不到门）→ 开封仪式 → 四层飞行穿越、深度刻度点击、
//       门牌随相机投影、穿模后的画面恢复、回大厅重置、合上盒子重开封、
//       窄屏降级、0 控制台错误。
// ★ 2026-11-04 六次改版再加红线：走廊长 88 单位、三排门间隔 15.5、
//   天花垂挂 14 张海报、点门板中间才开门（木牌纯展示不可点）、
//   合盒盒子须为看得见顶面/正面/侧面的三点透视 3D 立方体。
// ★ 2026-11-04 新增红线：参考 itomdev.com「一张纸撕开后才掉进走廊」，
//   用户要求「应该先打开电影盒子才能看到这些门」。首屏必须只有合盖盒子，
//   门牌/深度刻度一律隐藏；开封后五扇门才出现。本脚本守住这条顺序。
// ★ 历史事故：相机沿中轴推进会穿过中央电影盒子，盒内光柱贴脸放大成
//   一整片米黄，把整条走廊盖住（中段看似「全白空白」）。修复方式是
//   盒子在镜头靠近时化作光退场。本脚本用「中段可见门数 = 3」和
//   「深处可见门数 = 1」守住这条纵深链路，不再退回单张平面透视图。
// ============================================================
const puppeteer = require('puppeteer-core')
const fs = require('fs')
const path = require('path')
const CHROME = 'C:/Program Files/Google/Chrome/Application/chrome.exe'
const BASE = process.argv[2] || 'http://localhost:8080'
const OUT = path.resolve(__dirname, '..', '.workbuddy', 'screenshots')
const sleep = (ms) => new Promise((r) => setTimeout(r, ms))
let pass = 0
let fail = 0
const check = (name, ok, extra = '') => {
  if (ok) { pass++; console.log('  ✓ ' + name + (extra ? ' — ' + extra : '')) }
  else { fail++; console.log('  ✗ ' + name + (extra ? ' — ' + extra : '')) }
}

;(async () => {
  fs.mkdirSync(OUT, { recursive: true })
  const browser = await puppeteer.launch({
    executablePath: CHROME, headless: 'new',
    args: ['--hide-scrollbars', '--no-sandbox'],
    defaultViewport: { width: 1440, height: 900 },
  })
  const page = await browser.newPage()
  const errs = []
  page.on('console', (m) => { if (m.type() === 'error') errs.push(m.text().slice(0, 140)) })
  page.on('pageerror', (e) => errs.push('PAGEERROR ' + e.message.slice(0, 140)))

  await page.goto(BASE + '/screen', { waitUntil: 'networkidle2', timeout: 45000 })
  await sleep(2800)

  const state = () => page.evaluate(() => ({
    depth: document.querySelector('.ih__depth-now')?.textContent.trim() || '',
    on: [...document.querySelectorAll('.ih__depth-dot')].findIndex((d) => d.classList.contains('is-on')),
    dots: document.querySelectorAll('.ih__depth-dot').length,
    doors: document.querySelectorAll('.ih__room').length,
    visible: [...document.querySelectorAll('.ih__room')].filter((d) => !d.classList.contains('is-hidden')).length,
    tops: [...document.querySelectorAll('.ih__room')].map((d) => Math.round(d.getBoundingClientRect().top)),
    canvas: (() => { const c = document.querySelector('.ih__gl'); return c ? `${c.width}x${c.height}` : null })(),
    scale: (() => {
      const c = document.querySelector('.ih__gl')
      return c ? {
        corridor: Number(c.dataset.corridor || 0),
        gap: Math.abs(Number(c.dataset.doorGap || 0)),
        posters: Number(c.dataset.posters || 0),
      } : null
    })(),
    torn: !!document.querySelector('.ih__torn path'),
    progress: document.querySelector('.ih__depth-line')?.style.getPropertyValue('--p') || '',
    boxHidden: !!document.querySelector('.ih__box')?.classList.contains('is-hidden'),
    sealed: !!document.querySelector('.ih')?.classList.contains('is-sealed'),
    opened: !!document.querySelector('.ih')?.classList.contains('is-open'),
    title: document.querySelector('.ih__title')?.textContent.trim() || '',
    seal: document.querySelector('.ih__box-seal') ? getComputedStyle(document.querySelector('.ih__box-seal')).opacity : '0',
    house: !!document.querySelector('.ih'),
  }))

  // ---------- 合盒首屏：只见到一只盖得严严实实的盒子 ----------
  const sSeal = await state()
  check('WebGL 真 3D 画布已渲染', !!sSeal.canvas && parseInt(sSeal.canvas) >= 1000, sSeal.canvas || '')
  check('首屏处于「合盒」阶段', sSeal.sealed && !sSeal.opened)
  check('五扇门 DOM 齐全（合盒时仅隐藏）', sSeal.doors === 5, String(sSeal.doors))
  check('首屏刊头提示先打开盒子', /一只盒子/.test(sSeal.title), sSeal.title)
  check('合盒时封条可见', parseFloat(sSeal.seal) > 0.5, sSeal.seal)
  check('★ 合盒时五扇门一块都不出现（用户红线）', sSeal.visible === 0, String(sSeal.visible))
  check('合盒时盒子入口可点', !sSeal.boxHidden)
  await page.screenshot({ path: `${OUT}/depth-sealed.png` })

  // ---------- 点击电影盒子开封：掀盖 → 撕纸 → 四层长廊与五扇门显现 ----------
  await page.evaluate(() => document.querySelector('.ih__box').click())
  await sleep(2300)
  const s0 = await state()
  check('点盒子完成开封', s0.opened && !s0.sealed)
  check('开封后五扇门全部可见', s0.visible === 5, String(s0.visible))
  check('开封后盒子入口收起（已化作光）', s0.boxHidden)
  check('深度刻度 4 层', s0.dots === 4, String(s0.dots))
  check('初始停在「入口」', s0.on === 0 && s0.depth === '入口', `${s0.on}/${s0.depth}`)
  check('itomdev 撕纸锯齿描边存在', s0.torn)
  check('走廊拉长到 88 单位', s0.scale?.corridor >= 80, String(s0.scale?.corridor))
  check('三排门间隔 ≥15 单位（门隔得远）', s0.scale?.gap >= 15, String(s0.scale?.gap))
  check('天花垂挂 14 张电影海报', s0.scale?.posters >= 12, String(s0.scale?.posters))
  await page.screenshot({ path: `${OUT}/depth-entry.png` })

  // ---------- 滚轮推进：透视必须真的变了 ----------
  await page.mouse.move(720, 450)
  await page.mouse.wheel({ deltaY: 620 })
  await sleep(1700)
  const s1 = await state()
  check('滚轮推进改变门牌投影（不是静态透视图）', JSON.stringify(s0.tops) !== JSON.stringify(s1.tops),
    `${s0.tops[2]} → ${s1.tops[2]}`)
  check('深度刻度随滚轮点亮到 2 层以上', s1.on >= 2, String(s1.on))
  check('深度进度条推进', parseFloat(s1.progress) > 20, s1.progress)
  check('中段保留 3 扇可见门（盒子已退场，走廊没被盖住）', s1.visible === 3, String(s1.visible))
  check('盒子命中区随盒子一起收起', s1.boxHidden)
  await page.screenshot({ path: `${OUT}/depth-middle.png` })

  // ---------- 深处 ----------
  await page.mouse.wheel({ deltaY: 900 })
  await sleep(1900)
  const s2 = await state()
  check('抵达「深处」层', s2.on === 3 && s2.depth === '深处', `${s2.on}/${s2.depth}`)
  check('深处只剩最后一扇门（确实穿过了前面的层）', s2.visible === 1, String(s2.visible))
  await page.screenshot({ path: `${OUT}/depth-deep.png` })

  // ---------- 点刻度跳转 ----------
  await page.evaluate(() => document.querySelectorAll('.ih__depth-dot')[1].click())
  await sleep(1400)
  const s3 = await state()
  check('点刻度跳到「门廊」', s3.on === 1 && s3.depth === '门廊', `${s3.on}/${s3.depth}`)
  await page.evaluate(() => document.querySelectorAll('.ih__depth-dot')[0].click())
  await sleep(1900)
  const s4 = await state()
  check('点刻度回到入口并恢复 5 扇门', s4.on === 0 && s4.visible === 5, `${s4.on}/${s4.visible}`)
  check('回到入口后盒子仍收起（已开封，不再出现合盒盒子）', s4.boxHidden)

  // ---------- 进展厅再回来：深度必须重置 ----------
  await page.evaluate(() => document.querySelectorAll('.ih__room')[2].click())
  await sleep(1100)
  const inRoom = await state()
  check('点门进入展厅', !inRoom.house)
  await page.evaluate(() => document.querySelector('.room-nav__back')?.click())
  await sleep(1400)
  const back = await state()
  check('回大厅后深度重置为入口', back.house && back.on === 0 && back.visible === 5,
    `${back.on}/${back.visible}`)
  check('回大厅保持已开封状态', back.opened)

  // ---------- 合上盒子 → 再滚轮开封：把「必须先开盒」闭环验一遍 ----------
  await page.evaluate(() => document.querySelector('.ih__after-btn--quiet').click())
  await sleep(1700)
  const re = await state()
  check('合上盒子回到封盒首屏', re.sealed && !re.opened, `${re.sealed}/${re.opened}`)
  check('合上盒子后五扇门再次全部隐藏', re.visible === 0, String(re.visible))
  await page.screenshot({ path: `${OUT}/depth-resealed.png` })
  await page.mouse.move(720, 450)
  await page.mouse.wheel({ deltaY: 420 })
  await sleep(1800)
  const wo = await state()
  check('滚轮也能开封（参考站 scroll to fly）', wo.opened && !wo.sealed)
  check('滚轮开封后五扇门重新出现', wo.visible === 5, String(wo.visible))

  // ---------- 点击命中：门板中间才开门，上方木牌只作展示 ----------
  const hit = await page.evaluate(() => {
    const d = document.querySelectorAll('.ih__room')[0]
    const r = d.getBoundingClientRect()
    const q = d.querySelector('.ih__plaque').getBoundingClientRect()
    return {
      pe: getComputedStyle(d.querySelector('.ih__plaque')).pointerEvents,
      w: Math.round(r.width), h: Math.round(r.height),
      door: { x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2) },
      plaque: { x: Math.round(q.left + q.width / 2), y: Math.round(q.top + q.height / 2) },
    }
  })
  check('门牌木牌不可点（pointer-events:none）', hit.pe === 'none', hit.pe)
  check('命中区是门板矩形（不是一条窄木牌）', hit.w >= 60 && hit.h >= 120, `${hit.w}×${hit.h}`)
  await page.mouse.click(hit.plaque.x, hit.plaque.y)
  await sleep(800)
  check('★ 点上方木板不会开门（用户红线）',
    await page.evaluate(() => !!document.querySelector('.ih')))
  await page.mouse.click(hit.door.x, hit.door.y)
  await sleep(1200)
  const hitRoom = await page.evaluate(() => ({
    house: !!document.querySelector('.ih'),
    plate: (document.querySelector('.room-nav__plate b') || {}).textContent,
  }))
  check('★ 点门板中间开门进入对应展厅', !hitRoom.house && hitRoom.plate === '口碑星图', hitRoom.plate)
  await page.evaluate(() => document.querySelector('.room-nav__back')?.click())
  await sleep(1200)

  // ---------- 窄屏降级 ----------
  const m = await browser.newPage()
  await m.setViewport({ width: 390, height: 844, isMobile: true, deviceScaleFactor: 2 })
  const merrs = []
  m.on('pageerror', (e) => merrs.push(e.message.slice(0, 100)))
  await m.goto(BASE + '/screen', { waitUntil: 'networkidle2', timeout: 45000 })
  await sleep(1400)
  const mobSeal = await m.evaluate(() => ({
    sealed: document.querySelector('.ih')?.classList.contains('is-sealed'),
    doorsHidden: getComputedStyle(document.querySelector('.ih__doors')).display === 'none',
    box: Math.round(document.querySelector('.ih__box')?.getBoundingClientRect().width || 0),
  }))
  check('窄屏同样先合盒、门牌不出现', !!mobSeal.sealed && mobSeal.doorsHidden, JSON.stringify(mobSeal))
  check('窄屏盒子入口够大可点', mobSeal.box >= 70, String(mobSeal.box))
  await m.evaluate(() => document.querySelector('.ih__box').click())
  await sleep(1700)
  const mob = await m.evaluate(() => ({
    noGl: document.querySelector('.ih')?.className.includes('no-gl'),
    opened: document.querySelector('.ih')?.classList.contains('is-open'),
    depthHidden: getComputedStyle(document.querySelector('.ih__depth')).display === 'none',
    doors: document.querySelectorAll('.ih__room').length,
    visible: [...document.querySelectorAll('.ih__room')].filter((d) => !d.classList.contains('is-hidden')).length,
    ovf: document.documentElement.scrollWidth - innerWidth,
  }))
  check('窄屏不建 WebGL（平面降级）', !!mob.noGl)
  check('窄屏开封后五扇门出现', !!mob.opened && mob.doors === 5 && mob.visible === 5,
    `${mob.doors}/${mob.visible}`)
  check('窄屏隐藏深度刻度', mob.depthHidden)
  check('窄屏无横向溢出', mob.ovf <= 0, String(mob.ovf))

  const all = errs.concat(merrs)
  check('0 控制台错误', all.length === 0, all.slice(0, 3).join(' | '))
  console.log('\n结果：' + pass + ' 通过 / ' + fail + ' 失败')
  await browser.close()
  if (fail) process.exitCode = 1
})()
