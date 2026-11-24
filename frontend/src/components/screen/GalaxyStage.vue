<template>
  <div ref="host" class="galaxy-stage" @pointermove="onMove" @pointerleave="onLeave">
    <!-- 悬停解读卡：每颗星 = 一部真实影片，悬停即读出它的口碑与热度 -->
    <div
      v-if="tip.show && tip.movie"
      class="galaxy-tip"
      :class="[tip.flipX ? 'galaxy-tip--lx' : '', tip.flipY ? 'galaxy-tip--ly' : '']"
      :style="{ left: tip.x + 'px', top: tip.y + 'px' }"
    >
      <b class="galaxy-tip__name">{{ tip.movie.title_zh || tip.movie.title || tip.movie.movie_id }}</b>
      <span class="galaxy-tip__meta">
        评分 {{ fmtRating(tip.movie.rating) }} · {{ fmtVotes(tip.movie.votes) }} 票 · {{ (tip.movie.genres_zh || []).slice(0, 3).join(' / ') || '类型未标' }}
      </span>
      <span class="galaxy-tip__note">{{ tip.note }}</span>
    </div>
  </div>
</template>

<script setup>
// ============================================================
// 深空电影宇宙 · 底层 3D 粒子星系（全屏画布）
// ------------------------------------------------------------
// 复用开源渲染栈（不自研轮子）：
//   three.js            —— Points 粒子 + 自定义 ShaderMaterial
//   postprocessing      —— Bloom(mipmapBlur) 泛光 + 暗角 + 边缘色散
//   camera-controls     —— 阻尼相机 / 拖拽旋转 / 缩放 / 空闲自转
//   maath/random        —— 背景星尘球内均匀分布
//   sc-datav flyLine 技法 —— CatmullRom 曲线滑窗 + percent 属性流星彗星
// 数据映射（真实数据驱动，非装饰）：
//   旋臂 = 主类型（Top 6 类型各成一条旋臂）· 半径 = 讨论热度（越热越靠核心）
//   Y 轴 = 评分（口碑决定星系厚度）· 颜色 = 冷蓝→紫→暖金（低分→高分）· 大小 = 票数
// 无任何坐标轴 / 网格 / 刻度。
// ★ 可读性三件套（2026-10-19 用户反馈"看不懂星系在表达什么"）：
//   ① 旋臂类型标签（pill 文字：类型名 + 影片数，随星系旋转）
//   ② 悬停解读卡（每颗星 = 一部影片：评分/票数/类型/热度百分位）
//   ③ 界面读图图例（见 UniverseScreen 的 .galaxy-legend）
// ============================================================
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import * as THREE from 'three'
import {
  EffectComposer, RenderPass, EffectPass, BloomEffect,
  ChromaticAberrationEffect, BlendFunction,
} from 'postprocessing'
import CameraControls from 'camera-controls'
import { inSphere } from 'maath/random'

CameraControls.install({ THREE })

const props = defineProps({
  movies: { type: Array, default: () => [] },
  paused: { type: Boolean, default: false },   // 鼠标停在 HUD 面板上时暂停自转
})

const host = ref(null)

/* ---------- 悬停解读：每颗星 = 一部真实影片 ---------- */
const tip = ref({ show: false, x: 0, y: 0, flipX: false, flipY: false, movie: null, note: '' })
let lastSorted = []   // buildGalaxy 的排序表（几何 index → movie），tooltip 回查用
let avgRating = 7     // 全场均分（note 文案对比用）
const raycaster = new THREE.Raycaster()
raycaster.params.Points.threshold = 3.4   // 世界单位；星星间距 ~2-4，够宽容又不烫手
const ndc = new THREE.Vector2()

function fmtRating(r) {
  const n = Number(r)
  return Number.isFinite(n) ? n.toFixed(1) : '—'
}
function fmtVotes(v) {
  const n = Number(v) || 0
  return n >= 10000 ? `${(n / 10000).toFixed(1)} 万` : String(n)
}

