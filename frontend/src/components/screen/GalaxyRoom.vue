<template>
  <!--
    ============================================================
    口碑星图展厅 · 沉浸式 3D 星系 + 悬浮读图卡
    ------------------------------------------------------------
    与"左中右三块"彻底不同：中央是整屏 3D 粒子星系（GalaxyStage 在底层透出），
    这里只放一张手绘读图卡，像展览里的展签。不包玻璃面板，让星空自己当主视觉。
    ============================================================
  -->
  <div class="galaxy-float">
    <!-- 左侧速览卡：用真实数据填掉大片的左半空白（星空不再孤零零） -->
    <div v-if="stats" class="galaxy-stats float-card">
      <div class="galaxy-stats__h">星系速览</div>
      <div class="galaxy-stats__grid">
        <div class="gs-item"><b>{{ stats.count }}</b><span>收录影片</span></div>
        <div class="gs-item"><b>{{ stats.avg.toFixed(1) }}</b><span>全场均分</span></div>
        <div class="gs-item"><b>{{ stats.arms }}</b><span>类型旋臂</span></div>
        <div class="gs-item"><b>{{ stats.topCount }}</b><span>{{ stats.topGenre }} 部</span></div>
      </div>
    </div>

    <!-- 右上报亭式卡片：情感分布 + 归纳词典（不挡中央星图） -->
    <div class="galaxy-echo float-card">
      <EchoChamber :sentiment="sentiment" :lexicon="lexicon" />
    </div>

    <!-- 左下旋臂图鉴：把星图里每条旋臂翻译成类型名 + 数量 + 均分 -->
    <ArmLegend v-if="movies.length" :movies="movies" class="galaxy-arms" />

    <div class="galaxy-card float-card">
      <div class="galaxy-card__head">
        📖 怎么读这张星图
        <i>每颗星 = 一部真实影片</i>
      </div>
      <div class="galaxy-card__row">
        <span class="gl-item"><i class="gl-item__bar" />颜色 = 影片口碑</span>
        <span class="gl-item">星星越大 = 讨论越热</span>
        <span class="gl-item">越靠核心 = 越热门</span>
        <span class="gl-item">每条旋臂 = 一个电影类型</span>
      </div>
      <div class="galaxy-card__stats">
        均分 {{ avgRating.toFixed(1) }} · {{ armCount }} 条类型旋臂 · 悬停任意星星查看影片详情
      </div>
    </div>

    <!-- 右下：影人×类型知识图谱（力导向网络，节点/边来自共现与 lift 真实计算） -->
    <div v-if="knowledge?.nodes?.length" class="galaxy-graph">
      <KnowledgeGraphPanel :knowledge="knowledge" />
    </div>
  </div>
</template>

<script setup>
// ============================================================
// 星系读图卡（独立组件，便于在大屏 / 深链里复用）
// ============================================================
import EchoChamber from './EchoChamber.vue'
import ArmLegend from './ArmLegend.vue'
import KnowledgeGraphPanel from './KnowledgeGraphPanel.vue'

const props = defineProps({
  avgRating: { type: Number, default: 0 },
  armCount: { type: Number, default: 0 },
  sentiment: { type: Object, default: null },
  lexicon: { type: Object, default: null },
  stats: { type: Object, default: null },
  movies: { type: Array, default: () => [] },
  knowledge: { type: Object, default: null },
})
</script>

<style scoped>
/* 占满星系层之上的落位区（room-nav 之下），卡片绝对定位在底部居中 */
.galaxy-float {
  position: relative;
  flex: 1;
  min-height: 0;
}

/* 左下旋臂图鉴：补掉左下的空白，同时给星图一份"图例说明" */
.galaxy-arms {
  position: absolute;
  left: 14px;
  bottom: 14px;
  width: 236px;
  max-width: 34%;
  z-index: 2;
}
@media (max-width: 1100px) {
  .galaxy-arms { display: none; }
}

