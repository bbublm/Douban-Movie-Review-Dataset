"""
想看清单存储：ES 上的"我想看"收藏关系。

设计要点（与 ratings_store 同构，踩过的坑不踩第二次）：

1. **_id = "用户名:movie_id"**。重复收藏是幂等 upsert（200 而不是 409）——
   前端的星标按钮经得起用户连点、刷新、重试。
   用户名不能含冒号由注册规则 ^[a-zA-Z0-9_]+$ 保证（双保险）。

2. **标题冗余存一份**。想看列表页直接展示，不为拼一个列表回查 movies 索引。

3. **列表带 hydration**：`list_watchlist` 只存 (movie_id, 标题, 时间)，
   卡片要海报/评分这些字段，由 API 层拿 movie_id 批量回 movies 取
   （ES 没有 join，mget 一次拿一批，避免 N+1 请求）。

4. **索引自举**：与 users/ratings 一样，服务启动时 ensure，不需要外部脚本。
"""
from __future__ import annotations

from datetime import datetime, timezone

from elasticsearch import AsyncElasticsearch
from elasticsearch.exceptions import NotFoundError

from common.settings import settings
from index.mappings import WATCHLIST_MAPPING


class WatchlistError(Exception):
    """想看清单领域异常基类。"""


def _watch_id(username: str, movie_id: str) -> str:
    return f"{username}:{movie_id}"


async def ensure_watchlist_index(es: AsyncElasticsearch) -> None:
    """watchlist 索引不存在就建好（幂等）。"""
    if await es.indices.exists(index=settings.es_index_watchlist):
        return
    await es.indices.create(index=settings.es_index_watchlist, mappings=WATCHLIST_MAPPING)


async def add_to_watchlist(
    es: AsyncElasticsearch,
    username: str,
    movie_id: str,
    movie_title: str | None,
) -> dict:
    """加入想看（重复调用是覆盖，幂等）。返回文档。"""
    await ensure_watchlist_index(es)
    doc = {
        "username": username,
        "movie_id": movie_id,
        "movie_title": movie_title,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await es.index(index=settings.es_index_watchlist,
                   id=_watch_id(username, movie_id), document=doc, refresh=True)
    return doc


async def remove_from_watchlist(es: AsyncElasticsearch, username: str, movie_id: str) -> bool:
    """移出想看。返回是否真的移除了（不存在 → False，接口层据此回 404）。"""
    try:
        await es.delete(index=settings.es_index_watchlist,
                        id=_watch_id(username, movie_id), refresh=True)
        return True
    except NotFoundError:
        return False


async def list_watchlist(
    es: AsyncElasticsearch,
    username: str,
    size: int = 100,
) -> list[dict]:
    """取某用户的想看清单（按加入时间倒序，最新看的想看在最前）。"""
    resp = await es.search(
        index=settings.es_index_watchlist,
        size=size,
        query={"bool": {"filter": [{"term": {"username": username}}]}},
        sort=[{"created_at": {"order": "desc"}}],
    )
    return [h["_source"] for h in resp["hits"]["hits"]]
