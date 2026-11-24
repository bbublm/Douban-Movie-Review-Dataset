<template>
  <!--
    ============================================================
    深度分析卡外壳（2026-11-04）
    ------------------------------------------------------------
    五间展厅各挂一张不同形式的图，统一用这张手绘纸卡承托：
      · 结论先行：kicker + title + 一行由后端算出的 note
      · 「放大」把卡片变成全屏纸面，图表随容器 resize 重绘
      · 展开时加一层纸色遮罩，点遮罩或按 Esc 收起
    样式用非 scoped：slot 里的图表容器由各图组件自己上色，
    外壳的 ac__* 前缀不污染其它页面。
    ============================================================
  -->
  <div class="ac" :class="{ 'is-expanded': expanded }">
    <div v-if="expanded" class="ac__scrim" @click="close" />
    <div class="ac__head">
      <div class="ac__titles">
        <span class="ac__kicker">{{ kicker }}</span>
        <b class="ac__title">{{ title }}</b>
      </div>
      <span class="ac__spacer" />
      <div v-if="tabs?.length" class="ac__tabs">
        <button
          v-for="t in tabs"
          :key="t.key"
          class="ac__tab"
          :class="{ 'is-on': active === t.key }"
          type="button"
          @click="active = t.key"
        >{{ t.label }}</button>
      </div>
      <button class="ac__expand" type="button" :aria-label="expanded ? '收起图表' : '放大图表'" @click="expanded = !expanded">
        {{ expanded ? '✕ 收起' : '⤢ 放大' }}
      </button>
    </div>
    <p v-if="note" class="ac__note">{{ note }}</p>
    <div class="ac__body"><slot :tab="active" /></div>
  </div>
</template>

<script setup>
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

const props = defineProps({
  kicker: { type: String, default: 'DEEP ANALYSIS' },
  title: { type: String, default: '' },
  note: { type: String, default: '' },
  tabs: { type: Array, default: () => [] },   // [{ key, label }]
})
const expanded = ref(false)
const active = ref(props.tabs?.[0]?.key || '')
watch(() => props.tabs, (t) => { if (t?.length && !t.some((x) => x.key === active.value)) active.value = t[0].key })
function close() { expanded.value = false }
function onKey(e) { if (e.key === 'Escape' && expanded.value) close() }
onMounted(() => window.addEventListener('keydown', onKey))
onBeforeUnmount(() => window.removeEventListener('keydown', onKey))
</script>

<style>
/* 非 scoped：外壳类名带 ac__ 前缀，slot 内容的样式由各图组件自理 */
.ac {
  position: relative;
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  padding: 10px 12px 12px;
  overflow: hidden;
  background:
    repeating-linear-gradient(92deg, rgba(120, 88, 50, .035) 0 2px, transparent 2px 11px),
    linear-gradient(172deg, #FFFCF4, #F3EAD7);
  border: 1.6px solid rgba(74, 60, 44, .72);
  border-radius: 4px 15px 4px 13px / 13px 4px 15px 4px;
  box-shadow: 3px 4px 0 rgba(74, 60, 44, .2), 0 10px 24px rgba(74, 44, 20, .09);
}
.ac.is-expanded {
  position: fixed;
  inset: 5vh 5vw;
  z-index: 200;
  overflow: visible;
  padding: 18px 22px 22px;
  box-shadow: 8px 10px 0 rgba(74, 60, 44, .26), 0 30px 80px rgba(58, 40, 20, .3);
}
.ac__scrim {
  position: fixed;
  inset: 0;
  z-index: -1;
  background: rgba(58, 46, 32, .38);
  backdrop-filter: blur(3px);
}
.ac__head { flex: none; display: flex; align-items: center; gap: 8px; }
.ac__titles { display: flex; flex-direction: column; gap: 1px; min-width: 0; }
.ac__kicker {
  font-family: "Orbitron", "Bahnschrift", sans-serif;
  font-size: 8.5px; font-weight: 700; letter-spacing: .2em; color: #8B5E1C;
}
.ac__title {
  font-family: "Kaiti SC", KaiTi, STKaiti, Georgia, serif;
  font-size: 15px; font-weight: 700; color: #241B12; letter-spacing: .02em;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.ac.is-expanded .ac__title { font-size: 22px; }
.ac__spacer { flex: 1; }
.ac__tabs { display: inline-flex; gap: 3px; padding: 2px; border-radius: 20px; background: rgba(166, 124, 46, .14); }
.ac__tab {
  border: 0; padding: 4px 9px; border-radius: 18px; cursor: pointer;
  font-family: inherit; font-size: 9.5px; font-weight: 700; color: #6B4A22;
  background: none; white-space: nowrap;
}
.ac__tab.is-on { color: #FFF6E9; background: linear-gradient(160deg, #A0522D, #8B4513); }
.ac__tab:focus-visible { outline: 2px dashed #C2410C; outline-offset: 2px; }
.ac__expand {
  flex: none; border: 1.4px solid rgba(139, 94, 28, .6); border-radius: 20px;
  padding: 5px 11px; cursor: pointer; font-family: inherit;
  font-size: 9.5px; font-weight: 700; color: #6B4A22;
  background: rgba(255, 252, 244, .92);
}
.ac__expand:hover { background: #FFF6DF; }
.ac__expand:focus-visible { outline: 2px dashed #C2410C; outline-offset: 2px; }
.ac__note {
  flex: none; margin: 6px 0 0; padding-left: 8px;
  border-left: 2px solid rgba(194, 65, 12, .55);
  font-size: 10px; line-height: 1.4; color: #8B4513;
}
.ac__body { flex: 1 1 0; min-height: 0; margin-top: 7px; }
.ac.is-expanded .ac__body { margin-top: 12px; }
@media (max-width: 900px) {
  .ac.is-expanded { inset: 2vh 2vw; padding: 12px; }
  .ac__tabs { display: none; }
}
</style>