/* 右上报亭式卡片：情感分布 + 归纳词典（贴右上角，不挡中央星图） */
.galaxy-echo {
  position: absolute;
  top: 14px;
  right: 14px;
  width: 300px;
  max-width: 40%;
  max-height: calc(100% - 28px);
  overflow: auto;
  padding: 12px 14px;
  background: linear-gradient(178deg, rgba(253, 251, 244, 0.95), rgba(247, 241, 227, 0.92));
}

/* 左侧速览卡：四宫格关键指标，填掉左侧空白，让星系不再孤悬 */
.galaxy-stats {
  position: absolute;
  top: 14px;
  left: 14px;
  width: 232px;
  max-width: 42%;
  padding: 11px 14px 12px;
  background: linear-gradient(178deg, rgba(253, 251, 244, 0.95), rgba(247, 241, 227, 0.92));
}
.galaxy-stats__h {
  font-size: 12.5px;
  font-weight: 700;
  color: var(--u-orange-deep);
  letter-spacing: 1px;
  padding-bottom: 7px;
  margin-bottom: 8px;
  border-bottom: 1px solid rgba(194, 65, 12, 0.22);
}
.galaxy-stats__grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 9px 14px;
}
.gs-item { display: flex; flex-direction: column; }
.gs-item b {
  font-family: var(--u-font-tech);
  font-size: 21px;
  font-weight: 800;
  color: #8B4513;
  line-height: 1.1;
}
.gs-item span { font-size: 10.5px; color: var(--u-text-2); margin-top: 2px; }
@media (max-width: 1180px) {
  .galaxy-stats { width: 210px; }
  .galaxy-stats__grid { gap: 7px 10px; }
}
@media (max-width: 900px) {
  .galaxy-stats { display: none; }
}

@media (max-width: 1180px) {
  .galaxy-echo { width: 260px; max-width: 44%; }
}
@media (max-width: 900px) {
  .galaxy-echo { display: none; }
}

.galaxy-card {
  position: absolute;
  left: 50%;
  bottom: 14px;
  transform: translateX(-50%);
  max-width: min(780px, calc(100% - 32px));
  text-align: center;
  padding: 12px 18px 14px;
}

.galaxy-card__head {
  display: flex;
  align-items: baseline;
  justify-content: center;
  gap: 10px;
  font-size: 12.5px;
  font-weight: 700;
  color: var(--u-orange-deep);
  letter-spacing: 1px;
}
.galaxy-card__head i {
  font-style: normal;
  font-size: 10px;
  font-weight: 400;
  color: var(--u-text-2);
}

.galaxy-card__row {
  display: flex;
  flex-wrap: wrap;
  justify-content: center;
  gap: 7px 18px;
  margin-top: 9px;
  font-size: 11.5px;
  color: #4A3C2A;
}
.gl-item { display: inline-flex; align-items: center; gap: 7px; }
.gl-item__bar {
  width: 46px;
  height: 8px;
  border-radius: 4px;
  background: linear-gradient(90deg, #4A7FB5, #A78BFA 52%, #D99A3A);
  box-shadow: 0 0 8px rgba(167, 139, 250, 0.18);
}

.galaxy-card__stats {
  margin-top: 9px;
  font-family: var(--u-font-tech);
  font-size: 10px;
  letter-spacing: 1.2px;
  color: var(--u-text-2);
}

/* ---------- 右下知识图谱卡 ----------
   ★ 34 节点 / 72 边塞在 330×228 里会糊成一团（实拍确认）。放大到 400×300，
     与右上的情感亭（限高 46%）、底部读图卡（限宽 600px）各占一块，不重叠。 */
.galaxy-graph {
  position: absolute;
  right: 14px;
  bottom: 14px;
  width: 400px;
  height: 300px;
  z-index: 3;
}
/* 更高特异性覆盖基础规则：给右下图腾出竖向空间、收窄底部读图卡避免压住图谱 */
.galaxy-float .galaxy-echo { max-height: 40%; }
.galaxy-float .galaxy-card { max-width: min(560px, calc(100% - 32px)); }
@media (max-width: 1180px) {
  .galaxy-graph { width: 320px; height: 240px; }
}
@media (max-width: 950px) {
  .galaxy-graph { display: none; }
}
</style>
