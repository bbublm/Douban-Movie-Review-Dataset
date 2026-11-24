"""
检索服务 —— 拿构建好的 DSL 去 ES 跑，再把结果组装成响应模型。

这一层是「唯一碰 ES 的地方」。它不含检索逻辑（那些在 query_builder.py），
只做三件事：发请求、拆响应、把 ES 的字段名翻译回业务字段名。
"""
from __future__ import annotations

import time
from typing import Any

import re

from backend.schemas.search import (
    DecadeCoverage,
    Facet,
    FacetBucket,
    GenreSentiment,
    MovieHit,
    MovieSearchRequest,
    MovieSearchResponse,
    LibraryMatch,
    NowPlayingDetail,
    NowPlayingHit,
    NowPlayingResponse,
    RatingDivergencePoint,
    ReviewHit,
    ReviewSearchRequest,
    ReviewSearchResponse,
    SearchMeta,
    SuggestItem,
    TopRatedMovie,
    TrailerItem,
    TrailersResponse,
)
from backend.api.v1.img import rewrite_poster_url
from backend.services.query_builder import (
    MOVIE_FACETS,
    REVIEW_FACETS,
    build_movie_query,
    build_review_query,
    build_sort,
    build_suggest_query,
)
from common.es_client import get_es
from common.settings import settings


class SearchUnavailable(Exception):
    """ES 连不上或查询失败。API 层会把它翻译成 503。"""


# ============================================================
# ES 结果 → 业务模型
# ============================================================

def _facets_from_response(raw: dict, facets: list[tuple[str, str, str, int, str]],
                          req: Any) -> list[Facet]:
    """把 ES 聚合结果翻译成 Facet 列表，并标出哪些项已被选中。"""
    aggs = raw.get("aggregations") or {}
    out: list[Facet] = []

    for name, _field, label, _size, _kind in facets:
        wrapper = aggs.get(f"facet_{name}") or {}
        buckets = (wrapper.get("top") or {}).get("buckets") or []
        if not buckets:
            continue
        out.append(Facet(
            field=name,
            label=label,
            buckets=[
                FacetBucket(
                    key=str(b.get("key_as_string") or b.get("key")),
                    count=int(b.get("doc_count", 0)),
                    selected=_is_selected(name, b, req),
                )
                for b in buckets
                if int(b.get("doc_count", 0)) > 0
            ],
        ))
    return out


def _is_selected(facet: str, bucket: dict, req: Any) -> bool:
    """这个分面项是否正被用户选中（前端据此打勾）。"""
    key = str(bucket.get("key_as_string") or bucket.get("key"))
    if facet == "genres":
        return key in (getattr(req, "genres", None) or [])
    if facet == "countries":
        return key in (getattr(req, "countries", None) or [])
    if facet == "languages":
        return key in (getattr(req, "languages", None) or [])
    if facet == "sentiment":
        return key in (getattr(req, "sentiment", None) or [])
    if facet == "years":
        # 年份分面是单选语义：只有"起止年份等于这一年"才算选中
        lo, hi = getattr(req, "year_from", None), getattr(req, "year_to", None)
        return lo is not None and lo == hi and str(lo) == key
    if facet == "rating":
        return _rating_range_selected(key, req)
    if facet == "length":
        return _length_range_selected(key, req)
    if facet == "sources":
        return key in (getattr(req, "sources", None) or [])
    if facet == "dataset":
        return key in (getattr(req, "dataset", None) or [])
    return False


def _length_range_selected(key: str, req: Any) -> bool:
    """篇幅区间是否被选中 —— 与 _rating_range_selected 同构，区间名来自 LENGTH_RANGES。

    前端点「长评（500 词以上）」时传 min_words=500，这里换算回区间名打勾。
    两边区间表必须一致：query_builder.LENGTH_RANGES 与这里的 bounds。
    """
    lo, hi = getattr(req, "min_words", None), getattr(req, "max_words", None)
    if lo is None and hi is None:
        return False
    bounds = {
        "长评（500 词以上）": (500, None),
        "中评（200 ~ 500 词）": (200, 500),
        "短评（50 ~ 200 词）": (50, 200),
        "微评（50 词以内）": (None, 50),
    }
    want = bounds.get(key)
    if not want:
        return False
    return lo == want[0] and hi == want[1]


