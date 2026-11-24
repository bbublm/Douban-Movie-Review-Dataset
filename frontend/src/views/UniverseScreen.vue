<template>
  <!--
    ============================================================
    电影盒子 · 影评洞察大屏（全屏 HUD）
    ------------------------------------------------------------
    用户 2026-10-19 定调：影评洞察页 = 这个数据分析大屏本体，
    不做纵向长网页。100vh 一屏、零滚动条，全部真实数据（ES 聚合）。

    两层：
      大厅（默认）：手绘影院外墙，五扇门 = 五个分类，推门进展厅（itomdev.com 式房间导航）
      展厅：顶部馆内导览（回大厅/门牌直达）+ 中央图表 + 左翼 + 右翼 + 底部真实影评流
    ============================================================
  -->
  <div ref="root" class="dashboard-container" :class="{ 'is-room': mode === 'room', 'is-scroll': isScroll }">

    <!-- ========== 背景：电影海报墙（仅数据展厅；星图厅自带 3D 星系背景） ========== -->
    <MovieBackdrop v-if="isScroll" :movies="movies" />
    <!-- 鼠标暖光：跟随指针的柔光，给长页一点"活"的感觉（A24 式） -->
    <div v-if="isScroll" class="room-spotlight" aria-hidden="true" />
    <!-- 长页滚动进度：顶栏下沿一条金色细线 -->
    <div v-if="isScroll" class="room-progress" aria-hidden="true"><i /></div>

    <!-- ========== 底层：3D 粒子星系（图表模式下压暗不卸载） ========== -->
    <div class="three-canvas-layer" :class="{ 'is-dim': mode !== 'room' || view !== 'galaxy' }">
      <!-- 深空背板：浅色页面上给粒子一块可见的"夜空"（椭圆盘=星系本体形状，
           边缘羽化融入暖白页面；没有它 NormalBlending 的粒子会被白底洗没） -->
      <div class="galaxy-bg" aria-hidden="true" />
      <GalaxyStage :movies="movies" :paused="hudHover || mode !== 'room' || view !== 'galaxy'" />
    </div>

    <!-- ========== 大厅层：A24 编辑式首页，六间展厅作章节索引（推门进入对应展厅） ========== -->
    <InsightHouse
      v-if="mode === 'house'"
      class="house-layer"
      :rooms="VIEWS"
      :cards="story?.cards || []"
      :posters="hallPosters"
      :start-open="houseOpened"
      @enter="enterRoom"
      @open="houseOpened = true"
      @close="houseOpened = false"
    />

    <!-- ========== 上层：悬浮 HUD（大厅模式下只留顶栏，其余区块收起） ========== -->
    <div class="hud-layer">

      <!-- ---- 01 顶部状态栏 ---- -->
      <header class="top-bar" @pointerenter="hudHover = true" @pointerleave="hudHover = false">
        <!-- 回大厅：放进吸顶状态栏内（滚动时不会压住下面的数据卡；
             高对比实底渐变 + 手绘抖边，暖白纸上始终看得见） -->
        <button v-show="mode === 'room'" class="room-nav__back" type="button" @click="backToHouse">← 回大厅</button>
        <div class="top-bar__brand">
          <span class="top-bar__logo">影评洞察</span>
          <span class="top-bar__sub">实时数据分析大屏</span>
        </div>
        <div class="top-bar__spacer" />
        <div class="top-bar__meta">
          <span>影评 <b class="top-bar__num"><RollingNumber :value="reviewTotal" :duration="2000" /></b> 条</span>
          <span>影片 <b class="top-bar__num"><RollingNumber :value="movieTotal" :duration="1800" /></b> 部</span>
          <span class="top-bar__live"><i class="top-bar__dot" />实时</span>
        </div>
        <button class="top-bar__btn" type="button" @click="toggleFs">⛶ 全屏</button>
      </header>

      <!-- 大厅模式：悬浮导览图按钮（itomdev 汉堡钮位）。合盒阶段先不给导览图，
           否则五间展厅会从地图里提前泄露；开封后才出现 -->
      <button v-show="mode === 'house' && houseOpened" class="house-map-btn" type="button" @click="mapOpen = true">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 4 3 6v14l6-2 6 2 6-2V4l-6 2-6-2zM9 4v14M15 6v14" /></svg>
        <span>导览图</span>
      </button>

      <!-- ---- 02 中央图表剧场（Flourish 式动态图表） ---- -->
      <!-- 标签栏常驻可见（用户反馈：星系视图下上方看不到切换入口）：
           星系视图只显示标签、不显示图表面板；切到图表视图再展开面板 -->
      <!-- 馆内导览：回大厅 / 当前展厅门牌 / 串门 / 六扇门直达
           （原 16s 自动轮播停用：房间是"走进去"的，不该自己换房） -->
      <div v-show="mode === 'room'" class="stage-dock" :class="{ 'is-wide': !curView.left.length && !curView.right.length }" @pointerenter="hudHover = true" @pointerleave="hudHover = false">
        <div class="room-nav">
          <!-- 回大厅按钮已移到页面左上角（见下方 .room-nav__back），此处仅留导览图 + 门牌 -->
          <button class="room-nav__map" type="button" aria-label="打开导览图" title="导览图" @click="mapOpen = true">
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M9 4 3 6v14l6-2 6 2 6-2V4l-6 2-6-2zM9 4v14M15 6v14" /></svg>
          </button>

          <div class="room-nav__plate">
            <i class="room-nav__icon">{{ curView.icon }}</i>
            <b>{{ curView.zh }}</b>
          </div>
          <!-- 每个展厅相互独立：进展厅后只保留「回大厅」出口，不提供串门 / 门牌直达，
               避免在一个门里跳转到其他门的数据（用户 2026-10-22 要求做分离）；
               换展厅请走「回大厅」或导览图 -->
        </div>
        <!-- 星图厅：3D 星系在底层透出，这里只放一张悬浮读图卡 + 右上情感分布卡 -->
        <GalaxyRoom
          v-if="view === 'galaxy'"
          v-sketch="{ sel:'.float-card', stagger:0.08, maxDelay:0.9 }"
          :avg-rating="avgRating"
          :arm-count="armCount"
          :sentiment="sentiment"
          :lexicon="lexicon"
          :stats="galaxyStats"
          :movies="movies"
          :knowledge="knowledge"
        />

        <!-- 其余展厅：每间各自一套排版（专属舞台组件），玻璃面板仅作承托 -->
        <div v-else class="stage-panel" :class="{ 'stage-panel--bare': view !== 'box' }">
          <div class="stage-panel__inner">
            <Transition name="stage-fade" mode="out-in">
              <BoxOfficeStage
                v-if="view === 'box'"
                :gallery="boxOffice?.gallery || []"
                :total-movies="boxOffice?.total_movies || 0"
                :total-revenue="boxOffice?.total_revenue || 0"
                :top-year="boxOffice?.top_year"
                :years="boxOffice?.years || []"
                :pick="boxPick"
                :correlations="correlations"
                @pick="boxPick = $event"
              />
              <RankRoom v-else-if="view === 'rank'" :matrix="matrix" :douban="douban" :sentiment="sentiment" :movies="movies" :correlations="correlations" :movie-total="movieTotal" :review-total="reviewTotal" />
              <FlowRoom v-else-if="view === 'flow'" :matrix="matrix" :trends="trends" :regions="regions" :douban="douban" :movies="movies" :flows="flows" :movie-total="movieTotal" :review-total="reviewTotal" />
              <DivergeRoom
                v-else-if="view === 'diverge'"
                :divergence="douban?.rating_divergence || []"
                :polarizing="polarizing"
                :douban="douban"
                :correlations="correlations"
                :movie-total="movieTotal"
                :review-total="reviewTotal"
              />
            </Transition>
          </div>
        </div>
      </div>

      <!-- ---- 06 底部真实影评流 ---- -->
      <footer
        v-show="mode === 'room'"
        class="bottom-bar"
        @pointerenter="hudHover = true"
        @pointerleave="hudHover = false"
      >
        <div class="bottom-bar__head">
          <span>◈ 影评流</span>
          <span>· 中文影评 · {{ reviews.length }} 条</span>
        </div>
        <div class="bottom-bar__track">
          <!-- 恒速滚动：时长由 JS 按轨道实测宽度反推（streamDur），内容增减速度不变 -->
          <div class="stream-track" :style="{ animationDuration: streamDur }">
            <span v-for="(c, i) in loopChips" :key="'s' + i" class="stream-chip">
              <i
                class="stream-chip__tag"
                :class="c.tone === 'neg' ? 'stream-chip__tag--neg' : 'stream-chip__tag--pos'"
              >{{ c.tone === 'neg' ? '差评' : '好评' }}</i><b v-if="c.title" class="stream-chip__title">《{{ c.title }}》</b>{{ c.text }}
            </span>
          </div>
        </div>
      </footer>

    </div>

    <!-- 馆长洞察卡已收编进大厅底部（见 InsightHouse 内的 HallInsights），此处不再单独渲染 -->

    <!-- 手绘导览图（itomdev MAP 面板）：大厅=传送地图，展厅=当前位置 + 回大厅 -->
    <InsightMap
      v-if="mapOpen"
      :rooms="VIEWS"
      :mode="mode"
      :current="view"
      @enter="onMapEnter"
      @back="onMapBack"
      @close="mapOpen = false"
    />
  </div>
