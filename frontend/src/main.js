// 装配入口：createApp + router + 全局错误处理。
// 不引 Pinia —— 共享状态只有登录态一处，用 composable 单例足够。
import { createApp } from 'vue'
import { MotionPlugin } from '@vueuse/motion'
import App from './App.vue'
import router from './router'
import './styles/theme.css'
// 共享组件样式（影片卡/网格、影评卡、详情弹窗）被多个视图复用，必须全局引入
import './styles/components.css'
import './styles/pages.css'
// 功能页样式（全局搜索/盲盒/首页/大屏/详情）
import './styles/features.css'
// Orbitron 科技感字体（@fontsource 本地自托管，SIL OFL 许可）
// 不走 Google Fonts CDN：实测本机网络不可达，会静默失败导致字体丢失
import '@fontsource/orbitron/400.css'
import '@fontsource/orbitron/500.css'
import '@fontsource/orbitron/700.css'
import '@fontsource/orbitron/900.css'
// 深空电影宇宙设计系统（仅洞察页 /analytics 使用 sp-space 作用域，不影响其余页面）
import './styles/space.css'
// 全屏 HUD 大屏（/screen）：100vh 不滚动 + 三区五块定位 + 玻璃拟态切角面板。
// 全局引入是因为 /analytics 第 07 章的「进入大屏」入口卡也复用其中样式。
import './styles/universe.css'
// 手绘「自我完成」揭示指令（itomdev 招牌效果）：v-sketch
import { sketch } from './directives/sketch.js'

const app = createApp(App)

app.use(router)
// 入场动效：@vueuse/motion（v-motion 指令 / <Motion> 组件）
app.use(MotionPlugin)
// 全局指令：v-sketch 给卡片/画廊框加手绘自我完成描边
app.directive('sketch', sketch)

// 全局错误处理：组件抛错不该留下白屏，至少留痕
app.config.errorHandler = (err, _instance, info) => {
  console.error('[电影盒子] 组件运行错误：', info, err)
}

app.mount('#app')
