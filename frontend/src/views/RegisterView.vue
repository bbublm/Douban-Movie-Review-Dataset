<script setup>
// ============================================================
// 注册页。与登录页分离 —— 产品语义：没账号的人才会被送到这里
// （登录页有「免费注册」入口，顶导航未登录态也有）。
// 注册成功后不自动跳首页，而是登录态进「个人中心」引导补全口味，
// 因为新用户此时最需要的是知道「这里能干什么」。
// ============================================================
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { auth } from '../composables/useAuth'
import { toast } from '../composables/useToast'

const router = useRouter()

const form = ref({ username: '', nickname: '', password: '', confirm: '' })
const error = ref('')
const loading = ref(false)

async function onRegister() {
  error.value = ''
  if (form.value.password !== form.value.confirm) {
    error.value = '两次输入的密码不一致'
    return
  }
  if (form.value.password.length < 6) {
    error.value = '密码至少 6 位'
    return
  }
  loading.value = true
  try {
    await auth.register(
      form.value.username.trim(),
      form.value.password,
      form.value.nickname.trim() || undefined,
    )
    toast.success('注册成功，已自动登录')
    router.push('/me')
  } catch (e) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="auth-page">
    <div class="auth-shell">
      <div class="auth-shell__header">
        <div class="auth-shell__icon">🎬</div>
        <h1>加入电影盒子</h1>
        <p>生活是场电影，每个人都是主角</p>
      </div>

      <div class="panel auth-card">
        <h2 class="auth-card__title">注册</h2>
        <p class="auth-card__sub">注册后可以收藏影片、记录评分、同步口味</p>

        <div v-if="error" class="alert alert--error auth-error"><span>⚠️</span><span>{{ error }}</span></div>

        <form @submit.prevent="onRegister">
          <div class="field">
            <label class="field__label">用户名</label>
            <input v-model="form.username" class="input" autocomplete="username" placeholder="字母/数字/下划线" />
          </div>
          <div class="field">
            <label class="field__label">昵称（选填）</label>
            <input v-model="form.nickname" class="input" autocomplete="nickname" placeholder="别人怎么称呼你" />
          </div>
          <div class="field">
            <label class="field__label">密码</label>
            <input v-model="form.password" class="input" type="password" autocomplete="new-password" placeholder="至少 6 位" />
          </div>
          <div class="field">
            <label class="field__label">确认密码</label>
            <input v-model="form.confirm" class="input" type="password" autocomplete="new-password" placeholder="再输一遍" />
          </div>
          <button class="btn btn--primary btn--block" type="submit" :disabled="loading">
            {{ loading ? '注册中…' : '注 册' }}
          </button>
        </form>

        <div class="auth-alt">
          已经有账号了？<router-link to="/login" class="auth-alt__link">直接登录 →</router-link>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* 页面布局样式见 src/styles/pages.css（已在 main.js 全局引入） */
</style>
