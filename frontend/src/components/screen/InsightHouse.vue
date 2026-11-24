<template>
  <!--
    ============================================================
    影评洞察馆 · 大厅（/screen 入口层）—— 手绘白描 3D 长廊 + 电影盒子
    ------------------------------------------------------------
    2026-11-04 改版：用户要「3D 效果、设计感、高级」，并指定参考
    itomdev.com 的白纸墨线走廊，且「中间做一个盒子，因为项目叫电影盒子」。
      · three.js 真透视长廊：白纸面 + 墨线勾边、木地板长线收束到消失点、
        尽头过曝白光出口（见 house3d.js）
      · 五扇白木门按三层 V 字纵深排布，门牌是挂在门楣的手绘木牌
      · 走廊正中央一只可开盖的 3D「电影盒子」
      · 手绘线稿云 / 树 / 草 / 猫点缀（itomdev 图 1）
      · 滚轮 = 沿长廊飞行穿越（相机 z 6 → -14），场景显式分四层：
        近景垂挂胶片/票根、中景五扇门与盒子、远景白化门与白光出口、
        空气层雾与逐道地面亮带；右侧深度刻度可点，直接跳到任一层
      · 鼠标环视、拖拽转头（松手回正）、点门飞入
      · 中文门牌用 DOM 按相机投影逐帧贴到门楣：字清晰、键盘可达、
        点击命中稳定（避开旧版 preserve-3d 命中测试静默失效的老坑）
    ------------------------------------------------------------
    ★ 2026-11-04 五次改版：用户「应该先打开电影盒子才能看到这些门」。
      参考站首屏是一张纸，纸撕开后访客才掉进手绘走廊。现在大厅两幕：
        ① 合盒 sealed：盖子扣死，整条走廊藏在一张白纸幕后，
           屏幕上只有盒子、刊头与手绘线稿；门牌/深度刻度/洞察卡全不出场
        ② 开封 open：点盒子（或滚轮 / 回车）→ 掀盖 → 盒内白光漫出 →
           DOM 撕纸层从中裂开 → 四层长廊与五扇门依次显现
      已开过盒后回大厅保持 open；「合上盒子」可重新体验开封。
      开盒进度 openP 由 rAF 单一插值，WebGL 纸幕、DOM 撕纸、门牌显隐
      共用它，保证「纸没撕开门不会露出来」。
    配色维持暖白纸 + 棕金点缀，不破坏 /screen 独立设计系统。
    窄屏不创建 WebGL 上下文（省显存），同样先开盒再见门。
    ============================================================
  -->
  <div
    ref="house"
    class="ih"
    :class="{
      'is-entering': entering, 'is-ready': ready, 'no-gl': flat,
      'is-sealed': phase === 'sealed', 'is-opening': phase === 'opening', 'is-open': phase === 'open',
      'is-revealed': revealed,
    }"
    :style="{
      '--ex': enterX, '--ey': enterY,
      '--flash': flash, '--tear': tear, '--tear-vis': tearVis,
    }"
    @pointerdown="onPointerDown"
    @pointermove="onPointerMove"
    @pointerup="onPointerUp"
    @pointerleave="onPointerLeave"
  >
    <!-- 真 3D 长廊（WebGL） -->
    <canvas ref="gl" class="ih__gl" aria-hidden="true" />
    <!-- 纸感叠层 -->
    <div class="ih__shade" aria-hidden="true" />

    <!-- ---------- 开封瞬间：盒内白光 + 一张纸从中间撕开（itomdev 首屏仪式） ---------- -->
    <div class="ih__flash" aria-hidden="true" />
    <div class="ih__tear ih__tear--top" aria-hidden="true" />
    <div class="ih__tear ih__tear--bot" aria-hidden="true" />

    <!-- ---------- 手绘线稿装饰（itomdev 图 1：云 / 树 / 草 / 猫） ---------- -->
    <svg class="ih__ink ih__ink--cloud" viewBox="0 0 240 90" aria-hidden="true">
      <path d="M22 64c-13 0-21-9-21-19 0-10 9-18 20-18 3-12 15-20 29-20 13 0 24 7 28 18 4-2 9-4 14-4 13 0 23 9 23 21 0 9-7 16-17 17z" />
      <path d="M150 55c-9 0-15-6-15-14 0-8 7-14 15-14 3-8 11-13 20-13 10 0 18 6 20 14 3-1 6-2 9-2 9 0 16 7 16 15 0 8-6 14-14 14z" />
    </svg>
    <svg class="ih__ink ih__ink--tree" viewBox="0 0 120 190" aria-hidden="true">
      <path d="M60 188V70" />
      <path d="M60 118c-14-6-24-18-27-34M60 100c13-6 22-18 25-33M60 150c-9-4-15-11-17-20" />
      <path d="M60 14c22 0 38 16 38 35 0 7-2 13-7 19 8 4 13 12 13 21 0 15-12 26-29 26-4 0-8-1-12-3-4 2-9 3-14 3-18 0-32-13-32-29 0-11 6-20 16-24-6-6-9-13-9-20 0-17 15-28 36-28z" />
    </svg>
    <svg class="ih__ink ih__ink--grass" viewBox="0 0 180 60" aria-hidden="true">
      <path d="M4 56c8-22 14-32 18-38M22 56c4-18 10-30 18-40M40 56c6-24 14-34 24-42M62 56c3-16 10-26 18-32M84 56c7-22 16-32 26-38M112 56c4-16 12-26 20-32M136 56c6-20 14-30 24-36" />
      <path d="M2 57h176" />
    </svg>
    <svg class="ih__ink ih__ink--cat" viewBox="0 0 90 120" aria-hidden="true">
      <path d="M24 44 20 14l20 12M66 44l4-30-20 12" />
      <path d="M22 46c0-16 10-26 23-26s23 10 23 26v22c0 18-10 30-23 30S22 86 22 68z" />
      <path d="M33 52h.1M57 52h.1" stroke-width="3" />
      <path d="M41 62l4 3 4-3M45 65v4M45 69c-3 4-8 3-10 0M45 69c3 4 8 3 10 0" />
      <path d="M28 76 8 70M28 82 6 84M62 76l20-6M62 82l22 2" />
      <path d="M68 96c18 4 20 18 8 22" />
    </svg>

    <!-- ---------- 手绘刊头 ---------- -->
    <header class="ih__masthead">
      <span class="ih__kicker">影评洞察馆 · THE INSIGHT ARCHIVE</span>
      <h1 v-if="phase === 'sealed'" class="ih__title">一只盒子，<br />装着五万条影评</h1>
      <h1 v-else class="ih__title">把五万条影评，<br />摊开成五间展厅</h1>
      <svg class="ih__rule" viewBox="0 0 260 14" aria-hidden="true"><path d="M4 8C40 3 80 12 120 7c40-5 80 4 136-1" /></svg>
      <p v-if="phase === 'sealed'" class="ih__lede">里面是五间展厅。先打开盒子。</p>
      <p v-else class="ih__lede">每一间，都是一种读法。</p>
      <p v-if="phase === 'sealed'" class="ih__ctrl">点盒子开封 · 或向下滚动</p>
      <p v-else class="ih__ctrl">滚轮向里走 · 拖拽环视 · 推门进入</p>
    </header>

    <!-- ---------- 五扇门：透明命中区贴「门板本身」，木牌只作展示 ----------
         用户要求「点门的中间开门，不是点上面的木板」：按钮由 project() 投影
         出门板屏幕矩形，木牌绝对定位在按钮上方且 pointer-events:none。 -->
    <div ref="doors" class="ih__doors">
      <button
        v-for="(r, i) in rooms"
        :key="r.key"
        class="ih__room"
        :class="{ 'is-active': hover === i }"
        type="button"
        :aria-label="`进入${r.zh}展厅`"
        @pointerenter="onDoorEnter(i)"
        @pointerleave="onDoorLeave(i)"
        @focus="onDoorEnter(i)"
        @blur="onDoorLeave(i)"
        @click="onDoorClick(r, i, $event)"
      >
        <span class="ih__door-cta" aria-hidden="true">推门进入 <i>→</i></span>
        <span class="ih__plaque">
          <span class="ih__sign-no">{{ String(i + 1).padStart(2, '0') }}</span>
          <b class="ih__zh">{{ r.zh }}</b>
          <span class="ih__desc">{{ r.desc }}</span>
          <span class="ih__go">进入展厅 <i>→</i></span>
        </span>
      </button>
    </div>

    <!-- 走廊海报是 WebGL 里的静态挂画（真实海报贴图常驻），
         不做 DOM 命中层、也不弹悬停卡：海报挂在哪里就在哪里显示。 -->

    <!-- ---------- 中央「电影盒子」：合盒时是唯一入口，打开后整条走廊显现 ---------- -->
    <button
      ref="boxBtn"
      class="ih__box"
      type="button"
      aria-label="打开电影盒子，进入影评洞察馆"
      @pointerenter="boxHover = 1"
      @pointerleave="boxHover = 0"
      @focus="boxHover = 1"
      @blur="boxHover = 0"
      @click="openBox"
    >
      <span class="ih__box-seal">封 · 五间展厅</span>
      <span class="ih__box-tag">✦ 打开电影盒子</span>
      <span class="ih__box-hint">点一下，或向下滚动</span>
    </button>

    <!-- 开封之后的两个小入口：随手抽一间展厅 / 合上盒子重看开封 -->
    <div class="ih__after">
      <button class="ih__after-btn" type="button" @click="randomRoom">✦ 随手抽一间</button>
      <button class="ih__after-btn ih__after-btn--quiet" type="button" @click="reclose">合上盒子</button>
    </div>

    <!-- ---------- 深度刻度：把 3D 走廊的四层变成看得见、点得到的导航 ---------- -->
    <nav class="ih__depth" aria-label="走廊深度">
      <!-- itomdev 同款撕纸锯齿描边：手绘纸片浮在 3D 空间之前 -->
      <svg class="ih__torn" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
        <path d="M 0 0 L 8 1 L 16 0 L 24 1 L 32 0 L 40 1 L 48 0 L 56 1 L 64 0 L 72 1 L 80 0 L 88 1 L 100 0 L 99 8 L 100 16 L 98 24 L 100 32 L 99 40 L 100 48 L 98 56 L 100 64 L 99 72 L 100 80 L 98 88 L 100 100 L 88 99 L 80 100 L 72 98 L 64 100 L 56 99 L 48 100 L 40 98 L 32 100 L 24 99 L 16 100 L 8 98 L 0 99 L 1 88 L 0 80 L 2 72 L 0 64 L 1 56 L 0 48 L 2 40 L 0 32 L 1 24 L 0 16 L 2 8 L 0 0 Z" />
      </svg>
      <span class="ih__depth-cap">深 度</span>
      <div class="ih__depth-rail">
        <span class="ih__depth-line" :style="{ '--p': depthProgress + '%' }" />
        <button
          v-for="(label, i) in depthLabels"
          :key="label"
          class="ih__depth-dot"
          :class="{ 'is-past': i <= depthIndex, 'is-on': i === depthIndex }"
          type="button"
          :aria-label="`走到${label}`"
          :aria-current="i === depthIndex ? 'step' : undefined"
          @click="goDepth(i)"
        >
          <span class="ih__depth-pip" />
          <span class="ih__depth-name">{{ label }}</span>
        </button>
      </div>
      <span class="ih__depth-now">{{ depthLabels[depthIndex] }}</span>
    </nav>

    <!-- ---------- 馆长洞察（主编精选） ---------- -->
    <div class="ih__stories">
      <HallInsights :cards="cards" @enter="$emit('enter', $event)" />
    </div>

    <!-- 纸纹颗粒 -->
    <div class="ih__grain" aria-hidden="true" />
  </div>
