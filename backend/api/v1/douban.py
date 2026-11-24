"""
阶段 1f · 豆瓣数据接口。

| 接口 | 用途 |
|---|---|
| `GET /api/v1/douban/nowplaying` | 豆瓣「正在热映」院线榜单 |
| `GET /api/v1/douban/nowplaying/{id}` | 单条热映片的站内采集档案（不外链源站） |

为什么单独一个路由而不是塞进 /search？
    热映榜是「库内片库之外的独立实体」（院线新片大多不在 266 部里，
    也没有 tmdb/imdb 锚点），它不参与 movies 混合检索，只做独立的卡片墙展示，
    单独成路由语义更清晰，也避免污染检索分面。
    卡片点击一律留在站内：详情读的是本索引里已采集的文档，不把访客送回源站。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from backend.schemas.search import (
    DoubanInsightsResponse,
    NowPlayingDetail,
    NowPlayingResponse,
)
from backend.services.search_service import (
    SearchUnavailable,
    get_douban_insights,
    get_nowplaying,
    get_nowplaying_detail,
)

router = APIRouter()


def _guard(exc: SearchUnavailable) -> HTTPException:
    return HTTPException(
        status_code=503,
        detail={
            "message": "检索服务暂时不可用（Elasticsearch 未连接或查询失败）",
            "hint": "先执行 docker-compose up -d，再跑 python -m index.run_index build 灌数据",
            "error": str(exc)[:300],
        },
    )


@router.get("/nowplaying", response_model=NowPlayingResponse, summary="豆瓣正在热映榜单")
async def nowplaying(
    size: int = Query(default=50, ge=1, le=100, description="最多返回多少条"),
) -> NowPlayingResponse:
    """拉取豆瓣院线热映榜。按热度（评价人数）降序返回全量，前端直接渲染。

    数据来自 douban_nowplaying 索引，由 `python -m ingest.run_collect douban`
    采集的 `/cinema/nowplaying/` 公开页。
    """
    try:
        return await get_nowplaying(size=size)
    except SearchUnavailable as exc:
        raise _guard(exc) from exc


@router.get("/nowplaying/{douban_id}", response_model=NowPlayingDetail,
            summary="单条院线热映影片的站内采集档案")
async def nowplaying_detail(douban_id: str) -> NowPlayingDetail:
    """站内详情页专用：读爬虫已落库的采集文档，不跳转、不现爬源站。

    响应除榜单字段外，还带 library_match —— 该片若在库内片库有严格同名影片，
    前端就能一键进 /movie/:id；库外片则给出站内检索入口。
    """
    try:
        detail = await get_nowplaying_detail(douban_id)
    except SearchUnavailable as exc:
        raise _guard(exc) from exc
    if detail is None:
        raise HTTPException(status_code=404, detail="这条院线热映记录不在已采集档案里")
    return detail


@router.get("/insights", response_model=DoubanInsightsResponse, summary="豆瓣 + 预告片 联合洞察")
async def insights() -> DoubanInsightsResponse:
    """豆瓣短评（文本数据）+ TMDB 预告片（视频数据）的联合聚合分析。

    返回：评分分歧（TMDB vs 豆瓣）、豆瓣情感分布、豆瓣高分 Top、
    预告片覆盖率（总库 + 按年代）、类型 × 情感。前端 Flourish 风格分析页直接渲染。
    """
    try:
        return await get_douban_insights()
    except SearchUnavailable as exc:
        raise _guard(exc) from exc
