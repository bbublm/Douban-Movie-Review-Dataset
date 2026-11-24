<template>
  <!--
    ============================================================
    口碑排名展厅 · 编辑式排版（参考 A24 编辑页：大图主导 + 侧栏精选）
    ------------------------------------------------------------
    与"左中右三块"不同：这里是一张占满主区的口碑变化大图（BumpChart），
    右上一块窄卡做「编辑精选 · 豆瓣口碑」，像杂志的副栏。两卡都用
    手绘纸框 + 硬阴影，直接铺在暖白纸面上（不含左右两翼）。
    ============================================================
  -->
  <div ref="root" class="rank-room" v-sketch="{ sel:'.room-hero, .float-card', stagger:0.07, maxDelay:0.9 }">
    <RoomHero
      icon="📈"
      kicker="Word of Mouth"
      title="口碑排名"
      en="Who climbed, who slipped"
      lead="各类型口碑的位次变化、登顶与跌落——谁在十年里稳居神坛，谁又悄悄滑出榜单。"
      :tags="['口碑变迁', '编辑精选', '类型雷达']"
      :stats="heroStats"
    />
    <RoomSection no="01" zh="口碑位次的十年" en="A Decade of Climbs"
      lead="一条曲线是一个类型：谁一路登顶，谁在十年里悄悄滑出榜单。右侧是编辑精选与类型榜。" />

    <div class="rr__grid">
      <section class="rr__main float-card">
        <BumpChart :matrix="matrix" />
      </section>
      <aside class="rr__side float-card">
        <div class="rr__side-h">编辑精选 · 豆瓣口碑</div>
        <div class="rr__side-body">
          <DoubanPanel :douban="douban" />
        </div>
        <div class="rr__side-h rr__side-h--2">类型口碑榜</div>
        <div class="rr__side-body rr__side-body--2">
          <GenreRankCard :by-genre="sentiment?.by_genre || []" />
        </div>
      </aside>

      <!-- 底部：导演口碑榜 + 高分片单（补足"数据要多一点"） -->
      <div class="rr__bottom u-reveal">
        <section class="float-card rr__cell">
          <DirectorBoard :movies="movies" />
        </section>
        <section class="float-card rr__cell">
          <PosterRail :movies="movies" />
        </section>
      </div>
    </div>

    <RoomSection no="02" zh="类型的多维画像" en="Genre Profiles · Radar"
      lead="把口碑、热度、产量、评分稳定性摊到一张雷达上，看清每个类型的性格。" />

    <!-- 第四层：类型多维画像雷达（5 个维度由后端现算，可放大细读） -->
    <section class="rr__deep u-reveal" style="--d:.1s">
      <GenreRadarPanel :correlations="correlations" />
    </section>
  </div>
</template>

<script setup>
// ============================================================
// 口碑排名：主图（BumpChart） + 侧栏精选（DoubanPanel + 类型口碑榜）
//            + 底部（导演口碑榜 / 高分片单）
// ============================================================
import { computed, ref } from 'vue'
import BumpChart from './BumpChart.vue'
import DoubanPanel from './DoubanPanel.vue'
import GenreRankCard from './GenreRankCard.vue'
import DirectorBoard from './DirectorBoard.vue'
import PosterRail from './PosterRail.vue'
import GenreRadarPanel from './GenreRadarPanel.vue'
import RoomHero from './RoomHero.vue'
import RoomSection from './RoomSection.vue'
import { useReveal } from '../../composables/useReveal.js'

const root = ref(null)
useReveal(root)

const props = defineProps({
  matrix: { type: Object, default: null },
  douban: { type: Object, default: null },
  sentiment: { type: Object, default: null },
  movies: { type: Array, default: () => [] },
  correlations: { type: Object, default: null },
  movieTotal: { type: Number, default: 0 },
  reviewTotal: { type: Number, default: 0 },
})

const heroStats = computed(() => [
  { value: props.movieTotal || 0, label: '收录影片' },
  { value: props.reviewTotal || 0, label: '影评总数' },
  { value: props.sentiment?.by_genre?.length || 0, label: '口碑类型维度' },
])
</script>

<style scoped>
/* 2026-11-06 大调整：height:auto + 明确分层，避免 flex:1 子项在
   父级 auto 高度里塌缩（历史坑：rank 侧栏曾被压成 88px） */
.rank-room {
  height: auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 20px;
}
/* rr__deep 移出栅格改由 flex 独占一行（配合章节标题），
   栅格从 3 行收成 2 行，主图多吃一行空间 */
.rr__grid {
  flex: 0 0 auto;
  height: clamp(700px, 84vh, 880px);
  min-height: 0;
  display: grid;
  grid-template-columns: 1fr 320px;
  grid-template-rows: minmax(0, 1fr) clamp(222px, 26vh, 250px);
  gap: 20px;
}
.rr__main { grid-column: 1; grid-row: 1; min-height: 0; overflow: hidden; }

.rr__side {
  grid-column: 2;
  grid-row: 1 / span 2;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

/* 底部两块：导演榜 + 高分片单 */
.rr__bottom {
  grid-column: 1;
  grid-row: 2;
  min-height: 0;
  display: grid;
  grid-template-columns: 1.02fr 1fr;
  gap: 14px;
}
.rr__cell { min-height: 0; overflow: hidden; padding: 10px 14px; }
.rr__deep { flex: 0 0 clamp(232px, 27vh, 272px); min-height: 0; }
.rr__side-h {
  flex: none;
  font-size: 12.5px;
  font-weight: 700;
  color: var(--u-text);
  letter-spacing: 1px;
  padding-bottom: 4px;
  margin-bottom: 3px;
  border-bottom: 1px solid rgba(194, 65, 12, 0.22);
}
.rr__side-h--2 { margin-top: 5px; }
/* 两卡都含 8 行列表：缩紧两节标题的留白（省出 ~19px 给列表），
   再按 1.32 / 1.0 分配 —— 两份都刚好够高，确保两张榜 8 行完整露出 */
.rr__side-body { flex: 1.32 1 0; min-height: 0; overflow: auto; }
.rr__side-body--2 { flex: 1 1 0; min-height: 0; overflow: auto; }

@media (max-width: 1180px) {
  .rr__grid { grid-template-columns: 1fr 260px; }
}
</style>
