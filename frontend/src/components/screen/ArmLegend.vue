<!--
  口碑星图展厅 · 左下「旋臂图鉴」
  ============================================================
  星图里每条旋臂对应一个电影类型，但光看图不知道哪条是哪条。
  这张卡把六条旋臂列出来：类型名 / 影片数 / 均分 / 占比条。
  悬停某一行，行内亮点会轻轻呼吸（和星图的呼吸节奏一致）。
  数据：热门影片的 genres_zh 首字段（与 GalaxyStage 同口径）。
-->
<template>
  <div class="arm float-card">
    <div class="arm__head">
      <span class="arm__zh">旋臂图鉴</span>
      <span class="arm__en">ARMS</span>
    </div>
    <div class="arm__list">
      <div
        v-for="(g, i) in rows"
        :key="g.name"
        class="arm__row"
        :style="{ animationDelay: `${i * 60}ms` }"
        :title="`${g.name}：${g.count} 部，均分 ${g.avg.toFixed(1)}`"
      >
        <i class="arm__dot" :style="{ background: g.color, boxShadow: `0 0 8px ${g.color}66` }" />
        <span class="arm__name">{{ g.name }}</span>
        <span class="arm__bar"><i :style="{ width: drawn ? g.pct + '%' : '0%', background: g.color }" /></span>
        <span class="arm__n">{{ g.count }}</span>
        <span class="arm__avg">{{ g.avg.toFixed(1) }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
// ============================================================
// 旋臂图鉴：类型 → 影片数 / 均分 / 占比
// ============================================================
import { computed, onMounted, ref } from 'vue'

const props = defineProps({
  movies: { type: Array, default: () => [] },
})

const drawn = ref(false)
onMounted(() => requestAnimationFrame(() => { drawn.value = true }))

/* 纸面友好的六色：棕 / 橙 / 青 / 金 / 紫 / 蓝，都和暖白底能拉开 */
const COLORS = ['#C2410C', '#0F766E', '#A67C2E', '#6D28D9', '#4A7FB5', '#8B4513']

const rows = computed(() => {
  const m = new Map()
  for (const mv of props.movies || []) {
    const g = (mv.genres_zh || [])[0]
    if (!g) continue
    const cur = m.get(g) || { name: g, count: 0, sum: 0 }
    cur.count += 1
    cur.sum += Number(mv.rating) || 0
    m.set(g, cur)
  }
  const list = [...m.values()].sort((a, b) => b.count - a.count).slice(0, 6)
  const max = Math.max(1, ...list.map((g) => g.count))
  return list.map((g, i) => ({
    ...g,
    avg: g.count ? g.sum / g.count : 0,
    pct: (g.count / max) * 100,
    color: COLORS[i % COLORS.length],
  }))
})
</script>

<style scoped>
.arm {
  padding: 10px 13px 11px;
  background: linear-gradient(178deg, rgba(253, 251, 244, 0.95), rgba(247, 241, 227, 0.92));
}
.arm__head { display: flex; align-items: baseline; gap: 7px; padding-bottom: 6px; border-bottom: 1px solid rgba(58, 46, 32, 0.32); }
.arm__zh { font-size: 12px; font-weight: 700; color: var(--u-orange-deep, #8B4513); letter-spacing: 0.14em; }
.arm__en { font-family: var(--u-font-tech, "Orbitron"), sans-serif; font-size: 8px; letter-spacing: 0.18em; color: rgba(125, 107, 82, 0.75); }

.arm__list { display: flex; flex-direction: column; padding-top: 2px; }
.arm__row {
  display: grid; grid-template-columns: 7px 44px 1fr 22px 26px; align-items: center; gap: 6px;
  padding: 3px 0; border-bottom: 1px solid rgba(58, 46, 32, 0.1);
  animation: arm-in 0.5s ease backwards;
  transition: padding-left 0.2s ease;
}
.arm__row:last-child { border-bottom: 0; }
.arm__row:hover { padding-left: 3px; }
@keyframes arm-in { from { opacity: 0; transform: translateX(-6px); } to { opacity: 1; transform: none; } }

.arm__dot { width: 7px; height: 7px; border-radius: 50%; animation: arm-pulse 2.6s ease-in-out infinite; }
.arm__row:nth-child(2) .arm__dot { animation-delay: 0.35s; }
.arm__row:nth-child(3) .arm__dot { animation-delay: 0.7s; }
.arm__row:nth-child(4) .arm__dot { animation-delay: 1.05s; }
.arm__row:nth-child(5) .arm__dot { animation-delay: 1.4s; }
.arm__row:nth-child(6) .arm__dot { animation-delay: 1.75s; }
@keyframes arm-pulse { 0%, 100% { opacity: 1; transform: scale(1); } 50% { opacity: 0.55; transform: scale(0.82); } }

.arm__name { font-size: 12px; font-weight: 600; color: var(--u-text, #3A2E20); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.arm__bar { height: 5px; border-radius: 3px; background: rgba(154, 96, 40, 0.2); overflow: hidden; }
.arm__bar i { display: block; height: 100%; border-radius: 3px; transition: width 0.9s cubic-bezier(0.22, 1, 0.36, 1); }
.arm__n { font-family: var(--u-font-tech, "Orbitron"), sans-serif; font-size: 11px; font-weight: 600; color: #5D4E38; text-align: right; }
.arm__avg { font-family: var(--u-font-tech, "Orbitron"), sans-serif; font-size: 11px; font-weight: 700; color: #8B4513; text-align: right; }

@media (prefers-reduced-motion: reduce) {
  .arm__row { animation: none; }
  .arm__dot { animation: none; }
  .arm__bar i { transition: none; }
}
</style>
