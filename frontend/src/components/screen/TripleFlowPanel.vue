<template>
  <!-- 三层桑基 + 类型×年代口碑热力：第三级由 ES range 聚合切出，不是平均值贴图 -->
  <AnalysisCard
    kicker="THREE-LAYER SANKEY / HEATMAP"
    title="类型 → 年代 → 口碑档"
    :note="note"
    :tabs="TABS"
    v-slot="{ tab }"
  >
    <div class="tf__chart">
      <v-chart v-if="tab === 'sankey'" :option="sankeyOption" autoresize />
      <v-chart v-else :option="heatOption" autoresize />
    </div>
  </AnalysisCard>
</template>

<script setup>
import { computed } from 'vue'
import VChart, { FONT } from '../insights/echarts.js'
import AnalysisCard from './AnalysisCard.vue'

const props = defineProps({ flows: { type: Object, default: null } })
const TABS = [
  { key: 'sankey', label: '三层流向' },
  { key: 'heat', label: '年代热力' },
]
const NODE_COLOR = { genre: '#C2410C', decade: '#A67C2E', tier: '#0F766E' }
const note = computed(() => (props.flows?.notes || []).join(' · ') || '暂无流向数据')

const sankeyOption = computed(() => {
  const f = props.flows
  return {
    backgroundColor: 'transparent',
    textStyle: { fontFamily: FONT },
    tooltip: {
      backgroundColor: '#FFFCF4', borderColor: '#8B7355', borderWidth: 1,
      textStyle: { color: '#3A2E20', fontSize: 11 },
      formatter: (p) => (p.dataType === 'edge'
        ? `${p.data.source} → ${p.data.target}<br/><b>${p.data.value}</b> 部`
        : `<b>${String(p.name).split('·').pop()}</b>`),
    },
    series: [{
      type: 'sankey',
      data: (f?.nodes || []).map((n) => ({
        name: n.name, itemStyle: { color: NODE_COLOR[n.kind] || '#8B7355', borderColor: '#FFF6E9' },
      })),
      links: (f?.links || []).map((l) => ({ source: l.source, target: l.target, value: l.value })),
      emphasis: { focus: 'adjacency' },
      label: {
        color: '#3A2E20', fontSize: 10, fontWeight: 600,
        position: 'right', distance: 4,
        formatter: (p) => String(p.name).split('·').pop(),
      },
      lineStyle: { color: 'gradient', opacity: 0.34, curveness: 0.45 },
      nodeWidth: 13, nodeGap: 11, layoutIterations: 32,
      left: 54, right: 54, top: 10, bottom: 8,
    }],
  }
})

const heatOption = computed(() => {
  const f = props.flows
  const decades = f?.decades || []
  const genres = f?.genres || []
  const data = (f?.heat || []).map((h) => [
    decades.indexOf(h.decade), genres.indexOf(h.genre),
    h.avg_rating == null ? '-' : h.avg_rating, h.movies,
  ]).filter((d) => d[0] >= 0 && d[1] >= 0)
  const axis = {
    type: 'category',
    axisLabel: { color: '#6F5C44', fontSize: 9, fontFamily: FONT },
    axisLine: { lineStyle: { color: '#C9B08A' } },
    axisTick: { show: false },
  }
  return {
    backgroundColor: 'transparent',
    grid: { left: 56, right: 14, top: 8, bottom: 48 },
    xAxis: { ...axis, data: decades.map((d) => `${d}s`) },
    yAxis: { ...axis, data: genres },
    visualMap: {
      min: 5, max: 9, calculable: true, orient: 'horizontal',
      left: 'center', bottom: 0, itemWidth: 10, itemHeight: 110,
      textStyle: { color: '#6F5C44', fontSize: 9 },
      inRange: { color: ['#EFE2C8', '#D9A15B', '#C2410C'] },
    },
    tooltip: {
      backgroundColor: '#FFFCF4', borderColor: '#8B7355', borderWidth: 1,
      textStyle: { color: '#3A2E20', fontSize: 11 },
      formatter: (p) => `${genres[p.value[1]]} · ${decades[p.value[0]]}s<br/>`
        + `${p.value[3]} 部 · 均分 <b>${p.value[2] === '-' ? '—' : p.value[2]}</b>`,
    },
    series: [{
      type: 'heatmap', data,
      label: { show: false },
      itemStyle: { borderColor: '#FFFCF4', borderWidth: 2 },
      emphasis: { itemStyle: { shadowBlur: 9, shadowColor: 'rgba(74,44,20,.4)' } },
    }],
  }
})
</script>

<style scoped>
.tf__chart { width: 100%; height: 100%; min-height: 0; }
</style>