</template>

<script setup>
// ============================================================
// 影评洞察大屏 /screen（用户定调：洞察页 = 数据分析大屏本体）
//   · 数据：sentiment / trends / matrix / boxOffice / lexicon / movies / reviews /
//     全部真实接口（matrix = ES 类型×年代聚合；boxOffice = ES 票房
//     聚合 + TOP 影片，2026-10-22 起替代原「类型竞赛」展厅）
//   · 视图：星图（3D 粒子，悬停可读单部影片）/ 票房（itomdev 式相框绳画廊）/
//     排名（口碑变化）/ 流向（桑基）/ 分歧（豆瓣对比）
//   · 3D 层切走时只压暗不卸载：反复销毁 WebGL context 会掉显存
// ============================================================
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import gsap from 'gsap'
import { api } from '../api'
import GalaxyStage from '../components/screen/GalaxyStage.vue'
import BoxOfficeStage from '../components/screen/BoxOfficeStage.vue'
import GalaxyRoom from '../components/screen/GalaxyRoom.vue'
import RankRoom from '../components/screen/RankRoom.vue'
import FlowRoom from '../components/screen/FlowRoom.vue'
import DivergeRoom from '../components/screen/DivergeRoom.vue'
import EchoChamber from '../components/screen/EchoChamber.vue'
import GenreRankCard from '../components/screen/GenreRankCard.vue'
import CoveragePanel from '../components/screen/CoveragePanel.vue'
import RollingNumber from '../components/screen/RollingNumber.vue'
import InsightHouse from '../components/screen/InsightHouse.vue'
import InsightMap from '../components/screen/InsightMap.vue'
import MovieBackdrop from '../components/screen/MovieBackdrop.vue'

