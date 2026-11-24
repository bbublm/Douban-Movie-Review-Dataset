// ============================================================
// 影评洞察馆 · 大厅 3D 纸艺长廊（three.js）
// ------------------------------------------------------------
// 2026-11-04 二次改版：对齐 itomdev.com 的「白纸 + 墨线白描」3D 走廊 ——
//   · 近乎纯白的纸面，全部体积靠墨线勾边（EdgesGeometry / 手绘纹理），
//     不做实体棕色材质；木地板纵向长线条一路收束到消失点
//   · 尽头过曝白光出口，五扇白木门沿 V 字三层纵深排布
//   · 走廊正中央一只「电影盒子」：可开盖的手绘木箱，盒内溢出白光与胶片，
//     呼应项目名，也是「随便看看」的盲盒入口
//   · 中文门牌用 DOM 挂在门楣上（清晰、键盘可达、点击命中稳定），
//     避开旧版 preserve-3d 命中测试静默失效的老坑
//
// ------------------------------------------------------------
// 2026-11-04 三次改版：用户指出「参考站的 3D 是有层次的」。
//   之前相机只在原地小幅走近，走廊读起来仍像一张透视插画。
//   现在把滚轮改成「沿长廊飞行穿越」，并显式分出四个深度层：
//     ① 近景：沿 z 密布的垂挂胶片串、地面票根、飘散纸屑（推进时快速掠过）
//     ② 中景：五扇门 + 中央电影盒子 + 每 6 单位一道手绘拱门廊
//     ③ 远景：白化到纸里的最后一扇门、尽头过曝白光出口
//     ④ 空气层：fog 从 7 单位起白化 + 每道门廊在地面投一道亮带，
//        穿过去时地面明暗交替，"过了一层"能被看见
//   右侧 DOM 深度刻度（4 层）把层次变成看得见、点得到的导航。
// ------------------------------------------------------------
//
// ------------------------------------------------------------
// 2026-11-04 四次改版：用户「应该先打开电影盒子才能看到这些门，
//   看看参考页面 itomdev.com」。参考站首屏是一张纸，纸被撕开后访客
//   才掉进手绘走廊 —— 也就是【先有开启动作，才看得见门】。
//   现在大厅分成两幕：
//     ① 合盒：镜头贴近一只盖得严严实实的电影盒子，身后是一整张
//        白纸幕（sheet），走廊、五扇门、深度刻度全部藏在纸后；
//        封条/馆长洞察卡片不出现，屏幕上只有盒子与刊头。
//     ② 开封：掀盖 → 盒内白光漫出 → 纸幕从中间撕开（DOM 撕纸层）
//        → 镜头拉回入口，四层纵深走廊与五扇门依次显现。
//   撕纸层是 DOM，走廊可见性是 WebGL 里的 sheet 透明度，两者共用
//   同一个 0→1 的 open 进度，不会出现「纸还没撕门就露出来」。
// ------------------------------------------------------------
//
// ------------------------------------------------------------
// 2026-11-04 六次改版：用户「走廊可以长一点，门隔得远一点，走廊上
//   挂一些电影海报，应该点门的中间开门而不是点上面的木板，盒子太丑
//   没有 3D 立体效果」。
//   ① 走廊 46 → 88 单位，五扇门的三排间距 7.2/7.8 → 15.5/18 单位，
//      滚轮飞行 20 → 42 单位，雾随之拉长，白光出口保持 fog:false
//   ② 两侧从天花垂挂 14 张手绘电影海报（程序化 CanvasTexture，零网络），
//      轻微摇摆；与门的 z 错开，不挡门
//   ③ 点击命中区从「门楣木牌」下移到「门板本身」：project() 改为投影
//      门板四角，返回屏幕矩形；DOM 木牌改成纯展示（pointer-events:none）
//   ④ 合盒相机从 (0,1.75,3.4) 平视改成右前上方三点透视俯视，
//      quaternion 与开封相机 slerp 过渡；可见顶面 + 正面 + 右侧面。
//      盒盖加烫金浮雕、铜包角、正面锁扣与底座，六个面拉开明暗
// ------------------------------------------------------------
//
// 内存纪律：无后处理、无阴影贴图、纹理共享、像素比封顶 1.5，
//           unmount 遍历释放几何/材质/纹理并主动丢 WebGL 上下文。
// ============================================================
import * as THREE from 'three'

/** 五扇门：两近两中一远，横向收束成 V 字；三排间隔 15.5 / 18 单位（用户要门隔得远） */
export const DOOR_POS = [
  { x: -3.15, z: -8.5 },
  { x: 3.15, z: -8.5 },
  { x: -2.15, z: -24 },
  { x: 2.15, z: -24 },
  { x: 0, z: -42 },
]
/** 中央电影盒子的位置：开盒后退回走廊里的位置 */
export const BOX_POS = { x: 0, y: 0, z: -5.0 }
/** 合盒阶段：盒子被推到相机眼前的近景位置（纸幕之前） */
const BOX_SEALED = { x: 0, y: 0, z: -1.15 }
/** 合盒相机：右前上方三点透视，俯看盒盖 + 正面 + 右侧面 */
const CAM_SEALED = { x: 1.7, y: 3.05, z: 3.15 }
/** 纸幕：挡住整条走廊的一整张白纸，开封时从中撕开 */
const SHEET_Z = -2.35

const HALF_W = 4.6
const HEIGHT = 4.3
const Z_NEAR = 14
const Z_FAR = -74
const PAPER = '#FBF7EE'
const INK = 0x4A3C2C
/** 滚轮从入口推进到走廊深处的总距离（相机 z: 6 → -36） */
const WALK_DEPTH = 42
/** 深度刻度的层数，与 InsightHouse.vue 的 DEPTH_LABELS 对齐 */
export const DEPTH_LAYERS = 4

/** 垂挂海报的片单（手绘复古海报，不用外部图片，避免容器出网 502） */
const POSTERS = [
  { zh: '海上钢琴师', en: 'THE LEGEND OF 1900', year: '1998', tint: '#B9603A', motif: 0 },
  { zh: '千与千寻', en: 'SPIRITED AWAY', year: '2001', tint: '#2F6E77', motif: 1 },
  { zh: '花样年华', en: 'IN THE MOOD FOR LOVE', year: '2000', tint: '#9B3B3B', motif: 2 },
  { zh: '教父', en: 'THE GODFATHER', year: '1972', tint: '#4A3C2C', motif: 3 },
  { zh: '星际穿越', en: 'INTERSTELLAR', year: '2014', tint: '#3C4C70', motif: 4 },
  { zh: '盗梦空间', en: 'INCEPTION', year: '2010', tint: '#6A5A3E', motif: 5 },
]

/** 走廊挂位数量（与 POSTER_Z 对齐）：真实海报就挂在这 14 个位置上，常驻显示 */
export const POSTER_SLOTS = 14

/** 真实影片 → 挂画纸卡文案（片单来自 /insights/hall-posters 的 ES 聚合结果） */
function toPosterCard(m, i) {
  const palette = ['#B9603A', '#2F6E77', '#9B3B3B', '#4A3C2C',
    '#3C4C70', '#6A5A3E', '#8B5E1C', '#0F766E']
  let h = 0
  const s = String(m?.title || '')
  for (let k = 0; k < s.length; k++) h = (h * 31 + s.charCodeAt(k)) >>> 0
  return {
    zh: (m?.title || '—').slice(0, 12),
    en: String(m?.title_en || m?.genre || 'MOVIE BOX').slice(0, 30).toUpperCase(),
    year: String(m?.year || ''),
    tint: palette[h % palette.length],
    motif: i % 6,
    seed: i,
  }
}

/* ---------- 程序化手绘纹理（零网络请求） ---------- */
const clamp01 = (v) => Math.min(1, Math.max(0, v))
const smooth = (v) => { const x = clamp01(v); return x * x * (3 - 2 * x) }
const lerp = (a, b, t) => a + (b - a) * t
function rng(seed) {
  let s = seed >>> 0
  return () => (s = (s * 1664525 + 1013904223) >>> 0) / 4294967296
}
function newCanvas(size = 512) {
  const c = document.createElement('canvas')
  c.width = c.height = size
  return [c, c.getContext('2d')]
}
function asTexture(c) {
  const t = new THREE.CanvasTexture(c)
  t.colorSpace = THREE.SRGBColorSpace
  t.anisotropy = 4
  return t
}

/** 纸面：极淡的斑驳 + 细噪点，保持「白纸」而不是塑料 */
function paperTexture(base, seed, strength = 1) {
  const [c, g] = newCanvas(512)
  const r = rng(seed)
  g.fillStyle = base
  g.fillRect(0, 0, 512, 512)
  for (let i = 0; i < 34; i++) {
    const x = r() * 512, y = r() * 512, rad = 46 + r() * 120
    const grad = g.createRadialGradient(x, y, 0, x, y, rad)
    grad.addColorStop(0, r() > 0.5 ? 'rgba(255,255,255,.14)' : `rgba(120,100,72,${0.055 * strength})`)
    grad.addColorStop(1, 'rgba(0,0,0,0)')
    g.fillStyle = grad
    g.fillRect(x - rad, y - rad, rad * 2, rad * 2)
  }
  for (let i = 0; i < 2600; i++) {
    g.fillStyle = `rgba(90,74,52,${0.035 * strength})`
    g.fillRect(r() * 512, r() * 512, 1.2, 1.2)
  }
  return asTexture(c)
}

