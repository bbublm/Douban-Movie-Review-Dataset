<template>
  <div class="echo">
    <!-- ===== 情感三分布：极细半透明圆环 + 动态描边 ===== -->
    <div class="echo__ring">
      <svg viewBox="0 0 120 120" class="echo__svg">
        <!-- 底轨：极淡的整圈 -->
        <circle class="echo__track" cx="60" cy="60" r="52" />
        <!-- 扫描环：缓慢旋转的虚线，制造"仪表扫描"感 -->
        <circle class="echo__scan" cx="60" cy="60" r="59" />
        <!-- 数据段：三段留缝（学习 sc-datav 的分段留白手法） -->
        <circle
          v-for="(s, i) in segs"
          :key="s.key"
          class="echo__seg"
          :class="`is-${s.key}`"
          cx="60" cy="60" r="52"
          :style="drawn ? {
            strokeDasharray: `${s.len} ${CIRC - s.len}`,
            strokeDashoffset: -s.offset,
            transitionDelay: `${i * 120}ms`,
          } : { strokeDasharray: `0 ${CIRC}` }"
        />
      </svg>
      <div class="echo__center">
        <div class="echo__value">
          <RollingNumber :value="positivePct" :decimals="1" suffix="%" :duration="1600" />
        </div>
        <div class="echo__label">正面率</div>
      </div>
    </div>

    <!-- 三段图例 -->
    <div class="echo__legend">
      <span v-for="s in segs" :key="s.key" class="echo__lg">
        <i :class="`is-${s.key}`" />{{ s.name }}
        <b>{{ s.count.toLocaleString() }}</b>
      </span>
    </div>

    <!-- ===== 归纳词典：正负热词 ===== -->
    <div class="echo__sub">
      <i class="echo__bar" />
      <span class="echo__sub-zh">归纳词典 · 情感极性词</span>
      <span class="echo__sub-en">按极性强度排序</span>
      <i class="echo__line" />
    </div>

    <div class="echo__words">
      <div v-for="w in words" :key="w.k + w.word" class="echo__word">
        <span class="echo__w-zh">{{ w.zh }}</span>
        <span class="echo__w-bar">
          <i :class="w.k === 'pos' ? 'is-pos' : 'is-neg'" :style="{ width: drawn ? w.pct + '%' : '0%' }" />
        </span>
      </div>
    </div>
  </div>
</template>

<script setup>
// ============================================================
// 左翼 · 跨文化回声廊
//   · 极细半透明圆环（stroke-width 3）+ 分段留缝 + 描边动画
//     —— 手法参照开源大屏项目 knight-L/sc-datav（分段留白 + 发光）
//   · 中心数字用 countup.js 滚动
//   · 词典热词：真实归纳式词典 log-odds 分值，中文译名仅辅助阅读
// ============================================================
import { computed, onMounted, ref } from 'vue'
import RollingNumber from './RollingNumber.vue'
import { toZh } from '../../utils/wordZhMap'

const props = defineProps({
  sentiment: { type: Object, default: null },
  lexicon: { type: Object, default: null },
})

const R = 52
const CIRC = 2 * Math.PI * R
const GAP = 5            // 段间留缝（视觉上更像仪表而非饼图）
const drawn = ref(false)
onMounted(() => requestAnimationFrame(() => { drawn.value = true }))

const NAME = { positive: '正面', negative: '负面', unknown: '中性' }
const ORDER = ['positive', 'negative', 'unknown']

const total = computed(() =>
  (props.sentiment?.buckets || []).reduce((a, b) => a + (b.count || 0), 0) || 1)

const segs = computed(() => {
  const map = new Map((props.sentiment?.buckets || []).map((b) => [b.key, b.count || 0]))
  let offset = 0
  return ORDER
    .filter((k) => map.has(k))
    .map((k) => {
      const count = map.get(k)
      const raw = (count / total.value) * CIRC
      const len = Math.max(0, raw - GAP)
      const seg = { key: k, name: NAME[k] || k, count, len, offset }
      offset += raw
      return seg
    })
})

const positivePct = computed(() => (props.sentiment?.positive_ratio ?? 0) * 100)

/* 正负热词各取 6 个，交替排列更直观；条长按 |score| 归一化。
   界面全中文：英文词经译名表转中文，多个英文词译同中文时只保留首个。 */
const words = computed(() => {
  const pos = (props.lexicon?.top_positive || []).slice(0, 6)
  const neg = (props.lexicon?.top_negative || []).slice(0, 6)
  const max = Math.max(
    0.001,
    ...pos.map((w) => Math.abs(w.score)),
    ...neg.map((w) => Math.abs(w.score)),
  )
  const out = []
  const seen = new Set()
  for (let i = 0; i < 6; i++) {
    for (const [list, k] of [[pos, 'pos'], [neg, 'neg']]) {
      const w = list[i]
      if (!w) continue
      const zh = toZh(w.word) || w.word
      if (seen.has(zh)) continue
      seen.add(zh)
      out.push({ k, word: w.word, score: w.score, pct: Math.abs(w.score) / max * 100, zh })
    }
  }
  return out
})
</script>

<style scoped>
.echo { display: flex; flex-direction: column; min-height: 0; height: 100%; }