const root = ref(null)
const hudHover = ref(false)

const movies = ref([])
const sentiment = ref(null)
const trends = ref(null)
const matrix = ref(null)
const boxOffice = ref(null)  // 票房分析（/insights/box-office）
const boxPick = ref(null)    // 左翼票房榜点选 → 中央画廊打开同一部档案
const lexicon = ref(null)
const reviews = ref([])
const douban = ref(null)    // 豆瓣联合洞察（/douban/insights，并入本大屏）
const story = ref(null)        // 大厅馆长洞察卡（/insights/story）
const polarizing = ref(null)   // 观众评分分化榜（/insights/polarizing）
const regions = ref(null)      // 国家/地区画像（/insights/regions）
const hallPosters = ref([])    // 走廊挂画：按类型聚合挑出的真实代表片
const knowledge = ref(null)    // 影人×类型知识图谱（共现 + lift）
const correlations = ref(null) // Pearson 矩阵 / 回归 / ROI 四分位 / 类型画像
const flows = ref(null)        // 类型→年代→口碑档三层流向 + 热力

const reviewTotal = computed(() => sentiment.value?.total || 0)
const movieTotal = computed(() => trends.value?.total_movies || 0)

/* ---------- 星图图例统计（与 GalaxyStage 内部同口径） ---------- */
const avgRating = computed(() => {
  const ms = movies.value
  return ms.length ? ms.reduce((s, m) => s + (Number(m.rating) || 0), 0) / ms.length : 0
})
const armCount = computed(() => {
  const c = new Map()
  for (const m of movies.value) {
    const g = (m.genres_zh || [])[0] || '其他'
    c.set(g, (c.get(g) || 0) + 1)
  }
  return Math.min(6, c.size)
})
/* 星图速览卡：与 GalaxyStage 同口径，但额外给出「最多类型」便于填掉左侧空白 */
const galaxyStats = computed(() => {
  const ms = movies.value
  const c = new Map()
  for (const m of ms) {
    const g = (m.genres_zh || [])[0] || '其他'
    c.set(g, (c.get(g) || 0) + 1)
  }
  const top = [...c.entries()].sort((a, b) => b[1] - a[1])[0]
  return {
    count: ms.length,
    avg: avgRating.value,
    arms: armCount.value,
    topGenre: top ? top[0] : '—',
    topCount: top ? top[1] : 0,
  }
})