/** 木地板：纵向长线 + 稀疏横向接缝（itomdev 图 2/3 的标志性透视） */
function floorTexture() {
  const [c, g] = newCanvas(512)
  const r = rng(97)
  g.fillStyle = '#FBF8F0'
  g.fillRect(0, 0, 512, 512)
  // 木板长线：不等间距、带轻微抖动，像手绘而不是 CAD
  let x = 0
  while (x < 512) {
    const step = 22 + r() * 20
    g.strokeStyle = `rgba(74,60,44,${0.20 + r() * 0.22})`
    g.lineWidth = 0.8 + r() * 1.1
    g.beginPath()
    g.moveTo(x, 0)
    for (let y = 0; y <= 512; y += 64) g.lineTo(x + (r() - 0.5) * 3.4, y)
    g.stroke()
    // 木纹细丝
    if (r() > 0.42) {
      g.strokeStyle = 'rgba(74,60,44,.07)'
      g.lineWidth = 0.6
      g.beginPath()
      g.moveTo(x + step * 0.55, 0)
      g.lineTo(x + step * 0.55 + (r() - 0.5) * 6, 512)
      g.stroke()
    }
    x += step
  }
  // 横向板缝：错开，不贯通
  for (let row = 0; row < 5; row++) {
    const y = 40 + row * 106 + r() * 18
    let cx = r() * 40
    while (cx < 512) {
      const len = 24 + r() * 62
      g.strokeStyle = 'rgba(74,60,44,.30)'
      g.lineWidth = 1.2
      g.beginPath()
      g.moveTo(cx, y + (r() - 0.5) * 2)
      g.lineTo(cx + len, y + (r() - 0.5) * 2)
      g.stroke()
      cx += len + 18 + r() * 30
    }
  }
  const t = asTexture(c)
  t.wrapS = t.wrapT = THREE.RepeatWrapping
  // 走廊从 46 拉长到 88 单位，木地板长线要同步加密才不会拉伸成粗带
  t.repeat.set(1, 17)
  return t
}

/** 手绘砖墙：错缝横线 + 短竖缝，墨色很淡，只做背景肌理 */
function brickTexture() {
  const [c, g] = newCanvas(512)
  const r = rng(311)
  g.fillStyle = '#FCF9F2'
  g.fillRect(0, 0, 512, 512)
  const rowH = 52
  for (let row = 0; row < 11; row++) {
    const y = row * rowH
    g.strokeStyle = 'rgba(74,60,44,.19)'
    g.lineWidth = 1.1
    g.beginPath()
    g.moveTo(0, y + (r() - 0.5) * 2)
    for (let x = 0; x <= 512; x += 64) g.lineTo(x, y + (r() - 0.5) * 3)
    g.stroke()
    const offset = (row % 2) * 48
    for (let bx = offset; bx < 512; bx += 96) {
      const jx = bx + (r() - 0.5) * 5
      g.strokeStyle = 'rgba(74,60,44,.16)'
      g.beginPath()
      g.moveTo(jx, y + 2)
      g.lineTo(jx + (r() - 0.5) * 3, y + rowH - 2)
      g.stroke()
    }
  }
  const t = asTexture(c)
  t.wrapS = t.wrapT = THREE.RepeatWrapping
  t.repeat.set(8, 1)
  return t
}

/** 白木门：内框线 + 一枚手绘贴纸（每间展厅一个色） */
function doorTexture(tint, no) {
  const [c, g] = newCanvas(512)
  const r = rng(71 + no * 13)
  g.fillStyle = '#FCF9F1'
  g.fillRect(0, 0, 512, 512)
  g.strokeStyle = 'rgba(74,60,44,.52)'
  g.lineWidth = 3
  g.strokeRect(26, 26, 460, 460)
  g.lineWidth = 1.5
  g.strokeStyle = 'rgba(74,60,44,.30)'
  g.strokeRect(38, 38, 436, 436)
  g.strokeRect(64, 70, 384, 170)
  g.strokeRect(64, 264, 384, 178)
  // 贴纸：手绘圆角矩形 + 展厅色，像 itomdev 门上贴的徽章
  for (let k = 0; k < 3; k++) {
    const px = 96 + r() * 250, py = 96 + r() * 300
    const w = 54 + r() * 42, h = 40 + r() * 26
    g.save()
    g.translate(px, py)
    g.rotate((r() - 0.5) * 0.5)
    g.fillStyle = k === 1 ? tint : 'rgba(255,252,244,.94)'
    g.strokeStyle = 'rgba(74,60,44,.55)'
    g.lineWidth = 2
    g.beginPath()
    g.roundRect(-w / 2, -h / 2, w, h, 7)
    g.fill()
    g.stroke()
    g.strokeStyle = 'rgba(74,60,44,.34)'
    g.lineWidth = 1.2
    g.beginPath()
    g.moveTo(-w / 2 + 7, 0)
    g.lineTo(w / 2 - 7, 0)
    g.stroke()
    g.restore()
  }
  return asTexture(c)
}

/** 胶片格：黑边 + 齿孔 + 中间一格暖色画面 */
function filmTexture(tint) {
  const [c, g] = newCanvas(256)
  g.fillStyle = '#FCF9F1'
  g.fillRect(0, 0, 256, 256)
  g.strokeStyle = 'rgba(74,60,44,.7)'
  g.lineWidth = 5
  g.strokeRect(8, 8, 240, 240)
  g.fillStyle = 'rgba(74,60,44,.62)'
  for (let y = 20; y < 240; y += 32) {
    g.fillRect(14, y, 18, 16)
    g.fillRect(224, y, 18, 16)
  }
  const grad = g.createLinearGradient(40, 40, 216, 216)
  grad.addColorStop(0, '#FFF3D6')
  grad.addColorStop(0.55, tint)
  grad.addColorStop(1, '#F6E7C9')
  g.fillStyle = grad
  g.fillRect(40, 34, 176, 188)
  // 褪色处理：把高饱和的展厅色压成旧照片淡彩，和暖白纸 / 墨线白描同一调子
  g.fillStyle = 'rgba(255, 251, 240, .4)'
  g.fillRect(40, 34, 176, 188)
  g.strokeStyle = 'rgba(74,60,44,.55)'
  g.lineWidth = 2
  g.strokeRect(40, 34, 176, 188)
  return asTexture(c)
}

/** 盒身正面标签：不做整面广告牌，留白边 + 细金线 + 胶片盘烫金章 */
function boxFaceTexture() {
  const [c, g] = newCanvas(512)
  const r = rng(555)
  g.fillStyle = '#FBF4E4'
  g.fillRect(0, 0, 512, 512)
  for (let i = 0; i < 70; i++) {
    g.strokeStyle = `rgba(120,88,50,${0.025 + r() * 0.05})`
    g.lineWidth = 0.8 + r()
    const y = r() * 512
    g.beginPath()
    g.moveTo(0, y)
    g.bezierCurveTo(160, y + (r() - 0.5) * 12, 340, y + (r() - 0.5) * 12, 512, y)
    g.stroke()
  }
  // 细金线双框：比旧版粗铆钉牌匾克制得多
  g.strokeStyle = 'rgba(139,94,28,.72)'
  g.lineWidth = 2.2
  g.strokeRect(22, 22, 468, 468)
  g.strokeStyle = 'rgba(139,94,28,.28)'
  g.lineWidth = 1.1
  g.strokeRect(32, 32, 448, 448)
  // 顶部一条胶片齿孔带，把「电影盒子」说清楚
  g.fillStyle = 'rgba(74,60,44,.72)'
  for (let x = 54; x < 460; x += 30) g.fillRect(x, 52, 17, 12)
  g.strokeStyle = 'rgba(74,60,44,.34)'
  g.lineWidth = 1.4
  g.strokeRect(48, 48, 416, 20)
  // 中央胶片盘烫金圆章
  g.save()
  g.translate(256, 168)
  g.strokeStyle = '#A67C2E'
  g.lineWidth = 3.2
  g.beginPath(); g.arc(0, 0, 58, 0, Math.PI * 2); g.stroke()
  g.lineWidth = 1.2
  g.beginPath(); g.arc(0, 0, 48, 0, Math.PI * 2); g.stroke()
  g.fillStyle = '#A67C2E'
  for (let k = 0; k < 3; k++) {
    const a = (k / 3) * Math.PI * 2 - Math.PI / 2
    g.beginPath(); g.arc(Math.cos(a) * 28, Math.sin(a) * 28, 10, 0, Math.PI * 2); g.fill()
  }
  g.beginPath(); g.arc(0, 0, 9, 0, Math.PI * 2); g.fill()
  g.restore()
  g.textAlign = 'center'
  g.fillStyle = '#3A2E20'
  g.font = 'bold 72px "Kaiti SC", KaiTi, Georgia, serif'
  g.fillText('电影盒子', 256, 308)
  g.strokeStyle = 'rgba(166,124,46,.8)'
  g.lineWidth = 1.8
  g.beginPath(); g.moveTo(146, 330); g.lineTo(366, 330); g.stroke()
  g.fillStyle = '#8B5E1C'
  g.font = 'bold 24px Georgia, serif'
  g.fillText('M O V I E   B O X', 256, 372)
  g.font = '20px "Kaiti SC", KaiTi, Georgia, serif'
  g.fillStyle = 'rgba(74,60,44,.72)'
  g.fillText('五 间 展 厅 · 五 万 条 影 评', 256, 414)
  // 底部五点 = 五间展厅
  g.fillStyle = '#A67C2E'
  for (let k = 0; k < 5; k++) {
    g.beginPath(); g.arc(216 + k * 20, 448, 3.6, 0, Math.PI * 2); g.fill()
  }
  return asTexture(c)
}

