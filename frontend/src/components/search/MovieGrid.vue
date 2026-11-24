<script setup>
// 结果网格：骨架屏 / 空态 / 卡片网格 / 加载更多四态。
// 分页用「加载更多」而不是页码跳页（功能清单 P0：每次 20 条追加），
// 已加载条数与剩余条数都如实告诉用户。
// 空态把后端 note 原样展示（如混搭器没有同时命中的影片），
// 不自己编解释 —— 数据层面的原因后端最清楚。
// 空态按功能清单给「🎲 去开个盲盒」出口：检索无果时去趣味发现逛逛。
import { computed } from 'vue'
import { blindBox } from '../../composables/useBlindBox'
import MovieCard from './MovieCard.vue'

const props = defineProps({
  loading: Boolean,
  movies: { type: Array, default: () => [] },
  total: { type: Number, default: 0 },
  page: { type: Number, default: 1 },
  pages: { type: Number, default: 0 },
  loadingMore: { type: Boolean, default: false },
  note: { type: String, default: '' },
  watchedIds: { type: Set, default: () => new Set() },
  myScores: { type: Object, default: () => ({}) },
})
const emit = defineEmits(['open', 'toggle-watch', 'load-more'])

const hasMore = computed(() => props.page < props.pages)
const remain = computed(() => Math.max(0, props.total - props.movies.length))
</script>

<template>
  <div v-if="loading" class="movie-grid movie-grid--skeleton">
    <div v-for="i in 10" :key="i" class="movie-card" style="cursor:default">
      <div class="skeleton" style="aspect-ratio:2/3;border-radius:0" />
      <div class="movie-card__body">
        <div class="skeleton" style="height:14px;width:80%" />
        <div class="skeleton" style="height:11px;width:55%" />
        <div class="skeleton" style="height:11px;width:40%" />
      </div>
    </div>
  </div>

  <div v-else-if="!movies.length" class="empty card">
    <div class="empty__icon">🎬</div>
    <div class="empty__title">没有找到相关电影，换个词试试？</div>
    <p v-if="note">{{ note }}</p>
    <p v-else>也可以放宽筛选条件，或者……</p>
    <button class="btn btn--primary empty__action" @click="blindBox.openBox()">🎲 去开个盲盒</button>
  </div>

  <template v-else>
    <div class="movie-grid">
      <MovieCard
        v-for="m in movies"
        :key="m.movie_id"
        :movie="m"
        :watched="watchedIds.has(m.movie_id)"
        :my-score="myScores[m.movie_id] ?? null"
        @open="emit('open', $event)"
        @toggle-watch="emit('toggle-watch', $event)"
      />
    </div>

    <div v-if="hasMore" class="load-more">
      <button class="btn btn--ghost load-more__btn" :disabled="loadingMore" @click="emit('load-more')">
        <span v-if="loadingMore" class="search-box__spinner" />
        <span v-else>加载更多</span>
        <span v-if="!loadingMore" class="load-more__remain">（还有 {{ remain.toLocaleString() }} 部）</span>
      </button>
      <div class="load-more__progress">
        已加载 {{ movies.length }} / {{ total.toLocaleString() }} 部
      </div>
    </div>
    <div v-else class="load-more load-more--done">
      已展示全部 {{ total.toLocaleString() }} 部影片
    </div>
  </template>
</template>
