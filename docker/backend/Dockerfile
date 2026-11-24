## 电影盒子 · 后端镜像（FastAPI + uvicorn）
##
## 设计要点：
##   1. **运行时依赖子集**（requirements.runtime.txt）：pandas/sklearn 等采集分析
##      期依赖不进镜像，体积从 ~1.2GB 压到 ~400MB。
##   2. **数据打进镜像**：data_lake/processed（266 部电影 + 49873 条影评）
##      和 data_lake/analysis（情感词典/主题/报告产物）一起 COPY 进去，
##      容器起来就能检索、能看影评洞察，不需要宿主再准备数据文件。
##   3. **入口三段式**（entrypoint.sh）：等 ES 就绪 → 索引缺失才自动导入
##      （幂等，_id 即业务主键）→ exec uvicorn。
##      所以 `docker compose up -d` 一条命令就是可用系统，而不是空壳。
##   4. **无 .env 依赖**：配置全部来自 compose 的 environment（ES_HOSTS 等），
##      镜像本身不携带任何密钥；.env 只服务本机开发。
##
## 构建：  docker-compose build backend
## 运行：  docker-compose up -d backend

FROM python:3.13-slim

# 容器里不写 .pyc、日志不缓冲，docker logs 能实时看到启动日志
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Asia/Shanghai

WORKDIR /app

# 先装依赖再拷代码 —— 改业务代码不用重新 pip install，层缓存生效
COPY docker/backend/requirements.runtime.txt ./requirements.runtime.txt
RUN pip install --no-cache-dir -r requirements.runtime.txt

# 运行路径模块（不含 ingest/transform/data：服务端不 import，见 requirements.runtime.txt 注释）
COPY common/ ./common/
COPY backend/ ./backend/
COPY index/ ./index/
COPY analysis/ ./analysis/

# 数据资产：processed 供索引导入，analysis 供 /insights 接口直读
COPY data_lake/processed/ ./data_lake/processed/
COPY data_lake/analysis/ ./data_lake/analysis/

COPY docker/backend/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000

# 健康检查：/api/v1/health 是现成探针；python:3.13-slim 没有 curl，用标准库 urllib
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=10 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=4).status==200 else 1)"

ENTRYPOINT ["/entrypoint.sh"]
