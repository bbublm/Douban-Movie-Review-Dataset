<!--
  票房分析展厅 · 第三层「数据背板」
  ============================================================
  用户 2026-11-02：每个数据页面的数据要多一点、更高级，
  并参考 a24.raviklaassens.com / justinesoulie.fr 的做法。

  所以这一层不做"卡片里的彩色条形图"，改成 A24 左侧那种「细线账簿」：
    · 标签左、数字右，中间一条发丝线，没有底色没有圆角
    · 数值下面只有一条 2px 的金色细线表示比例（不抢视线）
  数据全部来自 /insights/box-office。
-->
<template>
  <div class="bx">
    <!-- ① 票房总账 -->
    <section class="bx__cell">
      <header class="bx__h">
        <span>票房总账</span>
        <em>BOX OFFICE LEDGER</em>
      </header>
      <ul class="bx__ledger">
        <li v-for="(k, i) in kpis" :key="k.label" :style="{ animationDelay: `${i * 70}ms` }">
          <span class="bx__k">{{ k.label }}</span>
          <b v-if="k.plain" class="bx__v">{{ k.value }}<i>{{ k.unit }}</i></b>
          <b v-else class="bx__v">
            <RollingNumber :value="k.value" :decimals="k.decimals" :duration="1200" :delay="i * 90" /><i>{{ k.unit }}</i>
          </b>
        </li>
      </ul>
      <p class="bx__note">覆盖 {{ yearCount }} 个年份 · 库内 {{ totalMovies }} 部影片有票房记录</p>
    </section>

    <!-- ② 投资回报榜 -->
    <section class="bx__cell">
      <header class="bx__h">
        <span>投资回报榜</span>
        <em>ROI = 票房 ÷ 预算</em>
      </header>
      <ul class="bx__rows">
        <li
          v-for="(g, i) in roiRows"
          :key="g.movie_id"
          class="bx__row"
          :style="{ animationDelay: `${i * 55}ms`, '--w': pctRoi(g) + '%' }"
          :title="`${g.title}：票房 ${yi(g.revenue)} 亿 / 预算 ${yi(g.budget)} 亿`"
          @click="$emit('pick', g)"
        >
          <span class="bx__no" :class="{ 'is-top': i < 3 }">{{ String(i + 1).padStart(2, '0') }}</span>
          <span class="bx__nm">{{ g.title }}</span>
          <b class="bx__val">{{ g.roi.toFixed(1) }}<i>×</i></b>
        </li>
      </ul>
    </section>

    <!-- ③ 类型票房 -->
    <section class="bx__cell">
      <header class="bx__h">
        <span>类型票房</span>
        <em>TOP 24 · 按类型归集</em>
      </header>
      <ul class="bx__rows">
        <li
          v-for="(g, i) in genreRows"
          :key="g.name"
          class="bx__row bx__row--genre"
          :style="{ animationDelay: `${i * 60}ms`, '--w': g.pct + '%' }"
        >
          <span class="bx__nm">{{ g.name }}</span>
          <b class="bx__val">{{ g.total }}<i> 亿</i></b>
        </li>
      </ul>
      <p class="bx__note">一部影片可计入多个类型，故合计大于总票房</p>
    </section>
  </div>
</template>

<script setup>
// ============================================================
// 票房数据背板（总账 / ROI / 类型票房）—— 细线账簿排版
// ============================================================
import { computed, onMounted, ref } from 'vue'
import RollingNumber from './RollingNumber.vue'

const props = defineProps({
  gallery: { type: Array, default: () => [] },
  totalMovies: { type: Number, default: 0 },
  totalRevenue: { type: Number, default: 0 },
  topYear: { type: Number, default: null },
  years: { type: Array, default: () => [] },
})
defineEmits(['pick'])

const drawn = ref(false)
onMounted(() => requestAnimationFrame(() => { drawn.value = true }))

const USD_YI = 1e8
const yi = (v) => Math.round(((v || 0) / USD_YI) * 10) / 10

const yearCount = computed(() => (props.years || []).length || '—')

const kpis = computed(() => {
  const total = props.totalRevenue || 0
  const n = props.totalMovies || 1
  return [
    { label: '累计票房', value: Math.round(total / USD_YI), decimals: 0, unit: ' 亿' },
    { label: '有票房影片', value: props.totalMovies, decimals: 0, unit: ' 部' },
    { label: '单片均票房', value: Math.round((total / n / USD_YI) * 100) / 100, decimals: 2, unit: ' 亿' },
    // 年份不做千分位（2026 不该写成 2,026）
    { label: '最卖座年份', value: props.topYear || 0, decimals: 0, unit: '', plain: true },
  ]
})

/* 投资回报：ROI 已由后端算好（票房 ÷ 预算），取前 8 */
const roiRows = computed(() => (props.gallery || [])
  .filter((g) => g && g.roi > 0)
  .sort((a, b) => b.roi - a.roi)
  .slice(0, 8))
const roiMax = computed(() => Math.max(1, ...roiRows.value.map((g) => g.roi)))
const pctRoi = (g) => Math.max(6, (g.roi / roiMax.value) * 100)

