<script setup>
import { ref, watch, onMounted, onUnmounted } from 'vue'

// 数字滚动动画：从 0（或当前值）缓动到目标值。
// 原位于 components/insights/RollingNumber.vue，因大屏 /screen 依赖而迁至 components/screen/。
// 契约（各调用方共用，勿删）：
//   value   目标数值
//   decimals 小数位（默认 0；口碑值 1~2 位，百分比 1 位）
//   duration 动画时长 ms
//   delay    延迟启动 ms（配合错峰入场）
//   suffix   后缀（如 '%'）
defineOptions({ inheritAttrs: false })

const props = defineProps({
  value: { type: Number, default: 0 },
  decimals: { type: Number, default: 0 },
  duration: { type: Number, default: 1500 },
  delay: { type: Number, default: 0 },
  suffix: { type: String, default: '' },
})

const display = ref(0)
let raf = null
let timer = null

/** 千分位整数 + 固定小数位 */
function format(n) {
  const d = Math.max(0, Math.min(4, props.decimals || 0))
  const fixed = n.toFixed(d)
  const [int, dec] = fixed.split('.')
  const intFmt = Number(int).toLocaleString('en-US')
  return (dec ? `${intFmt}.${dec}` : intFmt) + props.suffix
}

function stop() {
  if (raf) cancelAnimationFrame(raf)
  if (timer) clearTimeout(timer)
  raf = null
  timer = null
}

function animate(to) {
  stop()
  const from = display.value
  const dur = Math.max(1, props.duration)
  const run = () => {
    const start = performance.now()
    const step = (t) => {
      const p = Math.min(1, (t - start) / dur)
      const eased = 1 - Math.pow(1 - p, 3)
      display.value = from + (to - from) * eased
      if (p < 1) raf = requestAnimationFrame(step)
      else { display.value = to; raf = null }
    }
    raf = requestAnimationFrame(step)
  }
  if (props.delay > 0) timer = setTimeout(run, props.delay)
  else run()
}

watch(() => props.value, (v) => animate(v))
onMounted(() => animate(props.value))
onUnmounted(stop)
</script>

<template>
  <span>{{ format(display) }}</span>
</template>
