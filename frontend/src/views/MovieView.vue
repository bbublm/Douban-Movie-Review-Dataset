<script setup>
// ============================================================
// 电影详情页 —— 清单「电影详情页」模块。
//
// 海报 240×360、片名 32px、元信息、导演与前 3 主演、简介 3 行折叠，
// 操作：收藏 / 加入盲盒 / 分享（复制链接）。
//
// ★ 清单里的「方面情感雷达（六维度）」与「时间趋势（首周/首月）」没有数据：
//   单片画像接口给的是关键词 + 类型口碑参考，所以这里展示
//   「关键词 + 口碑参考」，并在卡片上标注缺口，不画假雷达。
// ============================================================
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import { auth } from '../composables/useAuth'
import { blindBox } from '../composables/useBlindBox'
import { toast } from '../composables/useToast'

const route = useRoute()
const router = useRouter()

const movie = ref(null)
const insight = ref(null)
const similar = ref([])
const similarMode = ref('content')
const loading = ref(true)
const error = ref('')
const overviewOpen = ref(false)
const watched = ref(false)

const cast = computed(() => (movie.value?.cast || []).slice(0, 3))
const primaryRating = computed(() => {
  const douban = movie.value?.douban_score ?? movie.value?.douban_rating
  return douban != null ? douban : (movie.value?.rating ?? 0)
})
const primaryVotes = computed(() => {
  const douban = movie.value?.douban_score ?? movie.value?.douban_rating
  return douban != null
    ? (movie.value?.douban_votes ?? 0)
    : (movie.value?.votes ?? 0)
})
const primaryRatingSource = computed(() => {
  const douban = movie.value?.douban_score ?? movie.value?.douban_rating
  return douban != null ? '豆瓣评分' : 'TMDB评分'
})

// 观众短评（本片）：豆瓣 / TMDB / Kaggle 三个语料库一起找。
// 本片确实没有短评时，后端会退回同类型影片的真实短评，scope='peers' ——
// 页面文案随之改成"同类型观众在聊什么"，不拿别的片的评价冒充本片。
const voices = ref({ scope: 'none', items: [], stats: {}, genres_zh: [] })
const keywordTags = computed(() => (insight.value?.keywords || []).slice(0, 14))

// 本片评分 vs 同类型均分：把评分放回类型里看，比孤立一个数字有信息量。
const genreRef = computed(() => {
  const g = insight.value?.genre_ref
  if (!g || g.avg_rating == null || movie.value?.rating == null) return null
  const gap = movie.value.rating - g.avg_rating
  return {
    ...g,
    gap,
    text: Math.abs(gap) < 0.3
      ? `与「${g.genre}」类平均分基本持平`
      : `比「${g.genre}」类平均分${gap > 0 ? '高' : '低'} ${Math.abs(gap).toFixed(2)} 分`,
  }
})
// 评分条宽度：10 分制直接映射成百分比，底衬统一，长短一眼可比
const ratingWidth = (v) => `${Math.max(4, Math.min(100, (Number(v) || 0) * 10))}%`

const sentimentTotal = computed(() => {
  const s = voices.value?.stats || {}
  return (s.positive || 0) + (s.neutral || 0) + (s.negative || 0)
})
const sentimentPct = computed(() => {
  const t = sentimentTotal.value || 1
  const s = voices.value?.stats || {}
  const p = Math.round(((s.positive || 0) / t) * 100)
  const n = Math.round(((s.negative || 0) / t) * 100)
  return { pos: p, neg: n, neu: Math.max(0, 100 - p - n) }
})
const SOURCE_LABEL = {
  douban: '豆瓣',
  douban_dataset: '豆瓣数据集',
  tmdb: 'TMDB',
  kaggle: 'Kaggle',
}
const sourceLabel = (s) => SOURCE_LABEL[s] || '影评'

async function loadVoices(id) {
  voices.value = { scope: 'none', items: [], stats: {}, genres_zh: [] }
  try {
    const resp = await api.movieVoices(id, 8)
    if (resp) voices.value = resp
  } catch {
    voices.value = { scope: 'none', items: [], stats: {}, genres_zh: [] }
  }
}

