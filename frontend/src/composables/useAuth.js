/* ============================================================
   登录态单例 —— 不引 Pinia：全站共享状态只有"谁登录了"一处，
   reactive 单例 + localStorage 持久化足够，少一条依赖链。

   与 api 层的分工：
   · api/index.js 持有 token 引用并负责 401 自动清理；
   · 本文件持有 user 资料，监听 yj:auth-expired 同步登出。
   ============================================================ */

import { reactive, computed } from 'vue'
import { api, setToken } from '../api'

const state = reactive({
  token: localStorage.getItem('yj_token') || '',
  user: null,       // UserPublic：{username, role, nickname, created_at}
})

const isLoggedIn = computed(() => !!state.token && !!state.user)
const isAdmin = computed(() => state.user?.role === 'admin')

// token 失效（过期/被删）时 api 层派发的事件 → 同步登出，避免假登录态
window.addEventListener('yj:auth-expired', () => {
  state.user = null
})

// init 的并发安全：App.vue 与各视图 onMounted 都会调 init()，
// 必须共享**同一个进行中的 promise**，否则后调者拿到的还是"未完成"状态
// （user 仍为 null → isLoggedIn=false → 视图跳过数据加载，且不会重试）。
let initPromise = null

function init() {
  if (!initPromise) {
    initPromise = (async () => {
      if (!state.token) return
      try {
        state.user = await api.me()
      } catch {
        doLogout()
      }
    })()
  }
  return initPromise
}

function applyAuth(data) {
  state.token = data.access_token
  state.user = data.user
  setToken(data.access_token)
}

async function login(username, password) {
  applyAuth(await api.login({ username, password }))
}

async function register(username, password, nickname) {
  applyAuth(await api.register({ username, password, nickname: nickname || undefined }))
}

function doLogout() {
  state.token = ''
  state.user = null
  setToken(null)
}

async function refreshUser() {
  if (state.token) {
    state.user = await api.me()
  }
}

export const auth = {
  state,
  isLoggedIn,
  isAdmin,
  init,
  login,
  register,
  logout: doLogout,
  refreshUser,
}

/** 兼容组合式函数习惯用法（内部就是同一个单例）。 */
export function useAuth() {
  return auth
}
