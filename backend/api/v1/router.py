"""
v1 路由汇总。

新增模块的方式（后续阶段照着做）：
    from backend.api.v1 import search
    api_router.include_router(search.router, prefix="/search", tags=["检索"])
"""
from __future__ import annotations

from fastapi import APIRouter

from backend.api.v1 import auth, douban, fun, health, img, insights, ratings, recommend, search, watchlist

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(auth.router, prefix="/auth", tags=["用户认证"])
api_router.include_router(search.router, prefix="/search", tags=["混合检索"])
api_router.include_router(douban.router, prefix="/douban", tags=["豆瓣数据源"])
api_router.include_router(insights.router, prefix="/insights", tags=["分析洞察"])
api_router.include_router(recommend.router, prefix="/recommend", tags=["智能推荐"])
api_router.include_router(ratings.router, prefix="/ratings", tags=["评分"])
api_router.include_router(watchlist.router, prefix="/watchlist", tags=["想看清单"])
api_router.include_router(fun.router, prefix="/fun", tags=["趣味功能"])
api_router.include_router(img.router, prefix="/img", tags=["图片代理"])
