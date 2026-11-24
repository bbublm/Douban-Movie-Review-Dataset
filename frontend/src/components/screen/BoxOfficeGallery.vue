<!--
  票房分析展厅 · 中央画廊（参考 itomdev.com/gallery 的相框绳效果）
  ============================================================
  视觉契约（itomdev 原版）：手绘相框用木夹挂在晾衣绳上，滚轮沿线漂移浏览，
  点相框弹出大纸卡看详情。本组件保持该交互骨架，视觉换成本项目的暖纸棕金
  设计系统（原版是铅笔灰，我们有既定红线，不照搬颜色）。

  交互要点：
  · 滚轮/触摸：整条相框绳横向漂移（rAF 阻尼，松手滑行）
  · 相框常驻轻摇（transform-origin 在木夹处，像被风吹）
  · 点相框 → 详情纸卡（抖边 + 硬阴影 + 弹簧入场）；Esc / 点背卡外关闭
  · ≤900px：退化为原生横向滚动条（触摸友好），放弃滚轮漂移
  · 禁 mix-blend-mode（Chrome 合成层雷，见 MEMORY.md）

  数据契约：props 来自 /api/v1/insights/box-office，
  gallery 已按票房倒序取前 N 部；roi 缺预算时为 null（老片常态，不编数）。
-->
<template>
  <div class="bog" :class="{ 'is-mobile': isNarrow }">
    <!-- 总览条：收录数 / 总票房 / 最旺年份 -->
    <div class="bog__summary">
      <span class="bog__stat">收录影片 <b>{{ totalMovies }}</b> 部</span>
      <span class="bog__stat">合计 <b>{{ yi(totalRevenue) }}</b> 亿美元</span>
      <span class="bog__stat">最旺年份 <b>{{ topYear || '—' }}</b></span>
      <span class="bog__hint">滚轮沿绳浏览 · 点相框看详情</span>
    </div>

    <!-- 晾衣绳 + 相框绳 -->
    <div ref="scene" class="bog__scene" @wheel.prevent="onWheel">
      <svg class="bog__line" viewBox="0 0 1000 40" preserveAspectRatio="none" aria-hidden="true">
        <path d="M0 8 Q 500 30 1000 8" fill="none" stroke="#8B6B47" stroke-width="2.2"
          stroke-linecap="round" opacity="0.75" />
        <path d="M0 8 Q 500 30 1000 8" fill="none" stroke="#FFFDF7" stroke-width="0.9"
          stroke-linecap="round" opacity="0.5" stroke-dasharray="5 7" />
      </svg>

      <div class="bog__rail" :style="{ transform: `translate3d(${offset}px,0,0)` }">
        <button
          v-for="(g, i) in gallery"
          :key="g.movie_id"
          class="bog__frame"
          type="button"
          :class="{ 'is-sel': sel && sel.movie_id === g.movie_id }"
          :style="{ '--sd': `${(i % 5) * 0.7}s`, '--tilt': `${(i % 3 - 1) * 0.8}deg` }"
          @click="sel = g"
        >
          <i class="bog__pin" aria-hidden="true" />
          <span class="bog__mat">
            <img v-if="g.poster_url" :src="g.poster_url" :alt="g.title" loading="lazy"
              decoding="async" @error="onPosterError" />
            <i v-else class="bog__no-poster">🎞<em>{{ g.title }}</em></i>
          </span>
          <b class="bog__cap">{{ g.title }}</b>
          <em class="bog__rev">{{ yi(g.revenue) }} 亿<template v-if="g.roi"> · ROI {{ g.roi }}×</template></em>
        </button>
      </div>

      <!-- 绳尾提示：滚到尽头给个反馈 -->
      <div v-if="atEdge" class="bog__edge">{{ edgeHint }}</div>
    </div>

    <!-- 详情纸卡：itomdev 的 PROJECT DETAILS 等价物 -->
    <Transition name="bog-card">
      <div v-if="sel" class="bog-card" @click.self="sel = null">
        <div class="bog-card__paper">
          <button class="bog-card__x" type="button" aria-label="关闭" @click="sel = null">✕</button>
          <div class="bog-card__head">
            <span class="bog-card__kicker">BOX OFFICE · 票房档案</span>
            <h4 class="bog-card__title">{{ sel.title }}</h4>
            <p class="bog-card__sub">
              {{ sel.title_en || '' }}<template v-if="sel.title_en && sel.year"> · </template>{{ sel.year || '年份不详' }}
              <template v-if="sel.genres.length"> · {{ sel.genres.join(' / ') }}</template>
            </p>
          </div>
          <div class="bog-card__grid">
            <div class="bog-card__cell">
              <i>全球票房</i><b>{{ yi(sel.revenue) }} 亿美元</b>
            </div>
            <div class="bog-card__cell">
              <i>制作预算</i><b>{{ sel.budget ? yi(sel.budget) + ' 亿美元' : '暂无数据' }}</b>
            </div>
            <div class="bog-card__cell">
              <i>投资回报</i><b :class="{ 'is-hot': (sel.roi || 0) >= 5 }">{{ sel.roi ? sel.roi + ' 倍' : '暂无数据' }}</b>
            </div>
            <div class="bog-card__cell">
              <i>观众评分</i><b>{{ sel.vote_average ?? '—' }}</b>
            </div>
          </div>
          <div class="bog-card__foot">
            <RouterLink class="bog-card__link" :to="`/movie/${encodeURIComponent(sel.movie_id)}`">
              查看影片详情 →
            </RouterLink>
          </div>
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup>
/* ============================================================
   票房画廊：滚轮漂移 + rAF 阻尼（复用海报扇的成熟套路）
   ============================================================ */
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'