function onMove(e) {
  const el = host.value
  // props.paused 为真 = 悬停 HUD 面板 或 已切到图表视图：此时不抢镜
  if (!el || !points || props.paused) return
  const rect = el.getBoundingClientRect()
  const x = e.clientX - rect.left
  const y = e.clientY - rect.top
  ndc.x = (x / rect.width) * 2 - 1
  ndc.y = -(y / rect.height) * 2 + 1
  raycaster.setFromCamera(ndc, camera)
  const hit = raycaster.intersectObject(points, false)[0]
  if (!hit) {
    if (tip.value.show) hideTip()
    return
  }
  const m = lastSorted[hit.index]
  if (!m) return
  if (mat) mat.uniforms.uHover.value = hit.index
  const pct = Math.round((1 - hit.index / Math.max(1, lastSorted.length - 1)) * 100)
  const r = Number(m.rating) || 0
  tip.value = {
    show: true,
    x, y,
    flipX: x > rect.width - 320,
    flipY: y > rect.height - 140,
    movie: m,
    note: `热度超过 ${pct}% 的影片 · 口碑${r >= avgRating ? '高于' : '低于'}全场均分 ${avgRating.toFixed(1)}`,
  }
}
function hideTip() {
  tip.value = { ...tip.value, show: false }
  if (mat) mat.uniforms.uHover.value = -1
}
function onLeave() { hideTip() }

let renderer, scene, camera, controls, composer
let galaxy, points, dust, coreGlow
let geo, mat, dustGeo, dustMat
const comets = []
const armLabels = []   // 旋臂类型标签 sprite（随星系旋转，切换数据时重建）
let raf = 0, last = 0, ro = null
let disposed = false

/* 浅色版（2026-10-19 用户"整个页面改成浅色的"）：AdditiveBlending 在
   白纸上粒子会整体消失（加色越加越白），全部换 NormalBlending；
   颜色加深一档保证暖白底上的存在感 */
const COLD = new THREE.Color('#3D6B99')   // 冷蓝：低口碑
const MID = new THREE.Color('#8B5CF6')    // 紫：中口碑
const GOLD = new THREE.Color('#D9903A')   // 深金：高口碑（原 #FFD9A0 白底太浅）

/* ---------- 工具：柔和圆形贴图（核球辉光用） ---------- */
function makeGlowTexture(rgb) {
  const s = 128
  const c = document.createElement('canvas')
  c.width = c.height = s
  const ctx = c.getContext('2d')
  const g = ctx.createRadialGradient(s / 2, s / 2, 0, s / 2, s / 2, s / 2)
  g.addColorStop(0, rgb)
  g.addColorStop(0.25, 'rgba(255,236,180,0.55)')
  g.addColorStop(1, 'rgba(255,236,180,0)')
  ctx.fillStyle = g
  ctx.fillRect(0, 0, s, s)
  const t = new THREE.CanvasTexture(c)
  t.colorSpace = THREE.SRGBColorSpace
  return t
}

