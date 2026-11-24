"""
用户评分存储：ES 上的评分 CRUD，个性化推荐的输入。

设计要点：

1. **_id = "用户名:movie_id"**。重复打分同一部片是覆盖更新（upsert），
   不会给一个人刷出两行评分。副作用是用户名不能含冒号 ——
   注册规则已限定 ^[a-zA-Z0-9_]+$（schemas/auth.py），双保险。

2. **电影标题冗余存一份**。推荐理由要展示"因为你给《X》打了 9 分"，
    不想为拼一句话去 movies 索引回查一次（冗余换一次 RTT，评分场景值）。

3. **写评分前校验电影存在**。给不存在的 movie_id 打分会污染推荐口味，
    所以先 get 一下 movies（不存在就 404）。这一步顺带拿到标题。
"""
from __future__ import annotations

from datetime import datetime, timezone

from elasticsearch import AsyncElasticsearch
from elasticsearch.exceptions import NotFoundError

from common.settings import settings
from index.mappings import RATINGS_MAPPING


class RatingError(Exception):
    """评分领域异常基类。"""


class MovieNotFound(RatingError):
    """被打分的电影不存在。"""


def _rating_id(username: str, movie_id: str) -> str:
    return f"{username}:{movie_id}"


async def ensure_ratings_index(es: AsyncElasticsearch) -> None:
    """ratings 索引不存在就建好（幂等）。"""
    if await es.indices.exists(index=settings.es_index_ratings):
        return
    await es.indices.create(index=settings.es_index_ratings, mappings=RATINGS_MAPPING)


async def upsert_rating(
    es: AsyncElasticsearch,
    username: str,
    movie_id: str,
    movie_title: str | None,
    score: float,
) -> dict:
    """打分 / 改分（同一用户同一电影覆盖写）。"""
    await ensure_ratings_index(es)
    doc = {
        "username": username,
        "movie_id": movie_id,
        "movie_title": movie_title,
        "score": score,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await es.index(index=settings.es_index_ratings,
                   id=_rating_id(username, movie_id), document=doc, refresh=True)
    return doc


async def delete_rating(es: AsyncElasticsearch, username: str, movie_id: str) -> bool:
    """删除一条评分。返回是否真的删掉了（不存在 → False，接口层据此回 404）。"""
    try:
        await es.delete(index=settings.es_index_ratings,
                        id=_rating_id(username, movie_id), refresh=True)
        return True
    except NotFoundError:
        return False


async def list_user_ratings(
    es: AsyncElasticsearch,
    username: str,
    min_score: float | None = None,
    size: int = 100,
) -> list[dict]:
    """取某用户的评分（按分数倒序）。min_score 用于只取"喜欢"的片。"""
    query: dict = {"bool": {"filter": [{"term": {"username": username}}]}}
    if min_score is not None:
        query["bool"]["filter"].append({"range": {"score": {"gte": min_score}}})
    resp = await es.search(
        index=settings.es_index_ratings,
        size=size,
        query=query,
        sort=[{"score": {"order": "desc"}}],
    )
    return [h["_source"] for h in resp["hits"]["hits"]]
