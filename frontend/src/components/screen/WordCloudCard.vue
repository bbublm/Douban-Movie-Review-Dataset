<template>
  <div class="wcloud">
    <div class="wcloud__head">
      <span class="wcloud__head-zh">情感词典</span>
      <span class="wcloud__head-en">真实影评归纳</span>
      <span class="wcloud__head-hint">金 = 好评侧 · 蓝 = 差评侧</span>
    </div>
    <div class="wcloud__body">
      <div ref="el" class="wcloud__chart" />
      <p v-if="!words.length" class="wcloud__empty">词典加载中…</p>
    </div>
    <p class="wcloud__foot">
      从 {{ docs.toLocaleString() }} 条真实影评归纳：log(P(w|好评)/P(w|差评)) × df/(df+k) 收缩
    </p>
  </div>
</template>

<script setup>
// ============================================================
// 左翼 · 情感词典词云（echarts-wordcloud 复用）
// ------------------------------------------------------------
// 数据：/insights/lexicon（分析层产物，词 + 权重 + 正负侧）
// 颜色按侧别：好评侧金色系，差评侧冷蓝系；字号 = |权重|。
// 界面全中文：英文情感词经展示层译名表（wordZhMap）转中文，
// 未收录的词（多为导演/演员专名）保留原文 —— 专名翻不出意义。
// ============================================================
import { computed, watch } from 'vue'
import { useChart } from './useChart.js'
import { toZh } from '../../utils/wordZhMap.js'

const props = defineProps({
  // /insights/lexicon 的返回：{ meta:{docs,...}, size, top_positive:[{word,score}], top_negative:[...] }
  lexicon: { type: Object, default: null },
})

const docs = computed(() => props.lexicon?.meta?.docs || 0)

const words = computed(() => {
  const lex = props.lexicon || {}
  const pick = (list, side) =>
    (list || [])
      .filter((w) => w && w.word)
      .map((w) => ({ name: toZh(w.word) || w.word, value: Math.max(1, Math.abs(w.score || 1)), side }))
  // 多个英文词可能译成同一个中文词：按分值高的在前，去重避免词云里出现重复字
  const seen = new Set()
  return [...pick(lex.top_positive, 'positive'), ...pick(lex.top_negative, 'negative')]
    .filter((w) => (seen.has(w.name) ? false : seen.add(w.name) && true))
})

/* 增彩配色（2026-10-19 浅色版）：好评侧深暖橙金、差评侧深青蓝 */
const PALETTE = {
  positive: ['#D9903A', '#B45309', '#C2410C', '#A67C2E'],
  negative: ['#0E7490', '#0F766E', '#0369A1', '#4A7FB5'],
}

function buildOption() {
  const data = words.value
  const hasPos = data.some((d) => d.side === 'positive')
  const hasNeg = data.some((d) => d.side === 'negative')
  return {
    series: [{
      type: 'wordCloud',
      shape: 'circle',
      sizeRange: [14, 40],
      rotationRange: [-32, 32],
      rotationStep: 16,
      gridSize: 7,
      drawOutOfBound: false,
      layoutAnimation: true,
      textStyle: {
        fontFamily: '"PingFang SC", "Microsoft YaHei", sans-serif',
        fontWeight: 600,
        // 颜色回调：按词的正负侧取色（echarts-wordcloud 每次绘制回调一次）
        color: () => {
          let pool = PALETTE.positive
          if (hasNeg && (!hasPos || Math.random() < 0.42)) pool = PALETTE.negative
          return pool[Math.floor(Math.random() * pool.length)]
        },
      },
      data,
      emphasis: {
        textStyle: { textShadowBlur: 10, textShadowColor: 'rgba(194, 65, 12, 0.35)' },
      },
    }],
  }
}

const option = computed(buildOption)
const { el, set } = useChart(() => option.value)
watch(option, (o) => set(o))
</script>

<style scoped>
.wcloud { display: flex; flex-direction: column; height: 100%; min-height: 0; }

.wcloud__head { flex: none; display: flex; align-items: baseline; gap: 8px; }
.wcloud__head-zh { font-size: 13px; font-weight: 700; letter-spacing: 1.5px; color: var(--u-text); }
.wcloud__head-en { font-family: var(--u-font-tech); font-size: 9px; letter-spacing: 1.4px; color: rgba(125, 107, 82, 0.9); text-transform: uppercase; }
.wcloud__head-hint { margin-left: auto; font-size: 10px; color: rgba(125, 107, 82, 0.9); }

.wcloud__body { position: relative; flex: 1; min-height: 0; margin-top: 6px; }
.wcloud__chart { position: absolute; inset: 0; }
.wcloud__empty { position: absolute; inset: 0; display: grid; place-items: center; font-size: 12px; color: var(--u-text-2); }

.wcloud__foot { flex: none; margin: 8px 0 0; font-size: 10.5px; color: rgba(125, 107, 82, 0.9); }
</style>