/* ---------- 星系几何：对数螺旋 + 类型旋臂 ---------- */
function buildGalaxy() {
  const list = (props.movies || []).filter((m) => m && m.movie_id)
  if (!list.length) return

  // 按热度降序：越热的星越靠核心
  const sorted = [...list].sort((a, b) => (b.votes || 0) - (a.votes || 0))
  const maxVotes = Math.max(1, ...sorted.map((m) => m.votes || 0))

  // 主类型 → 旋臂（取出现最多的 6 个类型，其余归入"其他"臂）
  const genreCount = new Map()
  for (const m of sorted) {
    const g = (m.genres_zh || [])[0] || '其他'
    genreCount.set(g, (genreCount.get(g) || 0) + 1)
  }
  const arms = [...genreCount.entries()]
    .sort((a, b) => b[1] - a[1])
    .slice(0, 6)
    .map((e) => e[0])
  const ARM_N = Math.max(arms.length, 1)

  // 悬停解读回查表 + 全场均分（tooltip 文案用）
  lastSorted = sorted
  avgRating = sorted.reduce((s, m) => s + (Number(m.rating) || 0), 0) / Math.max(1, sorted.length)

  buildArmLabels(arms, genreCount, ARM_N)

  const n = sorted.length
  const pos = new Float32Array(n * 3)
  const col = new Float32Array(n * 3)
  const siz = new Float32Array(n)
  const idx = new Float32Array(n)   // 粒子序号：悬停高亮与回查影片用
  const tmp = new THREE.Color()

  sorted.forEach((m, i) => {
    idx[i] = i
    const g = (m.genres_zh || [])[0] || '其他'
    let arm = arms.indexOf(g)
    if (arm < 0) arm = i % ARM_N

    const t = n > 1 ? i / (n - 1) : 0
    // 半径：热度排名 → 指数分布，热片聚核、冷片散布外缘
    const r = 9 + Math.pow(t, 0.62) * 76 + (Math.random() - 0.5) * 6
    // 对数螺旋：半径越大绕得越开
    const theta = (arm / ARM_N) * Math.PI * 2 + r * 0.052 + (Math.random() - 0.5) * 0.30
    // Y：口碑决定星系盘面厚度（±7）
    const rating = Number(m.rating) || 6.5
    const y = ((rating - 6.6) / 3.4) * 7 + (Math.random() - 0.5) * 2.4

    pos[i * 3] = Math.cos(theta) * r
    pos[i * 3 + 1] = y
    pos[i * 3 + 2] = Math.sin(theta) * r

    // 颜色三段：冷蓝(口碑偏低) → 紫(中) → 暖金(口碑偏高)。
    // 2026-10-19 用户反馈"不要全是深颜色"：中段插入紫，冷暖之间不再糊成灰，
    // 整片星系从"双色"变"三色彩虹"，与 HUD 的橙/青强调色呼应。
    // 区间收窄到 6.8~8.6 分：本库影片集中在 7~8.5，宽区间会让绝大多数星糊成中间色。
    const k = THREE.MathUtils.clamp((rating - 6.8) / 1.8, 0, 1)
    if (k < 0.5) tmp.copy(COLD).lerp(MID, k * 2)
    else tmp.copy(MID).lerp(GOLD, (k - 0.5) * 2)
    col[i * 3] = tmp.r
    col[i * 3 + 1] = tmp.g
    col[i * 3 + 2] = tmp.b

    // 大小：票数开方（避免头部影片吞掉画面）；整体略放大让星系更有体量
    siz[i] = 2.0 + Math.sqrt((m.votes || 0) / maxVotes) * 7.0
  })

  geo = new THREE.BufferGeometry()
  geo.setAttribute('position', new THREE.BufferAttribute(pos, 3))
  geo.setAttribute('aColor', new THREE.BufferAttribute(col, 3))
  geo.setAttribute('aSize', new THREE.BufferAttribute(siz, 1))
  geo.setAttribute('aIndex', new THREE.BufferAttribute(idx, 1))

  mat = new THREE.ShaderMaterial({
    uniforms: {
      uPixelRatio: { value: Math.min(window.devicePixelRatio || 1, 2) },
      uOpacity: { value: 0 },            // 入场淡入
      uHover: { value: -1 },              // 悬停粒子序号（-1 = 无）
    },
    vertexShader: `
      attribute float aSize;
      attribute vec3 aColor;
      attribute float aIndex;
      uniform float uPixelRatio;
      uniform float uHover;
      varying vec3 vColor;
      varying float vFade;
      varying float vHl;
      void main() {
        vColor = aColor;
        vec4 mv = modelViewMatrix * vec4(position, 1.0);
        gl_Position = projectionMatrix * mv;
        float d = max(-mv.z, 1.0);
        // 悬停星：放大 1.9 倍 + 向白色偏移，从星海里"跳"出来
        // step(0.4, |aIndex-uHover|)：差 <0.4 → 0，取 1-step = 仅悬停项为 1
        vHl = 1.0 - step(0.4, abs(aIndex - uHover));
        gl_PointSize = aSize * uPixelRatio * (300.0 / d) * (1.0 + vHl * 0.9);
        vFade = clamp(1.0 - d / 900.0, 0.18, 1.0);
      }
    `,
    fragmentShader: `
      uniform float uOpacity;
      varying vec3 vColor;
      varying float vFade;
      varying float vHl;
      void main() {
        // smoothstep 双层柔边：外圈柔光晕 + 中心亮核
        vec2 uv = gl_PointCoord - 0.5;
        float dd = length(uv);
        float halo = smoothstep(0.5, 0.08, dd);
        float core = smoothstep(0.26, 0.0, dd);
        vec3 c = mix(vColor, vec3(1.0), max(core * 0.55, vHl * 0.35));
        // NormalBlending 下比加色版略提不透明度，弥补没有叠加变亮的损失
        float a = halo * vFade * (0.66 + core * 0.5 + vHl * 0.4) * uOpacity;
        if (a < 0.01) discard;
        gl_FragColor = vec4(c, a);
      }
    `,
    transparent: true,
    depthWrite: false,
    blending: THREE.NormalBlending,
  })

  points = new THREE.Points(geo, mat)
  galaxy.add(points)
}

