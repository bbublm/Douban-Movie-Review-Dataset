/* ============================================================
   大屏图表共用底座 —— HUD 风格（2026-10-19 起为暖白纸浅色版）
   ------------------------------------------------------------
   为什么不直接用 vue-echarts 组件？
       大屏图表有两种活法：
         · 静态 option（vue-echarts 的 :option 绑定足够）
         · 逐帧推 option（条形竞赛每 1.4s 重排一次，需要拿 chart 实例手动 setOption）
       第二种用 vue-echarts 要绕 ref，反而不如直接 init 来得直白。
       两种都走 echarts/core 的按需注册（insights/echarts.js 已 import 过本模块，
       注册表是全局的，这里只管 init/resize/dispose 三件事。

   注意：本文件只管实例生命周期，option 由各组件自己构造（每家图表差别太大，
   硬抽公共 option 只会造出一个没人用的抽象层）。
   ============================================================ */
import { onBeforeUnmount, onMounted, ref } from 'vue'
import { init } from 'echarts/core'
// ★ 关键副作用：echarts 按需注册表是模块级全局 —— CanvasRenderer 与
// BarChart/LineChart/SankeyChart/wordCloud 的注册发生在 insights/echarts.js 的
// use([...]) 里。本文件若只 import 'echarts/core' 就拿裸 init，
// 控制台会报 "Renderer 'undefined' is not imported"（渲染器从未注册）。
// 这里显式引入该模块，保证注册先于任何 init() 执行。
import '../insights/echarts.js'

/**
 * @param {() => object} getOption  构造 option 的函数（各组件传 () => option.value）
 * @param {{ onUpdate?: (chart) => void }} [opts] 实例就绪回调
 * @returns {{ el: Ref, chart: () => object|null, set: (option: object) => void }}
 *
 * ★ 为什么必须配 watch(option) 用：大屏数据全是异步接口（matrix/lexicon/sentiment），
 *   组件挂载时 props 往往还是 null。若只在 onMounted 建一次 option，
 *   数据到了图表就是空白（Stage 3 实测踩过：竞赛图 canvas 全黑 lit=0）。
 *   所以约定：option 一律写成 computed，再 watch(option, set) 补第二次绘制。
 */
export function useChart(getOption, opts = {}) {
  const el = ref(null)
  let chart = null
  let ro = null

  onMounted(() => {
    if (!el.value) return
    chart = init(el.value, null, { renderer: 'canvas' })
    chart.setOption(getOption())
    // 大屏可能被拖拽改变视口（或窗口缩放），图表跟着容器走
    if (typeof ResizeObserver !== 'undefined') {
      ro = new ResizeObserver(() => chart?.resize())
      ro.observe(el.value)
    }
    opts.onUpdate?.(chart)
  })

  onBeforeUnmount(() => {
    ro?.disconnect()
    ro = null
    chart?.dispose()
    chart = null
  })

  return { el, chart: () => chart, set: (o) => chart?.setOption(o) }
}

/* 大屏图表通用字/色（与 universe.css 令牌同源，ECharts 不吃 CSS 变量）。
   2026-10-19 浅色版：随整体暖白纸化，文字深咖、强调色加深一档 */
export const U = {
  gold: '#A67C2E',
  goldSoft: 'rgba(166, 124, 46, 0.55)',
  orange: '#C2410C',
  orangeSoft: 'rgba(194, 65, 12, 0.5)',
  cyan: '#0F766E',
  blue: '#4A7FB5',
  blueSoft: 'rgba(74, 127, 181, 0.5)',
  sky: '#0369A1',
  violet: '#6D28D9',
  text: '#3A2E20',
  text2: '#7D6B52',
  grid: 'rgba(154, 96, 40, 0.16)',
  tech: '"Orbitron", "Bahnschrift", sans-serif',
  cn: '"PingFang SC", "Microsoft YaHei", sans-serif',
}