const props = defineProps({
  gallery: { type: Array, default: () => [] },
  totalMovies: { type: Number, default: 0 },
  totalRevenue: { type: Number, default: 0 },
  topYear: { type: Number, default: null },
  /* 左翼票房榜点选联动：外部把某部影片推进来，画廊打开它的档案卡 */
  pick: { type: Object, default: null },
})

/* 美元 → 亿美元（保留一位小数；个位数不带 .0） */
function yi(usd) {
  const v = (usd || 0) / 1e8
  return v >= 10 ? Math.round(v) : Math.round(v * 10) / 10
}

/* ---------- 窄屏降级：原生横向滚动，放弃滚轮漂移 ---------- */
const isNarrow = ref(false)
let mq = null
function syncNarrow() { isNarrow.value = !!mq && mq.matches }
onMounted(() => {
  mq = window.matchMedia('(max-width: 900px)')
  syncNarrow()
  mq.addEventListener?.('change', syncNarrow)
})
onBeforeUnmount(() => mq?.removeEventListener?.('change', syncNarrow))

/* ---------- 滚轮漂移：目标位 + 阻尼逼近（松手滑行） ---------- */
const scene = ref(null)
const offset = ref(0)
let target = 0
const MIN_LEFT = -1400   // 相框绳可向左拖出的上限（24 帧 × ~118px 起）
let raf = 0

function clampOffset(v) {
  const el = scene.value
  if (!el) return Math.min(0, Math.max(MIN_LEFT, v))
  // 轨道实际宽度由内容决定：露不出最后一段就到底
  const rail = el.querySelector('.bog__rail')
  const over = rail ? rail.scrollWidth - el.clientWidth : 0
  const minX = -Math.max(0, over) - 8
  return Math.min(8, Math.max(minX, v))
}

function tick() {
  const d = target - offset.value
  if (Math.abs(d) < 0.4) {
    offset.value = target
    raf = 0
    return
  }
  offset.value += d * 0.12
  raf = requestAnimationFrame(tick)
}
function ensureRaf() { if (!raf) raf = requestAnimationFrame(tick) }

function onWheel(e) {
  if (isNarrow.value) return          // 窄屏交给原生触摸滚动
  target = clampOffset(target - e.deltaY * 0.9)
  ensureRaf()
}

/* 绳尾反馈：拖到任一端显示提示 */
const atEdge = computed(() => Math.abs(offset.value - clampOffset(offset.value)) < 1.5
  && Math.abs(offset.value) > 4)
const edgeHint = computed(() => offset.value >= -4 ? '← 起点已到' : '已到绳尾 →')

/* ---------- 详情卡 ---------- */
const sel = ref(null)
/* 左翼榜单点选 → 打开同一部的档案卡（pick 由外部传入） */
watch(() => props.pick, (g) => { if (g) sel.value = g })
function onKey(e) { if (e.key === 'Escape') sel.value = null }
onMounted(() => window.addEventListener('keydown', onKey))
onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKey)
  if (raf) cancelAnimationFrame(raf)
})

/* 海报加载失败：清 src 让 v-if 切占位（@error 里改 props 无效，直接操作 DOM） */
function onPosterError(e) { e.target.style.display = 'none' }
</script>

<style scoped>
/* ============================================================
   暖纸底 + 晾衣绳场景。所有圆角用手绘"抖边" Tricks
   （itomdev 签名：border-radius: 2px 255px 3px / 255px 5px 225px 3px 系），
   配 4px 硬阴影 —— 纸感来自"不完美的边 + 实心影"，不是渐变。
   ============================================================ */