</template>

<script setup>
// ============================================================
// 大厅只负责「选展厅」。相机与几何在 house3d.js，这里做交互与门牌投影。
// 状态量全部是普通变量（非响应式），rAF 里直接改 DOM，避免每帧触发 Vue 更新。
// ============================================================
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import HallInsights from './HallInsights.vue'
import { createHouse3D, DEPTH_LAYERS } from './house3d.js'

const props = defineProps({
  /** 五间展厅：与 UniverseScreen 的 VIEWS 同源 */
  rooms: { type: Array, default: () => [] },
  /** 馆长洞察卡（UniverseScreen 从 /insights/story 取，向下传） */
  cards: { type: Array, default: () => [] },
  /** 已经开过盒（回大厅 / 深链进展厅再返回时不再重复开封） */
  startOpen: { type: Boolean, default: false },
  /** 走廊挂画片单：/insights/hall-posters 的真实聚合结果，直接贴到 3D 挂画上 */
  posters: { type: Array, default: () => [] },
})
const emit = defineEmits(['enter', 'open', 'close'])

const house = ref(null)
const gl = ref(null)
const doors = ref(null)
const boxBtn = ref(null)
const ready = ref(false)
const entering = ref(false)
const flat = ref(false)          // WebGL 不可用 / 窄屏 → 平面降级
const hover = ref(-1)
const boxHover = ref(0)
const enterX = ref('50%')
const enterY = ref('50%')
const depthIndex = ref(0)
const depthProgress = ref(0)
const depthLabels = ['入口', '门廊', '回廊', '深处']

/* ---------- 开封两幕：sealed → opening → open ---------- */
const phase = ref(props.startOpen ? 'open' : 'sealed')
const revealed = ref(!!props.startOpen)   // 纸已撕开：门牌 / 刻度 / 洞察卡从此出场
const flash = ref(0)             // 盒内白光，0→1→0
const tear = ref(0)              // 纸片撕开位移 0→1
const tearVis = ref(0)           // 撕纸层可见度
const openP = { v: props.startOpen ? 1 : 0, t: props.startOpen ? 1 : 0 }

