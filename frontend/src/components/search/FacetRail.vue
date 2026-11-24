<script setup>
// 左侧分面栏：把 ES 返回的分面桶渲染成可点击的药丸标签。
// 设计原则：
//   · 分组可折叠，标题显示当前选中数量
//   · 每个分组配语义图标，减少纯文字枯燥感
//   · 药丸选中态带渐变 + 金色辉光 + 对勾滑入
//   · hover 微上浮 + 边框发光，营造"可交互"反馈
//   · 计数用独立 badge，避免与标签名粘在一起
//   · 展示层兜底：后端归一化偶有漏网英文国家名，前端再映射一次中文
import { computed, ref } from 'vue'

const props = defineProps({
  facets: { type: Array, default: () => [] },
  requirePoster: Boolean,
  yearRange: { type: Array, default: () => [null, null] },
})
const emit = defineEmits(['toggle', 'quality', 'clearGroup'])

const DECADES = [
  { key: 'decade:2020s', label: '2020s', from: 2020, to: 2029 },
  { key: 'decade:2010s', label: '2010s', from: 2010, to: 2019 },
  { key: 'decade:2000s', label: '2000s', from: 2000, to: 2009 },
  { key: 'decade:1990s', label: '90 年代', from: 1990, to: 1999 },
  { key: 'decade:older', label: '更早', from: null, to: 1989 },
]

const GROUP_META = {
  genres: { icon: '🎬', label: '类型' },
  countries: { icon: '🌍', label: '国家 / 地区' },
  languages: { icon: '🗣️', label: '语言' },
  years: { icon: '📅', label: '年份' },
  rating: { icon: '⭐', label: '评分' },
  sentiment: { icon: '💬', label: '情感' },
  dataset: { icon: '📚', label: '来源' },
  length: { icon: '📝', label: '篇幅' },
}

// 展示层兜底映射：后端归一化暂未覆盖的英文国家名 / 语言名
const DISPLAY_COUNTRY = {
  Belgium: '比利时',
  Netherlands: '荷兰',
  Thailand: '泰国',
  Indonesia: '印尼',
  Poland: '波兰',
  Portugal: '葡萄牙',
  'Czech Republic': '捷克',
  Austria: '奥地利',
  Hungary: '匈牙利',
  Chile: '智利',
  Colombia: '哥伦比亚',
  Finland: '芬兰',
  Ukraine: '乌克兰',
  Philippines: '菲律宾',
  Romania: '罗马尼亚',
  Venezuela: '委内瑞拉',
}
const DISPLAY_LANGUAGE = {
  English: '英语',
  Spanish: '西班牙语',
  Mandarin: '汉语',
  French: '法语',
  Japanese: '日语',
  Korean: '韩语',
  Russian: '俄语',
  Portuguese: '葡萄牙语',
  Italian: '意大利语',
  German: '德语',
  Hindi: '印地语',
  Arabic: '阿拉伯语',
  Cantonese: '粤语',
}

// 默认只展开「类型」，其余分组折叠（标题仍可见，点开即用）——
// 避免四组长分面全部展开把侧栏拉成三屏高的墙
const defaultExpanded = Object.fromEntries(
  ['genres', 'countries', 'languages', 'years'].map((k) => [k, k === 'genres'])
)
const expanded = ref({ ...defaultExpanded })

const groupInfo = computed(() => {
  const map = {}
  for (const f of props.facets) {
    const meta = GROUP_META[f.field] || { icon: '🔖', label: f.label || f.field }
    const selected = (f.buckets || []).filter((b) => b.selected).length
    map[f.field] = { ...meta, selected }
  }
  return map
})

function toggleGroup(field) {
  expanded.value[field] = !expanded.value[field]
}

function displayKey(field, key) {
  if (field === 'countries') return DISPLAY_COUNTRY[key] || key
  if (field === 'languages') return DISPLAY_LANGUAGE[key] || key
  return key
}

function decadeSelected(d) {
  return props.yearRange[0] === d.from && props.yearRange[1] === d.to
}

function isYearFacet(f) {
  return f.field === 'years'
}