async function load() {
  loading.value = true
  error.value = ''
  const id = route.params.id
  try {
    const m = await api.getMovie(id)
    if (!m) { error.value = '没有找到这部电影'; movie.value = null; return }
    movie.value = m
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
  // 次要数据失败不影响主信息
  api.movieInsight(id).then((d) => { insight.value = d }).catch(() => {})
  // 相似推荐：接口返回 {base, items:[{movie, reason}], mode}，
  // 之前误取 hits 导致永远空列表 —— 统一在这里拍平成影片数组。
  api.similar(id, 8)
    .then((d) => {
      const list = (d?.items || []).map((x) => x.movie).filter(Boolean)
      similar.value = list.length ? list : (d?.hits || [])
      similarMode.value = d?.mode || 'content'
    })
    .catch(() => { similar.value = [] })
  loadVoices(id).catch(() => {})
  if (auth.isLoggedIn.value) {
    api.watchlist().then((list) => {
      const ids = (list?.items || list?.movie_ids || []).map((x) => x.movie_id || x)
      watched.value = ids.includes(String(id))
    }).catch(() => {})
  }
}

onMounted(load)
watch(() => route.params.id, load)

async function toggleWatch() {
  if (!auth.isLoggedIn.value) { toast.info('登录后才能收藏'); router.push('/login'); return }
  try {
    if (watched.value) { await api.removeWatch(movie.value.movie_id); watched.value = false; toast.success('已取消收藏') }
    else { await api.addWatch(movie.value.movie_id); watched.value = true; toast.success('已加入收藏') }
  } catch (e) { toast.error(e.message) }
}

function share() {
  const url = window.location.href
  if (navigator.clipboard?.writeText) {
    navigator.clipboard.writeText(url)
    toast.success('链接已复制')
  } else {
    toast.info(url)
  }
}
</script>

<template>
  <div class="container page">
    <button class="btn btn--ghost btn--sm mb-16" @click="router.back()">← 返回</button>

    <div v-if="loading" class="mv-skeleton">
      <div class="skeleton" style="width:240px;height:360px;border-radius:12px" />
      <div style="flex:1">
        <div class="skeleton" style="height:34px;width:60%;margin-bottom:14px" />
        <div class="skeleton" style="height:18px;width:40%;margin-bottom:8px" />
        <div class="skeleton" style="height:18px;width:70%;margin-bottom:8px" />
        <div class="skeleton" style="height:120px;margin-top:16px" />
      </div>
    </div>

    <div v-else-if="error" class="empty">
      <span class="empty__icon">🎬</span>
      <span class="empty__title">{{ error }}</span>
      <router-link class="btn btn--primary mt-16" to="/search">去检索</router-link>
    </div>

    <template v-else-if="movie">
      <div class="mv">
        <div class="mv__poster">
          <img v-if="movie.poster_url" :src="movie.poster_url" :alt="movie.title" />
          <div v-else class="mv__ph">🎬</div>
        </div>

        <div class="mv__main">
          <h1 class="mv__title">{{ movie.title }}</h1>
          <p v-if="movie.title_zh && movie.title_zh !== movie.title" class="mv__titlezh">{{ movie.title_zh }}</p>

          <div class="mv__meta">
            <span>{{ movie.release_year || '—' }}</span>
            <span>{{ (movie.genres_zh || []).join(' / ') || '—' }}</span>
            <span>{{ (movie.production_countries || [])[0] || '—' }}</span>
            <span v-if="movie.runtime">{{ movie.runtime }} 分钟</span>
          </div>

          <div class="mv__score">
            <span class="stars">{{ '★'.repeat(Math.round(primaryRating / 2)) }}</span>
            <b :title="primaryRatingSource">{{ primaryRating.toFixed(1) }}</b>
            <span class="text-3 text-sm">{{ primaryVotes.toLocaleString() }} 人评</span>
            <span v-if="movie.douban_rating != null" class="mv__score-sep">·</span>
            <span v-if="movie.douban_rating != null" class="mv__douban" title="豆瓣评分（优先展示）">
              🟢 豆瓣 {{ (movie.douban_score ?? movie.douban_rating).toFixed(1) }}
              <span class="text-3 text-sm">{{ (movie.douban_votes || 0).toLocaleString() }} 人</span>
            </span>
          </div>

          <p class="mv__people">
            <b>导演：</b>{{ movie.director || '—' }}
            <span v-if="cast.length"> · <b>主演：</b>{{ cast.join('、') }}</span>
          </p>

          <div class="mv__ops">
            <button class="btn" :class="watched ? 'btn--primary' : 'btn--ghost'" @click="toggleWatch">
              {{ watched ? '★ 已收藏' : '☆ 收藏' }}
            </button>
            <button class="btn btn--ghost" @click="blindBox.openBox(movie.genres_zh || [])">🎲 加入盲盒</button>
            <button class="btn btn--ghost" @click="share">🔗 分享</button>
          </div>

          <div class="mv__overview">
            <p :class="{ 'is-clamped': !overviewOpen }">{{ movie.overview || '（该片暂无简介）' }}</p>
            <button v-if="(movie.overview || '').length > 90" class="mv__more" @click="overviewOpen = !overviewOpen">
              {{ overviewOpen ? '收起' : '展开' }}
            </button>
          </div>

        </div>
      </div>

      <!-- 口碑与关键词：把评分放回它的类型里看 -->
      <section class="panel mt-24">
        <h2 class="block__title">💬 口碑与关键词</h2>

        <div v-if="genreRef" class="mv-cmp">
          <div class="mv-cmp__row">
            <span class="mv-cmp__label">本片</span>
            <div class="mv-cmp__track">
              <i class="mv-cmp__fill is-self" :style="{ width: ratingWidth(movie.rating) }" />
            </div>
            <b class="mv-cmp__val">{{ movie.rating.toFixed(1) }}</b>
          </div>
          <div class="mv-cmp__row">
            <span class="mv-cmp__label">{{ genreRef.genre }}类均分</span>
            <div class="mv-cmp__track">
              <i class="mv-cmp__fill" :style="{ width: ratingWidth(genreRef.avg_rating) }" />
            </div>
            <b class="mv-cmp__val">{{ genreRef.avg_rating.toFixed(2) }}</b>
          </div>
          <p class="mv-cmp__note">
            {{ genreRef.text }}
            <span class="mv-cmp__scope">（{{ genreRef.movies }} 部{{ genreRef.genre }}类影片参照）</span>
          </p>
        </div>

        <div v-if="keywordTags.length" class="mv__kw">
          <span v-for="k in keywordTags" :key="k.term || k.keyword" class="tag tag--genre">
            {{ k.term || k.keyword }}
          </span>
        </div>
        <p v-else class="text-3 text-sm">本片暂无关键词标签</p>
      </section>

      <!-- 观众短评：本片没有时退回同类型影片的真实短评 -->
      <section class="panel mt-24">
        <div class="mv-voices__head">
          <h2 class="block__title">🗣 观众怎么说</h2>
          <span v-if="voices.scope === 'own'" class="mv-voices__count">
            共 {{ voices.stats.total }} 条短评
          </span>
        </div>

        <!-- 情感构成：一屏看懂这片子是夸是骂 -->
        <div v-if="voices.scope === 'own' && sentimentTotal" class="mv-voices__mood">
          <div class="mv-voices__bar">
            <span class="mv-voices__seg is-pos" :style="{ flex: voices.stats.positive || 0 }" />
            <span class="mv-voices__seg is-neu" :style="{ flex: voices.stats.neutral || 0 }" />
            <span class="mv-voices__seg is-neg" :style="{ flex: voices.stats.negative || 0 }" />
          </div>
          <div class="mv-voices__legend">
            <span><i class="dot dot--pos" />正面 {{ sentimentPct.pos }}%</span>
            <span><i class="dot dot--neu" />中性 {{ sentimentPct.neu }}%</span>
            <span><i class="dot dot--neg" />负面 {{ sentimentPct.neg }}%</span>
            <span v-if="voices.stats.avg_rating != null" class="mv-voices__avg">
              短评均分 {{ voices.stats.avg_rating.toFixed(1) }}
            </span>
          </div>
        </div>

        <p v-if="voices.scope === 'peers'" class="mv-voices__lead">
          本片还没有观众短评，先看看同类型（{{ (voices.genres_zh || []).slice(0, 2).join(' · ') || '相近题材' }}）影片的观众在聊什么。
        </p>

        <div v-if="voices.items.length" class="mv-voices__grid">
          <article v-for="v in voices.items" :key="v.review_id" class="mv-voice">
            <div class="mv-voice__head">
              <span class="mv-voice__src" :class="`is-${v.source || 'other'}`">{{ sourceLabel(v.source) }}</span>
              <span v-if="v.douban_sort" class="mv-voice__src">{{ v.douban_sort === 'time' ? '最新' : '最热' }}</span>
              <span v-if="v.sentiment" class="sent" :class="`sent--${v.sentiment}`">
                {{ { positive: '好评', negative: '差评', neutral: '中立' }[v.sentiment] || v.sentiment }}
              </span>
              <span v-if="v.rating != null" class="mv-voice__rating">★ {{ v.rating.toFixed(1) }}</span>
            </div>
            <p class="mv-voice__text">{{ v.text }}</p>
            <p v-if="v.review_time" class="mv-voice__from">评论时间：{{ v.review_time }}</p>
            <p v-if="voices.scope === 'peers' && v.movie_title" class="mv-voice__from">— 《{{ v.movie_title }}》的一条短评</p>
          </article>
        </div>
        <p v-else class="text-3 text-sm">
          本片和同类型影片都还没有收录短评。
          <router-link class="mv__link" to="/screen">去影评洞察看看 ›</router-link>
        </p>
      </section>

      <!-- 相似推荐 -->
      <section class="mt-24">
        <div class="mv-voices__head">
          <h2 class="block__title">🎯 相似推荐</h2>
          <span v-if="similar.length" class="mv-voices__count">
            {{ similarMode === 'genre' ? '同类型 · 评分与年代接近' : '简介与类型气质相近' }}
          </span>
        </div>
        <div v-if="similar.length" class="mix-grid">
          <div v-for="m in similar" :key="m.movie_id" class="mixcard" @click="router.push(`/movie/${encodeURIComponent(m.movie_id)}`)">
            <div class="mixcard__poster">
              <img v-if="m.poster_url" :src="m.poster_url" :alt="m.title" loading="eager" />
              <div v-else class="mixcard__ph">🎬</div>
            </div>
            <div class="mixcard__title">{{ m.title }}</div>
            <div class="mixcard__meta">
              {{ m.year || m.release_year || '—' }} · {{ (m.genres_zh || []).slice(0, 2).join('/') || '—' }}
            </div>
            <div class="mixcard__score">⭐ {{ (m.rating ?? 0).toFixed(1) }}</div>
          </div>
        </div>
        <p v-else class="text-3 text-sm">暂无相似推荐</p>
      </section>
    </template>
  </div>
</template>
