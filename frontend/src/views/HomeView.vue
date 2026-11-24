<script setup>
// ============================================================
// 首页 —— 清单「首页」模块：
//   Hero（主副标题 + 640×56 大搜索框 + 热门词 + 🎲 盲盒入口 + 右侧光盘展台）
//   🔥 大家都在看（横向滚动海报，悬停上浮 4px）
//   🎞️ 院线热映 Top 10（卡片一律进站内采集档案，不外链源站）
//   🎬 怪兽合影（静态设计稿图片）
// ============================================================
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
import { blindBox } from '../composables/useBlindBox'
import GlobalSearch from '../components/layout/GlobalSearch.vue'
import HeroDiscs from '../components/home/HeroDiscs.vue'

const router = useRouter()

const hot = ref([])
const nowPlaying = ref([])
const loading = ref(true)
const err = ref('')

onMounted(async () => {
  const jobs = [
    api.popular(20).then((d) => {
      // /recommend/popular 返回 {items:[{movie: MovieHit}]} 包装结构，解包成扁平对象
      hot.value = (d?.items || d?.hits || []).map((it) => it.movie || it)
    }).catch(() => {}),
    // 院线热映 Top 10：爬虫采集的榜单，按评分降序取前 10
    api.nowPlaying().then((d) => { nowPlaying.value = d?.items || [] }).catch(() => {}),
  ]
  await Promise.all(jobs)
  loading.value = false
})

// 院线热映：按采集评分降序取前 10（评分缺失的沉底，按票数兜底）
const nowTop = computed(() => {
  const list = [...nowPlaying.value]
  list.sort((a, b) => {
    const ra = a.douban_rating ?? -1
    const rb = b.douban_rating ?? -1
    if (rb !== ra) return rb - ra
    return (b.douban_votes || 0) - (a.douban_votes || 0)
  })
  return list.slice(0, 10)
})

// 热门搜索词（功能清单 P1）：从「大家都在看」的类型频次派生前 6 个，
// 数据驱动、不写死；加载完热门列表前隐藏该行。
const hotWords = computed(() => {
  const freq = new Map()
  for (const m of hot.value) {
    for (const g of m.genres_zh || []) freq.set(g, (freq.get(g) || 0) + 1)
  }
  return [...freq.entries()].sort((a, b) => b[1] - a[1]).slice(0, 6).map(([g]) => g)
})

function goSearch(w) {
  router.push(`/search?q=${encodeURIComponent(w)}`)
}

function goMovie(m) {
  router.push(`/movie/${encodeURIComponent(m.movie_id)}`)
}
</script>

<template>
  <div class="home">
    <!-- ===== Hero：原系统 dashboard-header 的 pattern 背景 + 棕灰叠加 ===== -->
    <section class="hero">
      <!-- 光盘展台：复刻 A24 实体 CD 效果，叠在 Hero 右侧预留列，不占额外滚动高度 -->
      <HeroDiscs v-if="!loading && hot.length" :movies="hot" />
      <div class="hero__inner">
        <h1 class="hero__title">搜电影，也可以很好玩</h1>
        <p class="hero__sub">影片与影评检索 · 口碑分析 · 随机盲盒 · 采集演示</p>

        <div class="hero__searchrow">
          <GlobalSearch size="lg" />
          <button class="btn-box btn-box--lg" @click="blindBox.openBox()">🎲 随便看看</button>
        </div>

        <!-- 热门搜索词（功能清单 P1）：从热门片单类型频次派生 -->
        <div v-if="hotWords.length" class="hero__hotwords">
          <span class="hero__hotlabel">大家都在搜</span>
          <button v-for="w in hotWords" :key="w" class="hero__hotword" @click="goSearch(w)">{{ w }}</button>
        </div>
      </div>
    </section>

    <div class="container home__body">
      <!-- ===== 大家都在看（原首页内容，结构未改动） ===== -->
      <section class="block">
        <div class="block__head">
          <h2 class="block__title">🔥 大家都在看</h2>
          <router-link class="block__more" to="/search?sort=popularity">查看更多 →</router-link>
        </div>

        <div v-if="loading" class="horizon">
          <div v-for="i in 8" :key="i" class="skeleton" style="width:150px;height:250px;border-radius:12px" />
        </div>
        <div v-else class="horizon">
          <div
            v-for="m in hot"
            :key="m.movie_id"
            class="hcard"
            @click="goMovie(m)"
          >
            <div class="hcard__poster">
              <img v-if="m.poster_url" :src="m.poster_url" :alt="m.title" loading="lazy" />
              <div v-else class="hcard__ph">🎬</div>
              <div class="hcard__mask">查看详情</div>
              <div v-if="m.rating" class="hcard__score">{{ m.rating.toFixed(1) }}</div>
            </div>
            <div class="hcard__title" :title="m.title">{{ m.title }}</div>
            <div class="hcard__meta">{{ m.year || m.release_year || '—' }} · {{ (m.genres_zh || [])[0] || '' }}</div>
          </div>
        </div>
      </section>

      <!-- ===== 院线热映 Top 10（爬虫采集榜单，点击进站内档案页） ===== -->
      <section class="block">
        <div class="block__head">
          <h2 class="block__title">🎞️ 院线热映 <span class="block__sub">Top 10</span></h2>
          <span class="block__note">站内采集档案 · 按评分排序</span>
        </div>

        <div v-if="loading" class="horizon">
          <div v-for="i in 10" :key="i" class="skeleton" style="width:150px;height:290px;border-radius:14px" />
        </div>
        <div v-else-if="nowTop.length" class="horizon">
          <router-link
            v-for="(m, i) in nowTop"
            :key="m.douban_id"
            class="npc"
            :to="`/nowplaying/${encodeURIComponent(m.douban_id)}`"
            :aria-label="`查看《${m.title || '影片'}》的站内采集档案`"
          >
            <div class="npc__poster">
              <img
                v-if="m.poster"
                :src="m.poster"
                :alt="m.title || ''"
                loading="lazy"
                @error="m.poster = null"
              >
              <div v-else class="npc__ph">{{ (m.title || '影').slice(0, 1) }}</div>
              <span class="npc__rank" :class="{ 'npc__rank--gold': i < 3 }">No.{{ i + 1 }}</span>
              <div class="npc__mask">查看采集档案</div>
              <div class="npc__shade">
                <span v-if="m.douban_rating" class="npc__score">★ {{ m.douban_rating.toFixed(1) }}</span>
                <span v-if="m.duration" class="npc__dur">{{ m.duration }}</span>
              </div>
            </div>
            <div class="npc__body">
              <div class="npc__title" :title="m.title">{{ m.title || '（未命名）' }}</div>
              <div class="npc__meta">{{ m.release_year || '—' }} · {{ (m.region || []).join('/') || '—' }}</div>
              <div v-if="(m.director || []).length" class="npc__meta npc__meta--dim">{{ m.director.join(' / ') }}</div>
            </div>
          </router-link>
        </div>
        <p v-else class="empty p-16">暂无院线热映数据</p>
      </section>

      <!-- ===== 角色合影 ===== -->
      <section class="block">
        <div class="block__head">
          <h2 class="block__title">🎬 怪兽合影</h2>
          <span class="block__note">设计稿素材</span>
        </div>
        <div class="caststill">
          <img
            src="/images/cast-group.jpg"
            alt="怪兽合影"
            loading="lazy"
            class="caststill__img"
          />
        </div>
      </section>
    </div>
  </div>
</template>