def _rating_range_selected(key: str, req: Any) -> bool:
    """评分区间是否被选中 —— 把用户传的 min/max 换算回区间名。"""
    lo, hi = getattr(req, "rating_min", None), getattr(req, "rating_max", None)
    if lo is None and hi is None:
        return False
    bounds = {
        "9 分以上": (9.0, None),
        "8 ~ 9 分": (8.0, 9.0),
        "7 ~ 8 分": (7.0, 8.0),
        "6 ~ 7 分": (6.0, 7.0),
        "6 分以下": (None, 6.0),
    }
    want = bounds.get(key)
    if not want:
        return False
    return lo == want[0] and hi == want[1]


def _to_movie_hit(hit: dict) -> MovieHit:
    src = hit.get("_source") or {}
    sources = src.get("sources") or []
    # tmdb_id 在 ES 里是数字，但响应模型统一用字符串 ——
    # 前端拿它拼 TMDB 链接（themoviedb.org/movie/<id>），字符串更顺手，
    # 而且不会出现"有时候是数字有时候是字符串"这种让前端崩溃的摇摆类型。
    tmdb = src.get("tmdb_id")
    return MovieHit(
        movie_id=src.get("movie_id") or hit.get("_id") or "",
        title=src.get("title"),
        title_zh=src.get("title_zh"),
        title_en=src.get("title_en"),
        year=src.get("release_year"),
        release_date=src.get("release_date"),
        release_year=src.get("release_year"),
        runtime=src.get("runtime"),
        rating=src.get("vote_average"),
        votes=src.get("vote_count"),
        popularity=src.get("popularity"),
        genres_zh=src.get("genres_zh") or [],
        director=src.get("director"),
        cast=src.get("cast") or [],
        overview=src.get("overview"),
        poster_url=rewrite_poster_url(src.get("poster_url")),
        countries=src.get("production_countries") or [],
        languages=src.get("spoken_languages") or [],
        imdb_id=src.get("imdb_id"),
        tmdb_id=str(tmdb) if tmdb is not None else None,
        douban_id=src.get("douban_id"),
        douban_rating=src.get("douban_rating"),
        douban_score=src.get("douban_score"),
        douban_votes=src.get("douban_votes"),
        douban_comments=src.get("douban_comments") or [],
        douban_short_comments=src.get("douban_short_comments") or [],
        douban_long_comments=src.get("douban_long_comments") or [],
        sources=sources,
        source_count=src.get("source_count") or len(sources),
        is_multi_source=bool(src.get("is_multi_source")),
        filming_locations=src.get("filming_locations") or [],
        score=hit.get("_score"),
        highlight=hit.get("highlight") or {},
    )


def _to_review_hit(hit: dict) -> ReviewHit:
    src = hit.get("_source") or {}
    return ReviewHit(
        review_id=src.get("review_id") or hit.get("_id") or "",
        movie_id=src.get("movie_id"),
        movie_title=src.get("movie_title"),
        sentiment=src.get("sentiment"),
        sentiment_score=src.get("sentiment_score"),
        word_count=src.get("word_count"),
        text=src.get("text"),
        dataset=src.get("dataset"),
        source=src.get("source"),
        score=hit.get("_score"),
        highlight=hit.get("highlight") or {},
    )


# ============================================================
# 检索入口
# ============================================================

async def search_movies(req: MovieSearchRequest) -> MovieSearchResponse:
    body = build_movie_query(req)
    sort_list, sort_used = build_sort(
        req.sort, req.order, has_query=bool(req.q and req.q.strip())
    )
    body["sort"] = sort_list

    try:
        es = get_es().options(request_timeout=15)
        raw = await es.search(
            index=settings.es_index_movies,
            query=body["query"],
            sort=body["sort"],
            from_=body["from"],
            size=body["size"],
            highlight=body["highlight"],
            track_total_hits=True,
            **({"post_filter": body["post_filter"]} if "post_filter" in body else {}),
            **({"aggs": body["aggs"]} if "aggs" in body else {}),
        )
    except Exception as exc:  # noqa: BLE001 - 统一转成领域异常，由 API 层决定响应码
        raise SearchUnavailable(f"{type(exc).__name__}: {exc}") from exc

    total = int(raw["hits"]["total"]["value"])
    size = req.size
    return MovieSearchResponse(
        query=req.q,
        meta=SearchMeta(
            total=total,
            page=req.page,
            size=size,
            pages=(total + size - 1) // size,
            took_ms=int(raw.get("took", 0)),
            applied=_applied_filters(req),
            sort_used=sort_used,
        ),
        hits=[_to_movie_hit(h) for h in raw["hits"]["hits"]],
        facets=_facets_from_response(raw, MOVIE_FACETS, req) if req.with_facets else [],
    )


