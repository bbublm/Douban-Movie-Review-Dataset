<script setup>
// ============================================================
// 类型混搭器 —— 清单「类型混搭器」模块。
//
// 交互：从标签池拖类型进「调酒台」，组合名实时生成，自动搜索。
// 拖拽用原生 HTML5 DnD（不引库，这个量级不值得）——
// 注意 dragover 必须 preventDefault，否则 drop 根本不触发（经典坑）。
//
// 宽松匹配：AND 组合经常一部都没有（"科幻+武侠"就是这样），
// 少于 3 部时自动补一批 OR 结果并标「接近匹配」，
// 比甩给用户一个空页面有用得多。
// ============================================================
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
import { blindBox } from '../composables/useBlindBox'
import { toast } from '../composables/useToast'
import PosterFan from '../components/mix/PosterFan.vue'
import WeatherScene from '../components/about/WeatherScene.vue'

const router = useRouter()

// 结果两种看法：海报扇（默认，可拖动的高颜值视图）/ 网格（横向比较全部）
const view = ref('fan')

const POOL = ['动作', '科幻', '喜剧', '爱情', '悬疑', '恐怖', '动画', '纪录片', '武侠', '黑色电影', '音乐', '历史']

const picked = ref([])
const loading = ref(false)
const resp = ref(null)
const loose = ref([])
const dragging = ref(null)
const dragOver = ref(false)

const comboName = computed(() => (picked.value.length ? picked.value.join(' + ') : '拖几个类型进来试试'))
const canSearch = computed(() => picked.value.length >= 2)

async function search() {
  if (!canSearch.value) { resp.value = null; loose.value = []; return }
  loading.value = true
  try {
    const data = await api.mix({ genres: picked.value, size: 20 })
    resp.value = data
    // 太独特 → 补一批 OR 结果
    if ((data?.hits || []).length < 3) {
      try {
        const or = await api.searchMovies({
          q: null, genres: picked.value, genre_op: 'or', size: 12, page: 1,
          sort: 'rating', order: 'desc', with_facets: false,
        })
        loose.value = or?.hits || []
      } catch { loose.value = [] }
    } else {
      loose.value = []
    }
  } catch (e) {
    toast.error(e.message)
    resp.value = null
  } finally {
    loading.value = false
  }
}

// 自动触发：组合变化就搜（清单允许自动触发），300ms 防抖
let timer = null
watch(picked, () => {
  clearTimeout(timer)
  timer = setTimeout(search, 300)
}, { deep: true })

function onDragStart(g) { dragging.value = g }
function onDrop() {
  dragOver.value = false
  const g = dragging.value
  dragging.value = null
  if (!g || picked.value.includes(g)) return
  if (picked.value.length >= 5) { toast.info('最多混搭 5 个类型'); return }
  picked.value = [...picked.value, g]
}
function remove(g) { picked.value = picked.value.filter((x) => x !== g) }
function clear() { picked.value = [] }
function random() {
  const n = 2 + Math.floor(Math.random() * 2)
  const pool = [...POOL].sort(() => Math.random() - 0.5)
  picked.value = pool.slice(0, n)
}
function replace(g) {
  remove(g)
  const next = POOL.find((x) => !picked.value.includes(x))
  if (next) picked.value = [...picked.value, next]
}
function openWithGenres(m) {
  blindBox.openBox(m.genres_zh || [])
}

function openMovie(m) {
  if (!m?.movie_id) return
  router.push(`/movie/${encodeURIComponent(m.movie_id)}`)
}
</script>

