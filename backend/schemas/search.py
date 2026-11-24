"""
检索接口的请求 / 响应模型。

★ 为什么分面筛选要用 post_filter 而不是直接塞进 query？
    这是筛选功能最容易做错的一处。如果筛选条件进了 query，
    聚合（分面计数）就只会统计"筛选之后"的文档 ——
    用户点掉「科幻」之后，类型分面里就再也看不到「喜剧」了，
    筛选器会把自己锁死在一条路上（facet self-locking）。

    正确做法：query 只管关键词，筛选条件放进 post_filter。
    这样聚合算的是「关键词命中的全集」，每个分面项都还能看到自己剩多少可选。
    电商（淘宝 / Amazon）的筛选栏都是这个行为。

★ 更进一步：分面之间互相排除。
    单纯 post_filter 仍有一个问题：选了「科幻」之后，类型分面里其它类型
    的计数会被「科幻」这个条件压掉。真正的做法是——
    **每个分面统计时，排除它自己的那个筛选条件**（drill-down / facet exclusion），
    只应用其它分面的条件。这样类型分面永远显示"如果我把类型换成 X 会有多少部"。
    本项目的 `build_facet_aggs()` 就是这么干的。
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

# ---------------- 排序与匹配模式 ----------------

SortKey = Literal["relevance", "rating", "votes", "year", "title", "popularity"]
MatchMode = Literal["best", "phrase", "cross"]
Order = Literal["asc", "desc"]


# ============================================================
# 请求
# ============================================================

class MovieSearchRequest(BaseModel):
    """电影检索请求。字段全部可空 —— 什么都不传就是「浏览全部」。"""

    # ---- 关键词 ----
    q: str | None = Field(default=None, description="检索词，支持中文（IK 分词）")
    mode: MatchMode = Field(default="best", description=(
        "best=任意字段命中即算（默认，召回高）；"
        "phrase=短语匹配，用于搜索框联想；"
        "cross=跨字段匹配，适合「导演+类型」这类组合长词"))

    # ---- 分面筛选 ----
    genres: list[str] = Field(default_factory=list, description="中文类型，如 ['科幻','喜剧']")
    genre_op: Literal["and", "or"] = Field(default="or",
                                           description="and=必须同时具备所有类型（类型混搭器要用）")
    countries: list[str] = Field(default_factory=list, description="出品国/地区")
    languages: list[str] = Field(default_factory=list, description="对白语言")
    # 数据来源分面（sources）对应的筛选：tmdb / imdb / wikidata / wikipedia。
    # 没有这个字段时，前端分面栏里的「数据来源」只能看不能点 —— 半残功能。
    sources: list[str] = Field(default_factory=list,
                               description="数据来源，如 ['tmdb','wikidata']")

    # ---- 区间筛选 ----
    year_from: int | None = None
    year_to: int | None = None
    rating_min: float | None = Field(default=None, ge=0, le=10)
    rating_max: float | None = Field(default=None, ge=0, le=10)
    runtime_min: int | None = None
    runtime_max: int | None = None

    # ---- 数据质量筛选（阶段 5 大屏要用）----
    require_poster: bool = False
    require_overview: bool = False
    multi_source_only: bool = Field(default=False, description="只要被多个数据源覆盖的（融合成功的）")

    # ---- 排序与分页 ----
    sort: SortKey = Field(default="relevance", description="无关键词时 relevance 自动退化为按热度")
    order: Order = "desc"
    page: int = Field(default=1, ge=1)
    size: int = Field(default=20, ge=1, le=50)

    # ---- 输出控制 ----
    with_facets: bool = Field(default=True, description="是否返回分面统计")


class ReviewSearchRequest(BaseModel):
    """影评检索请求。"""

    q: str | None = None
    sentiment: list[str] = Field(default_factory=list, description="positive / negative / neutral")
    # 影评「数据集」分面对应的筛选（imdb / rotten …），与 sources 同理：
    # 分面可见就可点，不做只能看不能点的半残功能。
    dataset: list[str] = Field(default_factory=list, description="影评数据集来源")
    # 阶段 1f：按「采集源」筛选（如 douban），与 dataset 正交：
    # douban 短评 source=douban 且 dataset=douban，但其它源可能只标 dataset。
    source: list[str] = Field(default_factory=list, description="影评采集源（如 douban）")
    lang: str | None = Field(default=None, description="影评语言：zh / en（索引 lang 字段，大屏中文影评流用）")
    movie_id: str | None = Field(default=None, description="只看某一部电影的影评")
    min_words: int | None = None
    max_words: int | None = None
    sort: Literal["relevance", "length", "sentiment"] = "relevance"
    order: Order = "desc"
    page: int = Field(default=1, ge=1)
    size: int = Field(default=10, ge=1, le=50)
    with_facets: bool = True


# ============================================================
# 响应
# ============================================================

class FacetBucket(BaseModel):
    """分面的一项：取值 + 命中数量。selected 表示它是否已被用户选中。"""
    key: str
    count: int
    selected: bool = False


class Facet(BaseModel):
    """一个分面维度。前端据此渲染筛选栏。"""
    field: str
    label: str
    buckets: list[FacetBucket]


class MovieHit(BaseModel):
    """一条电影结果。**所有字段都可能为空** —— 融合数据是稀疏的。"""
    movie_id: str
    title: str | None = None
    title_zh: str | None = None
    title_en: str | None = None
    year: int | None = None
    release_date: str | None = None
    release_year: int | None = Field(
        default=None, description="与 year 同值的兼容别名（老前端按 release_year 取年份）")
    runtime: int | None = None
    rating: float | None = None
    votes: int | None = None
    popularity: float | None = None
    genres_zh: list[str] = Field(default_factory=list)
    director: str | None = None
    cast: list[str] = Field(default_factory=list)
    overview: str | None = None
    poster_url: str | None = None
    countries: list[str] = Field(default_factory=list)
    languages: list[str] = Field(default_factory=list)
    imdb_id: str | None = None
    tmdb_id: str | None = None
    # ---- 豆瓣评分（阶段 1f，解除「禁采集豆瓣」红线后新增）----
    # 与 vote_average（TMDB/IMDb 聚合分）并列，让用户看到「国内口碑」一票。
    douban_id: str | None = None
    douban_rating: float | None = None
    douban_score: float | None = None
    douban_votes: int | None = None
    douban_comments: list[str] = Field(default_factory=list)
    douban_short_comments: list[str] = Field(default_factory=list)
    douban_long_comments: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    source_count: int = 0
    is_multi_source: bool = False
    filming_locations: list[dict] = Field(default_factory=list)
    # ---- 检索相关 ----
    score: float | None = None
    highlight: dict[str, list[str]] = Field(default_factory=dict)


class SearchMeta(BaseModel):
    """这次检索的元信息，前端展示「共 N 部 / 第 X 页 / 耗时」用。"""
    total: int = 0
    page: int = 1
    size: int = 20
    pages: int = 0
    took_ms: int = 0
    # 把实际生效的条件回显给前端，便于调试与展示"已选条件" chips
    applied: dict = Field(default_factory=dict)
    # 无关键词却按相关性排序时，会退化成按热度 —— 这里如实告知前端
    sort_used: str = "relevance"


class MovieSearchResponse(BaseModel):
    query: str | None = None
    meta: SearchMeta
    hits: list[MovieHit] = Field(default_factory=list)
    facets: list[Facet] = Field(default_factory=list)
    note: str | None = Field(default=None, description="结果为空或发生退化时的解释（如混搭器没有同时命中的影片）")


class ReviewHit(BaseModel):
    review_id: str
    movie_id: str | None = None
    movie_title: str | None = None
    sentiment: str | None = None
    sentiment_score: float | None = None
    word_count: int | None = None
    text: str | None = None
    dataset: str | None = None
    source: str | None = Field(
        default=None, description="语料来源（douban / tmdb / kaggle），前端用来标出处")
    score: float | None = None
    highlight: dict[str, list[str]] = Field(default_factory=dict)


class ReviewSearchResponse(BaseModel):
    query: str | None = None
    meta: SearchMeta
    hits: list[ReviewHit] = Field(default_factory=list)
    facets: list[Facet] = Field(default_factory=list)


class SuggestItem(BaseModel):
    """搜索框联想项。"""
    movie_id: str
    title: str
    year: int | None = None
    genres_zh: list[str] = Field(default_factory=list)
    rating: float | None = None
    poster_url: str | None = None


# ============================================================
# 豆瓣「正在热映」榜（阶段 1f · 独立实体，走 douban_nowplaying 索引）
# ============================================================

class NowPlayingHit(BaseModel):
    """一条院线热映影片。多数不在库内 266 部里，没有 tmdb/imdb 锚点，单独展示。"""
    douban_id: str
    title: str | None = None
    # 豆瓣海报原图 URL，序列化层已改写为 /api/v1/img 代理路径（防裂图）
    poster: str | None = None
    douban_rating: float | None = None
    douban_votes: int | None = None
    release_year: int | None = None
    # 豆瓣热映榜把地区/导演/主演压成空格分隔字符串，这里拆成列表方便前端渲染
    region: list[str] = Field(default_factory=list)
    director: list[str] = Field(default_factory=list)
    actors: list[str] = Field(default_factory=list)
    duration: str | None = None
    collected_at: str | None = None
    source: str | None = None


class NowPlayingResponse(BaseModel):
    """热映榜响应：带总数与时间戳，前端一行就能拿到全量。"""
    count: int = 0
    collected_at: str | None = None
    items: list[NowPlayingHit] = Field(default_factory=list)


class LibraryMatch(BaseModel):
    """院线采集片在库内片库里的同名匹配（ES 真检索，不做模糊猜测）。"""
    movie_id: str
    title: str | None = None
    release_year: int | None = None
    rating: float | None = None
    poster_url: str | None = None


class NowPlayingDetail(NowPlayingHit):
    """单条院线热映影片的站内采集档案。

    点击首页卡片进入站内详情页，直接读爬虫落库的 ES 文档，
    不再把访客送到源站；同时附上库内片库的真实关联。
    """
    library_match: LibraryMatch | None = None


# ============================================================
# TMDB 官方预告片（阶段 1g · 视频数据，走 tmdb_videos 索引）
# ============================================================

class TrailerItem(BaseModel):
    """一条官方预告片（YouTube）。"""
    key: str
    name: str | None = None
    type: str | None = None          # Trailer / Teaser
    official: bool = False
    published_at: str | None = None
    url: str | None = None           # https://www.youtube.com/embed/<key>


class TrailersResponse(BaseModel):
    """按 tmdb_id 取到的预告片集合。"""
    tmdb_id: str
    title: str | None = None
    title_zh: str | None = None
    trailers: list[TrailerItem] = Field(default_factory=list)
    trailer_count: int = 0


# ============================================================
# 豆瓣 + 预告片 聚合分析（阶段 1f/1g 联合洞察，走 /douban/insights）
# ============================================================

class RatingDivergencePoint(BaseModel):
    """评分分歧：一部电影在 TMDB（西方口碑）与豆瓣（国内口碑）的评分差。"""
    movie_id: str
    title: str | None = None
    tmdb_rating: float
    douban_rating: float
    gap: float                       # douban - tmdb；正=国内更爱，负=国外更爱
    year: int | None = None
    genres: list[str] = Field(default_factory=list)


class GenreSentiment(BaseModel):
    """某个类型下的豆瓣影评情感分布。"""
    genre: str
    positive: int = 0
    neutral: int = 0
    negative: int = 0
    total: int = 0


class TopRatedMovie(BaseModel):
    """豆瓣高分影片。"""
    movie_id: str
    title: str | None = None
    douban_rating: float
    douban_votes: int = 0


class DecadeCoverage(BaseModel):
    """某个年代的电影数与含预告片数。"""
    decade: str
    total: int = 0
    with_trailers: int = 0


class DoubanInsightsResponse(BaseModel):
    """豆瓣 + 预告片 联合洞察聚合结果（前端 Flourish 风格分析页直接渲染）。"""
    generated_at: str | None = None
    movies_with_douban: int = 0       # 库内带了豆瓣评分的电影数
    reviews_douban: int = 0           # 豆瓣短评总数
    nowplaying_count: int = 0          # 当前热映影片数
    rating_divergence: list[RatingDivergencePoint] = Field(default_factory=list)
    sentiment_dist: dict[str, int] = Field(default_factory=dict)
    sentiment_total: int = 0
    top_rated: list[TopRatedMovie] = Field(default_factory=list)
    trailer_coverage: dict = Field(default_factory=dict)
    genre_sentiment: list[GenreSentiment] = Field(default_factory=list)
