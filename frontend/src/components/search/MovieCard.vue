<script setup>
// 影片卡：海报 + 评分 + 年份 + 类型 + 导演 + 可解释标签。
// 海报可能缺失（融合数据稀疏）—— 缺失时显示占位块，不留破图。
// 可解释标签（功能清单 P1）：高热度 / 冷门佳片 / 口碑佳 ——
// 早期版本在这里展示「多源融合 / legacy / tmdb」等内部血缘字段，
// 对用户是噪音，已换成用户视角的标签。
import { computed, ref } from 'vue'

const props = defineProps({
  movie: { type: Object, required: true },
  watched: { type: Boolean, default: false },
  myScore: { type: Number, default: null },
})
const emit = defineEmits(['open', 'toggle-watch'])

const posterFailed = ref(false)

// ---- 可解释标签（按 votes / rating 派生，不依赖任何内部字段）----
const votes = computed(() => Number(props.movie.votes) || 0)
const rating = computed(() => Number(props.movie.rating) || 0)
const isHot = computed(() => votes.value >= 10000)
const isGem = computed(() => rating.value >= 7.5 && votes.value > 0 && votes.value < 3000)
const isPraise = computed(() => rating.value >= 8)

function title(m) {
  return m.title_zh || m.title || m.movie_id
}

function onWatch(e) {
  e.stopPropagation()
  emit('toggle-watch', props.movie)
}
</script>

<template>
  <article class="movie-card" @click="emit('open', movie)">
    <div class="movie-card__poster">
      <img
        v-if="movie.poster_url && !posterFailed"
        :src="movie.poster_url"
        :alt="title(movie)"
        loading="lazy"
        @error="posterFailed = true"
      />
      <div v-else class="movie-card__poster-ph">
        <span class="ph-icon">🎬</span>
        <span>暂无海报</span>
      </div>

      <!-- 悬停遮罩 + 查看详情（功能清单 P1）-->
      <div class="movie-card__poster-mask">
        <span class="movie-card__cta">查看详情</span>
      </div>

      <span v-if="movie.rating" class="movie-card__rating">★ {{ movie.rating.toFixed(1) }}</span>
      <button
        class="movie-card__watch"
        :class="{ 'is-on': watched }"
        :title="watched ? '移出想看' : '加入想看'"
        @click="onWatch"
      >{{ watched ? '★' : '☆' }}</button>
    </div>

    <div class="movie-card__body">
      <h3 class="movie-card__title" :title="title(movie)">{{ title(movie) }}</h3>
      <div class="movie-card__meta">
        <template v-if="movie.year">{{ movie.year }} 年</template>
        <template v-if="movie.runtime"> · {{ movie.runtime }} 分钟</template>
        <template v-if="movie.votes"> · {{ movie.votes.toLocaleString() }} 人评</template>
      </div>
      <div v-if="movie.genres_zh?.length" class="movie-card__genres">
        <span v-for="g in movie.genres_zh.slice(0, 3)" :key="g" class="tag tag--genre">{{ g }}</span>
      </div>
      <div v-if="movie.director" class="movie-card__director">导演：{{ movie.director }}</div>
      <div class="movie-card__badges">
        <span v-if="isHot" class="tag tag--hot">🔥 高热度</span>
        <span v-else-if="isGem" class="tag tag--gem">💎 冷门佳片</span>
        <span v-if="isPraise" class="tag tag--praise">口碑佳</span>
      </div>
    </div>

    <span v-if="myScore" class="movie-card__myscore">我打 {{ myScore }}</span>
  </article>
</template>
