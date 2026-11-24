/* ============================================================
   大屏 ECharts 按需注册中心（原 components/insights/echarts.js）
   ------------------------------------------------------------
   职责：
     1. 副作用：用 echarts/core 的 use() 按需注册「渲染器 + 图表 + 组件
        + 过渡特性」。注册表是模块级全局单例 —— 只要在任意 chart
        init 之前 import 过本模块一次即可，全应用共享。
     2. 默认导出 VChart —— vue-echarts 组件（大屏面板用它画饼/柱/散点，
        模板里直接 <v-chart>）。
     3. 命名导出大屏通用字/色：FONT、CHART_COLORS（情感三色）。
   2026-10-19 浅色版：情感三色随整体暖白纸化加深一档，与 universe.css
   令牌 / 词云 PALETTE 同源（ECharts 不吃 CSS 变量，必须硬编码）。
   ============================================================ */
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'

import {
  BarChart,
  LineChart,
  PieChart,
  ScatterChart,
  SankeyChart,
  // 2026-11-04 深度分析：知识图谱（graph）、相关矩阵/类型热力（heatmap）、
  // 类型画像（radar）、ROI 四分位（boxplot）都用得上。注册表是全局单例，
  // 不注册就写 type:'graph' 会报 "Series graph is not imported"。
  GraphChart,
  HeatmapChart,
  RadarChart,
  BoxplotChart,
} from 'echarts/charts'

import {
  GridComponent,
  TooltipComponent,
  LegendComponent,
  TitleComponent,
  AxisPointerComponent,
  VisualMapComponent,
  ToolboxComponent,
  MarkLineComponent,
  RadarComponent,
  DatasetComponent,
  DataZoomComponent,
} from 'echarts/components'

import { LabelLayout, UniversalTransition } from 'echarts/features'

// 词云（独立插件，注册为图表类型 'wordCloud'）。
// 作为副作用 import：把 wordCloud 系列挂到全局 echarts 注册表。
import 'echarts-wordcloud'

// vue-echarts 组件（内部复用同一个 echarts/core 全局注册表）
import VChart from 'vue-echarts'

/* ★ 一次性按需注册（全应用全局生效，顺序无关） */
use([
  CanvasRenderer,
  BarChart,
  LineChart,
  PieChart,
  ScatterChart,
  SankeyChart,
  GraphChart,
  HeatmapChart,
  RadarChart,
  BoxplotChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  TitleComponent,
  AxisPointerComponent,
  VisualMapComponent,
  ToolboxComponent,
  MarkLineComponent,
  RadarComponent,
  DatasetComponent,
  DataZoomComponent,
  LabelLayout,
  UniversalTransition,
])

/* 大屏通用字体（ECharts 不吃 CSS 变量，必须硬编码成字符串） */
export const FONT = '"PingFang SC", "Microsoft YaHei", "Bahnschrift", sans-serif'

/* 情感三色（与 universe.css 令牌 / 词云 PALETTE 同源；浅色版加深一档） */
export const CHART_COLORS = {
  positive: '#C2410C', // 正面 · 暖橙
  neutral: '#A67C2E', //  中性 · 金
  negative: '#0F766E', // 负面 · 青
}

export default VChart