async def search_reviews(req: ReviewSearchRequest) -> ReviewSearchResponse:
    body = build_review_query(req)
    try:
        es = get_es().options(request_timeout=15)
        raw = await es.search(
            index=settings.es_index_reviews,
            query=body["query"],
            sort=body["sort"],
            from_=body["from"],
            size=body["size"],
            highlight=body["highlight"],
            track_total_hits=True,
            **({"post_filter": body["post_filter"]} if "post_filter" in body else {}),
            **({"aggs": body["aggs"]} if "aggs" in body else {}),
        )
    except Exception as exc:  # noqa: BLE001
        raise SearchUnavailable(f"{type(exc).__name__}: {exc}") from exc

    total = int(raw["hits"]["total"]["value"])
    return ReviewSearchResponse(
        query=req.q,
        meta=SearchMeta(
            total=total,
            page=req.page,
            size=req.size,
            pages=(total + req.size - 1) // req.size,
            took_ms=int(raw.get("took", 0)),
            applied=req.model_dump(exclude_none=True, exclude={"page", "size"}),
            sort_used=req.sort if req.q else "length",
        ),
        hits=[_to_review_hit(h) for h in raw["hits"]["hits"]],
        facets=_facets_from_response(raw, REVIEW_FACETS, req) if req.with_facets else [],
    )


async def suggest_movies(q: str, size: int = 8) -> list[SuggestItem]:
    body = build_suggest_query(q, size)
    try:
        es = get_es().options(request_timeout=8)
        raw = await es.search(index=settings.es_index_movies, **body)
    except Exception as exc:  # noqa: BLE001
        raise SearchUnavailable(f"{type(exc).__name__}: {exc}") from exc

    items: list[SuggestItem] = []
    for hit in raw["hits"]["hits"]:
        src = hit.get("_source") or {}
        items.append(SuggestItem(
            movie_id=src.get("movie_id") or hit.get("_id") or "",
            title=src.get("title") or src.get("title_en") or "",
            year=src.get("release_year"),
            genres_zh=src.get("genres_zh") or [],
            rating=src.get("vote_average"),
            poster_url=rewrite_poster_url(src.get("poster_url")),
        ))
    return items


async def get_movie(movie_id: str) -> MovieHit | None:
    """按 movie_id 取单部电影。不存在返回 None（不是异常 —— 404 是正常业务结果）。"""
    try:
        es = get_es().options(request_timeout=8)
        raw = await es.get(index=settings.es_index_movies, id=movie_id)
    except Exception as exc:  # noqa: BLE001
        name = type(exc).__name__
        if "NotFound" in name or "404" in str(exc):
            return None
        raise SearchUnavailable(f"{name}: {exc}") from exc
    return _to_movie_hit({"_source": raw.get("_source") or {}, "_id": raw.get("_id")})


def _split_spaced(value: str | None) -> list[str]:
    """豆瓣热映榜把地区/导演/主演压成「空格或 / 分隔」字符串，拆成列表。

    地区是空格分隔（"德国 法国 美国"），主演是 " / " 分隔，
    导演通常是单个姓名（含中点 ·，不能切）。统一按 [空白/斜杠]+ 切，
    保留「·」这类姓名中点。空值 / 空串返回空列表，避免前端拿到 ['']。
    """
    if not value or not str(value).strip():
        return []
    return [v for v in re.split(r"[\s/]+", str(value).strip()) if v]


def _to_nowplaying_hit(hit: dict) -> NowPlayingHit:
    src = hit.get("_source") or {}
    return NowPlayingHit(
        douban_id=src.get("douban_id") or hit.get("_id") or "",
        title=src.get("title"),
        poster=rewrite_poster_url(src.get("poster")),
        douban_rating=src.get("douban_rating"),
        douban_votes=src.get("douban_votes"),
        release_year=src.get("release_year"),
        region=_split_spaced(src.get("region")),
        director=_split_spaced(src.get("director")),
        actors=_split_spaced(src.get("actors")),
        duration=src.get("duration"),
        collected_at=src.get("collected_at"),
        source=src.get("source"),
    )


