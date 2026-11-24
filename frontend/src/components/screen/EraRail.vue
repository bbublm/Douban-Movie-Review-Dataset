<!--
  年代流向展厅 · 底部「年代胶片」
  ============================================================
  参考 justinesoulie.fr：物件直接摆在纸面上，文字只有极小号标注。
  这里每个年代是一栏：一个大号年代数字 + 三张代表作海报 + 一行统计，
  栏与栏之间用发丝线分隔，像一张摊开的接触印相纸。

  交互同 a24：滚轮在栏上 → 横向漂移；按住拖动 → 直接拖；到头自动交还页面滚动。
  数据：/search/movies 热门影片按年代分组，取该年代评分最高的 3 部。
-->
<template>
  <div class="erail">
    <header class="erail__head">
      <span class="erail__zh">年代胶片</span>
      <em class="erail__en">EACH DECADE, IN FRAMES</em>
      <span class="erail__hint">滚轮 / 拖动 横向浏览</span>
      <div class="erail__nav">
        <button type="button" aria-label="向左" @click="scrollBy(-1)">‹</button>
        <button type="button" aria-label="向右" @click="scrollBy(1)">›</button>
      </div>
    </header>

    <div ref="strip" class="erail__strip">
      <div v-for="(g, gi) in groups" :key="g.decade" class="erail__group" :style="{ animationDelay: `${gi * 70}ms` }">
        <div class="erail__yr">
          <b>{{ g.decade }}</b><em>s</em>
          <span class="erail__stat">{{ g.count }} 部 · 均分 {{ g.avg.toFixed(1) }}</span>
        </div>
        <div class="erail__frames">
          <RouterLink
            v-for="(m, i) in g.movies"
            :key="m.movie_id"
            class="erail__frame"
            :to="`/movie/${m.movie_id}`"
            :style="{ animationDelay: `${gi * 70 + i * 40}ms` }"
            :title="`${m.title}（${m.year || g.decade}）· ${m.rating}`"
          >
            <img v-if="m.poster_url" :src="m.poster_url" :alt="m.title" loading="lazy" draggable="false" />
            <span class="erail__cap">
              <b>{{ m.title }}</b>
              <i>{{ m.rating }}</i>
            </span>
          </RouterLink>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
// ============================================================
// 年代胶片：按年代分组，取代表作 3 部，横滑浏览（滚轮漂移 + 拖动）
// ============================================================
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRailDrift } from '../../composables/useRailDrift'

const props = defineProps({
  movies: { type: Array, default: () => [] },
})

const strip = ref(null)
const drift = useRailDrift(strip, { ratio: 1.1 })
onMounted(() => drift.bind())
onBeforeUnmount(() => drift.unbind())

function scrollBy(dir) {
  const el = strip.value
  if (el) el.scrollBy({ left: dir * Math.max(260, el.clientWidth * 0.6), behavior: 'smooth' })
}

const groups = computed(() => {
  const m = new Map()
  for (const mv of props.movies || []) {
    const y = Number(mv.year)
    if (!y) continue
    const dec = Math.floor(y / 10) * 10
    const g = m.get(dec) || { decade: dec, list: [], sum: 0, count: 0 }
    g.list.push(mv)
    g.sum += Number(mv.rating) || 0
    g.count += 1
    m.set(dec, g)
  }
  return [...m.values()]
    .filter((g) => g.count >= 2)
    .sort((a, b) => a.decade - b.decade)
    .map((g) => ({
      decade: g.decade,
      count: g.count,
      avg: g.sum / g.count,
      movies: g.list
        .filter((x) => x.poster_url)
        .sort((a, b) => Number(b.rating) - Number(a.rating) || Number(b.votes) - Number(a.votes))
        .slice(0, 4),
    }))
    .filter((g) => g.movies.length)
})
</script>

