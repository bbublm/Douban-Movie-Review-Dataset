<template>
  <!-- 知识图谱：力导向关系网络，节点/边全部来自 /insights/knowledge-graph 的共现 + lift -->
  <AnalysisCard kicker="KNOWLEDGE GRAPH" title="影人 × 类型知识图谱" :note="note">
    <div class="kg__chart">
      <v-chart :option="option" autoresize />
    </div>
    <div class="kg__legend">
      <span><i style="background:#C2410C" />类型</span>
      <span><i style="background:#A67C2E" />导演</span>
      <span><i style="background:#0F766E" />演员</span>
      <b>拖一拖节点 · 滚轮缩放</b>
    </div>
  </AnalysisCard>
</template>

<script setup>
import { computed } from 'vue'
import VChart, { FONT } from '../insights/echarts.js'
import AnalysisCard from './AnalysisCard.vue'

const props = defineProps({ knowledge: { type: Object, default: null } })

const COLORS = { genre: '#C2410C', director: '#A67C2E', actor: '#0F766E' }
const note = computed(() => (props.knowledge?.notes || []).join(' · ') || '暂无共现数据')

const option = computed(() => {
  const k = props.knowledge
  // 小卡里 34 个节点全打标签 = 一团字。只给「全部类型 + 覆盖影片最多的 8 位影人」
  // 常驻标签，其余靠悬停 / 高亮显示；关系本身仍完整保留，不是删数据。
  const labelled = new Set((k?.nodes || [])
    .filter((n) => n.kind !== 'genre')
    .sort((a, b) => (b.value || 0) - (a.value || 0))
    .slice(0, 8).map((n) => n.id))
  const nodes = (k?.nodes || []).map((n) => ({
    id: n.id,
    name: n.name,
    category: n.kind === 'genre' ? 0 : n.kind === 'director' ? 1 : 2,
    symbolSize: Math.max(13, Math.min(46, 11 + Math.sqrt(n.value || 1) * 5.5)),
    value: n.value,
    avg_rating: n.avg_rating,
    label: { show: n.kind === 'genre' || labelled.has(n.id) },
    itemStyle: {
      color: COLORS[n.kind], borderColor: '#FFF8E8', borderWidth: 2,
      shadowBlur: 7, shadowColor: 'rgba(74,44,20,.24)',
    },
  }))
  const links = (k?.links || []).map((l) => ({
    source: l.source, target: l.target,
    weight: l.weight, lift: l.lift,
    lineStyle: {
      width: Math.min(5.5, 0.7 + Math.log2(1 + l.weight) * 0.72),
      color: l.kind === 'genre-genre' ? '#8B4513' : '#A98A55',
      opacity: 0.28 + Math.min(0.5, (l.lift - 1) * 0.12),
      curveness: l.kind === 'genre-genre' ? 0.2 : 0.06,
    },
  }))
  return {
    backgroundColor: 'transparent',
    textStyle: { fontFamily: FONT },
    animationDuration: 700,
    tooltip: {
      backgroundColor: '#FFFCF4', borderColor: '#8B7355', borderWidth: 1,
      textStyle: { color: '#3A2E20', fontSize: 11 },
      formatter: (p) => (p.dataType === 'edge'
        ? `共现 <b>${p.data.weight}</b> 部 · 提升度 <b>${p.data.lift}</b>`
        : `<b>${p.name}</b><br/>涉及影片 ${p.value} 部${p.data.avg_rating != null ? ` · 均分 ${p.data.avg_rating}` : ''}`),
    },
    // 图例由卡片底部的 .kg__legend 承担，画布里不再放第二份，省出纵向空间
    series: [{
      type: 'graph',
      layout: 'force',
      roam: true,
      draggable: true,
      data: nodes,
      links,
      categories: [
        { name: '类型', itemStyle: { color: COLORS.genre } },
        { name: '导演', itemStyle: { color: COLORS.director } },
        { name: '演员', itemStyle: { color: COLORS.actor } },
      ],
      // 斥力别开太大：400px 卡里 190 会把节点顶到边缘被裁掉半个圆
      force: { repulsion: 135, edgeLength: [40, 110], gravity: 0.16, friction: 0.6 },
      emphasis: { focus: 'adjacency', label: { show: true, fontSize: 11, fontWeight: 700 } },
      label: { show: true, position: 'right', distance: 4, fontSize: 10, color: '#3A2E20' },
      // 节点半径最大 23px，四边留够，圆不会被 chart 边界切掉
      left: 28, right: 28, top: 20, bottom: 16,
    }],
  }
})
</script>

<style scoped>
.kg__chart { width: 100%; height: calc(100% - 20px); min-height: 0; }
.kg__chart :deep(canvas) { cursor: grab; }
.kg__legend {
  display: flex; align-items: center; gap: 10px; height: 18px;
  font-size: 9px; color: #6F5C44;
}
.kg__legend span { display: inline-flex; align-items: center; gap: 4px; }
.kg__legend i { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
.kg__legend b { margin-left: auto; font-weight: 400; color: #8B5E1C; }
@media (max-width: 700px) { .kg__legend b { display: none; } }
</style>
