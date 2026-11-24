/* ============================================================
   全局轻提示 —— 不引 UI 库，一个单例 + 一个宿主组件够用。
   典型场景：未登录时点「想看」→ 提示并跳登录页；操作成功/失败的反馈。
   ============================================================ */

import { reactive } from 'vue'

const state = reactive({
  toasts: [],   // {id, type: 'info'|'success'|'error', message, timeout}
  seq: 0,
})

function dismiss(id) {
  const i = state.toasts.findIndex((t) => t.id === id)
  if (i >= 0) state.toasts.splice(i, 1)
}

function push(message, type = 'info', duration = 2600) {
  const id = ++state.seq
  state.toasts.push({ id, type, message })
  if (state.toasts.length > 4) state.toasts.shift()  // 有界：最多叠 4 条
  setTimeout(() => dismiss(id), duration)
  return id
}

export const toast = {
  state,
  push,
  dismiss,
  info: (m, d) => push(m, 'info', d),
  success: (m, d) => push(m, 'success', d),
  error: (m, d) => push(m, 'error', d),
}

export function useToast() {
  return toast
}
