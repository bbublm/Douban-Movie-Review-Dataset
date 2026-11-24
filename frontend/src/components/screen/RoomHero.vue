<template>
  <!--
    ============================================================
    展厅 Hero · 编辑式策展封面（itomdev / A24 杂志跨页）
    ------------------------------------------------------------
    2026-11-06 大调整：从「小标题 + 三颗胶囊数字」升级为一张展览封面——
      · 超大展示字标题 + 竖排英文刊名 + 手绘纸纹 / 胶带 / 钢印
      · 右侧真实指标改为大号数字带（衬线数字 + 细分隔线），不再塞小胶囊
      · progressive blur reveal：进场从模糊到清晰（itomdev 招牌渐显）
    数字全部来自父组件传入的真实聚合（拒绝硬编码）。
    ============================================================
    -->
  <header class="room-hero">
    <div class="rh__grain" aria-hidden="true" />
    <span class="rh__tape rh__tape--tl" aria-hidden="true" />
    <span class="rh__tape rh__tape--br" aria-hidden="true" />
    <span class="rh__spine" aria-hidden="true">{{ en || kicker }}</span>

    <div class="rh__left">
      <div class="rh__kicker">
        <span class="rh__icon">{{ icon }}</span>
        <span class="rh__kicker-zh">{{ kicker }}</span>
        <span class="rh__kicker-rule" />
        <span class="rh__kicker-no">EXHIBITION / 电影盒子 · 数据展厅</span>
      </div>
      <h1 class="rh__title">{{ title }}</h1>
      <p class="rh__en">{{ en }}</p>
      <p class="rh__lead">{{ lead }}</p>
      <div v-if="tags && tags.length" class="rh__tags">
        <span v-for="(t, i) in tags" :key="i" class="rh__tag">{{ t }}</span>
      </div>
    </div>

    <div class="rh__right">
      <div v-if="stats && stats.length" class="rh__stats">
        <div v-for="(s, i) in stats" :key="i" class="rh__stat">
          <div class="rh__num">
            <RollingNumber :value="s.value" :decimals="s.decimals || 0" :duration="s.duration || 1500" />
            <span v-if="s.suffix" class="rh__suffix">{{ s.suffix }}</span>
          </div>
          <div class="rh__label">{{ s.label }}</div>
        </div>
      </div>
      <div class="rh__foot">
        <span class="rh__seal" aria-hidden="true">影 · DATA</span>
        <div class="rh__cue" aria-hidden="true">
          <span class="rh__cue-arrow">↓</span>
          <span class="rh__cue-text">下滑展开展品</span>
        </div>
      </div>
    </div>
  </header>
</template>

<script setup>
// 展厅 Hero（独立的策展头，五间数据页复用）
import RollingNumber from './RollingNumber.vue'

defineProps({
  icon: { type: String, default: '' },
  kicker: { type: String, default: '' },
  title: { type: String, required: true },
  en: { type: String, default: '' },
  lead: { type: String, default: '' },
  // 左列策展关键词标签（填补标题区、强化引导）
  tags: { type: Array, default: () => [] },
  // 每项：{ value:Number, suffix?:String, label:String, decimals?:Number, duration?:Number }
  stats: { type: Array, default: () => [] },
})
</script>

