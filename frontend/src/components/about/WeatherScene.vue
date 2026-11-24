<script setup>
// ============================================================
// 天气剧场（WeatherScene）—— 说明页 Hero 互动场景
//
// 参考 justinesoulie.fr/about 实测行为（2026-10-21 用无头 Chrome 逐帧比对）：
//   1. 整幅插画由天空 / 云 / 山 / 主体 / 前景树 / 颗粒 分层叠成；
//   2. 鼠标移动时各层按「深度」位移不同幅度（越近动得越多）→ 视差纵深；
//   3. 点击画面循环切换四种天气：白天 → 夜晚 → 彩虹 → 下雨，
//      每一态同时换天空色、主体配色、文字颜色、氛围颗粒（尘埃 / 星与萤火 / 彩屑 / 雨丝）；
//   4. 页面不滚动（单屏），切换是整幅交叉淡入。
//
// 本站落地取舍：
//   · 不用 WebGL：全部 CSS/SVG 绘制，零新增依赖，方便随页面滚动；
//   · 配色守原系统棕金体系（白天暖纸、夜晚深棕、彩虹陶土粉、雨天暖灰），
//     不照搬参考站的粉紫霓虹，避免破坏站点视觉一致性；
//   · 主体用「天体圆盘 + 标语」代替手绘人物（我们没有插画资产）；
//   · 无障碍：可聚焦、← → 切天气、尊重 prefers-reduced-motion。
// ============================================================
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'

const props = defineProps({
  // hero=true：完整版（说明页）——中央圆盘 + 标语 + 天气标签；
  // hero=false：舞台版（类型混搭页）——只留天气场景当舞台，内容由 #overlay 插槽塞进来，
  //             高度改成由插槽内容撑开（海报扇多高，场景就多高）。
  hero: { type: Boolean, default: true },
  // 底部提示文案：说明页讲切天气，混搭页要同时讲清楚海报扇怎么翻
  hint: { type: String, default: '点击画面切换天气 · ← →' },
})

const STATES = [
  { key: 'day', name: '晴', kicker: '开场镜头', caption: '阳光正好，适合看一场电影' },
  { key: 'night', name: '夜', kicker: '午夜场', caption: '每一帧，都值得重看' },
  { key: 'rainbow', name: '彩虹', kicker: '片尾彩蛋', caption: '总有一个结局照亮你' },
  { key: 'rain', name: '雨', kicker: '雨天放映', caption: '雨天也有好故事' },
]

const idx = ref(0)
const sky = computed(() => STATES[idx.value].key)
const cur = computed(() => STATES[idx.value])

function go(i) { idx.value = ((i % STATES.length) + STATES.length) % STATES.length }
function next() { go(idx.value + 1) }
function prev() { go(idx.value - 1) }

// ---- 鼠标视差：归一化到 -1..1，rAF 阻尼跟随（帧率无关） ----
const scene = ref(null)
const mx = ref(0)
const my = ref(0)
let tx = 0
let ty = 0
let raf = null
let last = 0
let reduce = false

function onMove(e) {
  if (reduce || !scene.value) return
  const r = scene.value.getBoundingClientRect()
  tx = ((e.clientX - r.left) / r.width - 0.5) * 2
  ty = ((e.clientY - r.top) / r.height - 0.5) * 2
}
function reset() { tx = 0; ty = 0 }

function tick(t) {
  const dt = Math.min(64, t - (last || t)) || 16
  last = t
  const k = 1 - Math.pow(0.004, dt / 1000)
  mx.value += (tx - mx.value) * k
  my.value += (ty - my.value) * k
  raf = requestAnimationFrame(tick)
}

function onKey(e) {
  // 舞台版里方向键属于内部内容（海报扇翻片），场景不能抢
  if (!props.hero) return
  if (e.key === 'ArrowRight' || e.key === 'Enter' || e.key === ' ') { e.preventDefault(); next() }
  if (e.key === 'ArrowLeft') { e.preventDefault(); prev() }
}

// 点击画面切天气：但点到「真控件」上不算——卡片要翻片、按钮要下单，
// 不能顺手把天气也换了。舞台版靠这个做「点空白处换天气」。
const IGNORE = '.fan__card, .fan__info, .fan__ctrl, .fan__arrow, .fan__btn, .ws__tab, .ws__ctrl'
let downX = 0
let downY = 0
function onSceneDown(e) { downX = e.clientX; downY = e.clientY }
function onSceneClick(e) {
  // 拖拽/甩动之后浏览器照样会派发一次 click（起落点不同 → 目标是公共祖先），
  // 只看位移把它滤掉，否则「拖一下海报就换天气」。
  if (Math.hypot(e.clientX - downX, e.clientY - downY) > 6) return
  const t = e.target
  if (t && typeof t.closest === 'function' && t.closest(IGNORE)) return
  next()
}

