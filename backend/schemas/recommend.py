"""
推荐与评分接口的请求 / 响应模型。

推荐结果统一包装成 RecommendItem：影片 + 理由 + 分数。
"理由"是这个项目推荐系统的良心 —— 黑盒推荐只说"猜你喜欢"，
我们把"因为你给《肖申克的救赎》打了 9 分，它的导演是弗兰克·德拉邦特"
这种可解释的因果摆到台面上。
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from backend.schemas.search import MovieHit


class RecommendItem(BaseModel):
    """一条推荐：影片本体 + 人类可读理由 + 推荐分。"""

    movie: MovieHit
    reason: str | None = Field(default=None, description="推荐理由；无明确口味依据时为 None")
    score: float | None = Field(default=None, description="推荐分（热门=贝叶斯WR，相似=相关度）")


class SimilarResponse(BaseModel):
    """相似影片：参考片 + 相似列表。"""

    base: MovieHit
    items: list[RecommendItem] = Field(default_factory=list)
    mode: str = Field(
        default="content",
        description="召回方式：content=文本相似，genre=同类型兜底，none=参考片不存在")
    note: str | None = None


class PopularResponse(BaseModel):
    """热门榜单。formula 把贝叶斯参数原样带回，前端可展示公式本身。"""

    items: list[RecommendItem] = Field(default_factory=list)
    formula: dict = Field(default_factory=dict,
                          description='{"m": 门槛票数, "c": 全局均分} —— WR=(v/(v+m))·R+(m/(v+m))·C')


class ForYouResponse(BaseModel):
    """个性化推荐。

    degraded=True 表示用户没有评分记录、已退化为热门榜 ——
    如实标注，不假装"懂你"。
    """

    items: list[RecommendItem] = Field(default_factory=list)
    based_on: list[dict] = Field(default_factory=list,
                                 description="本次推荐参考了你的哪些评分（movie_id/title/score）")
    degraded: bool = False
    profile: dict | None = Field(default=None, description="统计出的口味画像（类型/导演）")
    formula: dict | None = None


# ---------------- 评分 ----------------

class RatingRequest(BaseModel):
    """给电影打分。1~10 分，与 IMDb/TMDB 同量纲。"""

    movie_id: str = Field(..., min_length=1, max_length=64)
    score: float = Field(..., ge=0.5, le=10)


class RatingItem(BaseModel):
    """一条评分记录。"""

    movie_id: str
    movie_title: str | None = None
    score: float
    created_at: str | None = None
