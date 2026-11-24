<!--
  口碑排名展厅 · 底部左卡「导演口碑榜」
  ============================================================
  主图看的是"类型位次怎么变"，这张卡回答"谁在稳定地拍好片"：
  按导演聚合热门影片（至少 2 部），算均分与作品数，均分高者在前。
  纯 DOM 条形榜：hover / 逐条入场动画比 canvas 更顺手。
  数据：/search/movies 拉回的热门影片（真实字段 director / rating / votes）。
-->
<template>
  <div class="dirb">
    <div class="dirb__head">
      <span class="dirb__zh">导演口碑榜</span>
      <span class="dirb__en">AT LEAST 2 FILMS</span>
      <span class="dirb__note">{{ total }} 位导演</span>
    </div>

    <div class="dirb__list">
      <div
        v-for="(d, i) in rows"
        :key="d.name"
        class="dirb__row"
        :style="{ animationDelay: `${i * 55}ms` }"
        :title="`${d.name}：${d.count} 部作品，均分 ${d.avg.toFixed(2)}`"
      >
        <span class="dirb__rank" :class="{ 'is-top': i < 3 }">{{ String(i + 1).padStart(2, '0') }}</span>
        <span class="dirb__name">{{ d.name }}</span>
        <span class="dirb__bar"><i :style="{ width: drawn ? d.pct + '%' : '0%' }" /></span>
        <span class="dirb__avg">{{ d.avg.toFixed(1) }}</span>
        <span class="dirb__n">{{ d.count }} 部</span>
      </div>
    </div>

    <p v-if="!rows.length" class="dirb__empty">影片数据加载中…</p>
  </div>
</template>

<script setup>
// ============================================================
// 导演口碑榜：按导演聚合，均分排序，至少 2 部作品
// ============================================================
import { computed, onMounted, ref } from 'vue'

const props = defineProps({
  movies: { type: Array, default: () => [] },
})

const drawn = ref(false)
onMounted(() => requestAnimationFrame(() => { drawn.value = true }))

const groups = computed(() => {
  const m = new Map()
  for (const mv of props.movies || []) {
    const name = (mv.director || '').trim()
    const rating = Number(mv.rating)
    if (!name || !rating) continue
    const g = m.get(name) || { name, sum: 0, count: 0, votes: 0 }
    g.sum += rating
    g.count += 1
    g.votes += Number(mv.votes) || 0
    m.set(name, g)
  }
  return [...m.values()]
    .filter((g) => g.count >= 2)
    .map((g) => ({ name: g.name, avg: g.sum / g.count, count: g.count, votes: g.votes }))
    .sort((a, b) => b.avg - a.avg || b.count - a.count)
})

const total = computed(() => groups.value.length)

const rows = computed(() => {
  const list = groups.value.slice(0, 8)
  const max = Math.max(1, ...list.map((d) => d.avg))
  return list.map((d) => ({ ...d, pct: (d.avg / max) * 100 }))
})
</script>

<style scoped>
.dirb { display: flex; flex-direction: column; height: 100%; min-height: 0; }
.dirb__head {
  display: flex; align-items: baseline; gap: 9px; flex: none;
  padding-bottom: 6px; border-bottom: 1px solid rgba(58, 46, 32, 0.32);
}
.dirb__zh { font-size: 12px; font-weight: 700; color: var(--u-text, #3A2E20); letter-spacing: 0.14em; }
.dirb__en { font-family: var(--u-font-tech, "Orbitron"), sans-serif; font-size: 8px; letter-spacing: 0.16em; color: rgba(125, 107, 82, 0.75); }
.dirb__note { margin-left: auto; font-size: 9.5px; color: var(--u-gold, #A67C2E); font-weight: 600; white-space: nowrap; }

.dirb__list { flex: 1; min-height: 0; display: flex; flex-direction: column; justify-content: space-around; overflow: auto; }
.dirb__row {
  display: grid; grid-template-columns: 22px 1fr 64px 28px 32px; align-items: center; gap: 8px;
  height: 22px; padding: 0;
  border-bottom: 1px solid rgba(58, 46, 32, 0.1);
  animation: dirb-fade 0.5s ease backwards;
  transition: padding-left 0.2s ease;
}
.dirb__row:last-child { border-bottom: 0; }
.dirb__row:hover { padding-left: 3px; }
.dirb__row:hover .dirb__name { color: #C2410C; }
@keyframes dirb-fade { from { opacity: 0; transform: translateY(7px); } to { opacity: 1; transform: none; } }

.dirb__rank { font-family: var(--u-font-tech, "Orbitron"), sans-serif; font-size: 9.5px; color: rgba(125, 107, 82, 0.8); }
.dirb__rank.is-top { color: #C2410C; }
.dirb__name { font-size: 11px; color: var(--u-text, #3A2E20); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; transition: color 0.2s ease; }
/* 比例只留一条 2px 细线，和票房页账簿同一语言 */
.dirb__bar { height: 2px; background: rgba(154, 96, 40, 0.1); }
.dirb__bar i { display: block; height: 100%; background: linear-gradient(90deg, rgba(15, 118, 110, 0.45), #C2410C); transition: width 0.9s cubic-bezier(0.22, 1, 0.36, 1); }
.dirb__avg { font-family: var(--u-font-tech, "Orbitron"), sans-serif; font-size: 11.5px; font-weight: 700; color: #8B4513; text-align: right; font-variant-numeric: tabular-nums; }
.dirb__n { font-size: 9px; color: rgba(125, 107, 82, 0.85); text-align: right; }
.dirb__empty { font-size: 11.5px; color: var(--u-text-2, #7D6B52); padding: 12px 4px; }

@media (prefers-reduced-motion: reduce) {
  .dirb__row { animation: none; }
  .dirb__bar i { transition: none; }
}
</style>