const tints = computed(() => props.rooms.map((r) => r.tint || '#A67C2E'))
const OPEN_MS = 640

/* ---------- 交互状态（rAF 用，非响应式） ---------- */
const look = { x: 0, y: 0, tx: 0, ty: 0 }
const walk = { v: 0, t: 0 }
const fly = { v: 0, t: 0, idx: -1, x: 0 }
let dragging = false
let dragMoved = false
let dragStart = { x: 0, y: 0 }
let suppressClick = false
let scene = null
let raf = 0
let ro = null
let startedAt = 0
let lastFrameAt = 0
let timer = 0

const clamp = (v, a, b) => Math.min(b, Math.max(a, v))

function onWheel(e) {
  if (entering.value) return
  e.preventDefault()
  // 合盒时滚轮的第一下就是「开封」（参考站 scroll to fly through my story）
  if (phase.value === 'sealed') { if (e.deltaY > 0) openBox(); return }
  if (!revealed.value || flat.value) return
  walk.t = clamp(walk.t + e.deltaY * 0.0009, 0, 1)
}
/** 键盘也能开封：Tab 到盒子按回车，或直接按回车 / 空格 */
function onKeyDown(e) {
  if (phase.value !== 'sealed' || entering.value) return
  if (e.key === 'Enter' || e.key === ' ' || e.key === 'Spacebar') {
    e.preventDefault()
    openBox()
  }
}
function onPointerDown(e) {
  dragging = true
  dragMoved = false
  dragStart = { x: e.clientX, y: e.clientY }
}
function onPointerMove(e) {
  if (!house.value) return
  const r = house.value.getBoundingClientRect()
  if (dragging) {
    const dx = e.clientX - dragStart.x
    const dy = e.clientY - dragStart.y
    if (Math.abs(dx) + Math.abs(dy) > 6) dragMoved = true
    look.tx = clamp(dx / (r.width * 0.32), -1, 1)
    look.ty = clamp(-dy / (r.height * 0.42), -1, 1)
  } else {
    // 静止时鼠标带来轻微环视（A24 式视差），不是全屏转头
    look.tx = clamp(((e.clientX - r.left) / r.width * 2 - 1) * 0.55, -0.7, 0.7)
    look.ty = clamp(-((e.clientY - r.top) / r.height * 2 - 1) * 0.42, -0.6, 0.6)
  }
}
function onPointerUp() {
  dragging = false
  if (dragMoved) {
    suppressClick = true
    setTimeout(() => { suppressClick = false }, 60)
  }
  look.tx = 0
  look.ty = 0
}
function onPointerLeave() {
  dragging = false
  look.tx = 0
  look.ty = 0
}
/** 点深度刻度：飞到走廊对应层（与滚轮共用同一套平滑插值） */
function goDepth(i) {
  if (flat.value || entering.value || !revealed.value) return
  walk.t = clamp(i / (DEPTH_LAYERS - 1), 0, 1)
}
function onDoorEnter(i) { if (revealed.value) hover.value = i }
function onDoorLeave(i) { if (hover.value === i) hover.value = -1 }

/** 打开电影盒子：掀盖 → 撕纸 → 四层长廊与五扇门显现（不再直接跳展厅） */
function openBox() {
  if (suppressClick || entering.value || phase.value !== 'sealed') return
  phase.value = 'opening'
  openP.t = 1
}
/** 合上盒子：回到首屏，随时可以重新体验开封 */
function reclose() {
  if (entering.value || phase.value !== 'open') return
  walk.t = 0; walk.v = 0
  depthIndex.value = 0
  depthProgress.value = 0
  phase.value = 'opening'
  openP.t = 0
}
/** 开盒之后的「随便看看」：随机挑一间展厅（原盒子的盲盒心智保留） */
function randomRoom() {
  if (entering.value || !revealed.value || !props.rooms.length) return
  const i = Math.floor(Math.random() * props.rooms.length)
  enter(props.rooms[i], i, null)
}

function onDoorClick(room, i, ev) {
  if (suppressClick || !revealed.value) return  // 拖拽转头后浏览器仍会派发一次 click
  enter(room, i, ev)
}

function enter(room, i, ev) {
  if (entering.value) return
  const el = house.value
  const btn = ev?.currentTarget
  if (el && btn) {
    const hr = el.getBoundingClientRect()
    const br = btn.getBoundingClientRect()
    enterX.value = `${(((br.left + br.width / 2 - hr.left) / hr.width) * 100).toFixed(2)}%`
    enterY.value = `${(((br.top + br.height / 2 - hr.top) / hr.height) * 100).toFixed(2)}%`
  }
  hover.value = i
  fly.idx = i
  fly.x = Math.sign((props.rooms.length ? [0, 1, 0, 1, 0][i] : 0) - 0.5) || 0
  fly.t = 1
  entering.value = true
  timer = setTimeout(() => emit('enter', room.key), OPEN_MS - 140)
}

