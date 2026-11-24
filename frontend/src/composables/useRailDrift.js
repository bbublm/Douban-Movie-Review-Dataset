/* ============================================================
   横向轨道交互：滚轮漂移 + 按住拖动（参考 a24.raviklaassens.com 的光盘轨道）
   ------------------------------------------------------------
   为什么不用纯 CSS 滚动条？
     · 参考站里"滚轮 = 画面里的物件横向滑走"，这是它的核心手感；
     · 但我们的数据页本身是纵向长页，若无条件拦截滚轮，用户会被卡住。

   所以这里的规则是「能滚才接管」：
     · 轨道还有余量 → preventDefault，把纵向滚轮换算成横向位移；
     · 滚到头了 → 不拦截，滚轮继续滚页面。
   指针拖动同样处理：位移 > 6px 才算拖动，并吞掉这次点击（避免拖动时误开详情页）。
   ============================================================ */

export function useRailDrift(elRef, opts = {}) {
  const ratio = opts.ratio ?? 1.15

  let dragging = false
  let startX = 0
  let startLeft = 0
  let moved = 0
  let el = null

  function onWheel(e) {
    if (!el) return
    const max = el.scrollWidth - el.clientWidth
    if (max <= 2) return
    const d = Math.abs(e.deltaY) >= Math.abs(e.deltaX) ? e.deltaY : e.deltaX
    if (!d) return
    const canForward = d > 0 && el.scrollLeft < max - 1
    const canBack = d < 0 && el.scrollLeft > 1
    if (!canForward && !canBack) return // 到头了：交还给页面滚动
    e.preventDefault()
    el.scrollLeft += d * ratio
  }

  function onPointerDown(e) {
    if (!el || e.button !== 0) return
    if (el.scrollWidth - el.clientWidth <= 2) return
    dragging = true
    moved = 0
    startX = e.clientX
    startLeft = el.scrollLeft
    el.classList.add('is-dragging')
    // 拖出轨道也要继续跟手：move/up 挂到 window
    window.addEventListener('pointermove', onPointerMove)
    window.addEventListener('pointerup', endDrag)
    window.addEventListener('pointercancel', endDrag)
  }

  function onPointerMove(e) {
    if (!dragging || !el) return
    const dx = e.clientX - startX
    moved = Math.max(moved, Math.abs(dx))
    el.scrollLeft = startLeft - dx
    if (moved > 6) e.preventDefault()
  }

  function endDrag() {
    if (!dragging) return
    dragging = false
    el?.classList.remove('is-dragging')
    window.removeEventListener('pointermove', onPointerMove)
    window.removeEventListener('pointerup', endDrag)
    window.removeEventListener('pointercancel', endDrag)
  }

  /* 拖动结束后浏览器仍会派发一次 click：位移超过 6px 就把它拦掉 */
  function onClickCapture(e) {
    if (moved > 6) {
      e.preventDefault()
      e.stopPropagation()
      moved = 0
    }
  }

  function onDragStart(e) {
    // 轨道里的都是 <a>：不拦掉浏览器的原生链接拖拽，会把 pointer 事件抢走
    e.preventDefault()
  }

  function bind() {
    el = elRef.value
    if (!el) return
    el.addEventListener('wheel', onWheel, { passive: false })
    el.addEventListener('dragstart', onDragStart)
    el.addEventListener('pointerdown', onPointerDown)
    el.addEventListener('click', onClickCapture, true)
  }

  function unbind() {
    if (!el) return
    el.removeEventListener('wheel', onWheel)
    el.removeEventListener('dragstart', onDragStart)
    el.removeEventListener('pointerdown', onPointerDown)
    el.removeEventListener('click', onClickCapture, true)
    endDrag()
    el = null
  }

  return { bind, unbind }
}