function ripple(e) {
  const btn = e.currentTarget
  const circle = document.createElement('span')
  const rect = btn.getBoundingClientRect()
  const size = Math.max(rect.width, rect.height)
  circle.style.width = circle.style.height = `${size}px`
  circle.style.left = `${e.clientX - rect.left - size / 2}px`
  circle.style.top = `${e.clientY - rect.top - size / 2}px`
  circle.classList.add('facet-ripple')
  btn.appendChild(circle)
  setTimeout(() => circle.remove(), 520)
}
</script>

<template>
  <aside class="facet-rail">
    <div class="facet-rail__head">
      <span class="facet-rail__title">🧩 筛选条件</span>
    </div>

    <div v-for="f in facets" :key="f.field" class="facet-group">
      <button
        class="facet-group__head"
        :class="{ 'is-expanded': expanded[f.field], 'has-selected': groupInfo[f.field]?.selected > 0 }"
        @click="toggleGroup(f.field)"
      >
        <span class="facet-group__icon">{{ groupInfo[f.field]?.icon || '🔖' }}</span>
        <span class="facet-group__title">
          {{ groupInfo[f.field]?.label || f.label }}
          <!-- 括号里的数字 = 这组有多少个可选筛选项（不是影片数），让人一眼知道选择面 -->
          <span class="facet-group__num">({{ (f.buckets || []).length }})</span>
        </span>
        <span v-if="groupInfo[f.field]?.selected > 0" class="facet-group__count">
          {{ groupInfo[f.field].selected }}
        </span>
        <span class="facet-group__chevron" aria-hidden="true">
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.5">
            <polyline points="6 9 12 15 18 9" />
          </svg>
        </span>
      </button>

      <div v-show="expanded[f.field]" class="facet-group__body">
        <!-- 年份：十年快捷按钮 + 单年列表 -->
        <template v-if="isYearFacet(f)">
          <div class="facet-decades">
            <button
              v-for="d in DECADES"
              :key="d.key"
              class="facet-decade"
              :class="{ 'is-selected': decadeSelected(d) }"
              @click="emit('toggle', { field: 'years', key: d.key })"
            >{{ d.label }}</button>
          </div>
          <div class="facet-year-list">
            <button
              v-for="b in f.buckets"
              :key="b.key"
              class="facet-year"
              :class="{ 'is-selected': b.selected, 'is-zero': b.count === 0 }"
              @click="emit('toggle', { field: f.field, key: b.key })"
            >
              <span class="facet-year__check" aria-hidden="true">
                <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="3">
                  <polyline points="20 6 9 17 4 12" />
                </svg>
              </span>
              <span class="facet-year__key">{{ b.key }}</span>
            </button>
          </div>
        </template>

        <div v-else class="facet-pills">
          <button
            v-for="b in f.buckets"
            :key="b.key"
            class="facet-pill"
            :class="{ 'is-selected': b.selected, 'is-zero': b.count === 0 }"
            :title="`${displayKey(f.field, b.key)}：${b.count} 条`"
            @click="(e) => { ripple(e); emit('toggle', { field: f.field, key: b.key }) }"
          >
            <span class="facet-pill__check" aria-hidden="true">
              <svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="currentColor" stroke-width="3.5">
                <polyline points="20 6 9 17 4 12" />
              </svg>
            </span>
            <span class="facet-pill__text">{{ displayKey(f.field, b.key) }}</span>
          </button>
        </div>
      </div>
    </div>

    <div class="facet-quality">
      <div class="facet-quality__head">
        <span class="facet-quality__icon">✨</span>
        <span>数据质量</span>
      </div>
      <label class="facet-quality__row">
        <div class="facet-quality__checkbox" :class="{ 'is-checked': requirePoster }">
          <svg v-if="requirePoster" viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="#fff" stroke-width="3.5">
            <polyline points="20 6 9 17 4 12" />
          </svg>
        </div>
        <input
          type="checkbox"
          :checked="requirePoster"
          @change="emit('quality', { key: 'require_poster', value: $event.target.checked })"
        />
        仅看有海报
      </label>
    </div>
  </aside>
</template>
