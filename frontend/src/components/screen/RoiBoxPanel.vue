<template>
  <!-- 各类型投资回报的四分位箱线：q1/median/q3 由后端 quantiles() 现算 -->
  <AnalysisCard kicker="ROI DISTRIBUTION / BOXPLOT" title="同一类型里，回报差得有多远" :note="note">
    <div class="rb__chart"><v-chart :option="option" autoresize /></div>
  </AnalysisCard>
</template>

<script setup>
import { computed } from 'vue'
import VChart, { FONT } from '../insights/echarts.js'
import AnalysisCard from './AnalysisCard.vue'

const props = defineProps({ correlations: { type: Object, default: null } })
const boxes = computed(() => (props.correlations?.roi_by_genre || []).slice(0, 9))
const note = computed(() => {
  const bs = boxes.value
  if (!bs.length) return '暂无足够的预算/票房配对样本'
  const widest = [...bs].sort((a, b) => b.iqr - a.iqr)[0]
  return `箱体最宽（内部分歧最大）：${widest.genre}，IQR ${widest.iqr.toFixed(2)}× · 中位数最高 ${bs[0].genre} ${bs[0].median.toFixed(2)}×`
})

const option = computed(() => ({
  backgroundColor: 'transparent',
  textStyle: { fontFamily: FONT },
  grid: { left: 44, right: 14, top: 14, bottom: 34 },
  xAxis: {
    type: 'category', data: boxes.value.map((b) => b.genre),
    axisLabel: { color: '#6F5C44', fontSize: 9, interval: 0, rotate: 24 },
    axisLine: { lineStyle: { color: '#C9B08A' } }, axisTick: { show: false },
  },
  yAxis: {
    type: 'value', name: 'ROI / 倍', nameTextStyle: { color: '#7D6B52', fontSize: 9 },
    axisLabel: { color: '#7D6B52', fontSize: 9 },
    splitLine: { lineStyle: { color: 'rgba(154,96,40,.14)' } },
  },
  tooltip: {
    backgroundColor: '#FFFCF4', borderColor: '#8B7355', borderWidth: 1,
    textStyle: { color: '#3A2E20', fontSize: 11 },
    formatter: (p) => {
      if (p.seriesType === 'line') return `中位数 <b>${Number(p.value).toFixed(2)}×</b>`
      const v = Array.isArray(p.value) ? p.value : []
      return `<b>${p.name}</b><br/>下须 ${Number(v[0]).toFixed(2)} · Q1 ${Number(v[1]).toFixed(2)}`
        + `<br/>中位 <b>${Number(v[2]).toFixed(2)}</b> · Q3 ${Number(v[3]).toFixed(2)} · 上须 ${Number(v[4]).toFixed(2)}`
    },
  },
  series: [
    {
      type: 'boxplot',
      data: boxes.value.map((b) => [b.min, b.q1, b.median, b.q3, b.max]),
      itemStyle: { color: 'rgba(194,65,12,.16)', borderColor: '#8B4513', borderWidth: 1.6 },
      emphasis: { itemStyle: { borderColor: '#C2410C', borderWidth: 2.4 } },
    },
    {
      type: 'line',
      data: boxes.value.map((b) => b.median),
      symbol: 'circle', symbolSize: 6,
      lineStyle: { color: '#0F766E', width: 1.6, type: 'dashed' },
      itemStyle: { color: '#0F766E' },
      z: 3,
    },
  ],
}))
</script>

<style scoped>
.rb__chart { width: 100%; height: 100%; min-height: 0; }
</style>
