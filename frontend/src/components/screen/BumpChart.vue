<template>
  <div class="bump">
    <div class="bump__head">
      <div class="bump__head-l">
        <i class="bump__head-bar" />
        <span class="bump__head-zh">口碑排名变化</span>
        <span class="bump__head-en">按各年代均分排名</span>
      </div>
      <span class="bump__note">{{ verdict }}</span>
    </div>
    <div class="bump__body">
      <div ref="el" class="bump__chart" />
      <p v-if="!series.length" class="bump__empty">暂无评分数据</p>
    </div>
    <p class="bump__foot">线条上下起伏 = 该年代的类型口碑位次变化（No.1 为口碑最佳）</p>
  </div>
</template>

<script setup>
// ============================================================
// 中央舞台 · 口碑排名变化（Flourish Bump Chart 的深空 HUD 版）
// ------------------------------------------------------------
// 数据：/insights/matrix 的 avg_rating 列
// 每年代内按均分排名（No.1 口碑最佳），Top 6 类型各一条折线，
// 线本身即"位次起伏"；缺评分的年代断线（connectNulls:false，不假装有数据）。
// 入场按线序错峰 animationDelay —— Flourish 的招牌错峰感。
// ============================================================
import { computed, watch } from 'vue'
import { useChart, U } from './useChart.js'

const props = defineProps({
  matrix: { type: Object, default: null },
})

/* 折线配色（2026-10-19 增彩）：暖金 / 青 / 橙 / 天蓝 / 紫 / 玫瑰，
   六条线在深蓝底上彼此可辨，不再是"金蓝灰"一家亲 */
const LINE_COLORS = ['#D9903A', '#0F766E', '#C2410C', '#0369A1', '#A78BFA', '#E11D48']

const series = computed(() => {
  const rows = props.matrix?.rows || []
  if (!rows.length || !decades.value.length) return []

  // 每个年代算一次均分排名（只排有分的类型，缺分不进榜）
  const rankOf = decades.value.map((d) => {
    const scored = rows
      .map((r) => {
        const cell = (r.cells || []).find((c) => c.decade === d)
        return { genre: r.genre, rating: cell?.avg_rating ?? null }
      })
      .filter((x) => x.rating != null)
      .sort((a, b) => b.rating - a.rating)
    const map = new Map()
    scored.forEach((x, i) => map.set(x.genre, i + 1))
    return map
  })

  return rows.slice(0, 6).map((r, i) => {
    const data = decades.value.map((d, di) => rankOf[di].get(r.genre) ?? null)
    const last = [...data].reverse().find((v) => v != null)
    return {
      name: r.genre,
      color: LINE_COLORS[i % LINE_COLORS.length],
      data,
      // 末端标签只给当前前三名：六根线末端都贴标签必然叠在一起
      showEnd: last != null && last <= 3,
    }
  })
})

/* ★ 只保留"至少一个类型有均分"的年代：1930s-1960s 库内影片稀少、
   评分全空，占着横轴四分之一让折线从半路才开始 —— 过滤后图幅全用在数据上。 */
const decades = computed(() => {
  const raw = props.matrix?.decades || []
  const rows = props.matrix?.rows || []
  return raw.filter((d) =>
    rows.some((r) => (r.cells || []).some((c) => c.decade === d && c.avg_rating != null)),
  )
})

const decadesLabel = computed(() => decades.value.map((d) => `${String(d).slice(2)}年代`))

/* 一句话结论：谁升得最快 / 谁守得最稳（首尾排名差推导，不写死文案） */
const verdict = computed(() => {
  const ss = series.value
  if (ss.length < 2) return ''
  const first = (s) => s.data.find((v) => v != null)
  const last = (s) => [...s.data].reverse().find((v) => v != null)
  let up = ss[0], gap = -Infinity
  for (const s of ss) {
    const d = (first(s) ?? 0) - (last(s) ?? 0)
    if (d > gap) { gap = d; up = s }
  }
  if (gap > 0) return `「${up.name}」口碑爬升最快，前进 ${gap} 位`
  // 没有明显爬升：让当前榜首自己说话
  const best = ss.reduce((a, b) => ((last(a) ?? 99) <= (last(b) ?? 99) ? a : b))
  return `「${best.name}」守住口碑榜首（第 ${last(best) ?? '—'} 名）`
})

