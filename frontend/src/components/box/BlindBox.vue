<script setup>
// ============================================================
// 盲盒弹窗（全局）—— 清单里的开盒动画在这里：
//   盒子弹入(0.2s) → 抖动 3 次(0.6s) → 开盒射光(0.2s) → 卡片升起(0.5s) ≈ 1.5s
//
// 动画用 CSS keyframes + animation-delay 串起来，不用 JS 定时器：
// 定时器会和 Vue 的渲染时序打架（数据到了但动画已播完），
// 而纯 CSS 只要给卡片换个 :key 就能整段重放。
// ============================================================
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../../api'
import { auth } from '../../composables/useAuth'
import { blindBox } from '../../composables/useBlindBox'
import { toast } from '../../composables/useToast'

const router = useRouter()
const watched = ref(new Set())
const saving = ref(false)

const { visible, movie, loading, error, count, history } = blindBox

watch(visible, async (v) => {
  if (v && auth.isLoggedIn.value) {
    try {
      const list = await api.watchlist()
      watched.value = new Set((list?.items || list?.movie_ids || []).map((x) => x.movie_id || x))
    } catch { /* 未登录或接口挂了：不影响开盒 */ }
  }
})

function close() { blindBox.close() }

function onKey(e) {
  if (e.key === 'Escape' && visible.value) close()
}
onMounted(() => document.addEventListener('keydown', onKey))
onUnmounted(() => document.removeEventListener('keydown', onKey))

function goDetail() {
  if (!movie.value) return
  close()
  router.push(`/movie/${encodeURIComponent(movie.value.movie_id)}`)
}

async function toggleWatch() {
  if (!auth.isLoggedIn.value) {
    toast.info('登录后才能收藏这部片')
    router.push('/login')
    return
  }
  if (!movie.value) return
  saving.value = true
  try {
    if (watched.value.has(movie.value.movie_id)) {
      await api.removeWatch(movie.value.movie_id)
      watched.value.delete(movie.value.movie_id)
      toast.success('已取消收藏')
    } else {
      await api.addWatch(movie.value.movie_id)
      watched.value.add(movie.value.movie_id)
      toast.success('已加入收藏')
    }
    watched.value = new Set(watched.value)
  } catch (e) {
    toast.error(e.message)
  } finally {
    saving.value = false
  }
}

function stars(rating) {
  const n = Math.round((rating || 0) / 2)
  return '★'.repeat(n) + '☆'.repeat(Math.max(0, 5 - n))
}
</script>

<template>
  <div v-if="visible" class="box-mask" @click.self="close">
    <div class="box-modal">
      <button class="box-close" @click="close">×</button>

      <div class="box-stagearea">
        <!-- 开盒中：金色盒子 + 抖动 -->
        <template v-if="loading || error">
          <div class="box-chest" :class="{ 'is-shaking': loading }">
            <div class="box-chest__body">🎁</div>
            <div class="box-chest__lid"></div>
          </div>
          <p v-if="error" class="box-error">{{ error }}</p>
          <p v-else class="box-tip">正在开盒…</p>
        </template>

        <!-- 已开出：光束 + 卡片升起 -->
        <div v-else-if="movie" class="box-result" :key="movie.movie_id">
          <div class="box-beam"></div>
          <div class="box-card">
            <div class="box-card__poster">
              <img v-if="movie.poster_url" :src="movie.poster_url" :alt="movie.title" />
              <div v-else class="box-card__ph">🎬</div>
            </div>
            <div class="box-card__info">
              <h3 class="box-card__title">{{ movie.title }}</h3>
              <div class="box-card__meta">
                {{ movie.release_year || '—' }} ·
                {{ (movie.genres_zh || []).slice(0, 3).join(' / ') || '—' }} ·
                {{ (movie.production_countries || [])[0] || '—' }}
              </div>
              <div class="box-card__score">
                <span class="stars">{{ stars(movie.rating) }}</span>
                <span class="stars__value">{{ (movie.rating ?? 0).toFixed(1) }}</span>
                <span class="box-card__votes">{{ (movie.votes || 0).toLocaleString() }} 人评</span>
              </div>
              <p class="box-card__reason">“{{ history.find((h) => h.movie_id === movie.movie_id)?.reason || '' }}”</p>
            </div>
          </div>
        </div>
      </div>

      <div class="box-actions">
        <button class="btn btn--ghost" @click="blindBox.again()" :disabled="loading">🎲 换一个</button>
        <button class="btn btn--ghost" @click="toggleWatch" :disabled="!movie || saving">
          {{ movie && watched.has(movie.movie_id) ? '★ 已收藏' : '☆ 收藏' }}
        </button>
        <button class="btn btn--primary" :disabled="!movie" @click="goDetail">查看详情</button>
      </div>

      <div class="box-foot">已开 {{ count }} 个盲盒 · 按 Esc 或点击空白处关闭</div>
    </div>
  </div>
</template>
