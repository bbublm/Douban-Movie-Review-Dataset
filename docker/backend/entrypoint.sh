#!/bin/sh
# ============================================================
# 电影盒子 · 后端容器入口
#
# 三段式：
#   1. 等 Elasticsearch 就绪（compose 的 depends_on 只等"容器起来"，
#      ES 进程 ready 还要几十秒，这里再兜一层，避免后端起来连不上 ES）
#   2. 索引缺失才自动导入（数据已打进镜像；_id 是业务主键，重跑幂等；
#      已有索引直接跳过，不让每次重启都重导 5 万条影评）
#   3. exec uvicorn —— 用 exec 替换 shell 进程，容器停止时信号直达 uvicorn
# ============================================================
set -eu

echo "[entrypoint] 电影盒子后端启动中，等待 Elasticsearch …"

# ---------- 1. 等 ES 就绪 ----------
python - <<'PY'
import os
import sys
import time
import urllib.request

host = os.environ.get("ES_HOSTS", "http://elasticsearch:9200").split(",")[0].strip()
url = host.rstrip("/") + "/_cluster/health?timeout=2s"
deadline = time.time() + float(os.environ.get("ES_WAIT_SECONDS", "180"))
last = ""
while time.time() < deadline:
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            if resp.status == 200:
                print(f"[entrypoint] ES 已就绪：{host}")
                sys.exit(0)
    except Exception as exc:  # noqa: BLE001 —— 等待期任何异常都继续重试
        last = f"{type(exc).__name__}: {exc}"
    time.sleep(2)
print(f"[entrypoint] 等待 ES 就绪超时（{last or '无响应'}）")
sys.exit(1)
PY

# ---------- 2. 索引缺失才自动导入 ----------
# 退出码约定：0 = 索引齐全直接起服务；42 = 缺索引，需要先导入
set +e
python - <<'PY'
import sys

from common.es_client import get_sync_es
from common.settings import settings

es = get_sync_es()
missing = []
for alias in (settings.es_index_movies, settings.es_index_reviews):
    try:
        has_alias = es.indices.exists_alias(name=alias)
        has_index = es.indices.exists(index=alias)
    except Exception:  # noqa: BLE001 —— 探测失败按缺失处理，交给 build 去报详细错
        has_alias = has_index = False
    if not (has_alias or has_index):
        missing.append(alias)

if missing:
    print("[entrypoint] 缺失索引：" + ", ".join(missing))
    sys.exit(42)
print("[entrypoint] 索引已存在（movies / reviews），跳过自动导入")
PY
status=$?
set -e

if [ "$status" -eq 42 ]; then
    echo "[entrypoint] 开始自动导入索引（数据已打进镜像，幂等可重跑）…"
    python -m index.run_index build
    echo "[entrypoint] 索引导入完成"
fi

# ---------- 3. 启动服务 ----------
echo "[entrypoint] 启动 uvicorn（0.0.0.0:${API_PORT:-8000}）…"
exec uvicorn backend.main:app --host 0.0.0.0 --port "${API_PORT:-8000}" "$@"
