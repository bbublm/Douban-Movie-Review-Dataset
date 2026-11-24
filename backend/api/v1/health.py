"""
健康检查 / 自检接口。

| 端点 | 语义 | 谁在用 |
|---|---|---|
| `GET /health`        | 详细自检：应用 + ES 连通 + 索引名 + 数据源配置 | 开发排查、演示开场 |
| `GET /health/live`   | 活体探针：进程能响应就 200，**不看依赖** | 部署平台判断容器要不要重启 |
| `GET /health/ready`  | 就绪探针：ES 连不上就 503 | 部署平台判断要不要切流量 |
| `GET /health/metrics`| 进程内请求统计（有界快照） | 演示"服务真的在扛流量" |

liveness 与 readiness 分开是容器部署的常识：ES 抖动时 ready 失败（摘流量），
但 live 仍然成功（不重启容器）—— 否则 ES 一挂全容器被连环重启，永远起不来。
这两个探针路径同时被限流与请求日志豁免（见 backend/middleware.py）。
"""
from __future__ import annotations

import platform
import sys
import time

from fastapi import APIRouter, Response

from backend.middleware import stats
from common.es_client import get_es
from common.settings import settings
from common.ttl_cache import cache

router = APIRouter(tags=["健康检查"])

_STARTED_AT = time.time()


@router.get("/health", summary="服务与依赖健康检查")
async def health() -> dict:
    """返回后端与 Elasticsearch 的连通状态。

    elasticsearch.ok 为 true 才说明环境真正打通。
    连不上时 detail 里会带具体异常，方便定位是容器没起还是端口被占。
    """
    es_status: dict = {"ok": False, "detail": None, "cluster": None, "version": None}

    try:
        es = get_es().options(request_timeout=5)
        info = await es.info()
        cluster = await es.cluster.health()

        es_status["ok"] = True
        es_status["version"] = info.get("version", {}).get("number")
        es_status["cluster"] = {
            "name": info.get("cluster_name"),
            "status": cluster.get("status"),
            "nodes": cluster.get("number_of_nodes"),
            "indices": cluster.get("active_shards"),
        }
    except Exception as exc:  # noqa: BLE001 - 自检接口需要吞掉异常并回传
        es_status["detail"] = f"{type(exc).__name__}: {exc}"

    return {
        "app": settings.app_name,
        "status": "ok" if es_status["ok"] else "degraded",
        "debug": settings.debug,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "elasticsearch": es_status,
        "indices": {
            "movies": settings.es_index_movies,
            "reviews": settings.es_index_reviews,
            "users": settings.es_index_users,
            "ratings": settings.es_index_ratings,
            "watchlist": settings.es_index_watchlist,
        },
        "data_sources": {
            "tmdb_key_configured": bool(settings.tmdb_api_key),
            "kaggle_dataset": settings.kaggle_dataset,
            "wikidata_endpoint": settings.wikidata_endpoint,
        },
    }


@router.get("/health/live", summary="活体探针（不看依赖）")
async def live() -> dict:
    """活体探针：只要事件循环还能转就返回 200。

    刻意**不查 ES**——ES 抖动不是进程的错，把它算进 liveness
    会导致部署平台连环重启容器（重启治不了 ES 挂）。
    """
    return {
        "status": "alive",
        "uptime_seconds": round(time.time() - _STARTED_AT, 1),
    }


@router.get("/health/ready", summary="就绪探针（查 ES 连通）")
async def ready(response: Response) -> dict:
    """就绪探针：ES 连不上返回 503（让流量先切走/等待），连上返回 200。

    与 /health 的区别：只回答"能不能接流量"这一个问题，
    不带一堆诊断字段（探针会被高频调用，响应要小要快）。
    """
    try:
        es = get_es().options(request_timeout=3)
        await es.info()
    except Exception:  # noqa: BLE001 —— 探针只关心通不通
        response.status_code = 503
        return {"status": "not_ready", "reason": "elasticsearch unreachable"}
    return {"status": "ready"}


@router.get("/health/metrics", summary="进程内请求统计（有界快照）")
async def metrics() -> dict:
    """请求计数 / 延迟 / 最近 20 条请求。数据来自 middleware 的 RequestStats。

    有界性：计数器是标量，recent 是 maxlen=500 的 deque，只外发最近 20 条——
    这个端点本身不会成为内存泄漏点。
    """
    return {
        "rate_limit": {
            "enabled": settings.rate_limit_enabled,
            "general_per_minute": settings.rate_limit_general_per_minute,
            "auth_fail_per_minute": settings.rate_limit_auth_fail_per_minute,
        },
        "cache": cache.stats(),
        "cache_ttl_seconds": settings.cache_ttl_seconds,
        **stats.snapshot(),
    }
