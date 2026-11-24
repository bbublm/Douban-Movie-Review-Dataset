<template>
  <div class="story">
    <!-- 一句话叙事（由真实数据推导） -->
    <p class="story__lede">
      <span class="story__lede-k">{{ spanText }}</span>
      <span class="story__lede-v">{{ ledeText }}</span>
    </p>

    <!-- 时间轴 -->
    <div class="story__axis">
      <div
        v-for="(d, i) in rows"
        :key="d.decade"
        class="story__row"
        :class="{ 'is-peak': d.decade === peakDecade }"
        :style="{ transitionDelay: `${i * 90}ms` }"
      >
        <i class="story__dot" />
        <div class="story__head">
          <span class="story__decade">{{ d.decade }} 年代</span>
          <span class="story__count">{{ d.movies }} 部</span>
          <span class="story__rating">
            <RollingNumber :value="d.avg_rating || 0" :decimals="2" :duration="1400" :delay="i * 90" />
          </span>
        </div>
        <div class="story__bar">
          <i :style="{ width: drawn ? d.pct + '%' : '0%' }" />
        </div>
      </div>
    </div>

    <!-- 底部结论 -->
    <div class="story__foot">
      <div class="story__foot-item">
        <span class="story__foot-k">影片总量</span>
        <span class="story__foot-v"><RollingNumber :value="totalMovies" :duration="1600" /></span>
      </div>
      <div class="story__foot-item">
        <span class="story__foot-k">口碑峰值</span>
        <span class="story__foot-v">{{ bestRating ? bestRating.toFixed(2) : '—' }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
// ============================================================
// 右翼 · 叙事时间轴
//   · 真实数据：GET /insights/trends（按年代聚合的影片数与均分）
//   · 竖轴金色节点 + 细条（无坐标轴/网格），条长=该年代影片数占比
//   · 顶部一句话叙事由数据推导（跨度 + 重心年代），不是写死的文案
// ============================================================
import { computed, onMounted, ref } from 'vue'
import RollingNumber from './RollingNumber.vue'

const props = defineProps({
  trends: { type: Object, default: null },
})

const drawn = ref(false)
onMounted(() => requestAnimationFrame(() => { drawn.value = true }))

const rows = computed(() => {
  const bs = (props.trends?.buckets || []).filter((b) => (b.movies || 0) > 0)
  const max = Math.max(1, ...bs.map((b) => b.movies || 0))
  return bs.map((b) => ({ ...b, pct: ((b.movies || 0) / max) * 100 }))
})

const totalMovies = computed(() => props.trends?.total_movies || 0)
const peakDecade = computed(() => {
  const r = rows.value
  return r.length ? r.reduce((a, b) => (b.movies > a.movies ? b : a)).decade : null
})
const bestRating = computed(() => {
  const rs = rows.value.filter((r) => r.avg_rating != null).map((r) => r.avg_rating)
  return rs.length ? Math.max(...rs) : null
})
const spanText = computed(() => {
  const r = rows.value
  if (!r.length) return '—'
  return `${r[0].decade} 年代 → ${r[r.length - 1].decade} 年代`
})
const ledeText = computed(() => {
  const r = rows.value
  if (!r.length) return '暂无年代数据'
  const peak = r.reduce((a, b) => (b.movies > a.movies ? b : a))
  const share = totalMovies.value ? Math.round((peak.movies / totalMovies.value) * 100) : 0
  return `影片重心落在 ${peak.decade} 年代，占全库 ${share}%`
})
</script>

<style scoped>
.story { display: flex; flex-direction: column; min-height: 0; height: 100%; }

.story__lede { flex: none; padding: 2px 0 12px; border-bottom: 1px solid rgba(194, 65, 12, 0.2); }
.story__lede-k {
  display: block;
  font-family: var(--u-font-tech);
  font-size: 13px;
  letter-spacing: 1.6px;
  color: var(--u-orange);
}
.story__lede-v { display: block; margin-top: 5px; font-size: 12px; line-height: 1.7; color: #4A3C2A; }

.story__axis {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  justify-content: space-around;
  padding: 4px 0 0 4px;
  /* 竖轴：贯穿各节点的极细金线 */
  background: linear-gradient(to right, transparent 3px, rgba(194, 65, 12, 0.2) 3px, rgba(194, 65, 12, 0.2) 4px, transparent 4px) repeat-y;
}

.story__row { position: relative; padding-left: 20px; padding-right: 6px; transition: transform .3s ease; }
.story__row:hover { transform: translateX(3px); }
.story__dot {
  position: absolute;
  left: 0; top: 6px;
  width: 8px; height: 8px;
  margin-left: -2px;
  border-radius: 50%;
  background: #FFFDF7;
  border: 1px solid var(--u-orange);
  box-shadow: 0 0 8px rgba(194, 65, 12, 0.45);
}
.story__row.is-peak .story__dot { background: var(--u-orange); box-shadow: 0 0 14px rgba(194, 65, 12, 0.5); }

.story__head { display: flex; align-items: baseline; gap: 8px; }
.story__decade { font-family: var(--u-font-tech); font-size: 13px; font-weight: 600; color: #3A2E20; letter-spacing: 1px; }
.story__count { font-size: 10.5px; color: #7D6B52; }
.story__rating {
  margin-left: auto;
  font-family: var(--u-font-tech);
  font-size: 14px;
  font-weight: 700;
  color: var(--u-orange);
  font-variant-numeric: tabular-nums;
}

.story__bar {
  margin-top: 6px;
  height: 4px;
  background: rgba(120, 90, 50, 0.06);
  clip-path: polygon(2px 0, 100% 0, calc(100% - 2px) 100%, 0 100%);
}
.story__bar i {
  display: block;
  height: 100%;
  background: linear-gradient(to right, rgba(15, 118, 110, 0.35), var(--u-orange));
  box-shadow: 0 0 10px rgba(194, 65, 12, 0.3);
  transition: width 1.15s cubic-bezier(0.16, 0.84, 0.44, 1);
}

.story__foot {
  flex: none;
  display: flex;
  gap: 12px;
  padding-top: 12px;
  border-top: 1px solid rgba(194, 65, 12, 0.2);
}
.story__foot-item {
  flex: 1;
  padding: 8px 10px;
  background: rgba(120, 90, 50, 0.05);
  border: 1px solid rgba(194, 65, 12, 0.24);
  clip-path: polygon(8px 0, 100% 0, 100% calc(100% - 8px), calc(100% - 8px) 100%, 0 100%, 0 8px);
}
.story__foot-k { display: block; font-size: 10px; color: #7D6B52; letter-spacing: 1px; }
.story__foot-v {
  display: block;
  margin-top: 3px;
  font-family: var(--u-font-tech);
  font-size: 18px;
  font-weight: 700;
  color: #3A2E20;
  font-variant-numeric: tabular-nums;
}
</style>
