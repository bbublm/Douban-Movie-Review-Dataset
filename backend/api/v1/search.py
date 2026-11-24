"""
阶段 3 · 检索接口。

| 接口 | 用途 |
|---|---|
| `POST /api/v1/search/movies` | 电影混合检索（全参数） |
| `GET  /api/v1/search/movies` | 同上，简化版 —— 方便浏览器/curl 直接试 |
| `GET  /api/v1/search/suggest` | 搜索框联想（边打字边出片名） |
| `GET  /api/v1/search/movies/{movie_id}` | 单部电影详情 |
| `POST /api/v1/search/reviews` | 影评检索（含情感分面） |
| `GET  /api/v1/search/reviews` | 同上，简化版 |

为什么每个检索都提供 POST 与 GET 两种？
    POST 能表达完整参数（数组、区间、多种排序），前端正式调用用它；
    GET 参数少但可以直接粘到浏览器地址栏里看结果 ——
    开发期调接口、答辩时现场演示，这一条能省掉一半功夫。
    Swagger UI 里两个都能点，POST 那个有完整的字段说明。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from backend.schemas.search import (
    MovieHit,
    MovieSearchRequest,
    MovieSearchResponse,
    ReviewHit,
    ReviewSearchRequest,
    ReviewSearchResponse,
    SuggestItem,
    TrailersResponse,
)
from backend.services.search_service import (
    SearchUnavailable,
    get_movie,
    get_trailers,
    search_movies,
    search_reviews,
    suggest_movies,
)

router = APIRouter()


def _split(value: str | None) -> list[str]:
    """把 "科幻,喜剧" 切成 ['科幻','喜剧']。空串得到空列表。"""
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]


def _guard(exc: SearchUnavailable) -> HTTPException:
    """ES 不可用时统一返回 503，并给出可操作的排查提示。"""
    return HTTPException(
        status_code=503,
        detail={
            "message": "检索服务暂时不可用（Elasticsearch 未连接或查询失败）",
            "hint": "先执行 docker-compose up -d，再跑 python -m index.run_index build 灌数据",
            "error": str(exc)[:300],
        },
    )


# ============================================================
# 电影检索
# ============================================================

@router.post("/movies", response_model=MovieSearchResponse, summary="电影混合检索（全参数）")
async def post_search_movies(req: MovieSearchRequest) -> MovieSearchResponse:
    """主检索接口。什么都不传就是「浏览全部」，按热度排序。

    - **q**：检索词，走 IK 中文分词
    - **分面**：genres / countries / languages / 年份 / 评分 / 片长 区间
    - **genre_op=and**：要求同时具备所有类型（阶段 6 类型混搭器要用）
    - **排序**：relevance（有 q 时）/ rating / votes / year / title / popularity
    """
    try:
        return await search_movies(req)
    except SearchUnavailable as exc:
        raise _guard(exc) from exc


@router.get("/movies", response_model=MovieSearchResponse, summary="电影检索（简化版，浏览器可直接试）")
async def get_search_movies(
    q: str | None = Query(default=None, description="检索词"),
    mode: str = Query(default="best", pattern="^(best|phrase|cross)$",
                      description="best=召回优先；phrase=短语；cross=跨字段"),
    genres: str | None = Query(default=None, description="类型，逗号分隔，如 科幻,喜剧"),
    genre_op: str = Query(default="or", pattern="^(and|or)$"),
    countries: str | None = Query(default=None, description="出品国，逗号分隔"),
    languages: str | None = Query(default=None, description="对白语言，逗号分隔"),
    sources: str | None = Query(default=None, description="数据来源，逗号分隔，如 tmdb,wikidata"),
    year_from: int | None = None,
    year_to: int | None = None,
    rating_min: float | None = Query(default=None, ge=0, le=10),
    rating_max: float | None = Query(default=None, ge=0, le=10),
    runtime_min: int | None = Query(default=None, ge=0, description="最短片长（分钟）"),
    runtime_max: int | None = Query(default=None, ge=0, description="最长片长（分钟）"),
    require_poster: bool = False,
    require_overview: bool = False,
    multi_source_only: bool = False,
    sort: str = Query(default="relevance",
                      pattern="^(relevance|rating|votes|year|title|popularity)$"),
    order: str = Query(default="desc", pattern="^(asc|desc)$"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=20, ge=1, le=50),
    with_facets: bool = Query(default=True, description="关掉可省掉一次聚合开销"),
) -> MovieSearchResponse:
    """简化版检索，参数与 POST 版一一对应，只是数组类参数改成逗号分隔字符串。

    ★ GET 的参数必须和请求模型逐个对齐。
        漏掉某个参数时 FastAPI **不会报错**，而是用一个默认值顶上 ——
        前端传了 `with_facets=false` 却依然拿到分面，这种"传了没反应"
        的问题最难排查。所以这里宁可写全，也别偷懒只挑常用的。
    """
    req = MovieSearchRequest(
        q=q, mode=mode, genres=_split(genres), genre_op=genre_op,  # type: ignore[arg-type]
        countries=_split(countries), languages=_split(languages),
        sources=_split(sources),
        year_from=year_from, year_to=year_to,
        rating_min=rating_min, rating_max=rating_max,
        runtime_min=runtime_min, runtime_max=runtime_max,
        require_poster=require_poster, require_overview=require_overview,
        multi_source_only=multi_source_only,
        sort=sort, order=order, page=page, size=size,  # type: ignore[arg-type]
        with_facets=with_facets,
    )
    try:
        return await search_movies(req)
    except SearchUnavailable as exc:
        raise _guard(exc) from exc


@router.get("/movies/{movie_id}", response_model=MovieHit, summary="按 movie_id 取单部电影")
async def get_movie_detail(movie_id: str) -> MovieHit:
    """movie_id 就是融合层生成的业务主键（优先 imdb_id，其次 tmdb_id，最后片名哈希）。"""
    try:
        movie = await get_movie(movie_id)
    except SearchUnavailable as exc:
        raise _guard(exc) from exc
    if movie is None:
        raise HTTPException(status_code=404, detail=f"找不到 movie_id={movie_id} 的电影")
    return movie


# ============================================================
# TMDB 官方预告片（阶段 1g · 视频数据）
# ============================================================

@router.get("/trailers/{tmdb_id}", response_model=TrailersResponse, summary="按 tmdb_id 取官方预告片")
async def trailers(tmdb_id: str) -> TrailersResponse:
    """取某部电影的 TMDB 官方 YouTube 预告片集合（Trailer / Teaser）。

    tmdb_id 来自电影详情的 `tmdb_id` 字段。没有预告片返回空集合（不是 404）。
    数据来自 tmdb_videos 索引，由 `python -m ingest.run_collect tmdb-videos` 采集。
    """
    try:
        return await get_trailers(tmdb_id)
    except SearchUnavailable as exc:
        raise _guard(exc) from exc


# ============================================================
# 搜索联想
# ============================================================

@router.get("/suggest", response_model=list[SuggestItem], summary="搜索框片名联想")
async def suggest(
    q: str = Query(..., min_length=1, description="已输入的部分片名"),
    size: int = Query(default=8, ge=1, le=20),
) -> list[SuggestItem]:
    """用 phrase_prefix 做前缀联想：输「流浪地」也能出《流浪地球》。

    只匹配片名字段，不搜简介 —— 联想屏很小，出剧情简介的命中项没意义。
    """
    try:
        return await suggest_movies(q, size)
    except SearchUnavailable as exc:
        raise _guard(exc) from exc


# ============================================================
# 影评检索
# ============================================================

@router.post("/reviews", response_model=ReviewSearchResponse, summary="影评检索（含情感分面）")
async def post_search_reviews(req: ReviewSearchRequest) -> ReviewSearchResponse:
    """影评检索。正文走英文分析器（词干还原），可按情感、篇幅、所属电影筛选。"""
    try:
        return await search_reviews(req)
    except SearchUnavailable as exc:
        raise _guard(exc) from exc


@router.get("/reviews", response_model=ReviewSearchResponse, summary="影评检索（简化版）")
async def get_search_reviews(
    q: str | None = None,
    sentiment: str | None = Query(default=None, description="positive,negative,neutral（逗号分隔）"),
    dataset: str | None = Query(default=None, description="影评数据集，逗号分隔，如 imdb"),
    source: str | None = Query(default=None, description="影评采集源，逗号分隔，如 douban"),
    lang: str | None = Query(default=None, description="影评语言：zh / en"),
    movie_id: str | None = None,
    min_words: int | None = None,
    max_words: int | None = None,
    sort: str = Query(default="relevance", pattern="^(relevance|length|sentiment)$"),
    order: str = Query(default="desc", pattern="^(asc|desc)$"),
    page: int = Query(default=1, ge=1),
    size: int = Query(default=10, ge=1, le=50),
    with_facets: bool = Query(default=True, description="是否返回情感分面统计"),
) -> ReviewSearchResponse:
    req = ReviewSearchRequest(
        q=q, sentiment=_split(sentiment), dataset=_split(dataset),
        source=_split(source), lang=lang,
        movie_id=movie_id,
        min_words=min_words, max_words=max_words,
        sort=sort, order=order, page=page, size=size,  # type: ignore[arg-type]
        with_facets=with_facets,
    )
    try:
        return await search_reviews(req)
    except SearchUnavailable as exc:
        raise _guard(exc) from exc
