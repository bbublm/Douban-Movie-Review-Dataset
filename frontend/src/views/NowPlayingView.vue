<script setup>
// ============================================================
// 院线热映 · 站内采集档案
//   首页卡片点进来读的是自己 ES 索引里「爬虫已落库」的文档，
//   不跳转数据源站点、也不在 Web 请求里现爬；页面里所有动作都留在站内。
//   评分对照 / 库内关联都是接口真算出来的，没有写死的片单与数字。
// ============================================================
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api } from '../api'

const route = useRoute()
const id = computed(() => String(route.params.id || ''))
const detail = ref(null)
const peers = ref([])
const loading = ref(true)
const error = ref('')
const posterFailed = ref(false)
const voices = ref({ scope: 'none', items: [], stats: {}, genres_zh: [] })
const voicesLoading = ref(false)
const voicesError = ref('')

const SOURCE_LABEL = { douban: '豆瓣', tmdb: 'TMDB', kaggle: 'Kaggle' }
const sourceLabel = (source) => SOURCE_LABEL[source] || '影评'

const votesText = computed(() => {
  const n = detail.value?.douban_votes || 0
  return n >= 10000 ? `${(n / 10000).toFixed(1)} 万人评价` : `${n.toLocaleString()} 人评价`
})
const collectedText = computed(() => {
  const s = detail.value?.collected_at
  if (!s) return '—'
  const d = new Date(s)
  return Number.isNaN(d.getTime()) ? String(s) : d.toLocaleString('zh-CN', {
    year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
  })
})
// 双源评分差：采集榜单评分 − 库内片库评分，两个值都真实存在才算
const gap = computed(() => {
  const d = detail.value
  const lib = d?.library_match
  if (!lib || d.douban_rating == null || lib.rating == null) return null
  const v = d.douban_rating - lib.rating
  return {
    value: Math.abs(v).toFixed(1),
    higher: v > 0 ? '榜单更高' : v < 0 ? '片库更高' : '两边一致',
    text: v > 0.05 ? '采集榜单给出的分数更宽松'
      : v < -0.05 ? '片库评分反而更认可这部片'
        : '两份数据几乎给出同一个判断',
  }
})
const peerList = computed(() => {
  const list = [...peers.value].filter((m) => m.douban_id !== id.value)
  list.sort((a, b) => {
    const ra = a.douban_rating ?? -1, rb = b.douban_rating ?? -1
    if (rb !== ra) return rb - ra
    return (b.douban_votes || 0) - (a.douban_votes || 0)
  })
  return list.slice(0, 8)
})
const searchLink = computed(() => `/search?q=${encodeURIComponent(detail.value?.title || '')}`)

async function loadVoices(movieId, pageId) {
  voices.value = { scope: 'none', items: [], stats: {}, genres_zh: [] }
  voicesError.value = ''
  voicesLoading.value = true
  try {
    const response = await api.movieVoices(movieId, 8)
    if (pageId === id.value) voices.value = response
  } catch {
    if (pageId === id.value) voicesError.value = '评论暂时加载失败，请稍后重试。'
  } finally {
    if (pageId === id.value) voicesLoading.value = false
  }
}

async function load() {
  const pageId = id.value
  loading.value = true
  error.value = ''
  detail.value = null
  posterFailed.value = false
  voices.value = { scope: 'none', items: [], stats: {}, genres_zh: [] }
  voicesLoading.value = false
  voicesError.value = ''
  const [one, all] = await Promise.all([
    api.nowPlayingDetail(pageId).catch(() => null),
    api.nowPlaying().then((d) => d?.items || []).catch(() => []),
  ])
  if (pageId !== id.value) return
  peers.value = all
  if (one) detail.value = one
  else error.value = '这条院线热映记录不在已采集的档案里'
  loading.value = false
  const movieId = one?.library_match?.movie_id
  if (movieId) loadVoices(movieId, pageId)
}

onMounted(load)
watch(id, load)          // 同榜影片之间跳转时重新读档
</script>

