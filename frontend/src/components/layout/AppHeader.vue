<script setup>
// ============================================================
// 顶导航（清单「全局功能」的落地）：
//  · Logo 回首页、导航链接当前页高亮
//  · 全局搜索框（自动补全，见 GlobalSearch）
//  · 固定金色「🎲 随便看看」—— 任意页面都能开盲盒
//  · 头像下拉：个人中心 / 我的收藏 / 退出；未登录显示登录·注册
//  · <1200px 折叠成汉堡菜单（手机端单栏的要求）
//
// 导航聚焦影片检索、影评洞察与采集演示；盲盒不占导航项，
// 右侧常驻「🎲 随便看看」金色按钮就是它的入口。
// 盲盒不占导航项：右侧常驻「🎲 随便看看」金色按钮就是它的入口
// （清单原文"任意页面可弹出盲盒"），导航里再放一项反而重复。
// ============================================================
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { auth } from '../../composables/useAuth'
import { blindBox } from '../../composables/useBlindBox'
import GlobalSearch from './GlobalSearch.vue'

const router = useRouter()
const menuOpen = ref(false)
const navOpen = ref(false)
const root = ref(null)

const isLoggedIn = computed(() => auth.isLoggedIn.value)
const isAdmin = computed(() => auth.isAdmin.value)
const user = computed(() => auth.state.user)
// 2026-10-19：大屏整体浅色化（用户"整个这个页面还是改成浅色的"）后，
// /screen 不再需要深色融态的导航 —— 回到站点默认的暖棕渐变导航，
// 与浅色大屏、与原系统视觉一致。
const isDark = computed(() => false)

// 命名全部从用户角度出发，不用开发词。
const NAV = [
  { to: '/', label: '首页', icon: '🏠' },
  { to: '/search', label: '检索', icon: '🔍' },
  // 「影评洞察」= 数据分析大屏（/screen）。用户 2026-10-19 明确：
  // 洞察页不要纵向长网页，大屏就是洞察页本体；且大屏保留本导航栏
  // （点击即达、不跳转），只隐藏页脚。2026-10-19 浅色化后导航回到默认态。
  { to: '/screen', label: '影评洞察', icon: '📊' },
  { to: '/dashboard/crawl', label: '采集演示', icon: '📡' },
]

function onNav(item) {
  navOpen.value = false
  if (item.to) router.push(item.to)
}

function toggleMenu() { menuOpen.value = !menuOpen.value }

function onClickOutside(e) {
  if (root.value && !root.value.contains(e.target)) menuOpen.value = false
}

function go(path) {
  menuOpen.value = false
  router.push(path)
}

function logout() {
  menuOpen.value = false
  auth.logout()
  router.push('/')
}

watch(() => router.currentRoute.value.fullPath, () => {
  menuOpen.value = false
  navOpen.value = false
})

if (typeof document !== 'undefined') {
  document.addEventListener('click', onClickOutside)
}

function avatarChar(name) {
  return (name || '?').trim().charAt(0).toUpperCase()
}
</script>

<template>
  <header class="app-header" :class="{ 'is-dark': isDark }">
    <div class="app-header__inner">
      <router-link to="/" class="app-header__brand">
        <span class="brand-icon">🎬</span>
        <span class="app-header__name">电影盒子</span>
        <span class="brand-subtitle">生活是场电影，每个人都是主角</span>
      </router-link>

      <button class="nav-burger" @click="navOpen = !navOpen" aria-label="菜单">☰</button>

      <nav class="app-nav" :class="{ 'is-open': navOpen }">
        <template v-for="item in NAV" :key="item.label">
          <router-link
            v-if="item.to"
            :to="item.to"
            class="app-nav__link"
            active-class="is-active"
          >
            <span class="nav-ico">{{ item.icon }}</span>
            <span>{{ item.label }}</span>
          </router-link>
          <button v-else class="app-nav__link" @click="onNav(item)">
            <span class="nav-ico">{{ item.icon }}</span>
            <span>{{ item.label }}</span>
          </button>
        </template>
      </nav>

      <GlobalSearch size="sm" class="app-header__search" />

      <button class="btn-box" @click="blindBox.openBox()">🎲 随便看看</button>

      <div class="user-area" ref="root">
        <template v-if="isLoggedIn">
          <button class="user-area__trigger" @click="toggleMenu">
            <span class="user-avatar">{{ avatarChar(user?.nickname || user?.username) }}</span>
            <span class="user-area__name">{{ user?.nickname || user?.username }}</span>
            <span v-if="isAdmin" class="role-badge">管理员</span>
            <span class="user-area__caret">▼</span>
          </button>
          <div v-if="menuOpen" class="user-menu">
            <div class="user-menu__name">@{{ user?.username }}</div>
            <button class="user-menu__item" @click="go('/me')">👤 个人中心</button>
            <button class="user-menu__item" @click="go('/me?tab=watch')">⭐ 我的收藏</button>
            <button class="user-menu__item user-menu__item--danger" @click="logout">退出登录</button>
          </div>
        </template>
        <template v-else>
          <button class="user-area__login" @click="go('/login')">登录</button>
          <button class="user-area__reg" @click="go('/register')">注册</button>
        </template>
      </div>
    </div>
  </header>
</template>