/* ---------- 旋臂类型标签：每条臂外缘一枚 pill（类型名 + 影片数） ----------
   用户 2026-10-19 反馈"星系不知道在表达什么"：把代码注释里的映射规则
   变成界面上看得见的信息 —— 标签随星系旋转，臂与文字始终对齐。 */
function makeLabelSprite(main, sub) {
  const fontMain = '600 42px "PingFang SC","Microsoft YaHei",sans-serif'
  const fontSub = '500 30px "PingFang SC","Microsoft YaHei",sans-serif'
  const probe = document.createElement('canvas').getContext('2d')
  probe.font = fontMain
  const wMain = probe.measureText(main).width
  probe.font = fontSub
  const wSub = probe.measureText(sub).width
  const padX = 36, padY = 16, gap = 10
  const c = document.createElement('canvas')
  c.width = Math.ceil(Math.max(wMain, wSub) + padX * 2)
  c.height = 42 + 30 + gap + padY * 2
  const ctx = c.getContext('2d')
  // 底 pill：半透明深蓝 + 暖金描边（HUD 同款质感）
  const rad = c.height / 2
  ctx.fillStyle = 'rgba(17, 27, 51, 0.82)'
  ctx.strokeStyle = 'rgba(255, 217, 160, 0.6)'
  ctx.lineWidth = 3
  ctx.beginPath()
  ctx.roundRect(1.5, 1.5, c.width - 3, c.height - 3, rad)
  ctx.fill()
  ctx.stroke()
  ctx.textAlign = 'center'
  ctx.textBaseline = 'middle'
  ctx.fillStyle = '#FFFFFF'
  ctx.font = fontMain
  ctx.fillText(main, c.width / 2, padY + 21)
  ctx.fillStyle = '#FFD9A0'
  ctx.font = fontSub
  ctx.fillText(sub, c.width / 2, padY + 42 + gap + 15)
  const tex = new THREE.CanvasTexture(c)
  tex.colorSpace = THREE.SRGBColorSpace
  tex.anisotropy = 4
  const m = new THREE.SpriteMaterial({
    map: tex, transparent: true, opacity: 0.96,
    depthTest: false, depthWrite: false,
  })
  const sp = new THREE.Sprite(m)
  const h = 9.5 // 世界单位高度（拉近后略放大，提升旋臂标签可读性）
  sp.scale.set(h * (c.width / c.height), h, 1)
  sp.renderOrder = 10
  return sp
}

function buildArmLabels(arms, genreCount, ARM_N) {
  clearArmLabels()
  const labelR = 92 // 星系外缘（星体最远 ~85），标签贴着盘缘
  for (let a = 0; a < ARM_N; a++) {
    const g = arms[a]
    if (!g) continue
    // 与星体同式的螺旋角：标签落在该臂的中线上
    const theta = (a / ARM_N) * Math.PI * 2 + labelR * 0.052
    const sp = makeLabelSprite(g, `${genreCount.get(g) || 0} 部`)
    sp.position.set(Math.cos(theta) * labelR, 9, Math.sin(theta) * labelR)
    galaxy.add(sp)
    armLabels.push(sp)
  }
}