<style scoped>
.erail { display: flex; flex-direction: column; height: 100%; min-height: 0; }
.erail__head {
  display: flex; align-items: baseline; gap: 9px; flex: none;
  padding-bottom: 6px; border-bottom: 1px solid rgba(58, 46, 32, 0.32);
}
.erail__zh { font-size: 12px; font-weight: 700; color: var(--u-text, #3A2E20); letter-spacing: 0.14em; }
.erail__en { font-family: var(--u-font-tech, "Orbitron"), sans-serif; font-size: 8px; letter-spacing: 0.18em; color: rgba(125, 107, 82, 0.75); }
.erail__hint { margin-left: auto; font-size: 9.5px; color: rgba(125, 107, 82, 0.8); }
.erail__nav { display: flex; gap: 3px; margin-left: 6px; }
.erail__nav button {
  width: 18px; height: 18px; display: grid; place-items: center; font-size: 12px; line-height: 1;
  cursor: pointer; color: #6B4E2E; background: transparent;
  border: 1px solid rgba(107, 78, 46, 0.32); border-radius: 50%;
  transition: background 0.18s ease, color 0.18s ease;
}
.erail__nav button:hover { background: #8B4513; color: #FFF6E9; border-color: #8B4513; }

/* 纸面上的接触印相：无底色，只有发丝分隔线 */
.erail__strip {
  flex: 1; min-height: 0;
  display: flex; align-items: stretch; gap: 0;
  overflow-x: auto; overflow-y: hidden;
  padding: 10px 2px 2px;
  scrollbar-width: none;
  cursor: grab;
}
.erail__strip::-webkit-scrollbar { display: none; }
.erail__strip.is-dragging { cursor: grabbing; }

.erail__group {
  flex: none;
  display: flex; flex-direction: column; gap: 7px;
  padding: 0 16px;
  border-left: 1px solid rgba(58, 46, 32, 0.14);
  animation: erail-in 0.55s cubic-bezier(0.16, 0.84, 0.44, 1) backwards;
}
.erail__group:first-child { border-left: 0; padding-left: 2px; }
@keyframes erail-in { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: none; } }

.erail__yr { display: flex; align-items: baseline; gap: 3px; }
.erail__yr b {
  font-family: var(--u-font-tech, "Orbitron"), sans-serif;
  font-size: 19px; font-weight: 800; letter-spacing: 0.02em; color: #8B4513;
  font-variant-numeric: tabular-nums;
}
.erail__yr em { font-style: normal; font-size: 9px; color: rgba(125, 107, 82, 0.8); margin-right: 8px; }
.erail__stat { font-size: 9px; color: rgba(125, 107, 82, 0.85); }

.erail__frames { flex: 1; min-height: 0; display: flex; gap: 7px; }
.erail__frame {
  position: relative; display: block; width: 62px; min-height: 0;
  overflow: hidden; text-decoration: none; background: #EFE4D2;
  border-radius: 2px;
  box-shadow: 0 5px 12px rgba(74, 40, 20, 0.16);
  animation: erail-in 0.5s ease backwards;
  transition: transform 0.32s cubic-bezier(0.16, 0.84, 0.44, 1), box-shadow 0.32s ease;
}
.erail__frame img { width: 100%; height: 100%; object-fit: cover; display: block; pointer-events: none; }
.erail__frame:hover {
  transform: translateY(-6px) rotate(-1.4deg);
  box-shadow: 0 14px 22px rgba(74, 40, 20, 0.26);
  z-index: 2;
}
.erail__frame:nth-child(even):hover { transform: translateY(-6px) rotate(1.4deg); }

.erail__cap {
  position: absolute; inset: auto 0 0 0;
  display: flex; flex-direction: column;
  padding: 14px 4px 4px;
  background: linear-gradient(to top, rgba(30, 22, 14, 0.88), rgba(30, 22, 14, 0));
  opacity: 0; transform: translateY(5px);
  transition: opacity 0.22s ease, transform 0.22s ease;
}
.erail__frame:hover .erail__cap { opacity: 1; transform: none; }
.erail__cap b {
  font-size: 8.5px; font-weight: 700; line-height: 1.25; color: #FFF6E9;
  display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;
}
.erail__cap i { font-style: normal; font-family: var(--u-font-tech, "Orbitron"), sans-serif; font-size: 8px; color: #F0B860; }

@media (max-width: 900px) {
  .erail__frame { width: 50px; }
  .erail__hint { display: none; }
}
@media (prefers-reduced-motion: reduce) {
  .erail__group, .erail__frame { animation: none; }
  .erail__frame:hover { transform: none; }
}
</style>
