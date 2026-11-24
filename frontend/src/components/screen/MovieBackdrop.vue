<template>
  <!--
    ============================================================
    展厅背景 · 电影海报墙（用户 2026-11-02："背景用电影图片，这样就不会太单调"）
    ------------------------------------------------------------
    取库里带海报的影片，铺成一面柔焦海报墙：
      · 整墙统一 blur(5px)，既保留"这是电影海报"的辨识度，又不抢数据
      · 暖白纱罩 + 暗角压一层，保证纸卡上的文字对比度
      · position: fixed —— 数据页可以纵向滚动，背景墙保持不动（像影院幕布）
    ============================================================
  -->
  <div class="mbackdrop" aria-hidden="true">
    <div class="mbackdrop__wall">
      <span
        v-for="(m, i) in picks"
        :key="i"
        class="mbackdrop__cell"
        :style="m.poster_url ? { backgroundImage: `url('${m.poster_url}')` } : null"
      />
    </div>
    <div class="mbackdrop__veil" />
    <div class="mbackdrop__vignette" />
  </div>
</template>

<script setup>
// ============================================================
// 海报墙：从已加载的影片里等距抽 36 部带海报的，铺满 9 列
// （等距抽样而不是前 36 部，避免背景全是最热门的那几部、颜色单一）
// ============================================================
import { computed } from 'vue'

const props = defineProps({
  movies: { type: Array, default: () => [] },
})

const WANT = 36

const picks = computed(() => {
  const withPoster = (props.movies || []).filter((m) => m && m.poster_url)
  if (!withPoster.length) return []
  const step = Math.max(1, Math.floor(withPoster.length / WANT))
  const out = []
  for (let i = 0; i < withPoster.length && out.length < WANT; i += step) out.push(withPoster[i])
  return out
})
</script>

<style scoped>
.mbackdrop {
  position: fixed;
  inset: 0;
  z-index: 1;
  pointer-events: none;
  overflow: hidden;
  background: #EDE4D2;
}

/* 海报墙本体：9 列 × 4 行，四边多铺 6% 以免 blur 后露白边 */
.mbackdrop__wall {
  position: absolute;
  inset: -6%;
  display: grid;
  grid-template-columns: repeat(9, 1fr);
  grid-auto-rows: 1fr;
  gap: 8px;
  filter: blur(4px) saturate(1.1) brightness(0.98);
  opacity: 0.74;
  /* 滚动视差：海报墙相对内容轻微上移（--u-scroll 由 UniverseScreen 写入） */
  transform: translate3d(0, calc(var(--u-scroll, 0) * -0.05px), 0) scale(1.03);
}
.mbackdrop__cell {
  background-color: #D8CCB6;
  background-size: cover;
  background-position: center;
  border-radius: 4px;
}

/* 暖白纱罩：把海报压成"背景"，纸卡上的深字始终可读 */
.mbackdrop__veil {
  position: absolute;
  inset: 0;
  background:
    linear-gradient(180deg, rgba(246, 241, 230, 0.62) 0%, rgba(246, 241, 230, 0.44) 40%, rgba(246, 241, 230, 0.64) 100%),
    radial-gradient(74% 64% at 50% 40%, rgba(246, 241, 230, 0.26), rgba(246, 241, 230, 0.72) 100%);
}

/* 暗角：四周收一点，视线聚焦中间的数据 */
.mbackdrop__vignette {
  position: absolute;
  inset: 0;
  box-shadow: inset 0 0 240px 70px rgba(58, 46, 32, 0.16);
}

@media (max-width: 900px) {
  .mbackdrop__wall { grid-template-columns: repeat(5, 1fr); filter: blur(7px) saturate(1.02); opacity: 0.5; }
}
</style>
