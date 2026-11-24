// ============================================================
// v-sketch —— 手绘「自我完成」揭示指令（itomdev "sketches that finish
// themselves" 招牌效果的中文落地）
// ------------------------------------------------------------
// 用法：
//   <div v-sketch>                      给自身画一道手绘描边
//   <RoomRoot v-sketch="'.float-card'">  给所有 .float-card 后代各画一道
//   v-sketch="{ sel:'.float-card', stagger:.06, maxDelay:.9 }"  带错峰
//
// 效果：元素进入视口时，一条略带抖动的铅笔描边沿轮廓「自己画出来」
//   （stroke-dashoffset 由满到 0），随后定格为淡描边，呼应手绘纸感。
//   可叠加在现有卡片淡入动画之上，不影响点击（pointer-events:none）。
//
// 安全红线：
//   · prefers-reduced-motion 时直接静态显示描边，不做动画；
//   · 异步数据（画廊框 v-for 后到）靠多次延迟重扫兜底；
//   · 卸载时清理 IO 与注入的 SVG，绝不泄漏。
// ============================================================
let styleInjected = false
function injectStyle() {
  if (styleInjected) return
  styleInjected = true
  const css = `
  .sketch-ov {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    pointer-events: none;
    z-index: 7;
    overflow: visible;
  }
  .sketch-ov path {
    fill: none;
    stroke: #6B4E2E;
    stroke-width: 2.6;
    stroke-linecap: round;
    stroke-linejoin: round;
    vector-effect: non-scaling-stroke;
    opacity: 0;
    transition:
      opacity 0.3s ease,
      stroke-dashoffset 1.25s cubic-bezier(0.55, 0.08, 0.25, 1);
  }
  /* 第二条复描线更淡、略细，像铅笔来回描了两遍 */
  .sketch-ov path.sketch-ov__ghost {
    stroke: #A67C2E;
    stroke-width: 1.5;
  }
  .sketch-ov.is-drawn path {
    opacity: 0.72;
    stroke-dashoffset: 0 !important;
  }
  .sketch-ov.is-drawn path.sketch-ov__ghost { opacity: 0.4; }
  @media (prefers-reduced-motion: reduce) {
    .sketch-ov path {
      transition: none !important;
      opacity: 0.5 !important;
      stroke-dashoffset: 0 !important;
    }
    .sketch-ov path.sketch-ov__ghost { opacity: 0.28 !important; }
  }`
  const s = document.createElement('style')
  s.textContent = css
  document.head.appendChild(s)
}

// 手绘矩形轮廓：四条边上各撒若干抖动点，闭合留一点缝隙，像人随手画的框。
// 坐标直接用元素像素尺寸（viewBox = 像素），保证 dash 长度与几何一致。
function roughRect(w, h, jit, per) {
  const m = 4 // 内缩，避免描边被裁
  const pts = []
  const edge = (x1, y1, x2, y2, n) => {
    for (let i = 0; i <= n; i++) {
      const t = i / n
      const jx = (Math.random() * 2 - 1) * jit
      const jy = (Math.random() * 2 - 1) * jit
      pts.push([x1 + (x2 - x1) * t + jx, y1 + (y2 - y1) * t + jy])
    }
  }
  edge(m, m, w - m, m, per)       // 上
  edge(w - m, m, w - m, h - m, per) // 右
  edge(w - m, h - m, m, h - m, per) // 下
  edge(m, h - m, m, m, per)         // 左
  let d = `M${pts[0][0].toFixed(1)} ${pts[0][1].toFixed(1)}`
  for (let i = 1; i < pts.length; i++) d += ` L${pts[i][0].toFixed(1)} ${pts[i][1].toFixed(1)}`
  return d
}

function applySketch(target, delay = 0) {
  if (!target.dataset) return
  if (target.dataset.sketch) return
  const w = target.clientWidth
  const h = target.clientHeight
  if (w < 3 || h < 3) return // 还没布局好，交给后续重扫
  target.dataset.sketch = '1'
  const cs = getComputedStyle(target)
  if (cs.position === 'static') target.style.position = 'relative'
  injectStyle()

  const ns = 'http://www.w3.org/2000/svg'
  const svg = document.createElementNS(ns, 'svg')
  svg.setAttribute('class', 'sketch-ov')
  svg.setAttribute('viewBox', `0 0 ${w} ${h}`)
  svg.setAttribute('preserveAspectRatio', 'none')
  target.appendChild(svg) // 先入 DOM，getTotalLength() 才可靠
  // itomdev 铅笔速写：主描边 + 一条抖动更大的淡色复描线，模拟手画两遍
  const jit = Math.max(1.5, Math.min(w, h) * 0.012)
  const specs = [
    { d: roughRect(w, h, jit, 7), cls: '', extra: 0 },
    { d: roughRect(w, h, jit * 1.7, 6), cls: 'sketch-ov__ghost', extra: 0.16 },
  ]
  for (const sp of specs) {
    const p = document.createElementNS(ns, 'path')
    p.setAttribute('d', sp.d)
    if (sp.cls) p.setAttribute('class', sp.cls)
    svg.appendChild(p)
    const len = p.getTotalLength()
    p.style.strokeDasharray = String(len)
    p.style.strokeDashoffset = String(len)
    const d = delay + sp.extra
    if (d) p.style.transitionDelay = `${d}s`
  }

  const root = target.closest('.dashboard-container') || null
  const io = new IntersectionObserver(
    (entries) => {
      for (const e of entries) {
        if (e.isIntersecting) {
          svg.classList.add('is-drawn')
          io.unobserve(e.target)
          break
        }
      }
    },
    { root, threshold: 0.15, rootMargin: '0px 0px -8% 0px' },
  )
  io.observe(target)
  target.__sketchIo = io
}

function scan(el, selector, stagger, maxDelay) {
  const targets = selector ? el.querySelectorAll(selector) : [el]
  let i = 0
  targets.forEach((t) => {
    const delay = stagger ? Math.min(i * stagger, maxDelay || stagger * 12) : 0
    applySketch(t, delay)
    i++
  })
}

export const sketch = {
  mounted(el, binding) {
    let selector = null
    let stagger = 0
    let maxDelay = 1
    const v = binding.value
    if (typeof v === 'string') selector = v
    else if (v && typeof v === 'object') {
      selector = v.sel || null
      stagger = v.stagger || 0
      maxDelay = v.maxDelay || 1
    }
    // 立即 + 下一帧 + 异步数据兜底（画廊框 v-for 后到）
    scan(el, selector, stagger, maxDelay)
    requestAnimationFrame(() => scan(el, selector, stagger, maxDelay))
    setTimeout(() => scan(el, selector, stagger, maxDelay), 700)
    setTimeout(() => scan(el, selector, stagger, maxDelay), 1700)
  },
  unmounted(el) {
    el.querySelectorAll('.sketch-ov').forEach((o) => {
      const t = o.parentElement
      if (t && t.__sketchIo) t.__sketchIo.disconnect()
      o.remove()
    })
    if (el.__sketchIo) el.__sketchIo.disconnect()
    if (el.classList && el.classList.contains('sketch-ov')) el.remove()
  },
}
