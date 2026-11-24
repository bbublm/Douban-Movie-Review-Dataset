<template>
  <!--
    ============================================================
    展厅章节标题 · 编辑式跨页节奏（itomdev 杂志分章）
    ------------------------------------------------------------
    2026-11-06 大调整：编号从 42px 实心放大成 90px 描边数字作背景水印，
    中文标题叠在其上；手绘双分隔线 + 右对齐英文刊号，拉开段落呼吸。
    ============================================================
    -->
  <div class="room-section" :class="{ 'room-section--bare': bare }">
    <div class="rs__head">
      <span class="rs__no" aria-hidden="true">{{ no }}</span>
      <div class="rs__titles">
        <span class="rs__eyebrow">CHAPTER {{ no }}</span>
        <h2 class="rs__zh">{{ zh }}</h2>
        <p v-if="en" class="rs__en">{{ en }}</p>
      </div>
      <span class="rs__line" aria-hidden="true" />
      <span class="rs__mark" aria-hidden="true">✦</span>
    </div>
    <p v-if="lead" class="rs__lead">{{ lead }}</p>
  </div>
</template>

<script setup>
defineProps({
  no: { type: [String, Number], default: '01' },
  zh: { type: String, required: true },
  en: { type: String, default: '' },
  lead: { type: String, default: '' },
  bare: { type: Boolean, default: false },
})
</script>

<style scoped>
.room-section {
  position: relative;
  margin: 20px 0 10px;
  padding-top: 4px;
}
.rs__head {
  display: flex;
  align-items: center;
  gap: 16px;
  min-height: 60px;
}
/* 超大描边序号：像印在纸上的水印，不抢正文。
   用衬线数字而非 Orbitron —— 后者的 0 自带斜线，空心描边下会被放大成
   「斜线方框」像乱码；衬线体也更贴 itomdev 的杂志编辑感。 */
.rs__no {
  flex: none;
  font-family: Georgia, 'Times New Roman', serif;
  font-size: clamp(62px, 7vw, 104px);
  font-weight: 700;
  line-height: 0.8;
  letter-spacing: -2px;
  color: transparent;
  -webkit-text-stroke: 1.6px rgba(154, 52, 18, 0.38);
  text-shadow: 2px 2px 0 rgba(166, 124, 46, 0.1);
  user-select: none;
}
.rs__titles { flex: none; position: relative; z-index: 1; }
.rs__eyebrow {
  display: block;
  font-family: var(--u-font-tech, 'Orbitron'), sans-serif;
  font-size: 9px;
  letter-spacing: 3px;
  color: rgba(154, 52, 18, 0.75);
  margin-bottom: 3px;
}
.rs__zh {
  margin: 0;
  font-family: var(--u-font-cn, 'Source Han Sans SC'), serif;
  font-size: clamp(21px, 2.2vw, 31px);
  font-weight: 800;
  letter-spacing: 2px;
  line-height: 1.15;
  color: #4A2E16;
}
.rs__en {
  margin: 3px 0 0;
  font-family: var(--u-font-tech, 'Orbitron'), sans-serif;
  font-size: 9.5px;
  letter-spacing: 2.6px;
  text-transform: uppercase;
  color: rgba(122, 92, 48, 0.8);
}
/* 手绘双分隔线：一粗一细，末端渐隐 */
.rs__line {
  flex: 1;
  height: 4px;
  align-self: center;
  background:
    linear-gradient(to right, rgba(154, 52, 18, 0.55), rgba(154, 52, 18, 0.12) 78%, transparent),
    linear-gradient(to right, rgba(166, 124, 46, 0.35), transparent 70%);
  background-size: 100% 1.5px, 100% 1px;
  background-position: 0 0, 0 3px;
  background-repeat: no-repeat;
  border-radius: 2px;
}
.rs__mark {
  flex: none;
  font-size: 15px;
  color: rgba(154, 52, 18, 0.6);
  transform: rotate(12deg);
}
.rs__lead {
  margin: 8px 0 0;
  padding-left: calc(clamp(62px, 7vw, 104px) + 22px);
  font-size: 12.5px;
  line-height: 1.8;
  letter-spacing: 0.4px;
  color: #6B5238;
  max-width: 62em;
}
.room-section--bare .rs__line { opacity: 0.5; }

@media (max-width: 900px) {
  .rs__no { font-size: 62px; }
  .rs__head { min-height: 56px; }
  .rs__lead { padding-left: 0; }
}
</style>
