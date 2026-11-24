<script setup>
// ============================================================
// 检索页右侧辅助面板（功能清单 P1 ×3）。
//
// 三条数据都坚持「能说清来源」：
// 1. 影评高频词 —— 全站 49,873 条影评经情感词典归纳的真实高频词
//    （/insights/topics）。Kaggle 影评没有片名/id，做不到「当前查询
//    相关的词」，所以明确标注是全站口径，不冒充局部统计。
// 2. 口碑温度计 —— 当前命中影片的评分均值。清单写的是「整体情感」，
//    但影评无法按影片关联（同上），用影片侧 vote_average 均值替代，
//    口径写在标题旁，不混淆。
// 3. 相关搜索 —— 从当前结果电影的类型/年代/导演派生，真实可点。
// ============================================================
import { computed, onMounted, ref } from 'vue'
import { api } from '../../api'

const props = defineProps({
  movies: { type: Array, default: () => [] },
  total: { type: Number, default: 0 },
})
const emit = defineEmits(['search'])

// ---- 1. 影评高频词（全站真实统计）----
const words = ref([])
const wordTotal = ref(0)
onMounted(async () => {
  try {
    const d = await api.topics()
    wordTotal.value = d?.docs || 0
    words.value = (d?.keywords || []).slice(0, 30)
  } catch {
    /* 面板是辅助信息，失败就不显示，不影响主检索流程 */
  }
})

// 词大小分三档：用 df 在全量里的相对位置，不拍脑袋
const wordSize = (w) => {
  const top = words.value[0]?.df || 1
  const r = (w.df || 0) / top
  return r > 0.5 ? 'lg' : r > 0.2 ? 'md' : 'sm'
}

// ---- 2. 口碑温度计（当前结果影片均分）----
const rated = computed(() => props.movies.filter((m) => m.rating > 0))
const avgRating = computed(() => {
  if (!rated.value.length) return null
  const sum = rated.value.reduce((s, m) => s + m.rating, 0)
  return sum / rated.value.length
})
const gaugePct = computed(() => Math.round((avgRating.value || 0) * 10))
const gaugeLevel = computed(() => {
  const r = avgRating.value || 0
  if (r >= 8) return { label: '口碑出众', cls: 'is-high' }
  if (r >= 7) return { label: '口碑良好', cls: 'is-good' }
  if (r >= 6) return { label: '口碑平平', cls: 'is-mid' }
  return { label: '口碑偏弱', cls: 'is-low' }
})

// ---- 3. 相关搜索（从当前结果派生）----
const related = computed(() => {
  const out = []
  const seen = new Set()
  const push = (label, q) => {
    if (out.length >= 6 || seen.has(label)) return
    seen.add(label)
    out.push({ label, q })
  }
  // 年代：取当前结果里出现最多的年份段
  const decadeCount = {}
  props.movies.forEach((m) => {
    if (!m.year) return
    const d = `${Math.floor(m.year / 10) * 10}年代`
    decadeCount[d] = (decadeCount[d] || 0) + 1
  })
  Object.entries(decadeCount)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 2)
    .forEach(([d, n]) => push(`${d} · ${n} 部`, d.replace('年代', '')))

  // 类型：当前结果最高频的 2 个
  const genreCount = {}
  props.movies.forEach((m) => (m.genres_zh || []).forEach((g) => { genreCount[g] = (genreCount[g] || 0) + 1 }))
  Object.entries(genreCount)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 2)
    .forEach(([g, n]) => push(`${g} · ${n} 部`, g))

  // 导演：当前结果里出现最多的
  const dirCount = {}
  props.movies.forEach((m) => { if (m.director) dirCount[m.director] = (dirCount[m.director] || 0) + 1 })
  Object.entries(dirCount)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 2)
    .forEach(([d, n]) => push(`${d} · ${n} 部`, d))

  return out
})

function onWord(w) {
  emit('search', w.word)
}
</script>

<template>
  <aside class="search-aside">
    <!-- 影评高频词 -->
    <section v-if="words.length" class="aside-card">
      <h3 class="aside-card__title">
        影评高频词
        <span v-if="wordTotal" class="aside-card__hint">全站 {{ wordTotal.toLocaleString() }} 条影评归纳</span>
      </h3>
      <div class="word-cloud">
        <button
          v-for="w in words"
          :key="w.word"
          class="word-cloud__w"
          :class="[`word-cloud__w--${wordSize(w)}`, w.side === 'positive' ? 'is-pos' : w.side === 'negative' ? 'is-neg' : '']"
          :title="`在 ${(w.df || 0).toLocaleString()} 篇影评中出现，点击搜索`"
          @click="onWord(w)"
        >
          {{ w.word }}
        </button>
      </div>
      <p class="aside-card__note">颜色 = 情感倾向（绿正 / 红负），点击词语加入搜索</p>
    </section>

    <!-- 口碑温度计 -->
    <section v-if="avgRating !== null" class="aside-card">
      <h3 class="aside-card__title">当前结果口碑</h3>
      <div class="gauge">
        <div class="gauge__track">
          <div class="gauge__fill" :class="gaugeLevel.cls" :style="{ width: gaugePct + '%' }" />
          <div class="gauge__thumb" :style="{ left: gaugePct + '%' }" />
        </div>
        <div class="gauge__foot">
          <span class="gauge__score">{{ avgRating.toFixed(1) }}<small>/10</small></span>
          <span class="gauge__label" :class="gaugeLevel.cls">{{ gaugeLevel.label }}</span>
        </div>
      </div>
    </section>

    <!-- 相关搜索 -->
    <section v-if="related.length" class="aside-card">
      <h3 class="aside-card__title">
        相关搜索
        <span class="aside-card__hint">来自当前结果</span>
      </h3>
      <div class="related-list">
        <button v-for="r in related" :key="r.label" class="related-list__item" @click="emit('search', r.q)">
          <span class="related-list__icon">🔍</span>
          <span class="related-list__label">{{ r.label }}</span>
        </button>
      </div>
    </section>
  </aside>
</template>

<style scoped>
@import '../../styles/search-aside.css';
</style>
