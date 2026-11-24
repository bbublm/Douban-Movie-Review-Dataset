<script setup>
// ============================================================
// 全局搜索框 —— 导航栏与首页 Hero 共用一个组件，只是尺寸不同。
//
// 清单对齐：
//  · 占位符「搜电影、导演、演员…」，聚焦边框变金色
//  · 输入 1 个字符后 200ms 防抖请求补全，下拉按 电影/导演/演员 分组
//  · 空输入时展示热门搜索词 + 本机搜索历史
//  · 键盘：↑↓ 选择、Enter 搜索、Esc 关闭面板
//
// 为什么补全要分组：用户的输入意图有三类，混在一个列表里会让人
// 分不清"点下去是去看片还是去搜人"。
// ============================================================
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../../api'
import { searchHistory } from '../../composables/useSearchHistory'

const props = defineProps({
  size: { type: String, default: 'sm' },   // sm=导航 / lg=首页 Hero
  modelValue: { type: String, default: '' },
})
const emit = defineEmits(['update:modelValue', 'search'])

const router = useRouter()
const root = ref(null)
const kw = ref(props.modelValue)
const open = ref(false)
const activeIdx = ref(-1)
const loading = ref(false)
const movies = ref([])
const directors = ref([])
const actors = ref([])
const hotWords = ref([])
let timer = null

watch(() => props.modelValue, (v) => { kw.value = v })

// 热门词取热门榜前几部片名；模块级缓存，避免导航与首页各拉一次
let hotCache = null
async function loadHot() {
  if (hotCache) { hotWords.value = hotCache; return }
  try {
    const data = await api.popular(6)
    hotCache = (data?.items || data?.hits || []).map((m) => m.title).filter(Boolean).slice(0, 6)
    hotWords.value = hotCache
  } catch { hotWords.value = [] }
}

// 分组后的可选项：先电影、再导演、再演员，键盘上下穿过三组
const groups = computed(() => {
  const out = []
  if (movies.value.length) {
    out.push({
      key: 'movies',
      label: '电影',
      items: movies.value.map((m) => ({
        type: 'movie',
        text: m.title,
        meta: [m.year, (m.genres_zh || []).slice(0, 2).join('/')].filter(Boolean).join(' · '),
        id: m.movie_id,
      })),
    })
  }
  if (directors.value.length) {
    out.push({ key: 'directors', label: '导演', items: directors.value.map((d) => ({ type: 'person', text: d, meta: '导演' })) })
  }
  if (actors.value.length) {
    out.push({ key: 'actors', label: '演员', items: actors.value.map((a) => ({ type: 'person', text: a, meta: '演员' })) })
  }
  return out
})

const flat = computed(() => groups.value.flatMap((g) => g.items))

// 模板里要用历史的当前值：ref 暴露成 computed，避免模板写 .value
const history = computed(() => searchHistory.items.value)

async function runSuggest() {
  const q = kw.value.trim()
  if (!q) { movies.value = []; directors.value = []; actors.value = []; return }
  loading.value = true
  try {
    const data = await api.suggest(q, 6)
    movies.value = Array.isArray(data) ? data : (data?.movies || [])
    directors.value = data?.directors || []
    actors.value = data?.actors || []
  } catch {
    movies.value = []; directors.value = []; actors.value = []
  } finally {
    loading.value = false
  }
}

function onInput() {
  emit('update:modelValue', kw.value)
  open.value = true
  activeIdx.value = -1
  clearTimeout(timer)
  timer = setTimeout(runSuggest, 200)
}

function onFocus() {
  open.value = true
  loadHot()
}

function onKeyDown(e) {
  if (e.key === 'Escape') { open.value = false; return }
  if (!flat.value.length) { if (e.key === 'Enter') submit(); return }
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    activeIdx.value = (activeIdx.value + 1) % flat.value.length
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    activeIdx.value = activeIdx.value <= 0 ? flat.value.length - 1 : activeIdx.value - 1
  } else if (e.key === 'Enter') {
    e.preventDefault()
    if (activeIdx.value >= 0) pick(flat.value[activeIdx.value])
    else submit()
  }
}

function submit(word) {
  const q = (word ?? kw.value).trim()
  if (!q) return
  open.value = false
  kw.value = q
  searchHistory.add(q)
  emit('search', q)
  router.push({ path: '/search', query: { q } })
}

function pick(item) {
  if (!item) return
  open.value = false
  if (item.type === 'movie') {
    searchHistory.add(item.text)
    router.push({ path: `/movie/${encodeURIComponent(item.id)}` })
  } else {
    submit(item.text)
  }
}

function useWord(word) {
  kw.value = word
  submit(word)
}

function onOutside(e) {
  if (root.value && !root.value.contains(e.target)) open.value = false
}

onMounted(() => {
  document.addEventListener('click', onOutside)
  loadHot()
})

function relTime(ts) {
  const diff = Date.now() - ts
  if (diff < 60000) return '刚刚'
  if (diff < 3600000) return `${Math.floor(diff / 60000)} 分钟前`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)} 小时前`
  return `${Math.floor(diff / 86400000)} 天前`
}
</script>

<template>
  <div class="gsearch" :class="`gsearch--${size}`" ref="root">
    <div class="gsearch__box">
      <span class="gsearch__icon">🔍</span>
      <input
        v-model="kw"
        class="gsearch__input gsearch__input--hotkey"
        placeholder="搜电影、导演、演员…"
        autocomplete="off"
        @input="onInput"
        @focus="onFocus"
        @keydown="onKeyDown"
      />
      <button v-if="kw" class="gsearch__clear" @click="kw = ''; $emit('update:modelValue', '')">×</button>
      <button class="gsearch__go" @click="submit()">搜索</button>
    </div>

    <div v-if="open" class="gsearch__panel">
      <!-- 有输入：分组补全 -->
      <template v-if="kw.trim()">
        <div v-if="loading" class="gsearch__tip">联想中…</div>
        <template v-else>
          <div v-for="g in groups" :key="g.key" class="gsearch__group">
            <div class="gsearch__glabel">{{ g.label }}</div>
            <button
              v-for="(it, i) in g.items"
              :key="g.key + it.text + i"
              class="gsearch__item"
              :class="{ 'is-active': flat.indexOf(it) === activeIdx }"
              @click="pick(it)"
            >
              <span class="gsearch__itext">{{ it.text }}</span>
              <span class="gsearch__imeta">{{ it.meta }}</span>
            </button>
          </div>
          <div v-if="!groups.length" class="gsearch__tip">没有匹配的联想项，回车直接搜索</div>
        </template>
      </template>

      <!-- 空输入：热门词 + 历史 -->
      <template v-else>
        <div v-if="hotWords.length" class="gsearch__group">
          <div class="gsearch__glabel">🔥 热门搜索</div>
          <div class="gsearch__words">
            <button v-for="w in hotWords" :key="w" class="gsearch__word" @click="useWord(w)">{{ w }}</button>
          </div>
        </div>
        <div v-if="history.length" class="gsearch__group">
          <div class="gsearch__glabel">
            搜索历史
            <button class="gsearch__clr" @click="searchHistory.clear()">清空</button>
          </div>
          <button
            v-for="h in history.slice(0, 6)"
            :key="h.keyword"
            class="gsearch__item"
            @click="useWord(h.keyword)"
          >
            <span class="gsearch__itext">{{ h.keyword }}</span>
            <span class="gsearch__imeta">{{ relTime(h.time) }}</span>
          </button>
        </div>
      </template>
    </div>
  </div>
</template>
