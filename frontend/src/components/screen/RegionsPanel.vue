<template>
  <!--
    ============================================================
    年代流向展厅 · 国家/地区画像（右翼面板）—— 产量 × 口碑 气泡图
    ------------------------------------------------------------
    和「评分分化榜」的榜单版式刻意拉开：这里是空间叙事。
    · 横轴 = 影片数（对数刻度，否则美国 336 部会把其它点全压到左边）
    · 纵轴 = 平均评分；气泡越大 = 评价人数越多
    · 产量王（点最大）染橙、口碑王染金， hover 看明细
    · 一条参考线 = 这些国家的平均均分，上下一眼分出高产高质 / 高产平庸
    ============================================================
  -->
  <div class="rg">
    <div class="rg__head">
      <div class="rg__head-l">
        <i class="rg__bar" />
        <span class="rg__zh">谁在拍电影 · 谁拍得好</span>
        <span class="rg__en">OUTPUT vs QUALITY</span>
      </div>
      <span class="rg__note">{{ items.length }} 国/地区</span>
    </div>

    <v-chart class="rg__chart" :option="option" autoresize />

    <div class="rg__legend">
      <span><i class="rg__dot rg__dot--king" />产量王</span>
      <span><i class="rg__dot rg__dot--star" />口碑王</span>
      <span><i class="rg__dot rg__dot--avg" />平均线</span>
    </div>
  </div>
</template>

<script setup>
// ============================================================
// 国家/地区画像：产量 × 口碑 气泡散点（数据 /insights/regions）
// ============================================================
import { computed } from 'vue'
import VChart, { FONT } from '../insights/echarts.js'
import { U } from './useChart.js'

const props = defineProps({
  regions: { type: Object, default: null },
})

const items = computed(() => (props.regions?.items || [])
  .filter((r) => r.avg_rating !== null && r.avg_rating !== undefined))

const king = computed(() =>               // 产量王
  items.value.reduce((a, b) => (b.movies > (a?.movies ?? -1) ? b : a), null))
const star = computed(() => {             // 口碑王（>=8 部，样本太小没说服力）
  const sig = items.value.filter((r) => r.movies >= 8)
  const pool = sig.length ? sig : items.value
  return pool.reduce((a, b) => (b.avg_rating > (a?.avg_rating ?? -1) ? b : a), null)
})
const avgLine = computed(() => {
  if (!items.value.length) return 0
  return items.value.reduce((s, r) => s + r.avg_rating, 0) / items.value.length
})

function colorOf(r) {
  if (king.value && r.country === king.value.country) return U.orange
  if (star.value && r.country === star.value.country) return U.gold
  return 'rgba(125, 107, 82, 0.55)'
}

const option = computed(() => ({
  backgroundColor: 'transparent',
  grid: { left: 46, right: 20, top: 30, bottom: 44 },
  tooltip: {
    trigger: 'item',
    backgroundColor: 'rgba(58,46,32,.92)',
    borderWidth: 0,
    textStyle: { color: '#fff', fontFamily: FONT, fontSize: 12 },
    formatter: (p) => {
      const d = p.data
      return `<b>${d.name}</b><br/>影片 ${d.value[0]} 部 · 均分 ${d.value[1]}<br/>平均 ${Number(d.value[2]).toLocaleString()} 人评价`
    },
  },
  xAxis: {
    type: 'log',
    name: '影片数（部，对数）',
    nameLocation: 'middle', nameGap: 28,
    min: 5,
    nameTextStyle: { color: U.text2, fontFamily: FONT, fontSize: 10 },
    splitLine: { lineStyle: { color: U.grid } },
    axisLine: { lineStyle: { color: 'rgba(154,96,40,.4)' } },
    axisLabel: { color: U.text2, fontFamily: FONT, fontSize: 10 },
  },
  yAxis: {
    type: 'value',
    name: '平均评分',
    nameLocation: 'middle', nameGap: 32,
    min: (v) => Math.floor((v.min - 0.4) * 2) / 2,
    max: (v) => Math.ceil((v.max + 0.3) * 2) / 2,
    nameTextStyle: { color: U.text2, fontFamily: FONT, fontSize: 10 },
    splitLine: { lineStyle: { color: U.grid } },
    axisLine: { lineStyle: { color: 'rgba(154,96,40,.4)' } },
    axisLabel: { color: U.text2, fontFamily: FONT, fontSize: 10 },
  },
  series: [{
    type: 'scatter',
    data: items.value.map((r) => ({
      name: r.country,
      value: [r.movies, r.avg_rating, r.avg_votes || 0],
      itemStyle: { color: colorOf(r), opacity: 0.85, borderColor: '#fff', borderWidth: 1 },
    })),
    symbolSize: (v) => 11 + Math.log10(Math.max(1, v[0])) * 6,
    label: {
      show: true,
      position: 'top',
      distance: 6,
      color: U.text,
      fontFamily: FONT,
      fontSize: 11,
      fontWeight: 600,
      formatter: (p) => p.data.name,
    },
    emphasis: {
      itemStyle: { opacity: 1, borderColor: U.text, borderWidth: 1.5 },
      label: { fontSize: 12.5 },
    },
    markLine: {
      silent: true,
      symbol: 'none',
      lineStyle: { color: U.goldSoft, type: 'dashed', width: 1 },
      label: {
        position: 'insideEndTop',
        color: U.gold,
        fontFamily: FONT,
        fontSize: 9,
        formatter: `平均 ${avgLine.value.toFixed(2)}`,
      },
      data: [{ yAxis: avgLine.value }],
    },
    animationDuration: 800,
    animationEasing: 'cubicOut',
  }],
}))
</script>

<style scoped>
.rg { display: flex; flex-direction: column; height: 100%; min-height: 0; padding: 4px 2px; }
.rg__head { display: flex; align-items: flex-start; justify-content: space-between; gap: 10px; margin-bottom: 4px; }
.rg__head-l { display: flex; align-items: center; gap: 7px; flex-wrap: wrap; }
.rg__bar { width: 4px; height: 15px; border-radius: 2px; background: var(--u-gold); }
.rg__zh { font-size: 14.5px; font-weight: 700; color: var(--u-text); }
.rg__en { font-family: var(--u-font-tech); font-size: 9px; letter-spacing: .16em; color: var(--u-text-2); }
.rg__note { font-size: 11.5px; color: var(--u-gold); font-weight: 600; white-space: nowrap; }
.rg__chart { flex: 1; min-height: 0; }

.rg__legend {
  flex: none;
  display: flex;
  gap: 16px;
  padding-top: 6px;
  border-top: 1px solid rgba(154, 96, 40, .16);
  font-size: 10.5px;
  color: var(--u-text-2);
}
.rg__legend i { display: inline-block; width: 9px; height: 9px; border-radius: 50%; margin-right: 5px; vertical-align: -1px; }
.rg__dot--king { background: var(--u-orange); }
.rg__dot--star { background: var(--u-gold); }
.rg__dot--avg { background: transparent; border: 1.5px dashed var(--u-gold); border-radius: 0; height: 0; width: 12px; vertical-align: 3px; }
</style>
