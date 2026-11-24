<script setup>
// 影片详情弹窗：全字段展示 + 打分 / 想看 / 找相似 / 关键词画像。
// Esc 关闭；点遮罩关闭。关键词画像（/insights/movies/{id}）是增强信息，
// 失败不阻塞详情展示。
import { onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { api } from '../../api'

const props = defineProps({
  movie: { type: Object, required: true },
  myScore: { type: Number, default: null },
  watched: { type: Boolean, default: false },
})
const emit = defineEmits(['close', 'rate', 'delete-rating', 'toggle-watch', 'similar'])

const insight = ref(null)
const insightLoading = ref(false)
const SCORES = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]

watch(
  () => props.movie?.movie_id,
  async (id) => {
    if (!id) return
    insight.value = null
    insightLoading.value = true
    try {
      insight.value = await api.movieInsight(id)
    } catch {
      /* 画像失败不阻塞详情 */
    } finally {
      insightLoading.value = false
    }
  },
  { immediate: true },
)

function onKey(e) {
  if (e.key === 'Escape') emit('close')
}
onMounted(() => document.addEventListener('keydown', onKey))
onBeforeUnmount(() => document.removeEventListener('keydown', onKey))

function title(m) {
  return m.title_zh || m.title || m.movie_id
}
</script>

<template>
  <div class="modal-backdrop" @click.self="emit('close')">
    <button class="modal__close" title="关闭（Esc）" @click="emit('close')">×</button>
    <div class="modal">
      <div class="detail">
        <div class="detail__poster">
          <img v-if="movie.poster_url" :src="movie.poster_url" :alt="title(movie)" />
          <div v-else class="detail__poster-ph"><span style="font-size:44px">🎬</span><span>暂无海报</span></div>
        </div>

        <div class="detail__main">
          <h2 class="detail__title">{{ title(movie) }}</h2>
          <div v-if="movie.title_en && movie.title_en !== movie.title" class="detail__title-en">{{ movie.title_en }}</div>

          <div class="detail__metas">
            <span v-if="movie.rating" class="stars">★<span class="stars__value">{{ movie.rating.toFixed(1) }}</span></span>
            <span v-if="movie.votes" class="tag">{{ movie.votes.toLocaleString() }} 人评</span>
            <span v-if="movie.year" class="tag">{{ movie.year }} 年</span>
            <span v-if="movie.release_date" class="tag">上映 {{ movie.release_date }}</span>
            <span v-if="movie.runtime" class="tag">{{ movie.runtime }} 分钟</span>
            <span v-for="g in (movie.genres_zh || [])" :key="g" class="tag tag--genre">{{ g }}</span>
          </div>

          <p v-if="movie.overview" class="detail__overview">{{ movie.overview }}</p>
          <p v-else class="detail__overview text-3">（这部影片暂时没有剧情简介）</p>

          <dl class="detail__kv">
            <dt>导演</dt><dd>{{ movie.director || '—' }}</dd>
            <dt v-if="movie.cast?.length">主演</dt><dd v-if="movie.cast?.length">{{ movie.cast.slice(0, 6).join(' / ') }}</dd>
            <dt v-if="movie.countries?.length">出品</dt><dd v-if="movie.countries?.length">{{ movie.countries.join(' / ') }}</dd>
            <dt v-if="movie.languages?.length">语言</dt><dd v-if="movie.languages?.length">{{ movie.languages.join(' / ') }}</dd>
            <dt v-if="movie.imdb_id">IMDb</dt><dd v-if="movie.imdb_id">{{ movie.imdb_id }}</dd>
            <dt v-if="movie.filming_locations?.length">拍摄地</dt>
            <dd v-if="movie.filming_locations?.length">
              {{ movie.filming_locations.slice(0, 5).map((l) => l.name).filter(Boolean).join(' / ') }}
            </dd>
          </dl>

          <div class="detail__insight">
            <h4>🔍 观众评论关键词</h4>
            <div v-if="insightLoading" class="text-3 text-sm">分析中…</div>
            <template v-else-if="insight?.keywords?.length">
              <div class="kw-chips">
                <span v-for="k in insight.keywords.slice(0, 14)" :key="k.word" class="kw-chip" :class="k.side === 'positive' ? 'kw-chip--pos' : k.side === 'negative' ? 'kw-chip--neg' : ''">
                  {{ k.word }}
                </span>
              </div>
              <p v-if="insight.sentiment_hint" class="text-3 text-sm mt-8">{{ insight.sentiment_hint }}</p>
            </template>
            <div v-else class="text-3 text-sm">（该片暂无关键词画像）</div>
          </div>
        </div>
      </div>

      <div class="detail__actions">
        <div class="rate-row">
          <span class="rate-row__label">我的评分</span>
          <button
            v-for="s in SCORES"
            :key="s"
            class="rate-btn"
            :class="{ 'is-on': myScore === s }"
            :title="`打 ${s} 分`"
            @click="emit('rate', s)"
          >{{ s }}</button>
          <span v-if="myScore" class="rate-current">当前 {{ myScore }} 分</span>
          <button v-if="myScore" class="btn btn--ghost btn--sm" @click="emit('delete-rating')">删除评分</button>
        </div>
        <span style="flex:1" />
        <button class="btn btn--ghost btn--sm" @click="emit('toggle-watch')">
          {{ watched ? '★ 已想看' : '☆ 想 看' }}
        </button>
        <button class="btn btn--primary btn--sm" @click="emit('similar', movie)">找相似 →</button>
      </div>
    </div>
  </div>
</template>
