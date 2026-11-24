<template>
  <!--
    ============================================================
    口碑分歧展厅 · 观众评分分化榜（右翼面板）· A24 影片展
    ------------------------------------------------------------
    用真实电影数据复刻 A24 的"概念化影片展"：
    · 主视觉 = 漂浮的**海报圆盘**（真实 TMDB 海报，CD 质感：盘芯孔 + 边缘高光）
      鼠标移上去 = 3D 倾斜（parallax），平时轻轻上下浮动，像活着的碟片
    · 编辑式 credits：DIRECTED BY / YEAR / 评分，细横线分隔（A24 档案表）
    · 媒体星级 ★★★★★（由 vote_average 折算，支持半星）
    · 两条真实引文 = 嘶吼式衬线大字 + 引号（A24 pull-quote），好评橙 / 差评青
    · 底部"圆盘索引"：前十部分歧影片的小圆盘，点选切换主视觉（榜单联动保留）
    数据全部来自 /insights/polarizing（评分标准差排名 + 真实引文）。
    ============================================================
  -->
  <div class="pb">
    <header class="pb__head">
      <span class="pb__eyebrow">RATING SPLIT · 同一部片，有人打满分有人打最低分</span>
      <span class="pb__cnt">{{ items.length }} 部吵得最凶</span>
    </header>

    <div class="pb__scroll">
      <Transition name="pb-swap" mode="out-in">
        <div v-if="cur" :key="cur.movie_id" class="pb__feat">
          <!-- 片名：A24 式大衬线标题（影片展的主角） -->
          <div class="pb__film">{{ cur.title }}<small v-if="cur.title_en"> · {{ cur.title_en }}</small></div>

          <!-- 海报圆盘：真实海报 + CD 质感（盘芯孔 + 边缘高光） -->
          <div
            class="disc"
            :style="discStyle"
            @pointermove="onTilt"
            @pointerleave="onUntilt"
          >
            <div class="disc__face" :style="posterBg(cur)">
              <!-- 有海报用 <img>（可捕获裂图），加载失败/无海报则回落到设计海报 -->
              <img
                v-if="posterOk(cur)"
                class="disc__img"
                :src="cur.poster_url"
                :alt="cur.title"
                @error="markFailed(cur.poster_url)"
              />
              <span v-else class="disc__ph">
                <em class="disc__ph-k">FILM POSTER</em>
                <b class="disc__ph-t">{{ cur.title }}</b>
                <em class="disc__ph-y">{{ cur.year || '—' }}</em>
              </span>
            </div>
            <i class="disc__hole" />
            <i class="disc__shine" />
          </div>

          <!-- 编辑式 credits（A24 档案表） -->
          <div class="credits">
            <div class="cr"><span class="cr__k">DIRECTED BY</span><span class="cr__v">{{ cur.director || '—' }}</span></div>
            <div class="cr"><span class="cr__k">YEAR</span><span class="cr__v">{{ cur.year || '—' }}</span></div>
            <div class="cr"><span class="cr__k">媒体均分</span><span class="cr__v">{{ fmt(cur.vote_average) }}</span></div>
            <div class="cr"><span class="cr__k">观众均分</span><span class="cr__v">{{ fmt(cur.avg_rating) }}</span></div>
            <div class="cr"><span class="cr__k">评价样本</span><span class="cr__v">{{ cur.review_count || 0 }} 条</span></div>
          </div>

          <!-- 媒体星级（由 vote_average/2 折算，支持半星） -->
          <div class="stars" :aria-label="`评分 ${fmt(cur.vote_average)} / 10`">
            <i v-for="(s, i) in stars" :key="i" class="star" :class="s">★</i>
            <span class="stars__num">{{ fmt(cur.vote_average) }}</span>
          </div>

          <!-- 观众 vs 媒体：两条对比条，一眼看出"专业口碑"和"观众口碑"的差距 -->
          <div class="cmp" aria-label="观众均分与媒体均分对比">
            <div class="cmp__row">
              <span class="cmp__k">观众</span>
              <span class="cmp__bar"><i :style="{ width: pct10(cur.avg_rating) }" /></span>
              <b class="cmp__v">{{ fmt(cur.avg_rating) }}</b>
            </div>
            <div class="cmp__row">
              <span class="cmp__k">媒体</span>
              <span class="cmp__bar cmp__bar--media"><i :style="{ width: pct10(cur.vote_average) }" /></span>
              <b class="cmp__v">{{ fmt(cur.vote_average) }}</b>
            </div>
          </div>

          <!-- 分化指数：本榜的分析指标（标准差越大越两极） -->
          <div class="divind">
            <span class="divind__k">分化指数</span>
            <span class="divind__v">{{ fmt(cur.std_dev) }}</span>
            <span class="divind__hint">· {{ cur.review_count }} 条评价</span>
          </div>

          <!-- 两条真实引文（A24 嘶吼式衬线） -->
          <figure v-if="cur.pos_quote" class="quote quote--pos">
            <blockquote>{{ cur.pos_quote.text }}</blockquote>
            <figcaption>好评 · 该观众打 {{ scoreOf(cur.pos_quote.rating) }} 分</figcaption>
          </figure>
          <figure v-if="cur.neg_quote" class="quote quote--neg">
            <blockquote>{{ cur.neg_quote.text }}</blockquote>
            <figcaption>差评 · 该观众打 {{ scoreOf(cur.neg_quote.rating) }} 分</figcaption>
          </figure>
          <p v-if="!cur.pos_quote && !cur.neg_quote" class="pb__empty">该片暂无足够长的真实引文</p>
        </div>
      </Transition>
    </div>

    <!-- 圆盘索引：前十部分歧影片，点选切换主视觉 -->
    <div class="idx" role="tablist" aria-label="分歧影片索引">
      <button
        v-for="(it, i) in items"
        :key="it.movie_id"
        type="button"
        class="idx__d"
        :class="{ on: i === sel }"
        :style="thumbBg(it)"
        :title="it.title"
        :aria-selected="i === sel"
        @click="sel = i"
      >
        <img
          v-if="posterOk(it)"
          class="idx__img"
          :src="it.poster_url"
          :alt="it.title"
          @error="markFailed(it.poster_url)"
        />
        <span v-else class="idx__no">{{ i + 1 }}</span>
      </button>
    </div>
  </div>
