<!--
  票房分析展厅 · 左翼面板：全球票房榜 TOP 10
  ============================================================
  纯 DOM 条形榜（不引 ECharts）：十条以内的排名用 DOM 更轻，
  hover / 逐条延迟动画比 canvas 好做（与 GenreRankCard 同一套路）。
  数据：/insights/box-office 的 gallery（已按票房倒序）。
-->
<template>
  <div class="borank">
    <div class="borank__head">
      <span class="borank__head-zh">全球票房榜</span>
      <span class="borank__head-en">TOP 10</span>
    </div>
    <div class="borank__list">
      <div
        v-for="(g, i) in rows"
        :key="g.movie_id"
        class="borank__row"
        :style="{ animationDelay: `${i * 70}ms` }"
        @click="$emit('pick', g)"
      >
        <span class="borank__rank" :class="{ 'is-top': i < 3 }">{{ String(i + 1).padStart(2, '0') }}</span>
        <span class="borank__name" :title="g.title">{{ g.title }}</span>
        <span class="borank__bar"><i :style="{ width: drawn ? g.pct + '%' : '0%' }" /></span>
        <span class="borank__val">{{ yi(g.revenue) }}<em> 亿</em></span>
        <span v-if="g.roi" class="borank__roi" :class="{ 'is-hot': g.roi >= 5 }">{{ g.roi }}×</span>
      </div>
    </div>
    <p v-if="!rows.length" class="borank__empty">暂无票房数据</p>
  </div>
</template>

<script setup>
// ============================================================
// 票房榜：gallery 前 10 条，条形长度按票房归一
// ============================================================
import { computed, onMounted, ref } from 'vue'

const props = defineProps({
  gallery: { type: Array, default: () => [] },
  totalMovies: { type: Number, default: 0 },
})
defineEmits(['pick'])

const drawn = ref(false)
onMounted(() => requestAnimationFrame(() => { drawn.value = true }))

/* 美元 → 亿美元（个位数保留一位小数） */
function yi(usd) {
  const v = (usd || 0) / 1e8
  return v >= 10 ? Math.round(v) : Math.round(v * 10) / 10
}

const rows = computed(() => {
  const list = (props.gallery || []).filter((g) => g && g.revenue)
  const max = Math.max(1, ...list.map((g) => g.revenue))
  return list.slice(0, 10).map((g) => ({ ...g, pct: (g.revenue / max) * 100 }))
})
</script>

<style scoped>
.borank { display: flex; flex-direction: column; height: 100%; min-height: 0; }
.borank__head { display: flex; align-items: baseline; gap: 8px; padding-bottom: 8px; }
.borank__head-zh { font-size: 13px; font-weight: 800; color: var(--u-text, #3A2E20); letter-spacing: 0.04em; }
.borank__head-en { font-size: 10px; color: var(--u-text-2, #7D6B52); letter-spacing: 0.06em; }
.borank__list { flex: 1; min-height: 0; overflow: auto; display: flex; flex-direction: column; gap: 3px; }
.borank__row {
  display: grid;
  grid-template-columns: 24px 1fr 58px 42px auto;
  align-items: center;
  gap: 6px;
  padding: 2px 7px;
  background: rgba(255, 253, 247, 0.72);
  border: 1px solid rgba(139, 107, 71, 0.22);
  border-radius: 9px 4px 10px 4px;
  cursor: pointer;
  animation: borank-in 0.4s ease both;
  transition: border-color 0.2s ease, transform 0.2s ease;
}
.borank__row:hover { border-color: #C2410C; transform: translateX(2px); }
@keyframes borank-in { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: none; } }
.borank__rank {
  font-family: var(--u-font-tech, "Orbitron"), sans-serif;
  font-size: 12px;
  font-weight: 700;
  color: var(--u-text-2, #7D6B52);
  text-align: center;
}
.borank__rank.is-top { color: #C2410C; }
.borank__name {
  font-size: 11.5px;
  color: var(--u-text, #3A2E20);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.borank__bar { height: 5px; background: rgba(154, 96, 40, 0.14); border-radius: 3px; overflow: hidden; }
.borank__bar i {
  display: block;
  height: 100%;
  border-radius: 3px;
  background: linear-gradient(90deg, #A67C2E, #C2410C);
  transition: width 0.9s cubic-bezier(0.22, 1, 0.36, 1);
}
.borank__val { font-size: 12px; font-weight: 800; color: #8B4513; text-align: right; }
.borank__val em { font-style: normal; font-size: 9.5px; color: var(--u-text-2, #7D6B52); }
.borank__roi {
  font-size: 10px;
  font-weight: 700;
  color: #0F766E;
  background: rgba(15, 118, 110, 0.12);
  border-radius: 8px;
  padding: 1px 5px;
}
.borank__roi.is-hot { color: #C2410C; background: rgba(194, 65, 12, 0.12); }
.borank__empty { font-size: 11.5px; color: var(--u-text-2, #7D6B52); padding: 12px 4px; }

@media (prefers-reduced-motion: reduce) {
  .borank__row { animation: none; }
  .borank__bar i { transition: none; }
}
</style>