/** 盒盖顶面：俯视时首先看到的就是它，做一张烫金浮雕纸标 */
function lidTexture() {
  const [c, g] = newCanvas(512)
  g.fillStyle = '#EAD5AE'
  g.fillRect(0, 0, 512, 512)
  g.strokeStyle = 'rgba(139,94,28,.62)'
  g.lineWidth = 3
  g.strokeRect(18, 30, 476, 452)
  g.strokeStyle = 'rgba(139,94,28,.3)'
  g.lineWidth = 1.2
  g.strokeRect(30, 42, 452, 428)
  g.save()
  g.translate(256, 256)
  for (let k = 0; k < 3; k++) {
    g.strokeStyle = `rgba(166,124,46,${0.6 - k * 0.14})`
    g.lineWidth = 2.4
    g.beginPath(); g.arc(0, 0, 92 + k * 22, 0, Math.PI * 2); g.stroke()
  }
  g.fillStyle = 'rgba(139,94,28,.1)'
  g.beginPath(); g.arc(0, 0, 84, 0, Math.PI * 2); g.fill()
  g.restore()
  g.textAlign = 'center'
  g.fillStyle = '#6B4A22'
  g.font = 'bold 62px "Kaiti SC", KaiTi, Georgia, serif'
  g.fillText('电影盒子', 256, 244)
  g.font = 'bold 19px Georgia, serif'
  g.fillStyle = '#8B5E1C'
  g.fillText('THE INSIGHT ARCHIVE', 256, 288)
  g.font = '17px "Kaiti SC", KaiTi, Georgia, serif'
  g.fillStyle = 'rgba(74,60,44,.66)'
  g.fillText('掀 开 · 走 进 五 间 展 厅', 256, 330)
  return asTexture(c)
}

/** 盒身侧面：竖向木纹 + 胶片孔，让右侧面在三点透视里读得出体积 */
function boxSideTexture() {
  const [c, g] = newCanvas(256)
  const r = rng(808)
  g.fillStyle = '#DCC29B'
  g.fillRect(0, 0, 256, 256)
  for (let i = 0; i < 46; i++) {
    g.strokeStyle = `rgba(120,88,50,${0.05 + r() * 0.1})`
    g.lineWidth = 0.7 + r() * 1.2
    const x = r() * 256
    g.beginPath()
    g.moveTo(x, 0)
    g.bezierCurveTo(x + (r() - 0.5) * 9, 90, x + (r() - 0.5) * 9, 170, x, 256)
    g.stroke()
  }
  g.fillStyle = 'rgba(74,60,44,.5)'
  for (let y = 24; y < 240; y += 34) {
    g.fillRect(12, y, 15, 12)
    g.fillRect(229, y, 15, 12)
  }
  g.strokeStyle = 'rgba(74,60,44,.4)'
  g.lineWidth = 2
  g.strokeRect(8, 8, 240, 240)
  return asTexture(c)
}

/** 垂挂电影海报：程序化手绘复古海报，零网络请求、与暖白纸风格统一 */
function posterTexture(p, i) {
  const [c, g] = newCanvas(512)
  const r = rng(1200 + i * 37)
  g.fillStyle = '#FBF6E9'
  g.fillRect(0, 0, 512, 512)
  // 画面主色块：六种构图，避免 14 张海报长得一样
  const top = p.tint
  g.fillStyle = top
  g.globalAlpha = 0.88
  g.fillRect(34, 34, 444, 300)
  g.globalAlpha = 1
  g.save()
  g.beginPath(); g.rect(34, 34, 444, 300); g.clip()
  g.fillStyle = 'rgba(255,250,235,.16)'
  if (p.motif === 0) {          // 海 + 夕阳 + 船
    g.beginPath(); g.arc(256, 196, 96, 0, Math.PI * 2); g.fill()
    g.fillStyle = 'rgba(59,46,32,.55)'
    g.fillRect(34, 250, 444, 84)
    g.beginPath(); g.moveTo(190, 250); g.lineTo(322, 250); g.lineTo(296, 286); g.lineTo(216, 286); g.fill()
    g.fillRect(252, 176, 4, 74)
  } else if (p.motif === 1) {   // 神隐：层层拱门
    for (let k = 0; k < 4; k++) {
      g.strokeStyle = `rgba(255,246,222,${0.24 + k * 0.12})`
      g.lineWidth = 16
      g.beginPath(); g.arc(256, 300, 70 + k * 54, Math.PI, 0); g.stroke()
    }
    g.fillStyle = 'rgba(48,36,24,.6)'
    g.beginPath(); g.arc(256, 250, 26, 0, Math.PI * 2); g.fill()
  } else if (p.motif === 2) {   // 花样年华：旗袍曲线
    g.strokeStyle = 'rgba(255,240,210,.5)'
    for (let k = 0; k < 7; k++) {
      g.lineWidth = 3 + k
      g.beginPath()
      g.moveTo(80 + k * 44, 34)
      g.bezierCurveTo(140 + k * 30, 150, 200 + k * 20, 220, 130 + k * 46, 334)
      g.stroke()
    }
  } else if (p.motif === 3) {   // 教父：黑色剪影 + 提线
    g.fillStyle = 'rgba(40,30,20,.62)'
    g.beginPath(); g.arc(256, 172, 62, 0, Math.PI * 2); g.fill()
    g.beginPath(); g.moveTo(150, 334); g.lineTo(190, 236); g.lineTo(322, 236); g.lineTo(362, 334); g.fill()
    g.strokeStyle = 'rgba(255,244,214,.5)'
    g.lineWidth = 2
    for (let k = 0; k < 5; k++) { g.beginPath(); g.moveTo(210 + k * 22, 34); g.lineTo(232 + k * 10, 140); g.stroke() }
  } else if (p.motif === 4) {   // 星际：星环 + 行星
    g.fillStyle = 'rgba(255,250,232,.24)'
    g.beginPath(); g.arc(324, 174, 82, 0, Math.PI * 2); g.fill()
    g.strokeStyle = 'rgba(255,250,232,.62)'
    g.lineWidth = 9
    g.beginPath(); g.ellipse(324, 174, 150, 40, -0.35, 0, Math.PI * 2); g.stroke()
    g.fillStyle = 'rgba(255,252,240,.9)'
    for (let k = 0; k < 34; k++) { g.fillRect(r() * 478, r() * 300, 2, 2) }
  } else {                      // 盗梦：折叠城市
    g.strokeStyle = 'rgba(255,246,220,.55)'
    g.lineWidth = 3
    for (let k = 0; k < 9; k++) {
      const x = 60 + k * 50
      g.beginPath(); g.moveTo(x, 334); g.lineTo(x, 120 + (k % 4) * 34); g.lineTo(x + 46, 120 + (k % 4) * 34); g.stroke()
    }
    g.strokeStyle = 'rgba(255,246,220,.3)'
    g.beginPath(); g.moveTo(34, 250); g.lineTo(478, 190); g.stroke()
  }
  // 旧照片褪色感
  g.fillStyle = 'rgba(255,251,240,.24)'
  g.fillRect(34, 34, 444, 300)
  g.restore()
  // 纸框、题头、片名、年份
  g.strokeStyle = 'rgba(74,60,44,.78)'
  g.lineWidth = 3.5
  g.strokeRect(26, 26, 460, 460)
  g.lineWidth = 1.2
  g.strokeRect(38, 38, 436, 436)
  g.textAlign = 'center'
  g.fillStyle = '#8B5E1C'
  g.font = 'bold 13px Georgia, serif'
  g.fillText('MOVIE BOX  ·  ARCHIVE  ·  ' + p.year, 256, 364)
  g.fillStyle = '#3A2E20'
  let fs = 43
  g.font = `bold ${fs}px "Kaiti SC", KaiTi, Georgia, serif`
  while (g.measureText(p.zh).width > 380 && fs > 24) {
    fs -= 2
    g.font = `bold ${fs}px "Kaiti SC", KaiTi, Georgia, serif`
  }
  g.fillText(p.zh, 256, 416)
  g.strokeStyle = 'rgba(166,124,46,.8)'
  g.lineWidth = 1.6
  g.beginPath(); g.moveTo(146, 430); g.lineTo(366, 430); g.stroke()
  g.fillStyle = '#7A6242'
  g.font = 'bold 12px Georgia, serif'
  g.fillText(p.en.slice(0, 30), 256, 452)
  g.fillStyle = '#A67C2E'
  g.font = '15px Georgia, serif'
  g.fillText('★ ★ ★ ★ ★', 256, 476)
  // 四角铜钉
  g.fillStyle = 'rgba(139,94,28,.8)'
  for (const [x, y] of [[44, 44], [468, 44], [44, 468], [468, 468]]) {
    g.beginPath(); g.arc(x, y, 4, 0, Math.PI * 2); g.fill()
  }
  return asTexture(c)
}

/**
 * 走廊静态挂画：竖版纸卡 288×420，比例与 1.32×1.92 的 Plane 一致，不会被拉伸。
 * img 为真实海报时直接贴进画面；为 null 时先画手绘占位，出网失败也不留空白框。
 * ★ 图片异步到达后在「同一块 canvas」上重绘，只置 needsUpdate：
 *   14 张挂画始终 14 张纹理，不额外申请材质，峰值显存约 6.8MB。
 */