function clearArmLabels() {
  for (const sp of armLabels) {
    if (galaxy) galaxy.remove(sp)
    sp.material.map?.dispose()
    sp.material.dispose()
  }
  armLabels.length = 0
}

/* ---------- 背景星尘：球壳均匀分布 ---------- */
function buildDust(count = 2600) {
  const buf = new Float32Array(count * 3)
  inSphere(buf, { radius: 1 })
  const pos = new Float32Array(count * 3)
  for (let i = 0; i < count; i++) {
    const x = buf[i * 3], y = buf[i * 3 + 1], z = buf[i * 3 + 2]
    const len = Math.hypot(x, y, z) || 1
    const r = 150 + Math.random() * 230
    pos[i * 3] = (x / len) * r
    pos[i * 3 + 1] = (y / len) * r * 0.62
    pos[i * 3 + 2] = (z / len) * r
  }
  dustGeo = new THREE.BufferGeometry()
  dustGeo.setAttribute('position', new THREE.BufferAttribute(pos, 3))
  dustMat = new THREE.PointsMaterial({
    size: 1.15,
    sizeAttenuation: false,
    color: 0x9A8A6C,           // 浅底版：白星尘改暖灰棕微点
    transparent: true,
    opacity: 0.32,
    depthWrite: false,
    blending: THREE.NormalBlending,
  })
  dust = new THREE.Points(dustGeo, dustMat)
  scene.add(dust)
}

/* ---------- 清理旧星系（切换数据时避免显存泄漏） ---------- */
function clearGalaxy() {
  if (points) {
    galaxy.remove(points)
    points.geometry.dispose()
    points.material.dispose()
    points = null
  }
  clearArmLabels()
  hideTip()
}

/* ---------- 流星彗星：sc-datav flyLine 技法移植 ----------
   开源参照 knight-L/sc-datav（src/pages/Demo0/map/flyLine.tsx）：
   CatmullRomCurve3 闭合曲线 + 滑动取点窗口 + 自定义 attribute
   percent（0→1→0）经 shader 控制点大小 = "光头尾尖"的彗星沿曲线流动。
   本实现按 closed + getSpacedPoints（弧长均匀）预取整条点列，
   每帧只做索引滑窗 + 写预分配缓冲，比原版每帧重建曲线更轻。 */
function buildComets(count = 3) {
  const COMET_COLORS = ['#D9903A', '#C2410C', '#0F766E']  // 浅底加深版
  for (let c = 0; c < count; c++) {
    // 随机闭合控制点：散布在星系外围的椭圆环，带随机倾角
    const kn = 9
    const pts = []
    const baseR = 100 + Math.random() * 60
    const lift = (Math.random() - 0.5) * 46
    for (let i = 0; i < kn; i++) {
      const a = (i / kn) * Math.PI * 2
      const r = baseR * (0.72 + Math.random() * 0.56)
      pts.push(new THREE.Vector3(
        Math.cos(a) * r,
        Math.sin(a) * r * 0.4 + lift,
        Math.sin(a) * r,
      ))
    }
    const curve = new THREE.CatmullRomCurve3(pts, true, 'catmullrom', 0.5)
    const total = 900
    const pointsArr = curve.getSpacedPoints(total)
    const win = 48
    const half = win / 2

    const pos = new Float32Array(win * 3)
    const siz = new Float32Array(win)
    const geo = new THREE.BufferGeometry()
    geo.setAttribute('position', new THREE.BufferAttribute(pos, 3))
    geo.setAttribute('aSize', new THREE.BufferAttribute(siz, 1))
    geo.setAttribute('aPercent', new THREE.BufferAttribute(siz, 1)) // 复用同一份数据

    const mat = new THREE.ShaderMaterial({
      uniforms: {
        uPixelRatio: { value: Math.min(window.devicePixelRatio || 1, 2) },
        uColor: { value: new THREE.Color(COMET_COLORS[c % COMET_COLORS.length]) },
      },
      vertexShader: `
        attribute float aSize;
        uniform float uPixelRatio;
        varying float vPct;
        void main() {
          vPct = aSize;
          vec4 mv = modelViewMatrix * vec4(position, 1.0);
          gl_Position = projectionMatrix * mv;
          float d = max(-mv.z, 1.0);
          gl_PointSize = aSize * uPixelRatio * (300.0 / d);
        }
      `,
      fragmentShader: `
        uniform vec3 uColor;
        varying float vPct;
        void main() {
          vec2 uv = gl_PointCoord - 0.5;
          float dd = length(uv);
          float halo = smoothstep(0.5, 0.05, dd);
          float a = halo * vPct * 0.85;
          if (a < 0.01) discard;
          gl_FragColor = vec4(uColor, a);
        }
      `,
      transparent: true,
      depthWrite: false,
      blending: THREE.NormalBlending,
    })

    const comet = new THREE.Points(geo, mat)
    comet.frustumCulled = false
    scene.add(comet)
    comets.push({ points: pointsArr, total, win, half, geo, mat, index: Math.random() * total, speed: 26 + Math.random() * 22, comet })
  }
}

