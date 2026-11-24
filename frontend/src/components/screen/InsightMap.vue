<template>
  <!--
    ============================================================
    影评洞察馆 · 手绘导览图（参考 itomdev.com 的 MAP 面板）
    ------------------------------------------------------------
    itomdev 的导航核心不是"返回按钮"，而是一张手绘地图：
    纸质卡片 + 抖边描边 + 硬阴影，房间排在地图四周，
    一个「You are here」图钉标出当前位置，点房间传送。
    这里把五间展厅排成"三上两下围一条走廊"的平面图：
      · 大厅模式：五个房间都可点（= 传送进门），图钉在走廊入口
      · 展厅模式：只高亮当前展厅 + 图钉，其余置灰（展厅相互独立，
        不允许在展厅里串门 —— 用户 2026-10-22 红线），底部大按钮回大厅
    零依赖：纯 SVG + CSS，抖边路径由确定性伪随机生成（刷新不跳变）。
    ============================================================
  -->
  <div class="im" @click.self="emit('close')">
    <div class="im__backdrop" aria-hidden="true" />

    <div class="im__card" role="dialog" aria-label="洞察馆导览图">
      <!-- 撕纸抖边：itomdev map-border-overlay 同款（SVG path 描边绕卡片一圈） -->
      <svg class="im__torn" viewBox="0 0 100 100" preserveAspectRatio="none" aria-hidden="true">
        <path :d="tornPath" fill="none" stroke="#6B4E2E" stroke-width="0.9" stroke-linejoin="round" opacity="0.55" vector-effect="non-scaling-stroke" />
      </svg>

      <header class="im__head">
        <div class="im__head-t">
          <span class="im__kicker">INSIGHT MAP</span>
          <h2 class="im__title">洞察馆 · 导览图</h2>
        </div>
        <button class="im__close" type="button" aria-label="关闭导览图" @click="emit('close')">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M18 6L6 18M6 6l12 12" /></svg>
        </button>
      </header>

      <div class="im__map">
        <svg viewBox="0 0 960 540" aria-label="洞察馆平面图">
          <defs>
            <linearGradient id="im-cur" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0" stop-color="#FFE9C9" />
              <stop offset="1" stop-color="#FFD9A0" />
            </linearGradient>
            <filter id="im-glow" x="-30%" y="-30%" width="160%" height="160%">
              <feDropShadow dx="0" dy="3" stdDeviation="7" flood-color="#C2410C" flood-opacity="0.28" />
            </filter>
          </defs>

          <!-- 走廊：一条横贯的手绘通道 -->
          <path :d="corridorPath" class="im__corridor" />
          <path d="M34 278 L 404 278" class="im__corridor-dash" />
          <path d="M556 278 L 926 278" class="im__corridor-dash" />
          <text x="480" y="284" class="im__corridor-label">走  廊</text>

          <!-- 大厅出入口（图钉 + 说明） -->
          <g class="im__hall">
            <path d="M72 168c-11 0-20 9-20 20 0 14 20 30 20 30s20-16 20-30c0-11-9-20-20-20z" class="im__pin-shape" />
            <circle cx="72" cy="188" r="7.5" class="im__pin-dot" />
            <text x="72" y="234" class="im__hall-t">大厅</text>
            <text x="72" y="252" class="im__hall-s">{{ mode === 'room' ? '出口 · 回大厅' : '入口 · 你在这里' }}</text>
          </g>

          <!-- 五间展厅 -->
          <g
            v-for="(r, i) in rooms"
            :key="r.key"
            class="im__room"
            :class="{ 'is-cur': mode === 'room' && r.key === current, 'is-locked': mode === 'room' && r.key !== current }"
            :transform="`translate(${POS[i].x} ${POS[i].y})`"
            role="button"
            :tabindex="mode === 'house' ? 0 : -1"
            :aria-label="mode === 'house' ? `进入${r.zh}展厅` : `${r.zh}展厅`"
            @click="mode === 'house' && emit('enter', r.key)"
            @keydown.enter="mode === 'house' && emit('enter', r.key)"
          >
            <!-- 门洞连接走廊 -->
            <rect :x="BOX.w / 2 - 27" :y="i < 3 ? BOX.h : -56" width="54" :height="56" class="im__door" />
            <!-- 房间体（铅笔双线：同一路径错位画两遍） -->
            <path :d="roomPaths[i]" class="im__room-box" filter="url(#im-glow)" />
            <path :d="roomPaths[i]" class="im__room-box2" />
            <text :x="BOX.w / 2" y="46" class="im__room-icon">{{ r.icon }}</text>
            <text :x="BOX.w / 2" y="84" class="im__room-name">{{ r.zh }}</text>
            <text v-if="mode === 'room' && r.key !== current" :x="BOX.w / 2" y="99" class="im__room-lock">⊘ 需先回大厅</text>
            <!-- 当前位置图钉（展厅模式） -->
            <g v-if="mode === 'room' && r.key === current">
              <path d="M126 -22c-11 0-20 9-20 20 0 14 20 30 20 30s20-16 20-30c0-11-9-20-20-20z" class="im__pin-shape" />
              <circle cx="126" cy="-2" r="7.5" class="im__pin-dot" />
              <text :x="126" :y="i < 3 ? -32 : BOX.h + 26" class="im__here">你在这里</text>
            </g>
          </g>

          <!-- 指北针（手绘小装饰） -->
          <g class="im__compass" transform="translate(898 506)">
            <circle r="24" class="im__compass-c" />
            <path d="M0 -18 L 6 4 L 0 0 L -6 4 Z" class="im__compass-n" />
            <text y="-26" class="im__compass-t">N</text>
          </g>

          <!-- 比例尺（手绘小装饰） -->
          <g class="im__scale" transform="translate(40 512)">
            <path d="M0 0 L 108 0 M0 -5 L0 5 M27 -4 L27 4 M54 -5 L54 5 M81 -4 L81 4 M108 -5 L108 5" />
            <text x="54" y="-12">馆内比例</text>
          </g>
        </svg>
      </div>

      <footer class="im__foot">
        <p class="im__tip">
          <template v-if="mode === 'house'">点击任意房间可直接进入 · 走廊尽头就是大厅</template>
          <template v-else>展厅之间相互独立 · 回到大厅才能换其他展厅</template>
        </p>
        <button v-if="mode === 'room'" class="im__back" type="button" @click="emit('back')">← 回大厅</button>
      </footer>
    </div>
  </div>
