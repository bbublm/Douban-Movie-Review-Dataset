<script setup>
// ============================================================
// Hero 光盘展台（复刻 a24.raviklaassens.com 的实体 CD 效果）
//
// 那个站的招牌不是「黑胶横墙」，而是把电影海报印在一张实体光盘上：
//   · 圆形盘面 = 影片海报
//   · 盘心 = 半透明白色塑料轮毂 + 中心孔（真实 CD 的塑料件）
//   · 塑料高光 = conic-gradient 反光 + 斜向光带，缓慢游走
//   · 换片时整盘旋转，像把盘翻过来换一张
// 这里放在首页 Hero 的右侧预留列里，不占额外滚动高度，Hero 原有内容完全不动。
// ============================================================
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

const props = defineProps({
  movies: { type: Array, default: () => [] },
  // 自动换片间隔（ms）
  interval: { type: Number, default: 5200 },
})

const router = useRouter()
const list = computed(() => (props.movies || []).filter((m) => m && m.title).slice(0, 12))
const idx = ref(0)
const cur = computed(() => list.value[idx.value] || null)

// 累计旋转角度：每次换片再转 200°，配合淡入淡出像「盘片转过去」
const spin = ref(0)
// 拖拽中的实时角度（松手后并入 spin，不回弹）
const drag = ref(0)
const spinning = ref(false)
let spinTimer = null
let autoTimer = null

const hovered = ref(false)
const dragging = ref(false)
// 悬停/拖拽时暂停自动换片与反光自转
const halted = computed(() => hovered.value || dragging.value)

// 指针倾斜（鼠标在盘面上移动时的 3D 微倾，让盘「活」起来）
const tilt = ref({ x: 0, y: 0 })
const cdEl = ref(null)
const cdStyle = computed(() => ({
  transform: `rotate(${spin.value + drag.value}deg) rotateX(${tilt.value.x}deg) rotateY(${tilt.value.y}deg)`,
  width: cdSize.value ? cdSize.value + 'px' : null,
}))

// 盘径自适应：Hero 是定高 banner，盘太大就会把「片名 + 控件」顶出 Hero。
// 按 Hero 实际高度 - 文案预留 120px，再与列宽取小，保证永不溢出。
const hdEl = ref(null)
const colEl = ref(null)
const cdSize = ref(0)
let ro = null
function fitCd() {
  const host = hdEl.value
  const col = colEl.value
  if (!host || !col) return
  const h = host.clientHeight
  if (!h) return
  const size = Math.min(300, col.clientWidth, h - 120)
  cdSize.value = Math.max(150, Math.round(size))
}

let reduced = false

const year = computed(() => cur.value?.year || cur.value?.release_year || '')
const genre = computed(() => (cur.value?.genres_zh || [])[0] || '')
const rating = computed(() => {
  const r = cur.value?.rating
  return typeof r === 'number' && r > 0 ? r.toFixed(1) : ''
})
// 没有海报时的兜底：取片名首字 + 暖棕渐变盘面
const failed = ref([]) // 图片加载失败过的 movie_id（海报代理偶发 502）
const noPoster = computed(() => !cur.value?.poster_url || failed.value.includes(cur.value?.movie_id))
function markFail(id) {
  if (id && !failed.value.includes(id)) failed.value = [...failed.value, id]
}

/* ---------- 换片 ---------- */
function wrap(i) {
  const len = list.value.length
  return ((i % len) + len) % len
}

function pulseSpin() {
  if (reduced) return
  spinning.value = true
  clearTimeout(spinTimer)
  spinTimer = setTimeout(() => { spinning.value = false }, 1200)
}

function step(dir = 1) {
  const len = list.value.length
  if (len < 2) return
  idx.value = wrap(idx.value + dir)
  if (!reduced) {
    // 每次换片转整圈：转完海报始终是正的（转 200° 会越换越歪）
    spin.value += 360 * dir
    pulseSpin()
  }
  startAuto()
}

