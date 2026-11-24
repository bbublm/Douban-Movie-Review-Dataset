import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 开发联调：/api 代理到本机 uvicorn（8000），前端零 CORS 改动。
// 生产构建后 dist/ 可由任意静态服务器托管，仍需反代 /api 到后端。
export default defineConfig({
  plugins: [vue()],
  // 显式声明需要预构建的依赖：避免 Vite 在运行中"发现新依赖"时重建缓存，
  // 那会批量删除 node_modules/.vite/deps_temp_* 而触发环境的删除守卫。
  optimizeDeps: {
    include: [
      'three',
      'postprocessing',
      'camera-controls',
      'maath/random',
      'maath/easing',
      'countup.js',
      '@vueuse/motion',
      'echarts-wordcloud',
      'gsap',
      // gsap 子路径也要显式声明：否则 dev 期首次访问到首页时 Vite 才"发现"它，
      // 触发运行时重优化 + 清理 deps_temp，被环境删除守卫拦下导致 dev server 崩。
      'gsap/ScrollTrigger',
    ],
  },
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    outDir: 'dist',
    // echarts 完整包 ~1MB，默认 500KB 警告阈值只会刷噪音，抬到 1.2MB
    chunkSizeWarningLimit: 1200,
  },
})
