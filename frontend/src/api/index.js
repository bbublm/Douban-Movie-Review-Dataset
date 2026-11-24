/* ============================================================
   API 请求层 —— 原生 fetch 封装，不引 axios（接口少而简单）。

   三个设计点：
   1. **错误归一化**：FastAPI 的 detail 有三种形态（字符串 / 对象 / 422 数组），
      统一翻译成 ApiError{status, message}，组件里只需 catch 一个字段。
   2. **token 单一入口**：登录态存在 localStorage，这里持有唯一引用；
      401 时自动清理并派发 yj:auth-expired 事件，useAuth 监听后同步登出。
   3. **路径基准**：全部走 /api/v1 前缀，dev 期由 vite 代理到 8000，
      生产由 nginx 反代，前端代码零环境判断。
   ============================================================ */

const BASE = '/api/v1'
const TOKEN_KEY = 'yj_token'

let token = localStorage.getItem(TOKEN_KEY) || ''

export function setToken(next) {
  token = next || ''
  if (token) {
    localStorage.setItem(TOKEN_KEY, token)
  } else {
    localStorage.removeItem(TOKEN_KEY)
  }
}

export class ApiError extends Error {
  constructor(status, message, detail) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.detail = detail
  }
}

/** 把 FastAPI 的 detail（字符串 / {message,hint,error} / 422 数组）翻成人话。 */
function humanizeDetail(detail, status) {
  if (!detail) return `请求失败（HTTP ${status}）`
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    // pydantic 422：[{loc, msg, type}...]
    return detail
      .map((e) => `${(e.loc || []).slice(-1)[0] || '参数'}：${e.msg}`)
      .join('；')
  }
  if (typeof detail === 'object') {
    return [detail.message, detail.hint].filter(Boolean).join(' —— ') || `请求失败（HTTP ${status}）`
  }
  return String(detail)
}

async function request(path, { method = 'GET', body } = {}) {
  const headers = {}
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (token) headers.Authorization = `Bearer ${token}`

  let resp
  try {
    resp = await fetch(BASE + path, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    })
  } catch {
    throw new ApiError(0, '连不上后端服务：请确认 uvicorn（127.0.0.1:8000）已启动')
  }

  if (resp.status === 204) return null

  const text = await resp.text()
  let data = null
  if (text) {
    try { data = JSON.parse(text) } catch { /* 非 JSON 响应体（如网关错误页）原样带出 */ }
  }

  if (!resp.ok) {
    // token 失效（过期 / 用户被删）：自动登出，避免界面停留在"已登录"的假象
    if (resp.status === 401 && token) {
      setToken(null)
      window.dispatchEvent(new Event('yj:auth-expired'))
    }
    throw new ApiError(resp.status, humanizeDetail(data?.detail, resp.status), data)
  }
  return data
}

/** GET 查询串小工具：自动跳过 null/undefined/空数组。 */
function qs(params = {}) {
  const p = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v === null || v === undefined || v === '') continue
    if (Array.isArray(v)) {
      if (!v.length) continue
      v.forEach((item) => p.append(k, item))
    } else {
      p.set(k, String(v))
    }
  }
  const s = p.toString()
  return s ? `?${s}` : ''
}

export const api = {
  // ---- 混合检索 ----
  searchMovies: (body) => request('/search/movies', { method: 'POST', body }),
  searchReviews: (body) => request('/search/reviews', { method: 'POST', body }),
  suggest: (q, size = 8) => request(`/search/suggest${qs({ q, size })}`),
  getMovie: (id) => request(`/search/movies/${encodeURIComponent(id)}`),

  // ---- 院线热映（站内采集档案，卡片点击不出站） ----
  nowPlaying: () => request('/douban/nowplaying'),
  nowPlayingDetail: (id) => request(`/douban/nowplaying/${encodeURIComponent(id)}`),
  doubanInsights: () => request('/douban/insights'),

  // ---- 影评洞察 ----
  sentimentStats: () => request('/insights/sentiment'),
  trends: () => request('/insights/trends'),
  matrix: () => request('/insights/matrix'),
  boxOffice: (top = 24) => request(`/insights/box-office${qs({ top })}`),
  topics: (top = 30) => request(`/insights/topics${qs({ top })}`),
  lexicon: (top = 20) => request(`/insights/lexicon${qs({ top })}`),
  movieInsight: (id) => request(`/insights/movies/${encodeURIComponent(id)}`),
  movieVoices: (id, size = 8) =>
    request(`/insights/movies/${encodeURIComponent(id)}/voices${qs({ size })}`),
  polarizing: () => request('/insights/polarizing'),
  regions: () => request('/insights/regions'),
  story: () => request('/insights/story'),
  // 深度分析（2026-11-04）：全部由 ES 聚合 + 后端现算得出
  hallPosters: () => request('/insights/hall-posters'),
  knowledgeGraph: () => request('/insights/knowledge-graph'),
  correlations: () => request('/insights/correlations'),
  flows: () => request('/insights/flows'),
  scoreText: (text, lang = 'auto') =>
    request('/insights/sentiment', { method: 'POST', body: { text, lang } }),

  // ---- 推荐 ----
  popular: (size = 20) => request(`/recommend/popular${qs({ size })}`),
  similar: (id, size = 10) =>
    request(`/recommend/similar/${encodeURIComponent(id)}${qs({ size })}`),
  forYou: (size = 20) => request(`/recommend/for-you${qs({ size })}`),

  // ---- 评分 ----
  rate: (movie_id, score) => request('/ratings', { method: 'POST', body: { movie_id, score } }),
  myRatings: () => request('/ratings'),
  deleteRating: (movie_id) =>
    request(`/ratings/${encodeURIComponent(movie_id)}`, { method: 'DELETE' }),

  // ---- 趣味功能 ----
  mix: (body) => request('/fun/mix', { method: 'POST', body }),
  box: ({ seed = null, genres = [], minRating = 7 } = {}) =>
    request(`/fun/box${qs({ seed, genres, min_rating: minRating })}`),

  // ---- 认证 ----
  register: (body) => request('/auth/register', { method: 'POST', body }),
  login: (body) => request('/auth/login', { method: 'POST', body }),
  me: () => request('/auth/me'),
  updateProfile: (body) => request('/auth/me', { method: 'PATCH', body }),
  changePassword: (body) => request('/auth/change-password', { method: 'POST', body }),

  // ---- 想看清单 ----
  watchlist: () => request('/watchlist'),
  addWatch: (movie_id) =>
    request(`/watchlist/${encodeURIComponent(movie_id)}`, { method: 'POST' }),
  removeWatch: (movie_id) =>
    request(`/watchlist/${encodeURIComponent(movie_id)}`, { method: 'DELETE' }),
}
