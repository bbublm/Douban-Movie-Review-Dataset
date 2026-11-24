## 电影盒子 · 前端镜像（Vite 构建 + Nginx 托管）
##
## 设计要点：
##   1. **多阶段构建**：node:22-alpine 里 npm ci + vite build，
##      产出的 dist/ 只含静态文件；运行时用 nginx:alpine，
##      最终镜像 ~80MB，里面没有 node、没有源码、没有 node_modules。
##   2. **SPA fallback**：前端是 history 模式路由（/search /mix /map …），
##      直接刷新深链接时 nginx 要回退到 index.html，否则 404。
##   3. **/api 反代**：前端代码里 API 基准是相对路径 /api/v1（见 src/api/index.js），
##      由 nginx 代到 compose 网络里的 backend:8000 —— 浏览器看到的是同源请求，
##      不需要 CORS，前端零环境判断。
##   4. **指纹资产长缓存**：vite 产出的 /assets/*.js|css 带内容 hash，
##      可以放心 Cache-Control: immutable。
##
## 构建（在仓库根目录执行）：
##   docker-compose build frontend
## 注意 build context 是仓库根目录（compose 里指定），
## node_modules / dist 由根 .dockerignore 挡在上下文外，镜像内重新安装与构建。

# ---------- 阶段一：构建 ----------
FROM node:22-alpine AS build

WORKDIR /app

# 先只拷依赖清单 —— 业务代码改动不用重新 npm install，层缓存生效
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ .
RUN npm run build

# ---------- 阶段二：托管 ----------
FROM nginx:1.27-alpine

# 站点配置（SPA fallback + /api 反代 + 静态缓存）
COPY docker/frontend/nginx.conf /etc/nginx/conf.d/default.conf

COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

# nginx 官方镜像自带 /docker-entrypoint.d 健康机制，这里用探针即可
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=6 \
  CMD wget -q -O /dev/null http://127.0.0.1/ || exit 1