async def get_nowplaying(size: int = 50) -> NowPlayingResponse:
    """拉取豆瓣「正在热映」榜单（douban_nowplaying 索引）。

    热映榜是独立实体（多数不在库内 266 部里），不参与 movies 检索，
    所以单独一个接口一次性返回全量，前端直接渲染卡片墙。
    """
    size = max(1, min(size, 100))
    try:
        es = get_es().options(request_timeout=10)
        raw = await es.search(
            index=settings.es_index_douban_nowplaying,
            query={"match_all": {}},
            sort=[{"douban_votes": {"order": "desc"}}],
            from_=0,
            size=size,
            track_total_hits=True,
        )
    except Exception as exc:  # noqa: BLE001
        raise SearchUnavailable(f"{type(exc).__name__}: {exc}") from exc

    hits = raw["hits"]["hits"]
    items = [_to_nowplaying_hit(h) for h in hits]
    latest = None
    if items:
        # 同一批采集，取最新一条的采集时间作为榜单时间
        latest = max((it.collected_at for it in items if it.collected_at), default=None)
    return NowPlayingResponse(count=len(items), collected_at=latest, items=items)


def _norm_title(value: str | None) -> str:
    """片名归一化：去空白、常见标点与书名号后小写。

    只用于「采集片 ↔ 库内片」的严格比对；不参与召回，召回仍走 ES 分词。
    归一化后完全相同才算匹配，避免《XX》误连到同名续集 / 相似片。
    """
    return re.sub(
        r"[\s:：·・\-—_,，.。!！?？'\"“”‘’()（）\[\]【】《》]",
        "", str(value or ""),
    ).lower()


async def _library_match_by_title(title: str | None) -> LibraryMatch | None:
    """采集片是否在库内片库有同名影片：先 ES 召回，再 Python 严格比对。

    这是详情页的增强信息，失败/超时不影响档案本身，故异常一律吞掉返回 None。
    """
    key = _norm_title(title)
    if not key:
        return None
    try:
        es = get_es().options(request_timeout=6)
        raw = await es.search(
            index=settings.es_index_movies,
            query={"multi_match": {
                "query": str(title), "type": "best_fields",
                "fields": ["title^4", "title_zh^4", "title_en^2", "original_title^2"],
            }},
            size=8,
            _source=["movie_id", "title", "title_zh", "title_en", "original_title",
                     "release_year", "vote_average", "poster_url"],
            track_total_hits=False,
        )
    except Exception:  # noqa: BLE001
        return None
    for h in raw.get("hits", {}).get("hits", []):
        src = h.get("_source") or {}
        fields = ("title", "title_zh", "title_en", "original_title")
        if not any(_norm_title(src.get(f)) == key for f in fields):
            continue
        return LibraryMatch(
            movie_id=src.get("movie_id") or h.get("_id") or "",
            title=src.get("title") or src.get("title_zh"),
            release_year=src.get("release_year"),
            rating=src.get("vote_average"),
            poster_url=rewrite_poster_url(src.get("poster_url")),
        )
    return None


async def get_nowplaying_detail(douban_id: str) -> NowPlayingDetail | None:
    """按 _id 读单条爬虫采集档案（站内详情页用）。

    与榜单接口同源：都是 douban_nowplaying 索引里已经落库的采集结果，
    不在 Web 请求里现爬源站；找不到返回 None，由 API 层转 404。
    """
    try:
        es = get_es().options(request_timeout=8)
        raw = await es.get(index=settings.es_index_douban_nowplaying, id=douban_id)
    except Exception as exc:  # noqa: BLE001
        if getattr(exc, "status_code", None) == 404:
            return None
        raise SearchUnavailable(f"{type(exc).__name__}: {exc}") from exc
    hit = {"_id": raw.get("_id"), "_source": raw.get("_source") or {}}
    detail = NowPlayingDetail(**_to_nowplaying_hit(hit).model_dump())
    detail.library_match = await _library_match_by_title(detail.title)
    return detail


