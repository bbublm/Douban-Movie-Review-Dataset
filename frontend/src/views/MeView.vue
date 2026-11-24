<script setup>
// ============================================================
// 我的：评分记录 / 想看清单 / 我的记录（搜索历史 + 盲盒记录）/ 个人资料。
// 未登录展示引导卡，不假装有数据。
//
// 清单对齐（个人中心 P1）：
//   · 搜索历史：关键词 / 时间 / 结果数量，可单条删、可一键清空
//   · 盲盒记录：电影 / 推荐理由 / 时间，可再次查看详情
// 两者都是 localStorage 本机痕迹（composables 单例），
// 不走后端 —— 隐私口径更简单，也不需要登录就能积累。
// ============================================================
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
import { auth } from '../composables/useAuth'
import { blindBox } from '../composables/useBlindBox'
import { searchHistory } from '../composables/useSearchHistory'
import { toast } from '../composables/useToast'
import MovieCard from '../components/search/MovieCard.vue'

const router = useRouter()

// ---- 我的评分 ----
const ratings = ref([])
const ratingsLoading = ref(false)

// ---- 想看清单 ----
const watchlist = ref([])
const watchLoading = ref(false)

// ---- 资料 ----
const nickname = ref('')
const savingProfile = ref(false)
const pwdForm = ref({ old: '', next: '' })
const pwdError = ref('')
const pwdSaving = ref(false)

const watchItems = computed(() => watchlist.value.filter((w) => w.movie))

// ---- 我的记录：搜索历史 + 盲盒记录（localStorage 单例，响应式）----
const searchItems = computed(() => searchHistory.items.value)
const boxItems = computed(() => blindBox.history.value)

