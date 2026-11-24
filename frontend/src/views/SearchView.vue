<script setup>
// ============================================================
// 首页 · 混合检索（平台的主路径）
//
// 这个组件是「状态编排器」：所有筛选状态集中在这里，
// 子组件（SearchBox/FacetRail/SortBar/MovieGrid/ReviewPanel/MovieDetail）
// 全部无业务状态，只负责渲染与回传事件。
//
// 三个设计决定：
// 1. **URL 同步**：筛选条件写进地址栏 query，刷新不丢、链接可分享。
//    答辩时现场粘一个带条件的链接就能复现检索现场。
// 2. **双 Tab 数据各自缓存**：影片/影评切换不重新请求，
//    但任何筛选变化只请求当前 Tab（影评没有类型筛选，反之亦然）。
// 3. **区间分面换算表与后端一致**：评分/篇幅的中文区间名 ↔ min/max，
//    两张表在 query_builder.py 与本文件各存一份，注释互相点名，同步维护。
// ============================================================
import { computed, onMounted, reactive } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
import { auth } from '../composables/useAuth'
import { useMovieActions } from '../composables/useMovieActions'
import { searchHistory } from '../composables/useSearchHistory'
import { toast } from '../composables/useToast'
import SearchBox from '../components/search/SearchBox.vue'
import FacetRail from '../components/search/FacetRail.vue'
import ActiveChips from '../components/search/ActiveChips.vue'
import SortBar from '../components/search/SortBar.vue'
import MovieGrid from '../components/search/MovieGrid.vue'
import ReviewPanel from '../components/search/ReviewPanel.vue'
import SearchAside from '../components/search/SearchAside.vue'
import MovieDetail from '../components/search/MovieDetail.vue'

const router = useRouter()

const state = reactive({
  tab: 'movies',           // movies | reviews
  q: '',
  // 影片筛选
  genres: [], countries: [], languages: [],
  yearFrom: null, yearTo: null,
  ratingMin: null, ratingMax: null,
  requirePoster: false,
  sort: 'relevance', order: 'desc',
  page: 1, size: 20,
  // 影评筛选
  sentiment: [], dataset: [],
  minWords: null, maxWords: null,
  reviewSort: 'relevance', reviewOrder: 'desc',
  // 结果
  loading: false,
  loadingMore: false,
  error: '',
  movieResp: null,
  reviewResp: null,
})

// 区间换算表 —— 必须与 backend/services/query_builder.py 的 RATING_RANGES / LENGTH_RANGES 一致
const RATING_BOUNDS = {
  '9 分以上': [9, null],
  '8 ~ 9 分': [8, 9],
  '7 ~ 8 分': [7, 8],
  '6 ~ 7 分': [6, 7],
  '6 分以下': [null, 6],
}
const LENGTH_BOUNDS = {
  '长评（500 词以上）': [500, null],
  '中评（200 ~ 500 词）': [200, 500],
  '短评（50 ~ 200 词）': [50, 200],
  '微评（50 词以内）': [null, 50],
}
// 十年区间表 —— 与 FacetRail 的 DECADES 一致（两边同步维护）
const DECADE_BOUNDS = {
  'decade:2020s': [2020, 2029],
  'decade:2010s': [2010, 2019],
  'decade:2000s': [2000, 2009],
  'decade:1990s': [1990, 1999],
  'decade:older': [null, 1989],
}

// ============================================================
// 检索执行
// ============================================================

// 影片检索请求体 —— 抽成函数：首页检索与「加载更多」共用一份口径，
// 只差 page。以前两处各写一遍，改筛选时容易漏改一处（实测踩过）。
function movieBody(page) {
  return {
    q: state.q.trim() || null,
    mode: 'best',
    genres: state.genres,
    genre_op: 'or',
    countries: state.countries,
    languages: state.languages,
    year_from: state.yearFrom,
    year_to: state.yearTo,
    rating_min: state.ratingMin,
    rating_max: state.ratingMax,
    require_poster: state.requirePoster,
    sort: state.sort,
    order: state.order,
    page,
    size: state.size,
    with_facets: true,
  }
}