<template>
  <div class="container page">
    <div class="dash-header">
      <h1 class="dash-header__title">🍹 类型混搭器</h1>
      <p class="dash-header__sub">把两个八竿子打不着的类型倒在一起，看看能调出什么</p>
    </div>

    <!-- 标签池 -->
    <div class="panel mb-16">
      <div class="mix-pool__label">类型标签池（拖到右边的调酒台）</div>
      <div class="mix-pool">
        <span
          v-for="g in POOL"
          :key="g"
          class="gtag"
          :class="{ 'is-picked': picked.includes(g), 'is-dragging': dragging === g }"
          draggable="true"
          @dragstart="onDragStart(g)"
          @dragend="dragging = null"
          @click="picked.includes(g) ? remove(g) : (picked.length >= 5 ? toast.info('最多混搭 5 个类型') : picked.push(g))"
        >{{ g }}</span>
      </div>
    </div>

    <!-- 调酒台 -->
    <div
      class="mix-bar"
      :class="{ 'is-over': dragOver }"
      @dragover.prevent="dragOver = true"
      @dragleave="dragOver = false"
      @drop="onDrop"
    >
      <div class="mix-bar__label">调酒台</div>
      <div class="mix-bar__stage">
        <span v-if="!picked.length" class="mix-bar__ph">把标签拖到这里 →</span>
        <span v-for="g in picked" :key="g" class="gtag gtag--in" draggable="true" @dragstart="onDragStart(g)">
          {{ g }}
          <button class="gtag__x" @click.stop="remove(g)">×</button>
        </span>
      </div>
      <div class="mix-bar__ops">
        <span class="mix-bar__name">{{ comboName }}</span>
        <button class="btn btn--ghost btn--sm" @click="random">🎲 随机</button>
        <button class="btn btn--ghost btn--sm" @click="clear">清空</button>
      </div>
    </div>

    <!-- 结果 -->
    <div class="mt-24">
      <div v-if="loading" class="mix-grid">
        <div v-for="i in 8" :key="i" class="skeleton" style="height:260px;border-radius:12px" />
      </div>

      <template v-else>
        <p v-if="!canSearch" class="empty">
          <span class="empty__icon">🍹</span>
          至少选 2 个类型才能开始混搭
        </p>

        <template v-else>
          <div class="block__head">
            <h2 class="block__title">
              命中 {{ resp?.meta?.total ?? (resp?.hits || []).length }} 部
              <span class="block__note">（同时具备全部类型）</span>
            </h2>
            <div v-if="(resp?.hits || []).length" class="view-toggle" role="tablist" aria-label="结果视图">
              <button
                class="view-toggle__btn"
                :class="{ 'is-on': view === 'fan' }"
                role="tab"
                :aria-selected="view === 'fan'"
                @click="view = 'fan'"
              >海报扇</button>
              <button
                class="view-toggle__btn"
                :class="{ 'is-on': view === 'grid' }"
                role="tab"
                :aria-selected="view === 'grid'"
                @click="view = 'grid'"
              >网格</button>
            </div>
          </div>

          <!-- 海报扇直接摆进「天气剧场」：插画当舞台，四态可换，扇子仍是可拖可滚的
               hero=false 只留场景本体（不画中央圆盘和标语），高度由扇子撑开 -->
          <WeatherScene
            v-if="view === 'fan' && (resp?.hits || []).length"
            :hero="false"
            hint="拖动海报翻片 · 点空白处换天气"
          >
            <template #overlay>
              <PosterFan
                :movies="resp.hits"
                bare
                @open="openMovie"
                @blind="openWithGenres"
              />
            </template>
          </WeatherScene>

          <div v-else-if="(resp?.hits || []).length" class="mix-grid">
            <div v-for="m in resp.hits" :key="m.movie_id" class="mixcard" @click="router.push(`/movie/${encodeURIComponent(m.movie_id)}`)">
              <div class="mixcard__poster">
                <img v-if="m.poster_url" :src="m.poster_url" :alt="m.title" loading="lazy" />
                <div v-else class="mixcard__ph">🎬</div>
              </div>
              <div class="mixcard__title">{{ m.title }}</div>
              <div class="mixcard__meta">{{ m.release_year || '—' }} · {{ (m.genres_zh || []).slice(0, 2).join('/') }}</div>
              <div class="mixcard__score">⭐ {{ (m.rating ?? 0).toFixed(1) }}</div>
              <button class="btn btn--ghost btn--sm mixcard__btn" @click.stop="openWithGenres(m)">🎲 加入盲盒</button>
            </div>
          </div>

          <template v-if="loose.length">
            <p class="loose-tip">这个组合太独特了，试试这些接近的：</p>
            <div class="mix-grid">
              <div v-for="m in loose" :key="m.movie_id" class="mixcard" @click="router.push(`/movie/${encodeURIComponent(m.movie_id)}`)">
                <div class="mixcard__poster">
                  <img v-if="m.poster_url" :src="m.poster_url" :alt="m.title" loading="lazy" />
                  <div v-else class="mixcard__ph">🎬</div>
                </div>
                <div class="mixcard__title">{{ m.title }}</div>
                <div class="mixcard__meta">{{ m.release_year || '—' }} · {{ (m.genres_zh || []).slice(0, 2).join('/') }}</div>
                <div class="mixcard__score">⭐ {{ (m.rating ?? 0).toFixed(1) }}</div>
                <span class="mixcard__loose">接近匹配</span>
              </div>
            </div>
          </template>

          <p v-if="!(resp?.hits || []).length && !loose.length" class="empty">
            <span class="empty__icon">🎭</span>
            <span class="empty__title">这个组合太独特了</span>
            片库里没有同时具备这些类型的影片，换个搭配试试
          </p>
        </template>
      </template>
    </div>
  </div>
</template>