// 圆点直达：按相对位置决定转的方向
function goTo(i) {
  const len = list.value.length
  if (!len || i === idx.value) return
  const dir = i > idx.value ? 1 : -1
  idx.value = wrap(i)
  if (!reduced) {
    spin.value += 360 * dir
    pulseSpin()
  }
  startAuto()
}

function startAuto() {
  stopAuto()
  if (reduced || list.value.length < 2) return
  autoTimer = setInterval(() => { if (!halted.value) step(1) }, props.interval)
}
function stopAuto() {
  if (autoTimer) clearInterval(autoTimer)
  autoTimer = null
}

function openMovie() {
  if (cur.value?.movie_id) router.push(`/movie/${encodeURIComponent(cur.value.movie_id)}`)
}

/* ---------- 拖拽旋转 ---------- */
const dragState = { active: false, lastAngle: 0, moved: 0 }
let suppressClick = false

function angleAt(el, e) {
  const r = el.getBoundingClientRect()
  const deg = Math.atan2(e.clientY - (r.top + r.height / 2), e.clientX - (r.left + r.width / 2)) * 180 / Math.PI
  return deg
}

function onPointerDown(e) {
  if (e.pointerType === 'mouse' && e.button !== 0) return
  if (list.value.length < 2) return
  dragState.active = true
  dragState.lastAngle = angleAt(e.currentTarget, e)
  dragState.moved = 0
  drag.value = 0
  dragging.value = true
  tilt.value = { x: 0, y: 0 }
  // 捕获指针：鼠标移出盘面也不断连
  try { e.currentTarget.setPointerCapture(e.pointerId) } catch { /* ignore */ }
}

function onPointerMove(e) {
  const el = e.currentTarget
  if (!dragState.active) {
    if (reduced) return
    const r = el.getBoundingClientRect()
    const px = (e.clientX - r.left) / r.width - 0.5
    const py = (e.clientY - r.top) / r.height - 0.5
    tilt.value = { x: -py * 9, y: px * 9 }
    return
  }
  const a = angleAt(el, e)
  let d = a - dragState.lastAngle
  if (d > 180) d -= 360
  else if (d < -180) d += 360
  dragState.lastAngle = a
  drag.value += d
  dragState.moved += Math.abs(d)
}

function endDrag(e) {
  if (!dragState.active) return
  dragState.active = false
  dragging.value = false
  try { e.currentTarget.releasePointerCapture?.(e.pointerId) } catch { /* ignore */ }

  const total = drag.value
  const turns = Math.round(-total / 120) // 每拖过约 120° 记一次切片（向左拖 = 下一张）
  if (turns !== 0 && list.value.length > 1) idx.value = wrap(idx.value + turns)

  // 松手吸附：盘面转到最近的整圈，海报回到正立（不吸附会越拖越歪）
  let target = Math.round((spin.value + total) / 360) * 360
  if (turns !== 0 && !reduced) {
    target += 360 * Math.sign(turns)
    pulseSpin()
  }
  spin.value = target
  drag.value = 0

  // 拖过就不当作点击，避免误跳详情页
  if (dragState.moved > 7) {
    suppressClick = true
    setTimeout(() => { suppressClick = false }, 320)
  }
  startAuto()
}

function onLeave() {
  hovered.value = false
  tilt.value = { x: 0, y: 0 }
}

function onClick() {
  if (suppressClick) return
  openMovie()
}

/* ---------- 键盘 ---------- */
function onKeydown(e) {
  if (e.key === 'ArrowLeft') { e.preventDefault(); step(-1) }
  else if (e.key === 'ArrowRight') { e.preventDefault(); step(1) }
}

/* ---------- 触控板横滑切片（竖向滚轮放行，不抢页面滚动） ---------- */
let wheelLock = 0
function onWheel(e) {
  if (Math.abs(e.deltaX) <= Math.abs(e.deltaY) * 1.2) return
  e.preventDefault()
  const now = Date.now()
  if (now - wheelLock < 300) return
  wheelLock = now
  step(e.deltaX > 0 ? 1 : -1)
}

