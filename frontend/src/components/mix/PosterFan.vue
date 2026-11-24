<script setup>
// ============================================================
// 海报扇（PosterFan）—— 参考 justinesoulie.fr 首页的 WebGL 拖拽画廊
//
// 效果构成（照参考站实测还原）：
//   · 中间一张正立、清晰、投影最重；两侧按距离向内旋转 + 缩小 + 后移 + 高斯虚化
//   · 按住横向拖动 → 整扇跟手移动，松手按速度吸附到最近一张
//   · 滚轮（横向/Shift+滚轮）/ 左右按钮 / 圆点 / 键盘 ← → 都能换片
//   · 中间片信息（片名/年份/类型/评分）在下方跟手切换
//
// 实现选择：CSS 3D transform + rAF 阻尼插值，不引 WebGL——
// 参考站的形变是 shader 级"纸张弯曲"，这里用 rotateY + blur 做景深近似，
// 观感接近而成本低得多（页面本身还要留给检索结果）。
// ============================================================
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue'

const props = defineProps({
  movies: { type: Array, default: () => [] },
  // bare：不画自己的纸面底/边框/投影，直接浮在别的背景上（类型混搭页的天气舞台用）
  bare: { type: Boolean, default: false },
})

const emit = defineEmits(['open', 'blind'])

const list = computed(() => (props.movies || []).filter((m) => m && m.movie_id))
const len = computed(() => list.value.length)

const stage = ref(null)
const cards = ref([])
// 海报下载状态：占位卡面 + 载入后才淡入（冷启动走后端代理要几秒，先给一张暖纸卡，别露出空白底）
const loaded = reactive(new Set())
const failed = reactive(new Set())
function markLoaded(id) { loaded.add(id) }
const pos = ref(0)         // 实际渲染位置（浮点，拖拽时跟手；可为任意实数）
const target = ref(0)      // 吸附目标，pos 以阻尼追它
const dragging = ref(false)
const moved = ref(0)

let spacing = 220
let raf = null
let lastT = 0
let dragX = 0
let dragPos = 0
let velocity = 0
let lastMoveX = 0
let lastMoveT = 0
let suppressClick = false
let ro = null

function wrapIndex(i) {
  const n = len.value || 1
  return ((Math.round(i) % n) + n) % n
}
// 当前居中的是第几张（循环扇，pos 可以跑到任意区间）
const activeIndex = computed(() => wrapIndex(pos.value))
const cur = computed(() => list.value[activeIndex.value] || null)
const curYear = computed(() => cur.value?.year || cur.value?.release_year || '')
const curGenres = computed(() => (cur.value?.genres_zh || []).slice(0, 3).join(' / '))
const curRating = computed(() => {
  const r = cur.value?.rating
  return typeof r === 'number' && r > 0 ? r.toFixed(1) : '—'
})

function clamp(v, lo, hi) { return Math.min(hi, Math.max(lo, v)) }

// 每张卡片的位置由「它离当前位置几格」决定：格数越大 → 越向内转、越靠后、越虚
// 取模成最短环形距离 → 首尾相接，永远两侧都有片（参考站就是循环扇）
function cardStyle(i) {
  const n = len.value
  let off = i - pos.value
  if (n > 1) {
    off = ((off % n) + n) % n
    if (off > n / 2) off -= n
  }
  const a = Math.abs(off)
  const sign = off >= 0 ? 1 : -1
  const k = Math.min(a, 3.2)
  const x = off * spacing
  const rotY = sign * k * 15          // 内侧边缘朝向观众 → 像一扇打开的折扇
  const z = -k * 96
  const scale = 1 - k * 0.045
  const blur = Math.min(a * 2.1, 6.5)
  const opacity = a > 3.6 ? 0 : 1 - Math.min(a, 3.2) * 0.1
  return {
    transform: `translate(-50%, -50%) translate3d(${x.toFixed(2)}px, 0, ${z.toFixed(2)}px) rotateY(${rotY.toFixed(2)}deg) scale(${scale.toFixed(3)})`,
    filter: blur > 0.02 ? `blur(${blur.toFixed(2)}px)` : 'none',
    opacity: opacity.toFixed(3),
    zIndex: 100 - Math.round(a * 10),
    pointerEvents: a > 3.0 ? 'none' : 'auto',
    // 圈外的卡片直接不画：避免 20 张同时吃 blur 滤镜
    visibility: a > 3.4 ? 'hidden' : 'visible',
  }
}

