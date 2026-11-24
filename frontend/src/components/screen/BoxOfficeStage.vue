<!--
  票房分析展厅 · 全宽舞台（参考 itomdev.com/gallery 的相框绳效果）
  ============================================================
  用户 2026-11-01 要求：不要每间数据页都套"左中右三块"，按数据实情调整。
  票房这间的"主角是挂在绳上的全球 TOP 相框"（itomdev 招牌交互），所以：
    · 上方 = 全宽相框绳画廊（BoxOfficeGallery），滚轮漂移、点框看档案
    · 下方 = 两栏附带面板：左「全球票房榜 TOP10」、右「年度票房趋势」
      （这两块原本是左翼/右翼，现在收到展厅底部做配套，腾出全宽给画廊）
  整间房不再有左右两翼，区别于其他"左图右表"的展厅。
-->
<template>
  <div ref="root" class="box-stage" v-sketch="{ sel:'.room-hero, .box-stage__cell, .box-stage__extras, .box-stage__deep, .bog__frame', stagger:0.035, maxDelay:1.1 }">
    <RoomHero
      icon="🎬"
      kicker="Box Office"
      title="票房分析"
      en="Where the money went"
      lead="把全球票房挂在一条绳上：从十亿俱乐部到投资回报，看清哪些电影真正赚到了钱、哪些只是叫好不叫座。"
      :tags="['十亿俱乐部', '投资回报', '相框画廊']"
      :stats="heroStats"
    />
    <!-- 章节在前、展品在后：恢复「分章 → 展品」的策展节奏
         （2026-11-06 修正：此前编号排在展品之后，读起来像给上一节做注脚） -->
    <RoomSection no="01" zh="全球票房画廊" en="Box Office Gallery" lead="全球票房 TOP 影片挂在一条绳上，滚轮沿绳浏览，点框看档案。" />
    <div class="box-stage__gallery">
      <BoxOfficeGallery
        :gallery="gallery"
        :total-movies="totalMovies"
        :total-revenue="totalRevenue"
        :top-year="topYear"
        :pick="pick"
      />
    </div>

    <RoomSection no="02" zh="榜单与年度趋势" en="Top 10 · Yearly Trend" lead="左为十亿俱乐部榜单，右为各年度票房走势，看清水涨船高的年份。" />
    <div class="box-stage__dock u-reveal">
      <div class="box-stage__cell box-stage__cell--rank">
        <BoxOfficeRank
          :gallery="gallery"
          :total-movies="totalMovies"
          @pick="(g) => emit('pick', g)"
        />
      </div>
      <div class="box-stage__cell box-stage__cell--trend">
        <BoxOfficeTrend
          :years="years"
          :total-revenue="totalRevenue"
          :total-movies="totalMovies"
        />
      </div>
    </div>

    <RoomSection no="03" zh="总账 · 回报 · 类型" en="Ledger · ROI · Genre" lead="从票房总账到投资回报，再到各类型票房占比，看清钱去了哪里。" />
    <!-- 第三层：票房总账 / 投资回报 / 类型票房（用户要求"数据要多一点"） -->
    <div class="box-stage__extras u-reveal" style="--d:.08s">
      <BoxExtras
        :gallery="gallery"
        :total-movies="totalMovies"
        :total-revenue="totalRevenue"
        :top-year="topYear"
        :years="years"
        @pick="(g) => emit('pick', g)"
      />
    </div>

    <RoomSection no="04" zh="票房与口碑的相关" en="Correlation · Regression" lead="预算花得多就一定卖得好？把散点、相关系数与回归线摊开，看钱和口碑到底有多相关。" />
    <!-- 第四层：相关矩阵 / 预算×票房散点回归（Pearson r 与 R² 由后端现算） -->
    <div class="box-stage__deep u-reveal" style="--d:.16s">
      <CorrelationPanel :correlations="correlations" />
    </div>
  </div>
</template>

