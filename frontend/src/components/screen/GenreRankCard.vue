<template>
  <div class="grank">
    <div class="grank__head">
      <span class="grank__head-zh">类型口碑</span>
      <span class="grank__head-en">电影侧均分 · IMDb/TMDB</span>
    </div>
    <div class="grank__list">
      <div
        v-for="(g, i) in rows"
        :key="g.genre"
        class="grank__row"
        :style="{ animationDelay: `${i * 80}ms` }"
      >
        <span class="grank__rank" :class="{ 'is-top': i === 0 }">{{ String(i + 1).padStart(2, '0') }}</span>
        <span class="grank__name">{{ g.genre }}</span>
        <span class="grank__bar"><i :style="{ width: drawn ? g.pct + '%' : '0%' }" /></span>
        <span class="grank__score">
          <RollingNumber :value="g.avg_rating || 0" :decimals="1" :duration="1200" :delay="i * 80" />
        </span>
        <span class="grank__n">{{ g.movies }} 部</span>
      </div>
    </div>
    <p v-if="!rows.length" class="grank__empty">暂无类型口碑数据</p>
  </div>
</template>

<script setup>
// ============================================================
// 右翼 · 类型口碑榜（纯 CSS 条形，不引 ECharts —— 十条以内的排名
// 用 DOM 更轻，且 hover/延迟动画比 canvas 好做）
// ------------------------------------------------------------
// 数据：/insights/sentiment 的 by_genre（电影侧均分，口径见 foot 注释）
// ============================================================
import { computed, onMounted, ref } from 'vue'
import RollingNumber from './RollingNumber.vue'

const props = defineProps({
  byGenre: { type: Array, default: () => [] },
})

const drawn = ref(false)
onMounted(() => requestAnimationFrame(() => { drawn.value = true }))

const rows = computed(() => {
  const list = (props.byGenre || [])
    .filter((g) => g && g.genre && g.avg_rating != null)
    .sort((a, b) => b.avg_rating - a.avg_rating)
    .slice(0, 12)   // 接口共 12 个类型；页面加长后取满，不再留大片空白
  const max = Math.max(1, ...list.map((g) => g.avg_rating))
  return list.map((g) => ({ ...g, pct: (g.avg_rating / max) * 100 }))
})
</script>

<style scoped>
.grank { display: flex; flex-direction: column; height: 100%; min-height: 0; }

.grank__head { flex: none; display: flex; align-items: baseline; gap: 8px; padding-bottom: 5px; border-bottom: 1px solid rgba(194, 65, 12, 0.25); }
.grank__head-zh { font-size: 12.5px; font-weight: 700; letter-spacing: 1.5px; color: var(--u-text); }
.grank__head-en { font-family: var(--u-font-tech); font-size: 9px; letter-spacing: 1.2px; color: rgba(125, 107, 82, 0.9); text-transform: uppercase; }

.grank__list { flex: 1; min-height: 0; display: flex; flex-direction: column; gap: 3px; padding: 2px 0; }
.grank__row {
  display: grid;
  grid-template-columns: 24px 48px 1fr 32px 38px;
  align-items: center;
  gap: 7px;
  height: 22px;
  padding: 0 6px;
  margin: 0 -6px;
  border-radius: 6px;
  opacity: 0;
  transform: translateX(-8px);
  animation: grank-in .55s cubic-bezier(0.16, 0.84, 0.44, 1) forwards;
  transition: background .18s ease;
}
.grank__row:hover { background: rgba(194, 65, 12, 0.07); }
@keyframes grank-in { to { opacity: 1; transform: none; } }

.grank__rank { font-family: var(--u-font-tech); font-size: 10.5px; line-height: 22px; color: rgba(125, 107, 82, 0.8); }
.grank__rank.is-top { color: var(--u-orange); text-shadow: 0 0 8px rgba(194, 65, 12, 0.35); }
.grank__name { font-size: 11.5px; line-height: 22px; color: var(--u-text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.grank__bar { height: 5px; background: rgba(120, 90, 50, 0.06); clip-path: polygon(2px 0, 100% 0, calc(100% - 2px) 100%, 0 100%); }
.grank__bar i {
  display: block; height: 100%;
  background: linear-gradient(to right, rgba(15, 118, 110, 0.35), var(--u-orange));
  box-shadow: 0 0 8px rgba(194, 65, 12, 0.3);
  transition: width 1.1s cubic-bezier(0.16, 0.84, 0.44, 1);
}
.grank__score { font-family: var(--u-font-tech); font-size: 12px; line-height: 22px; font-weight: 700; color: var(--u-orange); text-align: right; font-variant-numeric: tabular-nums; }
.grank__n { font-size: 9.5px; line-height: 22px; color: rgba(125, 107, 82, 0.85); text-align: right; }

.grank__empty { flex: 1; display: grid; place-items: center; font-size: 12px; color: var(--u-text-2); }
</style>