/* ---------- 渲染循环 ---------- */
function frame(now) {
  const t = (now - startedAt) / 1000
  // 按真实时间插值：无头浏览器 / 软件 WebGL 帧率可能只有 15fps，
  // 用「每帧固定系数」会让开封动画拖到 3 秒以上，纸还没撕开门却已可点。
  // 按真实时间插值：无头浏览器 / 软件 WebGL 帧率可能只有 10~15fps。
  // dt 上限必须放到 0.12s（≈8fps），否则低帧率下 1.5s 的开封动画
  // 会被拉长到 3s，回归里「点盒子完成开封」会偶发超时。
  const dt = lastFrameAt ? Math.min(0.12, (now - lastFrameAt) / 1000) : 0.016
  lastFrameAt = now
  // 线性 1.5s 分幕（指数收敛会让撕纸只闪 0.1 秒，肉眼读不到）：
  //   0.00–0.30 掀盖 → 0.20–0.60 纸从中撕开 + 白光漫出
  //   → 0.60–0.84 走廊显现 → 0.84 五扇门牌出场 → 1.00 完成
  const step = dt / 1.5
  openP.v = openP.t > openP.v
    ? Math.min(openP.t, openP.v + step)
    : Math.max(openP.t, openP.v - step)

  // 开封进度：单一 0→1 插值。WebGL 纸幕透明度、DOM 撕纸/白闪、门牌显隐
  // 全部读它，因此「纸没撕开门不会露出来」是结构上保证的，不靠 setTimeout 对齐。
  const o = openP.v
  const isRevealed = o > 0.84
  if (isRevealed !== revealed.value) revealed.value = isRevealed
  if (openP.t === 1 && o > 0.995 && phase.value !== 'open') {
    openP.v = 1; phase.value = 'open'; emit('open')
  } else if (openP.t === 0 && o < 0.005 && phase.value !== 'sealed') {
    openP.v = 0; phase.value = 'sealed'; emit('close')
  }
  const cl = (x) => Math.min(1, Math.max(0, x))
  flash.value = Math.sin(cl((o - 0.16) / 0.64) * Math.PI) * 0.92
  tear.value = cl((o - 0.26) / 0.52)
  tearVis.value = cl((o - 0.2) / 0.1) * (1 - cl((o - 0.56) / 0.34) * 0.94)

  // 按真实时间插值：无头 / 软件 WebGL 帧率可能只有 15fps，固定系数
  // 会让滚轮飞行「走不到位」（冷启动首跑深度刻度卡在 1 层）。
  const kWalk = 1 - Math.exp(-dt * 5.2)
  const kFly = 1 - Math.exp(-dt * 4.6)
  look.x += (look.tx - look.x) * kWalk
  look.y += (look.ty - look.y) * kWalk
  walk.v += (walk.t - walk.v) * kWalk
  fly.v += (fly.t - fly.v) * kFly

  // 深度刻度是响应式 ref，只在跨层 / 进度变化 ≥2% 时写，
  // 避免 rAF 每帧触发 Vue 更新（其余动画状态全是普通变量）
  const di = Math.min(DEPTH_LAYERS - 1, Math.round(walk.v * (DEPTH_LAYERS - 1)))
  if (di !== depthIndex.value) depthIndex.value = di
  const dp = Math.round(walk.v * 100)
  if (Math.abs(dp - depthProgress.value) >= 2) depthProgress.value = dp

  if (scene) {
    scene.tick({
      time: t,
      open: o,
      lookX: look.x,
      lookY: look.y,
      walk: walk.v,
      fly: fly.v,
      flyIndex: fly.idx,
      flyX: fly.x,
      hover: hover.value,
      boxHover: boxHover.value,
    })
    const el = house.value
    const btns = doors.value?.children
    if (el && btns) {
      const w = el.clientWidth, h = el.clientHeight
      const showDoors = isRevealed         // 纸已撕开（tear 位移到 0.78 完成）才放门牌出来
      for (let i = 0; i < btns.length; i++) {
        const p = scene.project(i, w, h)
        const b = btns[i]
        b.style.setProperty('--px', `${p.x.toFixed(1)}px`)
        b.style.setProperty('--py', `${p.y.toFixed(1)}px`)
        b.style.setProperty('--s', p.s.toFixed(3))
        b.style.setProperty('--dw', `${p.w.toFixed(1)}px`)
        b.style.setProperty('--dh', `${p.h.toFixed(1)}px`)
        b.classList.toggle('is-hidden', !showDoors || !p.visible)
      }
      if (boxBtn.value) {
        const b = scene.projectBox(w, h)
        boxBtn.value.style.setProperty('--px', `${b.x.toFixed(1)}px`)
        boxBtn.value.style.setProperty('--py', `${b.y.toFixed(1)}px`)
        boxBtn.value.style.setProperty('--bw', `${b.w.toFixed(1)}px`)
        boxBtn.value.style.setProperty('--bh', `${b.h.toFixed(1)}px`)
        boxBtn.value.classList.toggle('is-hidden', !b.visible)
      }
    }
  } else if (doors.value) {
    // 平面降级没有逐帧投影：直接用开封阶段门控，合盒时同样看不到门
    const hide = !isRevealed
    for (const b of doors.value.children) b.classList.toggle('is-hidden', hide)
    boxBtn.value?.classList.toggle('is-hidden', !hide)
  }
  raf = requestAnimationFrame(frame)
}

onMounted(() => {
  requestAnimationFrame(() => { ready.value = true })
  const el = house.value
  if (!el) return

  const small = window.matchMedia('(max-width: 900px)').matches
  if (!small && gl.value) {
    try {
      scene = createHouse3D(gl.value, tints.value, props.posters)
      scene.resize(el.clientWidth, el.clientHeight)
      ro = new ResizeObserver(() => scene?.resize(el.clientWidth, el.clientHeight))
      ro.observe(el)
    } catch (err) {
      // WebGL 建不起来也要能用：退化成平面门牌墙，不白屏
      console.warn('[insight-house] WebGL 不可用，降级为平面大厅', err)
      scene = null
    }
  }
  if (!scene) flat.value = true
  // 片单是异步接口：到达后只替换海报纹理，不重建 WebGL 上下文（省显存）
  watch(() => props.posters, (list) => { if (list?.length) scene?.setPosters(list) })

  el.addEventListener('wheel', onWheel, { passive: false })
  window.addEventListener('keydown', onKeyDown)
  startedAt = performance.now()
  raf = requestAnimationFrame(frame)
})

onUnmounted(() => {
  cancelAnimationFrame(raf)
  clearTimeout(timer)
  house.value?.removeEventListener('wheel', onWheel)
  window.removeEventListener('keydown', onKeyDown)
  ro?.disconnect()
  scene?.dispose()
  scene = null
})

defineExpose({
  reset() {
    entering.value = false
    fly.t = 0; fly.v = 0
    // 回大厅一律从入口重新开始：停在深处时五扇门都在相机背后，门牌会全隐藏
    walk.t = 0; walk.v = 0
    depthIndex.value = 0
    depthProgress.value = 0
  },
})
</script>

<style scoped>
.ih {
  --paper: #FBF7EE;
  --ink: #3A2E20;
  --ink-line: #4A3C2C;
  --text-2: #6F5C44;
  --gold: #A67C2E;
  --orange: #C2410C;
  position: absolute;
  inset: 0;
  overflow: hidden;
  background: var(--paper);
  color: var(--ink);
  font-family: var(--u-font-cn, 'Source Han Sans SC', 'PingFang SC', 'Microsoft YaHei', sans-serif);
  opacity: 0;
  transform: scale(1.02);
  transition: opacity 0.5s ease, transform 0.7s cubic-bezier(0.22, 1, 0.36, 1);
  cursor: grab;
}
.ih:active { cursor: grabbing; }
.ih.is-ready { opacity: 1; transform: scale(1); }
.ih.is-entering {
  transform-origin: var(--ex, 50%) var(--ey, 50%);
  transform: scale(2.6);
  opacity: 0;
  transition: transform 0.64s cubic-bezier(0.5, 0, 0.9, 0.4), opacity 0.5s ease 0.12s;
  pointer-events: none;
}

/* ---------- 3D 画布 + 纸感叠层 ---------- */
.ih__gl { position: absolute; inset: 0; z-index: 0; display: block; width: 100%; height: 100%; }
.ih.no-gl .ih__gl { display: none; }
.ih__shade {
  position: absolute; inset: 0; z-index: 1; pointer-events: none;
  background:
    radial-gradient(125% 82% at 50% 42%, transparent 56%, rgba(96, 66, 34, .07) 100%),
    linear-gradient(180deg, rgba(255, 253, 247, .48) 0%, transparent 20%, transparent 74%, rgba(251, 247, 238, .78) 100%);
}
/* 合盒首屏：把纸幕之外的透视檐线/地板线往纸白里压一压，
   视线只落在盒子上，读起来才是「一张纸上的盒子」而不是半截走廊 */