def _applied_filters(req: MovieSearchRequest) -> dict:
    """回显实际生效的筛选条件（空值不回显，前端直接拿来渲染 chips）。"""
    data = req.model_dump(exclude_none=True, exclude={"page", "size"})
    return {k: v for k, v in data.items() if v not in (None, [], "")}


# ============================================================
# TMDB 官方预告片（阶段 1g · 视频数据）
# ============================================================

def _to_trailers(hit: dict) -> TrailersResponse:
    src = hit.get("_source") or {}
    trailers = [
        TrailerItem(
            key=t.get("key") or "",
            name=t.get("name"),
            type=t.get("type"),
            official=bool(t.get("official")),
            published_at=t.get("published_at"),
            url=t.get("url"),
        )
        for t in (src.get("trailers") or [])
    ]
    return TrailersResponse(
        tmdb_id=str(src.get("tmdb_id") or hit.get("_id") or ""),
        title=src.get("title"),
        title_zh=src.get("title_zh"),
        trailers=trailers,
        trailer_count=src.get("trailer_count") or len(trailers),
    )


async def get_trailers(tmdb_id: str) -> TrailersResponse:
    """按 tmdb_id 取官方预告片集合。不存在返回空集合（正常业务结果）。"""
    try:
        es = get_es().options(request_timeout=8)
        raw = await es.get(index=settings.es_index_tmdb_videos, id=str(tmdb_id))
    except Exception as exc:  # noqa: BLE001
        name = type(exc).__name__
        if "NotFound" in name or "404" in str(exc):
            return TrailersResponse(tmdb_id=str(tmdb_id), trailers=[])
        raise SearchUnavailable(f"{name}: {exc}") from exc
    return _to_trailers({"_source": raw.get("_source") or {}, "_id": raw.get("_id")})


# ============================================================
# 豆瓣 + 预告片 联合洞察聚合（阶段 1f / 1g）
# ============================================================

