import { onBeforeUnmount, onMounted } from 'vue'

/**
 * 滚动揭示（scroll-reveal）：给展厅里「首屏以下」的板块加进入视口时的
 * 错峰淡入上移动画，让可纵向滚动的长数据页有逐层展开的高级感。
 *
 * 2026-11-06：叠加 progressive blur（itomdev 招牌「从模糊到清晰」）。
 * 揭示动画结束后加 is-settled，把 CSS filter 归零 —— 否则 filter:blur(0)
 * 会长期制造 containing block，影响卡片内部 absolute 定位的浮层/图表。
 *
 * 用法：在展厅根节点挂 ref="root"，给目标板块 class="u-reveal"（可配 style="--d:.1s" 错峰），
 *       然后 useReveal(root)。样式在 styles/universe.css 的 .u-reveal。
 *
 * 安全红线：
 *   · 不支持 IntersectionObserver 时立即全部显示 —— 绝不把内容藏没；
 *   · 一旦揭示就 unobserve（is-in 常驻），回滚不会反复触发；
 *   · 只挂「非 float-card 的容器」，避免和卡片自身的进场动画抢 transform/opacity。
 */
export function useReveal(rootRef) {
  let observer = null
  const timers = new Set()

  const revealNow = (el) => {
    el.classList.add('is-in')
    // 与 CSS transition 时长（.72s + 错峰 delay）对齐后清掉 filter
    const delay = parseFloat(getComputedStyle(el).getPropertyValue('--d')) || 0
    const t = setTimeout(() => {
      el.classList.add('is-settled')
      timers.delete(t)
    }, (delay + 0.78) * 1000)
    timers.add(t)
  }

  const revealAll = (root) =>
    root.querySelectorAll('.u-reveal').forEach(revealNow)

  onMounted(() => {
    const root = rootRef && rootRef.value
    if (!root) return
    if (!('IntersectionObserver' in window)) { revealAll(root); return }

    const observeAll = () => {
      const targets = [...root.querySelectorAll('.u-reveal:not(.is-in)')]
      targets.forEach((el) => observer.observe(el))
    }

    observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            revealNow(entry.target)
            observer.unobserve(entry.target)
          }
        }
      },
      // 提前一点触发，滚到位时动画已基本播完，不会出现「先空白再跳出」
      { threshold: 0.1, rootMargin: '0px 0px -6% 0px' }
    )
    observeAll()
    // 异步数据让 DOM 后到（如票房 extras）：补扫一次，避免漏掉的板块永远隐藏
    const t = setTimeout(() => { if (observer) observeAll(); timers.delete(t) }, 1200)
    timers.add(t)
  })

  onBeforeUnmount(() => {
    observer && observer.disconnect()
    timers.forEach(clearTimeout)
    timers.clear()
  })
}
