// ============================================================
// 盲盒状态（全局单例）—— 导航栏、首页 Hero、检索页、混搭器都要能开盲盒，
// 所以状态必须提到组件之外，否则每个入口各自维护一份，计数和历史会对不上。
//
// 清单对齐：
//  · 开盒计数（本次会话）+ 历史记录（localStorage，个人中心可看）
//  · 抽签用后端 seed：同一个 seed 抽到的片固定，"换一个"才换 seed
// ============================================================
import { ref } from 'vue'
import { api } from '../api'

const KEY = 'yj_box_history'

function readHistory() {
  try {
    const raw = JSON.parse(localStorage.getItem(KEY) || '[]')
    return Array.isArray(raw) ? raw : []
  } catch {
    return []
  }
}

const visible = ref(false)
const movie = ref(null)
const loading = ref(false)
const error = ref('')
const seed = ref(null)
const count = ref(0)
const history = ref(readHistory())
const genres = ref([])

function persist() {
  try {
    localStorage.setItem(KEY, JSON.stringify(history.value.slice(0, 50)))
  } catch { /* 隐私模式忽略 */ }
}

async function draw() {
  loading.value = true
  error.value = ''
  movie.value = null
  try {
    const data = await api.box({ seed: seed.value, genres: genres.value, minRating: 6.5 })
    movie.value = data?.movie || null
    seed.value = data?.seed ?? null
    error.value = data?.movie ? '' : (data?.note || '这个条件下没抽到片子')
    if (movie.value) {
      count.value += 1
      history.value = [
        {
          movie_id: movie.value.movie_id,
          title: movie.value.title,
          year: movie.value.release_year,
          poster_url: movie.value.poster_url,
          reason: reasonOf(movie.value),
          time: Date.now(),
        },
        ...history.value.filter((x) => x.movie_id !== movie.value.movie_id),
      ]
      persist()
    }
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

// 推荐理由：清单给了五条规则，但只有「冷门高分」有数据支撑
// （Kaggle 影评没有片名、没有时间维度，"首周评分/争议比例"都算不出来），
// 剩下几条先用可算的口径兜底，并从接口取值而不是编数字。
export function reasonOf(m) {
  const rating = m.vote_average ?? m.rating ?? 0
  const votes = m.vote_count ?? 0
  if (rating >= 7.5 && votes && votes < 5000) {
    return `只有 ${votes.toLocaleString()} 人看过，但均分 ${rating.toFixed(1)} —— 冷门高分。`
  }
  if (rating >= 8) return `均分 ${rating.toFixed(1)}，属于那种"没看过会遗憾"的片子。`
  if (votes > 50000) return `${votes.toLocaleString()} 人评过，群众基础扎实。`
  if (m.release_year && m.release_year < 1990) return `${m.release_year} 年的老片，适合换个口味。`
  return '随机抽中的一部，好不好看看缘分。'
}

export const blindBox = {
  visible,
  movie,
  loading,
  error,
  count,
  history,
  genres,
  draw,
  openBox(nextGenres = []) {
    genres.value = nextGenres
    seed.value = null
    visible.value = true
    draw()
  },
  async again() {
    seed.value = null
    await draw()
  },
  close() {
    visible.value = false
  },
  clearHistory() {
    history.value = []
    persist()
  },
}