// ---- 阻尼循环：把 pos 平滑推向 target ----
function tick(t) {
  const dt = Math.min(64, t - (lastT || t)) || 16
  lastT = t
  if (!dragging.value) {
    const k = 1 - Math.pow(0.0025, dt / 1000) // 与帧率无关的阻尼
    const d = target.value - pos.value
    if (Math.abs(d) > 0.0015) {
      pos.value += d * k
    } else {
      pos.value = target.value
      // 收敛后把坐标折回 [0, n)：取模后每张卡片的相对位置完全等价，画面不跳
      const n = len.value
      if (n > 1 && Math.abs(pos.value) >= n) {
        const back = Math.floor(pos.value / n) * n
        pos.value -= back
        target.value -= back
      }
    }
  }
  raf = requestAnimationFrame(tick)
}

// 跳到第 i 张（走环形最短方向）
function goTo(i) {
  const n = len.value
  if (!n) return
  let delta = i - activeIndex.value
  if (n > 1) {
    if (delta > n / 2) delta -= n
    if (delta < -n / 2) delta += n
  }
  target.value = pos.value + delta
}
function step(d) { goTo(activeIndex.value + d) }

function onPointerDown(ev) {
  if (len.value < 2) return
  // 只处理主键 / 触摸
  if (ev.pointerType === 'mouse' && ev.button !== 0) return
  // 点在按钮/信息区上时不能开始拖拽：
  // 一旦 setPointerCapture，后续 click 会被重定向到 stage，箭头和按钮就点不动了
  if (ev.target?.closest?.('button, a, .fan__ops, .fan__ctrl')) return
  dragging.value = true
  moved.value = 0
  dragX = ev.clientX
  dragPos = pos.value
  velocity = 0
  lastMoveX = ev.clientX
  lastMoveT = performance.now()
  stage.value?.classList.add('is-grab')
  stage.value?.setPointerCapture?.(ev.pointerId)
}

function onPointerMove(ev) {
  if (!dragging.value) return
  const dx = ev.clientX - dragX
  moved.value = Math.max(moved.value, Math.abs(dx))
  // 环形扇：不夹边界，一直可以拖（pos 取模后等价）
  pos.value = dragPos - dx / spacing
  const now = performance.now()
  const dt = now - lastMoveT
  if (dt > 0) velocity = (ev.clientX - lastMoveX) / dt // px/ms
  lastMoveX = ev.clientX
  lastMoveT = now
}

function onPointerUp(ev) {
  if (!dragging.value) return
  dragging.value = false
  stage.value?.classList.remove('is-grab')
  try { stage.value?.releasePointerCapture?.(ev.pointerId) } catch { /* 未捕获时忽略 */ }
  // 拖动超过阈值就不当作点击
  if (moved.value > 6) {
    suppressClick = true
    setTimeout(() => { suppressClick = false }, 300)
  }
  // 甩动惯性：按速度多走一点，然后吸附到最近的整格
  const fling = clamp(-velocity * 0.55, -2, 2)
  target.value = Math.round(pos.value + fling)
}

function onWheel(ev) {
  if (len.value < 2) return
  // 只接管横向滚动 / Shift+滚轮，纵向滚轮放行给页面
  const horizontal = Math.abs(ev.deltaX) > Math.abs(ev.deltaY)
  if (!horizontal && !ev.shiftKey) return
  ev.preventDefault()
  const d = horizontal ? ev.deltaX : ev.deltaY
  wheelAcc += d
  if (Math.abs(wheelAcc) > 42) {
    step(wheelAcc > 0 ? 1 : -1)
    wheelAcc = 0
  }
}
let wheelAcc = 0