/* ---------- 视图切换（含 16s 自动轮播） ---------- */
// 命名原则（用户 2026-10-19）：从用户视角说清"这是做什么的"，不用抽象词
/* 房间（展厅）与大厅
   itomdev.com 的房间式导航：大屏的五个分类 = 五扇门，推开就是一间展厅。
   glow = 门缝里透出的展厅光，desc = 门牌提示（悬停时显示在底部条）。
   每间展厅各自一套排版（见下方 <Transition> 的专属舞台组件），不再共用"左中右三块"。 */
/* 五间展厅：每间各自一套排版（不再共用"左中右三块"）。
   left / right 全部清空 —— 旧的两翼面板已废弃，各房改用专属舞台组件
   （见下方 <Transition> 的 GalaxyRoom / RankRoom / FlowRoom / DivergeRoom）。 */
const VIEWS = [
  { key: 'galaxy', zh: '口碑星图', icon: '🌌', desc: '每颗星是一部影片，越亮越热', glow: '#3B2F63', tint: '#6D28D9',
    left: [], right: [] },
  { key: 'box', zh: '票房分析', icon: '🎬', desc: '全球票房 TOP 挂在绳上，点框看档案', glow: '#8B4513', tint: '#C2410C',
    left: [], right: [] },
  { key: 'rank', zh: '口碑排名', icon: '📈', desc: '各类型口碑位次变化', glow: '#A0522D', tint: '#B45309',
    left: [], right: [] },
  { key: 'flow', zh: '年代流向', icon: '🌊', desc: '类型与年代之间的影片流向', glow: '#0F766E', tint: '#0F766E',
    left: [], right: [] },
  { key: 'diverge', zh: '口碑分歧', icon: '⚖️', desc: '豆瓣评分和这里的口碑，不一定一致', glow: '#7D3C1E', tint: '#A67C2E',
    left: [], right: [] },
]

const view = ref('galaxy')

/* house = 大厅（六扇门）；room = 展厅（图表 + 两翼面板）。
   每个展厅相互独立：进展厅后只能「回大厅」再进其他门，展厅内不提供跳到其他展厅的入口。 */
const mode = ref('house')
/* 是否已经开过电影盒子：合盒首屏不显示导览图，回大厅/深链返回时保持已开状态 */
const houseOpened = ref(false)
const roomIdx = computed(() => Math.max(0, VIEWS.findIndex((v) => v.key === view.value)))
const curView = computed(() => VIEWS[roomIdx.value] || VIEWS[0])

/* 数据展厅 = 可纵向滚动的长页（用户 2026-11-02："数据页面可以加长，不用固定页面大小"）。
   星图厅是 3D 全景，保持一屏不滚；大厅也保持一屏。 */
const isScroll = computed(() => mode.value === 'room' && view.value !== 'galaxy')

/* 切房/回大厅时把滚动位置归零，避免带着上一间展厅的滚动偏移进来 */
function resetScroll() {
  nextTick(() => {
    if (root.value) root.value.scrollTop = 0
  })
}

function enterRoom(key) {
  view.value = key
  mode.value = 'room'
  resetScroll()
  playRoomIntro()
}
function backToHouse() {
  revealIO?.disconnect()
  revealIO = null
  mode.value = 'house'
  resetScroll()
}
/* 导览图（itomdev MAP 面板）：大厅模式点房间=传送进门；展厅模式只回大厅 */
const mapOpen = ref(false)
function onMapEnter(key) {
  mapOpen.value = false
  enterRoom(key)
}
function onMapBack() {
  mapOpen.value = false
  backToHouse()
}

/* 展厅入场：从大厅推门进来，各区块错峰落位（与大厅的推近动画首尾相接） */
function playRoomIntro() {
  nextTick(() => {
    gsap.from(['.room-nav'], { y: -18, opacity: 0, duration: 0.55, ease: 'power2.out' })
    gsap.from(['.stage-panel'], { y: 20, opacity: 0, duration: 0.6, delay: 0.08, ease: 'power2.out' })
    gsap.from(['.bottom-bar'], { y: 30, opacity: 0, duration: 0.6, delay: 0.24, ease: 'power2.out' })
    // Transition(mode=out-in) 有换场时间：错开两次调用，确保新房间的卡片都挂上了
    setTimeout(setupReveal, 80)
    setTimeout(setupReveal, 460)
  })
}

/* 两遍拼接实现无缝循环（内容相同，位移 -50% 时视觉无跳变） */
const chips = computed(() => reviews.value.map((r) => ({
  title: r.title,
  text: r.text,
  tone: r.sentiment === 'negative' ? 'neg' : 'pos',
})))
const loopChips = computed(() => (chips.value.length ? [...chips.value, ...chips.value] : []))

