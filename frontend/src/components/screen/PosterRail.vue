<!--
  口碑排名展厅 · 底部右卡「高分片单」
  ============================================================
  参考 justinesoulie.fr 的做法：不做卡片，直接把海报当成物件摆在纸面上，
  物件下面只有一行小字（片名 / 年份·类型），留白占大头。

  交互（参考 a24.raviklaassens.com 的光盘轨道）：
    · 滚轮在轨道上 → 海报横向漂移，滚到尽头自动把滚动交还页面
    · 按住拖动 → 直接拖动画布（位移 > 6px 会吞掉这次点击，避免误跳详情）
  数据：/search/movies 热门影片，按评分倒序、票数过滤水片。
-->
<template>
  <div class="prail">
    <header class="prail__head">
      <span class="prail__zh">高分片单</span>
      <em class="prail__en">TOP RATED</em>
      <span class="prail__hint">滚轮 / 拖动 横向浏览 · 点海报看详情</span>
      <div class="prail__nav">
        <button type="button" aria-label="向左" @click="scrollBy(-1)">‹</button>
        <button type="button" aria-label="向右" @click="scrollBy(1)">›</button>
      </div>
    </header>

    <div ref="rail" class="prail__track">
      <RouterLink
        v-for="(m, i) in rows"
        :key="m.movie_id"
        class="prail__card"
        :to="`/movie/${m.movie_id}`"
        :style="{ animationDelay: `${i * 45}ms` }"
      >
        <span class="prail__poster">
          <img v-if="m.poster_url" :src="m.poster_url" :alt="m.title" loading="lazy" draggable="false" />
          <i v-else class="prail__noimg">{{ m.title.slice(0, 4) }}</i>
          <b class="prail__score">{{ Number(m.rating).toFixed(1) }}</b>
        </span>
        <span class="prail__title">{{ m.title }}</span>
        <span class="prail__meta">{{ m.year || '—' }} · {{ genreOf(m) }}</span>
      </RouterLink>
    </div>

    <p v-if="!rows.length" class="prail__empty">影片数据加载中…</p>
  </div>
</template>

<script setup>
// ============================================================
// 高分片单：悬浮海报条（滚轮漂移 + 按住拖动）
// ============================================================
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRailDrift } from '../../composables/useRailDrift'

const props = defineProps({
  movies: { type: Array, default: () => [] },
})

const rail = ref(null)
const drift = useRailDrift(rail, { ratio: 1.2 })
onMounted(() => drift.bind())
onBeforeUnmount(() => drift.unbind())

function scrollBy(dir) {
  const el = rail.value
  if (el) el.scrollBy({ left: dir * Math.max(220, el.clientWidth * 0.7), behavior: 'smooth' })
}

/* 评分优先、票数做次级排序；票数 < 200 的不上墙（避免 1 人打 10 分） */
const rows = computed(() => (props.movies || [])
  .filter((m) => Number(m.rating) > 0 && Number(m.votes || 0) >= 200 && m.poster_url)
  .sort((a, b) => Number(b.rating) - Number(a.rating) || Number(b.votes) - Number(a.votes))
  .slice(0, 12))

const genreOf = (m) => (m.genres_zh || [])[0] || '电影'
</script>

<style scoped>
.prail { display: flex; flex-direction: column; height: 100%; min-height: 0; }

/* 极小号标签 + 一条发丝线，和 A24 的栏目头一致 */
.prail__head {
  display: flex; align-items: baseline; gap: 9px; flex: none;
  padding-bottom: 6px; border-bottom: 1px solid rgba(58, 46, 32, 0.32);
}
.prail__zh { font-size: 12px; font-weight: 700; color: var(--u-text, #3A2E20); letter-spacing: 0.14em; }
.prail__en {
  font-family: var(--u-font-tech, "Orbitron"), sans-serif;
  font-size: 8px; letter-spacing: 0.18em; color: rgba(125, 107, 82, 0.75);
}
.prail__hint { margin-left: auto; font-size: 9.5px; color: rgba(125, 107, 82, 0.8); }
.prail__nav { display: flex; gap: 3px; margin-left: 6px; }
.prail__nav button {
  width: 18px; height: 18px; display: grid; place-items: center;
  font-size: 12px; line-height: 1; cursor: pointer; color: #6B4E2E;
  background: transparent; border: 1px solid rgba(107, 78, 46, 0.32); border-radius: 50%;
  transition: background 0.18s ease, color 0.18s ease;
}
.prail__nav button:hover { background: #8B4513; color: #FFF6E9; border-color: #8B4513; }

/* 轨道：纸面本身，不加底色；拖动时 cursor: grabbing */
.prail__track {
  flex: 1; min-height: 0;
  display: flex; align-items: flex-start; gap: 16px;
  padding: 12px 2px 4px;
  overflow-x: auto; overflow-y: hidden;
  scrollbar-width: none;
  cursor: grab;
  scroll-behavior: auto;
}
.prail__track::-webkit-scrollbar { display: none; }
.prail__track.is-dragging { cursor: grabbing; }

.prail__card {
  flex: none; width: 88px;
  display: flex; flex-direction: column; gap: 5px;
  text-decoration: none;
  transform-origin: 50% 100%;
  animation: prail-in 0.55s cubic-bezier(0.16, 0.84, 0.44, 1) backwards;
  transition: transform 0.32s cubic-bezier(0.16, 0.84, 0.44, 1), filter 0.32s ease;
  -webkit-user-select: none; user-select: none;
}
@keyframes prail-in { from { opacity: 0; transform: translateY(16px) scale(0.97); } to { opacity: 1; transform: none; } }

/* 悬停：像 A24 那样"物件被指尖抬起"，带一点倾斜与真实投影 */
.prail__card:hover { transform: translateY(-7px) rotate(-1.6deg); filter: drop-shadow(0 14px 18px rgba(74, 40, 20, 0.22)); }
.prail__card:nth-child(even):hover { transform: translateY(-7px) rotate(1.6deg); }

.prail__poster {
  position: relative; display: block; width: 100%; aspect-ratio: 2 / 3;
  overflow: hidden; background: #EFE4D2;
  border-radius: 2px;
  box-shadow: 0 6px 14px rgba(74, 40, 20, 0.18), 0 1px 0 rgba(255, 255, 255, 0.6) inset;
}
.prail__poster img { width: 100%; height: 100%; object-fit: cover; display: block; pointer-events: none; }
.prail__noimg {
  position: absolute; inset: 0; display: grid; place-items: center;
  font-family: "Kaiti SC", KaiTi, serif; font-style: normal; font-size: 12px; color: #6B4E2E;
}
/* 评分不做彩色胶囊，只用一行小字压在右下角（更接近参考站的克制） */
.prail__score {
  position: absolute; right: 5px; bottom: 4px;
  font-family: var(--u-font-tech, "Orbitron"), sans-serif;
  font-size: 11px; font-weight: 800; color: #FFF6E9;
  text-shadow: 0 1px 6px rgba(0, 0, 0, 0.75);
}
.prail__title {
  margin-top: 2px; font-size: 10.5px; line-height: 1.35; color: #3A2E20;
  display: -webkit-box; -webkit-line-clamp: 1; -webkit-box-orient: vertical; overflow: hidden;
}
.prail__meta { font-size: 9px; color: rgba(125, 107, 82, 0.85); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.prail__empty { font-size: 11.5px; color: var(--u-text-2, #7D6B52); padding: 12px 4px; }

@media (prefers-reduced-motion: reduce) {
  .prail__card { animation: none; transition: none; }
  .prail__card:hover { transform: none; }
}
</style>