// ---- 颗粒：用确定性伪随机（同序号每次刷新位置一致，避免闪烁跳动） ----
const rnd = (i, salt) => {
  const v = Math.sin((i + 1) * 12.9898 + salt * 78.233) * 43758.5453
  return v - Math.floor(v)
}
const stars = Array.from({ length: 26 }, (_, i) => ({
  x: (rnd(i, 1) * 98 + 1).toFixed(2),
  y: (rnd(i, 2) * 62 + 2).toFixed(2),
  s: (1 + rnd(i, 3) * 1.8).toFixed(2),
  d: (rnd(i, 4) * 3.2).toFixed(2),
}))
const fireflies = Array.from({ length: 7 }, (_, i) => ({
  x: (rnd(i, 5) * 84 + 8).toFixed(2),
  y: (rnd(i, 6) * 34 + 48).toFixed(2),
  d: (rnd(i, 7) * 2.6).toFixed(2),
}))
const drops = Array.from({ length: 34 }, (_, i) => ({
  x: (rnd(i, 8) * 100).toFixed(2),
  delay: (rnd(i, 9) * 1.4).toFixed(2),
  dur: (0.65 + rnd(i, 10) * 0.5).toFixed(2),
  len: (10 + rnd(i, 11) * 18).toFixed(0),
}))
const dust = Array.from({ length: 12 }, (_, i) => ({
  x: (rnd(i, 12) * 96 + 2).toFixed(2),
  y: (rnd(i, 13) * 78 + 6).toFixed(2),
  s: (2 + rnd(i, 14) * 3).toFixed(1),
  d: (rnd(i, 15) * 4).toFixed(2),
}))
const confetti = Array.from({ length: 14 }, (_, i) => ({
  x: (rnd(i, 16) * 96 + 2).toFixed(2),
  y: (rnd(i, 17) * 60 + 8).toFixed(2),
  s: (3 + rnd(i, 18) * 4).toFixed(1),
  d: (rnd(i, 19) * 3).toFixed(2),
  r: (rnd(i, 20) * 60 - 30).toFixed(0),
}))

onMounted(() => {
  reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  if (!reduce) raf = requestAnimationFrame(tick)
})
onBeforeUnmount(() => { if (raf) cancelAnimationFrame(raf) })
</script>