function fmtTime(ts) {
  if (!ts) return ''
  const d = new Date(ts)
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

function research(keyword) {
  router.push(`/search?q=${encodeURIComponent(keyword)}`)
}

function clearSearches() {
  searchHistory.clear()
  toast.info('搜索历史已清空')
}

function clearBoxes() {
  blindBox.clearHistory()
  toast.info('盲盒记录已清空')
}

async function loadAll() {
  if (!auth.isLoggedIn.value) return
  ratingsLoading.value = true
  watchLoading.value = true
  try {
    const [r, w] = await Promise.all([api.myRatings(), api.watchlist()])
    ratings.value = (r || []).sort((a, b) => (b.created_at || '').localeCompare(a.created_at || ''))
    watchlist.value = w.items || []
  } catch (e) {
    toast.error(e.message)
  } finally {
    ratingsLoading.value = false
    watchLoading.value = false
  }
}

async function removeRating(movieId, title) {
  try {
    await api.deleteRating(movieId)
    ratings.value = ratings.value.filter((r) => r.movie_id !== movieId)
    toast.info(`已删除《${title || movieId}》的评分`)
  } catch (e) {
    toast.error(e.message)
  }
}

async function removeWatch(movieId) {
  try {
    await api.removeWatch(movieId)
    watchlist.value = watchlist.value.filter((w) => w.movie_id !== movieId)
    toast.info('已移出想看清单')
  } catch (e) {
    toast.error(e.message)
  }
}

async function saveNickname() {
  const n = nickname.value.trim()
  if (!n) return
  savingProfile.value = true
  try {
    await api.updateProfile({ nickname: n })
    await auth.refreshUser()
    toast.success('昵称已更新')
  } catch (e) {
    toast.error(e.message)
  } finally {
    savingProfile.value = false
  }
}

async function changePassword() {
  pwdError.value = ''
  if (pwdForm.value.next.length < 6) {
    pwdError.value = '新密码至少 6 位'
    return
  }
  pwdSaving.value = true
  try {
    await api.changePassword({ old_password: pwdForm.value.old, new_password: pwdForm.value.next })
    pwdForm.value = { old: '', next: '' }
    toast.success('密码已修改，下次登录用新密码')
  } catch (e) {
    pwdError.value = e.message
  } finally {
    pwdSaving.value = false
  }
}

onMounted(async () => {
  await auth.init()
  if (auth.isLoggedIn.value) {
    nickname.value = auth.state.user?.nickname || ''
    await loadAll()
  }
})
</script>

<template>
  <div class="container page">
    <h1 class="page-title">我的</h1>
    <p class="page-subtitle">评分记录 · 想看清单 · 我的记录 · 个人资料</p>

    <div v-if="!auth.isLoggedIn.value" class="empty card">
      <div class="empty__icon">🔐</div>
      <div class="empty__title">还没有登录</div>
      <p>登录后可以给影片评分、管理想看清单、获得个性化推荐</p>
      <button class="btn btn--primary mt-16" @click="router.push('/login?next=/me')">去登录 / 注册</button>
    </div>

    <template v-else>
      <!-- 我的评分 -->
      <h2 class="section-title">⭐ 我的评分（{{ ratings.length }}）</h2>
      <div v-if="ratingsLoading" class="rank-list">
        <div v-for="i in 3" :key="i" class="skeleton" style="height:64px;border-radius:10px" />
      </div>
      <div v-else-if="!ratings.length" class="empty card">
        <div class="empty__icon">⭐</div>
        <div class="empty__title">还没有评分</div>
        <p>在任意影片详情里打 1~10 分，这里就会出现记录</p>
      </div>
      <div v-else class="rank-list">
        <div v-for="r in ratings" :key="r.movie_id" class="rank-row" style="cursor:default">
          <span class="rank-row__no rank-row__no--top">{{ r.score }}</span>
          <div class="rank-row__main">
            <div class="rank-row__title">{{ r.movie_title || r.movie_id }}</div>
            <div class="rank-row__reason">{{ r.created_at ? new Date(r.created_at).toLocaleString('zh-CN') : '' }}</div>
          </div>
          <button class="btn btn--ghost btn--sm" @click="removeRating(r.movie_id, r.movie_title)">删除</button>
        </div>
      </div>

      <!-- 想看清单 -->
      <h2 class="section-title">🎬 想看清单（{{ watchlist.length }}）</h2>
      <div v-if="watchLoading" class="movie-grid movie-grid--skeleton">
        <div v-for="i in 4" :key="i" class="movie-card" style="cursor:default">
          <div class="skeleton" style="aspect-ratio:2/3;border-radius:0" />
        </div>
      </div>
      <div v-else-if="!watchlist.length" class="empty card">
        <div class="empty__icon">🎬</div>
        <div class="empty__title">想看清单是空的</div>
        <p>在影片卡片或详情里点 ☆ 收藏想看的片</p>
      </div>
      <div v-else class="movie-grid">
        <div v-for="w in watchItems" :key="w.movie_id" style="position:relative">
          <MovieCard
            :movie="w.movie"
            :watched="true"
            :my-score="null"
            @open="$router.push(`/?q=${encodeURIComponent(w.movie.title_zh || w.movie.title || '')}`)"
            @toggle-watch="removeWatch(w.movie_id)"
          />
          <button
            class="btn btn--ghost btn--sm"
            style="position:absolute;right:8px;bottom:8px;z-index:2"
            @click="removeWatch(w.movie_id)"
          >移出</button>
        </div>
        <div v-for="w in watchlist.filter(x => !x.movie)" :key="`x-${w.movie_id}`" class="review-card">
          <div class="review-card__movie">{{ w.movie_title || w.movie_id }}</div>
          <p class="text-3 text-xs">该影片已不在当前影片库中，仅保留标题记录</p>
          <button class="btn btn--ghost btn--sm mt-8" @click="removeWatch(w.movie_id)">移出</button>
        </div>
      </div>

      <!-- 我的记录：搜索历史 + 盲盒记录（功能清单 P1）-->
      <h2 class="section-title">🗂 我的记录</h2>
      <div class="me-grid">
        <div class="panel">
          <h3 class="fun-panel__title">
            搜索历史（{{ searchItems.length }}）
            <button v-if="searchItems.length" class="btn btn--ghost btn--sm" @click="clearSearches">清空</button>
          </h3>
          <div v-if="!searchItems.length" class="text-3 text-sm">还没有搜索记录 —— 在搜索框里搜点什么试试</div>
          <div v-else class="rank-list">
            <div v-for="h in searchItems" :key="h.keyword" class="rank-row" style="cursor:pointer" @click="research(h.keyword)">
              <span class="rank-row__no">🔍</span>
              <div class="rank-row__main">
                <div class="rank-row__title">{{ h.keyword }}</div>
                <div class="rank-row__reason">
                  {{ fmtTime(h.time) }}
                  <span v-if="h.count != null"> · {{ h.count }} 条结果</span>
                </div>
              </div>
              <button
                class="btn btn--ghost btn--sm"
                @click.stop="searchHistory.remove(h.keyword)"
              >删除</button>
            </div>
          </div>
        </div>

        <div class="panel">
          <h3 class="fun-panel__title">
            盲盒记录（{{ boxItems.length }}）
            <button v-if="boxItems.length" class="btn btn--ghost btn--sm" @click="clearBoxes">清空</button>
          </h3>
          <div v-if="!boxItems.length" class="text-3 text-sm">还没有开过盲盒 —— 点导航栏「🎲 随便看看」</div>
          <div v-else class="rank-list">
            <div v-for="b in boxItems" :key="b.movie_id" class="rank-row" style="cursor:pointer" @click="router.push(`/movie/${encodeURIComponent(b.movie_id)}`)">
              <img v-if="b.poster_url" :src="b.poster_url" :alt="b.title" class="boxlog__poster" />
              <span v-else class="rank-row__no">🎲</span>
              <div class="rank-row__main">
                <div class="rank-row__title">{{ b.title }}<span v-if="b.year" class="text-3"> （{{ b.year }}）</span></div>
                <div class="rank-row__reason">{{ b.reason }}</div>
                <div class="rank-row__reason text-3">{{ fmtTime(b.time) }}</div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 个人资料 -->
      <h2 class="section-title">⚙️ 个人资料</h2>
      <div class="me-grid">
        <div class="panel">
          <h3 class="fun-panel__title">基本信息</h3>
          <div class="field">
            <label class="field__label">用户名（不可改，它是数据主键）</label>
            <input class="input" :value="auth.state.user?.username" disabled />
          </div>
          <div class="field">
            <label class="field__label">角色</label>
            <input class="input" :value="auth.state.user?.role === 'admin' ? '管理员' : '普通用户'" disabled />
          </div>
          <div class="field">
            <label class="field__label">昵称</label>
            <div class="flex gap-8">
              <input v-model="nickname" class="input" maxlength="32" placeholder="展示名" />
              <button class="btn btn--primary" :disabled="savingProfile || !nickname.trim()" @click="saveNickname">保存</button>
            </div>
          </div>
        </div>

        <div class="panel">
          <h3 class="fun-panel__title">修改密码</h3>
          <div v-if="pwdError" class="alert alert--error auth-error"><span>⚠️</span><span>{{ pwdError }}</span></div>
          <div class="field">
            <label class="field__label">当前密码</label>
            <input v-model="pwdForm.old" class="input" type="password" autocomplete="current-password" />
          </div>
          <div class="field">
            <label class="field__label">新密码（至少 6 位）</label>
            <input v-model="pwdForm.next" class="input" type="password" autocomplete="new-password" />
          </div>
          <button class="btn btn--primary" :disabled="pwdSaving || !pwdForm.old || !pwdForm.next" @click="changePassword">
            {{ pwdSaving ? '提交中…' : '修改密码' }}
          </button>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
/* 页面布局样式见 src/styles/pages.css（已在 main.js 全局引入） */
.boxlog__poster {
  width: 34px;
  height: 50px;
  object-fit: cover;
  border-radius: 5px;
  flex: none;
  background: var(--surface-2);
}
.fun-panel__title { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
</style>
