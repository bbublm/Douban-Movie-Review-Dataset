<template>
  <div class="dbp">
    <!-- 情感环 -->
    <div class="dbp__ring">
      <v-chart class="dbp__chart" :option="sentOption" autoresize />
    </div>
    <div class="dbp__legend">
      <span v-for="s in sentItems" :key="s.key" class="dbp__leg">
        <i :style="{ background: s.color }" />{{ s.label }} <b>{{ s.value }}</b>
        <em class="dbp__leg-p">{{ s.pct }}%</em>
      </span>
    </div>

    <!-- 高分 Top -->
    <div class="dbp__top-h">豆瓣高分 Top（票数 ≥ 200）</div>
    <div class="dbp__rows">
      <div v-for="m in topRated" :key="m.title" class="dbp__row">
        <span class="dbp__row-t" :title="m.title">{{ m.title }}</span>
        <span class="dbp__row-v">{{ m.douban_rating.toFixed(1) }}</span>
      </div>
      <p v-if="!topRated.length" class="dbp__empty">暂无高分数据</p>
    </div>
  </div>
</template>

<script setup>
// ============================================================
// 左翼面板 · 豆瓣口碑（情感分布环 + 高分 Top）
// ------------------------------------------------------------
// 数据：/douban/insights 的 sentiment_dist / top_rated（真实豆瓣短评）
// ============================================================
import { computed } from 'vue'
import VChart, { CHART_COLORS, FONT } from '../insights/echarts.js'

const props = defineProps({
  douban: { type: Object, default: null },
})

const SENT = [
  { key: 'positive', label: '正面', color: CHART_COLORS.positive },
  { key: 'neutral', label: '中性', color: CHART_COLORS.neutral },
  { key: 'negative', label: '负面', color: CHART_COLORS.negative },
]

const sentItems = computed(() => {
  const dist = props.douban?.sentiment_dist || {}
  const total = props.douban?.sentiment_total || 0
  return SENT.map((s) => ({ ...s, value: dist[s.key] || 0, pct: total ? Math.round(100 * (dist[s.key] || 0) / total) : 0 }))
})

const sentOption = computed(() => ({
  backgroundColor: 'transparent',
  tooltip: { trigger: 'item', formatter: (p) => `${p.name}：${p.value} 篇（${p.percent}%）`, textStyle: { fontFamily: FONT } },
  legend: { show: false },
  series: [{
    type: 'pie', radius: ['52%', '74%'], center: ['50%', '50%'],
    avoidLabelOverlap: true, label: { show: false },
    itemStyle: { borderColor: 'rgba(255,253,247,.9)', borderWidth: 3, borderRadius: 6 },
    data: sentItems.value.map((s) => ({ name: s.label, value: s.value, itemStyle: { color: s.color } })),
    animationType: 'scale', animationDuration: 800,
  }],
}))

// 接口共 12 条真实高分片；数据页加长后 8 行会留一大截空白，取满 12 行
const topRated = computed(() => (props.douban?.top_rated || []).slice(0, 12))
</script>

<style scoped>
.dbp { display: flex; flex-direction: column; height: 100%; gap: 3px; }
/* 数据页加长后高度充裕：情感环放大到可读尺寸（原先压到 38px 是被矮卡片逼的），
   仍用 clamp 兜底，窄屏下不会把 12 行榜单挤没 */
.dbp__ring { height: clamp(96px, 13vh, 132px); }
.dbp__chart { width: 100%; height: 100%; }
.dbp__legend { display: flex; flex-wrap: wrap; gap: 5px 12px; justify-content: center; margin-top: -3px; }
.dbp__leg { display: inline-flex; align-items: center; gap: 5px; font-size: 11px; color: var(--u-text-2); }
.dbp__leg i { width: 9px; height: 9px; border-radius: 3px; }
.dbp__leg b { color: var(--u-text); }
.dbp__leg-p { font-style: normal; font-size: 9.5px; color: rgba(125, 107, 82, .8); }
.dbp__top-h {
  margin-top: 1px; font-size: 12px; font-weight: 700; color: var(--u-text);
  border-top: 1px solid var(--u-line); padding-top: 4px;
}
.dbp__rows { display: flex; flex-direction: column; gap: 3px; overflow-y: auto; flex: 1; min-height: 48px; }
.dbp__row {
  display: flex; align-items: center; justify-content: space-between; gap: 8px;
  font-size: 11.5px; height: 22px; line-height: 22px;
  padding: 0 6px; margin: 0 -6px; border-radius: 6px;
  transition: background .18s ease, transform .18s ease;
}
.dbp__row:hover { background: rgba(194, 65, 12, .07); transform: translateX(2px); }
.dbp__row-t {
  color: var(--u-text); flex: 1; min-width: 0;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.dbp__row-v { color: var(--u-gold); font-weight: 700; }
.dbp__empty { font-size: 12px; color: var(--u-text-2); }
</style>
