// 路由表。视图一律懒加载（动态 import）—— 首页是主路径，
// 分析大屏（ECharts）不该进首包。
//
// 结构按功能清单一级模块划分：
//   首页 / 影片检索 / 影评洞察 / 采集演示 / 电影详情 / 个人中心
//
// history 模式：dev 期 vite 自动处理 SPA fallback；
// 生产用 nginx 时需要 try_files $uri $uri/ /index.html（见 README）。
import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    name: 'home',
    component: () => import('../views/HomeView.vue'),
    meta: { title: '首页' },
  },
  {
    path: '/search',
    name: 'search',
    component: () => import('../views/SearchView.vue'),
    meta: { title: '影片检索' },
  },
  {
    path: '/movie/:id',
    name: 'movie',
    component: () => import('../views/MovieView.vue'),
    meta: { title: '电影详情' },
  },
  { path: '/mix', redirect: '/' },
  { path: '/map', redirect: '/' },
  {
    // 院线热映榜 Top 10 在首页；点卡片进「站内采集档案」详情页。
    // 这里一律是自己的页面，不再把访客外链到数据源站点。
    path: '/nowplaying',
    redirect: '/',
  },
  {
    path: '/nowplaying/:id',
    name: 'nowplaying-detail',
    component: () => import('../views/NowPlayingView.vue'),
    meta: { title: '院线热映档案' },
  },
  {
    // 豆瓣 × 预告片 联合洞察已并入影评洞察大屏（/screen）。
    path: '/douban-insights',
    redirect: '/screen',
  },
  // 影评洞察 = 全屏数据分析大屏（用户 2026-10-19 明确：洞察页不要再做成
  // 纵向长网页，数据分析大屏本身就是影评洞察页）。原纵向长页 AnalyticsView /
  // InsightsView 与其子组件已于 2026-10-20 清理（被大屏取代、零路由引用），
  // 两个旧入口（/analytics、/insights）统一收敛到同一个全屏 HUD。
  { path: '/analytics', redirect: '/screen' },
  { path: '/insights', redirect: '/screen' },
  // 发现页已移除；旧书签 /discover、/for-you 统一回首页。
  { path: '/discover', redirect: '/' },
  { path: '/for-you', redirect: '/' },
  {
    path: '/login',
    name: 'login',
    component: () => import('../views/LoginView.vue'),
    meta: { title: '登录' },
  },
  {
    // 注册独立成页：没账号的人才需要注册（用户反馈两表并排对谁都是干扰）
    path: '/register',
    name: 'register',
    component: () => import('../views/RegisterView.vue'),
    meta: { title: '注册' },
  },
  {
    path: '/me',
    name: 'me',
    component: () => import('../views/MeView.vue'),
    meta: { title: '个人中心' },
  },
  {
    path: '/about',
    name: 'about',
    component: () => import('../views/AboutView.vue'),
    meta: { title: '项目说明' },
  },
  {
    // 影评洞察 = 全屏数据分析大屏（用户 2026-10-19 明确：洞察页不要再做成
    // 纵向长网页，数据分析大屏本身就是影评洞察页）。旧纵向长页已于 2026-10-20
    // 清理，两个旧入口（/analytics、/insights）统一收敛到同一个全屏 HUD。
    //
    // 2026-10-19 二次调整：大屏不再是"裸奔"全屏（meta.bare 已废除）——
    // 用户要求点击「影评洞察」就在站点内看到大屏、保留导航栏不跳转。
    // 故只隐藏页脚（100vh 一屏到底，页脚会逼出滚动条），导航栏照常显示。
    path: '/screen',
    name: 'screen',
    component: () => import('../views/UniverseScreen.vue'),
    meta: { title: '影评洞察', hideFooter: true },
  },
  {
    path: '/dashboard/crawl',
    name: 'crawl-dashboard',
    component: () => import('../views/CrawlDemoView.vue'),
    meta: { title: '爬虫采集流水线演示中心', hideFooter: true },
  },
  // 未匹配路径回首页（检索平台没有 404 页的必要时不浪费一页）
  { path: '/:pathMatch(.*)*', redirect: '/' },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
  scrollBehavior: () => ({ top: 0 }),
})

router.afterEach((to) => {
  const section = to.meta?.title
  document.title = section ? `${section} · 电影盒子` : '电影盒子'
})

export default router
