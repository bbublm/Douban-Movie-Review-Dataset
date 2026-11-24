<template>
  <!-- 类型多维画像雷达：5 个维度全部来自 /insights/correlations 的现算画像 -->
  <AnalysisCard kicker="GENRE PROFILE / RADAR" title="一个类型的性格，不止看评分" :note="note">
    <div class="gr__chart"><v-chart :option="option" autoresize /></div>
  </AnalysisCard>
</template>

<script setup>
import { computed } from 'vue'
import VChart, { FONT } from '../insights/echarts.js'
import AnalysisCard from './AnalysisCard.vue'

const props = defineProps({ correlations: { type: Object, default: null } })

const DIMS = [
  { key: 'movies', label: '产量' },
  { key: 'avg_rating', label: '均分' },
  { key: 'hit_rate', label: '8 分率' },
  { key: 'median_roi', label: 'ROI' },
  { key: 'avg_runtime', label: '片长' },
]
const PALETTE = ['#C2410C', '#A67C2E', '#0F766E', '#4A7FB5', '#6D28D9', '#8B4513']
const profiles = computed(() => (props.correlations?.profiles || []).slice(0, 6))
const maxes = computed(() => {
  const m = {}
  for (const d of DIMS) {
    m[d.key] = Math.max(0.0001, ...profiles.value.map((p) => Number(p[d.key]) || 0))
  }
  return m
})
const norm = (p, key) => Math.round(((Number(p[key]) || 0) / maxes.value[key]) * 100)
const note = computed(() => {
  const ps = profiles.value
  if (!ps.length) return '暂无画像样本'
  const scored = ps.map((p) => ({
    g: p.genre,
    s: DIMS.reduce((a, d) => a + norm(p, d.key), 0) / DIMS.length,
  })).sort((a, b) => b.s - a.s)
  return `五维归一化后综合画像最突出：${scored[0].g}（均值 ${scored[0].s.toFixed(0)}）· ${props.correlations?.sample_size || 0} 部影片现算`
})

const option = computed(() => ({
  backgroundColor: 'transparent',
  textStyle: { fontFamily: FONT },
  tooltip: {
    backgroundColor: '#FFFCF4', borderColor: '#8B7355', borderWidth: 1,
    textStyle: { color: '#3A2E20', fontSize: 11 },
  },
  legend: {
    bottom: 0, data: profiles.value.map((p) => p.genre),
    textStyle: { color: '#6F5C44', fontSize: 9 }, itemWidth: 10, itemHeight: 8,
  },
  radar: {
    indicator: DIMS.map((d) => ({ name: d.label, max: 100 })),
    radius: '60%', center: ['50%', '48%'],
    axisName: { color: '#6F5C44', fontSize: 10 },
    splitLine: { lineStyle: { color: 'rgba(154,96,40,.22)' } },
    splitArea: { areaStyle: { color: ['rgba(255,255,255,.38)', 'rgba(166,124,46,.05)'] } },
    axisLine: { lineStyle: { color: 'rgba(154,96,40,.3)' } },
  },
  series: [{
    type: 'radar',
    data: profiles.value.map((p, i) => ({
      name: p.genre,
      value: DIMS.map((d) => norm(p, d.key)),
      lineStyle: { width: 2, color: PALETTE[i % PALETTE.length] },
      itemStyle: { color: PALETTE[i % PALETTE.length] },
      areaStyle: { color: PALETTE[i % PALETTE.length], opacity: 0.07 },
    })),
  }],
}))
</script>

<style scoped>
.gr__chart { width: 100%; height: 100%; min-height: 0; }
</style>
