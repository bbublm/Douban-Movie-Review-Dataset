<template>
  <!--
    ============================================================
    口碑分歧展厅 · 编辑式对照跨页
    ------------------------------------------------------------
    2026-11-06 大调整修复：原根节点是 display:grid，Hero 没有显式网格定位，
    被自动布局挤到页面中部（首屏看不到标题）。改为 flex 纵向 + 内层 .dr__grid
    承载左右对照，Hero / 章节标题独占整行，恢复「封面 → 分章 → 展品」的节奏。
    左半 = 观众评分分化榜（A24 海报圆盘展）
    右半 = 分歧散点 + 豆瓣口碑 + 平台分歧榜
    ============================================================
    -->
  <div ref="root" class="diverge-room" v-sketch="{ sel:'.room-hero, .float-card', stagger:0.07, maxDelay:0.9 }">
    <RoomHero
      icon="⚖️"
      kicker="Two Platforms, One Film"
      title="口碑分歧"
      en="When scores disagree"
      lead="豆瓣的口碑，和这里统计的口碑，不一定一致。把两个平台的评分并排对照，看清哪些电影被一方偏爱、被另一方冷落。"
      :tags="['平台分歧', 'ROI 箱线', '评分断层']"
      :stats="heroStats"
    />

    <RoomSection no="01" zh="同一部片，两种口碑" en="One Film · Two Scores"
      lead="左边是被观众撕裂的影片，右边是两套评分体系的正面交锋。分数差得越多，越值得看一眼。" />

    <div class="dr__grid">
      <section class="dr__left float-card">
        <PolarizingBoard :polarizing="polarizing" />
      </section>
      <div class="dr__right">
        <section class="dr__cell float-card">
          <DivergenceChart :divergence="divergence" />
        </section>
        <section class="dr__cell dr__cell--dbp float-card">
          <div class="dr__cell-h">豆瓣口碑</div>
          <div class="dr__cell-body">
            <DoubanPanel :douban="douban" />
          </div>
        </section>
        <section class="dr__cell dr__cell--gap float-card">
          <GapBoard :divergence="divergence" />
        </section>
      </div>
    </div>

    <RoomSection no="02" zh="回报的四个分位" en="Return by Quartile"
      lead="同一类型里，票房回报能差多远？箱线把最低、四分位、中位与最高一次摊开。" />

    <!-- 第四层：各类型 ROI 四分位箱线（q1/中位/q3 由后端现算） -->
    <section class="dr__deep u-reveal">
      <RoiBoxPanel :correlations="correlations" />
    </section>
  </div>
</template>

<script setup>
// ============================================================
// 口碑分歧：左 = 分化榜（A24 圆盘展）；右 = 分歧散点 + 豆瓣口碑 + 平台分歧榜
// ============================================================
import { computed, ref } from 'vue'
import PolarizingBoard from './PolarizingBoard.vue'
import DivergenceChart from './DivergenceChart.vue'
import DoubanPanel from './DoubanPanel.vue'
import GapBoard from './GapBoard.vue'
import RoiBoxPanel from './RoiBoxPanel.vue'
import RoomHero from './RoomHero.vue'
import RoomSection from './RoomSection.vue'
import { useReveal } from '../../composables/useReveal.js'

const root = ref(null)
useReveal(root)

const props = defineProps({
  divergence: { type: Array, default: () => [] },
  polarizing: { type: Object, default: null },
  douban: { type: Object, default: null },
  correlations: { type: Object, default: null },
  movieTotal: { type: Number, default: 0 },
  reviewTotal: { type: Number, default: 0 },
})

const heroStats = computed(() => [
  { value: props.divergence?.length || 0, label: '分歧影片' },
  { value: props.movieTotal || 0, label: '收录影片' },
  { value: props.reviewTotal || 0, label: '影评总数' },
])
</script>

<style scoped>
/* 2026-11-06：height:auto + 明确分层，Hero / 章节独占整行，
   左右对照栅格给足高度，三块右栏卡片不再被压扁 */
.diverge-room {
  height: auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 20px;
}
/* 内层对照栅格：只装左右两块 */
.dr__grid {
  flex: 0 0 auto;
  height: clamp(720px, 86vh, 900px);
  min-height: 0;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 20px;
}
.dr__left { min-height: 0; overflow: hidden; }
.dr__deep { flex: 0 0 clamp(300px, 36vh, 380px); min-height: 0; }

.dr__right {
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 20px;
}
.dr__cell {
  flex: 1 1 0;
  min-height: 0;
  overflow: hidden;
  display: flex;
  flex-direction: column;
}
/* 豆瓣口碑卡（情感环 + 12 行高分榜）内容最高，给它约两倍竖向空间，
   散点图与分歧榜各占一份 —— 三块都不需要滚动就能看全 */
.dr__cell--dbp { flex: 1.95 1 0; }
/* 平台分歧榜：右栏底部，再补一块真实数据 */
.dr__cell--gap { flex: 1.02 1 0; }
.dr__cell-h {
  flex: none;
  font-size: 12.5px;
  font-weight: 700;
  color: var(--u-text);
  letter-spacing: 1px;
  padding-bottom: 8px;
  margin-bottom: 6px;
  border-bottom: 1px solid rgba(194, 65, 12, 0.22);
}
.dr__cell-body { flex: 1; min-height: 0; overflow: auto; }

@media (max-width: 900px) {
  .dr__grid { grid-template-columns: 1fr; }
}
</style>