<script setup>
// ============================================================
// 票房分析全宽舞台：画廊（主）+ 底部两栏配套（次）
// ============================================================
import { computed, ref } from 'vue'
import BoxOfficeGallery from './BoxOfficeGallery.vue'
import BoxOfficeRank from './BoxOfficeRank.vue'
import BoxOfficeTrend from './BoxOfficeTrend.vue'
import BoxExtras from './BoxExtras.vue'
import CorrelationPanel from './CorrelationPanel.vue'
import RoomHero from './RoomHero.vue'
import RoomSection from './RoomSection.vue'
import { useReveal } from '../../composables/useReveal.js'

const root = ref(null)
useReveal(root)

const props = defineProps({
  gallery: { type: Array, default: () => [] },
  totalMovies: { type: Number, default: 0 },
  totalRevenue: { type: Number, default: 0 },
  topYear: { type: Number, default: null },
  years: { type: Array, default: () => [] },
  /* 榜单点选联动：打开画廊里同一部的档案卡 */
  pick: { type: Object, default: null },
  /* 深度分析：Pearson 相关矩阵 / 回归散点 */
  correlations: { type: Object, default: null },
})
const emit = defineEmits(['pick'])

// Hero 真实指标：影片数 / 全球总票房(美元→亿美元) / 票房峰值年
const heroStats = computed(() => [
  { value: props.totalMovies || 0, label: '收录影片' },
  { value: Math.round(((props.totalRevenue || 0) / 1e8) * 10) / 10, decimals: 1, label: '全球总票房（亿美元）' },
  { value: props.topYear || 0, label: '票房峰值年' },
])
</script>

<style scoped>
.box-stage {
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  gap: 10px;
  /* 抵消 styles/pages.css 里全局同名 .box-stage（盲盒页）的副作用：
     否则会继承 26px 内边距 / 虚线边框 / 渐变底 / 14px 下外边距，
     挤掉底部榜单高度并露出怪边框 */
  padding: 6px;
  margin: 0;
  background: none;
  border: 0;
  border-radius: 0;
  text-align: left;
}
/* 画廊（相框绳）固定占上部：整张相框约 181px + 场景内边距，
   给到 262 才不会把片名/票房的最后一行裁掉（2026-11-02 实测 156px 场景裁掉 31px）。
   下方 dock 仍有余量（10 行榜单只需约 270px），所以让画廊多拿一点。 */
.box-stage__gallery { flex: 0 0 clamp(212px, 29vh, 262px); min-height: 0; }
/* 让画廊随舞台收缩（默认 min-height:420 会在窄舞台顶破容器） */
.box-stage__gallery :deep(.bog) { min-height: 0; }

/* 底部两栏配套：全球票房榜 + 年度票房趋势（收编自原左右两翼）。
   2026-11-05 修复：父级 .box-stage 改为 height:auto（内容定高），
   这里不能再 flex:1 1 0（无剩余空间会塌成 0），改为固定最小高度自撑：
   TOP10 十条 + 趋势图都能完整显示，矮屏时榜单内部自行滚动。 */
.box-stage__dock {
  flex: 0 0 auto;
  min-height: 440px;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.box-stage__cell {
  min-width: 0;
  min-height: 0;
  padding: 8px 12px 6px;
  border-radius: 16px;
  background: linear-gradient(180deg, #FDFAF3 0%, #F8F2E6 60%, #F3EADA 100%);
  border: 1px solid rgba(139, 69, 19, 0.18);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.85), 0 8px 22px rgba(139, 69, 19, 0.06);
  overflow: hidden;
}
.box-stage__cell--trend { padding-bottom: 10px; }

/* 第三层数据背板：固定高度，占页面下半屏（不再抢榜单的空间）。
   243px 才够 8 行 ROI + 抬头 + 脚注全部露出（实测 225 会裁掉最后一行）。 */
.box-stage__extras { flex: 0 0 clamp(226px, 27vh, 250px); min-height: 0; }
/* 第四层：相关矩阵 / 回归散点，固定高度、页面自然变长（不抢画廊与榜单） */
.box-stage__deep { flex: 0 0 clamp(232px, 27vh, 272px); min-height: 0; }
</style>