/* 每帧推进彗星：滑窗取点 + percent（0→1→0）写入预分配缓冲 */
function updateComets(dt) {
  for (const cm of comets) {
    const arr = cm.points
    if (!arr || !arr.length) continue
    cm.index = (cm.index + cm.speed * dt) % arr.length
    const start = Math.floor(cm.index)
    const pos = cm.geo.attributes.position.array
    const siz = cm.geo.attributes.aSize.array
    for (let i = 0; i < cm.win; i++) {
      const p = arr[(start + i) % arr.length]
      if (!p) continue
      pos[i * 3] = p.x
      pos[i * 3 + 1] = p.y
      pos[i * 3 + 2] = p.z
      siz[i] = i < cm.half ? i / cm.half : 1 - (i - cm.half) / cm.half
    }
    cm.geo.attributes.position.needsUpdate = true
    cm.geo.attributes.aSize.needsUpdate = true
  }
}

/* ---------- 渲染循环 ---------- */
function tick(now) {
  raf = requestAnimationFrame(tick)
  if (document.hidden || disposed) return
  const dt = Math.min((now - last) / 1000, 0.05)
  last = now

  // 入场淡入 + 缓慢自转
  if (mat && mat.uniforms.uOpacity.value < 1) {
    mat.uniforms.uOpacity.value = Math.min(1, mat.uniforms.uOpacity.value + dt * 0.7)
  }
  galaxy.rotation.y += dt * 0.028
  if (dust) dust.rotation.y -= dt * 0.006
  updateComets(dt)

  // 空闲自转：鼠标停在 HUD 面板（paused）或用户操作中时不抢镜
  if (!props.paused && !controls.active) controls.rotate(dt * 0.06, 0, true)

  controls.update(dt)
  composer.render(dt)
}

/* ---------- 尺寸 ---------- */
function resize() {
  const el = host.value
  if (!el || !renderer) return
  const w = el.clientWidth || window.innerWidth
  const h = el.clientHeight || window.innerHeight
  camera.aspect = w / h
  camera.updateProjectionMatrix()
  renderer.setSize(w, h, false)
  composer.setSize(w, h)
}

