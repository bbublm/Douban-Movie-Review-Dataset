<script setup>
// 影评列表：情感标签 + 所属影片 + ES 高亮片段 + 篇幅。
// 高亮片段是 ES 在索引内容上包的 <em>，内容源自我们自己的数据集，
// 用 v-html 渲染是 ES 高亮的标准做法；纯文本截断到 300 字防止卡片过长。
import { ref, computed } from 'vue'

const props = defineProps({
  loading: Boolean,
  reviews: { type: Array, default: () => [] },
  total: { type: Number, default: 0 },
  page: { type: Number, default: 1 },
  pages: { type: Number, default: 0 },
})
const emit = defineEmits(['page'])

const SENT_LABEL = { positive: '正面', negative: '负面', neutral: '中性' }

// 高亮优先；没有高亮时截断正文
function snippet(r) {
  const frags = r.highlight?.text
  if (frags && frags.length) return frags.join(' … ')
  const t = r.text || ''
  return t.length > 300 ? t.slice(0, 300) + '…' : t
}

function isHtml(r) {
  return !!(r.highlight?.text && r.highlight.text.length)
}
</script>

<template>
  <div v-if="loading" class="review-list">
    <div v-for="i in 5" :key="i" class="review-card">
      <div class="skeleton" style="height:16px;width:30%;margin-bottom:10px" />
      <div class="skeleton" style="height:12px;width:100%;margin-bottom:6px" />
      <div class="skeleton" style="height:12px;width:92%;margin-bottom:6px" />
      <div class="skeleton" style="height:12px;width:64%" />
    </div>
  </div>

  <div v-else-if="!reviews.length" class="empty card">
    <div class="empty__icon">📝</div>
    <div class="empty__title">没有找到符合条件的影评</div>
    <p>换个关键词，或切换情感分面试试</p>
  </div>

  <template v-else>
    <div class="review-list">
      <article v-for="r in reviews" :key="r.review_id" class="review-card">
        <div class="review-card__head">
          <span v-if="r.sentiment" class="sent" :class="`sent--${r.sentiment}`">
            {{ SENT_LABEL[r.sentiment] || r.sentiment }}
          </span>
          <span v-if="r.movie_title" class="review-card__movie">{{ r.movie_title }}</span>
          <span v-if="r.sentiment_score != null" class="review-card__score">
            情感分 {{ r.sentiment_score.toFixed(2) }}
          </span>
          <span v-if="r.word_count" class="review-card__words">{{ r.word_count }} 词</span>
        </div>
        <p v-if="isHtml(r)" class="review-card__text" v-html="snippet(r)" />
        <p v-else class="review-card__text">{{ snippet(r) }}</p>
      </article>
    </div>

    <div v-if="pages > 1" class="pager">
      <button class="pager__btn" :disabled="page <= 1" @click="emit('page', page - 1)">‹ 上一页</button>
      <button class="pager__btn" disabled style="min-width:auto">{{ page }} / {{ pages }}</button>
      <button class="pager__btn" :disabled="page >= pages" @click="emit('page', page + 1)">下一页 ›</button>
      <span class="pager__info">共 {{ total.toLocaleString() }} 条</span>
    </div>
  </template>
</template>
