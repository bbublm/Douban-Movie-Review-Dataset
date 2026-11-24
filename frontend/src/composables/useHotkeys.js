// ============================================================
// 全局键盘快捷键（功能清单 P2）：
//   /      聚焦全局搜索框（搜索框已聚焦时不拦截，否则打不了斜杠）
//   Esc    关闭最上层弹窗（盲盒优先；详情弹窗由页面自己监听）
//   ← / →  盲盒打开时换一部
//   Enter  搜索框内提交（各输入框自己处理，这里不重复绑）
//
// 为什么挂 window 而不是每个组件各绑：快捷键是全局行为，
// 散在各组件里会出现「两个弹窗同时开时 Esc 关错一个」。
// 输入态只保留 Esc —— 用户在打字时按 / 就该输入斜杠本身。
// ============================================================
import { onMounted, onUnmounted } from 'vue'
import { blindBox } from './useBlindBox'

function isTyping(target) {
  return (
    target instanceof HTMLElement &&
    (target.tagName === 'INPUT' ||
      target.tagName === 'TEXTAREA' ||
      target.isContentEditable)
  )
}

export function useHotkeys() {
  function onKeyDown(e) {
    // Esc：全局唯一，输入态也生效（用户此时最想关掉打扰）
    if (e.key === 'Escape') {
      if (blindBox.visible.value) blindBox.close()
      return
    }

    if (isTyping(e.target)) return

    // / 聚焦搜索框
    if (e.key === '/') {
      e.preventDefault()
      const input = document.querySelector('.gsearch__input--hotkey')
      if (input) {
        input.focus()
        input.select()
      }
      return
    }

    // 盲盒打开时 ← → 换一部（未打开不拦截，避免和页面滚动打架）
    if (blindBox.visible.value && (e.key === 'ArrowLeft' || e.key === 'ArrowRight')) {
      e.preventDefault()
      blindBox.again()
    }
  }

  onMounted(() => window.addEventListener('keydown', onKeyDown))
  onUnmounted(() => window.removeEventListener('keydown', onKeyDown))
}
