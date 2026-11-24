<script setup>
// 品牌大搜索框：停输 250ms 出联想，键盘上下选、回车确认、Esc 收起。
// 联想只走 /search/suggest（phrase_prefix 前缀匹配片名），不搜简介 ——
// 联想屏很小，出剧情命中项没有意义。
import { ref, watch } from 'vue'
import { api } from '../../api'

const props = defineProps({
  modelValue: { type: String, default: '' },
  placeholder: { type: String, default: '搜片名 / 导演 / 剧情，中文也可以' },
})
const emit = defineEmits(['update:modelValue', 'search', 'pick'])

const text = ref(props.modelValue)
const open = ref(false)
const items = ref([])
const active = ref(-1)
const loading = ref(false)
let timer = null
let seq = 0 // 竞态防护：旧联想返回时丢弃，避免闪回的旧结果覆盖新结果

watch(() => props.modelValue, (v) => { text.value = v })

function onInput() {
  emit('update:modelValue', text.value)
  clearTimeout(timer)
  const q = text.value.trim()
  if (!q) {
    items.value = []
    open.value = false
    return
  }
  timer = setTimeout(() => fetchSuggest(q), 250)
}

async function fetchSuggest(q) {
  const mine = ++seq
  loading.value = true
  try {
    const list = await api.suggest(q, 8)
    if (mine !== seq) return
    items.value = list || []
    open.value = items.value.length > 0
    active.value = -1
  } catch {
    /* 联想失败不打扰输入，正式检索时再报错 */
  } finally {
    if (mine === seq) loading.value = false
  }
}

function onKeydown(e) {
  if (!open.value) {
    if (e.key === 'Enter') submit()
    return
  }
  if (e.key === 'ArrowDown') {
    e.preventDefault()
    active.value = (active.value + 1) % items.value.length
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    active.value = (active.value - 1 + items.value.length) % items.value.length
  } else if (e.key === 'Enter') {
    e.preventDefault()
    if (active.value >= 0) pick(items.value[active.value])
    else submit()
  } else if (e.key === 'Escape') {
    open.value = false
  }
}

function pick(item) {
  text.value = item.title
  emit('update:modelValue', item.title)
  open.value = false
  emit('pick', item)
}

function submit() {
  open.value = false
  emit('search', text.value)
}

// 失焦延迟收起，给 mousedown 点击项留出触发时间
function onBlur() {
  setTimeout(() => { open.value = false }, 160)
}
</script>

<template>
  <div class="search-box">
    <form class="search-box__row" @submit.prevent="submit">
      <input
        v-model="text"
        class="search-box__input"
        type="text"
        :placeholder="placeholder"
        autocomplete="off"
        maxlength="64"
        @input="onInput"
        @keydown="onKeydown"
        @blur="onBlur"
      />
      <span v-if="loading" class="search-box__spinner" />
      <button class="search-box__btn" type="submit">搜 索</button>
    </form>

    <div v-if="open" class="suggest">
      <button
        v-for="(item, i) in items"
        :key="item.movie_id"
        class="suggest__item"
        :class="{ 'is-active': i === active }"
        @mousedown.prevent="pick(item)"
        @mouseenter="active = i"
      >
        <img v-if="item.poster_url" :src="item.poster_url" class="suggest__poster" alt="" loading="lazy" />
        <span v-else class="suggest__poster" style="display:flex;align-items:center;justify-content:center">🎬</span>
        <span class="suggest__title">{{ item.title }}</span>
        <span class="suggest__meta">
          <template v-if="item.year">{{ item.year }} 年</template>
          <template v-if="item.rating"> · ★ {{ item.rating.toFixed(1) }}</template>
        </span>
      </button>
    </div>
  </div>
</template>