// 光盘元素是 v-if 渲染的（数据异步到达），因此监听随元素出现/消失绑定
watch(cdEl, (el, prev) => {
  if (prev) prev.removeEventListener('wheel', onWheel)
  if (el) el.addEventListener('wheel', onWheel, { passive: false })
}, { flush: 'post' })

// 根节点尺寸变化（Hero 高度、窗口缩放、字体）时重算盘径
watch(hdEl, (el) => {
  if (ro) ro.disconnect()
  if (!el || !ro) return
  ro.observe(el)
  fitCd()
}, { flush: 'post' })

watch(() => list.value.length, () => { idx.value = 0; startAuto() })

onMounted(() => {
  reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  ro = new ResizeObserver(() => fitCd())
  if (hdEl.value) ro.observe(hdEl.value)
  fitCd()
  startAuto()
})
onBeforeUnmount(() => {
  stopAuto()
  clearTimeout(spinTimer)
  if (ro) ro.disconnect()
  if (cdEl.value) cdEl.value.removeEventListener('wheel', onWheel)
})
</script>

<template>
  <div v-if="cur" ref="hdEl" class="hd">
    <div ref="colEl" class="hd__col">
      <button
        ref="cdEl"
        class="cd"
        type="button"
        :style="cdStyle"
        :class="{ 'is-spinning': spinning, 'is-dragging': dragging }"
        :title="`拖动可旋转 · 点击查看《${cur.title}》`"
        @click="onClick"
        @pointerdown="onPointerDown"
        @pointermove="onPointerMove"
        @pointerup="endDrag"
        @pointercancel="endDrag"
        @pointerenter="hovered = true"
        @pointerleave="onLeave"
        @focus="hovered = true"
        @blur="onLeave"
        @keydown="onKeydown"
      >
        <!-- 盘面：海报印在光盘上 -->
        <span class="cd__platter">
          <Transition name="cd-fade">
            <img
              v-if="!noPoster"
              :key="cur.movie_id"
              class="cd__art"
              :src="cur.poster_url"
              :alt="cur.title"
              loading="eager"
              draggable="false"
              @error="markFail(cur.movie_id)"
            />
            <span v-else :key="cur.movie_id" class="cd__art cd__art--empty">
              {{ (cur.title || '影').slice(0, 1) }}
            </span>
          </Transition>

          <!-- 印刷在塑料上的压暗 + 环形纹理，让盘面不「平」 -->
          <span class="cd__tint" />
          <span class="cd__grooves" />
          <!-- 塑料反光：随盘缓慢游走 -->
          <span class="cd__sheen" :class="{ 'is-paused': halted }" />
          <span class="cd__gloss" />
          <!-- 盘心塑料轮毂 + 中心孔 -->
          <span class="cd__hub" />
          <span class="cd__hole" />
          <!-- 盘缘 -->
          <span class="cd__rim" />
        </span>
      </button>

      <!-- 片名 / 年份 / 类型 / 评分（对标参考站左侧的影片信息） -->
      <button class="hd__cap" type="button" @click="onClick">
        <span class="hd__cap-title">{{ cur.title }}</span>
        <span class="hd__cap-meta">
          <template v-if="year">{{ year }}</template>
          <template v-if="genre"> · {{ genre }}</template>
          <template v-if="rating"> · ★{{ rating }}</template>
        </span>
      </button>

      <!-- 手动交互：左右换片 + 圆点直达 -->
      <div class="hd__ctrl">
        <button class="hd__arrow" type="button" aria-label="上一张" @click="step(-1)">‹</button>
        <div class="hd__dots">
          <button
            v-for="(m, i) in list"
            :key="m.movie_id"
            type="button"
            class="hd__dot"
            :class="{ 'is-on': i === idx }"
            :aria-label="`第 ${i + 1} 张：${m.title}`"
            :aria-current="i === idx"
            @click="goTo(i)"
          />
        </div>
        <button class="hd__arrow" type="button" aria-label="下一张" @click="step(1)">›</button>
        <p class="hd__hint">拖动旋转 · 箭头切换 · 点击看详情</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* 覆盖层：铺满 Hero，但不吃鼠标事件；只有光盘可点 */
