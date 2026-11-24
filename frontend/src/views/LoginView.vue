<script setup>
// ============================================================
// 登录页。只有登录一件事 —— 注册是独立页面（/register），
// 这里放一个入口：「没有账号？免费注册」。
// 产品语义：有账号的人来登录，没账号的人才会去注册，
// 两个表单并排摆在一页，对谁都是干扰（用户原话）。
// next 参数：从需要登录的页面被踢过来时，登录后送回原页面。
// ============================================================
import { ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { auth } from '../composables/useAuth'
import { toast } from '../composables/useToast'

const route = useRoute()
const router = useRouter()

const form = ref({ username: '', password: '' })
const error = ref('')
const loading = ref(false)

async function onLogin() {
  error.value = ''
  loading.value = true
  try {
    await auth.login(form.value.username.trim(), form.value.password)
    toast.success(`欢迎回来，${auth.state.user?.nickname || auth.state.user?.username}`)
    goNext()
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

function goNext() {
  const next = route.query.next
  router.push(typeof next === 'string' && next.startsWith('/') ? next : '/')
}
</script>

<template>
  <!-- 全屏棕渐变 + 玻璃拟态卡：原系统 login-container / login-card 的 Vue 版 -->
  <div class="auth-page">
    <div class="auth-shell">
      <div class="auth-shell__header">
        <div class="auth-shell__icon">🎬</div>
        <h1>欢迎来到电影盒子</h1>
        <p>生活是场电影，每个人都是主角</p>
      </div>

      <div class="panel auth-card">
        <h2 class="auth-card__title">登录</h2>
        <p class="auth-card__sub">登录后可以收藏影片、记录评分、同步口味</p>

        <div v-if="error" class="alert alert--error auth-error"><span>⚠️</span><span>{{ error }}</span></div>

        <form @submit.prevent="onLogin">
          <div class="field">
            <label class="field__label">用户名</label>
            <input v-model="form.username" class="input" autocomplete="username" placeholder="字母/数字/下划线" />
          </div>
          <div class="field">
            <label class="field__label">密码</label>
            <input v-model="form.password" class="input" type="password" autocomplete="current-password" placeholder="••••••" />
          </div>
          <button class="btn btn--primary btn--block" type="submit" :disabled="loading">
            {{ loading ? '登录中…' : '登 录' }}
          </button>
        </form>

        <div class="auth-demo">
          💡 演示管理员：<b>admin</b> / <b>admin123</b>（服务启动时自动播种，仅本机开发用）
        </div>

        <div class="auth-alt">
          还没有账号？<router-link to="/register" class="auth-alt__link">免费注册 →</router-link>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* 页面布局样式见 src/styles/pages.css（已在 main.js 全局引入） */
</style>