/* ---------- 细圆环 ---------- */
.echo__ring {
  position: relative;
  flex: none;
  height: 168px;
  display: grid;
  place-items: center;
  margin-top: 4px;
}
.echo__svg { width: 168px; height: 168px; transform: rotate(-90deg); overflow: visible; }
.echo__track {
  fill: none;
  stroke: rgba(201, 169, 110, 0.1);
  stroke-width: 3;
}
.echo__scan {
  fill: none;
  stroke: rgba(201, 169, 110, 0.35);
  stroke-width: 1;
  stroke-dasharray: 2 7;
  transform-origin: 60px 60px;
  animation: echo-spin 14s linear infinite;
}
@keyframes echo-spin { to { transform: rotate(360deg); } }
.echo__seg {
  fill: none;
  stroke-width: 3;
  stroke-linecap: round;
  transition: stroke-dasharray 1.25s cubic-bezier(0.16, 0.84, 0.44, 1),
              stroke-dashoffset 1.25s cubic-bezier(0.16, 0.84, 0.44, 1);
}
.echo__seg.is-positive { stroke: #C2410C; filter: drop-shadow(0 0 5px rgba(194, 65, 12, 0.45)); }
.echo__seg.is-negative { stroke: #0F766E; filter: drop-shadow(0 0 5px rgba(15, 118, 110, 0.45)); }
.echo__seg.is-unknown  { stroke: rgba(139, 149, 165, 0.6); }

.echo__center { position: absolute; inset: 0; display: grid; place-content: center; text-align: center; }
.echo__value {
  font-family: var(--u-font-tech);
  font-size: 30px;
  font-weight: 700;
  color: #3A2E20;
  text-shadow: 0 0 16px rgba(201, 169, 110, 0.4);
  font-variant-numeric: tabular-nums;
}
.echo__label {
  margin-top: 4px;
  font-size: 10px;
  letter-spacing: 2px;
  color: var(--u-text-2);
}

/* ---------- 图例 ---------- */
.echo__legend {
  flex: none;
  display: flex;
  flex-wrap: wrap;
  gap: 6px 14px;
  justify-content: center;
  padding: 6px 0 10px;
}
.echo__lg { display: inline-flex; align-items: center; gap: 6px; font-size: 11px; color: var(--u-text-2); }
.echo__lg b { color: #3A2E20; font-family: var(--u-font-tech); font-weight: 600; }
.echo__lg i { width: 7px; height: 7px; border-radius: 50%; }
.echo__lg i.is-positive { background: #C2410C; box-shadow: 0 0 6px rgba(194, 65, 12, 0.5); }
.echo__lg i.is-negative { background: #0F766E; box-shadow: 0 0 6px rgba(15, 118, 110, 0.5); }
.echo__lg i.is-unknown { background: rgba(139, 149, 165, 0.7); }

/* ---------- 小标题 ---------- */
.echo__sub {
  flex: none;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 10px 0 8px;
  border-top: 1px solid rgba(201, 169, 110, 0.14);
}
.echo__bar { width: 3px; height: 12px; background: linear-gradient(to bottom, var(--u-orange), rgba(194, 65, 12, 0.12)); }
.echo__sub-zh { font-size: 12.5px; font-weight: 700; letter-spacing: 1px; color: #3A2E20; }
.echo__sub-en { font-family: var(--u-font-tech); font-size: 9px; letter-spacing: 1.4px; color: rgba(125, 107, 82, 0.9); }
.echo__line { flex: 1; height: 1px; background: linear-gradient(to right, var(--u-line), transparent); position: relative; overflow: hidden; }
/* 标题线扫光：一小段暖橙光点周期性流过（sc-datav 头部扫光移植） */
.echo__line::after {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  width: 28%;
  height: 100%;
  background: linear-gradient(90deg, transparent, var(--u-orange), transparent);
  animation: u-line-sweep 3.4s ease-in-out infinite;
}
@keyframes u-line-sweep {
  0% { transform: translateX(-110%); }
  100% { transform: translateX(360%); }
}

/* ---------- 热词 ---------- */
.echo__words {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 7px;
  overflow: hidden;
}
.echo__word {
  display: grid;
  grid-template-columns: 66px 1fr 96px;
  align-items: center;
  gap: 8px;
  font-size: 11.5px;
}
.echo__w-zh { color: var(--u-text); font-weight: 600; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.echo__w-bar { height: 4px; background: rgba(120, 90, 50, 0.06); clip-path: polygon(2px 0, 100% 0, calc(100% - 2px) 100%, 0 100%); }
.echo__w-bar i {
  display: block;
  height: 100%;
  transition: width 1.1s cubic-bezier(0.16, 0.84, 0.44, 1);
}
.echo__w-bar i.is-pos { background: linear-gradient(to right, rgba(194, 65, 12, 0.22), #D9903A); box-shadow: 0 0 8px rgba(194, 65, 12, 0.35); }
.echo__w-bar i.is-neg { background: linear-gradient(to right, rgba(15, 118, 110, 0.25), #0F766E); box-shadow: 0 0 8px rgba(15, 118, 110, 0.35); }

@media (prefers-reduced-motion: reduce) {
  .echo__scan { animation: none; }
}
</style>