.hd {
  position: absolute;
  inset: 0;
  z-index: 2;
  pointer-events: none;
}

/* 光盘列：贴右，在 Hero 高度内垂直居中
   （撑满 Hero 而不是靠 50% 位移，否则盘一大就会顶出 banner） */
.hd__col {
  position: absolute;
  top: 0;
  right: 24px;
  bottom: 0;
  width: var(--hd-w, 280px);
  /* 底部多留一点：操作提示浮在控件下方时不贴 Hero 底边 */
  padding: 10px 0 30px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 8px;
  /* 指针微倾的透视基准 */
  perspective: 900px;
}

/* ---------- 光盘本体 ---------- */
.cd {
  width: 100%;
  aspect-ratio: 1 / 1;
  padding: 0;
  border: 0;
  background: none;
  border-radius: 50%;
  pointer-events: auto;
  cursor: grab;
  /* 横向拖动由组件接管，纵向留给页面滚动 */
  touch-action: pan-y;
  transform-origin: 50% 50%;
  transform-style: preserve-3d;
  transition: transform 1.15s cubic-bezier(0.22, 0.8, 0.24, 1), filter 0.3s ease;
  filter: drop-shadow(0 22px 30px rgba(20, 12, 4, 0.45)) drop-shadow(0 4px 8px rgba(0, 0, 0, 0.3));
  will-change: transform;
}
.cd:hover { filter: drop-shadow(0 26px 38px rgba(20, 12, 4, 0.5)) drop-shadow(0 0 0 1px rgba(212, 175, 55, 0.35)); }
.cd:focus-visible { outline: 2px solid rgba(212, 175, 55, 0.9); outline-offset: 6px; }
/* 拖拽中：取消过渡（否则跟手会「拖泥带水」），光标变抓紧 */
.cd.is-dragging {
  cursor: grabbing;
  transition: filter 0.3s ease;
}