<template>
  <section
    ref="scene"
    class="ws"
    :class="{ 'ws--stage': !hero }"
    :data-sky="sky"
    :style="{ '--mx': mx.toFixed(3), '--my': my.toFixed(3) }"
    :tabindex="hero ? 0 : -1"
    :role="hero ? 'button' : 'group'"
    :aria-label="hero
      ? `天气场景：${cur.name}。点击或按方向键切换天气`
      : `混搭结果舞台，当前天气：${cur.name}。底部标签可切换天气`"
    @click="onSceneClick"
    @pointerdown="onSceneDown"
    @pointermove="onMove"
    @pointerleave="reset"
    @keydown="onKey"
  >
    <!-- 1. 天空：四套渐变各一层，交叉淡入（背景渐变无法 transition，只能叠层改 opacity） -->
    <div class="ws__sky ws__sky--day" />
    <div class="ws__sky ws__sky--night" />
    <div class="ws__sky ws__sky--rainbow" />
    <div class="ws__sky ws__sky--rain" />

    <!-- 2. 远层：星与萤火（夜）、雨丝（雨） -->
    <div class="ws__far">
      <span
        v-for="(s, i) in stars"
        :key="'s' + i"
        class="ws__star"
        :style="{ left: s.x + '%', top: s.y + '%', width: s.s + 'px', height: s.s + 'px', animationDelay: s.d + 's' }"
      />
      <span
        v-for="(f, i) in fireflies"
        :key="'f' + i"
        class="ws__fly"
        :style="{ left: f.x + '%', top: f.y + '%', animationDelay: f.d + 's' }"
      />
    </div>

    <!-- 3. 天体：白天太阳 / 夜晚月亮 / 雨天弱化的光斑 -->
    <div class="ws__orb" />
    <!-- 彩虹弧（仅彩虹态显形） -->
    <div class="ws__arc" aria-hidden="true" />

    <!-- 4. 云层（中景，三层不同深度） -->
    <div class="ws__clouds">
      <span class="ws__cloud ws__cloud--c1" />
      <span class="ws__cloud ws__cloud--c2" />
      <span class="ws__cloud ws__cloud--c3" />
      <span class="ws__cloud ws__cloud--c4" />
      <!-- 飞鸟：只有晴天出没，给中景一点生气 -->
      <svg class="ws__birds" viewBox="0 0 120 44" fill="none" aria-hidden="true">
        <path d="M4 20c5-6 9-6 14 0 5-6 9-6 14 0" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" />
        <path d="M46 10c4-5 7-5 11 0 4-5 7-5 11 0" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" />
        <path d="M74 30c3.5-4.5 6-4.5 9.5 0 3.5-4.5 6-4.5 9.5 0" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" />
      </svg>
    </div>

    <!-- 5. 远山与近坡 -->
    <span class="ws__hill ws__hill--far" />
    <span class="ws__hill ws__hill--near" />

    <!-- 6. 主体：天体圆盘 + 标语（圆盘是天体，标题压在它上面）；舞台版交给插槽 -->
    <div v-if="hero" class="ws__stage">
      <span class="ws__kicker">{{ cur.kicker }}</span>
      <span class="ws__disc" aria-hidden="true" />
      <!-- 视觉标语用 div：页面已有 h1（项目说明），避免标题层级重复 -->
      <div class="ws__title">
        <span>生活是场电影</span>
        <span>每个人都是主角</span>
      </div>
      <p class="ws__caption">{{ cur.caption }}</p>
    </div>

    <!-- 7. 前景灌木（深度最大，动得最多） -->
    <div class="ws__trees" aria-hidden="true">
      <span class="ws__bush ws__bush--l1" />
      <span class="ws__bush ws__bush--l2" />
      <span class="ws__bush ws__bush--r1" />
      <span class="ws__bush ws__bush--r2" />
    </div>

    <!-- 8. 颗粒：雨丝 / 尘埃 / 彩屑 -->
    <div class="ws__fx" aria-hidden="true">
      <span
        v-for="(d, i) in drops"
        :key="'d' + i"
        class="ws__drop"
        :style="{ left: d.x + '%', height: d.len + 'px', animationDelay: d.delay + 's', animationDuration: d.dur + 's' }"
      />
      <span
        v-for="(p, i) in dust"
        :key="'p' + i"
        class="ws__dust"
        :style="{ left: p.x + '%', top: p.y + '%', width: p.s + 'px', height: p.s + 'px', animationDelay: p.d + 's' }"
      />
      <span
        v-for="(c, i) in confetti"
        :key="'c' + i"
        class="ws__confetti"
        :style="{ left: c.x + '%', top: c.y + '%', width: c.s + 'px', height: (c.s * 1.6) + 'px', animationDelay: c.d + 's', transform: `rotate(${c.r}deg)` }"
      />
    </div>

    <!-- 9. 纸纹（一次性 SVG 噪声，给画面手绘质感） -->
    <div class="ws__grain" aria-hidden="true" />

    <!-- 9.5 舞台内容（类型混搭页把海报扇放这里）：不挡点击，
         点到卡片/按钮由 onSceneClick 的忽略表拦下，点到空白处才换天气 -->
    <div v-if="$slots.overlay" class="ws__overlay">
      <slot name="overlay" />
    </div>

    <!-- 10. 控件 -->
    <div class="ws__ctrl" @click.stop>
      <button
        v-for="(s, i) in STATES"
        :key="s.key"
        class="ws__tab"
        :class="{ 'is-on': i === idx }"
        type="button"
        @click="go(i)"
      >{{ s.name }}</button>
      <span class="ws__hint">{{ hint }}</span>
    </div>
  </section>
</template>

<style scoped>
/* ------- 容器 ------- */
.ws {
  --mx: 0;
  --my: 0;
  position: relative;
  height: clamp(360px, 44vw, 470px);
  margin-top: 4px;
  border-radius: 18px;
  overflow: hidden;
  isolation: isolate;
  cursor: pointer;
  outline: none;
  box-shadow: var(--shadow-lg);
  background: var(--page-bg);
}
.ws:focus-visible { box-shadow: 0 0 0 3px rgba(139, 69, 19, 0.35), var(--shadow-lg); }