</template>

<script setup>
// ============================================================
// 观众评分分化 · A24 影片展（数据 /insights/polarizing）
// 圆盘 3D 倾斜：pointermove 写 --rx/--ry，transform 由 CSS 消费（与项目海报扇同款手法）
// ============================================================
import { computed, reactive, ref } from 'vue'

const props = defineProps({
  polarizing: { type: Object, default: null },
})

const items = computed(() => props.polarizing?.items || [])
const sel = ref(0)
const cur = computed(() => items.value[sel.value] || null)

const fmt = (n) => (n === null || n === undefined ? '—' : Number(n).toFixed(1))
const scoreOf = (r) => (r === null || r === undefined ? '?' : Math.round(Number(r)))
// 10 分制 → 百分比条宽
const pct10 = (n) => (n === null || n === undefined ? '0%' : `${Math.max(0, Math.min(100, Number(n) * 10))}%`)

// 媒体星级：vote_average(/10) → /5，支持半星
const stars = computed(() => {
  const v = (cur.value?.vote_average || 0) / 2
  return Array.from({ length: 5 }, (_, i) => {
    if (v >= i + 1) return 'full'
    if (v >= i + 0.5) return 'half'
    return 'empty'
  })
})

// 无海报时的极简海报：按片名/ID 哈希出一组双色渐变，
// 每部片颜色不同，看起来像一张设计过的概念海报，而不是空白盘。
function fallbackGradient(it) {
  const seed = String(it?.movie_id || it?.title || 'film')
  let h = 0
  for (const ch of seed) h = (h * 31 + ch.charCodeAt(0)) % 360
  const hi = `hsl(${(h + 46) % 360} 44% 58%)`
  const lo = `hsl(${h} 42% 32%)`
  return `radial-gradient(circle at 34% 26%, ${hi}, ${lo} 64%, #241c15 100%)`
}

