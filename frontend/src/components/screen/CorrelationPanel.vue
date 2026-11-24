<template>
  <!-- 相关矩阵热力 + 预算×票房散点回归：r / R² 都由后端现算 -->
  <AnalysisCard
    kicker="CORRELATION / REGRESSION"
    title="钱和口碑，到底有没有关系"
    :note="note"
    :tabs="TABS"
    v-slot="{ tab }"
  >
    <div class="cp__chart">
      <v-chart v-if="tab === 'matrix'" :option="heatOption" autoresize />
      <v-chart v-else :option="scatterOption" autoresize />
    </div>
  </AnalysisCard>
</template>

<script setup>
import { computed } from 'vue'
import VChart, { FONT } from '../insights/echarts.js'
import AnalysisCard from './AnalysisCard.vue'

const props = defineProps({ correlations: { type: Object, default: null } })
const TABS = [
  { key: 'matrix', label: '相关矩阵' },
  { key: 'scatter', label: '散点回归' },
]
const note = computed(() => (props.correlations?.notes || []).slice(0, 2).join(' · ') || '暂无统计样本')

const heatOption = computed(() => {
  const c = props.correlations
  const labels = c?.labels || []
  const data = []
  ;(c?.matrix || []).forEach((row, i) => row.forEach((v, j) => {
    data.push([j, i, v == null ? '-' : v])
  }))
  const axis = {
    type: 'category',
    data: labels,
    axisLabel: { color: '#6F5C44', fontSize: 10, fontFamily: FONT },
    axisLine: { lineStyle: { color: '#C9B08A' } },
    axisTick: { show: false },
    splitArea: { show: true, areaStyle: { color: ['rgba(255,255,255,.3)', 'transparent'] } },
  }
  return {
    backgroundColor: 'transparent',
    grid: { left: 62, right: 16, top: 28, bottom: 32 },
    xAxis: axis,
    yAxis: { ...axis, splitArea: { show: false } },
    visualMap: {
      min: -1, max: 1, calculable: true, orient: 'horizontal',
      // 色标单独占顶部一条，别压在 x 轴标签上（实拍发现过重叠）
      left: 'center', top: 0, itemWidth: 10, itemHeight: 96,
      textStyle: { color: '#6F5C44', fontSize: 9 },
      inRange: { color: ['#0F766E', '#FBF7EE', '#C2410C'] },
    },
    tooltip: {
      backgroundColor: '#FFFCF4', borderColor: '#8B7355', borderWidth: 1,
      textStyle: { color: '#3A2E20', fontSize: 11 },
      formatter: (p) => `${labels[p.value[1]]} × ${labels[p.value[0]]}<br/>Pearson r = <b>${Number(p.value[2]).toFixed(2)}</b>`,
    },
    series: [{
      type: 'heatmap', data,
      label: {
        show: true, color: '#3A2E20', fontSize: 11, fontFamily: FONT,
        formatter: (p) => (p.value[2] === '-' ? '—' : Number(p.value[2]).toFixed(2)),
      },
      itemStyle: { borderColor: '#FFFCF4', borderWidth: 2 },
      emphasis: { itemStyle: { shadowBlur: 9, shadowColor: 'rgba(74,44,20,.4)' } },
    }],
  }
})

const scatterOption = computed(() => {
  const c = props.correlations
  const pts = (c?.scatter || []).map((p) => [p.x / 1e8, p.y / 1e8, p.rating, p.title])
  const reg = c?.regression
  let line = null
  if (reg && pts.length) {
    const xs = pts.map((p) => p[0])
    const lo = Math.min(...xs), hi = Math.max(...xs)
    // 回归式是「美元」口径；坐标轴换算成亿美元：y = slope·x + intercept/1e8
    line = [[lo, reg.slope * lo + reg.intercept / 1e8],
      [hi, reg.slope * hi + reg.intercept / 1e8]]
  }
  return {
    backgroundColor: 'transparent',
    grid: { left: 52, right: 18, top: 16, bottom: 40 },
    xAxis: {
      type: 'value', name: '预算 / 亿美元', nameTextStyle: { color: '#7D6B52', fontSize: 9 },
      axisLabel: { color: '#7D6B52', fontSize: 9 },
      splitLine: { lineStyle: { color: 'rgba(154,96,40,.14)' } },
    },
    yAxis: {
      type: 'value', name: '票房 / 亿美元', nameTextStyle: { color: '#7D6B52', fontSize: 9 },
      axisLabel: { color: '#7D6B52', fontSize: 9 },
      splitLine: { lineStyle: { color: 'rgba(154,96,40,.14)' } },
    },
    tooltip: {
      backgroundColor: '#FFFCF4', borderColor: '#8B7355', borderWidth: 1,
      textStyle: { color: '#3A2E20', fontSize: 11 },
      formatter: (p) => (p.seriesType === 'line'
        ? '最小二乘回归线'
        : `<b>${p.data[3] || '—'}</b><br/>预算 ${p.data[0].toFixed(2)} 亿 · 票房 ${p.data[1].toFixed(2)} 亿`
          + (p.data[2] != null ? `<br/>评分 ${p.data[2]}` : '')),
    },
    series: [
      {
        type: 'scatter', data: pts,
        symbolSize: (d) => 7 + Math.min(9, (Number(d[2]) || 7) * 0.55),
        itemStyle: { color: '#A0522D', opacity: 0.74, borderColor: '#FFF6E9', borderWidth: 1 },
        emphasis: { itemStyle: { color: '#C2410C', opacity: 1 } },
      },
      ...(line ? [{
        type: 'line', data: line, showSymbol: false, silent: true,
        lineStyle: { color: '#C2410C', width: 2, type: 'dashed' },
      }] : []),
    ],
  }
})
</script>

<style scoped>
.cp__chart { width: 100%; height: 100%; min-height: 0; }
</style>