<style scoped>
.room-hero {
  position: relative;
  /* 压在固定海报墙背景层（z-index:1）之上：Hero 是实心纸面入口，不蒙海报 */
  z-index: 2;
  display: grid;
  grid-template-columns: minmax(0, 1.35fr) minmax(280px, 0.65fr);
  align-items: stretch;
  gap: 30px;
  margin: 4px 0 20px;
  padding: 32px 46px 26px;
  /* 手绘抖边：像裁下来的手工纸，四角都不规整 */
  border-radius: 6px 26px 8px 22px / 22px 8px 26px 6px;
  background:
    radial-gradient(90% 120% at 8% 0%, rgba(255, 253, 246, 0.96), rgba(255, 253, 246, 0) 62%),
    linear-gradient(135deg, #FEFBF3 0%, #F9F2E2 58%, #F1E7D2 100%);
  border: 1.6px solid rgba(107, 78, 46, 0.4);
  box-shadow:
    0 22px 52px rgba(90, 64, 34, 0.2),
    5px 6px 0 rgba(107, 78, 46, 0.1),
    inset 0 1px 0 rgba(255, 255, 255, 0.95);
  overflow: hidden;
}
/* 纸纹：极淡的斜向纤维，纯 CSS 不引外部资源 */
.rh__grain {
  position: absolute;
  inset: 0;
  pointer-events: none;
  opacity: 0.5;
  background:
    repeating-linear-gradient(0deg, rgba(139, 107, 71, 0.035) 0 1px, transparent 1px 4px),
    repeating-linear-gradient(90deg, rgba(139, 107, 71, 0.022) 0 1px, transparent 1px 6px);
}
/* 手绘暖金光晕：左上角策展灯光 */
.room-hero::before {
  content: '';
  position: absolute;
  left: -140px;
  top: -170px;
  width: 520px;
  height: 520px;
  background: radial-gradient(circle, rgba(194, 65, 12, 0.14), rgba(166, 124, 46, 0.06) 48%, transparent 72%);
  pointer-events: none;
}
/* 胶带：半透明牛皮纸贴在两角 */
.rh__tape {
  position: absolute;
  width: 108px;
  height: 30px;
  background: linear-gradient(180deg, rgba(214, 186, 133, 0.62), rgba(190, 158, 104, 0.5));
  border-left: 1px dashed rgba(255, 255, 255, 0.5);
  border-right: 1px dashed rgba(255, 255, 255, 0.5);
  box-shadow: 0 2px 6px rgba(90, 64, 34, 0.16);
  pointer-events: none;
  z-index: 3;
}
/* Hero 有 overflow:hidden，胶带必须落在纸面内侧才不会被裁掉 */
.rh__tape--tl { top: 6px; left: 30px; transform: rotate(-16deg); }
.rh__tape--br { bottom: 8px; right: 42px; transform: rotate(-11deg); }
/* 右缘竖排英文刊名：杂志书脊感 */
.rh__spine {
  position: absolute;
  right: 9px;
  top: 26px;
  writing-mode: vertical-rl;
  font-family: var(--u-font-tech, 'Orbitron'), sans-serif;
  font-size: 10px;
  letter-spacing: 4px;
  text-transform: uppercase;
  color: rgba(107, 78, 46, 0.42);
  pointer-events: none;
}

.rh__kicker {
  display: flex;
  align-items: center;
  gap: 10px;
  font-family: var(--u-font-tech, 'Orbitron'), sans-serif;
  font-size: 11px;
  letter-spacing: 2.2px;
  color: var(--u-orange-deep, #9A3412);
  text-transform: uppercase;
}
.rh__icon { font-size: 18px; filter: drop-shadow(0 0 8px rgba(194, 65, 12, 0.25)); }
.rh__kicker-zh { letter-spacing: 1.5px; font-weight: 700; white-space: nowrap; }
.rh__kicker-rule { width: 34px; height: 1px; background: rgba(154, 52, 18, 0.55); }
.rh__kicker-no { letter-spacing: 1.2px; font-size: 9.5px; color: rgba(107, 78, 46, 0.7); white-space: nowrap; }

/* 展示字标题：超大中文衬线，杂志跨页主视觉 */
.rh__title {
  margin: 16px 0 6px;
  font-family: var(--u-font-cn, 'Source Han Sans SC'), serif;
  font-size: clamp(48px, 6.4vw, 96px);
  font-weight: 900;
  line-height: 1.02;
  letter-spacing: 3px;
  background: linear-gradient(118deg, #6B2710 0%, #9A3412 40%, #B45309 78%, #8A5A18 100%);
  -webkit-background-clip: text;
  background-clip: text;
  -webkit-text-fill-color: transparent;
  filter: drop-shadow(1px 2px 0 rgba(255, 253, 246, 0.8));
}
.rh__en {
  font-family: var(--u-font-tech, 'Orbitron'), sans-serif;
  font-size: clamp(11px, 1.1vw, 13px);
  letter-spacing: 5px;
  color: rgba(122, 92, 48, 0.85);
  text-transform: uppercase;
  margin: 0 0 18px;
}
.rh__lead {
  margin: 0;
  max-width: 40em;
  font-size: clamp(13px, 1.15vw, 15.5px);
  line-height: 1.9;
  color: #4A3A28;
  padding-left: 14px;
  border-left: 2px solid rgba(194, 65, 12, 0.35);
}
.rh__tags {
  display: flex;
  flex-wrap: wrap;
  gap: 9px;
  margin-top: 20px;
}
.rh__tag {
  font-family: var(--u-font-cn, 'Source Han Sans SC'), sans-serif;
  font-size: 11.5px;
  font-weight: 700;
  letter-spacing: 1.4px;
  color: #7C2D12;
  padding: 6px 15px;
  background: rgba(194, 65, 12, 0.1);
  border: 1.2px solid rgba(194, 65, 12, 0.36);
  /* 手绘标签：两端不等圆 */
  border-radius: 14px 4px 13px 5px / 5px 13px 4px 14px;
}

/* 右侧：大号数字带（去掉白胶囊，改成账本式竖排） */
.rh__right {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  align-items: flex-end;
  padding-right: 14px;
  position: relative;
  z-index: 2;
}
.rh__stats {
  width: 100%;
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.rh__stat {
  display: flex;
  align-items: baseline;
  justify-content: flex-end;
  gap: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid rgba(139, 107, 71, 0.28);
}
.rh__num {
  /* 衬线账本数字：Orbitron 的 7 形近 1，173 会被看成 113（实测），
     且衬线体更贴杂志编辑式的策展封面。 */
  font-family: Georgia, 'Times New Roman', serif;
  font-size: clamp(34px, 4.2vw, 60px);
  font-weight: 700;
  line-height: 0.98;
  letter-spacing: 0.5px;
  color: #7C2D12;
  font-variant-numeric: tabular-nums;
}
.rh__suffix {
  font-size: 0.44em;
  font-weight: 700;
  color: var(--u-text-2, #7D6B52);
  margin-left: 3px;
}
.rh__label {
  order: -1;
  flex: 1;
  text-align: right;
  font-size: 11.5px;
  letter-spacing: 1.4px;
  line-height: 1.5;
  color: rgba(90, 70, 46, 0.92);
  font-weight: 600;
}
.rh__foot {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 18px;
  margin-top: 18px;
  width: 100%;
}
/* 钢印：手绘圆章 */
.rh__seal {
  display: grid;
  place-items: center;
  width: 58px;
  height: 58px;
  border: 2px solid rgba(154, 52, 18, 0.5);
  border-radius: 50% 46% 52% 48%;
  color: rgba(154, 52, 18, 0.62);
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 1px;
  transform: rotate(-12deg);
  box-shadow: inset 0 0 0 2px rgba(255, 253, 246, 0.7), inset 0 0 0 3px rgba(154, 52, 18, 0.22);
}
.rh__cue {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  font-size: 11px;
  letter-spacing: 1.6px;
  font-weight: 700;
  color: #6B4E2E;
  white-space: nowrap;
}
.rh__cue-arrow {
  font-size: 17px;
  font-weight: 700;
  color: #8B2D0A;
  animation: rh-bob 1.8s ease-in-out infinite;
}
@keyframes rh-bob {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(5px); }
}
@media (prefers-reduced-motion: reduce) {
  .rh__cue-arrow { animation: none; }
}

/* 窄屏：单栏堆叠，数字带改横向 */
@media (max-width: 900px) {
  .room-hero {
    grid-template-columns: 1fr;
    gap: 22px;
    padding: 26px 24px 26px;
  }
  .rh__title { font-size: clamp(40px, 11vw, 64px); }
  .rh__stats { flex-direction: row; flex-wrap: wrap; gap: 14px 22px; }
  .rh__stat { flex: 1 1 130px; flex-direction: column; align-items: flex-start; gap: 4px; border-bottom: none; padding-bottom: 0; }
  .rh__label { order: 0; text-align: left; }
  .rh__num { font-size: 34px; }
  .rh__spine { display: none; }
}

/* 入场：progressive blur reveal —— 从模糊到清晰，itomdev 招牌渐显 */
.room-hero {
  animation: rh-in 0.85s cubic-bezier(.16, .84, .44, 1) both;
}
@keyframes rh-in {
  from { opacity: 0; filter: blur(14px); transform: translateY(20px); }
  to { opacity: 1; filter: blur(0); transform: none; }
}
@media (prefers-reduced-motion: reduce) {
  .room-hero { animation: none; }
}
</style>
