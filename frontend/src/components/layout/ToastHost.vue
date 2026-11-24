<script setup>
// Toast 宿主：固定在视口右上角，3 秒左右自动消失。
import { toast } from '../../composables/useToast'

const ICONS = { info: '💬', success: '✅', error: '⚠️' }
</script>

<template>
  <div class="toast-host">
    <transition-group name="toast">
      <div v-for="t in toast.state.toasts" :key="t.id" class="toast" :class="`toast--${t.type}`">
        <span class="toast__icon">{{ ICONS[t.type] || '💬' }}</span>
        <span class="toast__msg">{{ t.message }}</span>
        <button class="toast__x" @click="toast.dismiss(t.id)">×</button>
      </div>
    </transition-group>
  </div>
</template>

<style scoped>
.toast-host {
  position: fixed;
  top: 72px;
  right: 20px;
  z-index: 1000;
  display: flex;
  flex-direction: column;
  gap: 8px;
  pointer-events: none;
}
.toast {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 220px;
  max-width: 360px;
  padding: 10px 14px;
  border-radius: 8px;
  background: var(--surface);
  border: 1px solid var(--border-strong);
  box-shadow: var(--shadow-lg);
  font-size: 14px;
  pointer-events: auto;
  animation: toast-in 0.22s ease both;
}
.toast--success { border-color: rgba(95, 122, 97, 0.5); }
.toast--error { border-color: rgba(181, 80, 47, 0.5); }
.toast__msg { flex: 1; }
.toast__x {
  border: none;
  background: none;
  font-size: 16px;
  cursor: pointer;
  color: var(--text-3);
  padding: 0 2px;
}
.toast__x:hover { color: var(--text-main); }

@keyframes toast-in {
  from { opacity: 0; transform: translateX(16px); }
  to { opacity: 1; transform: translateX(0); }
}
.toast-enter-active, .toast-leave-active { transition: all 0.2s ease; }
.toast-leave-to { opacity: 0; transform: translateX(16px); }
</style>
