"""
想看清单接口（全部需登录）。

| 接口 | 用途 |
|---|---|
| `POST   /api/v1/watchlist/{movie_id}` | 加入想看（幂等，重复加返回 200） |
| `GET    /api/v1/watchlist` | 我的想看清单（带影片详情，最新加入在前） |
| `DELETE /api/v1/watchlist/{movie_id}` | 移出想看 |

两个设计决定：

1. **写路径先校验影片存在**（与评分同一套逻辑）：给不存在的 movie_id
   加想看只会得到一张永远点不开的卡片。顺带拿标题冗余存清单里。
2. **列表 hydration**：清单只存 movie_id，卡片要海报/评分，用一次 mget
   批量取回（ES 没有 join，mget 一次 N 个，避免 N+1 请求把 ES 打满）。
   影片被数据更新淘汰时 movie 字段为 None，标题兜底展示，不整条消失。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from backend.api.v1.errors import es_unavailable
from backend.schemas.watchlist import WatchlistActionResponse, WatchlistItem, WatchlistResponse
from backend.services.auth import get_current_user
from backend.services.search_service import SearchUnavailable, _to_movie_hit, get_movie
from backend.services.watchlist_store import (
    add_to_watchlist,
    list_watchlist,
    remove_from_watchlist,
)
from common.es_client import get_es
from common.settings import settings

router = APIRouter()


@router.post("/{movie_id}", response_model=WatchlistActionResponse,
             summary="加入想看清单")
async def add_watch(
    movie_id: str,
    user: dict = Depends(get_current_user),
) -> WatchlistActionResponse:
    """把一部片加入想看。幂等 —— 连点星标按钮不会报错也不会加出两行。"""
    try:
        movie = await get_movie(movie_id)
    except SearchUnavailable as exc:
        raise es_unavailable(exc) from exc
    if movie is None:
        raise HTTPException(status_code=404,
                            detail=f"找不到 movie_id={movie_id} 的电影，无法加入想看")

    try:
        await add_to_watchlist(get_es(), user["username"], movie_id,
                               movie.title_zh or movie.title)
    except Exception as exc:  # noqa: BLE001 —— ES 写入失败统一 503
        raise es_unavailable(exc) from exc
    return WatchlistActionResponse(
        movie_id=movie_id, added=True,
        message=f"已加入想看：{movie.title_zh or movie.title}",
    )


@router.get("", response_model=WatchlistResponse, summary="我的想看清单")
async def my_watchlist(user: dict = Depends(get_current_user)) -> WatchlistResponse:
    """当前用户的想看清单，最新加入的在最前，影片详情一次 mget 批量取回。"""
    try:
        rows = await list_watchlist(get_es(), user["username"], size=200)
        if not rows:
            return WatchlistResponse(items=[], total=0)
        mget = await get_es().mget(index=settings.es_index_movies,
                                   ids=[r["movie_id"] for r in rows])
    except Exception as exc:  # noqa: BLE001
        raise es_unavailable(exc) from exc

    movies_by_id = {d["_id"]: _to_movie_hit(d)
                    for d in mget.get("docs", []) if d.get("found")}
    items = [
        WatchlistItem(
            movie_id=r["movie_id"],
            movie_title=r.get("movie_title"),
            added_at=r.get("created_at"),
            movie=movies_by_id.get(r["movie_id"]),
        )
        for r in rows
    ]
    return WatchlistResponse(items=items, total=len(items))


@router.delete("/{movie_id}", response_model=WatchlistActionResponse,
               summary="移出想看清单")
async def remove_watch(
    movie_id: str,
    user: dict = Depends(get_current_user),
) -> WatchlistActionResponse:
    """移出想看。没加过这部电影时返回 404（而不是假装成功）。"""
    try:
        removed = await remove_from_watchlist(get_es(), user["username"], movie_id)
    except Exception as exc:  # noqa: BLE001
        raise es_unavailable(exc) from exc
    if not removed:
        raise HTTPException(status_code=404, detail="你的想看清单里没有这部电影")
    return WatchlistActionResponse(movie_id=movie_id, added=False, message="已移出想看")