.cd__platter {
  position: absolute;
  inset: 0;
  border-radius: 50%;
  overflow: hidden;
  isolation: isolate;
  background: radial-gradient(circle at 34% 28%, #6b5540, #33291d 60%, #17120c);
}

.cd__art {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: cover;
  /* 海报放大一点，避免圆形裁切后主体被切掉 */
  transform: scale(1.02);
  user-select: none;
}
.cd__art--empty {
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 64px;
  font-weight: 800;
  color: rgba(255, 248, 236, 0.9);
  letter-spacing: 0.1em;
  background: radial-gradient(circle at 35% 30%, #8b6b4a, #4a3a28 65%, #2a2016);
}

/* 盘面压暗 + 中心发亮，模拟印刷在塑料基材上 */
.cd__tint {
  position: absolute;
  inset: 0;
  border-radius: 50%;
  background:
    radial-gradient(circle at 50% 50%, rgba(255, 255, 255, 0.14) 0 12%, rgba(255, 255, 255, 0) 30%),
    radial-gradient(circle at 50% 50%, rgba(0, 0, 0, 0) 46%, rgba(0, 0, 0, 0.22) 88%, rgba(0, 0, 0, 0.4) 100%),
    linear-gradient(200deg, rgba(255, 255, 255, 0.1), rgba(0, 0, 0, 0.12) 55%, rgba(0, 0, 0, 0.28));
  pointer-events: none;
}

/* 极细同心沟槽：玻璃盘才有的质感，肉眼几乎不可见但能「立住」 */
.cd__grooves {
  position: absolute;
  inset: 0;
  border-radius: 50%;
  background: repeating-radial-gradient(
    circle at 50% 50%,
    rgba(255, 255, 255, 0.05) 0 0.5px,
    rgba(0, 0, 0, 0.05) 0.5px 1.6px
  );
  opacity: 0.55;
  pointer-events: none;
}

/* 塑料扇形反光：慢速自转（不转盘面，只转这层光） */
.cd__sheen {
  position: absolute;
  inset: 0;
  border-radius: 50%;
  pointer-events: none;
  mix-blend-mode: screen;
  background: conic-gradient(
    from 0deg,
    rgba(255, 255, 255, 0) 0deg,
    rgba(255, 245, 225, 0.28) 34deg,
    rgba(255, 255, 255, 0.06) 74deg,
    rgba(255, 255, 255, 0) 120deg,
    rgba(255, 255, 255, 0) 210deg,
    rgba(255, 246, 230, 0.2) 252deg,
    rgba(255, 255, 255, 0) 300deg,
    rgba(255, 255, 255, 0) 360deg
  );
  animation: cd-sheen 11s linear infinite;
}
.cd__sheen.is-paused { animation-play-state: paused; }

/* 一道斜向高光带，真实塑料件的镜面反射 */
.cd__gloss {
  position: absolute;
  inset: 0;
  border-radius: 50%;
  pointer-events: none;
  background: linear-gradient(
    104deg,
    rgba(255, 255, 255, 0) 38%,
    rgba(255, 255, 255, 0.16) 44%,
    rgba(255, 255, 255, 0.34) 47%,
    rgba(255, 255, 255, 0.12) 51%,
    rgba(255, 255, 255, 0) 58%
  );
  mix-blend-mode: screen;
}

/* 盘心塑料轮毂：外径 26%、中心孔 14.5%（照参考站实测比例 120mm/15mm 附近）
   颜色是中性银灰 + 斜面，而不是纯白，否则会像贴纸不像塑料件 */
.cd__hub {
  position: absolute;
  left: 50%;
  top: 50%;
  width: 26%;
  aspect-ratio: 1;
  transform: translate(-50%, -50%);
  border-radius: 50%;
  pointer-events: none;
  background:
    radial-gradient(
      circle at 50% 50%,
      rgba(255, 255, 255, 0) 0 54%,
      rgba(246, 248, 250, 0.95) 56% 60%,
      rgba(214, 219, 225, 0.92) 62% 78%,
      rgba(236, 239, 242, 0.95) 80% 90%,
      rgba(178, 184, 191, 0.55) 94% 100%
    ),
    conic-gradient(
      from 214deg,
      rgba(160, 168, 176, 0.5),
      rgba(255, 255, 255, 0.85) 18%,
      rgba(196, 203, 210, 0.45) 42%,
      rgba(255, 255, 255, 0.7) 62%,
      rgba(170, 178, 186, 0.5) 82%,
      rgba(160, 168, 176, 0.5)
    );
  box-shadow:
    inset 0 1px 2px rgba(255, 255, 255, 0.9),
    inset 0 -1px 3px rgba(90, 84, 74, 0.45),
    0 1px 6px rgba(0, 0, 0, 0.35);
}

/* 中心孔：真实 CD 是通孔，透出后面的背景 */
.cd__hole {
  position: absolute;
  left: 50%;
  top: 50%;
  width: 14.5%;
  aspect-ratio: 1;
  transform: translate(-50%, -50%);
  border-radius: 50%;
  pointer-events: none;
  background: radial-gradient(circle, rgba(12, 8, 4, 0.98) 0 58%, rgba(34, 25, 15, 0.96) 100%);
  box-shadow:
    0 0 0 1px rgba(255, 255, 255, 0.75),
    inset 0 2px 5px rgba(0, 0, 0, 0.95),
    inset 0 -1px 2px rgba(255, 255, 255, 0.2);
}

/* 盘缘：一圈很细的亮边 + 内侧阴影 */
.cd__rim {
  position: absolute;
  inset: 0;
  border-radius: 50%;
  pointer-events: none;
  box-shadow:
    inset 0 0 0 1px rgba(255, 255, 255, 0.5),
    inset 0 0 0 2px rgba(0, 0, 0, 0.12),
    inset 0 0 18px rgba(0, 0, 0, 0.35);
}

/* 换片：整盘自转 + 新海报淡入（参考站换片就是这个观感） */
.cd-fade-enter-active { transition: opacity 0.55s ease 0.12s; }
.cd-fade-leave-active { transition: opacity 0.4s ease; position: absolute; }
.cd-fade-enter-from { opacity: 0; }
.cd-fade-leave-to { opacity: 0; }

/* ---------- 片名/元信息 ---------- */
.hd__cap {
  pointer-events: auto;
  border: 0;
  background: none;
  padding: 2px 6px 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 3px;
  cursor: pointer;
  color: #fff;
  max-width: 100%;
  border-top: 1px solid rgba(255, 255, 255, 0.22);
  transition: border-color 0.25s, transform 0.25s;
}
.hd__cap:hover { border-color: rgba(212, 175, 55, 0.85); transform: translateY(-1px); }
.hd__cap-title {
  font-size: 13.5px;
  font-weight: 700;
  letter-spacing: 0.04em;
  max-width: 100%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  color: #fff;
  text-shadow: 0 1px 6px rgba(0, 0, 0, 0.5);
}
.hd__cap-meta {
  font-size: 11px;
  letter-spacing: 0.08em;
  color: rgba(255, 255, 255, 0.72);
}

/* ---------- 手动交互：左右箭头 + 圆点 ---------- */
.hd__ctrl {
  position: relative;
  pointer-events: auto;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 2px 0 0;
}
.hd__arrow {
  width: 22px;
  height: 22px;
  padding: 0;
  display: grid;
  place-items: center;
  border: 1px solid rgba(255, 255, 255, 0.28);
  border-radius: 50%;
  background: rgba(0, 0, 0, 0.18);
  color: rgba(255, 255, 255, 0.85);
  font-size: 14px;
  line-height: 1;
  cursor: pointer;
  transition: background 0.25s, border-color 0.25s, color 0.25s, transform 0.25s;
}
.hd__arrow:hover {
  border-color: rgba(212, 175, 55, 0.85);
  background: rgba(212, 175, 55, 0.22);
  color: #fff;
  transform: scale(1.08);
}
.hd__arrow:active { transform: scale(0.94); }

.hd__dots {
  display: flex;
  align-items: center;
  gap: 5px;
}
.hd__dot {
  width: 5px;
  height: 5px;
  padding: 0;
  border: 0;
  border-radius: 50%;
  background: rgba(255, 255, 255, 0.3);
  cursor: pointer;
  transition: background 0.25s, width 0.25s, border-radius 0.25s;
}
.hd__dot:hover { background: rgba(255, 255, 255, 0.65); }
.hd__dot.is-on {
  width: 14px;
  border-radius: 3px;
  background: rgba(212, 175, 55, 0.95);
}

/* 操作提示：默认隐身，鼠标进到 Hero 光盘区才浮现，绝对定位不占布局高度 */
.hd__hint {
  position: absolute;
  left: 0;
  right: 0;
  bottom: -17px;
  margin: 0;
  text-align: center;
  font-size: 11px;
  letter-spacing: 0.05em;
  white-space: nowrap;
  color: rgba(255, 255, 255, 0.78);
  text-shadow: 0 1px 4px rgba(0, 0, 0, 0.5);
  opacity: 0;
  transition: opacity 0.3s ease;
  pointer-events: none;
}
.hd__col:hover .hd__hint { opacity: 1; }

@keyframes cd-sheen {
  to { transform: rotate(360deg); }
}

/* 窄屏不展示（Hero 中部空间不够，避免压住搜索框） */
@media (max-width: 1279px) {
  .hd { display: none; }
}
/* 减弱动效：不自动换片、不转光 */
@media (prefers-reduced-motion: reduce) {
  .cd { transition: none; }
  .cd__sheen { animation: none; }
}
</style>
