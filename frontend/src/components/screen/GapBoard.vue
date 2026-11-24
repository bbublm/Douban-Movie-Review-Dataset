<!--
  口碑分歧展厅 · 右栏底卡「平台分歧榜」
  ============================================================
  参考 A24 的元数据表：发丝线分行、标签极小、数字右对齐，没有彩色胶囊。
  每一行仍保留两条 2px 细轨（青 = TMDB，橙 = 豆瓣），共用 0–10 刻度；
  差值作为右端的一个数字，不喧哗。
  数据：/douban/insights 的 rating_divergence（库内 173 部双平台有评分）。
-->
<template>
  <div class="gapb">
    <header class="gapb__head">
      <span class="gapb__zh">平台分歧榜</span>
      <em class="gapb__en">TMDB vs DOUBAN</em>
      <span class="gapb__note">平均差 {{ avgAbs }}</span>
    </header>

    <p class="gapb__counts">
      豆瓣更高 <b>{{ counts.up }}</b><i />
      基本一致 <b>{{ counts.flat }}</b><i />
      TMDB 更高 <b>{{ counts.down }}</b>
    </p>

    <div class="gapb__list">
      <div
        v-for="(d, i) in rows"
        :key="d.movie_id"
        class="gapb__row"
        :style="{ animationDelay: `${i * 40}ms` }"
        :title="`${d.title}：TMDB ${d.tmdb_rating} / 豆瓣 ${d.douban_rating}`"
        @click="open(d.movie_id)"
      >
        <span class="gapb__rank" :class="{ 'is-top': i < 3 }">{{ String(i + 1).padStart(2, '0') }}</span>
        <b class="gapb__title">{{ d.title }}</b>
        <span class="gapb__bar">
          <i :class="d.gap > 0 ? 'is-up' : 'is-down'" :style="{ width: barPct(d) + '%' }" />
        </span>
        <span class="gapb__nums">
          <b>{{ d.tmdb_rating }}</b><i>/</i><b>{{ d.douban_rating }}</b>
        </span>
        <em class="gapb__gap" :class="d.gap > 0 ? 'is-up' : 'is-down'">{{ d.gap > 0 ? '+' : '' }}{{ d.gap }}</em>
      </div>
    </div>
  </div>
</template>

<script setup>
// ============================================================
// 平台分歧榜：按 |gap| 倒序，双轨对比
// ============================================================
import { computed } from 'vue'
import { useRouter } from 'vue-router'

const props = defineProps({
  divergence: { type: Array, default: () => [] },
})

const router = useRouter()

function open(id) {
  if (id) router.push(`/movie/${id}`)
}

const sorted = computed(() => (props.divergence || [])
  .filter((d) => d && d.tmdb_rating != null && d.douban_rating != null)
  .slice()
  .sort((a, b) => Math.abs(b.gap) - Math.abs(a.gap)))

const rows = computed(() => sorted.value.slice(0, 7))

const counts = computed(() => {
  let up = 0, down = 0, flat = 0
  for (const d of sorted.value) {
    if (d.gap > 0.5) up++
    else if (d.gap < -0.5) down++
    else flat++
  }
  return { up, down, flat }
})

const avgAbs = computed(() => {
  const list = sorted.value
  if (!list.length) return '—'
  return (list.reduce((acc, d) => acc + Math.abs(d.gap), 0) / list.length).toFixed(2)
})

/* 单行版：条形只表达"差值有多大"，颜色区分谁更高 */
const maxGap = computed(() => Math.max(0.1, ...rows.value.map((d) => Math.abs(d.gap))))
const barPct = (d) => Math.max(4, (Math.abs(d.gap) / maxGap.value) * 100)
</script>

<style scoped>
.gapb { display: flex; flex-direction: column; height: 100%; min-height: 0; }
.gapb__head {
  display: flex; align-items: baseline; gap: 9px; flex: none;
  padding-bottom: 6px; border-bottom: 1px solid rgba(58, 46, 32, 0.32);
}
.gapb__zh { font-size: 12px; font-weight: 700; color: var(--u-text, #3A2E20); letter-spacing: 0.14em; }
.gapb__en { font-family: var(--u-font-tech, "Orbitron"), sans-serif; font-size: 8px; letter-spacing: 0.16em; color: rgba(125, 107, 82, 0.75); }
.gapb__note { margin-left: auto; font-size: 9.5px; font-weight: 600; color: var(--u-gold, #A67C2E); white-space: nowrap; }

/* 三档计数：一行小字，用竖细线分隔（不做彩色胶囊） */
.gapb__counts {
  flex: none; display: flex; align-items: center; gap: 8px;
  margin: 0; padding: 6px 0 5px;
  font-size: 9.5px; color: rgba(125, 107, 82, 0.9);
  border-bottom: 1px solid rgba(58, 46, 32, 0.1);
}
.gapb__counts b { font-family: var(--u-font-tech, "Orbitron"), sans-serif; font-size: 11px; color: #8B4513; }
.gapb__counts i { width: 1px; height: 9px; background: rgba(58, 46, 32, 0.18); }

.gapb__list { flex: 1; min-height: 0; overflow: auto; display: flex; flex-direction: column; }
.gapb__row {
  display: grid; grid-template-columns: 18px 1fr 56px 46px 32px; align-items: center; gap: 8px;
  padding: 4px 0;
  border-bottom: 1px solid rgba(58, 46, 32, 0.1);
  cursor: pointer;
  animation: gapb-in 0.45s ease backwards;
  transition: padding-left 0.2s ease;
}
.gapb__row:last-child { border-bottom: 0; }
.gapb__row:hover { padding-left: 3px; }
.gapb__row:hover .gapb__title { color: #C2410C; }
@keyframes gapb-in { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: none; } }

.gapb__rank { font-family: var(--u-font-tech, "Orbitron"), sans-serif; font-size: 9.5px; color: rgba(125, 107, 82, 0.8); }
.gapb__rank.is-top { color: #C2410C; }

.gapb__title {
  font-size: 11px; font-weight: 500; color: var(--u-text, #3A2E20);
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  transition: color 0.2s ease;
}
/* 单条差值细线：长度=差值大小，颜色=哪边更高 */
.gapb__bar { height: 3px; background: rgba(58, 46, 32, 0.08); }
.gapb__bar i { display: block; height: 100%; }
.gapb__bar i.is-up { background: linear-gradient(90deg, rgba(194, 65, 12, 0.45), #C2410C); }
.gapb__bar i.is-down { background: linear-gradient(90deg, rgba(15, 118, 110, 0.45), #0F766E); }

.gapb__nums { display: flex; align-items: baseline; justify-content: flex-end; gap: 2px; }
.gapb__nums i { font-style: normal; font-size: 9px; color: rgba(125, 107, 82, 0.6); }
.gapb__nums b {
  font-family: var(--u-font-tech, "Orbitron"), sans-serif;
  font-size: 10px; font-weight: 700; line-height: 1.2; font-variant-numeric: tabular-nums;
}
.gapb__nums b:first-child { color: #0F766E; }
.gapb__nums b:last-child { color: #C2410C; }

.gapb__gap {
  font-style: normal; text-align: right;
  font-family: var(--u-font-tech, "Orbitron"), sans-serif;
  font-size: 10px; font-weight: 700; font-variant-numeric: tabular-nums;
}
.gapb__gap.is-up { color: #C2410C; }
.gapb__gap.is-down { color: #0F766E; }

@media (prefers-reduced-motion: reduce) {
  .gapb__row { animation: none; }
}
</style>