// 首页检索：永远是第一页，整体替换结果。
async function runMovieSearch() {
  state.loading = true
  state.error = ''
  try {
    state.movieResp = await api.searchMovies(movieBody(1))
  } catch (e) {
    state.error = e.message
    state.movieResp = null
  } finally {
    state.loading = false
  }
}

// 加载更多（功能清单 P0：每次 20 条，底部「加载更多」而非跳页）。
// 追加 hits、其余字段用新响应覆盖；重复触发用 loadingMore 挡掉。
async function loadMoreMovies() {
  if (state.loadingMore || state.loading) return
  const next = movieMeta.value.page + 1
  if (next > movieMeta.value.pages) return
  state.loadingMore = true
  try {
    const resp = await api.searchMovies(movieBody(next))
    state.movieResp = {
      ...resp,
      hits: [...(state.movieResp?.hits || []), ...(resp.hits || [])],
    }
  } catch (e) {
    toast.show(e.message || '加载失败，请重试')
  } finally {
    state.loadingMore = false
  }
}

async function runReviewSearch() {
  state.loading = true
  state.error = ''
  try {
    state.reviewResp = await api.searchReviews({
      q: state.q.trim() || null,
      sentiment: state.sentiment,
      dataset: state.dataset,
      min_words: state.minWords,
      max_words: state.maxWords,
      sort: state.reviewSort,
      order: state.reviewOrder,
      page: state.page,
      size: 10,
      with_facets: true,
    })
  } catch (e) {
    state.error = e.message
    state.reviewResp = null
  } finally {
    state.loading = false
  }
}

function runSearchNow() {
  if (state.tab === 'movies') return runMovieSearch()
  return runReviewSearch()
}

// 统一入口：检索落地后回写 URL（replace 不污染历史栈）。
// 所有筛选事件都调这个，不单独调 runSearchNow —— 漏一次 syncUrl，
// 刷新后条件就丢了，而这种丢失在现场演示时才会被发现。
async function runSearch() {
  await runSearchNow()
  syncUrl()
  // 搜索历史回填结果数量（功能清单：记录关键词、时间、结果数量）。
  // 提交搜索时还不知道命中多少，这里拿到 total 后补 —— 只改 count
  // 不动顺序，所以不会把同一次搜索反复顶到最前面。
  if (state.q.trim()) searchHistory.updateCount(state.q.trim(), currentTotal.value)
}

// ============================================================
// 事件处理
// ============================================================

function onSearch(q) {
  state.q = q
  state.page = 1
  runSearch()
}

function onPick(item) {
  // 联想选中：直接以该片名检索（不打开详情，行为可预期）
  state.q = item.title
  state.page = 1
  runSearch()
}

function onTab(tab) {
  if (state.tab === tab) return
  state.tab = tab
  state.page = 1
  // 切换 Tab 时若该 Tab 还没数据才请求；有数据直接展示（秒切）
  if (tab === 'movies' && !state.movieResp) runMovieSearch()
  else if (tab === 'reviews' && !state.reviewResp) runReviewSearch()
  syncUrl()
}

function onSort(sort) {
  if (state.tab === 'movies') state.sort = sort
  else state.reviewSort = sort
  state.page = 1
  runSearch()
}

function onOrder(order) {
  if (state.tab === 'movies') state.order = order
  else state.reviewOrder = order
  state.page = 1
  runSearch()
}