function paintHangingPoster(c, g, card, img) {
  const W = c.width, H = c.height
  const pad = W * 0.05
  const x = pad, y = pad, iw = W - pad * 2, ih = H * 0.79 - pad
  g.clearRect(0, 0, W, H)
  g.fillStyle = '#FBF6E9'
  g.fillRect(0, 0, W, H)
  if (img) {
    const s = Math.max(iw / img.width, ih / img.height)
    const dw = img.width * s, dh = img.height * s
    g.save()
    g.beginPath(); g.rect(x, y, iw, ih); g.clip()
    g.drawImage(img, x + (iw - dw) / 2, y + (ih - dh) / 2, dw, dh)
    // 轻微褪色，让彩色海报融进暖白纸的走廊
    g.fillStyle = 'rgba(255,247,228,.09)'
    g.fillRect(x, y, iw, ih)
    g.restore()
  } else {
    const r = rng(1200 + card.seed * 37)
    g.fillStyle = card.tint
    g.globalAlpha = 0.86
    g.fillRect(x, y, iw, ih)
    g.globalAlpha = 1
    g.fillStyle = 'rgba(255,250,235,.2)'
    g.beginPath(); g.arc(W * 0.62, y + ih * 0.38, W * 0.22, 0, Math.PI * 2); g.fill()
    g.fillStyle = 'rgba(59,46,32,.5)'
    g.fillRect(x, y + ih * 0.72, iw, ih * 0.28)
    g.fillStyle = 'rgba(255,250,235,.65)'
    for (let k = 0; k < 22; k++) g.fillRect(x + r() * iw, y + r() * ih * 0.7, 1.4, 1.4)
  }
  // 手绘纸框 + 四角铜钉
  g.strokeStyle = 'rgba(74,60,44,.8)'
  g.lineWidth = 2.2
  g.strokeRect(pad * 0.5, pad * 0.5, W - pad, H - pad)
  g.strokeStyle = 'rgba(74,60,44,.4)'
  g.lineWidth = 1
  g.strokeRect(x, y, iw, ih)
  g.fillStyle = 'rgba(139,94,28,.85)'
  for (const [px, py] of [[pad * 0.85, pad * 0.85], [W - pad * 0.85, pad * 0.85],
    [pad * 0.85, H - pad * 0.85], [W - pad * 0.85, H - pad * 0.85]]) {
    g.beginPath(); g.arc(px, py, 2.2, 0, Math.PI * 2); g.fill()
  }
  // 底部档案标签：片名 / 年份 / 原文名，挂的不是装饰画而是真实影片
  g.textAlign = 'center'
  g.fillStyle = '#8B5E1C'
  g.font = `bold ${Math.round(W * 0.036)}px Georgia, serif`
  g.fillText('MOVIE BOX · ARCHIVE · ' + (card.year || '—'), W / 2, H * 0.845, W * 0.9)
  g.fillStyle = '#3A2E20'
  let fs = Math.round(W * 0.085)
  g.font = `bold ${fs}px "Kaiti SC", KaiTi, Georgia, serif`
  while (g.measureText(card.zh).width > W * 0.86 && fs > 12) {
    fs -= 1
    g.font = `bold ${fs}px "Kaiti SC", KaiTi, Georgia, serif`
  }
  g.fillText(card.zh, W / 2, H * 0.912, W * 0.86)
  g.strokeStyle = 'rgba(166,124,46,.8)'
  g.lineWidth = 1.1
  g.beginPath(); g.moveTo(W * 0.3, H * 0.928); g.lineTo(W * 0.7, H * 0.928); g.stroke()
  g.fillStyle = '#7A6242'
  g.font = `bold ${Math.round(W * 0.033)}px Georgia, serif`
  g.fillText(card.en.slice(0, 34), W / 2, H * 0.962, W * 0.86)
}

/** 柔光贴图：门内暖光 / 地面光斑 / 尽头过曝白光 */
function glowTexture() {
  const [c, g] = newCanvas(256)
  const grad = g.createRadialGradient(128, 128, 4, 128, 128, 128)
  grad.addColorStop(0, 'rgba(255,255,255,1)')
  grad.addColorStop(0.3, 'rgba(255,250,232,.98)')
  grad.addColorStop(0.62, 'rgba(255,228,176,.55)')
  grad.addColorStop(1, 'rgba(190,140,70,0)')
  g.fillStyle = grad
  g.fillRect(0, 0, 256, 256)
  return asTexture(c)
}

/** 天花：只留极淡的手绘折痕，不做斑驳（斑驳贴到天花会被拉成脏灰带） */
function ceilingTexture() {
  const [c, g] = newCanvas(512)
  const r = rng(88)
  g.fillStyle = '#FFFCF5'
  g.fillRect(0, 0, 512, 512)
  for (let i = 0; i < 7; i++) {
    const y = 40 + i * 70 + r() * 20
    g.strokeStyle = 'rgba(90,74,52,.055)'
    g.lineWidth = 1 + r() * 0.8
    g.beginPath()
    g.moveTo(0, y)
    for (let x = 0; x <= 512; x += 64) g.lineTo(x, y + (r() - 0.5) * 8)
    g.stroke()
  }
  const t = asTexture(c)
  t.wrapS = t.wrapT = THREE.RepeatWrapping
  t.repeat.set(2, 14)
  return t
}

/** 地面落影：让中央盒子"坐"在地板上，而不是浮着 */
function shadowTexture() {
  const [c, g] = newCanvas(256)
  const grad = g.createRadialGradient(128, 128, 8, 128, 128, 128)
  grad.addColorStop(0, 'rgba(74,60,44,.38)')
  grad.addColorStop(0.55, 'rgba(74,60,44,.16)')
  grad.addColorStop(1, 'rgba(74,60,44,0)')
  g.fillStyle = grad
  g.fillRect(0, 0, 256, 256)
  return asTexture(c)
}

/** 电影票根：贴地的近景小纸片，推进时从脚下快速掠过 */
function ticketTexture() {
  const [c, g] = newCanvas(256)
  g.fillStyle = '#FFF9EA'
  g.fillRect(0, 0, 256, 256)
  g.strokeStyle = 'rgba(74,60,44,.72)'
  g.lineWidth = 5
  g.strokeRect(10, 10, 236, 236)
  g.setLineDash([9, 8])
  g.lineWidth = 2.5
  g.beginPath(); g.moveTo(178, 14); g.lineTo(178, 242); g.stroke()
  g.setLineDash([])
  g.fillStyle = '#A67C2E'
  g.font = 'bold 34px Georgia, serif'
  g.textAlign = 'center'
  g.fillText('★', 214, 108)
  g.save()
  g.translate(214, 150)
  g.rotate(-Math.PI / 2)
  g.fillStyle = 'rgba(74,60,44,.65)'
  g.font = 'bold 19px Georgia, serif'
  g.fillText('ADMIT ONE', 0, 0)
  g.restore()
  g.fillStyle = 'rgba(74,60,44,.5)'
  g.font = 'bold 22px Georgia, serif'
  g.fillText('MOVIE BOX', 92, 76)
  for (let i = 0; i < 5; i++) {
    g.fillRect(30, 112 + i * 24, 60 + (i % 3) * 34, 3)
  }
  return asTexture(c)
}

/** 给网格加墨线描边：白描风格的核心 */
function outlined(geometry, faceMat, opacity = 0.72) {
  const group = new THREE.Group()
  group.add(new THREE.Mesh(geometry, faceMat))
  const edges = new THREE.LineSegments(
    new THREE.EdgesGeometry(geometry, 18),
    new THREE.LineBasicMaterial({ color: INK, transparent: true, opacity }),
  )
  group.add(edges)
  return group
}

