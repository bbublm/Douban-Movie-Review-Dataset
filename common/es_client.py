"""
Elasticsearch 客户端工厂。

后端服务用 AsyncElasticsearch（FastAPI 是异步的，
阻塞式 IO 会把事件循环卡死）；
采集脚本用同步 Elasticsearch（顺序读写，逻辑更简单）。
两者共用同一份连接配置。
"""
from __future__ import annotations

from typing import Any

from common.settings import settings

_async_client: Any = None
_sync_client: Any = None


def _common_kwargs() -> dict:
    kwargs: dict = {
        "hosts": settings.es_host_list,
        "request_timeout": 30,
        # 开发期关掉 SSL 校验告警噪音
        "verify_certs": False,
        "ssl_show_warn": False,
    }
    if settings.es_username:
        kwargs["basic_auth"] = (settings.es_username, settings.es_password)
    return kwargs


# ---------------- 异步（FastAPI 用）----------------

def get_es():
    """获取全局异步客户端（惰性创建，进程内单例）。"""
    global _async_client
    if _async_client is None:
        from elasticsearch import AsyncElasticsearch

        _async_client = AsyncElasticsearch(**_common_kwargs())
    return _async_client


async def close_es() -> None:
    global _async_client
    if _async_client is not None:
        await _async_client.close()
        _async_client = None


# ---------------- 同步（采集/建索引脚本用）----------------

def get_sync_es():
    global _sync_client
    if _sync_client is None:
        from elasticsearch import Elasticsearch

        _sync_client = Elasticsearch(**_common_kwargs())
    return _sync_client


def close_sync_es() -> None:
    global _sync_client
    if _sync_client is not None:
        _sync_client.close()
        _sync_client = None