function onPage(p) {
  if (p < 1) return
  state.page = p
  runSearch()
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

function onQuality({ key, value }) {
  state[key] = value
  state.page = 1
  runSearch()
}

function onFacetToggle({ field, key }) {
  const arrayFields = ['genres', 'countries', 'languages', 'sentiment', 'dataset']
  if (arrayFields.includes(field)) {
    const arr = state[field]
    const i = arr.indexOf(key)
    if (i >= 0) arr.splice(i, 1)
    else arr.push(key)
  } else if (field === 'years') {
    if (key.startsWith('decade:')) {
      // 十年快捷按钮：换算成区间，再点一次取消
      const [lo, hi] = DECADE_BOUNDS[key] || [null, null]
      if (state.yearFrom === lo && state.yearTo === hi) {
        state.yearFrom = state.yearTo = null
      } else {
        state.yearFrom = lo
        state.yearTo = hi
      }
    } else {
      const y = Number(key)
      if (state.yearFrom === y && state.yearTo === y) {
        state.yearFrom = state.yearTo = null
      } else {
        state.yearFrom = y
        state.yearTo = y
      }
    }
  } else if (field === 'rating') {
    const [lo, hi] = RATING_BOUNDS[key] || [null, null]
    if (state.ratingMin === lo && state.ratingMax === hi) {
      state.ratingMin = state.ratingMax = null
    } else {
      state.ratingMin = lo
      state.ratingMax = hi
    }
  } else if (field === 'length') {
    const [lo, hi] = LENGTH_BOUNDS[key] || [null, null]
    if (state.minWords === lo && state.maxWords === hi) {
      state.minWords = state.maxWords = null
    } else {
      state.minWords = lo
      state.maxWords = hi
    }
  }
  state.page = 1
  runSearch()
}

// ============================================================
// 已选条件 chips
// ============================================================

const chips = computed(() => {
  const out = []
  if (state.q.trim()) out.push({ key: 'q', label: `关键词：${state.q.trim()}` })
  if (state.tab === 'movies') {
    state.genres.forEach((g) => out.push({ key: `genres:${g}`, label: `类型：${g}` }))
    state.countries.forEach((c) => out.push({ key: `countries:${c}`, label: `国家/地区：${c}` }))
    state.languages.forEach((l) => out.push({ key: `languages:${l}`, label: `语言：${l}` }))
    if (state.yearFrom != null || state.yearTo != null) {
      // 命中十年区间时显示「2010s」而不是「2010 ~ 2019」
      const decade = Object.entries(DECADE_BOUNDS).find(
        ([, v]) => v[0] === state.yearFrom && v[1] === state.yearTo,
      )?.[0]
      out.push({
        key: 'years',
        label: decade ? `年份：${decade.slice(7)}` : `年份：${state.yearFrom ?? '…'} ~ ${state.yearTo ?? '…'}`,
      })
    }
    if (state.ratingMin != null || state.ratingMax != null) {
      const label = Object.entries(RATING_BOUNDS).find(
        ([, v]) => v[0] === state.ratingMin && v[1] === state.ratingMax,
      )?.[0]
      out.push({ key: 'rating', label: `评分：${label || `${state.ratingMin ?? 0} ~ ${state.ratingMax ?? 10} 分`}` })
    }
    if (state.requirePoster) out.push({ key: 'quality:require_poster', label: '仅有海报' })
  } else {
    state.sentiment.forEach((s) => out.push({ key: `sentiment:${s}`, label: `情感：${s}` }))
    state.dataset.forEach((d) => out.push({ key: `dataset:${d}`, label: `数据集：${d}` }))
    if (state.minWords != null || state.maxWords != null) {
      const label = Object.entries(LENGTH_BOUNDS).find(
        ([, v]) => v[0] === state.minWords && v[1] === state.maxWords,
      )?.[0]
      out.push({ key: 'length', label: `篇幅：${label || '自定义'}` })
    }
  }
  return out
})

function onChipRemove(key) {
  if (key === 'q') state.q = ''
  else if (key === 'years') { state.yearFrom = state.yearTo = null }
  else if (key === 'rating') { state.ratingMin = state.ratingMax = null }
  else if (key === 'length') { state.minWords = state.maxWords = null }
  else if (key.startsWith('quality:')) {
    state[key.slice('quality:'.length)] = false
  } else {
    const idx = key.indexOf(':')
    const field = key.slice(0, idx)
    const value = key.slice(idx + 1)
    const arr = state[field]
    const i = arr.indexOf(value)
    if (i >= 0) arr.splice(i, 1)
  }
  state.page = 1
  runSearch()
}

function onClearAll() {
  state.q = ''
  state.genres = []
  state.countries = []
  state.languages = []
  state.yearFrom = state.yearTo = null
  state.ratingMin = state.ratingMax = null
  state.requirePoster = false
  state.sentiment = []
  state.dataset = []
  state.minWords = state.maxWords = null
  state.page = 1
  runSearch()
}

// ============================================================
// 影片操作（评分 / 想看 / 详情弹窗 / 找相似）
// 与发现页共用 useMovieActions —— 行为数据操作只有一处真相。
// ============================================================

const {
  watchedIds,
  myScores,
  detail,
  loadWatchlist,
  loadMyRatings,
  onToggleWatch,
  onRate,
  onDeleteRating,
  openDetail,
  closeDetail,
  onSimilar,
} = useMovieActions()

// ============================================================
// URL 同步（筛选条件进地址栏：刷新不丢、链接可分享）
// ============================================================

function splitParam(v) {
  return typeof v === 'string' && v ? v.split(',').filter(Boolean) : []
}

function readUrl() {
  const q = router.currentRoute.value.query
  state.q = typeof q.q === 'string' ? q.q : ''
  state.tab = q.tab === 'reviews' ? 'reviews' : 'movies'
  state.page = Number(q.page) > 0 ? Number(q.page) : 1
  state.genres = splitParam(q.genres)
  state.countries = splitParam(q.countries)
  state.languages = splitParam(q.languages)
  state.yearFrom = q.yf ? Number(q.yf) : null
  state.yearTo = q.yt ? Number(q.yt) : null
  state.ratingMin = q.rmin != null ? Number(q.rmin) : null
  state.ratingMax = q.rmax != null ? Number(q.rmax) : null
  state.requirePoster = q.poster === '1'
  const movieSorts = ['relevance', 'rating', 'votes', 'year', 'title', 'popularity']
  state.sort = movieSorts.includes(q.sort) ? q.sort : 'relevance'
  state.order = q.order === 'asc' ? 'asc' : 'desc'
  state.sentiment = splitParam(q.sentiment)
  state.dataset = splitParam(q.dataset)
  state.minWords = q.wmin != null ? Number(q.wmin) : null
  state.maxWords = q.wmax != null ? Number(q.wmax) : null
  state.reviewSort = ['relevance', 'length', 'sentiment'].includes(q.rsort) ? q.rsort : 'relevance'
  state.reviewOrder = q.rorder === 'asc' ? 'asc' : 'desc'
}

function syncUrl() {
  const query = { tab: state.tab }
  if (state.q.trim()) query.q = state.q.trim()
  if (state.page > 1) query.page = String(state.page)
  if (state.tab === 'movies') {
    if (state.genres.length) query.genres = state.genres.join(',')
    if (state.countries.length) query.countries = state.countries.join(',')
    if (state.languages.length) query.languages = state.languages.join(',')
    if (state.yearFrom != null) query.yf = String(state.yearFrom)
    if (state.yearTo != null) query.yt = String(state.yearTo)
    if (state.ratingMin != null) query.rmin = String(state.ratingMin)
    if (state.ratingMax != null) query.rmax = String(state.ratingMax)
    if (state.requirePoster) query.poster = '1'
    if (state.sort !== 'relevance') query.sort = state.sort
    if (state.order !== 'desc') query.order = state.order
  } else {
    if (state.sentiment.length) query.sentiment = state.sentiment.join(',')
    if (state.dataset.length) query.dataset = state.dataset.join(',')
    if (state.minWords != null) query.wmin = String(state.minWords)
    if (state.maxWords != null) query.wmax = String(state.maxWords)
    if (state.reviewSort !== 'relevance') query.rsort = state.reviewSort
    if (state.reviewOrder !== 'desc') query.rorder = state.reviewOrder
  }
  router.replace({ query })
}

// ============================================================
// 计算属性
// ============================================================

const currentFacets = computed(() =>
  state.tab === 'movies' ? (state.movieResp?.facets || []) : (state.reviewResp?.facets || []),
)
const movies = computed(() => state.movieResp?.hits || [])
const reviews = computed(() => state.reviewResp?.hits || [])
const movieMeta = computed(() => state.movieResp?.meta || { total: 0, took_ms: 0, page: 1, pages: 0 })
const reviewMeta = computed(() => state.reviewResp?.meta || { total: 0, took_ms: 0, page: 1, pages: 0 })
const currentTotal = computed(() => (state.tab === 'movies' ? movieMeta.value.total : reviewMeta.value.total))
const currentTook = computed(() => (state.tab === 'movies' ? movieMeta.value.took_ms : reviewMeta.value.took_ms))
const currentSort = computed(() => (state.tab === 'movies' ? state.sort : state.reviewSort))
const currentOrder = computed(() => (state.tab === 'movies' ? state.order : state.reviewOrder))

// ============================================================
// 生命周期
// ============================================================

onMounted(async () => {
  await auth.init()
  readUrl()
  await runSearch()
  await Promise.all([loadWatchlist(), loadMyRatings()])
})
</script>

<template>
  <div class="page">
    <div class="search-hero">
      <h1 class="search-hero__title">电影盒子</h1>
      <p class="search-hero__sub">
        汇集多个公开平台的影片与影评资料库 —— 搜片名、导演、剧情，或去影评里找证据
      </p>
      <SearchBox v-model="state.q" @search="onSearch" @pick="onPick" />
    </div>

    <ActiveChips :chips="chips" @remove="onChipRemove" @clear="onClearAll" />

    <div class="search-body">
      <FacetRail
        :facets="currentFacets"
        :require-poster="state.requirePoster"
        :year-range="[state.yearFrom, state.yearTo]"
        @toggle="onFacetToggle"
        @quality="onQuality"
      />

      <div class="result-area">
        <SortBar
          :tab="state.tab"
          :sort="currentSort"
          :order="currentOrder"
          :total="currentTotal"
          :took-ms="currentTook"
          :page="state.tab === 'movies' ? movieMeta.page : reviewMeta.page"
          :pages="state.tab === 'movies' ? movieMeta.pages : reviewMeta.pages"
          @tab="onTab"
          @sort="onSort"
          @order="onOrder"
        />

        <div v-if="state.error" class="alert alert--error mb-16">
          <span>⚠️</span>
          <span>{{ state.error }}</span>
        </div>

        <MovieGrid
          v-if="state.tab === 'movies'"
          :loading="state.loading"
          :movies="movies"
          :total="movieMeta.total"
          :page="movieMeta.page"
          :pages="movieMeta.pages"
          :loading-more="state.loadingMore"
          :note="state.movieResp?.note || ''"
          :watched-ids="watchedIds"
          :my-scores="myScores"
          @open="openDetail"
          @toggle-watch="onToggleWatch"
          @load-more="loadMoreMovies"
        />
        <ReviewPanel
          v-else
          :loading="state.loading"
          :reviews="reviews"
          :total="reviewMeta.total"
          :page="reviewMeta.page"
          :pages="reviewMeta.pages"
          @page="onPage"
        />
      </div>

      <!-- 右侧辅助面板：影评高频词 / 口碑温度计 / 相关搜索（功能清单 P1）。
           窄屏由 search.css 的媒体查询隐藏，主检索链路不受影响。 -->
      <SearchAside
        v-if="state.tab === 'movies'"
        :movies="movies"
        :total="movieMeta.total"
        @search="onSearch"
      />
    </div>

    <MovieDetail
      v-if="detail"
      :movie="detail"
      :my-score="myScores[detail.movie_id] ?? null"
      :watched="watchedIds.has(detail.movie_id)"
      @close="closeDetail"
      @rate="onRate"
      @delete-rating="onDeleteRating"
      @toggle-watch="onToggleWatch(detail)"
      @similar="onSimilar"
    />
  </div>
</template>

<!--
  注意：这里必须用「非 scoped」引入。
  search.css 里的 .facet-* / .sort-bar / .active-chips / .movie-card 等选择器
  大多作用于子组件（FacetRail/SortBar 等）的内部元素，scoped 会给选择器
  附加本组件的 data-v 属性，子组件内部元素不携带该属性，导致整组规则
  静默失效（表现为：筛选药丸变成裸灰框、对勾常显）。类名已核对无全局冲突。
-->
<style>
@import '../styles/search.css';
</style>