onMounted(() => {
  const el = host.value
  if (!el) return
  const w = el.clientWidth || window.innerWidth
  const h = el.clientHeight || window.innerHeight

  renderer = new THREE.WebGLRenderer({ antialias: false, alpha: true, powerPreference: 'high-performance' })
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2))
  renderer.setSize(w, h, false)
  renderer.domElement.style.display = 'block'
  el.appendChild(renderer.domElement)

  scene = new THREE.Scene()
  camera = new THREE.PerspectiveCamera(52, w / h, 0.1, 3000)
  camera.position.set(0, 46, 160)

  controls = new CameraControls(camera, renderer.domElement)
  controls.dampingFactor = 0.07
  controls.draggingSmoothTime = 0.14
  controls.minDistance = 70
  controls.maxDistance = 420
  controls.minPolarAngle = Math.PI * 0.12
  controls.maxPolarAngle = Math.PI * 0.88
  controls.setLookAt(0, 46, 160, 0, 0, 0, false)

  // 后处理：Bloom(mipmapBlur) + 边缘色散（浅色版去掉暗角——
  // 白纸场景四角逐层压暗像脏污，观感比深色底差得多）
  composer = new EffectComposer(renderer, { multisampling: 0 })
  composer.addPass(new RenderPass(scene, camera))
  // 阈值 0.55 / 强度 0.9：浅色场景大面积亮部，只有最亮的核才允许开花
  const bloom = new BloomEffect({
    blendFunction: BlendFunction.ADD,
    mipmapBlur: true,
    luminanceThreshold: 0.55,
    luminanceSmoothing: 0.3,
    intensity: 0.9,
    radius: 0.7,
    levels: 7,
  })
  const chroma = new ChromaticAberrationEffect({
    blendFunction: BlendFunction.NORMAL,
    offset: new THREE.Vector2(0.0006, 0.0004),
    radialModulation: true,
    modulationOffset: 0.32,
  })
  composer.addPass(new EffectPass(camera, bloom, chroma))

  galaxy = new THREE.Group()
  scene.add(galaxy)

  coreGlow = new THREE.Sprite(new THREE.SpriteMaterial({
    map: makeGlowTexture('rgba(217,154,58,1)'),   // 浅底版：暖金核（原亮黄在白底上发灰）
    blending: THREE.NormalBlending,
    depthWrite: false, transparent: true, opacity: 0.5,
  }))
  coreGlow.scale.set(40, 40, 1)
  galaxy.add(coreGlow)

  buildDust()
  buildComets()
  buildGalaxy()

  ro = new ResizeObserver(resize)
  ro.observe(el)

  last = performance.now()
  raf = requestAnimationFrame(tick)
})

watch(() => props.movies, () => {
  if (!galaxy) return
  clearGalaxy()
  buildGalaxy()
})

// 切走视图 / 悬停 HUD 面板时收起解读卡，避免残影
watch(() => props.paused, (v) => { if (v) hideTip() })

onBeforeUnmount(() => {
  disposed = true
  if (raf) cancelAnimationFrame(raf)
  if (ro) ro.disconnect()
  clearGalaxy()
  clearArmLabels()
  for (const cm of comets) {
    scene.remove(cm.comet)
    cm.geo.dispose()
    cm.mat.dispose()
  }
  comets.length = 0
  if (coreGlow) { coreGlow.material.map?.dispose(); coreGlow.material.dispose() }
  if (dust) { dustGeo.dispose(); dustMat.dispose() }
  if (composer) composer.dispose?.()
  if (renderer) { renderer.dispose(); renderer.domElement.remove() }
})
</script>

<style scoped>
.galaxy-stage {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
}
/* 悬停解读卡（不抢画布事件；靠近右/下边缘时翻转方向） */
.galaxy-tip {
  position: absolute;
  z-index: 5;
  pointer-events: none;
  min-width: 210px;
  max-width: 300px;
  padding: 10px 14px;
  background: rgba(17, 27, 51, 0.93);
  backdrop-filter: blur(10px);
  -webkit-backdrop-filter: blur(10px);
  border: 1px solid rgba(255, 217, 160, 0.45);
  clip-path: polygon(10px 0, 100% 0, 100% calc(100% - 10px), calc(100% - 10px) 100%, 0 100%, 0 10px);
  transform: translate(14px, 14px);
}
.galaxy-tip--lx { transform: translate(calc(-100% - 14px), 14px); }
.galaxy-tip--ly { transform: translate(14px, calc(-100% - 14px)); }
.galaxy-tip--lx.galaxy-tip--ly { transform: translate(calc(-100% - 14px), calc(-100% - 14px)); }
.galaxy-tip__name { display: block; font-size: 13px; color: #FFFFFF; line-height: 1.45; }
.galaxy-tip__meta {
  display: block; margin-top: 4px; font-size: 11px; color: #FFD9A0;
  font-family: var(--u-font-tech); letter-spacing: .5px;
}
.galaxy-tip__note { display: block; margin-top: 4px; font-size: 10.5px; color: var(--u-text-2); }
</style>
