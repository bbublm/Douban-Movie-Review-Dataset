<template>
  <!--
    ============================================================
    大厅 · 馆长洞察卡叠（A24 编辑排版 × itomdev 手绘纸卡）
    ------------------------------------------------------------
    推门之前先给结论：三张卡各讲一个真实分析发现（数据 /insights/story）。
    · A24 credits 式键值行：标签左对齐 / 值右对齐 / 细线分隔
    · 核心数字衬线大字；问题用楷体（Windows 自带，贴合手绘纸感）
    · 交互：鼠标移动 = 卡片轻微视差倾斜（mousemove 写 --rx/--ry）；点击直达对应展厅
    · 容器 pointer-events:none、卡片 auto —— 间隙不挡六扇门的点击
    ============================================================
  -->
  <div v-if="cards.length" class="hi" aria-label="馆长洞察">
    <div class="hi__head">
      <i class="hi__head-pin" />
      <span class="hi__head-zh">馆长洞察</span>
      <span class="hi__head-en">DATA STORIES</span>
      <i class="hi__head-line" />
    </div>

    <div class="hi__row">
      <article
        v-for="(c, i) in cards"
        :key="c.kind"
        class="hi__card"
        :style="cardStyle(c.kind, i)"
        :data-kind="c.kind"
        role="button"
        tabindex="0"
        @pointermove="onTilt(c.kind, $event)"
        @pointerleave="onUntilt(c.kind)"
        @click="$emit('enter', c.room)"
        @keydown.enter="$emit('enter', c.room)"
      >
        <div class="hi__card-in">
          <div class="hi__kicker">{{ c.kicker }}</div>
          <div class="hi__q">{{ c.question }}</div>
          <div class="hi__a">{{ c.answer }}</div>
          <div class="hi__credits">
            <div v-for="f in c.facts" :key="f.k" class="hi__fact">
              <span class="hi__k">{{ f.k }}</span>
              <span class="hi__v" :class="{ 'is-big': f.big }">{{ f.v }}</span>
            </div>
          </div>
          <div class="hi__go">推门看详情 <i>→</i></div>
        </div>
      </article>
    </div>
  </div>
</template>

<script setup>
// ============================================================
// 馆长洞察卡：纯展示 + 轻交互（视差倾斜），数据来自父级 /insights/story
// 倾斜不用 JS 动画库，直接 mousemove 写 CSS 变量，transform 由 CSS 消费 ——
// 与项目里海报扇 / 3D 走廊同款手法，零额外依赖、无 rAF 负担
// ============================================================
import { reactive } from 'vue'

defineProps({
  cards: { type: Array, default: () => [] },
})
defineEmits(['enter'])

// 每张卡的倾斜角按 kind 惰性记录（ kind 唯一），任何时序都不会读到 undefined
const tilt = reactive({})
function tiltOf(kind) {
  if (!tilt[kind]) tilt[kind] = { x: 0, y: 0, lift: 0 }
  return tilt[kind]
}
function cardStyle(kind, i) {
  const t = tiltOf(kind)
  return { '--d': i, '--rx': t.x + 'deg', '--ry': t.y + 'deg', '--lift': t.lift + 'px' }
}

function onTilt(kind, e) {
  const t = tiltOf(kind)
  const el = e.currentTarget
  const r = el.getBoundingClientRect()
  const px = (e.clientX - r.left) / r.width - 0.5   // -0.5 ~ 0.5
  const py = (e.clientY - r.top) / r.height - 0.5
  t.y = (px * 7).toFixed(2)    // 绕 Y 轴左右倾
  t.x = (-py * 6).toFixed(2)   // 绕 X 轴前后倾
  t.lift = 5
}
function onUntilt(kind) {
  const t = tiltOf(kind)
  t.x = 0
  t.y = 0
  t.lift = 0
}
</script>