function buildOption() {
  const max = Math.max(2, ...series.value.map((s) => Math.max(...s.data.filter((v) => v != null))))
  return {
    grid: { left: 4, right: 74, top: 12, bottom: 2, containLabel: true },
    xAxis: {
      type: 'category',
      boundaryGap: ['8%', '8%'],
      data: decadesLabel.value,
      axisLine: { lineStyle: { color: U.grid } },
      axisTick: { show: false },
      axisLabel: { color: U.text2, fontFamily: U.tech, fontSize: 10, margin: 10 },
    },
    yAxis: {
      type: 'value',
      inverse: true,
      min: 1,
      max,
      minInterval: 1,
      // 数值轴默认按 splitNumber=5 取刻度，会跳着显示（第1/第3/第5名）；
      // 名次是 1..N 的整数，强制步长 1 才能把每一名都标出来
      interval: 1,
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { show: false },
      axisLabel: {
        color: U.text2, fontFamily: U.tech, fontSize: 10,
        interval: 0,        // 名次只有 6~8 条，全部标出来
        hideOverlap: false, // 否则 ECharts 仍会静默抽掉「第 3 名」这类中间刻度
        formatter: '第 {value} 名',
      },
    },
    tooltip: {
      trigger: 'axis',
      backgroundColor: 'rgba(19, 27, 45, 0.95)',
      borderColor: 'rgba(194, 65, 12, 0.3)',
      textStyle: { color: '#4A3C2A', fontFamily: U.cn, fontSize: 12 },
      formatter: (ps) => {
        const d = decades.value[ps[0].dataIndex]
        const head = `${d} 年代`
        const rows = ps
          .filter((p) => p.value != null)
          .sort((a, b) => a.value - b.value)
          .map((p) => `${p.marker} ${p.seriesName} · 第 ${p.value} 名`)
        return [head, ...rows].join('<br/>')
      },
    },
    series: series.value.map((s, i) => ({
      type: 'line',
      name: s.name,
      smooth: 0.35,
      symbol: 'circle',
      symbolSize: 8,
      connectNulls: false,
      data: s.data,
      lineStyle: {
        width: 2.2,
        color: s.color,
        shadowColor: s.color,
        shadowBlur: 10,
        shadowOffsetY: 2,
      },
      itemStyle: { color: s.color, borderColor: '#FBF8F1', borderWidth: 1.5 },
      endLabel: {
        show: s.showEnd,
        distance: 8,
        formatter: s.name,
        color: s.color,
        fontFamily: U.cn,
        fontSize: 11,
        fontWeight: 600,
      },
      labelLayout: { moveOverlap: 'shiftY' },
      animationDelay: 260 + i * 230,
      animationDuration: 900,
    })),
  }
}

const option = computed(buildOption)
const { el, set } = useChart(() => option.value)
watch(option, (o) => set(o))
</script>

<style scoped>
.bump { display: flex; flex-direction: column; height: 100%; min-height: 0; }

.bump__head { flex: none; display: flex; align-items: center; justify-content: space-between; gap: 10px; }
.bump__head-l { display: flex; align-items: center; gap: 8px; }
.bump__head-bar { width: 3px; height: 13px; background: linear-gradient(to bottom, var(--u-cyan), transparent); box-shadow: 0 0 8px rgba(79, 209, 197, 0.6); }
.bump__head-zh { font-size: 13px; font-weight: 700; letter-spacing: 1.5px; color: var(--u-text); }
.bump__head-en { font-family: var(--u-font-tech); font-size: 9px; letter-spacing: 1.4px; color: rgba(125, 107, 82, 0.9); text-transform: uppercase; }
.bump__note {
  font-size: 11px; color: var(--u-orange);
  padding: 3px 10px;
  background: rgba(194, 65, 12, 0.08);
  border: 1px solid rgba(194, 65, 12, 0.3);
  clip-path: var(--u-poly); --u-cut: 6px;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  max-width: 52%;
}

.bump__body { position: relative; flex: 1; min-height: 0; margin-top: 4px; }
.bump__chart { position: absolute; inset: 0; }
.bump__empty { position: absolute; inset: 0; display: grid; place-items: center; font-size: 12px; color: var(--u-text-2); }

.bump__foot { flex: none; margin: 8px 0 0; font-size: 10.5px; color: rgba(125, 107, 82, 0.9); letter-spacing: .5px; }
</style>
