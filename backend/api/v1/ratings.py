"""
阶段 5 前 · 评分接口（全部需登录）。

| 接口 | 用途 |
|---|---|
| `POST /api/v1/ratings` | 给电影打分 / 改分（同一部片重复打是覆盖） |
| `GET  /api/v1/ratings` | 我的评分列表（按分数倒序） |
| `DELETE /api/v1/ratings/{movie_id}` | 删除一条评分 |

评分是整个推荐系统的**输入**：for-you 的口味画像完全由
"用户给哪些片打了 ≥8 分"统计而来。所以写路径上多做两件事：

1. **先校验电影存在**（movies 索引 get 一下）。给不存在的 movie_id
   打分会污染口味画像，404 掉。顺带拿到标题冗余进评分文档——
   推荐理由要展示"因为你给《X》打了 9 分"，不想为拼一句话回查一次。
2. **幂等 upsert**（_id = 用户名:movie_id）。重复打分是覆盖而不是追加，
   不会给一个人刷出两行评分。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from backend.api.v1.errors import es_unavailable
from backend.schemas.recommend import RatingItem, RatingRequest
from backend.services.auth import get_current_user
from backend.services.ratings_store import (
    delete_rating,
    list_user_ratings,
    upsert_rating,
)
from backend.services.search_service import SearchUnavailable, get_movie
from common.es_client import get_es

router = APIRouter()


@router.post("", response_model=RatingItem, summary="给电影打分 / 改分")
async def rate_movie(
    req: RatingRequest,
    user: dict = Depends(get_current_user),
) -> RatingItem:
    """给一部电影打分（0.5 ~ 10 分，与 IMDb/TMDB 同量纲）。

    重复给同一部片打分会**覆盖**旧分数——改分不需要先删再打。
    """
    try:
        movie = await get_movie(req.movie_id)
    except SearchUnavailable as exc:
        raise es_unavailable(exc) from exc
    if movie is None:
        raise HTTPException(status_code=404,
                            detail=f"找不到 movie_id={req.movie_id} 的电影，无法给不存在的影片打分")

    try:
        doc = await upsert_rating(
            get_es(), user["username"], req.movie_id,
            movie.title_zh or movie.title, req.score,
        )
    except Exception as exc:  # noqa: BLE001 —— ES 写入失败统一 503
        raise es_unavailable(exc) from exc
    return RatingItem(**doc)


@router.get("", response_model=list[RatingItem], summary="我的评分列表")
async def my_ratings(user: dict = Depends(get_current_user)) -> list[RatingItem]:
    """当前用户的全部评分，按分数倒序（最爱的在最前）。"""
    try:
        rows = await list_user_ratings(get_es(), user["username"], size=200)
    except Exception as exc:  # noqa: BLE001
        raise es_unavailable(exc) from exc
    return [
        RatingItem(
            movie_id=r["movie_id"],
            movie_title=r.get("movie_title"),
            score=r["score"],
            created_at=r.get("created_at"),
        )
        for r in rows
    ]


@router.delete("/{movie_id}", summary="删除我的评分")
async def remove_rating(
    movie_id: str,
    user: dict = Depends(get_current_user),
) -> dict:
    """删除一条评分。删除后 for-you 的口味画像会随之变化（下一部推荐就不参考它了）。"""
    try:
        deleted = await delete_rating(get_es(), user["username"], movie_id)
    except Exception as exc:  # noqa: BLE001
        raise es_unavailable(exc) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="你没有给这部电影打过评分")
    return {"message": "已删除评分", "movie_id": movie_id}