<style scoped>
/* ---------- 容器：底部托盘 dock，浮在大厅场景之上 ---------- */
.hi {
  position: absolute;
  left: 50%;
  bottom: 14px;
  transform: translateX(-50%);
  z-index: 30;
  width: min(1080px, calc(100vw - 40px));
  pointer-events: none;            /* 间隙不挡门，卡片自身恢复 auto */
  background: linear-gradient(to bottom, rgba(255, 253, 247, .94), rgba(250, 245, 233, .96));
  border: 1.5px solid rgba(107, 78, 46, .4);
  border-radius: 6px 220px 8px 220px / 8px 220px 6px 220px;
  box-shadow: 0 -6px 22px rgba(74, 40, 20, .16), 5px 5px 0 rgba(74, 40, 20, .16);
  padding: 10px 16px 12px;
  backdrop-filter: blur(3px);
}
.hi__head {
  display: flex;
  align-items: baseline;
  gap: 8px;
  margin: 0 4px 8px;
  pointer-events: none;
}
.hi__head-pin {
  width: 9px; height: 9px;
  border-radius: 50%;
  background: radial-gradient(circle at 34% 32%, #D9A441, #A67C2E 70%);
  box-shadow: 0 1px 3px rgba(74, 40, 20, .4);
  align-self: center;
}
.hi__head-zh { font-size: 12.5px; font-weight: 800; letter-spacing: .12em; color: #4A2E16; }
.hi__head-en { font-family: var(--u-font-tech); font-size: 8.5px; letter-spacing: .22em; color: var(--u-text-2); }
.hi__head-line { flex: 1; height: 1px; background: linear-gradient(to right, rgba(154, 96, 40, .32), transparent); }

.hi__row {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 12px;
}

/* ---------- 卡片：手绘纸 + A24 credits ---------- */
.hi__card {
  pointer-events: auto;
  cursor: pointer;
  perspective: 700px;
  transition: transform .18s ease;
  transform: translateY(var(--lift)) perspective(700px) rotateX(var(--rx)) rotateY(var(--ry));
  animation: hi-in .6s cubic-bezier(.2, .8, .3, 1) both;
  animation-delay: calc(var(--d) * 0.12s);
}
@keyframes hi-in {
  from { opacity: 0; transform: translateY(22px) perspective(700px) rotateX(6deg); }
  to   { opacity: 1; }
}
.hi__card-in {
  height: 100%;
  background: var(--u-paper, #FFFDF7);
  border: 1.4px solid rgba(107, 78, 46, .4);
  border-radius: 2px 255px 3px / 255px 5px 225px 3px;
  box-shadow: 3px 3px 0 rgba(74, 40, 20, .18);
  padding: 10px 14px 9px;
  transition: box-shadow .18s ease, border-color .18s ease;
  display: flex;
  flex-direction: column;
  /* a24 光盘式轻悬浮：让卡叠"活着"；错开相位，三卡不齐步；悬停时停住便于阅读 */
  animation: hi-bob 5.2s ease-in-out infinite;
  animation-delay: calc(var(--d, 0) * -1.6s);
}
@keyframes hi-bob {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-3px); }
}
.hi__card:hover .hi__card-in { animation-play-state: paused; }
.hi__card:hover .hi__card-in {
  border-color: rgba(166, 124, 46, .85);
  box-shadow: 4px 5px 0 rgba(74, 40, 20, .24), 0 10px 22px rgba(74, 40, 20, .18);
}

.hi__kicker {
  font-size: 9.5px;
  font-weight: 800;
  letter-spacing: .2em;
  color: var(--u-gold, #A67C2E);
}
.hi__q {
  font-family: "Kaiti SC", KaiTi, STKaiti, "Songti SC", serif;
  font-size: 16.5px;
  font-weight: 700;
  line-height: 1.25;
  color: #3A2E20;
  margin: 4px 0 1px;
}
.hi__a {
  font-size: 10px;
  color: var(--u-text-2, #7D6B52);
  margin-bottom: 6px;
}

/* credits：标签左 / 值右 / 细线分隔（A24 手法） */
.hi__credits { border-top: 1px solid rgba(154, 96, 40, .2); margin-top: auto; }
.hi__fact {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 10px;
  padding: 3px 0;
  border-bottom: 1px solid rgba(154, 96, 40, .2);
}
.hi__fact:last-child { border-bottom: 0; }
.hi__k { font-size: 10px; color: var(--u-text-2, #7D6B52); letter-spacing: .05em; white-space: nowrap; }
.hi__v { font-size: 11px; font-weight: 700; color: #3A2E20; text-align: right; }
.hi__v.is-big {
  font-family: "Kaiti SC", KaiTi, STKaiti, serif;
  font-size: 19px;
  font-weight: 700;
  color: var(--u-orange, #C2410C);
  line-height: 1;
}

.hi__go {
  margin-top: 6px;
  font-size: 9.5px;
  letter-spacing: .06em;
  color: var(--u-gold, #A67C2E);
  font-weight: 700;
  display: flex;
  align-items: center;
  gap: 5px;
  opacity: .75;
  transition: opacity .16s ease, gap .16s ease;
}
.hi__go i { font-style: normal; transition: transform .16s ease; }
.hi__card:hover .hi__go { opacity: 1; gap: 9px; }
.hi__card:hover .hi__go i { transform: translateX(3px); }

/* 窄屏：横向滚动条，保持三卡可达 */
@media (max-width: 900px) {
  .hi { bottom: 10px; padding: 8px 12px 10px; }
  .hi__row { display: flex; overflow-x: auto; padding-bottom: 4px; scrollbar-width: thin; }
  .hi__card { flex: 0 0 232px; }
}
@media (prefers-reduced-motion: reduce) {
  .hi__card { animation: none; transform: none; }
  .hi__card-in { animation: none; }
}
</style>
