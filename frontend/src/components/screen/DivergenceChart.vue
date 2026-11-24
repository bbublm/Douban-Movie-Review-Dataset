<template>
  <div class="dv">
    <div class="dv__head">
      <div class="dv__head-l">
        <i class="dv__head-bar" />
        <span class="dv__head-zh">口碑分歧 · 豆瓣 vs TMDB</span>
        <span class="dv__head-en">双平台都有评分的影片</span>
      </div>
      <span class="dv__note">{{ pts.length }} 部</span>
    </div>
    <v-chart class="dv__chart" :option="option" autoresize />
    <p class="dv__foot">
      橙 = 豆瓣更高，青 = TMDB 更高，金 = 基本一致；点越大分歧越悬殊。
      明显偏离对角线的，多为「主旋律 / 国产大片」或「小众艺术片」。
    </p>
  </div>
</template>

<script setup>
// ============================================================
// 中央舞台 · 口碑分歧散点（豆瓣 × TMDB 评分对照）
// ------------------------------------------------------------
// 数据：/douban/insights 的 rating_divergence（真实：库内 173 部双平台有评分）
// 浅色 HUD 调色：橙=豆瓣更高 / 青=TMDB更高 / 金=一致
// ============================================================
import { computed } from 'vue'
import VChart, { FONT } from '../insights/echarts.js'
import { U } from './useChart.js'

const props = defineProps({
  divergence: { type: Array, default: () => [] },
})

const pts = computed(() => (props.divergence || []).map((p) => ({
  name: p.title,
  value: [p.tmdb_rating, p.douban_rating],
  gap: p.gap,
  year: p.year,
})))

const option = computed(() => ({
  backgroundColor: 'transparent',
  grid: { left: 54, right: 22, top: 26, bottom: 46 },
  tooltip: {
    trigger: 'item',
    backgroundColor: 'rgba(58,46,32,.92)',
    borderWidth: 0,
    textStyle: { color: '#fff', fontFamily: FONT },
    formatter: (p) => {
      const d = p.data
      return `<b>${d.name}</b>${d.year ? '（' + d.year + '）' : ''}<br/>`
        + `TMDB ${d.value[0]} · 豆瓣 ${d.value[1]}<br/>`
        + `差值 ${d.gap > 0 ? '+' : ''}${d.gap}（${d.gap > 0 ? '豆瓣更高' : d.gap < 0 ? 'TMDB更高' : '一致'}）`
    },
  },
  xAxis: {
    name: 'TMDB', nameLocation: 'middle', nameGap: 28,
    nameTextStyle: { color: U.text2, fontFamily: FONT },
    min: 0, max: 10, interval: 2,
    splitLine: { lineStyle: { color: U.grid } },
    axisLine: { lineStyle: { color: 'rgba(154,96,40,.4)' } },
    axisLabel: { color: U.text2, fontFamily: FONT },
  },
  yAxis: {
    name: '豆瓣', nameLocation: 'middle', nameGap: 34,
    nameTextStyle: { color: U.text2, fontFamily: FONT },
    min: 0, max: 10, interval: 2,
    splitLine: { lineStyle: { color: U.grid } },
    axisLine: { lineStyle: { color: 'rgba(154,96,40,.4)' } },
    axisLabel: { color: U.text2, fontFamily: FONT },
  },
  series: [{
    type: 'scatter',
    // 173 部同屏：点径收小、透明度降低，密集区不再糊成一团（悬停高亮会放大）
    symbolSize: (v) => 6.5 + Math.min(15, Math.abs(v[2] ?? 0) * 5),
    data: pts.value.map((p) => ({ ...p, value: [...p.value, p.gap] })),
    itemStyle: {
      color: (p) => {
        const g = p.data.gap
        return g > 0.5 ? U.orange : g < -0.5 ? U.cyan : U.gold
      },
      opacity: 0.72, borderColor: '#fff', borderWidth: 0.8,
    },
    emphasis: { itemStyle: { opacity: 1, borderColor: U.text } },
    animationDuration: 900, animationEasing: 'cubicOut',
  }],
}))
</script>

<style scoped>
.dv { display: flex; flex-direction: column; height: 100%; padding: 4px 2px; }
.dv__head { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; margin-bottom: 4px; }
.dv__head-l { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.dv__head-bar { width: 4px; height: 16px; border-radius: 2px; background: var(--u-orange); }
.dv__head-zh { font-size: 15px; font-weight: 700; color: var(--u-text); }
.dv__head-en { font-size: 11px; color: var(--u-text-2); }
.dv__note { font-size: 12px; color: var(--u-gold); font-weight: 600; white-space: nowrap; }
.dv__chart { flex: 1; min-height: 0; }
.dv__foot {
  margin: 4px 2px 0; font-size: 11.5px; line-height: 1.6; color: var(--u-text-2);
  border-left: 2px solid var(--u-orange); padding-left: 10px;
}
</style>