/* ---------- 影评流恒速（用户三次反馈"太快/慢一点"） ----------
   固定秒数在内容量变化时会漂：174 条长文 + 95s 实测 1319px/s（≈110 字/秒），
   快成老虎机。改为测量轨道实际宽度，按恒定像素速度反推 animation-duration：
   45px/s ≈ 3.5 字/秒（比 75px/s 再降四成，中文慢读节奏），内容增减速度恒定。
   注意 keyframes 位移是 -50%（一圈=一份 chips），所以每圈内容宽 = scrollWidth/2。 */
const STREAM_PX_PER_SEC = 45
const streamDur = ref('160s') // CSS 兜底值：JS 测量完成前先用它
watch(loopChips, async () => {
  await nextTick()
  const track = document.querySelector('.stream-track')
  if (!track) return
  const oneLoop = track.scrollWidth / 2 // 位移 -50% = 一份内容的宽度
  if (oneLoop > 0) streamDur.value = `${Math.max(60, Math.round(oneLoop / STREAM_PX_PER_SEC))}s`
}, { flush: 'post' })

/* 中文影评兜底打标：库内中文影评 sentiment 多为 None，
   用高频情感词做轻量判断（负面词优先——负面表达更具体、误判成本更低） */
const ZH_NEG = ['烂', '差劲', '难看', '无聊', '失望', '尴尬', '睡着', '催眠', '糟蹋', '狗血', '退票', '翻车', '吐槽', '莫名其妙', '看不下去', '浪费']
const ZH_POS = ['好看', '精彩', '震撼', '经典', '推荐', '喜欢', '感动', '完美', '神作', '惊喜', '优秀', '封神', '治愈', '牛', '杰作', '不错']
function guessZhTone(text) {
  const t = text || ''
  if (ZH_NEG.some((w) => t.includes(w))) return 'negative'
  if (ZH_POS.some((w) => t.includes(w))) return 'positive'
  return 'positive' // 无明显倾向时按好评计（流式氛围位，不承担判定职责）
}
/** CJK 字符占比：>0.3 视为中文文本（兜底过滤，即使脏数据绕过 lang 也不会漏进流里） */
function cjkRatio(text) {
  const t = (text || '').replace(/\s/g, '')
  if (!t) return 0
  let n = 0
  for (const ch of t) if (ch >= '\u4e00' && ch <= '\u9fff') n++
  return n / t.length
}

/* ---------- 展厅动效：鼠标暖光跟随 + 滚动视差变量 + 首屏外卡片渐入 ---------- */
let spotRaf = 0
let revealIO = null

/* 首屏之下的卡片先藏起来，滚到跟前再浮上来（A24 的"逐段揭示"节奏）。
   ★ 只在本容器内观察；JS 失效时卡片默认可见（隐藏类只由 JS 添加）。 */
function setupReveal() {
  revealIO?.disconnect()
  revealIO = null
  if (!isScroll.value || !root.value) return
  const cards = root.value.querySelectorAll('.float-card, .box-stage__extras')
  if (!cards.length) return
  revealIO = new IntersectionObserver((entries) => {
    for (const e of entries) {
      if (!e.isIntersecting) continue
      e.target.classList.add('is-revealed')
      revealIO?.unobserve(e.target)
    }
  }, { root: root.value, rootMargin: '0px 0px -70px 0px', threshold: 0.01 })

  const fold = window.innerHeight - 40
  for (const c of cards) {
    if (c.getBoundingClientRect().top > fold) {
      c.classList.add('is-below')
      revealIO.observe(c)
    }
  }
}

function onSpotMove(e) {
  if (spotRaf) return
  spotRaf = requestAnimationFrame(() => {
    spotRaf = 0
    const el = root.value
    if (!el || !isScroll.value) return
    el.style.setProperty('--mx', `${e.clientX}px`)
    el.style.setProperty('--my', `${e.clientY}px`)
  })
}
function onRoomScroll() {
  const el = root.value
  if (!el) return
  el.style.setProperty('--u-scroll', String(el.scrollTop))
  const max = el.scrollHeight - el.clientHeight
  el.style.setProperty('--u-progress', max > 0 ? String(Math.min(1, el.scrollTop / max)) : '0')
}
function bindRoomMotion() {
  const el = root.value
  if (!el) return
  el.addEventListener('pointermove', onSpotMove, { passive: true })
  el.addEventListener('scroll', onRoomScroll, { passive: true })
}