function onKey(ev) {
  if (ev.key === 'ArrowLeft') { ev.preventDefault(); step(-1) }
  else if (ev.key === 'ArrowRight') { ev.preventDefault(); step(1) }
  else if (ev.key === 'Home') { ev.preventDefault(); goTo(0) }
  else if (ev.key === 'End') { ev.preventDefault(); goTo(len.value - 1) }
  else if (ev.key === 'Enter' || ev.key === ' ') {
    if (cur.value) { ev.preventDefault(); emit('open', cur.value) }
  }
}

function openCard(m) {
  if (suppressClick) return
  if (m) emit('open', m)
}

function measure() {
  const el = cards.value[activeIndex.value] || cards.value[0]
  const w = el?.offsetWidth || 200
  spacing = Math.max(120, w * 1.12 + 18)
}

watch(() => list.value.length, () => {
  pos.value = 0
  target.value = 0
  wheelAcc = 0
  measure()
})

onMounted(() => {
  measure()
  ro = new ResizeObserver(() => measure())
  if (stage.value) ro.observe(stage.value)
  raf = requestAnimationFrame(tick)
})
onBeforeUnmount(() => {
  if (raf) cancelAnimationFrame(raf)
  ro?.disconnect()
})
</script>

<template>
  <section
    ref="stage"
    class="fan"
    :class="{ 'is-dragging': dragging, 'is-single': len < 2, 'fan--bare': bare }"
    tabindex="0"
    role="group"
    aria-label="混搭结果海报扇，左右方向键切换"
    @pointerdown="onPointerDown"
    @pointermove="onPointerMove"
    @pointerup="onPointerUp"
    @pointercancel="onPointerUp"
    @wheel="onWheel"
    @keydown="onKey"
  >
    <!-- 扇面：所有海报绝对定位在中心，按 pos 展开 -->
    <div class="fan__stage">
      <div
        v-for="(m, i) in list"
        :key="m.movie_id"
        ref="cards"
        class="fan__card"
        :class="{ 'is-active': i === activeIndex }"
        :style="cardStyle(i)"
        :aria-hidden="i !== activeIndex"
        @click="openCard(m)"
      >
        <div class="fan__poster">
          <!-- 占位：海报还在下载时先显示暖纸卡面（片名首字 + 扫光），避免两侧出现整块空白米色 -->
          <div v-if="!loaded.has(m.movie_id)" class="fan__ph">
            <span class="fan__ph-ch">{{ (m.title || '影').slice(0, 1) }}</span>
            <span class="fan__ph-name">{{ m.title }}</span>
            <span v-if="m.poster_url && !failed.has(m.movie_id)" class="fan__ph-skel" aria-hidden="true" />
          </div>
          <!-- 不能用 loading="lazy"：卡片是 3D 变换 + 绝对定位，Chrome 会判定「不在视口」而不加载，
               两侧常驻出现整块米色空白（2026-10-21 实测 naturalWidth=0）。扇面本来就要 ±3 张同时可见。 -->
          <img
            v-if="m.poster_url && !failed.has(m.movie_id)"
            :src="m.poster_url"
            :alt="m.title"
            decoding="async"
            draggable="false"
            :class="{ 'is-ready': loaded.has(m.movie_id) }"
            @load="markLoaded(m.movie_id)"
            @error="failed.add(m.movie_id)"
          />
          <span class="fan__gloss" aria-hidden="true" />
        </div>
      </div>
    </div>

    <!-- 两侧渐隐，做出「扇子伸进纸里」的纵深 -->
    <span class="fan__fade fan__fade--l" aria-hidden="true" />
    <span class="fan__fade fan__fade--r" aria-hidden="true" />

    <!-- 当前片信息 -->
    <div v-if="cur" class="fan__info">
      <div class="fan__title">{{ cur.title }}</div>
      <div class="fan__meta">
        <span v-if="curYear">{{ curYear }}</span>
        <span v-if="curYear && curGenres" class="fan__dot">·</span>
        <span v-if="curGenres">{{ curGenres }}</span>
        <span class="fan__score">★ {{ curRating }}</span>
      </div>
      <div class="fan__ops">
        <button class="fan__btn fan__btn--solid" type="button" @click.stop="emit('open', cur)">看详情</button>
        <button class="fan__btn" type="button" @click.stop="emit('blind', cur)">🎲 加入盲盒</button>
      </div>
    </div>

    <!-- 控件 -->
    <div class="fan__ctrl">
      <button class="fan__arrow" type="button" aria-label="上一张" @click.stop="step(-1)">‹</button>
      <span class="fan__count">
        <b>{{ String(activeIndex + 1).padStart(2, '0') }}</b>
        <i>/</i>
        {{ String(len).padStart(2, '0') }}
      </span>
      <button class="fan__arrow" type="button" aria-label="下一张" @click.stop="step(1)">›</button>
    </div>

    <p class="fan__hint">按住左右拖动 · 滚轮横滑 · ← → 切换 · 点击看详情</p>
  </section>
