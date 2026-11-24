<template>
  <div class="flow">
    <div class="flow__head">
      <div class="flow__head-l">
        <i class="flow__head-bar" />
        <span class="flow__head-zh">类型 → 年代 流向</span>
        <span class="flow__head-en">影片数矩阵</span>
      </div>
      <span class="flow__note">{{ total }} 部次</span>
    </div>
    <div class="flow__body">
      <div ref="el" class="flow__chart" />
      <p v-if="!links.length" class="flow__empty">暂无矩阵数据</p>
    </div>
    <p class="flow__foot">
      左列 = 影片数 Top 8 类型，右列 = 年代；带宽 = 落入该年代的组合片数。
      一部电影可同时流向多个类型（混搭语义），故总带宽大于影片总数。
    </p>
  </div>
</template>

<script setup>
// ============================================================
// 中央舞台 · 类型→年代桑基流向（Flourish Sankey 的深空 HUD 版）
// ------------------------------------------------------------
// 数据：/insights/matrix
// 左节点 = Top 8 类型（金），右节点 = 年代（冷蓝），链接带宽 = 该类型在该年代的影片数。
// ECharts 原生 sankey + lineStyle.color:'gradient' 自动出源→目标渐变。
// ============================================================
import { computed, watch } from 'vue'
import { useChart, U } from './useChart.js'

const props = defineProps({
  matrix: { type: Object, default: null },
})

const model = computed(() => {
  const rows = props.matrix?.rows || []
  const rawDecades = props.matrix?.decades || []
  const top = rows.slice(0, 8)
  // 只保留"真的有片流入"的年代：1930s-1960s 无影片，
  // 留着会在右列竖排出一串空节点，白占四分之一幅面
  const decades = rawDecades.filter((d) =>
    top.some((g) => (g.cells || []).some((c) => c.decade === d && c.movies > 0)),
  )
  const nodes = [
    ...top.map((g) => ({ name: g.genre, itemStyle: { color: U.orange, borderColor: U.orange } })),
    ...decades.map((d) => ({ name: `${d} 年代`, itemStyle: { color: U.cyan, borderColor: U.cyan } })),
  ]
  const links = []
  for (const g of top) {
    for (const c of g.cells || []) {
      if (c.movies > 0) links.push({ source: g.genre, target: `${c.decade} 年代`, value: c.movies })
    }
  }
  return { nodes, links }
})

const links = computed(() => model.value.links)

const total = computed(() => links.value.reduce((s, l) => s + l.value, 0))

function buildOption() {
  const { nodes, links } = model.value
  return {
    tooltip: {
      trigger: 'item',
      backgroundColor: 'rgba(19, 27, 45, 0.95)',
      borderColor: 'rgba(194, 65, 12, 0.3)',
      textStyle: { color: '#4A3C2A', fontFamily: U.cn, fontSize: 12 },
      formatter: (p) =>
        p.dataType === 'edge'
          ? `${p.data.source} → ${p.data.target}<br/>${p.data.value} 部`
          : `${p.name} · ${p.value} 部`,
    },
    series: [{
      type: 'sankey',
      left: 6,
      right: 78,
      top: 8,
      bottom: 8,
      nodeWidth: 9,
      nodeGap: 7,
      nodeAlign: 'justify',
      data: nodes,
      links,
      lineStyle: {
        color: 'gradient',
        curveness: 0.52,
        opacity: 0.44,
      },
      label: {
        color: '#4A3C2A',
        fontFamily: U.cn,
        fontSize: 11,
      },
      emphasis: {
        focus: 'adjacency',
        lineStyle: { opacity: 0.62 },
      },
      animationDuration: 900,
      animationDelay: (i) => i * 40,
    }],
  }
}

const option = computed(buildOption)
const { el, set } = useChart(() => option.value)
watch(option, (o) => set(o))
</script>

<style scoped>
.flow { display: flex; flex-direction: column; height: 100%; min-height: 0; }

.flow__head { flex: none; display: flex; align-items: center; justify-content: space-between; }
.flow__head-l { display: flex; align-items: center; gap: 8px; }
.flow__head-bar { width: 3px; height: 13px; background: linear-gradient(to bottom, var(--u-orange), var(--u-cyan)); box-shadow: 0 0 8px rgba(194, 65, 12, 0.35); }
.flow__head-zh { font-size: 13px; font-weight: 700; letter-spacing: 1.5px; color: var(--u-text); }
.flow__head-en { font-family: var(--u-font-tech); font-size: 9px; letter-spacing: 1.4px; color: rgba(125, 107, 82, 0.9); text-transform: uppercase; }
.flow__note {
  font-family: var(--u-font-tech); font-size: 11px; letter-spacing: 1px;
  color: var(--u-gold);
  padding: 3px 10px;
  background: rgba(194, 65, 12, 0.08);
  border: 1px solid rgba(194, 65, 12, 0.3);
  clip-path: var(--u-poly); --u-cut: 6px;
}

.flow__body { position: relative; flex: 1; min-height: 0; margin-top: 4px; }
.flow__chart { position: absolute; inset: 0; }
.flow__empty { position: absolute; inset: 0; display: grid; place-items: center; font-size: 12px; color: var(--u-text-2); }

.flow__foot { flex: none; margin: 8px 0 0; font-size: 10.5px; line-height: 1.7; color: rgba(125, 107, 82, 0.9); }
</style>