async def get_douban_insights() -> "DoubanInsightsResponse":
    """豆瓣短评（文本数据）+ TMDB 预告片（视频数据）的联合洞察。

    数据量很小（库内 ~490 部、豆瓣短评 ~数百条），直接「拉全量 → Python 关联计算」，
    比写一堆 ES 复合聚合更直观、也更不容易出错；代价是单次查询多拉几条，
    对这个量级完全可接受。

    返回：
        rating_divergence   TMDB vs 豆瓣 评分分歧（每部两者都有的电影一个点）
        sentiment_dist      豆瓣短评情感分布
        top_rated           豆瓣高分 Top（按评分、票数门槛过滤）
        trailer_coverage    预告片覆盖率（总库 / 按年代）
        genre_sentiment     类型 × 情感
    """
    from backend.schemas.search import DoubanInsightsResponse  # noqa: PLC0415

    try:
        es = get_es().options(request_timeout=20)

        # 1) 全部电影：id / 片名 / TMDB 评分 / 豆瓣评分 / 类型 / 年份 / tmdb_id
        movies_raw = await es.search(
            index=settings.es_index_movies,
            query={"match_all": {}},
            _source=[
                "movie_id", "title", "title_zh", "vote_average",
                "douban_rating", "douban_votes", "genres_zh",
                "release_year", "tmdb_id",
            ],
            size=2000,
            track_total_hits=True,
        )
        movies = [h["_source"] for h in movies_raw["hits"]["hits"]]

        # 2) 豆瓣短评：movie_id + sentiment（只拉这两列，省带宽）
        rev_raw = await es.search(
            index=settings.es_index_reviews,
            query={"term": {"source": "douban"}},
            _source=["movie_id", "sentiment"],
            size=10000,
            track_total_hits=True,
        )
        reviews = rev_raw["hits"]["hits"]

        # 3) 热映影片数
        np_count = await es.count(index=settings.es_index_douban_nowplaying)

        # 4) 含预告片的 tmdb_id 集合
        vid_raw = await es.search(
            index=settings.es_index_tmdb_videos,
            query={"match_all": {}},
            _source=["tmdb_id"],
            size=2000,
            track_total_hits=True,
        )
        trailer_tmdb_ids = {
            str(h["_source"].get("tmdb_id"))
            for h in vid_raw["hits"]["hits"] if h["_source"].get("tmdb_id")
        }
    except Exception as exc:  # noqa: BLE001
        raise SearchUnavailable(f"{type(exc).__name__}: {exc}") from exc

    # ---- 关联计算 ----
    movie_by_id: dict[str, dict] = {}
    for m in movies:
        mid = m.get("movie_id")
        if mid:
            movie_by_id[mid] = m

    # 评分分歧：两者都有评分
    divergence: list[RatingDivergencePoint] = []
    movies_with_douban = 0
    for m in movies:
        dr = m.get("douban_rating")
        va = m.get("vote_average")
        if dr is None or va is None:
            continue
        movies_with_douban += 1
        divergence.append(RatingDivergencePoint(
            movie_id=m.get("movie_id") or "",
            title=m.get("title_zh") or m.get("title"),
            tmdb_rating=round(float(va), 1),
            douban_rating=round(float(dr), 1),
            gap=round(float(dr) - float(va), 1),
            year=m.get("release_year"),
            genres=m.get("genres_zh") or [],
        ))
    # 按 |gap| 降序，分歧最大的排前面（最值得看的一张图）
    divergence.sort(key=lambda p: abs(p.gap), reverse=True)

    # 情感分布
    sentiment_dist: dict[str, int] = {}
    for h in reviews:
        s = (h["_source"].get("sentiment") or "unknown")
        sentiment_dist[s] = sentiment_dist.get(s, 0) + 1

    # 豆瓣高分 Top（票数门槛，避免冷门片虚高）
    top_rated: list[TopRatedMovie] = []
    for m in movies:
        dr = m.get("douban_rating")
        if dr is None or (m.get("douban_votes") or 0) < 200:
            continue
        top_rated.append(TopRatedMovie(
            movie_id=m.get("movie_id") or "",
            title=m.get("title_zh") or m.get("title"),
            douban_rating=round(float(dr), 1),
            douban_votes=int(m.get("douban_votes") or 0),
        ))
    top_rated.sort(key=lambda x: x.douban_rating, reverse=True)
    top_rated = top_rated[:12]

    # 预告片覆盖率（总库 + 按年代）
    total_movies = len(movies)
    with_trailers = 0
    decade: dict[str, DecadeCoverage] = {}
    for m in movies:
        tid = str(m.get("tmdb_id")) if m.get("tmdb_id") else None
        y = m.get("release_year")
        dec = f"{(y // 10) * 10}s" if y else "未知"
        bucket = decade.setdefault(dec, DecadeCoverage(decade=dec))
        bucket.total += 1
        if tid and tid in trailer_tmdb_ids:
            with_trailers += 1
            bucket.with_trailers += 1
    decade_list = sorted(decade.values(), key=lambda d: d.decade)
    coverage_pct = round(100.0 * with_trailers / total_movies, 1) if total_movies else 0.0
    trailer_coverage = {
        "total_movies": total_movies,
        "with_trailers": with_trailers,
        "coverage_pct": coverage_pct,
        "by_decade": [d.model_dump() for d in decade_list],
    }

    # 类型 × 情感（豆瓣短评按电影类型归集）
    genre_sent: dict[str, GenreSentiment] = {}
    for h in reviews:
        src = h["_source"]
        mid = src.get("movie_id")
        s = src.get("sentiment")
        if not mid or s not in ("positive", "negative", "neutral"):
            continue
        m = movie_by_id.get(mid)
        if not m:
            continue
        for g in (m.get("genres_zh") or []):
            gs = genre_sent.setdefault(g, GenreSentiment(genre=g))
            gs.total += 1
            if s == "positive":
                gs.positive += 1
            elif s == "negative":
                gs.negative += 1
            else:
                gs.neutral += 1
    genre_sentiment = sorted(
        (g for g in genre_sent.values() if g.total >= 5),
        key=lambda g: g.total, reverse=True,
    )[:10]

    return DoubanInsightsResponse(
        generated_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        movies_with_douban=movies_with_douban,
        reviews_douban=len(reviews),
        nowplaying_count=int(np_count.get("count", 0)),
        rating_divergence=divergence,
        sentiment_dist=sentiment_dist,
        sentiment_total=sum(sentiment_dist.values()),
        top_rated=top_rated,
        trailer_coverage=trailer_coverage,
        genre_sentiment=genre_sentiment,
    )