</template>

<style scoped>
/* 扇面容器：暖纸底 + 顶部柔光，让海报像摆在纸上 */
.fan {
  position: relative;
  margin-top: 4px;
  padding: 26px 0 18px;
  border-radius: 20px;
  background:
    radial-gradient(120% 90% at 50% 0%, rgba(255, 252, 244, 0.9), rgba(250, 245, 235, 0) 62%),
    linear-gradient(180deg, #fdfaf3 0%, #f8f2e6 58%, #f4ece0 100%);
  border: 1px solid var(--border);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.85), 0 10px 30px rgba(139, 69, 19, 0.07);
  overflow: hidden;
  cursor: grab;
  user-select: none;
  -webkit-user-select: none;
  touch-action: pan-y;   /* 竖向留给页面滚动，横向交给拖拽 */
  outline: none;
}
.fan.is-dragging { cursor: grabbing; }
.fan:focus-visible { box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.85), 0 0 0 3px rgba(210, 105, 30, 0.28); }

.fan__stage {
  position: relative;
  height: clamp(300px, 40vw, 430px);
  perspective: 1400px;
  perspective-origin: 50% 44%;
  transform-style: preserve-3d;
}

.fan__card {
  position: absolute;
  left: 50%;
  top: 50%;
  width: clamp(132px, 15.5vw, 208px);
  aspect-ratio: 2 / 3;
  transform-origin: 50% 50%;
  will-change: transform, filter, opacity;
  cursor: pointer;
  transition: box-shadow 0.25s ease;
}
.fan__card.is-active { cursor: pointer; }