/* ---------- 场景 ---------- */
export function createHouse3D(canvasEl, tints = [], movies = []) {
  const renderer = new THREE.WebGLRenderer({
    canvas: canvasEl, antialias: true, alpha: false, powerPreference: 'high-performance',
  })
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 1.5))
  renderer.outputColorSpace = THREE.SRGBColorSpace
  renderer.setClearColor(new THREE.Color(PAPER), 1)
  // 供回归脚本读取场景尺度，不参与渲染
  canvasEl.dataset.corridor = String(Z_NEAR - Z_FAR)
  canvasEl.dataset.doorGap = String(DOOR_POS[2].z - DOOR_POS[0].z)

  const scene = new THREE.Scene()
  scene.background = new THREE.Color(PAPER)
  // 空气透视随走廊一起拉长：远门自然「退进纸里」，但不会出现中段全白
  scene.fog = new THREE.Fog(PAPER, 12, 96)

  const camera = new THREE.PerspectiveCamera(58, 1.6, 0.1, 100)
  camera.rotation.order = 'YXZ'

  // 白描用 MeshBasic，不吃光照；只有铜件用 Standard 留一点高光
  scene.add(new THREE.AmbientLight(0xFFFFFF, 1.5))
  const key = new THREE.DirectionalLight(0xFFF0D2, 0.7)
  key.position.set(4, 8, 7)
  scene.add(key)

  const floorTex = floorTexture()
  const brickTex = brickTexture()
  const ceilTex = ceilingTexture()
  const glowTex = glowTexture()
  const boxFace = boxFaceTexture()
  const lidFace = lidTexture()
  const boxSide = boxSideTexture()
  const shadowTex = shadowTexture()
  const ticketTex = ticketTexture()
  // 胶片纹理共享：近景垂挂串 + 盒里飘出的胶片共用 5 张，不按格重复生成
  const filmTextures = Array.from({ length: 5 }, (_, i) => filmTexture(tints[i] || '#A67C2E'))
  // 手绘电影海报：初始 6 张纹理轮播，14 个挂位复用，不为每张单独开 canvas。
  // 真实片单到达后由 setPosters() 换成「一片一纹理」（片名不同）；
  // 旧材质 / 新纹理都登记给 dispose() 统一释放，不做重复常驻。
  const posterTextures = POSTERS.map((p, i) => posterTexture(p, i))
  /** 真实海报挂画自有的纹理/材质：片单刷新时先释放，避免叠加占显存 */
  const posterOwned = []
  /** 在途的 <img>：组件卸载或片单刷新时摘掉回调，防止旧图盖新图 */
  const posterLoads = []
  let disposed = false

  // ---- 合盒阶段的「一整张纸」 ----
  // 参考站首屏就是一张纸：撕开之前，访客看不到走廊里的任何门。
  // 这张纸幕放在盒子背后、五扇门之前，透明渐隐 = 纸被撕开、走廊显现。
  // depthWrite:false + renderOrder 拉到最后，确保门内的暖光不会透纸漏出来。
  const sheetTex = paperTexture('#FBF7EE', 909, 0.6)
  const sheet = new THREE.Mesh(
    new THREE.PlaneGeometry(26, 14),
    new THREE.MeshBasicMaterial({
      map: sheetTex, fog: false, transparent: true, depthWrite: false,
      // ★ 不做深度测试：纸幕最后渲染时无条件盖住走廊近端（地板线 / 墙线），
      //   合盒首屏才真的是「一张纸上只有一只盒子」，而不是半截走廊。
      depthTest: false, side: THREE.DoubleSide,
    }),
  )
  sheet.position.set(0, 1.0, SHEET_Z)
  sheet.renderOrder = 20
  scene.add(sheet)

  const white = new THREE.MeshBasicMaterial({ color: 0xFFFDF7, side: THREE.DoubleSide })
  const floorMat = new THREE.MeshBasicMaterial({ map: floorTex, side: THREE.DoubleSide })
  const wallMat = new THREE.MeshBasicMaterial({ map: brickTex, side: THREE.DoubleSide })
  const ceilMat = new THREE.MeshBasicMaterial({ map: ceilTex, side: THREE.DoubleSide })
  const woodLine = new THREE.MeshStandardMaterial({ color: 0xC9A875, roughness: 0.8, metalness: 0.05 })
  const brass = new THREE.MeshStandardMaterial({ color: 0xA67C2E, roughness: 0.42, metalness: 0.4 })
  // 白描场景没有强光，Standard 铜件会发暗发黑；包角/锁扣用亮金 Basic 更精致
  const brassLight = new THREE.MeshBasicMaterial({ color: 0xC99A4B })

  const LEN = Z_NEAR - Z_FAR
  const MID = (Z_NEAR + Z_FAR) / 2

  // ---- 地板 / 天花 / 砖墙 ----
  const floor = new THREE.Mesh(new THREE.PlaneGeometry(HALF_W * 2, LEN), floorMat)
  floor.rotation.x = -Math.PI / 2
  floor.position.set(0, 0, MID)
  scene.add(floor)

  const ceiling = new THREE.Mesh(new THREE.PlaneGeometry(HALF_W * 2, LEN), ceilMat)
  ceiling.rotation.x = Math.PI / 2
  ceiling.position.set(0, HEIGHT, MID)
  scene.add(ceiling)

  for (const side of [-1, 1]) {
    const wall = new THREE.Mesh(new THREE.PlaneGeometry(LEN, HEIGHT), wallMat)
    wall.rotation.y = side < 0 ? Math.PI / 2 : -Math.PI / 2
    wall.position.set(side * HALF_W, HEIGHT / 2, MID)
    scene.add(wall)
    // 墙脚墨线 + 檐线：两条细线把透视收束到消失点（太粗会横切刊头）
    for (const y of [0.14, 3.36]) {
      const upper = y > 1
      const rail = new THREE.Mesh(
        new THREE.BoxGeometry(0.04, upper ? 0.028 : 0.05, LEN),
        upper ? woodLine : brass,
      )
      rail.position.set(side * (HALF_W - 0.04), y, MID)
      scene.add(rail)
    }
  }

  // ---- 门廊节点：每 6 单位一道，构成「一层一层往里」的节奏 ----
  // 立柱 + 手绘拱弧 + 地面亮带 + 两侧垂挂胶片串。相机推进时依次穿过，
  // 地面明暗交替、近景胶片从画面边缘掠过 —— 层次靠深度，不靠配色。
  const archMat = new THREE.LineBasicMaterial({ color: INK, transparent: true, opacity: 0.34 })
  const bandMat = new THREE.MeshBasicMaterial({
    map: glowTex, transparent: true, opacity: 0.17, depthWrite: false,
  })
  const hangings = []

  for (let z = 4; z > -70; z -= 8) {
    // 一道浅拱弧：细墨线抛物线，不做横贯粗梁（走近时才不会横切刊头）
    const arch = []
    for (let k = 0; k <= 24; k++) {
      const x = -HALF_W + (k / 24) * HALF_W * 2
      arch.push(new THREE.Vector3(x, 3.28 + 0.62 * (1 - (x / HALF_W) ** 2), z))
    }
    scene.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(arch), archMat))

    for (const side of [-1, 1]) {
      const pil = outlined(new THREE.BoxGeometry(0.16, HEIGHT, 0.3), white, 0.6)
      pil.position.set(side * (HALF_W - 0.08), HEIGHT / 2, z)
      scene.add(pil)
      const sconce = new THREE.Mesh(
        new THREE.PlaneGeometry(1.1, 1.5),
        new THREE.MeshBasicMaterial({ map: glowTex, transparent: true, opacity: 0.3, depthWrite: false, side: THREE.DoubleSide }),
      )
      sconce.position.set(side * (HALF_W - 0.2), 2.4, z - 2.6)
      sconce.rotation.y = side < 0 ? Math.PI / 2 : -Math.PI / 2
      scene.add(sconce)

      // 垂挂胶片串：挂在走廊内侧，近处大到占画面边缘，推进时快速掠过
      const hx = side * 3.78
      scene.add(new THREE.Line(
        new THREE.BufferGeometry().setFromPoints([
          new THREE.Vector3(hx, 3.95, z - 0.25),
          new THREE.Vector3(hx, 1.5, z - 0.25),
        ]), archMat,
      ))
      for (let k = 0; k < 4; k++) {
        const f = new THREE.Mesh(
          new THREE.PlaneGeometry(0.42, 0.42),
          new THREE.MeshBasicMaterial({
            map: filmTextures[(k + (side > 0 ? 2 : 0)) % 5],
            transparent: true, side: THREE.DoubleSide,
          }),
        )
        f.position.set(hx, 3.55 - k * 0.52, z - 0.25)
        scene.add(f)
        hangings.push({ mesh: f, phase: k * 0.8 + z * 0.12, base: 3.55 - k * 0.52 })
      }
    }

    // 地面亮带：每穿过一道门廊，地面明暗交替一次
    const band = new THREE.Mesh(new THREE.PlaneGeometry(HALF_W * 2, 1.5), bandMat)
    band.rotation.x = -Math.PI / 2
    band.position.set(0, 0.026, z)
    scene.add(band)
  }

  // ---- 近景层：沿 z 密布的飘散票根 ----
  // 比中景的门更靠近相机，推进时掠过速度明显更快；
  // 近 / 中 / 远三层不同速率，就是「层次」最直接的来源。
  const scraps = []
  const scrapMat = new THREE.MeshBasicMaterial({
    map: ticketTex, transparent: true, opacity: 0.88, side: THREE.DoubleSide,
  })
  const rs = rng(4242)
  for (let z = 10; z > -68; z -= 3.4) {
    const size = 0.22 + rs() * 0.16
    const s = new THREE.Mesh(new THREE.PlaneGeometry(size, size), scrapMat)
    const y = 0.8 + rs() * 2.5
    s.position.set((rs() > 0.5 ? 1 : -1) * (2.6 + rs() * 1.5), y, z)
    s.rotation.set(rs() * 0.5, rs() * 0.8, rs() * Math.PI)
    scene.add(s)
    scraps.push({ mesh: s, base: y, phase: rs() * 6.28 })
  }
  for (let z = 9; z > -66; z -= 5.4) {
    const t = new THREE.Mesh(new THREE.PlaneGeometry(0.52, 0.34), scrapMat)
    t.rotation.x = -Math.PI / 2
    t.rotation.z = rs() * Math.PI
    t.position.set((rs() > 0.5 ? 1 : -1) * (1.5 + rs() * 2.2), 0.034, z)
    scene.add(t)
  }

  // ---- 中近景层：从天花垂挂的真实电影海报 ----
  // 用户「走廊上面可以挂一些电影海报」「海报挂在哪里」：海报就常驻在这些挂位上，
  // 不做悬停弹卡。冷启动先显示手绘占位，/insights/hall-posters 片单到达后
  // setPosters() 把每部影片的真实海报（走 /api/v1/img 代理）画进同一张纹理；
  // 容器出网失败时占位仍在，不会挂一排空白框。
  // 近中段左右成对悬挂，一眼能数出「挂了一排海报」；
  // ★ z 坐标刻意避开五扇门的 -8.5 / -24 / -42，海报不挡门板中间。
  const POSTER_Z = [-1, -1, -5.5, -5.5, -14, -14, -19.5, -19.5,
    -29, -29, -35, -49, -56, -64]
  const posterMats = posterTextures.map((tex) => new THREE.MeshBasicMaterial({ map: tex, side: THREE.DoubleSide }))
  const posterBack = new THREE.MeshBasicMaterial({ color: 0xFFFCF3, side: THREE.DoubleSide })
  const posterInk = new THREE.LineBasicMaterial({ color: INK, transparent: true, opacity: 0.62 })
  const posterCord = new THREE.LineBasicMaterial({ color: INK, transparent: true, opacity: 0.46 })
  const posters = []
  const posterGeo = new THREE.PlaneGeometry(1.32, 1.92)
  const posterFrameGeo = new THREE.PlaneGeometry(1.44, 2.04)
  const posterEdgeGeo = new THREE.EdgesGeometry(posterFrameGeo)
  const pinGeo = new THREE.BoxGeometry(0.13, 0.17, 0.07)
  POSTER_Z.forEach((z, k) => {
    const side = k % 2 ? 1 : -1
    const grp = new THREE.Group()
    grp.position.set(side * 3.9, 2.4, z)
    grp.rotation.y = -side * 0.32
    const back = new THREE.Mesh(posterFrameGeo, posterBack)
    back.position.z = -0.014
    grp.add(back)
    const face = new THREE.Mesh(posterGeo, posterMats[k % posterMats.length])
    grp.add(face)
    const edge = new THREE.LineSegments(posterEdgeGeo, posterInk)
    edge.position.z = 0.012
    grp.add(edge)
    // 两根细绳从天花垂到海报上沿 + 两枚铜夹
    grp.add(new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints([
      new THREE.Vector3(-0.5, 1.9, -0.01), new THREE.Vector3(-0.5, 1.0, -0.01),
      new THREE.Vector3(0.5, 1.9, -0.01), new THREE.Vector3(0.5, 1.0, -0.01),
    ]), posterCord))
    for (const px of [-0.5, 0.5]) {
      const pin = new THREE.Mesh(pinGeo, brass)
      pin.position.set(px, 1.0, 0.03)
      grp.add(pin)
    }
    scene.add(grp)
    posters.push({ grp, face, phase: k * 0.74 })
  })
  canvasEl.dataset.posters = String(posters.length)
  canvasEl.dataset.posterSlots = String(POSTER_SLOTS)
  if (movies.length) setPosters(movies)

  // 中央地毯：两条铜线把视线引到尽头的盒子
  const runner = new THREE.Mesh(
    new THREE.PlaneGeometry(1.9, LEN),
    new THREE.MeshBasicMaterial({ color: 0xC9B08A, transparent: true, opacity: 0.16, depthWrite: false }),
  )
  runner.rotation.x = -Math.PI / 2
  runner.position.set(0, 0.012, MID)
  scene.add(runner)
  for (const sx of [-0.93, 0.93]) {
    const line = new THREE.Mesh(new THREE.BoxGeometry(0.022, 0.012, LEN), brass)
    line.position.set(sx, 0.02, MID)
    scene.add(line)
  }

  // 尽头过曝白光出口（itomdev 图 3）
  const exitGlow = new THREE.Mesh(
    new THREE.PlaneGeometry(4.2, 4.0),
    new THREE.MeshBasicMaterial({ color: 0xFFFFFF, transparent: true, opacity: 1, fog: false }),
  )
  exitGlow.position.set(0, 2.0, Z_FAR + 0.3)
  scene.add(exitGlow)
  const exitHalo = new THREE.Mesh(
    new THREE.PlaneGeometry(7.6, 6.4),
    new THREE.MeshBasicMaterial({ map: glowTex, transparent: true, opacity: 0.85, depthWrite: false, fog: false }),
  )
  exitHalo.position.set(0, 2.0, Z_FAR + 0.25)
  scene.add(exitHalo)

  // ---- 五扇白木门 ----
  const doors = DOOR_POS.map((p, i) => {
    const group = new THREE.Group()
    group.position.set(p.x, 0, p.z)

    const inner = new THREE.Mesh(new THREE.PlaneGeometry(1.78, 2.9), new THREE.MeshBasicMaterial({ color: 0x8A6A42 }))
    inner.position.set(0, 1.5, -0.3)
    group.add(inner)
    const glow = new THREE.Mesh(
      new THREE.PlaneGeometry(1.78, 2.9),
      new THREE.MeshBasicMaterial({ map: glowTex, transparent: true, opacity: 0.02, depthWrite: false }),
    )
    glow.position.set(0, 1.5, -0.26)
    group.add(glow)

    const pool = new THREE.Mesh(
      new THREE.PlaneGeometry(3.4, 3.4),
      new THREE.MeshBasicMaterial({ map: glowTex, transparent: true, opacity: 0.3, depthWrite: false }),
    )
    pool.rotation.x = -Math.PI / 2
    pool.position.set(0, 0.024, 1.4)
    group.add(pool)

    // 门框：白木 + 墨线，铜色合页
    for (const sx of [-1, 1]) {
      const post = outlined(new THREE.BoxGeometry(0.15, 3.12, 0.24), white, 0.8)
      post.position.set(sx * 1.0, 1.56, 0.02)
      group.add(post)
    }
    const lintel = outlined(new THREE.BoxGeometry(2.24, 0.18, 0.28), white, 0.8)
    lintel.position.set(0, 3.13, 0.02)
    group.add(lintel)

    const pivot = new THREE.Group()
    pivot.position.set(-0.9, 0, 0.1)
    group.add(pivot)
    const panelMat = new THREE.MeshBasicMaterial({ map: doorTexture(tints[i] || '#A67C2E', i), side: THREE.DoubleSide })
    const panel = outlined(new THREE.BoxGeometry(1.8, 2.94, 0.09), panelMat, 0.85)
    panel.position.set(0.9, 1.5, 0)
    pivot.add(panel)
    const knob = new THREE.Mesh(new THREE.SphereGeometry(0.055, 14, 12), brass)
    knob.position.set(1.63, 1.45, 0.09)
    pivot.add(knob)

    // 门楣上方两枚挂钉（配合 DOM 木牌，观感像牌子真挂在门上）
    for (const sx of [-0.7, 0.7]) {
      const nail = new THREE.Mesh(new THREE.SphereGeometry(0.035, 10, 8), brass)
      nail.position.set(sx, 3.34, 0.16)
      group.add(nail)
    }

    scene.add(group)
    return { group, pivot, glow }
  })

  // ---- 中央「电影盒子」 ----
  const box = new THREE.Group()
  // 合盒时推到镜头眼前的近景；开封后由 tick 按 open 进度退回走廊中轴
  box.position.set(BOX_SEALED.x, BOX_SEALED.y, BOX_SEALED.z)
  box.scale.setScalar(1.0)
  // 侧过来 24°：配合右前上方俯视相机，正面 / 顶面 / 右侧面同时入画
  box.rotation.y = -0.42
  const BW = 2.85, BH = 1.7, BD = 1.9

  // 地面落影：白纸场景里最有效的"贴地"线索
  const shadow = new THREE.Mesh(
    new THREE.PlaneGeometry(BW * 1.9, BD * 2.1),
    new THREE.MeshBasicMaterial({ map: shadowTex, transparent: true, depthWrite: false }),
  )
  shadow.rotation.x = -Math.PI / 2
  shadow.position.set(0, 0.03, 0.28)
  box.add(shadow)

  // 六个面分明暗：白描场景里只有靠面差才能读出「这是一只立方体盒子」
  const boxGeo = new THREE.BoxGeometry(BW, BH, BD)
  const boxMats = [
    new THREE.MeshBasicMaterial({ map: boxSide }),  // +x 右侧面（俯视主见）
    new THREE.MeshBasicMaterial({ color: 0xE4CFAE }), // -x 左侧面
    new THREE.MeshBasicMaterial({ color: 0xFFF8E8 }), // +y 顶面
    new THREE.MeshBasicMaterial({ color: 0xC9AE86 }), // -y 底面
    new THREE.MeshBasicMaterial({ color: 0xFFFDF7 }), // +z 正面
    new THREE.MeshBasicMaterial({ map: boxSide }),  // -z 背面
  ]
  const boxBody = new THREE.Group()
  boxBody.add(new THREE.Mesh(boxGeo, boxMats))
  boxBody.add(new THREE.LineSegments(
    new THREE.EdgesGeometry(boxGeo, 18),
    new THREE.LineBasicMaterial({ color: INK, transparent: true, opacity: 0.95 }),
  ))
  boxBody.position.set(0, BH / 2, 0)
  box.add(boxBody)
  // 正面标签缩小、四周留出纸边：旧版铺满整面，读起来就是一块广告牌
  const face = new THREE.Mesh(
    new THREE.PlaneGeometry(BW * 0.74, BH * 0.72),
    new THREE.MeshBasicMaterial({ map: boxFace, transparent: true }),
  )
  face.position.set(0, BH * 0.48, BD / 2 + 0.012)
  box.add(face)

  // 立体细节：略宽的底座 + 八枚铜包角 + 正面锁扣。
  // 这三类小体积在俯视透视里比任何贴图都更能证明「它是 3D 盒子」。
  const base = outlined(
    new THREE.BoxGeometry(BW + 0.14, 0.15, BD + 0.14),
    new THREE.MeshBasicMaterial({ color: 0xD8BE98 }), 0.8,
  )
  base.position.set(0, 0.075, 0)
  box.add(base)
  for (const sx of [-1, 1]) {
    for (const sz of [-1, 1]) {
      for (const sy of [0.14, BH - 0.1]) {
        const cap = new THREE.Mesh(new THREE.BoxGeometry(0.1, 0.14, 0.1), brassLight)
        cap.position.set(sx * (BW / 2 - 0.005), sy, sz * (BD / 2 - 0.005))
        box.add(cap)
      }
    }
  }
  const latchPlate = new THREE.Mesh(new THREE.BoxGeometry(0.28, 0.2, 0.055), brassLight)
  latchPlate.position.set(0, BH * 0.87, BD / 2 + 0.04)
  box.add(latchPlate)
  const latchRing = new THREE.Mesh(new THREE.TorusGeometry(0.07, 0.02, 8, 20), brassLight)
  latchRing.position.set(0, BH * 0.86 - 0.16, BD / 2 + 0.07)
  box.add(latchRing)

  // 盒盖：以后沿为铰链，向上掀开
  const lidPivot = new THREE.Group()
  lidPivot.position.set(0, BH, -BD / 2)
  box.add(lidPivot)
  const lid = outlined(
    new THREE.BoxGeometry(BW + 0.16, 0.2, BD + 0.12),
    new THREE.MeshBasicMaterial({ color: 0xE8D3AC }),
    0.95,
  )
  lid.position.set(0, 0, BD / 2)
  // 盖顶烫金纸标：俯视相机看到的第一块面，必须有内容而不是空白米板
  const lidArt = new THREE.Mesh(
    new THREE.PlaneGeometry(BW * 0.9, BD * 0.86),
    new THREE.MeshBasicMaterial({ map: lidFace, transparent: true, side: THREE.DoubleSide }),
  )
  lidArt.rotation.x = -Math.PI / 2
  lidArt.position.set(0, 0.103, 0)
  lid.add(lidArt)
  lidPivot.add(lid)

  // 盒内白光（盒盖打开才透出来）
  const boxLight = new THREE.Mesh(
    new THREE.PlaneGeometry(BW * 1.2, BD * 1.2),
    new THREE.MeshBasicMaterial({ map: glowTex, transparent: true, opacity: 0.6, depthWrite: false }),
  )
  boxLight.rotation.x = -Math.PI / 2
  boxLight.position.set(0, BH + 0.02, 0)
  box.add(boxLight)
  const beam = new THREE.Mesh(
    new THREE.PlaneGeometry(BW * 0.9, 3.2),
    new THREE.MeshBasicMaterial({ map: glowTex, transparent: true, opacity: 0.36, depthWrite: false, side: THREE.DoubleSide }),
  )
  beam.position.set(0, BH + 1.5, 0)
  box.add(beam)

  // 从盒里飘出的胶片格
  const films = filmTextures.map((tex, i) => {
    const f = outlined(
      new THREE.PlaneGeometry(0.48, 0.48),
      new THREE.MeshBasicMaterial({ map: tex, transparent: true, side: THREE.DoubleSide }),
      0.7,
    )
    const a = (i / 5) * Math.PI * 2
    f.position.set(Math.cos(a) * 1.15, BH + 0.85 + (i % 3) * 0.36, Math.sin(a) * 0.7)
    box.add(f)
    return { mesh: f, base: f.position.y, a }
  })

  // 盒子上方一枚金色小光盘（A24 的漂浮感，只留一枚做点缀）
  const haloDisc = new THREE.Mesh(
    new THREE.RingGeometry(0.12, 0.33, 48),
    new THREE.MeshBasicMaterial({ color: 0xA67C2E, transparent: true, opacity: 0.55, side: THREE.DoubleSide, depthWrite: false }),
  )
  haloDisc.position.set(0, BH + 2.35, 0)
  haloDisc.rotation.x = -0.7
  box.add(haloDisc)

  scene.add(box)
  // 盒子必须画在纸幕之上（纸幕 depthTest:false 最后盖住走廊）
  box.traverse((o) => { o.renderOrder = 30 })
  const dustPos = new Float32Array(150 * 3)
  const rd = rng(2026)
  for (let i = 0; i < 150; i++) {
    dustPos[i * 3] = (rd() - 0.5) * (HALF_W * 2 - 0.4)
    dustPos[i * 3 + 1] = 0.3 + rd() * (HEIGHT - 0.7)
    dustPos[i * 3 + 2] = Z_FAR + rd() * (LEN - 4)
  }
  const dustGeo = new THREE.BufferGeometry()
  dustGeo.setAttribute('position', new THREE.BufferAttribute(dustPos, 3))
  const dust = new THREE.Points(
    dustGeo,
    new THREE.PointsMaterial({ color: 0x9A7A4E, size: 0.03, transparent: true, opacity: 0.42, depthWrite: false }),
  )
  scene.add(dust)

  // 纸幕在合盒时走 opaque 队列，凡是 transparent 的走廊装饰都必须
  // 整体隐藏：three 的 transparent 队列永远在 opaque 之后渲染，否则
  // 门廊墨线、地面亮带、门内光斑会浮在纸幕之上把走廊漏出来。
  const fxNodes = []
  scene.traverse((o) => {
    if (!o.material || o === sheet) return
    let p = o, inBox = false
    while (p) { if (p === box) { inBox = true; break } p = p.parent }
    if (inBox) return
    const mats = Array.isArray(o.material) ? o.material : [o.material]
    if (mats.some((m) => m && m.transparent)) fxNodes.push(o)
  })

  const v = new THREE.Vector3()
  const v2 = new THREE.Vector3()
  const v3 = new THREE.Vector3()
  // 合盒 / 开封两套相机朝向：用四元数 slerp，避免 Euler 插值时的翻滚跳变
  // 用相机对象（而非普通 Object3D）算 lookAt：普通对象的 +z 指向目标，
  // 相机的 -z 才指向目标，混用会让合盒镜头转向盒子背后
  const sealedCam = new THREE.PerspectiveCamera()
  const qSealed = new THREE.Quaternion()
  const qOpen = new THREE.Quaternion()
  let curOpen = 0        // 当前开盒进度（0=合盒纸幕，1=走廊全开），供 DOM 投影门控
  let boxFade = 0        // 相机靠近时盒子退场的进度（0=完整，1=已化作光）

  function resize(w, h) {
    if (!w || !h) return
    renderer.setSize(w, h, false)
    camera.aspect = w / h
    camera.updateProjectionMatrix()
  }

  function tick(state) {
    const t = state.time || 0
    const depth = state.walk || 0
    // open: 0=合盒（纸幕遮住走廊，只见盒子）→ 1=开封（镜头退回入口，四层长廊展开）
    const open = clamp01(state.open ?? 1)
    curOpen = open
    const ease = smooth(open)

    // 纸幕：开封到 0.18 起从中撕开，0.60 前完全淡尽。
    // DOM 撕纸层与这里共用同一个 open 进度，所以「纸撕开」和「门出现」严格同步。
    const sheetAlpha = 1 - smooth((open - 0.18) / 0.42)
    sheet.material.opacity = sheetAlpha
    // ★ 纸幕完全不透明时走 opaque 队列（renderOrder 20），盒身六面
    //   （opaque / renderOrder 30）才画在它上面。若一直留在 transparent
    //   队列，three 会先画所有 opaque（含盒身），再用纸幕盖掉它们，
    //   结果只剩贴图与墨线浮在纸白上 —— 侧面木纹与体积感全丢。
    //   撕纸阶段才切回 transparent 做渐隐，此时盒子已在化光，不影响观感。
    const wantTransparent = sheetAlpha < 0.999
    if (sheet.material.transparent !== wantTransparent) {
      sheet.material.transparent = wantTransparent
      sheet.material.needsUpdate = true
    }
    sheet.visible = sheetAlpha > 0.01
    // 合盒：透明队列的走廊装饰一律收起（纸幕是 opaque，挡不住它们）
    fxNodes.forEach((o) => { o.visible = open > 0.2 })

    // 相机：合盒时贴近盒子俯看（48° 特写），开封后平滑退回入口的 58° 广角，
    // 之后才由滚轮接管 6 → -14 的纵深飞行。两幕之间不做硬切。
    const openZ = 6 - depth * WALK_DEPTH - state.fly * 5.5
    camera.position.set(
      lerp(CAM_SEALED.x + state.lookX * 0.1, state.lookX * 0.24 + Math.sin(t * 0.33) * 0.018, ease),
      lerp(CAM_SEALED.y + state.lookY * 0.05, 1.68 + state.lookY * 0.1 + Math.sin(t * 0.62) * 0.022, ease),
      lerp(CAM_SEALED.z, openZ, ease),
    )
    camera.rotation.set(
      -state.lookY * 0.045 - depth * 0.012,
      -state.lookX * 0.085 + state.fly * (state.flyX || 0) * 0.09,
      0,
    )
    qOpen.copy(camera.quaternion)
    // 合盒：相机抬到盒子右前上方俯看，顶面 / 正面 / 右侧面同时入画。
    // 旧版相机 y=1.75 低于盒盖顶 y≈2.2，只能看到正面一张纸 =「没有 3D」。
    sealedCam.position.set(
      CAM_SEALED.x + state.lookX * 0.12,
      CAM_SEALED.y + state.lookY * 0.06,
      CAM_SEALED.z,
    )
    sealedCam.lookAt(BOX_SEALED.x, 0.92, BOX_SEALED.z)
    qSealed.copy(sealedCam.quaternion)
    camera.quaternion.copy(qSealed).slerp(qOpen, ease)
    const fov = lerp(48, 58, ease)
    if (Math.abs(camera.fov - fov) > 0.02) { camera.fov = fov; camera.updateProjectionMatrix() }

    doors.forEach((d, i) => {
      let target = state.hover === i ? -0.72 : 0
      if (state.fly > 0 && state.flyIndex === i) target = -1.4
      d.pivot.rotation.y += (target - d.pivot.rotation.y) * 0.12
      const open = Math.min(1, Math.max(0, -d.pivot.rotation.y / 0.7))
      d.glow.material.opacity = 0.02 + open * (0.9 + Math.sin(t * 1.1 + i) * 0.05)
    })

    // ---- 开盒：盖得严严实实 → 掀盖 → 盒内白光漫出 → 盒子化作光退场 ----
    box.rotation.y = -0.42 + Math.sin(t * 0.32) * 0.045
    const lidOpen = smooth(open / 0.34)
    lidPivot.rotation.x = -1.52 * lidOpen
    boxLight.material.opacity = 0.04 + lidOpen * (0.82 + (state.boxHover || 0) * 0.14)
    beam.material.opacity = 0.04 + lidOpen * 0.8
    haloDisc.rotation.z = t * 0.22
    haloDisc.position.y = BH + 2.35 + Math.sin(t * 0.9) * 0.12
    // 合盒首屏要「一张纸上只有一只盒子」：盒里飘出的胶片与光盘等开封后再出现
    haloDisc.visible = open > 0.12
    films.forEach((f, i) => {
      f.mesh.visible = open > 0.12
      f.mesh.position.y = f.base + Math.sin(t * 0.8 + i * 1.4) * 0.14 + lidOpen * 0.35
      f.mesh.rotation.y = Math.sin(t * 0.45 + f.a) * 0.5
      f.mesh.rotation.z = Math.sin(t * 0.6 + i) * 0.12
    })

    // 盒子先被光胀大一点，再缩小上浮、完全化光；同时从近景退回走廊中轴。
    // 与 DOM 的撕纸 / 白闪叠在一起，读起来就是「盒子打开，里面的走廊铺展开」。
    const boxGone = smooth((open - 0.34) / 0.5)
    const swell = Math.sin(Math.min(1, open / 0.8) * Math.PI) * 0.26
    const boxScale = Math.max(0.001, 1.0 + swell - boxGone * boxGone * 1.32)
    box.scale.setScalar(boxScale)
    box.position.z = lerp(BOX_SEALED.z, BOX_POS.z, ease)
    box.position.y = BOX_POS.y + boxGone * 0.8
    box.visible = boxGone < 0.995 && boxScale > 0.01
    // ★ 历史事故防护：相机沿中轴推进时会穿过盒子，盒内光柱贴脸会放大成
    //   一整片米黄把走廊盖住（「中段全白」）。滚轮一推进就彻底撤掉盒子。
    boxFade = Math.min(1, Math.max(0, (depth - 0.1) / 0.24))
    if (boxFade >= 0.995) box.visible = false

    // 近景层：垂挂胶片与飘散票根缓慢呼吸；相机推进时它们比中景的门
    // 掠过得快得多，三层不同速率合起来就是「空间有层次」。
    hangings.forEach((h) => {
      h.mesh.visible = open > 0.22
      h.mesh.rotation.z = Math.sin(t * 0.7 + h.phase) * 0.09
      h.mesh.position.y = h.base + Math.sin(t * 0.9 + h.phase) * 0.04
    })
    scraps.forEach((s) => {
      s.mesh.visible = open > 0.22
      s.mesh.position.y = s.base + Math.sin(t * 0.55 + s.phase) * 0.14
      s.mesh.rotation.z += 0.0012
    })
    // 垂挂海报：合盒时整组藏在纸幕后，开封后沿走廊依次出现并轻轻摇摆。
    // 海报是静态展示物，不随鼠标缩放（用户明确不要悬停弹卡）。
    posters.forEach((p) => {
      p.grp.visible = open > 0.24
      p.grp.rotation.z = Math.sin(t * 0.6 + p.phase) * 0.024
    })
    dust.visible = open > 0.3
    // 空气层：越往深处走，门廊地面亮带越亮（尽头白光在逼近）
    bandMat.opacity = 0.13 + depth * 0.14
    dust.position.y = Math.sin(t * 0.24) * 0.14
    renderer.render(scene, camera)
  }

  /** 第 i 扇门的门板屏幕矩形（DOM 命中区贴门板本身，不再贴门楣木牌） */
  function project(i, w, h) {
    const p = DOOR_POS[i]
    v.set(p.x, 1.5, p.z + 0.14).project(camera)
    const x = (v.x * 0.5 + 0.5) * w
    const y = (-v.y * 0.5 + 0.5) * h
    // 门板四角投影出屏幕宽高：近门大、远门小，命中区始终精确覆盖门板
    v2.set(p.x - 0.9, 0.03, p.z + 0.14).project(camera)
    v3.set(p.x + 0.9, 2.97, p.z + 0.14).project(camera)
    const bw = Math.abs(v3.x - v2.x) * 0.5 * w
    const bh = Math.abs(v3.y - v2.y) * 0.5 * h
    const distance = Math.max(1, camera.position.z - p.z)
    const s = Math.max(0.58, Math.min(1.15, 10 / distance))
    // ★ 合盒阶段门牌一律不出现：参考站是「纸撕开之后才看得见门」，
    //   这里用同一个 open 进度门控投影，避免门牌提前浮在纸幕上。
    return {
      x, y, s, w: bw, h: bh,
      visible: curOpen > 0.86 && v.z < 1 && x > -120 && x < w + 120 && y > -120 && y < h + 120,
    }
  }

  /** 盒子正面屏幕矩形：DOM「打开盒子」命中区精确贴合俯视下的 3D 盒身 */
  function projectBox(w, h) {
    box.updateMatrixWorld(true)
    // 俯视 + 盒子绕 Y 旋转后，正面是斜四边形；只取两个对角点会被透视
    // 压缩成一条矮矩形（实测 150px vs 实际 400px），CTA 就会压到盒身文字。
    // 四个角全投影取轴对齐包围盒，命中区才真正贴合屏幕上的盒身。
    let minX = Infinity, minY = Infinity, maxX = -Infinity, maxY = -Infinity, front = true
    for (const [cx, cy] of [[-BW / 2, 0.03], [BW / 2, 0.03],
      [-BW / 2, BH + 0.12], [BW / 2, BH + 0.12]]) {
      v.set(cx, cy, BD / 2).applyMatrix4(box.matrixWorld).project(camera)
      const sx = (v.x * 0.5 + 0.5) * w
      const sy = (-v.y * 0.5 + 0.5) * h
      minX = Math.min(minX, sx); maxX = Math.max(maxX, sx)
      minY = Math.min(minY, sy); maxY = Math.max(maxY, sy)
      front = front && v.z < 1
    }
    // 盒子开始化光时 DOM 命中区一起收起，避免点到看不见的东西
    return {
      x: (minX + maxX) / 2, y: (minY + maxY) / 2,
      w: maxX - minX, h: maxY - minY,
      visible: curOpen < 0.34 && box.visible && front,
    }
  }

  /**
   * 真实片单到达：把每部影片的海报「静态贴」到对应挂位上。
   * 用户最新要求：不需要鼠标悬停弹海报，海报挂在哪里就在哪里显示。
   * 一片一纹理、同一 canvas 重绘，图片失败保留手绘占位。
   */
  function setPosters(list) {
    if (!Array.isArray(list) || !list.length || disposed) return
    // 片单刷新：先掐掉在途图片回调，再释放上一轮自有资源
    posterLoads.forEach((im) => { im.onload = null; im.onerror = null })
    posterLoads.length = 0
    const freed = new Set()
    posterOwned.forEach((o) => { if (o && !freed.has(o)) { freed.add(o); o.dispose() } })
    posterOwned.length = 0

    let real = 0
    posters.forEach((p, i) => {
      const m = list[i % list.length]
      const card = toPosterCard(m, i)
      const c = document.createElement('canvas')
      c.width = 288
      c.height = 420
      const g = c.getContext('2d')
      paintHangingPoster(c, g, card, null)
      const tex = asTexture(c)
      const mat = new THREE.MeshBasicMaterial({ map: tex, side: THREE.DoubleSide })
      p.face.material = mat
      posterOwned.push(tex, mat)
      if (!m?.poster_url) return
      const im = new Image()
      im.crossOrigin = 'anonymous'
      im.onload = () => {
        if (disposed || !im.naturalWidth) return
        paintHangingPoster(c, g, card, im)
        tex.needsUpdate = true
        real += 1
        canvasEl.dataset.posterReal = String(real)
      }
      // 容器出网失败时不报错、不空白：手绘占位继续挂着
      im.onerror = () => {}
      im.src = m.poster_url
      posterLoads.push(im)
    })
    canvasEl.dataset.posterBound = String(list.length)
    canvasEl.dataset.posterReal = '0'
  }

  function dispose() {
    disposed = true
    posterLoads.forEach((im) => { im.onload = null; im.onerror = null })
    posterLoads.length = 0
    // 近景层大量复用同一批纹理/材质，必须去重后再释放
    const seen = new Set()
    const kill = (o) => { if (o && !seen.has(o)) { seen.add(o); o.dispose() } }
    scene.traverse((obj) => {
      kill(obj.geometry)
      const mats = Array.isArray(obj.material) ? obj.material : obj.material ? [obj.material] : []
      mats.forEach((m) => { if (m?.map) kill(m.map); kill(m) })
    })
    ;[floorTex, brickTex, ceilTex, glowTex, boxFace, lidFace, boxSide,
      shadowTex, ticketTex, ...filmTextures, ...posterTextures,
      ...posterMats, ...posterOwned,
      archMat, bandMat, scrapMat, posterBack, posterInk, posterCord].forEach(kill)
    renderer.dispose()
    renderer.forceContextLoss()
  }

  return { resize, tick, project, projectBox, setPosters, dispose }
}