/* ------- 天空：四态各一层 ------- */
.ws__sky {
  position: absolute;
  inset: 0;
  opacity: 0;
  transition: opacity 0.9s ease;
  pointer-events: none;
}
.ws[data-sky='day'] .ws__sky--day,
.ws[data-sky='night'] .ws__sky--night,
.ws[data-sky='rainbow'] .ws__sky--rainbow,
.ws[data-sky='rain'] .ws__sky--rain { opacity: 1; }

.ws__sky--day {
  background:
    radial-gradient(58% 46% at 74% 26%, rgba(255, 238, 196, 0.95), rgba(255, 238, 196, 0) 70%),
    linear-gradient(180deg, #fbf0da 0%, #f4e0bd 58%, #ecd0a4 100%);
}
.ws__sky--night {
  background:
    radial-gradient(60% 46% at 70% 24%, rgba(122, 96, 62, 0.55), rgba(122, 96, 62, 0) 72%),
    linear-gradient(180deg, #241c15 0%, #33261b 55%, #453322 100%);
}
.ws__sky--rainbow {
  background:
    radial-gradient(58% 44% at 30% 28%, rgba(255, 240, 228, 0.95), rgba(255, 240, 228, 0) 72%),
    linear-gradient(180deg, #fdeee2 0%, #f8ddcb 56%, #f0cdb8 100%);
}
.ws__sky--rain {
  background:
    radial-gradient(64% 44% at 62% 22%, rgba(196, 184, 166, 0.4), rgba(196, 184, 166, 0) 74%),
    linear-gradient(180deg, #7a7268 0%, #645c53 55%, #4e4740 100%);
}

/* ------- 远层颗粒 ------- */
.ws__far { position: absolute; inset: 0; pointer-events: none; }
.ws__star,
.ws__fly {
  position: absolute;
  border-radius: 50%;
  opacity: 0;
  transition: opacity 0.8s ease;
}
.ws__star {
  background: #f6e3b4;
  box-shadow: 0 0 6px rgba(246, 227, 180, 0.8);
  animation: ws-twinkle 3.4s ease-in-out infinite;
}
.ws[data-sky='night'] .ws__star { opacity: 0.9; }
.ws__fly {
  width: 5px; height: 5px;
  background: #ffd479;
  box-shadow: 0 0 10px 2px rgba(255, 212, 121, 0.85);
  animation: ws-float 6s ease-in-out infinite;
}
.ws[data-sky='night'] .ws__fly { opacity: 0.95; }

/* ------- 天体 ------- */
.ws__orb {
  position: absolute;
  top: 16%;
  right: 13%;
  width: clamp(74px, 9vw, 118px);
  aspect-ratio: 1;
  border-radius: 50%;
  transform: translate3d(calc(var(--mx) * -10px), calc(var(--my) * -10px), 0);
  transition: background 0.9s ease, box-shadow 0.9s ease, opacity 0.9s ease;
}
.ws[data-sky='day'] .ws__orb {
  background: radial-gradient(circle at 34% 30%, #ffe6a8, #e8b84b 62%, #dda63a 100%);
  box-shadow: 0 0 90px 34px rgba(232, 184, 75, 0.42);
}
.ws[data-sky='night'] .ws__orb {
  background: radial-gradient(circle at 36% 32%, #fff8e4, #f0dcae 66%, #ddc493 100%);
  box-shadow: 0 0 70px 22px rgba(240, 220, 174, 0.28);
}
.ws[data-sky='rainbow'] .ws__orb {
  background: radial-gradient(circle at 36% 32%, #fff6ec, #f7dcc6 70%, #eec9ac 100%);
  box-shadow: 0 0 80px 26px rgba(238, 201, 172, 0.4);
}
.ws[data-sky='rain'] .ws__orb {
  /* 阴天没有天体，只留一层极淡的散射光，避免"云后挂着一个球" */
  background: radial-gradient(circle at 36% 32%, rgba(240, 235, 226, 0.16), rgba(214, 206, 194, 0) 72%);
  box-shadow: none;
  opacity: 0.65;
}

/* 彩虹弧：只有彩虹态显形 */
.ws__arc {
  position: absolute;
  left: 50%;
  bottom: 16%;
  width: min(88%, 940px);
  height: 460px;
  transform: translate(-50%, 0) translate3d(calc(var(--mx) * -6px), calc(var(--my) * -6px), 0);
  border-radius: 50% 50% 0 0 / 100% 100% 0 0;
  opacity: 0;
  transition: opacity 1s ease;
  background: conic-gradient(from 270deg at 50% 100%, #b5502f, #d2691e, #e8b84b, #cbb08a, #8ba58a, #5f7a61, #b5502f);
  -webkit-mask: radial-gradient(50% 100% at 50% 100%, transparent 62%, #000 63%, #000 82%, transparent 83%);
  mask: radial-gradient(50% 100% at 50% 100%, transparent 62%, #000 63%, #000 82%, transparent 83%);
  pointer-events: none;
}
.ws[data-sky='rainbow'] .ws__arc { opacity: 0.72; }

/* ------- 云 ------- */
.ws__clouds { position: absolute; inset: 0; pointer-events: none; }
.ws__cloud {
  position: absolute;
  border-radius: 999px;
  background: #fffdf7;
  transition: background 0.9s ease, opacity 0.9s ease;
  filter: blur(0.4px);
}
.ws__cloud::before,
.ws__cloud::after {
  content: '';
  position: absolute;
  border-radius: 50%;
  background: inherit;
}
.ws__cloud::before { width: 62%; height: 150%; left: 12%; top: -74%; }
.ws__cloud::after { width: 46%; height: 122%; right: 10%; top: -52%; }

.ws__cloud--c1 {
  width: 168px; height: 46px; left: 6%; top: 16%;
  transform: translate3d(calc(var(--mx) * -7px), calc(var(--my) * -5px), 0);
  opacity: 0.9;
}
.ws__cloud--c2 {
  width: 232px; height: 58px; right: 3%; top: 42%;
  transform: translate3d(calc(var(--mx) * -9px), calc(var(--my) * -6px), 0);
  opacity: 0.82;
}
.ws__cloud--c3 {
  width: 138px; height: 40px; left: 24%; top: 46%;
  transform: translate3d(calc(var(--mx) * -11px), calc(var(--my) * -8px), 0);
  opacity: 0.75;
}
.ws__cloud--c4 {
  width: 200px; height: 50px; right: 24%; top: 10%;
  transform: translate3d(calc(var(--mx) * -6px), calc(var(--my) * -4px), 0);
  opacity: 0.7;
}
.ws[data-sky='night'] .ws__cloud { background: #3f3226; opacity: 0.42; }
.ws[data-sky='rain'] .ws__cloud { background: #8d8579; opacity: 0.55; }
.ws[data-sky='rainbow'] .ws__cloud { background: #fff6ef; }

/* 飞鸟 */
.ws__birds {
  position: absolute;
  left: 17%;
  top: 22%;
  width: clamp(84px, 8vw, 118px);
  height: auto;
  color: #8a6a48;
  opacity: 0;
  transition: opacity 0.9s ease;
  transform: translate3d(calc(var(--mx) * -8px), calc(var(--my) * -5px), 0);
}
.ws[data-sky='day'] .ws__birds { opacity: 0.5; }

/* ------- 山与坡 ------- */
.ws__hill {
  position: absolute;
  left: -12%;
  width: 124%;
  border-radius: 50% 50% 0 0 / 100% 100% 0 0;
  pointer-events: none;
  transition: background 0.9s ease;
}
.ws__hill--far {
  bottom: -6%;
  height: 42%;
  background: #d9c19a;
  transform: translate3d(calc(var(--mx) * -9px), calc(var(--my) * -4px), 0);
}
.ws__hill--near {
  bottom: -14%;
  left: -22%;
  width: 144%;
  height: 40%;
  background: #c2a57c;
  transform: translate3d(calc(var(--mx) * -14px), calc(var(--my) * -6px), 0);
}
.ws[data-sky='night'] .ws__hill--far { background: #3d2e21; }
.ws[data-sky='night'] .ws__hill--near { background: #2b2018; }
.ws[data-sky='rainbow'] .ws__hill--far { background: #e6c6b2; }
.ws[data-sky='rainbow'] .ws__hill--near { background: #d3ab94; }
.ws[data-sky='rain'] .ws__hill--far { background: #544b42; }
.ws[data-sky='rain'] .ws__hill--near { background: #403830; }

/* ------- 主体：圆盘 + 标语 ------- */
.ws__stage {
  position: absolute;
  inset: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 2px;
  text-align: center;
  transform: translate3d(calc(var(--mx) * -17px), calc(var(--my) * -11px), 0);
}
.ws__disc {
  position: absolute;
  width: clamp(190px, 24vw, 300px);
  aspect-ratio: 1;
  border-radius: 50%;
  transition: background 0.9s ease, opacity 0.9s ease;
  z-index: 0;
}
.ws[data-sky='day'] .ws__disc { background: transparent; }
.ws[data-sky='night'] .ws__disc {
  background: radial-gradient(circle at 40% 34%, #8a6440, #6d4d30 70%, #5b3f27 100%);
  box-shadow: 0 0 48px rgba(109, 77, 48, 0.55);
}
.ws[data-sky='rainbow'] .ws__disc {
  background: radial-gradient(circle at 40% 34%, #a9714f, #8b5a3e 72%, #77492f 100%);
  box-shadow: 0 0 42px rgba(139, 90, 62, 0.4);
}
.ws[data-sky='rain'] .ws__disc {
  background: radial-gradient(circle at 40% 34%, rgba(122, 112, 100, 0.75), rgba(90, 82, 73, 0.7) 72%, rgba(70, 64, 57, 0.65) 100%);
}

.ws__kicker {
  position: relative;
  z-index: 1;
  font-size: 11px;
  letter-spacing: 0.34em;
  font-weight: 700;
  color: var(--dark-brown);
  opacity: 0.7;
  margin-bottom: 6px;
  transition: color 0.9s ease;
}
.ws__title {
  position: relative;
  z-index: 1;
  margin: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
  font-family: 'HarmonyOS Sans', 'Source Han Sans SC', 'Noto Sans SC', system-ui, sans-serif;
  font-size: clamp(28px, 3.6vw, 46px);
  font-weight: 900;
  letter-spacing: 0.06em;
  line-height: 1.18;
  color: #7b4a24;
  text-shadow: 0 2px 0 rgba(255, 255, 255, 0.35);
  transition: color 0.9s ease, text-shadow 0.9s ease;
}
.ws[data-sky='night'] .ws__kicker { color: #f0dcae; opacity: 0.75; }
.ws[data-sky='night'] .ws__title { color: #f7e7c4; text-shadow: 0 2px 10px rgba(0, 0, 0, 0.45); }
.ws[data-sky='rainbow'] .ws__kicker { color: #fbe6d6; opacity: 0.85; }
.ws[data-sky='rainbow'] .ws__title { color: #fdf3ea; text-shadow: 0 2px 12px rgba(74, 40, 20, 0.45); }
.ws[data-sky='rainbow'] .ws__caption { color: #fbe8da; opacity: 0.86; }
.ws[data-sky='rain'] .ws__kicker { color: #f2ece2; opacity: 0.8; }
.ws[data-sky='rain'] .ws__title { color: #fdf8ef; text-shadow: 0 2px 12px rgba(0, 0, 0, 0.4); }

.ws__caption {
  position: relative;
  z-index: 1;
  margin: 10px 0 0;
  font-size: clamp(12px, 1.05vw, 14px);
  letter-spacing: 0.16em;
  color: var(--dark-brown);
  opacity: 0.72;
  transition: color 0.9s ease;
}
.ws[data-sky='night'] .ws__caption,
.ws[data-sky='rain'] .ws__caption { color: #f4ead8; opacity: 0.8; }

/* ------- 前景灌木 ------- */
.ws__trees { position: absolute; inset: 0; pointer-events: none; }
.ws__bush {
  position: absolute;
  border-radius: 50%;
  transition: background 0.9s ease;
}
.ws__bush::after,
.ws__bush::before {
  content: '';
  position: absolute;
  border-radius: 50%;
  background: inherit;
}
.ws__bush--l1 {
  width: clamp(96px, 16%, 220px); aspect-ratio: 1.22; left: -4%; bottom: -12%;
  background: #8b7355;
  transform: translate3d(calc(var(--mx) * -26px), calc(var(--my) * -10px), 0);
}
.ws__bush--l1::before { width: 62%; height: 62%; left: 34%; top: -34%; }
.ws__bush--l2 {
  width: clamp(62px, 9.2%, 128px); aspect-ratio: 1.23; left: 7%; bottom: -9%;
  background: #9c8364;
  transform: translate3d(calc(var(--mx) * -32px), calc(var(--my) * -12px), 0);
}
.ws__bush--r1 {
  width: clamp(112px, 18.7%, 260px); aspect-ratio: 1.3; right: -5%; bottom: -13%;
  background: #7f684d;
  transform: translate3d(calc(var(--mx) * -28px), calc(var(--my) * -11px), 0);
}
.ws__bush--r1::before { width: 54%; height: 54%; right: 30%; top: -30%; }
.ws__bush--r2 {
  width: clamp(72px, 10.8%, 150px); aspect-ratio: 1.29; right: 8.5%; bottom: -9%;
  background: #93795c;
  transform: translate3d(calc(var(--mx) * -34px), calc(var(--my) * -13px), 0);
}
.ws[data-sky='night'] .ws__bush--l1 { background: #221a13; }
.ws[data-sky='night'] .ws__bush--l2 { background: #2c2117; }
.ws[data-sky='night'] .ws__bush--r1 { background: #1c150f; }
.ws[data-sky='night'] .ws__bush--r2 { background: #271d15; }
.ws[data-sky='rainbow'] .ws__bush--l1 { background: #c79a86; }
.ws[data-sky='rainbow'] .ws__bush--l2 { background: #d8ad99; }
.ws[data-sky='rainbow'] .ws__bush--r1 { background: #bb8d7a; }
.ws[data-sky='rainbow'] .ws__bush--r2 { background: #cda190; }
.ws[data-sky='rain'] .ws__bush--l1 { background: #3b342d; }
.ws[data-sky='rain'] .ws__bush--l2 { background: #47403a; }
.ws[data-sky='rain'] .ws__bush--r1 { background: #322c26; }
.ws[data-sky='rain'] .ws__bush--r2 { background: #3f3831; }

/* ------- 颗粒 ------- */
.ws__fx { position: absolute; inset: 0; pointer-events: none; }
.ws__drop,
.ws__dust,
.ws__confetti { position: absolute; opacity: 0; }

.ws__drop {
  top: -12%;
  width: 1.5px;
  border-radius: 2px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0), rgba(255, 255, 255, 0.75));
  animation: ws-fall linear infinite;
}
.ws[data-sky='rain'] .ws__drop { opacity: 0.75; }

.ws__dust {
  border-radius: 50%;
  background: radial-gradient(circle, rgba(255, 244, 214, 0.95), rgba(255, 244, 214, 0) 70%);
  animation: ws-float 7s ease-in-out infinite;
}
.ws[data-sky='day'] .ws__dust { opacity: 0.9; }

.ws__confetti {
  border-radius: 2px;
  background: linear-gradient(160deg, #d2691e, #e8b84b);
  animation: ws-drift 5.5s ease-in-out infinite;
}
.ws[data-sky='rainbow'] .ws__confetti { opacity: 0.85; }
.ws[data-sky='rainbow'] .ws__confetti:nth-child(3n) { background: linear-gradient(160deg, #5f7a61, #8ba58a); }
.ws[data-sky='rainbow'] .ws__confetti:nth-child(4n) { background: linear-gradient(160deg, #b5502f, #d99b6c); }

/* ------- 纸纹 ------- */
.ws__grain {
  position: absolute;
  inset: 0;
  pointer-events: none;
  opacity: 0.16;
  mix-blend-mode: multiply;
  background-image: url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='140' height='140'><filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='2' stitchTiles='stitch'/><feColorMatrix type='saturate' values='0'/></filter><rect width='140' height='140' filter='url(%23n)' opacity='0.5'/></svg>");
}
.ws[data-sky='night'] .ws__grain { opacity: 0.1; mix-blend-mode: screen; }

/* ------- 控件 ------- */
.ws__ctrl {
  position: absolute;
  left: 18px;
  bottom: 16px;
  display: flex;
  align-items: center;
  gap: 8px;
  z-index: 3;
  cursor: default;
}
.ws__tab {
  border: 1px solid rgba(107, 79, 58, 0.28);
  background: rgba(255, 253, 247, 0.66);
  color: var(--dark-brown);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
  padding: 5px 12px;
  border-radius: 999px;
  cursor: pointer;
  backdrop-filter: blur(4px);
  transition: background 0.25s ease, color 0.25s ease, transform 0.25s ease, border-color 0.25s ease;
}
.ws__tab:hover { transform: translateY(-1px); border-color: rgba(139, 69, 19, 0.5); }
.ws__tab.is-on {
  background: linear-gradient(135deg, #8b4513, #a0522d);
  border-color: transparent;
  color: #fff8ec;
}
.ws__hint {
  margin-left: 4px;
  font-size: 11px;
  letter-spacing: 0.06em;
  color: var(--dark-brown);
  opacity: 0.55;
}
.ws[data-sky='night'] .ws__hint,
.ws[data-sky='rain'] .ws__hint { color: #f4ead8; opacity: 0.7; }

/* ------- 动画 ------- */
@keyframes ws-twinkle {
  0%, 100% { opacity: 0.35; transform: scale(0.85); }
  50% { opacity: 1; transform: scale(1.15); }
}
@keyframes ws-float {
  0%, 100% { transform: translate3d(0, 0, 0); }
  50% { transform: translate3d(6px, -12px, 0); }
}
@keyframes ws-fall {
  0% { transform: translate3d(0, 0, 0); }
  100% { transform: translate3d(-26px, 560px, 0); }
}
@keyframes ws-drift {
  0%, 100% { transform: translate3d(0, 0, 0) rotate(0deg); }
  50% { transform: translate3d(10px, -14px, 0) rotate(18deg); }
}

/* ------- 响应式 ------- */
@media (max-width: 860px) {
  .ws { height: clamp(300px, 62vw, 400px); border-radius: 14px; }
  .ws__disc { width: clamp(150px, 44vw, 200px); }
  .ws__orb { width: 56px; top: 11%; right: 9%; }
  .ws__title { font-size: 25px; letter-spacing: 0.04em; }
  .ws__caption { margin-top: 8px; font-size: 11.5px; letter-spacing: 0.1em; }
  .ws__arc { height: 300px; }
  .ws__hint { display: none; }
  .ws__ctrl { left: 12px; bottom: 12px; gap: 6px; }
  .ws__tab { padding: 4px 10px; font-size: 11px; }
  .ws__cloud--c3, .ws__cloud--c4 { display: none; }
}
@media (prefers-reduced-motion: reduce) {
  .ws__star, .ws__fly, .ws__dust, .ws__confetti, .ws__drop { animation: none; }
  .ws__sky, .ws__orb, .ws__arc, .ws__disc, .ws__cloud, .ws__hill, .ws__bush { transition-duration: 0.2s; }
}

/* ------- 舞台模式（类型混搭页） -------
   高度不再写死，交给插槽内容撑开：海报扇多高，天空就多高，
   移动端也不会出现「场景比内容矮一截」或「空出一大片」。 */
.ws--stage {
  height: auto;
  min-height: 470px;
  cursor: default;
}
.ws__overlay {
  position: relative;
  z-index: 6;
  padding: 10px 10px 58px;
}
/* 雨丝/尘埃走到海报前面：雨被扇子挡在背后就没了沉浸感 */
.ws--stage .ws__fx { z-index: 7; }
/* 舞台比说明页高一倍，天体照原比例会被海报挡个正着，抬到天上才看得见 */
.ws--stage .ws__orb { top: 8%; right: 7%; }
.ws--stage[data-sky='rain'] .ws__drop { opacity: 0.5; }
/* 占位卡面跟着天气走：夜里一张米色纸卡会亮得像贴了灯箱 */
.ws[data-sky='night'] :deep(.fan__ph) {
  background: linear-gradient(150deg, #443421 0%, #362a1b 55%, #2a2015 100%);
}
.ws[data-sky='night'] :deep(.fan__ph-ch) { color: rgba(247, 231, 196, 0.14); text-shadow: none; }
.ws[data-sky='night'] :deep(.fan__ph-name) { color: rgba(247, 231, 196, 0.38); }
.ws[data-sky='night'] :deep(.fan__ph-skel) { opacity: 0.3; }
.ws[data-sky='rain'] :deep(.fan__ph) { filter: brightness(0.72) saturate(0.72); }
/* 彩虹弧整条抬到海报行上方：放在扇子后面只会被切成几块橘斑，
   压扁成一道横跨天空的浅拱，反而一眼认出是"虹"。 */
.ws--stage[data-sky='rainbow'] .ws__arc {
  bottom: 72%;
  width: min(78%, 980px);
  height: 210px;
  opacity: 0.82;
  filter: saturate(1.35) brightness(1.04);
  -webkit-mask: radial-gradient(50% 100% at 50% 100%, transparent 66%, #000 68%, #000 79%, transparent 81%);
  mask: radial-gradient(50% 100% at 50% 100%, transparent 66%, #000 68%, #000 79%, transparent 81%);
}
/* 天气标签挪到正中下方，避开海报扇自己的翻片按钮；z 要压在插槽层之上，
   否则会被 .ws__overlay 的留白盖住点不到 */
.ws--stage .ws__ctrl {
  left: 50%;
  bottom: 14px;
  transform: translateX(-50%);
  white-space: nowrap;
  z-index: 8;
}
@media (max-width: 860px) {
  .ws--stage { min-height: 420px; border-radius: 16px; }
  .ws__overlay { padding: 6px 2px 50px; }
  .ws--stage .ws__ctrl { left: 50%; bottom: 10px; }
}
</style>
