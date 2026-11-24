<script setup>
// 排序栏：影片/影评 Tab 切换 + 排序下拉 + 升降序 + 结果计数与耗时。
// 排序选项按 Tab 不同（影评没有评分/票数排序，有篇幅/情感排序）。
defineProps({
  tab: { type: String, default: 'movies' },
  sort: { type: String, default: 'relevance' },
  order: { type: String, default: 'desc' },
  total: { type: Number, default: 0 },
  tookMs: { type: Number, default: 0 },
  page: { type: Number, default: 1 },
  pages: { type: Number, default: 0 },
})
const emit = defineEmits(['tab', 'sort', 'order'])

const MOVIE_SORTS = [
  { value: 'relevance', label: '相关度' },
  { value: 'rating', label: '评分' },
  { value: 'votes', label: '票数' },
  { value: 'year', label: '年份' },
  { value: 'title', label: '片名' },
  { value: 'popularity', label: '热度' },
]
const REVIEW_SORTS = [
  { value: 'relevance', label: '相关度' },
  { value: 'length', label: '篇幅' },
  { value: 'sentiment', label: '情感分' },
]
</script>

<template>
  <div class="sort-bar">
    <div class="sort-bar__tabs">
      <button class="sort-bar__tab" :class="{ 'is-active': tab === 'movies' }" @click="emit('tab', 'movies')">
        🎬 影片
      </button>
      <button class="sort-bar__tab" :class="{ 'is-active': tab === 'reviews' }" @click="emit('tab', 'reviews')">
        📝 影评
      </button>
    </div>

    <span class="sort-bar__sep" />

    <span class="sort-bar__label">排序</span>
    <select class="sort-bar__sort" :value="sort" @change="emit('sort', $event.target.value)">
      <option v-for="s in (tab === 'movies' ? MOVIE_SORTS : REVIEW_SORTS)" :key="s.value" :value="s.value">
        {{ s.label }}
      </option>
    </select>
    <button class="sort-bar__order" :title="order === 'desc' ? '当前降序，点击切换升序' : '当前升序，点击切换降序'" @click="emit('order', order === 'desc' ? 'asc' : 'desc')">
      {{ order === 'desc' ? '↓ 降序' : '↑ 升序' }}
    </button>

    <span class="sort-bar__meta">
      共 <b>{{ total.toLocaleString() }}</b> 条 · {{ tookMs }} ms
      <template v-if="pages > 1"> · 第 {{ page }} / {{ pages }} 页</template>
    </span>
  </div>
</template>