/* 类型票房：TOP24 画廊按类型归集，取前 6 */
const genreRows = computed(() => {
  const m = new Map()
  for (const g of props.gallery || []) {
    for (const ge of g.genres || []) m.set(ge, (m.get(ge) || 0) + (g.revenue || 0))
  }
  const rows = [...m.entries()].map(([name, v]) => ({ name, v })).sort((a, b) => b.v - a.v).slice(0, 6)
  const max = Math.max(1, ...rows.map((r) => r.v))
  return rows.map((r) => ({ name: r.name, total: Math.round(r.v / USD_YI), pct: (r.v / max) * 100 }))
})
</script>

<style scoped>
.bx {
  display: grid;
  grid-template-columns: 0.9fr 1.3fr 0.95fr;
  height: 100%;
  min-height: 0;
}
/* 细线分栏：不用卡片，只在中缝画一条发丝线（A24 的表格感） */
.bx__cell {
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: 0 20px;
}
.bx__cell:first-child { padding-left: 2px; }
.bx__cell:last-child { padding-right: 2px; }
.bx__cell + .bx__cell { border-left: 1px solid rgba(58, 46, 32, 0.14); }

.bx__h {
  flex: none;
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 10px;
  padding-bottom: 7px;
  border-bottom: 1px solid rgba(58, 46, 32, 0.32);
}
.bx__h span { font-size: 12px; font-weight: 700; color: var(--u-text, #3A2E20); letter-spacing: 0.14em; }
.bx__h em {
  font-style: normal;
  font-family: var(--u-font-tech, "Orbitron"), sans-serif;
  font-size: 8px; letter-spacing: 0.16em; color: rgba(125, 107, 82, 0.75);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}

/* ① 总账：四行标签/数字 */
.bx__ledger { flex: 1; min-height: 0; display: flex; flex-direction: column; justify-content: center; }
.bx__ledger li {
  display: flex; align-items: baseline; justify-content: space-between; gap: 12px;
  padding: 6px 0; border-bottom: 1px solid rgba(58, 46, 32, 0.1);
  animation: bx-in 0.5s ease backwards;
}
.bx__ledger li:last-child { border-bottom: 0; }
.bx__k { font-size: 11px; color: var(--u-text-2, #7D6B52); letter-spacing: 0.04em; }
.bx__v {
  font-family: var(--u-font-tech, "Orbitron"), sans-serif;
  font-size: 22px; font-weight: 800; line-height: 1; color: #8B4513;
  font-variant-numeric: tabular-nums;
}
.bx__v i { font-style: normal; font-size: 10px; font-weight: 500; color: var(--u-text-2, #7D6B52); margin-left: 3px; }

/* ②③ 榜单：细线行 + 2px 金色进度线（不画满格条） */
.bx__rows { flex: 1; min-height: 0; display: flex; flex-direction: column; justify-content: space-around; }
.bx__row {
  position: relative;
  display: grid;
  grid-template-columns: 22px 1fr auto;
  align-items: baseline;
  gap: 10px;
  padding: 2px 0 3px;
  border-bottom: 1px solid rgba(58, 46, 32, 0.1);
  cursor: pointer;
  animation: bx-in 0.45s ease backwards;
  transition: color 0.2s ease, padding-left 0.2s ease;
}
.bx__row--genre { grid-template-columns: 1fr auto; }
.bx__row:last-child { border-bottom: 0; }
/* 比例只用一条 2px 线表达：短、克制、不抢数字 */
.bx__row::after {
  content: '';
  position: absolute; left: 0; bottom: -1px;
  width: var(--w, 0%);
  height: 2px;
  background: linear-gradient(90deg, rgba(166, 124, 46, 0.55), #C2410C);
  transition: width 0.85s cubic-bezier(0.22, 1, 0.36, 1);
}
.bx__row:hover { padding-left: 3px; }
.bx__row:hover .bx__nm { color: #C2410C; }
@keyframes bx-in { from { opacity: 0; transform: translateY(7px); } to { opacity: 1; transform: none; } }

.bx__no {
  font-family: var(--u-font-tech, "Orbitron"), sans-serif;
  font-size: 9.5px; color: rgba(125, 107, 82, 0.8); letter-spacing: 0.05em;
}
.bx__no.is-top { color: #C2410C; }
.bx__nm {
  font-size: 11.5px; line-height: 1.25; color: var(--u-text, #3A2E20);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  transition: color 0.2s ease;
}
.bx__val {
  font-family: var(--u-font-tech, "Orbitron"), sans-serif;
  font-size: 12px; font-weight: 700; line-height: 1.2; color: #8B4513;
  font-variant-numeric: tabular-nums; white-space: nowrap;
}
.bx__val i { font-style: normal; font-size: 9px; font-weight: 500; color: var(--u-text-2, #7D6B52); }

.bx__note {
  flex: none; margin: 6px 0 0; padding-top: 5px;
  border-top: 1px solid rgba(58, 46, 32, 0.1);
  font-size: 9.5px; line-height: 1.45; color: rgba(125, 107, 82, 0.9);
}

@media (max-width: 1280px) {
  .bx { grid-template-columns: 1fr 1fr; grid-template-rows: auto auto; }
  .bx__cell:first-child { grid-column: 1 / -1; border-left: 0; padding-left: 2px; }
  .bx__cell:nth-child(2) { border-left: 0; }
}
@media (prefers-reduced-motion: reduce) {
  .bx__ledger li, .bx__row { animation: none; }
  .bx__row::after { transition: none; }
}
</style>
