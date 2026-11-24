<template>
  <!--
    ============================================================
    年代流向展厅 · 上主图 + 下双栏（参考 itomdev 一张大图配两张副卡）
    ------------------------------------------------------------
    与"左中右三块"不同：上方一整张类型→年代桑基流向图为主视觉，下方并排两张
    手绘副卡——左「年代故事」（StoryTimeline）、右「地区画像」（RegionsPanel），
    像展览里的两块说明牌，不再塞进左右两翼。
    ============================================================
  -->
  <div ref="root" class="flow-room" v-sketch="{ sel:'.room-hero, .float-card', stagger:0.07, maxDelay:0.9 }">
    <RoomHero
      icon="🌊"
      kicker="Currents of Time"
      title="年代流向"
      en="Where genres drifted"
      lead="类型与年代之间的影片流向：哪些类型在新时代崛起，哪些慢慢退潮——一张桑基图讲完九十年的取舍。"
      :tags="['桑基流向', '年代胶片', '地区画像']"
      :stats="heroStats"
    />
    <RoomSection no="01" zh="类型与年代流向" en="Genre × Era Flow" lead="一张桑基图，看清类型如何在年代之间迁移、哪些类型在新时代崛起。" />
    <section class="fr__top float-card">
      <SankeyFlow :matrix="matrix" />
    </section>
    <RoomSection no="02" zh="年代故事 · 地区画像" en="Story · Regions" lead="每个年代的代表叙事，以及影片来自哪里。" />
    <div class="fr__bottom u-reveal">
      <section class="fr__cell float-card">
        <StoryTimeline :trends="trends" />
      </section>
      <section class="fr__cell float-card">
        <CoveragePanel :douban="douban" />
      </section>
      <section class="fr__cell float-card">
        <RegionsPanel :regions="regions" />
      </section>
    </div>

    <RoomSection no="03" zh="年代胶片" en="Era Reels" lead="每个年代的代表作，横滑回看九十年的银幕记忆。" />
    <!-- 底部：年代胶片（每个年代的代表作，横滑可看） -->
    <section class="fr__rail float-card">
      <EraRail :movies="movies" />
    </section>

    <RoomSection no="04" zh="三层流向 · 热力" en="Triple Flow · Heatmap" lead="类型→年代→口碑档的三层流向，叠加类型×年代均分热力。" />
    <!-- 第四层：类型→年代→口碑档三层桑基 + 类型×年代均分热力 -->
    <section class="fr__deep u-reveal" style="--d:.08s">
      <TripleFlowPanel :flows="flows" />
    </section>
  </div>
</template>

<script setup>
// ============================================================
// 年代流向：桑基主图 + 年代故事 / 预告覆盖 / 地区画像 三副卡 + 年代胶片
// ============================================================
import { computed, ref } from 'vue'
import SankeyFlow from './SankeyFlow.vue'
import StoryTimeline from './StoryTimeline.vue'
import CoveragePanel from './CoveragePanel.vue'
import RegionsPanel from './RegionsPanel.vue'
import EraRail from './EraRail.vue'
import TripleFlowPanel from './TripleFlowPanel.vue'
import RoomHero from './RoomHero.vue'
import RoomSection from './RoomSection.vue'
import { useReveal } from '../../composables/useReveal.js'

const root = ref(null)
useReveal(root)

const props = defineProps({
  matrix: { type: Object, default: null },
  trends: { type: Object, default: null },
  regions: { type: Object, default: null },
  douban: { type: Object, default: null },
  movies: { type: Array, default: () => [] },
  flows: { type: Object, default: null },
  movieTotal: { type: Number, default: 0 },
  reviewTotal: { type: Number, default: 0 },
})

const heroStats = computed(() => [
  { value: props.movieTotal || props.trends?.total_movies || 0, label: '收录影片' },
  { value: props.reviewTotal || 0, label: '影评总数' },
  { value: props.flows?.genres?.length || 0, label: '类型维度' },
])
</script>

<style scoped>
/* 2026-11-06 大调整：Hero/章节放大后，原来 flex:1 的桑基主图被压成扁条。
   改为 height:auto + 每层明确高度，长页按内容自然舒展，图表不再被挤压。 */
.flow-room {
  height: auto;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 20px;
}
.fr__top {
  flex: 0 0 clamp(400px, 48vh, 520px);
  min-height: 0;
  overflow: hidden;
}
.fr__bottom {
  flex: 0 0 clamp(300px, 36vh, 380px);
  min-height: 0;
  display: grid;
  grid-template-columns: 1fr 1fr 1fr;
  gap: 20px;
}
.fr__cell { min-height: 0; overflow: auto; }

/* 年代胶片：纸面接触印相条，固定高度铺满页面底部 */
.fr__rail { flex: 0 0 clamp(178px, 21vh, 204px); min-height: 0; overflow: hidden; padding: 9px 14px; }
/* 三层桑基 / 年代热力：固定高度，页面自然变长，不挤压上方主图 */
.fr__deep { flex: 0 0 clamp(300px, 36vh, 380px); min-height: 0; }
</style>