// 记录裂图 URL：一旦 <img> 报错就切到设计海报，避免"有字段但图裂"又变空白盘
const failed = reactive(new Set())
const posterOk = (it) => !!(it?.poster_url && !failed.has(it.poster_url))
function markFailed(url) { if (url) failed.add(url) }

// 有真实海报时背景留空（由 <img> 呈现）；否则铺哈希渐变
function posterBg(it) {
  return posterOk(it) ? {} : { backgroundImage: fallbackGradient(it) }
}
function thumbBg(it) {
  return posterOk(it) ? {} : { backgroundImage: fallbackGradient(it) }
}

// 圆盘 3D 倾斜
const tilt = reactive({ x: 0, y: 0 })
const discStyle = computed(() => ({ '--rx': tilt.x + 'deg', '--ry': tilt.y + 'deg' }))
function onTilt(e) {
  const r = e.currentTarget.getBoundingClientRect()
  const px = (e.clientX - r.left) / r.width - 0.5
  const py = (e.clientY - r.top) / r.height - 0.5
  tilt.y = (px * 16).toFixed(2)   // 绕 Y 轴
  tilt.x = (-py * 14).toFixed(2)  // 绕 X 轴
}
function onUntilt() {
  tilt.x = 0
  tilt.y = 0
}
</script>

<style scoped>
.pb { display: flex; flex-direction: column; height: 100%; min-height: 0; }

.pb__head { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; padding: 2px 4px 9px; }
.pb__eyebrow {
  font-family: var(--u-font-tech); font-size: 9px; letter-spacing: .14em;
  color: var(--u-text-2); line-height: 1.3; text-transform: uppercase;
}
.pb__cnt { font-size: 10.5px; color: var(--u-gold); font-weight: 600; white-space: nowrap; flex: none; }

.pb__scroll { flex: 1; min-height: 0; overflow-y: auto; scrollbar-width: thin; padding: 2px 4px 6px; }

