<script setup>
// 根组件：渐变导航 + 路由视图（淡入上移过渡）+ 页脚。
// 登录态在挂载时 hydrate 一次（localStorage 里有 token 就换回 user）。
// 影评洞察页（/screen）为浅色大屏（2026-10-19 用户定调"整个页面改成浅色的"），
// 导航回到站点默认暖棕渐变态，不再需要深色融色。
// 大屏页保留导航栏（用户 2026-10-19：点击影评洞察就在站点内看大屏，不跳转），
// 只隐藏页脚 —— 100vh 一屏到底，多一个像素都会产生滚动条。
import { computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import AppHeader from './components/layout/AppHeader.vue'
import AppFooter from './components/layout/AppFooter.vue'
import ToastHost from './components/layout/ToastHost.vue'
import BlindBox from './components/box/BlindBox.vue'
import { auth } from './composables/useAuth'
import { useHotkeys } from './composables/useHotkeys'

// 快捷键要在 setup 同步区注册（内部用 onMounted/onUnmounted），
// 不能塞进 onMounted 回调里 —— 那时已经没有活动实例可挂了。
const route = useRoute()
// 仅大屏页（/screen）隐藏页脚；导航栏全站常驻（meta.bare 已于 2026-10-19 废除）
const hideFooter = computed(() => !!route.meta?.hideFooter)

useHotkeys()

onMounted(() => auth.init())
</script>

<template>
  <div class="app-shell">
    <AppHeader />
    <main class="app-main">
      <router-view v-slot="{ Component }">
        <transition name="fade-up" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </main>
    <AppFooter v-if="!hideFooter" />
    <!-- 盲盒挂在根上：导航、首页、检索页、混搭器都能唤起同一个弹窗 -->
    <BlindBox />
    <ToastHost />
  </div>
</template>
