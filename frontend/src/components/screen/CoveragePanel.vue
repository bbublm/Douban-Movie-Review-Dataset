<template>
  <div class="cvp">
    <!-- 预告覆盖率（按年代） -->
    <div class="cvp__sec">
      <div class="cvp__h">
        <i class="cvp__bar" />预告覆盖率 · 按年代
        <span class="cvp__note">{{ cov?.coverage_pct ?? '—' }}%</span>
      </div>
      <v-chart class="cvp__chart" :option="covOption" autoresize />
    </div>

    <!-- 类型 × 情感 -->
    <div class="cvp__sec">
      <div class="cvp__h"><i class="cvp__bar" />类型 × 情感</div>
      <v-chart class="cvp__chart cvp__chart--tall" :option="genreOption" autoresize />
    </div>
  </div>
</template>

<script setup>
// ============================================================
// 右翼面板 · 预告覆盖（按年代覆盖率 + 类型×情感）
// ------------------------------------------------------------
// 数据：/douban/insights 的 trailer_coverage.by_decade / genre_sentiment（真实）
// ============================================================
import { computed } from 'vue'
import VChart, { CHART_COLORS, FONT } from '../insights/echarts.js'
import { U } from './useChart.js'

const props = defineProps({
  douban: { type: Object, default: null },
})

const cov = computed(() => props.douban?.trailer_coverage || null)

const covOption = computed(() => {
  const byDecade = cov.value?.by_decade || []
  return {
    backgroundColor: 'transparent',
    grid: { left: 8, right: 16, top: 18, bottom: 22, containLabel: true },
    tooltip: {
      trigger: 'axis', formatter: (ps) => {
        const i = ps[0].dataIndex
        const d = byDecade[i]
        const pct = d.total ? Math.round(100 * d.with_trailers / d.total) : 0
        return `${d.decade}<br/>含预告片 ${d.with_trailers} / ${d.total} 部（${pct}%）`
      }, textStyle: { fontFamily: FONT },
    },
    xAxis: {
      type: 'category', data: byDecade.map((d) => d.decade),
      axisLine: { lineStyle: { color: 'rgba(154,96,40,.4)' } }, axisTick: { show: false },
      axisLabel: { color: U.text2, fontFamily: FONT, fontSize: 10, interval: 0, rotate: byDecade.length > 6 ? 24 : 0 },
    },
    yAxis: {
      type: 'value', name: '部', nameTextStyle: { color: U.text2, fontFamily: FONT, fontSize: 10 },
      splitLine: { lineStyle: { color: U.grid } }, axisLabel: { color: U.text2, fontFamily: FONT, fontSize: 10 },
    },
    series: [{
      type: 'bar', data: byDecade.map((d) => d.with_trailers),
      barWidth: '52%', itemStyle: { color: U.gold, borderRadius: [5, 5, 0, 0] },
      animationDuration: 800, animationEasing: 'cubicOut',
    }],
  }
})

const genreOption = computed(() => {
  const list = props.douban?.genre_sentiment || []
  const cats = list.map((g) => g.genre)
  const mk = (key, color, name) => ({
    name, type: 'bar', stack: 's', data: list.map((g) => g[key]),
    itemStyle: { color, borderRadius: 0 }, emphasis: { focus: 'series' },
  })
  return {
    backgroundColor: 'transparent',
    grid: { left: 8, right: 12, top: 30, bottom: 20, containLabel: true },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' }, textStyle: { fontFamily: FONT } },
    legend: { top: 0, textStyle: { color: U.text2, fontFamily: FONT, fontSize: 10 }, itemWidth: 10, itemHeight: 10 },
    xAxis: {
      type: 'category', data: cats,
      axisLine: { lineStyle: { color: 'rgba(154,96,40,.4)' } }, axisTick: { show: false },
      axisLabel: { color: U.text, fontFamily: FONT, fontSize: 10, interval: 0, rotate: cats.length > 5 ? 22 : 0 },
    },
    yAxis: { type: 'value', splitLine: { lineStyle: { color: U.grid } }, axisLabel: { color: U.text2, fontFamily: FONT, fontSize: 10 } },
    series: [
      mk('positive', CHART_COLORS.positive, '正面'),
      mk('neutral', CHART_COLORS.neutral, '中性'),
      mk('negative', CHART_COLORS.negative, '负面'),
    ],
    animationDuration: 800, animationEasing: 'cubicOut',
  }
})
</script>

<style scoped>
.cvp { display: flex; flex-direction: column; gap: 8px; height: 100%; }
.cvp__sec { display: flex; flex-direction: column; min-height: 0; }
.cvp__sec:first-child { flex: 0 0 auto; }
.cvp__sec:last-child { flex: 1; min-height: 0; }
.cvp__h {
  display: flex; align-items: center; gap: 7px;
  font-size: 12.5px; font-weight: 700; color: var(--u-text); margin-bottom: 2px;
}
.cvp__bar { width: 4px; height: 14px; border-radius: 2px; background: var(--u-gold); }
.cvp__note { margin-left: auto; color: var(--u-gold); font-weight: 700; font-size: 12px; }
.cvp__chart { height: 108px; }
.cvp__chart--tall { height: 100%; min-height: 92px; }
</style>