/* ---------- 主视觉：海报圆盘 ---------- */
.pb__feat { display: flex; flex-direction: column; align-items: center; text-align: center; }
.pb__film {
  font-family: "Kaiti SC", KaiTi, STKaiti, serif;
  font-size: 19px; font-weight: 700; line-height: 1.2; color: var(--u-text);
  margin: 2px 0 8px; max-width: 100%;
}
.pb__film small { display: block; font-family: var(--u-font-tech); font-size: 9px; letter-spacing: .12em; color: var(--u-text-2); margin-top: 2px; text-transform: uppercase; }
.disc {
  position: relative;
  width: 150px; height: 150px;
  margin: 4px 0 11px;
  border-radius: 50%;
  perspective: 700px;
  transform: rotateX(var(--rx, 0deg)) rotateY(var(--ry, 0deg));
  transition: transform .2s ease;
  cursor: pointer;
  flex: none;
}
.disc__face {
  position: absolute; inset: 0;
  border-radius: 50%;
  background-color: #efe7d6;
  border: 2px solid rgba(74, 40, 20, .35);
  box-shadow: inset 0 0 0 6px rgba(255, 253, 247, .25),
              inset 0 0 22px rgba(74, 40, 20, .28),
              0 10px 24px rgba(74, 40, 20, .28);
  overflow: hidden;
  animation: disc-bob 5.5s ease-in-out infinite;
}
@keyframes disc-bob {
  0%, 100% { transform: translateY(0) rotate(-.6deg); }
  50% { transform: translateY(-7px) rotate(.6deg); }
}
/* 无海报兜底：极简海报（胶片竖纹 + 衬线片名 + 年份），不再是空白盘 */
.disc__img {
  position: absolute; inset: 0;
  width: 100%; height: 100%;
  object-fit: cover;
  display: block;
}
.disc__ph {
  position: absolute; inset: 0;
  display: flex; flex-direction: column; align-items: center; justify-content: flex-end;
  gap: 3px; padding: 0 16px 22px; text-align: center;
  color: #FBF3E4;
  /* 下半部压暗：片名压在深色区上，浅底渐变也不会糊字；竖纹保留胶片感 */
  background-image:
    linear-gradient(to top, rgba(20, 14, 8, .62) 0%, rgba(20, 14, 8, 0) 48%),
    repeating-linear-gradient(90deg, rgba(255, 255, 255, .055) 0 2px, transparent 2px 8px);
}
.disc__ph-k {
  position: absolute; top: 24px; left: 0; right: 0;
  font-style: normal; font-family: var(--u-font-tech); font-size: 7.5px; letter-spacing: .3em; opacity: .72;
}
.disc__ph-t {
  font-family: "Kaiti SC", KaiTi, STKaiti, serif;
  font-size: 13px; font-weight: 700; line-height: 1.25;
  max-width: 100%;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  text-shadow: 0 2px 10px rgba(0, 0, 0, .7);
}
.disc__ph-y { font-style: normal; font-family: var(--u-font-tech); font-size: 8.5px; letter-spacing: .26em; opacity: .72; }
/* 盘芯孔 */
.disc__hole {
  position: absolute; left: 50%; top: 50%;
  width: 26px; height: 26px; transform: translate(-50%, -50%);
  border-radius: 50%;
  background: radial-gradient(circle at 40% 38%, #FBF6EC, #E7DCC6 70%, #D8C9AC);
  box-shadow: 0 0 0 4px rgba(255, 253, 247, .35), inset 0 1px 3px rgba(74,40,20,.4);
  pointer-events: none;
}
/* 边缘高光（碟片反光，不用 mix-blend-mode，避免手绘纸层合成问题） */
.disc__shine {
  position: absolute; inset: 0; border-radius: 50%; pointer-events: none;
  background: linear-gradient(125deg, rgba(255,255,255,.45) 0%, rgba(255,255,255,0) 30%, rgba(255,255,255,0) 68%, rgba(255,255,255,.2) 100%);
}
.disc:hover .disc__face { animation-play-state: paused; }

/* ---------- 编辑式 credits ---------- */
.credits { width: 100%; max-width: 250px; margin: 0 auto 8px; }
.cr {
  display: flex; justify-content: space-between; align-items: baseline; gap: 12px;
  padding: 4px 2px;
  border-bottom: 1px solid rgba(154, 96, 40, .22);
}
.cr:first-child { border-top: 1px solid rgba(154, 96, 40, .22); }
.cr__k { font-family: var(--u-font-tech); font-size: 8.5px; letter-spacing: .18em; color: var(--u-text-2); white-space: nowrap; }
.cr__v { font-size: 12px; font-weight: 700; color: var(--u-text); text-align: right; }

/* ---------- 媒体星级 ---------- */
.stars { display: flex; align-items: center; gap: 3px; margin: 2px 0 9px; }
.star { font-style: normal; font-size: 14px; line-height: 1; color: rgba(154, 96, 40, .28); }
.star.full { color: var(--u-gold); }
.star.half {
  color: transparent;
  background: linear-gradient(90deg, var(--u-gold) 50%, rgba(154, 96, 40, .28) 50%);
  -webkit-background-clip: text; background-clip: text;
}
.stars__num { font-size: 11px; font-weight: 700; color: var(--u-text-2); margin-left: 4px; }

/* ---------- 观众 vs 媒体 对比条 ---------- */
.cmp { width: 100%; max-width: 250px; margin: 2px auto 10px; display: flex; flex-direction: column; gap: 5px; }
.cmp__row { display: grid; grid-template-columns: 28px 1fr 26px; align-items: center; gap: 8px; }
.cmp__k { font-family: var(--u-font-tech); font-size: 8.5px; letter-spacing: .12em; color: var(--u-text-2); }
.cmp__bar { height: 6px; border-radius: 3px; background: rgba(120, 90, 50, .1); overflow: hidden; }
.cmp__bar i {
  display: block; height: 100%; border-radius: 3px;
  background: linear-gradient(90deg, rgba(15, 118, 110, .45), var(--u-orange));
  transition: width .9s cubic-bezier(.16, .84, .44, 1);
}
.cmp__bar--media i { background: linear-gradient(90deg, rgba(166, 124, 46, .5), var(--u-gold)); }
.cmp__v { font-family: var(--u-font-tech); font-size: 10px; font-weight: 700; color: var(--u-text); text-align: right; }

/* ---------- 分化指数 ---------- */
.divind {
  display: inline-flex; align-items: baseline; gap: 5px;
  padding: 3px 10px; margin-bottom: 12px;
  border: 1px solid rgba(194, 65, 12, .35); border-radius: 999px;
  background: rgba(194, 65, 12, .06);
}
.divind__k { font-family: var(--u-font-tech); font-size: 8.5px; letter-spacing: .16em; color: var(--u-orange); }
.divind__v { font-family: "Kaiti SC", KaiTi, STKaiti, serif; font-size: 16px; font-weight: 700; color: var(--u-orange); line-height: 1; }
.divind__hint { font-size: 9.5px; color: var(--u-text-2); }

/* ---------- 嘶吼式引文（A24 pull-quote） ---------- */
.quote { margin: 0 0 14px; text-align: left; }
.quote blockquote {
  margin: 0;
  font-family: "Kaiti SC", KaiTi, STKaiti, "Songti SC", serif;
  font-weight: 700;
  font-size: 14.5px;
  line-height: 1.5;
  color: #3A2E20;
  padding: 4px 0 4px 20px;
  position: relative;
  display: -webkit-box;
  -webkit-line-clamp: 4;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.quote blockquote::before {
  content: '“';
  position: absolute; left: -2px; top: -4px;
  font-family: Georgia, "Times New Roman", serif;
  font-size: 34px; line-height: 1;
}
.quote--pos blockquote::before { color: var(--u-orange); }
.quote--neg blockquote::before { color: var(--u-cyan); }
.quote figcaption {
  margin-top: 5px; padding-left: 20px;
  font-family: var(--u-font-tech); font-size: 8.5px; letter-spacing: .12em;
  text-transform: uppercase;
}
.quote--pos figcaption { color: var(--u-orange); }
.quote--neg figcaption { color: var(--u-cyan); }

.pb__empty { font-size: 11.5px; color: var(--u-text-2); text-align: center; padding: 18px 4px; }

/* ---------- 圆盘索引 ---------- */
.idx {
  flex: none;
  display: flex; gap: 7px; overflow-x: auto; padding: 9px 4px 4px;
  border-top: 1px solid rgba(154, 96, 40, .2);
  scrollbar-width: thin;
}
.idx__d {
  flex: 0 0 auto;
  width: 40px; height: 40px; border-radius: 50%;
  border: 2px solid transparent; background-color: #efe7d6;
  background-size: cover; background-position: center;
  cursor: pointer; padding: 0; position: relative;
  box-shadow: 0 2px 5px rgba(74, 40, 20, .2);
  transition: transform .15s ease, border-color .15s ease;
}
.idx__d:hover { transform: translateY(-3px); }
.idx__d.on { border-color: var(--u-orange); transform: translateY(-3px) scale(1.06); }
.idx__img {
  position: absolute; inset: 0;
  width: 100%; height: 100%;
  object-fit: cover;
  border-radius: 50%;
  display: block;
}
.idx__no {
  position: absolute; inset: 0; display: flex; align-items: center; justify-content: center;
  font-family: "Kaiti SC", KaiTi, serif; font-size: 13px; font-weight: 700;
  color: #FBF3E4; text-shadow: 0 1px 6px rgba(0, 0, 0, .5);
}

/* 切换交叉淡入 */
.pb-swap-enter-active, .pb-swap-leave-active { transition: opacity .26s ease, transform .26s ease; }
.pb-swap-enter-from { opacity: 0; transform: translateY(10px); }
.pb-swap-leave-to { opacity: 0; transform: translateY(-6px); }

@media (prefers-reduced-motion: reduce) {
  .disc__face { animation: none; }
  .pb-swap-enter-active, .pb-swap-leave-active { transition: none; }
}
</style>
