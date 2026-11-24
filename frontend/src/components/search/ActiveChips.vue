<script setup>
// 已选条件 chips：点 × 移除单项，「全部清除」一键重置。
// chips 由 HomeView 根据当前筛选状态生成，这里无状态、纯展示。
defineProps({
  chips: { type: Array, default: () => [] },  // [{key, label}]
})
const emit = defineEmits(['remove', 'clear'])
</script>

<template>
  <div v-if="chips.length" class="active-chips">
    <span class="active-chips__label">已选条件</span>
    <span v-for="c in chips" :key="c.key" class="chip">
      {{ c.label }}
      <button class="chip__x" :title="`移除 ${c.label}`" @click="emit('remove', c.key)">×</button>
    </span>
    <button class="active-chips__clear" @click="emit('clear')">全部清除</button>
  </div>
</template>