.ih.is-sealed .ih__shade {
  background:
    radial-gradient(78% 72% at 52% 52%, transparent 62%, rgba(251, 247, 238, .55) 100%),
    linear-gradient(180deg, rgba(255, 253, 247, .4) 0%, transparent 28%, transparent 72%, rgba(251, 247, 238, .6) 100%);
}
.ih.no-gl {
  background:
    linear-gradient(118deg, rgba(255, 255, 255, .8), transparent 22%, rgba(120, 100, 70, .08) 46%, transparent 62%, rgba(255, 255, 255, .7)),
    linear-gradient(160deg, #FDFBF5 0%, #F8F3E8 58%, #F1E9D8 100%);
}
.ih__grain {
  position: absolute; inset: 0; z-index: 8; pointer-events: none; opacity: .26;
  background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='200' height='200'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2' stitchTiles='stitch'/%3E%3CfeColorMatrix type='matrix' values='0 0 0 0 0.2 0 0 0 0 0.16 0 0 0 0 0.1 0 0 0 0.04 0'/%3E%3C/filter%3E%3Crect width='200' height='200' filter='url(%23n)'/%3E%3C/svg%3E");
}

/* 走廊挂画全部在 WebGL 里（真实海报静态常驻），大厅不再叠 DOM 命中层与悬停卡，
   避免任何透明层抢走门板 / 盒子的点击（preserve-3d 命中测试老雷）。 */

/* ---------- 开封：盒内白光漫出 + 一整张纸从中间撕开（itomdev 首屏仪式） ---------- */
.ih__flash {
  position: absolute; inset: 0; z-index: 7; pointer-events: none;
  opacity: var(--flash, 0);
  background: radial-gradient(58% 58% at 50% 56%,
    rgba(255, 255, 255, .98) 0%, rgba(255, 247, 225, .9) 34%, rgba(255, 240, 205, 0) 78%);
}
.ih__tear {
  position: absolute; left: -2%; width: 104%; height: 52%; z-index: 7;
  pointer-events: none; opacity: var(--tear-vis, 0);
  background:
    repeating-linear-gradient(93deg, rgba(120, 88, 50, .035) 0 2px, transparent 2px 12px),
    linear-gradient(168deg, #FFFCF4, #F2E7D1);
  box-shadow: 0 10px 26px rgba(74, 60, 44, .16);
  will-change: transform;
}
/* 撕口是手绘锯齿，不是直线；两片纸分别向上/下掀走 */
.ih__tear--top {
  top: 0;
  clip-path: polygon(0 0, 100% 0, 100% 92%, 96% 96%, 92% 91%, 88% 97%, 84% 92%, 80% 96%, 76% 90%, 72% 97%, 68% 92%, 64% 96%, 60% 91%, 56% 97%, 52% 92%, 48% 96%, 44% 90%, 40% 97%, 36% 92%, 32% 96%, 28% 91%, 24% 97%, 20% 92%, 16% 96%, 12% 90%, 8% 97%, 4% 92%, 0 96%);
  transform: translateY(calc(-102% * var(--tear, 0)));
}
.ih__tear--bot {
  bottom: 0;
  clip-path: polygon(0 8%, 4% 4%, 8% 9%, 12% 3%, 16% 8%, 20% 4%, 24% 9%, 28% 3%, 32% 8%, 36% 4%, 40% 9%, 44% 3%, 48% 8%, 52% 4%, 56% 9%, 60% 3%, 64% 8%, 68% 4%, 72% 9%, 76% 3%, 80% 8%, 84% 4%, 88% 9%, 92% 3%, 96% 8%, 100% 4%, 100% 100%, 0 100%);
  transform: translateY(calc(102% * var(--tear, 0)));
}

/* ---------- 合盒阶段：门 / 深度刻度 / 洞察卡 / 开封后按钮一律不出场 ----------
   is-revealed 由开盒进度（纸已撕开）驱动，不是 phase，避免「门牌已放行但 CSS 还压着」。 */
.ih:not(.is-revealed) .ih__depth,
.ih:not(.is-revealed) .ih__stories,
.ih:not(.is-revealed) .ih__after { opacity: 0; pointer-events: none; }
.ih:not(.is-revealed) .ih__room { opacity: 0 !important; pointer-events: none !important; }
.ih.is-revealed .ih__box { opacity: 0; pointer-events: none; }

/* ---------- 手绘线稿装饰（纯 SVG，墨线白描，不吃点击） ---------- */
.ih__ink {
  position: absolute; z-index: 2; pointer-events: none;
  fill: none; stroke: var(--ink-line); stroke-width: 2.1;
  stroke-linecap: round; stroke-linejoin: round;
  opacity: .52;
}
.ih__ink path { vector-effect: non-scaling-stroke; }
.ih__ink--cloud { width: clamp(150px, 19vw, 270px); top: 9%; right: 14%; opacity: .38; }
.ih__ink--tree { width: clamp(90px, 11vw, 160px); left: 1.2%; top: 27%; }
.ih__ink--grass { width: clamp(120px, 15vw, 210px); left: 4%; bottom: 26%; opacity: .45; }
.ih__ink--cat { width: clamp(58px, 6vw, 88px); right: 20%; bottom: 25%; opacity: .6; }

/* ---------- 刊头 ---------- */
.ih__masthead {
  position: absolute; z-index: 4;
  left: clamp(24px, 4vw, 70px); top: 22px;
  max-width: 430px; pointer-events: none;
  padding: 14px 20px 16px;
  /* 半透明纸卡：墙上的透视檐线不会横切标题 */
  background: linear-gradient(168deg, rgba(255, 253, 247, .9), rgba(251, 247, 238, .76));
  /* 毛玻璃 + 双层投影：把刊头明确推到 3D 长廊「之前」，形成 UI 浮层 */
  backdrop-filter: blur(6px);
  border-left: 2px solid rgba(166, 124, 46, .55);
  border-radius: 2px 12px 3px 10px / 10px 3px 12px 2px;
  box-shadow: 3px 4px 0 rgba(74, 60, 44, .14), 0 14px 34px rgba(74, 44, 20, .1);
}
.ih__kicker {
  display: inline-block;
  font-family: var(--u-font-tech, 'Orbitron', sans-serif);
  font-size: 10.5px; letter-spacing: .3em; color: #8B5E1C;
  text-transform: uppercase; margin-bottom: 8px; font-weight: 700;
}
.ih__title {
  margin: 0;
  font-family: "Kaiti SC", KaiTi, STKaiti, Georgia, "Songti SC", serif;
  font-weight: 700; font-size: clamp(24px, 2.9vw, 38px);
  line-height: 1.12; letter-spacing: .01em; color: #241B12;
}
.ih__rule {
  display: block; width: clamp(150px, 20vw, 260px); height: 13px;
  margin: 7px 0 5px; color: var(--orange);
}
.ih__rule path { fill: none; stroke: currentColor; stroke-width: 2; stroke-linecap: round; }
.ih__lede {
  margin: 0; max-width: 560px;
  font-family: "Kaiti SC", KaiTi, STKaiti, Georgia, serif;
  font-size: clamp(11px, 1vw, 14px); line-height: 1.5; color: #5C4A34;
}
.ih__ctrl {
  margin: 10px 0 0; font-family: var(--u-font-tech, 'Orbitron', sans-serif);
  font-size: 10px; letter-spacing: .14em; color: #8B5E1C; font-weight: 700;
}
.ih__ctrl::before { content: '✦'; margin-right: 7px; color: var(--orange); }

/* ---------- 门牌（DOM 覆盖在 3D 门面上） ---------- */
.ih__doors { position: absolute; inset: 0; z-index: 3; pointer-events: none; }
.ih__room {
  position: absolute;
  left: var(--px, 50%); top: var(--py, 50%);
  /* 宽高由 house3d.project() 投影出的门板矩形给出，命中区 = 门板本身 */
  width: max(38px, var(--dw, 152px));
  height: max(56px, var(--dh, 200px));
  padding: 0; margin: 0;
  background: none; border: 0; color: inherit; font-family: inherit;
  cursor: pointer; pointer-events: auto;
  transform: translate(-50%, -50%);
  transform-origin: center center;
  transition: opacity .3s ease;
  -webkit-tap-highlight-color: transparent;
}
/* 门板中央：hover 才浮出的虚线框 + 推门提示，把「点这里」说清楚 */
.ih__room::before {
  content: ''; position: absolute; inset: 4% 10%;
  border: 1.5px dashed rgba(139, 94, 28, 0);
  border-radius: 3px 14px 3px 12px / 12px 3px 14px 3px;
  background: rgba(255, 246, 220, 0);
  transition: border-color .25s ease, background .25s ease;
}
.ih__room:hover::before,
.ih__room.is-active::before,
.ih__room:focus-visible::before {
  border-color: rgba(139, 94, 28, .55);
  background: rgba(255, 246, 220, .16);
}
.ih__door-cta {
  position: absolute; left: 50%; top: 50%;
  transform: translate(-50%, -50%) scale(.9);
  display: inline-flex; align-items: center; gap: 5px;
  white-space: nowrap; padding: 6px 12px; border-radius: 25px;
  font-size: 10px; font-weight: 700; letter-spacing: .08em;
  color: #FFF6E9; background: linear-gradient(160deg, #A0522D, #8B4513);
  box-shadow: 2px 3px 0 rgba(74, 60, 44, .3);
  opacity: 0; pointer-events: none;
  transition: opacity .25s ease, transform .25s ease;
}
.ih__room:hover .ih__door-cta,
.ih__room.is-active .ih__door-cta,
.ih__room:focus-visible .ih__door-cta {
  opacity: 1; transform: translate(-50%, -50%) scale(1);
}
.ih__door-cta i { font-style: normal; }
.ih__room.is-hidden { opacity: 0; pointer-events: none; }
.ih__room:focus-visible { outline: 2px dashed var(--orange); outline-offset: 6px; }
.ih__plaque {
  /* ★ 木牌只作展示：挂在门楣（按钮上沿之外），不可点击 */
  position: absolute; left: 50%; bottom: calc(100% + 9px + var(--lift, 0px));
  /* ★ 必须给显式宽度：父按钮是投影出的窄门板（远门仅 38px），
     绝对定位元素不写 width 会被 containing block 挤成竖条 */
  width: 152px;
  transform: translateX(-50%) scale(var(--s, 1));
  transform-origin: bottom center;
  pointer-events: none;
  display: flex; flex-direction: column; align-items: center;
  gap: 1px; padding: 13px 11px 10px;
  background:
    repeating-linear-gradient(92deg, rgba(120, 88, 50, .055) 0 2px, transparent 2px 11px),
    linear-gradient(172deg, #FFFCF3, #F2E5CB);
  border: 1.8px solid rgba(74, 60, 44, .8);
  border-radius: 3px 15px 4px 13px / 13px 4px 15px 3px;
  box-shadow: 3px 4px 0 rgba(74, 60, 44, .24), 0 10px 22px rgba(74, 44, 20, .1);
  transition: transform .28s cubic-bezier(.22, 1, .36, 1), box-shadow .28s ease, border-color .28s ease;
}
/* 两枚挂钉：让木牌看起来真的钉在门楣上 */
.ih__plaque::before,
.ih__plaque::after {
  content: ''; position: absolute; top: 4px; width: 5px; height: 5px;
  border-radius: 50%; background: #A67C2E;
  box-shadow: inset 0 -1px 1px rgba(74, 44, 20, .5);
}
.ih__plaque::before { left: 10px; }
.ih__plaque::after { right: 10px; }
.ih__room.is-active .ih__plaque,
.ih__room:hover .ih__plaque {
  transform: translateX(-50%) translateY(-5px) rotate(-1.4deg) scale(var(--s, 1));
  border-color: var(--orange);
  box-shadow: 5px 7px 0 rgba(139, 69, 19, .28), 0 18px 30px rgba(74, 44, 20, .2);
}
.ih__sign-no {
  position: absolute; left: 8px; top: 6px;
  font-family: Georgia, "Times New Roman", serif; font-size: 10px; font-weight: 700;
  letter-spacing: .04em; color: var(--gold);
}
.ih__zh {
  font-family: "Kaiti SC", KaiTi, STKaiti, Georgia, serif;
  font-size: 16px; font-weight: 700; color: #241B12; letter-spacing: .02em;
  line-height: 1.25; margin-top: 5px;
}
.ih__desc {
  font-size: 10px; line-height: 1.35; color: var(--text-2);
  text-align: center; max-width: 132px;
}
.ih__go {
  margin-top: 5px; display: inline-flex; align-items: center; gap: 5px;
  font-family: var(--u-font-tech, 'Orbitron', sans-serif);
  font-size: 9px; letter-spacing: .1em; color: var(--gold); font-weight: 700;
}
.ih__go i { font-style: normal; transition: transform .2s ease; }
.ih__room.is-active .ih__go, .ih__room:hover .ih__go { color: var(--orange); }
.ih__room.is-active .ih__go i, .ih__room:hover .ih__go i { transform: translateX(3px); }

/* 纵深 LOD：远处三扇门的木牌收成紧凑小牌，避免三块牌子挤在消失点；
   悬停时展开说明，信息不丢（回归脚本只依赖 .ih__zh 与点击） */
/* 远处三扇门收束到消失点，木牌按纵深分层上提，避免三块牌子叠成一团 */
.ih__room:nth-child(3) { --lift: 16px; }
.ih__room:nth-child(4) { --lift: 32px; }
.ih__room:nth-child(5) { --lift: 48px; }
.ih__room:nth-child(n+3) .ih__plaque { width: 132px; padding: 9px 9px 7px; }
.ih__room:nth-child(n+3) .ih__zh { font-size: 15px; }
.ih__room:nth-child(n+3) .ih__desc { display: none; }
.ih__room:nth-child(n+3) .ih__go { margin-top: 2px; font-size: 8px; }
.ih__room:nth-child(n+3).is-active .ih__desc,
.ih__room:nth-child(n+3):hover .ih__desc { display: block; }

/* ---------- 中央电影盒子：合盒时是首屏唯一入口，DOM 命中层贴在 3D 盒身上 ---------- */
.ih__box {
  position: absolute; z-index: 4;
  left: var(--px, 50%); top: var(--py, 62%);
  /* 命中区由 house3d.projectBox() 按俯视透视投影出的盒身矩形给出 */
  width: max(160px, var(--bw, 320px));
  height: max(120px, var(--bh, 220px));
  transform: translate(-50%, -50%);
  background: none; border: 0; padding: 0; margin: 0;
  cursor: pointer; pointer-events: auto;
  -webkit-tap-highlight-color: transparent;
}
/* 合盒特写：命中区随 3D 盒身缩放，整只盒子都能点 */
.ih.is-sealed .ih__box { opacity: 1; }
.ih__box.is-hidden { opacity: 0; pointer-events: none; }
.ih__box:focus-visible { outline: 2px dashed var(--orange); outline-offset: 4px; }
/* 封条：斜贴在盒盖与盒身之间，开封时被撕纸动画带走 */
.ih__box-seal {
  position: absolute; left: 30%; top: 0%;
  transform: translate(-50%, -50%) rotate(-4deg);
  padding: 9px 22px; white-space: nowrap;
  font-family: "Kaiti SC", KaiTi, STKaiti, Georgia, serif;
  font-size: clamp(14px, 1.5vw, 20px); font-weight: 700; letter-spacing: .22em;
  color: #6B4A22;
  background: repeating-linear-gradient(91deg, rgba(166, 124, 46, .09) 0 2px, transparent 2px 9px), #FFF6DF;
  border: 1.5px dashed rgba(139, 94, 28, .7);
  border-radius: 2px 9px 3px 8px / 8px 3px 9px 2px;
  box-shadow: 2px 3px 0 rgba(74, 60, 44, .2);
  opacity: 0; transition: opacity .35s ease;
}
.ih.is-sealed .ih__box-seal { opacity: 1; }
.ih__box-tag {
  position: absolute; left: 50%; bottom: -6px; transform: translate(-50%, 100%);
  white-space: nowrap; padding: 9px 20px;
  font-family: var(--u-font-tech, 'Orbitron', sans-serif);
  font-size: 11px; letter-spacing: .1em; font-weight: 700;
  color: #FFF6E9;
  background: linear-gradient(160deg, #A0522D, #8B4513);
  border-radius: 25px;
  box-shadow: 2px 3px 0 rgba(74, 60, 44, .3);
  opacity: 0; transition: opacity .25s ease, transform .25s ease;
}
.ih.is-sealed .ih__box-tag,
.ih__box:hover .ih__box-tag,
.ih__box:focus-visible .ih__box-tag { opacity: 1; transform: translate(-50%, calc(100% + 4px)); }
.ih__box-hint {
  position: absolute; left: 50%; bottom: -54px; transform: translateX(-50%);
  white-space: nowrap; padding: 4px 11px; border-radius: 20px;
  background: rgba(255, 252, 244, .94);
  box-shadow: 1px 2px 0 rgba(74, 60, 44, .16);
  font-size: 10.5px; letter-spacing: .1em; color: #8B5E1C;
  opacity: 0; transition: opacity .3s ease;
}
.ih.is-sealed .ih__box-hint { opacity: 1; }

/* ---------- 开封后的两个小入口 ----------
   顶栏「导览图」按钮在 top:84px / right:24px（UniverseScreen），
   这一组从 140px 起，避免两个胶囊叠在一起把「随手抽一间」吃掉。 */
.ih__after {
  position: absolute; z-index: 6; right: 20px; top: 140px;
  display: flex; flex-direction: column; align-items: flex-end; gap: 8px;
  pointer-events: auto; transition: opacity .35s ease;
}
.ih__after-btn {
  padding: 8px 15px; border: 0; border-radius: 25px;
  font-family: inherit; font-size: 11px; font-weight: 700; letter-spacing: .06em;
  color: #FFF6E9; background: linear-gradient(160deg, #A0522D, #8B4513);
  box-shadow: 2px 3px 0 rgba(74, 60, 44, .26);
  cursor: pointer; -webkit-tap-highlight-color: transparent;
  transition: transform .2s ease, box-shadow .2s ease;
}
.ih__after-btn:hover { transform: translateY(-2px); box-shadow: 3px 5px 0 rgba(74, 60, 44, .3); }
.ih__after-btn:focus-visible { outline: 2px dashed var(--orange); outline-offset: 3px; }
.ih__after-btn--quiet {
  color: #6B4A22; background: rgba(255, 252, 244, .92);
  border: 1.5px solid rgba(139, 94, 28, .55);
}

/* ---------- 平面降级：门牌按静态坐标铺开 ---------- */
.ih.no-gl .ih__room:nth-child(1) { --px: 16%; --py: 40%; --s: 1; }
.ih.no-gl .ih__room:nth-child(2) { --px: 34%; --py: 57%; --s: 1; }
.ih.no-gl .ih__room:nth-child(3) { --px: 52%; --py: 40%; --s: 1; }
.ih.no-gl .ih__room:nth-child(4) { --px: 70%; --py: 57%; --s: 1; }
.ih.no-gl .ih__room:nth-child(5) { --px: 86%; --py: 40%; --s: 1; }

/* ---------- 深度刻度：itomdev 撕纸纸卡，浮在 3D 长廊之前 ---------- */
.ih__depth {
  position: absolute; z-index: 6; right: 18px; top: 42%;
  width: 112px; padding: 13px 12px 11px;
  display: flex; flex-direction: column; align-items: center; gap: 8px;
  background: rgba(255, 252, 244, .84);
  backdrop-filter: blur(7px);
  box-shadow: 3px 4px 0 rgba(74, 60, 44, .18), 0 12px 28px rgba(74, 44, 20, .1);
  font-family: "Kaiti SC", KaiTi, STKaiti, Georgia, serif;
  pointer-events: auto;
}
.ih__torn { position: absolute; inset: 0; z-index: 2; width: 100%; height: 100%; pointer-events: none; }
.ih__torn path {
  fill: none; stroke: #4A3C2C; stroke-width: 1.4;
  stroke-linecap: round; stroke-linejoin: round; vector-effect: non-scaling-stroke;
}
.ih__depth-cap {
  font-family: var(--u-font-tech, 'Orbitron', sans-serif);
  font-size: 9px; font-weight: 700; letter-spacing: .28em; color: #8B5E1C;
}
.ih__depth-rail {
  position: relative; display: flex; flex-direction: column;
  align-items: flex-start; gap: 11px; padding: 3px 0;
}
.ih__depth-line {
  position: absolute; left: 4.5px; top: 9px; bottom: 9px; width: 1.5px;
  background: rgba(74, 60, 44, .22);
}
.ih__depth-line::after {
  content: ''; position: absolute; left: 0; top: 0; width: 100%;
  height: var(--p, 0%);
  background: linear-gradient(180deg, #A67C2E, #C2410C);
  transition: height .25s ease;
}
.ih__depth-dot {
  position: relative; z-index: 1; display: inline-flex; align-items: center; gap: 7px;
  background: none; border: 0; padding: 0; margin: 0;
  cursor: pointer; font-family: inherit; color: #6F5C44;
  -webkit-tap-highlight-color: transparent;
}
.ih__depth-pip {
  width: 9px; height: 9px; border-radius: 50%;
  border: 1.5px solid #8B7355; background: #FFFCF3;
  transition: transform .22s ease, background .22s ease, border-color .22s ease, box-shadow .22s ease;
}
.ih__depth-dot.is-past .ih__depth-pip { border-color: #A67C2E; background: #A67C2E; }
.ih__depth-dot.is-on .ih__depth-pip {
  transform: scale(1.5); background: #C2410C; border-color: #C2410C;
  box-shadow: 0 0 0 3px rgba(194, 65, 12, .14);
}
.ih__depth-name {
  font-size: 10.5px; white-space: nowrap; opacity: .55;
  transition: opacity .2s ease, color .2s ease;
}
.ih__depth-dot.is-on .ih__depth-name,
.ih__depth-dot:hover .ih__depth-name { opacity: 1; color: #8B4513; font-weight: 700; }
.ih__depth-dot:focus-visible { outline: 2px dashed var(--orange); outline-offset: 3px; }
.ih__depth-now { font-size: 12px; font-weight: 700; letter-spacing: .08em; color: #8B4513; }

/* ---------- 馆长洞察 ---------- */
.ih__stories {
  position: absolute; z-index: 5;
  left: clamp(24px, 4vw, 70px); right: clamp(24px, 4vw, 70px); bottom: 16px;
  max-height: 226px; pointer-events: auto;
}
.ih__stories :deep(.hi) {
  position: static; left: auto; bottom: auto; transform: none; width: 100%;
  background: none; border: none; border-radius: 0; box-shadow: none;
  backdrop-filter: none; padding: 0; pointer-events: auto;
}
.ih__stories :deep(.hi__head) { margin: 0 4px 5px; }
.ih__stories :deep(.hi__row) { gap: clamp(8px, 1vw, 14px); }
.ih__stories :deep(.hi__card-in) {
  padding: 8px 12px; background: rgba(255, 252, 244, .9);
  border: 1px solid rgba(120, 92, 54, .3); border-radius: 3px;
  box-shadow: 3px 3px 0 rgba(120, 92, 54, .18);
}
.ih__stories :deep(.hi__q) { font-size: 14.5px; margin: 3px 0 1px; }
.ih__stories :deep(.hi__a) { margin-bottom: 4px; }
.ih__stories :deep(.hi__kicker) { font-size: 8.5px; }
.ih__stories :deep(.hi__credits) { margin-top: 4px; }
.ih__stories :deep(.hi__fact) { padding: 2px 0; }
.ih__stories :deep(.hi__fact:last-child) { padding-bottom: 0; }

/* ---------- 窄屏：不建 WebGL，竖排门牌，保留全部入口 ---------- */
@media (max-width: 900px) {
  .ih { overflow-y: auto; display: flex; flex-direction: column; cursor: default; padding-top: 72px; }
  .ih__gl, .ih__shade, .ih__depth { display: none; }
  .ih__masthead, .ih__doors, .ih__stories { position: relative; left: auto; right: auto; top: auto; bottom: auto; max-width: none; max-height: none; }
  .ih__masthead { order: 0; padding: 18px 18px 4px; }
  .ih__doors {
    order: 1; inset: auto; display: flex; flex-direction: column; gap: 12px;
    padding: 10px 16px 6px; pointer-events: auto;
  }
  .ih__stories { order: 2; padding: 8px 16px 20px; }
  .ih__ink { display: none !important; }
  /* 平面降级同样「先开盒才见门」：合盒时整组门牌从布局里移除 */
  .ih.is-sealed .ih__doors { display: none !important; }
  .ih.is-revealed .ih__box { display: none !important; }
  .ih__after {
    position: relative; right: auto; top: auto; order: 1;
    flex-direction: row; justify-content: center; flex-wrap: wrap;
    padding: 4px 16px 6px;
  }
  .ih__box {
    position: relative; left: auto !important; top: auto !important;
    order: 1; width: 100%; max-width: 320px; height: 54px; margin: 2px auto 8px;
    transform: none !important; opacity: 1 !important;
    border: 1.8px solid rgba(74, 60, 44, .8);
    border-radius: 4px 14px 4px 14px / 14px 4px 14px 4px;
    background: linear-gradient(172deg, #FFFCF3, #F2E5CB);
    box-shadow: 3px 4px 0 rgba(74, 60, 44, .24);
    display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 7px;
  }
  .ih.is-sealed .ih__box { width: min(86vw, 340px); height: 148px; }
  .ih__box-seal { position: static; transform: rotate(-4deg); font-size: 16px; }
  .ih__box-tag { position: static; transform: none; opacity: 1; font-size: 10px; padding: 7px 14px; }
  .ih__box:hover .ih__box-tag { transform: none; }
  .ih__box-hint { position: static; transform: none; opacity: .9; }
  .ih.no-gl .ih__room:nth-child(n),
  .ih__room {
    position: relative; left: auto !important; top: auto !important;
    width: 100%; max-width: 320px; height: auto; margin: 0 auto;
    transform: none !important; opacity: 1 !important; pointer-events: auto;
  }
  /* 窄屏没有 3D 门板，中央虚线框与推门胶囊都收起，木牌回到卡片内 */
  .ih__room::before, .ih__door-cta { display: none; }
  .ih__plaque {
    position: static; width: 100%; transform: none !important;
    flex-direction: row; flex-wrap: wrap; align-items: center; gap: 4px 10px;
    text-align: left; padding: 12px 14px;
  }
  .ih__sign-no { position: static; font-size: 12px; }
  .ih__zh { margin-top: 0; font-size: 16px; }
  .ih__desc { flex: 1 1 100%; text-align: left; max-width: none; }
  .ih__go { margin-top: 0; }
  .ih__room.is-active .ih__plaque, .ih__room:hover .ih__plaque { transform: none; }
  /* 窄屏把纵深 LOD 收起的小木牌恢复完整说明 */
  .ih__room:nth-child(n+3) .ih__desc { display: block !important; }
  .ih__room:nth-child(n+3) .ih__plaque { padding: 12px 14px; }
  /* 馆长洞察三张卡改为竖排，不再横向被裁 */
  .ih__stories :deep(.hi__row) { display: flex !important; flex-direction: column; overflow: visible !important; }
  .ih__stories :deep(.hi__card) { flex: none !important; width: 100% !important; }
}

@media (max-height: 820px) and (min-width: 901px) {
  .ih__stories { max-height: 168px; }
}

@media (prefers-reduced-motion: reduce) {
  .ih, .ih.is-entering { transition-duration: .16s; }
}
</style>
