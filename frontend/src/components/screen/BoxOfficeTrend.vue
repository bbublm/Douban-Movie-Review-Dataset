<!--
  票房分析展厅 · 右翼面板：年度票房趋势
  ============================================================
  ECharts 柱状图：每年上映影片的票房合计。
  走 useChart 底座（computed option + watch 补绘 —— 异步接口数据的既定约定）。
  峰值年份用强调色标出。x 轴年份自动抽稀（40+ 个标签全显会挤成一团）。
-->
<template>
  <div class="botrend">
    <div class="botrend__head">
      <span class="botrend__head-zh">年度票房</span>
      <span class="botrend__head-en">上映年合计 · 亿美元</span>
    </div>
    <div ref="el" class="botrend__chart" />
    <p v-if="peak" class="botrend__peak">
      峰值 <b>{{ peak.year }}</b> 年 · <b>{{ yi(peak.revenue) }}</b> 亿美元
    </p>
  </div>
</template>

<script setup>
// ============================================================
// 年度票房趋势：ES 聚合（by_year 桶）→ 柱状图
// option 写 computed + watch 是既定约定（接口异步，挂载时数据常未到）
// ============================================================
import { computed, watch } from 'vue'
import { useChart, U } from './useChart.js'

const props = defineProps({
  years: { type: Array, default: () => [] },
  totalRevenue: { type: Number, default: 0 },
  totalMovies: { type: Number, default: 0 },
})

/* 美元 → 亿美元（个位数保留一位小数） */
function yi(usd) {
  const v = (usd || 0) / 1e8
  return v >= 10 ? Math.round(v) : Math.round(v * 10) / 10
}

const rows = computed(() =>
  (props.years || [])
    .filter((y) => y && y.year && y.revenue > 0)
    .sort((a, b) => a.year - b.year)
    .map((y) => ({ ...y, yi: (y.revenue / 1e8) }))
)

const peak = computed(() =>
  rows.value.length ? rows.value.reduce((a, b) => (b.yi > a.yi ? b : a)) : null
)

const option = computed(() => ({
  grid: { left: 44, right: 12, top: 18, bottom: 26 },
  tooltip: {
    trigger: 'axis',
    backgroundColor: 'rgba(255,253,247,0.96)',
    borderColor: 'rgba(139,107,71,0.4)',
    textStyle: { color: U.text, fontSize: 11 },
    formatter: (ps) => {
      const p = ps[0]
      const y = rows.value[p.dataIndex]
      if (!y) return ''
      return `${y.year} 年<br/>票房 <b>${yi(y.revenue)}</b> 亿美元 · ${y.movies} 部`
    },
  },
  xAxis: {
    type: 'category',
    data: rows.value.map((y) => y.year),
    axisLine: { lineStyle: { color: U.grid } },
    axisTick: { show: false },
    // 抽稀由 echarts autoSkip 决定（不写 interval: 0）：40+ 个年份标签在 340px
    // 面板里全显必然重叠成糊，rotate 也随标签密度收斂到 30°
    axisLabel: { color: U.text2, fontSize: 9.5, rotate: rows.value.length > 12 ? 30 : 0 },
  },
  yAxis: {
    type: 'value',
    name: '亿美元',
    nameTextStyle: { color: U.text2, fontSize: 10 },
    splitLine: { lineStyle: { color: U.grid, type: 'dashed' } },
    axisLabel: { color: U.text2, fontSize: 9.5 },
  },
  series: [{
    type: 'bar',
    data: rows.value.map((y) => ({
      value: Math.round(y.yi * 10) / 10,
      itemStyle: {
        color: peak.value && y.year === peak.value.year ? U.orange : U.gold,
        borderRadius: [3, 3, 0, 0],
      },
    })),
    barMaxWidth: 16,
    animationDuration: 900,
    animationDelay: (idx) => idx * 28,
  }],
}))

const { el, set } = useChart(() => option.value)
watch(option, (o) => set(o), { deep: true })
</script>

<style scoped>
.botrend { display: flex; flex-direction: column; height: 100%; min-height: 0; }
.botrend__head { display: flex; align-items: baseline; gap: 8px; padding-bottom: 8px; }
.botrend__head-zh { font-size: 13px; font-weight: 800; color: var(--u-text, #3A2E20); letter-spacing: 0.04em; }
.botrend__head-en { font-size: 10px; color: var(--u-text-2, #7D6B52); letter-spacing: 0.06em; }
.botrend__chart { flex: 1; min-height: 120px; }
.botrend__peak { margin: 6px 0 0; font-size: 11.5px; color: var(--u-text, #3A2E20); padding-bottom: 4px; }
.botrend__peak b { color: #C2410C; font-size: 13px; }
</style>
