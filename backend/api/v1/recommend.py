"""
阶段 5 前 · 推荐接口。

| 接口 | 范式 | 数据来源 |
|---|---|---|
| `GET /api/v1/recommend/similar/{movie_id}` | 基于内容 | more_like_this：拿该片自己的文本找气质相近的 |
| `GET /api/v1/recommend/popular` | 全局统计 | 贝叶斯加权分 WR（IMDb Top 250 同款公式） |
| `GET /api/v1/recommend/for-you` | 个性化 | 用户评分口味画像 → 候选召回（需登录） |

三个接口都不写推荐逻辑（那在 recommend_service.py），这里只做：
参数校验 → 调服务 → 领域异常翻 HTTP → 装配响应模型。

★ for-you 需要登录：口味画像来自"这个用户"的评分，
  没有登录就没有"你"——退化成热门榜虽然也行（服务层已处理），
  但接口上要求 Bearer token，语义更诚实。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from backend.api.v1.errors import es_unavailable
from backend.schemas.recommend import (
    ForYouResponse,
    PopularResponse,
    RecommendItem,
    SimilarResponse,
)
from backend.services.auth import get_current_user
from backend.services.recommend_service import (
    for_you_movies,
    popular_movies,
    similar_movies,
)
from backend.services.search_service import SearchUnavailable
from common.ttl_cache import cache

router = APIRouter()


@router.get("/similar/{movie_id}", response_model=SimilarResponse, summary="相似影片")
async def similar(
    movie_id: str,
    size: int = Query(default=10, ge=1, le=50, description="返回多少部相似影片"),
) -> SimilarResponse:
    """与指定影片"气质相近"的其它影片。

    两段召回，理由分开写：
        1. more_like_this —— 拿该片自己的简介/片名/类型找文本重合度高的片，
           不需要任何人工标注的"相似片"表；
        2. 同类型补齐 —— MLT 召回不足 size 张时，用同类型 + 评分/年代接近的片补上，
           不让详情页只剩一两个卡片。
    参考片不存在 → 404；库里实在没有相近的 → 200 + 空列表 + note（不是错误）。
    """
    try:
        base, contents, extras = await similar_movies(movie_id, size)
    except SearchUnavailable as exc:
        raise es_unavailable(exc) from exc
    if base is None:
        raise HTTPException(status_code=404, detail=f"找不到 movie_id={movie_id} 的电影")

    base_name = base.title_zh or base.title or movie_id
    genres = "、".join((base.genres_zh or [])[:2])
    content_reason = f"与《{base_name}》在剧情与类型上气质相近"
    genre_reason = (f"同属「{genres}」，评分与年代也接近" if genres
                    else "评分与年代跟它接近")
    items = (
        [RecommendItem(movie=m, reason=content_reason, score=m.score) for m in contents]
        + [RecommendItem(movie=m, reason=genre_reason, score=m.score) for m in extras]
    )
    mode = "content" if contents else ("genre" if extras else "none")
    note = None if items else "片库里暂时没有与它相近的其它影片"
    return SimilarResponse(base=base, items=items, mode=mode, note=note)


@router.get("/popular", response_model=PopularResponse, summary="热门榜单（贝叶斯加权）")
async def popular(
    size: int = Query(default=20, ge=1, le=50, description="榜单长度"),
) -> PopularResponse:
    """全局热门榜。不是按均分排，而是按贝叶斯加权分 WR：

        WR = (v/(v+m))·R + (m/(v+m))·C

    v=票数、R=均分、m=进榜门槛、C=全局均分。
    直接按均分排的话，一部 3 人打过 9.9 分的片会霸榜——
    WR 用 m 把"证据不足"的片往全局均分拉，票数越少越接近 C。
    formula 字段把 m 和 C 原样带回，前端可以直接把公式画给用户看。

    ★ 缓存：榜单是全库聚合，结果不随用户变，进 TTL 缓存（默认 5 分钟）。
      key 带 size，不同榜单长度互不污染。索引重建跑在独立进程里
      （invalidate 只对同进程有效，跨进程清内存缓存没有意义），
      所以这里接受"最多陈旧 5 分钟"，用 TTL 自然到期兜底。
    """
    cache_key = f"recommend:popular:{size}"

    async def _produce() -> PopularResponse:
        hits, params = await popular_movies(size)
        items = []
        for m in hits:
            if m.votes and m.votes >= 10000:
                votes_text = f"{m.votes / 10000:.1f} 万人"
            elif m.votes:
                votes_text = f"{m.votes} 人"
            else:
                votes_text = "票数未知"
            wr = m.score
            items.append(RecommendItem(
                movie=m,
                reason=f"加权分 {wr:.2f} · {votes_text}评分" if wr is not None else votes_text + "评分",
                score=wr,
            ))
        return PopularResponse(items=items, formula=params)

    try:
        return await cache.get_or_set(cache_key, _produce)
    except SearchUnavailable as exc:
        raise es_unavailable(exc) from exc


@router.get("/for-you", response_model=ForYouResponse, summary="个性化推荐（需登录）")
async def for_you(
    size: int = Query(default=20, ge=1, le=50, description="推荐多少部"),
    user: dict = Depends(get_current_user),
) -> ForYouResponse:
    """为当前登录用户生成个性化推荐。

    流程：取该用户 ≥8 分的影片 → 统计类型（top 3）与导演（top 2）画像
    → 按画像召回候选（排除已评分的全部影片）→ 每条附人类可读理由。

    没有评分记录时服务层退化为热门榜，并用 degraded=True 如实标注——
    不假装"懂你"。
    """
    try:
        data = await for_you_movies(user["username"], size)
    except SearchUnavailable as exc:
        raise es_unavailable(exc) from exc
    return ForYouResponse(**data)
