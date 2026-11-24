"""
想看清单接口的请求 / 响应模型。

WatchlistItem 里 movie 字段允许为 None：影片可能后来被数据更新淘汰
（movies 索引重建时没进来），此时列表照样展示标题兜底，不整条消失。
"""
from __future__ import annotations

from backend.schemas.search import MovieHit
from pydantic import BaseModel


class WatchlistItem(BaseModel):
    """一条想看记录。movie 为 hydration 后的影片详情（可能为 None）。"""

    movie_id: str
    movie_title: str | None = None
    added_at: str | None = None
    movie: MovieHit | None = None


class WatchlistResponse(BaseModel):
    items: list[WatchlistItem] = []
    total: int = 0


class WatchlistActionResponse(BaseModel):
    """加入/移出的操作结果。added=True 表示本次调用真的写入了。"""

    movie_id: str
    added: bool
    message: str