<template>
  <div class="container npv">
    <nav class="npv__crumb" aria-label="面包屑">
      <router-link to="/">首页</router-link>
      <span>/</span>
      <span>院线热映</span>
      <span>/</span>
      <b>{{ detail?.title || '采集档案' }}</b>
    </nav>

    <div v-if="loading" class="npv__loading">正在读取站内采集档案…</div>

    <div v-else-if="error" class="empty">
      <span class="empty__icon">🎬</span>
      <span class="empty__title">{{ error }}</span>
      <router-link class="btn btn--primary mt-16" to="/">回首页看热映榜</router-link>
    </div>

    <template v-else-if="detail">
      <article class="npv__hero">
        <div class="npv__poster">
          <img
            v-if="detail.poster && !posterFailed"
            :src="detail.poster"
            :alt="detail.title || ''"
            @error="posterFailed = true"
          >
          <div v-else class="npv__ph">{{ (detail.title || '影').slice(0, 1) }}</div>
        </div>

        <div class="npv__main">
          <span class="npv__tag">🎞️ 院线热映 · 站内采集档案</span>
          <h1 class="npv__title">{{ detail.title || '（未命名）' }}</h1>

          <div class="npv__score">
            <b>★ {{ detail.douban_rating != null ? detail.douban_rating.toFixed(1) : '—' }}</b>
            <span>{{ votesText }}</span>
          </div>

          <dl class="npv__facts">
            <div><dt>上映年份</dt><dd>{{ detail.release_year || '—' }}</dd></div>
            <div><dt>制片地区</dt><dd>{{ (detail.region || []).join(' / ') || '—' }}</dd></div>
            <div><dt>片长</dt><dd>{{ detail.duration || '—' }}</dd></div>
            <div><dt>导演</dt><dd>{{ (detail.director || []).join(' / ') || '—' }}</dd></div>
            <div><dt>主演</dt><dd>{{ (detail.actors || []).join(' / ') || '—' }}</dd></div>
          </dl>

          <div class="npv__ops">
            <router-link
              v-if="detail.library_match"
              class="btn btn--primary"
              :to="`/movie/${encodeURIComponent(detail.library_match.movie_id)}`"
            >查看片库影片档案 →</router-link>
            <router-link v-else class="btn btn--primary" :to="searchLink">在片库检索同名影片 →</router-link>
            <router-link class="btn btn--ghost" :to="{ path: '/screen', query: { room: 'diverge' } }">口碑分歧洞察</router-link>
            <router-link class="btn btn--ghost" to="/">← 回热映榜</router-link>
          </div>
        </div>
      </article>

      <div class="npv__cards">
        <section class="npv__card">
          <h2 class="npv__card-h">采集档案</h2>
          <div class="npv__kv"><span>采集时间</span><b>{{ collectedText }}</b></div>
          <div class="npv__kv"><span>档案编号</span><b>{{ detail.douban_id }}</b></div>
          <div class="npv__kv"><span>采集来源</span><b>{{ detail.source || '—' }}</b></div>
          <p class="npv__card-note">这张卡片的字段都来自已经采集入库的榜单文档，点击不会离开本站。</p>
        </section>

        <section v-if="gap" class="npv__card">
          <h2 class="npv__card-h">双源评分对照</h2>
          <div class="npv__duo">
            <div><span>采集榜单</span><b>{{ detail.douban_rating.toFixed(1) }}</b></div>
            <i>vs</i>
            <div><span>片库评分</span><b>{{ detail.library_match.rating.toFixed(1) }}</b></div>
          </div>
          <p class="npv__duo-note">
            相差 <b>{{ gap.value }}</b> 分，{{ gap.higher }}。{{ gap.text }}。
          </p>
        </section>

        <section class="npv__card">
          <h2 class="npv__card-h">站内关联</h2>
          <template v-if="detail.library_match">
            <p class="npv__link-line">片库已收录同名影片《{{ detail.library_match.title }}》</p>
            <div class="npv__kv"><span>片库编号</span><b>{{ detail.library_match.movie_id }}</b></div>
            <div class="npv__kv"><span>片库年份</span><b>{{ detail.library_match.release_year || '—' }}</b></div>
          </template>
          <p v-else class="npv__link-line">片库暂未收录同名影片，可直接在站内检索这部片的相关记录。</p>
          <router-link class="npv__inline" :to="searchLink">在片库里搜「{{ detail.title }}」→</router-link>
        </section>
      </div>

      <section class="panel mt-24" aria-labelledby="npv-voices-title">
        <div class="mv-voices__head">
          <h2 id="npv-voices-title" class="block__title">💬 观众评论</h2>
          <span v-if="voices.scope === 'own'" class="mv-voices__count">
            本片收录 {{ voices.stats.total || voices.items.length }} 条
          </span>
          <span v-else-if="voices.scope === 'peers'" class="mv-voices__count">同类型影片参考</span>
        </div>

        <p v-if="!detail.library_match" class="text-3 text-sm">
          片库中没有严格匹配的影片，暂时无法可靠关联评论。
          <router-link class="mv__link" :to="searchLink">去片库检索 ›</router-link>
        </p>
        <p v-else-if="voicesLoading" class="text-3 text-sm">正在读取已入库评论…</p>
        <p v-else-if="voicesError" class="text-3 text-sm">{{ voicesError }}</p>
        <template v-else>
          <p v-if="voices.scope === 'peers'" class="mv-voices__lead">
            本片暂未收录评论，以下是同类型影片的评论参考，不代表本片评价。
          </p>
          <div v-if="voices.items.length" class="mv-voices__grid">
            <article v-for="voice in voices.items" :key="voice.review_id" class="mv-voice">
              <div class="mv-voice__head">
                <span class="mv-voice__src" :class="`is-${voice.source || 'other'}`">
                  {{ sourceLabel(voice.source) }}
                </span>
                <span v-if="voice.douban_sort" class="mv-voice__src">
                  {{ voice.douban_sort === 'time' ? '最新' : '最热' }}
                </span>
                <span v-if="voice.sentiment" class="sent" :class="`sent--${voice.sentiment}`">
                  {{ { positive: '好评', negative: '差评', neutral: '中立' }[voice.sentiment] || voice.sentiment }}
                </span>
                <span v-if="voice.rating != null" class="mv-voice__rating">★ {{ voice.rating.toFixed(1) }}</span>
              </div>
              <p class="mv-voice__text">{{ voice.text }}</p>
              <p v-if="voice.review_time" class="mv-voice__from">评论时间：{{ voice.review_time }}</p>
              <p v-if="voices.scope === 'peers' && voice.movie_title" class="mv-voice__from">
                — 《{{ voice.movie_title }}》的评论
              </p>
            </article>
          </div>
          <p v-else class="text-3 text-sm">本片及同类型影片暂时没有可展示的已入库评论。</p>
        </template>
      </section>

      <section v-if="peerList.length" class="block npv__peers-block">
        <div class="block__head">
          <h2 class="block__title">🎞️ 同榜影片</h2>
          <span class="block__note">同样来自站内采集榜单</span>
        </div>
        <div class="horizon">
          <router-link
            v-for="(m, i) in peerList"
            :key="m.douban_id"
            class="npc"
            :to="`/nowplaying/${encodeURIComponent(m.douban_id)}`"
          >
            <div class="npc__poster">
              <img v-if="m.poster" :src="m.poster" :alt="m.title || ''" loading="lazy" @error="m.poster = null">
              <div v-else class="npc__ph">{{ (m.title || '影').slice(0, 1) }}</div>
              <span class="npc__rank" :class="{ 'npc__rank--gold': i < 3 }">No.{{ i + 1 }}</span>
              <div class="npc__mask">查看采集档案</div>
              <div class="npc__shade">
                <span v-if="m.douban_rating" class="npc__score">★ {{ m.douban_rating.toFixed(1) }}</span>
              </div>
            </div>
            <div class="npc__body">
              <div class="npc__title" :title="m.title">{{ m.title || '（未命名）' }}</div>
              <div class="npc__meta">{{ m.release_year || '—' }} · {{ (m.region || []).join('/') || '—' }}</div>
            </div>
          </router-link>
        </div>
      </section>
    </template>
  </div>
</template>