</template>

<script setup>
// ============================================================
// 导览图：只画"选门/回大厅"，不碰数据。房间几何（位置/抖边路径）
// 用确定性伪随机生成一次，避免每次渲染抖边跳变。
// ============================================================
import { computed, onMounted, onUnmounted } from 'vue'

const props = defineProps({
  rooms: { type: Array, default: () => [] },
  mode: { type: String, default: 'house' },   // 'house' 大厅 | 'room' 展厅
  current: { type: String, default: null },   // 当前展厅 key
})
const emit = defineEmits(['enter', 'back', 'close'])

/* ---------- 确定性伪随机（mulberry32）：抖边形态稳定 ---------- */
function mulberry32(a) {
  return () => {
    a |= 0; a = (a + 0x6D2B79F5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}
/* 闭合多边形的铅笔抖边：每边中点外扩随机偏移，Q 曲线过渡 */
function wobble(pts, amp, seed) {
  const rnd = mulberry32(seed)
  let d = ''
  for (let i = 0; i < pts.length; i++) {
    const [x, y] = pts[i]
    const [nx, ny] = pts[(i + 1) % pts.length]
    const mx = (x + nx) / 2 + (rnd() - 0.5) * amp
    const my = (y + ny) / 2 + (rnd() - 0.5) * amp
    d += `${i === 0 ? 'M' : 'L'}${x} ${y} Q${mx.toFixed(1)} ${my.toFixed(1)} ${nx} ${ny} `
  }
  return d + 'Z'
}

const BOX = { w: 252, h: 104 }
const POS = [
  { x: 40, y: 24 }, { x: 354, y: 24 }, { x: 668, y: 24 },
  { x: 197, y: 380 }, { x: 511, y: 380 },
]

const tornPath = computed(() => wobble([[1, 1], [99, 1], [99, 99], [1, 99]], 2.2, 7))
const corridorPath = computed(() => wobble([[26, 256], [934, 256], [934, 300], [26, 300]], 3, 11))
const roomPaths = computed(() =>
  POS.map((_, i) => wobble([[2, 2], [BOX.w - 2, 3], [BOX.w - 1, BOX.h - 2], [3, BOX.h - 1]], 5, 21 + i * 9)),
)

/* Esc 关闭 */
function onKey(e) { if (e.key === 'Escape') emit('close') }
onMounted(() => window.addEventListener('keydown', onKey))
onUnmounted(() => window.removeEventListener('keydown', onKey))
</script>

<style scoped>
/* ---------- 背板（itomdev global-overlay-backdrop 同款：压暗 + 模糊） ---------- */
.im { position: fixed; inset: 0; z-index: 3000; display: grid; place-items: center; padding: 20px; }
.im__backdrop {
  position: absolute; inset: 0;
  background: rgba(74, 46, 22, 0.42);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  animation: im-fade 0.4s ease both;
}
@keyframes im-fade { from { opacity: 0; } to { opacity: 1; } }

/* ---------- 纸卡：抖边 + 硬阴影 + 弹簧入场 ---------- */
.im__card {
  position: relative;
  width: min(1040px, 94vw);
  max-height: 92vh;
  display: flex;
  flex-direction: column;
  padding: 26px 30px 22px;
  background:
    radial-gradient(120% 90% at 18% 8%, rgba(255, 255, 255, 0.9), rgba(255, 255, 255, 0) 55%),
    linear-gradient(168deg, #FFFDF7 0%, #FBF5E9 60%, #F6EFDF 100%);
  border: 2.6px solid #3A2E20;
  /* itomdev 手绘抖边绝技：不对称大圆角 = 纸上手画的框 */
  border-radius: 255px 18px 225px 18px / 18px 225px 18px 255px;
  box-shadow: 10px 12px 0 rgba(74, 40, 20, 0.22), 0 30px 70px rgba(74, 40, 20, 0.3);
  animation: im-in 0.55s cubic-bezier(0.34, 1.56, 0.64, 1) both;
}
@keyframes im-in {
  from { transform: translateY(70px) scale(0.94); opacity: 0; }
  to { transform: translateY(0) scale(1); opacity: 1; }
}
.im__torn { position: absolute; inset: 0; width: 100%; height: 100%; pointer-events: none; z-index: 4; }

/* ---------- 卡头 ---------- */
.im__head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin-bottom: 10px; }
.im__kicker {
  display: inline-block; font-size: 10px; font-weight: 800; letter-spacing: 4px;
  color: #FFF6E9; background: linear-gradient(160deg, #A0522D, #8B4513);
  padding: 3px 12px 4px; border: 1.6px solid #5C4326;
  border-radius: 255px 15px 225px 15px / 15px 225px 15px 255px;
  box-shadow: 2px 2px 0 rgba(74, 40, 20, 0.25);
}
.im__title { margin: 8px 0 0; font-size: clamp(20px, 2.4vw, 27px); font-weight: 800; color: #3A2E20; letter-spacing: 0.06em; }
.im__close {
  flex: none; width: 38px; height: 38px; display: grid; place-items: center; cursor: pointer;
  background: #FFFDF7; border: 2px solid #3A2E20; color: #3A2E20;
  border-radius: 15px 225px 15px 255px / 255px 15px 225px 15px;
  box-shadow: 3px 3px 0 rgba(74, 40, 20, 0.25);
  transition: transform 0.18s ease, background 0.18s ease, color 0.18s ease;
}
.im__close svg { width: 17px; height: 17px; fill: none; stroke: currentColor; stroke-width: 2.4; stroke-linecap: round; }
.im__close:hover { background: linear-gradient(160deg, #A0522D, #8B4513); color: #FFF6E9; transform: translate(1px, 1px) rotate(-4deg); box-shadow: 1px 1px 0 rgba(74, 40, 20, 0.3); }

/* ---------- 地图画布 ---------- */
.im__map {
  flex: 1; min-height: 0; display: grid; place-items: center;
  background:
    repeating-linear-gradient(0deg, rgba(139, 115, 85, 0.05) 0 1px, rgba(139, 115, 85, 0) 1px 26px),
    repeating-linear-gradient(90deg, rgba(139, 115, 85, 0.05) 0 1px, rgba(139, 115, 85, 0) 1px 26px),
    #FBF6EC;
  border: 2px solid rgba(107, 78, 46, 0.4);
  border-radius: 18px 120px 16px 130px / 130px 16px 120px 18px;
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.7), inset 0 2px 14px rgba(107, 78, 46, 0.08);
  padding: 8px;
}
.im__map svg { width: 100%; height: auto; max-height: min(58vh, 520px); display: block; }

.im__corridor { fill: #F6F1E6; stroke: #A08B6A; stroke-width: 2.2; }
.im__corridor-dash { fill: none; stroke: #B7A488; stroke-width: 3.4; stroke-linecap: round; stroke-dasharray: 1 10; }
.im__corridor-label { font-size: 13px; fill: #8B7355; letter-spacing: 7px; text-anchor: middle; font-weight: 700; }

.im__door { fill: #F3EBDC; stroke: #B7A488; stroke-width: 2; }

/* 房间 */
.im__room { cursor: default; }
.im__room-box { fill: #FBF6EC; stroke: #6B4E2E; stroke-width: 2.6; }
.im__room-box2 { fill: none; stroke: rgba(107, 78, 46, 0.28); stroke-width: 1.2; transform: translate(1.6px, 1.4px); }
.im__room-icon { font-size: 30px; text-anchor: middle; }
.im__room-name { font-size: 21px; font-weight: 800; fill: #4A2E16; text-anchor: middle; letter-spacing: 0.04em; }
.im__room-lock { font-size: 11.5px; fill: #9A8B70; text-anchor: middle; letter-spacing: 0.05em; }

/* 大厅模式：全部可点，悬停换色（注意：SVG 上不能写 CSS transform，
   会覆盖 g 元素的 translate 定位属性，只改填充/描边） */
.im__room:not(.is-locked):not(.is-cur) { cursor: pointer; }
.im__room:not(.is-locked):not(.is-cur):hover .im__room-box { fill: #FFF7E6; stroke: #C2410C; }
.im__room:focus-visible { outline: none; }
.im__room:focus-visible .im__room-box { stroke: #C2410C; stroke-width: 3.4; }

/* 展厅模式：当前房暖色高亮 + 光晕；其余置灰不可点 */
.im__room.is-cur .im__room-box { fill: url(#im-cur); stroke: #C2410C; stroke-width: 3.4; }
.im__room.is-locked { opacity: 0.42; }
.im__room.is-locked .im__room-box { stroke-dasharray: 7 6; fill: #F0E9DA; }

/* 图钉 */
.im__pin-shape { fill: #C2410C; stroke: #6B4E2E; stroke-width: 2.4; }
.im__pin-dot { fill: #FFF6E9; stroke: #6B4E2E; stroke-width: 2; }
.im__here { font-size: 14px; font-weight: 800; fill: #C2410C; text-anchor: middle; letter-spacing: 0.1em; }
.im__hall-t { font-size: 15px; font-weight: 800; fill: #4A2E16; text-anchor: middle; letter-spacing: 0.08em; }
.im__hall-s { font-size: 11.5px; fill: #7D6B52; text-anchor: middle; letter-spacing: 0.06em; }

/* 指北针 + 比例尺 */
.im__compass-c { fill: rgba(255, 253, 247, 0.85); stroke: #8B7355; stroke-width: 2; }
.im__compass-n { fill: #C2410C; stroke: #6B4E2E; stroke-width: 1.4; }
.im__compass-t { font-size: 13px; font-weight: 800; fill: #6B4E2E; text-anchor: middle; }
.im__scale path { fill: none; stroke: #8B7355; stroke-width: 2; stroke-linecap: round; }
.im__scale text { font-size: 11px; fill: #8B7355; text-anchor: middle; letter-spacing: 0.2em; }

/* ---------- 卡脚 ---------- */
.im__foot { display: flex; align-items: center; justify-content: space-between; gap: 14px; margin-top: 14px; flex-wrap: wrap; }
.im__tip { margin: 0; font-size: 12.5px; color: #7D6B52; letter-spacing: 0.04em; }
.im__back {
  padding: 11px 26px; font-size: 15px; font-weight: 800; letter-spacing: 0.08em; cursor: pointer;
  color: #FFF6E9; background: linear-gradient(160deg, #A0522D, #8B4513);
  border: 2.2px solid #5C4326;
  border-radius: 255px 15px 225px 15px / 15px 225px 15px 255px;
  box-shadow: 4px 4px 0 rgba(74, 40, 20, 0.35);
  transition: transform 0.16s ease, box-shadow 0.16s ease, background 0.2s ease;
}
.im__back:hover { background: linear-gradient(160deg, #B5651D, #A0522D); transform: translate(2px, 2px); box-shadow: 1px 1px 0 rgba(74, 40, 20, 0.4); }
.im__back:active { transform: translate(4px, 4px); box-shadow: 0 0 0 rgba(74, 40, 20, 0.4); }

@media (max-width: 720px) {
  .im__card { padding: 18px 16px 14px; }
  .im__map svg { max-height: 46vh; }
  .im__foot { justify-content: center; }
  .im__tip { width: 100%; text-align: center; }
}
</style>
