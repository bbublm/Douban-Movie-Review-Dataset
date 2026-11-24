/* ============================================================
   影片操作组合式函数 —— 评分 / 想看 / 详情弹窗 / 找相似。
   首页（HomeView）与检索页（SearchView）共用同一份实现：
   行为数据操作只有一处真相，改规则不用记着改两个地方。
   ============================================================ */

import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
import { auth } from './useAuth'
import { toast } from './useToast'

export function useMovieActions() {
  const router = useRouter()

  const watchedIds = ref(new Set())
  const myScores = ref({})
  const detail = ref(null)

  function requireLogin(action) {
    if (auth.isLoggedIn.value) return true
    toast.info(`请先登录后再${action}`)
    router.push({ path: '/login', query: { next: router.currentRoute.value.fullPath } })
    return false
  }

  async function loadWatchlist() {
    if (!auth.isLoggedIn.value) return
    try {
      const data = await api.watchlist()
      watchedIds.value = new Set((data.items || []).map((i) => i.movie_id))
    } catch {
      /* 想看状态是增强信息，加载失败不阻塞主流程 */
    }
  }

  async function loadMyRatings() {
    if (!auth.isLoggedIn.value) return
    try {
      const list = await api.myRatings()
      const map = {}
      ;(list || []).forEach((r) => { map[r.movie_id] = r.score })
      myScores.value = map
    } catch {
      /* 同上 */
    }
  }

  async function onToggleWatch(movie) {
    if (!requireLogin('管理想看清单')) return
    try {
      if (watchedIds.value.has(movie.movie_id)) {
        await api.removeWatch(movie.movie_id)
        watchedIds.value.delete(movie.movie_id)
        toast.success(`已移出想看：${movie.title_zh || movie.title}`)
      } else {
        await api.addWatch(movie.movie_id)
        watchedIds.value.add(movie.movie_id)
        toast.success(`已加入想看：${movie.title_zh || movie.title}`)
      }
    } catch (e) {
      toast.error(e.message)
    }
  }

  async function onRate(score) {
    const movie = detail.value
    if (!movie || !requireLogin('评分')) return
    try {
      await api.rate(movie.movie_id, score)
      myScores.value[movie.movie_id] = score
      toast.success(`已记录：《${movie.title_zh || movie.title}》${score} 分`)
    } catch (e) {
      toast.error(e.message)
    }
  }

  async function onDeleteRating() {
    const movie = detail.value
    if (!movie) return
    try {
      await api.deleteRating(movie.movie_id)
      delete myScores.value[movie.movie_id]
      toast.info('已删除评分')
    } catch (e) {
      toast.error(e.message)
    }
  }

  function openDetail(movie) {
    detail.value = movie
  }
  function closeDetail() {
    detail.value = null
  }
  function onSimilar(movie) {
    detail.value = null
    // 发现页已移除（与其他页面功能冲突）：找相似统一去影片详情页的「🎯 相似推荐」区块
    router.push(`/movie/${encodeURIComponent(movie.movie_id)}`)
  }

  return {
    watchedIds,
    myScores,
    detail,
    requireLogin,
    loadWatchlist,
    loadMyRatings,
    onToggleWatch,
    onRate,
    onDeleteRating,
    openDetail,
    closeDetail,
    onSimilar,
  }
}