.fan__poster {
  position: relative;
  width: 100%;
  height: 100%;
  border-radius: 6px;
  overflow: hidden;
  background: linear-gradient(135deg, var(--light-brown), var(--warm-gray));
  box-shadow:
    0 1px 2px rgba(60, 40, 20, 0.18),
    0 14px 30px rgba(60, 40, 20, 0.22);
  transition: box-shadow 0.3s ease;
}
.fan__card.is-active .fan__poster {
  box-shadow:
    0 2px 4px rgba(60, 40, 20, 0.2),
    0 26px 48px rgba(60, 40, 20, 0.3);
}
.fan__poster img {
  position: absolute;
  inset: 0;
  z-index: 1;
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
  opacity: 0;
  transition: opacity 0.36s ease;
}
.fan__poster img.is-ready { opacity: 1; }
/* 占位卡面：暖纸渐变 + 片名首字 + 斜向扫光（图片到了才被盖住） */
.fan__ph {
  position: absolute;
  inset: 0;
  z-index: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 12px;
  box-sizing: border-box;
  overflow: hidden;
  color: rgba(74, 47, 22, 0.55);
  background:
    radial-gradient(120% 80% at 18% 12%, rgba(255, 255, 255, 0.55), rgba(255, 255, 255, 0) 60%),
    linear-gradient(150deg, #efe3cd 0%, #e2cfb2 55%, #d6bd9a 100%);
}
/* 首字当水印用，弱对比铺满卡面，远看是一张「待冲洗」的纸卡 */
.fan__ph-ch {
  font-size: clamp(38px, 4.2vw, 58px);
  font-weight: 900;
  line-height: 1;
  color: rgba(74, 47, 22, 0.16);
  text-shadow: 0 1px 0 rgba(255, 255, 255, 0.5);
}
.fan__ph-name {
  max-width: 100%;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
  line-height: 1.3;
  text-align: center;
  color: rgba(74, 47, 22, 0.42);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.fan__ph-skel {
  position: absolute;
  top: 0;
  bottom: 0;
  left: -40%;
  width: 40%;
  background: linear-gradient(90deg, rgba(255, 255, 255, 0) 0%, rgba(255, 255, 255, 0.42) 50%, rgba(255, 255, 255, 0) 100%);
  animation: fan-sweep 1.5s ease-in-out infinite;
}
@keyframes fan-sweep {
  0% { left: -40%; }
  100% { left: 110%; }
}
/* 纸面高光：斜向一条淡光，让海报不像贴图 */
.fan__gloss {
  position: absolute;
  inset: 0;
  z-index: 2;
  background: linear-gradient(118deg, rgba(255, 255, 255, 0.22) 0%, rgba(255, 255, 255, 0) 34%, rgba(255, 255, 255, 0) 66%, rgba(255, 255, 255, 0.12) 100%);
  pointer-events: none;
  mix-blend-mode: screen;
}

/* 两侧渐隐到纸色 */
.fan__fade {
  position: absolute;
  top: 0;
  bottom: 92px;
  width: 15%;
  pointer-events: none;
  z-index: 40;
}
.fan__fade--l { left: 0; background: linear-gradient(90deg, #fbf7ee 8%, rgba(251, 247, 238, 0) 100%); }
.fan__fade--r { right: 0; background: linear-gradient(270deg, #f7f0e2 8%, rgba(247, 240, 226, 0) 100%); }

.fan__info {
  position: relative;
  z-index: 50;
  text-align: center;
  padding: 2px 20px 0;
  min-height: 96px;
}
.fan__title {
  font-size: clamp(17px, 1.5vw, 21px);
  font-weight: 800;
  letter-spacing: 0.01em;
  color: var(--dark-brown);
  line-height: 1.25;
  max-width: 680px;
  margin: 0 auto;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.fan__meta {
  margin-top: 6px;
  font-size: 12.5px;
  letter-spacing: 0.06em;
  color: var(--text-3);
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 7px;
  flex-wrap: wrap;
}
.fan__dot { opacity: 0.5; }
.fan__score { color: var(--gold); font-weight: 800; letter-spacing: 0.02em; }

.fan__ops {
  margin-top: 11px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 9px;
}
.fan__btn {
  padding: 7px 18px;
  border-radius: 999px;
  border: 1.5px solid var(--border-strong);
  background: var(--surface);
  color: var(--text-2);
  font-size: 13px;
  font-weight: 700;
  cursor: pointer;
  transition: all 0.16s ease;
}
.fan__btn:hover { border-color: var(--gold); color: var(--gold); transform: translateY(-1px); }
.fan__btn--solid {
  background: linear-gradient(135deg, var(--brand) 0%, var(--brand-2) 100%);
  border-color: transparent;
  color: #fff;
  box-shadow: 0 6px 16px rgba(139, 69, 19, 0.24);
}
.fan__btn--solid:hover { color: #fff; box-shadow: 0 9px 20px rgba(139, 69, 19, 0.32); }

.fan__ctrl {
  position: relative;
  z-index: 50;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 14px;
  margin-top: 6px;
}
.fan__arrow {
  width: 32px;
  height: 32px;
  border-radius: 50%;
  border: 1.5px solid var(--border-strong);
  background: var(--surface);
  color: var(--brand);
  font-size: 19px;
  line-height: 1;
  cursor: pointer;
  display: grid;
  place-items: center;
  padding: 0 0 3px;
  transition: all 0.16s ease;
}
.fan__arrow:hover:not(:disabled) { border-color: var(--gold); background: #fdf6ea; }
.fan__arrow:disabled { opacity: 0.32; cursor: default; }
.fan__count {
  font-size: 12px;
  letter-spacing: 0.12em;
  color: var(--text-3);
  font-variant-numeric: tabular-nums;
  display: inline-flex;
  align-items: baseline;
  gap: 3px;
}
.fan__count b { color: var(--dark-brown); font-size: 14px; font-weight: 800; }
.fan__count i { font-style: normal; opacity: 0.5; }

.fan__hint {
  position: relative;
  z-index: 50;
  margin: 8px 0 0;
  text-align: center;
  font-size: 11px;
  letter-spacing: 0.08em;
  color: var(--text-3);
  opacity: 0.72;
}

.fan.is-single .fan__ctrl { display: none; }

/* ------- 裸扇：浮在天气舞台上 -------
   去掉纸面底/边框/投影，让海报直接站进插画里；
   两侧不再盖纸色渐变（会在天空间糊出一条米色带），改成遮罩淡出到透明。 */
.fan--bare {
  padding: 16px 0 6px;
  background: none;
  border-color: transparent;
  border-radius: 0;
  box-shadow: none;
}
.fan--bare .fan__stage {
  -webkit-mask-image: linear-gradient(90deg, transparent 0%, #000 15%, #000 85%, transparent 100%);
  mask-image: linear-gradient(90deg, transparent 0%, #000 15%, #000 85%, transparent 100%);
}
.fan--bare .fan__fade { display: none; }
/* 片名块换磨砂玻璃：夜晚/雨天是深色天空，纯深棕字会糊掉 */
.fan--bare .fan__info {
  max-width: 560px;
  min-height: 0;
  margin: 10px auto 0;
  padding: 12px 22px 14px;
  border-radius: 16px;
  background: rgba(255, 253, 247, 0.74);
  border: 1px solid rgba(255, 255, 255, 0.55);
  box-shadow: 0 12px 30px rgba(52, 34, 18, 0.18);
  -webkit-backdrop-filter: blur(14px) saturate(1.15);
  backdrop-filter: blur(14px) saturate(1.15);
}
.fan--bare .fan__ctrl {
  width: fit-content;
  margin: 10px auto 0;
  padding: 4px 10px;
  gap: 12px;
  border-radius: 999px;
  background: rgba(255, 253, 247, 0.68);
  border: 1px solid rgba(255, 255, 255, 0.5);
  -webkit-backdrop-filter: blur(10px);
  backdrop-filter: blur(10px);
}
.fan--bare .fan__arrow {
  background: transparent;
  border-color: rgba(139, 69, 19, 0.22);
}
.fan--bare .fan__arrow:hover:not(:disabled) { background: rgba(255, 255, 255, 0.7); }
/* 操作提示统一由舞台底部那条讲，避免两行提示打架 */
.fan--bare .fan__hint { display: none; }

@media (max-width: 720px) {
  .fan { padding: 18px 0 14px; }
  .fan__stage { height: 300px; }
  .fan__fade--l, .fan__fade--r { bottom: 86px; width: 9%; }
  .fan__hint { display: none; }
  .fan--bare { padding: 8px 0 4px; }
  .fan--bare .fan__info { max-width: 100%; padding: 10px 14px 12px; border-radius: 14px; }
  .fan--bare .fan__stage {
    -webkit-mask-image: linear-gradient(90deg, transparent 0%, #000 9%, #000 91%, transparent 100%);
    mask-image: linear-gradient(90deg, transparent 0%, #000 9%, #000 91%, transparent 100%);
  }
}
@media (prefers-reduced-motion: reduce) {
  .fan__card { transition: none; }
}
</style>