.bog {
  position: relative;
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  padding: 8px 14px 12px;
  border-radius: 20px;
  background:
    radial-gradient(120% 80% at 50% 0%, rgba(255, 252, 244, 0.92), rgba(250, 245, 235, 0) 60%),
    linear-gradient(180deg, #FDFAF3 0%, #F8F2E6 60%, #F3EADA 100%);
  border: 1px solid var(--border, rgba(139, 69, 19, 0.18));
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.85), 0 10px 30px rgba(139, 69, 19, 0.07);
  overflow: hidden;
}

/* ---------- 总览条 ---------- */
.bog__summary {
  display: flex;
  align-items: baseline;
  flex-wrap: wrap;
  gap: 6px 18px;
  padding: 2px 4px 10px;
  border-bottom: 1.5px dashed rgba(139, 107, 71, 0.35);
}
.bog__stat { font-size: 12.5px; color: var(--u-text-2, #7D6B52); letter-spacing: 0.03em; }
.bog__stat b { font-size: 16px; color: #8B4513; margin: 0 2px; font-weight: 800; }
.bog__hint { margin-left: auto; font-size: 11.5px; color: rgba(125, 107, 82, 0.85); }
.bog__hint::before { content: '🖱 '; }

/* ---------- 场景 ---------- */
.bog__scene {
  position: relative;
  flex: 1;
  min-height: 0;
  margin-top: 8px;
  /* 横向滚动交给滚轮漂移（transform），纵向在相框高于视区时允许滚动，
     保证相框下半截（片名 / 票房）永不被裁切 */
  overflow-x: hidden;
  overflow-y: auto;
}
.bog__line {
  position: absolute;
  left: -2%;
  right: -2%;
  top: 0;
  width: 104%;
  height: 34px;
  z-index: 3;
  pointer-events: none;
}
.bog__rail {
  position: relative;
  left: 0;
  margin-top: 6px;
  display: flex;
  align-items: flex-start;
  gap: 26px;
  padding: 0 40px;
  will-change: transform;
}

/* ---------- 相框 ---------- */
.bog__frame {
  position: relative;
  flex: 0 0 auto;
  width: 104px;
  padding: 14px 8px 10px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 5px;
  background: #FFFDF7;
  border: 2.4px solid #6B4E2E;
  /* 抖边：每帧都"不一样圆"，像手画的 */
  border-radius: 3px 14px 5px 16px / 16px 4px 15px 5px;
  box-shadow: 4px 5px 0 rgba(107, 78, 46, 0.18);
  cursor: pointer;
  transform-origin: 50% -14px;      /* 摇点在木夹上 */
  animation: bog-sway 5.2s ease-in-out infinite;
  animation-delay: var(--sd, 0s);
  transition: transform 0.22s ease, box-shadow 0.22s ease, border-color 0.22s ease;
}
.bog__frame:nth-child(even) { border-radius: 15px 4px 17px 5px / 5px 16px 4px 15px; }
.bog__frame:hover {
  transform: translateY(-3px) rotate(var(--tilt, 0deg)) scale(1.03);
  border-color: #C2410C;
  box-shadow: 5px 7px 0 rgba(194, 65, 12, 0.22);
}
.bog__frame.is-sel { border-color: #C2410C; box-shadow: 5px 7px 0 rgba(194, 65, 12, 0.3); }
@keyframes bog-sway {
  0%, 100% { transform: rotate(calc(var(--tilt, 0deg) - 0.7deg)); }
  50%      { transform: rotate(calc(var(--tilt, 0deg) + 0.7deg)); }
}

/* 木夹：相框顶端的小夹子 */
.bog__pin {
  position: absolute;
  top: -11px;
  left: 50%;
  transform: translateX(-50%) rotate(-4deg);
  width: 16px;
  height: 22px;
  background: linear-gradient(180deg, #B08954, #8B6B47);
  border: 1.6px solid #5C4326;
  border-radius: 3px 3px 6px 6px;
  box-shadow: 0 2px 3px rgba(74, 40, 20, 0.25);
  z-index: 2;
}
.bog__pin::after {   /* 夹子上的小铆钉 */
  content: '';
  position: absolute;
  left: 50%;
  top: 5px;
  transform: translateX(-50%);
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background: #5C4326;
}

/* 相框纸边 + 海报：固定高度（不再按 2:3 撑高），整体收一档，
   画廊压窄后相框仍能完整落进场景，片名/票房不裁切 */
.bog__mat {
  display: block;
  width: 100%;
  height: 84px;
  overflow: hidden;
  background: #F1E8D8;
  border: 1.4px solid rgba(107, 78, 46, 0.45);
  border-radius: 2px 8px 3px 9px / 9px 3px 8px 2px;
}
.bog__mat img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
  opacity: 0;
  animation: bog-img-in 0.4s ease forwards;
}
@keyframes bog-img-in { to { opacity: 1; } }
.bog__no-poster {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  height: 100%;
  font-style: normal;
  font-size: 22px;
  color: rgba(139, 69, 19, 0.5);
  padding: 6px;
  text-align: center;
}
.bog__no-poster em {
  font-size: 10.5px;
  font-style: normal;
  line-height: 1.3;
  color: rgba(125, 107, 82, 0.9);
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

/* 相框下的手写caption */
.bog__cap {
  max-width: 100%;
  font-size: 12px;
  font-weight: 700;
  color: #4A3423;
  text-align: center;
  line-height: 1.25;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.bog__rev {
  font-size: 11px;
  font-style: normal;
  color: #C2410C;
  font-weight: 700;
  letter-spacing: 0.02em;
}

/* 绳尾提示 */
.bog__edge {
  position: absolute;
  right: 10px;
  bottom: 2px;
  font-size: 11px;
  color: rgba(125, 107, 82, 0.8);
  background: rgba(255, 253, 247, 0.85);
  border: 1px dashed rgba(139, 107, 71, 0.4);
  border-radius: 12px;
  padding: 3px 10px;
}

/* ---------- 详情纸卡（itomdev PROJECT DETAILS 等价物） ---------- */
.bog-card {
  position: absolute;
  inset: 0;
  z-index: 10;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(74, 52, 35, 0.28);
}
.bog-card__paper {
  position: relative;
  width: min(460px, 88%);
  max-height: 86%;
  overflow: auto;
  padding: 22px 24px 18px;
  background: #FFFDF7;
  border: 2.6px solid #4A3423;
  border-radius: 6px 22px 8px 24px / 24px 7px 22px 8px;   /* 抖边大纸卡 */
  box-shadow: 8px 9px 0 rgba(74, 52, 35, 0.22);
}
.bog-card__x {
  position: absolute;
  top: 10px;
  right: 12px;
  width: 26px;
  height: 26px;
  border: 1.6px solid rgba(107, 78, 46, 0.5);
  border-radius: 50% 46% 52% 48%;
  background: #FFFDF7;
  color: #6B4E2E;
  font-size: 12px;
  cursor: pointer;
}
.bog-card__x:hover { border-color: #C2410C; color: #C2410C; }
.bog-card__kicker {
  font-size: 10.5px;
  font-weight: 800;
  letter-spacing: 0.18em;
  color: #A67C2E;
}
.bog-card__title {
  margin: 4px 0 2px;
  font-size: 22px;
  line-height: 1.15;
  color: #3A2E20;
}
.bog-card__sub { margin: 0 0 14px; font-size: 12px; color: var(--u-text-2, #7D6B52); }
.bog-card__grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
  padding: 12px;
  background: #F8F2E6;
  border: 1.6px dashed rgba(139, 107, 71, 0.45);
  border-radius: 4px 12px 5px 14px / 14px 5px 12px 4px;
}
.bog-card__cell { display: flex; flex-direction: column; gap: 2px; }
.bog-card__cell i { font-style: normal; font-size: 11px; color: var(--u-text-2, #7D6B52); }
.bog-card__cell b { font-size: 16.5px; color: #4A3423; }
.bog-card__cell b.is-hot { color: #C2410C; }
.bog-card__foot {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 14px;
}
.bog-card__link {
  font-size: 13px;
  font-weight: 800;
  color: #FFF6E9;
  text-decoration: none;
  padding: 8px 16px;
  background: linear-gradient(160deg, #A0522D, #8B4513);
  border: 1.4px solid rgba(255, 246, 233, 0.55);
  border-radius: 25px;
  box-shadow: 0 3px 10px rgba(139, 69, 19, 0.38);
}
.bog-card__link:hover { filter: brightness(1.08); }

/* 纸卡弹簧入场 */
.bog-card-enter-active { transition: transform 0.34s cubic-bezier(0.34, 1.56, 0.64, 1), opacity 0.24s ease; }
.bog-card-leave-active { transition: transform 0.18s ease, opacity 0.18s ease; }
.bog-card-enter-from, .bog-card-leave-to { transform: scale(0.82) translateY(14px); opacity: 0; }

/* ---------- 窄屏：原生横向滚动（触摸友好） ---------- */
.bog.is-mobile .bog__scene { overflow-x: auto; scroll-snap-type: x mandatory; -webkit-overflow-scrolling: touch; }
.bog.is-mobile .bog__rail { transform: none !important; }
.bog.is-mobile .bog__frame { scroll-snap-align: center; animation-duration: 7s; }
.bog.is-mobile .bog__hint { display: none; }

/* ---------- 减弱动效 ---------- */
@media (prefers-reduced-motion: reduce) {
  .bog__frame { animation: none; transform: rotate(var(--tilt, 0deg)); }
  .bog__rail { transition: none; }
  .bog-card-enter-active, .bog-card-leave-active { transition-duration: 0.12s; }
}
</style>