onMounted(async () => {
  document.body.classList.add('u-body-lock')
  document.documentElement.classList.add('u-body-lock')
  bindRoomMotion()
  // 大厅模式：只落顶栏（两翼/底带属于展厅，等推门时再由 playRoomIntro 落位）
  gsap.from(['.top-bar'], { y: -26, opacity: 0, duration: 0.7, ease: 'power2.out' })

  // 深链直达展厅：/screen?room=rank（答辩演示/回归脚本用，避免每次从大厅点进去）
  const q = new URLSearchParams(location.search).get('room')
  if (q && VIEWS.some((v) => v.key === q)) {
    view.value = q
    mode.value = 'room'
    houseOpened.value = true   // 深链已经进过展厅，回大厅不必再开一次盒
    playRoomIntro()
  }

  // 星系粒子：4 页并发（单页上限 50）
  const pages = await Promise.all(
    [1, 2, 3, 4].map((page) =>
      api.searchMovies({ size: 50, sort: 'popularity', with_facets: false, page }).catch(() => null),
    ),
  )
  const seen = new Set()
  const all = []
  for (const r of pages) {
    for (const m of r?.hits || []) {
      if (seen.has(m.movie_id)) continue
      seen.add(m.movie_id)
      all.push(m)
    }
  }
  movies.value = all

  // 面板数据
  api.sentimentStats().then((d) => { sentiment.value = d }).catch(() => {})
  api.trends().then((d) => { trends.value = d }).catch(() => {})
  api.matrix().then((d) => { matrix.value = d }).catch(() => {})
  // 票房分析（2026-10-22：替代原「类型竞赛」展厅）
  api.boxOffice(24).then((d) => { boxOffice.value = d }).catch(() => {})
  api.lexicon(40).then((d) => { lexicon.value = d }).catch(() => {})
  // 豆瓣联合洞察（评分分歧 / 情感 / 高分 / 预告覆盖 / 类型情感）—— 并入本大屏
  api.doubanInsights().then((d) => { douban.value = d }).catch(() => {})
  // 馆长洞察卡 + 评分分化榜 + 地区画像（2026-11-01 新增分析展厅数据源）
  api.story().then((d) => { story.value = d }).catch(() => {})
  api.polarizing().then((d) => { polarizing.value = d }).catch(() => {})
  api.regions().then((d) => { regions.value = d }).catch(() => {})
  // 深度分析四路（2026-11-04）：全部 ES 实时聚合 / 现算统计，失败静默降级
  api.hallPosters().then((d) => { hallPosters.value = d?.items || [] }).catch(() => {})
  api.knowledgeGraph().then((d) => { knowledge.value = d }).catch(() => {})
  api.correlations().then((d) => { correlations.value = d }).catch(() => {})
  api.flows().then((d) => { flows.value = d }).catch(() => {})

  // 底部真实影评流（中文化：lang=zh 走索引 lang 字段，库内共 87 条中文影评，
  // 取两页拿全；CJK 比例兜底过滤防脏数据；sentiment 为 None 的中文影评用
  // 内置情感词表前端打标，不再出现英文原文）
  try {
    const pages = await Promise.all(
      [1, 2].map((page) =>
        api.searchReviews({ q: null, lang: 'zh', size: 50, sort: 'relevance', with_facets: false, page }).catch(() => null),
      ),
    )
    const all = []
    for (const r of pages) for (const h of r?.hits || []) all.push(h)
    reviews.value = all
      .filter((r) => cjkRatio(r.text) > 0.3)
      .map((r) => ({
        title: (r.movie_title || '').trim(),
        text: (r.text || '').replace(/[*_>#`]+/g, '').replace(/\s+/g, ' ').trim().slice(0, 48) || '（空文本）',
        sentiment: r.sentiment || guessZhTone(r.text),
      }))
  } catch { /* 影评流不可用时静默降级，不影响大屏其余模块 */ }

  // 数据到位后布局会长高：再扫一遍首屏外卡片（否则票房页第三层不会被标记）
  setTimeout(setupReveal, 500)
  setTimeout(setupReveal, 1400)
})

onBeforeUnmount(() => {
  document.body.classList.remove('u-body-lock')
  document.documentElement.classList.remove('u-body-lock')
  revealIO?.disconnect()
  revealIO = null
  const el = root.value
  if (el) {
    el.removeEventListener('pointermove', onSpotMove)
    el.removeEventListener('scroll', onRoomScroll)
  }
  if (spotRaf) cancelAnimationFrame(spotRaf)
})

function toggleFs() {
  if (document.fullscreenElement) document.exitFullscreen()
  else root.value?.requestFullscreen?.().catch(() => {})
}
</script>

<style scoped>
/* 面板内内容需要撑满高度 */
.panel-scroll > :deep(*) { height: 100%; }

/* 大厅层：盖在星系 3D 之上、HUD 之下（顶栏靠 DOM 顺序压在它上面） */
.house-layer { z-index: 2; }

/* ---------- 馆内导览条（房间模式顶部） ---------- */
.room-nav {
  flex: none;
  display: flex;
  align-items: center;
  justify-content: center;
  /* 允许换行：屏幕变窄时导览条会被挤出舞台区（stage-dock 左右各让 388px） */
  flex-wrap: wrap;
  row-gap: 6px;
  gap: 10px;
  margin-bottom: 12px;
  padding: 6px 12px;
  background: rgba(255, 253, 247, 0.92);
  border: 1.4px solid rgba(107, 78, 46, 0.32);
  border-radius: 26px;
  box-shadow: 0 6px 18px rgba(74, 40, 20, 0.14);
  backdrop-filter: blur(6px);
}
.room-nav button {
  font-family: inherit;
  cursor: pointer;
  border-radius: 20px;
  border: 1.2px solid rgba(107, 78, 46, 0.34);
  background: rgba(255, 253, 247, 0.9);
  color: #6B4E2E;
  transition: background 0.2s ease, color 0.2s ease, transform 0.16s ease;
}
.room-nav button:hover { background: #8B4513; color: #FFF6E9; transform: translateY(-1px); }

/* ★ 回大厅按钮：放在吸顶状态栏里（滚动看数据时也不会压住卡片内容）。
   暖白纸面上必须高对比 / 大号 / 手绘抖边硬阴影，否则用户会"看不见返回按钮"。 */
.room-nav__back {
  flex: none;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  height: 38px;
  padding: 0 16px;
  cursor: pointer;
  font-family: inherit;
  font-size: 14px;
  font-weight: 800;
  letter-spacing: 0.04em;
  white-space: nowrap;
  color: #FFF6E9;
  background: linear-gradient(160deg, #A0522D, #8B4513);
  border: 2.2px solid #5C4326;
  border-radius: 255px 16px 225px 16px / 16px 225px 16px 255px;
  box-shadow: 0 3px 10px rgba(139, 69, 19, 0.38), 4px 4px 0 rgba(74, 40, 20, 0.3);
  transition: transform 0.16s ease, box-shadow 0.16s ease, background 0.2s ease;
}
.room-nav__back:hover {
  background: linear-gradient(160deg, #B5651D, #A0522D);
  color: #FFF6E9;
  transform: translate(2px, 2px);
  box-shadow: 0 2px 6px rgba(139, 69, 19, 0.38), 1px 1px 0 rgba(74, 40, 20, 0.35);
}
.room-nav__back:active {
  transform: translate(4px, 4px);
  box-shadow: 0 1px 3px rgba(139, 69, 19, 0.38);
}
@media (max-width: 900px) {
  .room-nav__back { padding: 0 11px; font-size: 13px; height: 34px; }
  .top-bar__sub { display: none; }
}

/* 导览图圆钮（手绘纸质小圆牌，itomdev nav-btn 位） */
.room-nav__map {
  flex: none;
  width: 38px;
  height: 38px;
  display: grid;
  place-items: center;
  cursor: pointer;
  background: #FFFDF7;
  border: 2px solid #3A2E20;
  border-radius: 16px 240px 14px 250px / 250px 14px 240px 16px;
  box-shadow: 3px 3px 0 rgba(74, 40, 20, 0.25);
  transition: transform 0.16s ease, background 0.2s ease, box-shadow 0.16s ease;
}
.room-nav__map svg {
  width: 19px;
  height: 19px;
  fill: none;
  stroke: #4A2E16;
  stroke-width: 2;
  stroke-linejoin: round;
  stroke-linecap: round;
}
.room-nav__map:hover {
  background: linear-gradient(160deg, #FFE9C9, #FFD9A0);
  transform: translate(1px, 1px);
  box-shadow: 1px 1px 0 rgba(74, 40, 20, 0.3);
}

/* 大厅悬浮导览图按钮（顶栏左下常驻，进大厅就能看到"馆内地图"入口） */
.house-map-btn {
  position: absolute;
  top: 84px;
  left: auto;
  right: 24px;
  z-index: 40;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 9px 18px 9px 14px;
  font-size: 13.5px;
  font-weight: 800;
  letter-spacing: 0.08em;
  color: #FFF6E9;
  background: linear-gradient(160deg, #A0522D, #8B4513);
  border: 2.2px solid #5C4326;
  border-radius: 255px 16px 225px 16px / 16px 225px 16px 255px;
  box-shadow: 0 4px 12px rgba(139, 69, 19, 0.34), 4px 4px 0 rgba(74, 40, 20, 0.28);
  cursor: pointer;
  transition: transform 0.16s ease, background 0.2s ease, box-shadow 0.16s ease;
}
.house-map-btn svg {
  width: 19px;
  height: 19px;
  fill: none;
  stroke: currentColor;
  stroke-width: 2;
  stroke-linejoin: round;
  stroke-linecap: round;
}
.house-map-btn:hover {
  background: linear-gradient(160deg, #B5651D, #A0522D);
  transform: translate(2px, 2px);
  box-shadow: 0 2px 8px rgba(139, 69, 19, 0.34), 1px 1px 0 rgba(74, 40, 20, 0.32);
}
@media (max-width: 900px) {
  .house-map-btn { top: 78px; left: auto; right: 14px; padding: 8px 14px 8px 11px; font-size: 12.5px; }
}

.room-nav__plate { display: flex; align-items: baseline; gap: 6px; white-space: nowrap; }
.room-nav__icon { font-size: 15px; font-style: normal; }
.room-nav__plate b { font-size: 14.5px; font-weight: 800; color: #4A2E16; letter-spacing: 0.06em; }
.room-nav__plate span { font-size: 11px; color: var(--u-text-2, #7D6B52); letter-spacing: 0.05em; }

.room-nav__go { display: flex; gap: 5px; }
.room-nav__go button { padding: 4px 10px; font-size: 11.5px; }

.room-nav__doors { display: flex; gap: 4px; padding-left: 4px; margin-left: 2px; border-left: 1px solid rgba(107, 78, 46, 0.22); }
.room-nav__door {
  width: 25px;
  height: 25px;
  display: grid;
  place-items: center;
  font-size: 13px;
  line-height: 1;
  opacity: 0.6;
}
.room-nav__door.is-on {
  opacity: 1;
  background: linear-gradient(160deg, #A0522D, #8B4513);
  border-color: #6B4E2E;
  color: #FFF6E9;
  box-shadow: 0 2px 6px rgba(139, 69, 19, 0.32);
}
.room-nav__door.is-on:hover { background: linear-gradient(160deg, #A0522D, #8B4513); }

/* 1280 左右舞台区只有 584px，全量导览条会换行把面板挤矮（实测 78px 两行）→ 收起次要项 */
@media (max-width: 1360px) {
  .room-nav__plate span, .room-nav__go { display: none; }
}

/* ---------- 鼠标暖光层（跟随指针的柔光，长页滚动时固定不动） ---------- */
.room-spotlight {
  position: fixed;
  inset: 0;
  z-index: 2;
  pointer-events: none;
  background: radial-gradient(
    340px 340px at var(--mx, 50%) var(--my, 36%),
    rgba(255, 214, 150, 0.22),
    rgba(194, 65, 12, 0.07) 45%,
    transparent 72%
  );
}
/* 长页滚动进度：顶栏下沿金色细线（scaleX 由 --u-progress 驱动） */
.room-progress {
  position: fixed;
  top: calc(var(--header-h, 60px) + 64px);
  left: 0;
  right: 0;
  height: 3px;
  z-index: 31;
  pointer-events: none;
  background: rgba(139, 69, 19, 0.1);
}
.room-progress i {
  display: block;
  height: 100%;
  transform-origin: 0 50%;
  transform: scaleX(var(--u-progress, 0));
  background: linear-gradient(90deg, var(--u-gold), var(--u-orange));
  box-shadow: 0 0 8px rgba(194, 65, 12, 0.5);
  transition: transform 0.12s linear;
}

@media (prefers-reduced-motion: reduce) {
  .room-spotlight { display: none; }
  .room-progress i { transition: none; }
}

/* ---------- 首屏外卡片：滚到跟前再浮起（A24 逐段揭示） ---------- */
:deep(.float-card.is-below),
:deep(.box-stage__extras.is-below) { opacity: 0; animation: none; }
:deep(.float-card.is-below.is-revealed),
:deep(.box-stage__extras.is-below.is-revealed) {
  opacity: 1;
  animation: reveal-in 0.72s cubic-bezier(0.16, 0.84, 0.44, 1) backwards;
}
@keyframes reveal-in {
  from { opacity: 0; transform: translateY(26px); }
  to { opacity: 1; transform: none; }
}

/* 减弱动效偏好：不藏、不浮，直接显示（必须放在上面两条之后） */
@media (prefers-reduced-motion: reduce) {
  :deep(.float-card.is-below),
  :deep(.box-stage__extras.is-below) { opacity: 1; animation: none; }
}
</style>
