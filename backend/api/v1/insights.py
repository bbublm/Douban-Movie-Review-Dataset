"""
阶段 4 · 洞察接口。

| 接口 | 用途 |
|---|---|
| `POST /api/v1/insights/sentiment` | 任意文本情感打分（返回每个命中词，可解释） |
| `GET  /api/v1/insights/sentiment` | 全局情感分布 + 各类型均分（大屏用） |
| `GET  /api/v1/insights/topics` | 主题词榜：观众在夸什么 / 骂什么 |
| `GET  /api/v1/insights/lexicon` | 学出来的情感词典本身（答辩演示用） |
| `GET  /api/v1/insights/trends` | 年代趋势：每十年影片数与均分（折线图） |
| `GET  /api/v1/insights/matrix` | 类型×年代矩阵：大屏动态图表（竞赛/排名/流向）数据源 |
| `GET  /api/v1/insights/box-office` | 票房分析：TOP 影片画廊 + 年度票房趋势 |
| `GET  /api/v1/insights/movies/{id}` | 单片画像：关键词 + 类型口碑参考 |

★ 这些接口的数据从哪来？
    情感分布走 Elasticsearch 聚合（实时、真数据）；
    主题榜 / 词典 / 单片关键词走**分析层产物文件**
    （data_lake/analysis/*.json），带 mtime 缓存，不会每个请求都重读一遍。
    产物缺失时返回 503 并告诉用户该跑哪条命令 —— 不返回空数组假装正常。
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from backend.api.v1.errors import es_unavailable as _guard
from backend.api.v1.img import rewrite_poster_url
from backend.schemas.insights import (
    GenreRating,
    GenreRef,
    BoxOfficeItem,
    BoxOfficeResponse,
    BoxOfficeYearBucket,
    CorrelationPoint,
    CorrelationResponse,
    FlowHeat,
    FlowLayersResponse,
    FlowLink,
    FlowNode,
    GenreProfile,
    GraphLink,
    GraphNode,
    HallPoster,
    HallPostersResponse,
    KnowledgeGraphResponse,
    KeywordItem,
    MatrixCell,
    MatrixResponse,
    MatrixRow,
    MovieInsight,
    MovieVoices,
    PolarizingItem,
    PolarizingResponse,
    Quote,
    RegionItem,
    RegionsResponse,
    RegressionInfo,
    RoiBox,
    ScoreRequest,
    ScoreResponse,
    SentimentBucket,
    SentimentStats,
    StoryCard,
    StoryFact,
    StoryResponse,
    TopicItem,
    TopicsResponse,
    TrendBucket,
    TrendsResponse,
    VoiceItem,
    VoiceStats,
    WordHit,
)
from backend.services.insight_stats import (
    lift as calc_lift,
    linear_regression,
    pearson,
    quantiles,
)
from backend.services.query_builder import (
    build_box_office_years,
    build_correlations_sample,
    build_decade_aggs,
    build_flow_layers,
    build_genre_decade_matrix,
    build_hall_posters,
    build_knowledge_graph,
    build_polarizing,
    build_regions,
)
from backend.services.search_service import SearchUnavailable, get_movie
from common.es_client import get_es
from common.settings import settings
from common.ttl_cache import cache

router = APIRouter()


def _artifact(name: str) -> Path:
    return settings.lake("analysis", name)


# ============================================================
# 产物文件缓存
# ============================================================

# 产物是"跑一次分析就固定"的文件，没必要每个请求都解析一遍 JSON。
# 缓存键 = (路径, mtime, size)：文件被重新生成后 mtime 变化，缓存自动失效。
_CACHE: dict[str, tuple[tuple, Any]] = {}


def _load_artifact(name: str, what: str) -> Any:
    path = _artifact(name)
    if not path.exists():
        raise HTTPException(
            status_code=503,
            detail={
                "message": f"分析产物 {name} 不存在，{what}需要先跑分析层",
                "hint": "python -m analysis.run_analysis lexicon && "
                        "python -m analysis.run_analysis topics",
            },
        )
    try:
        st = path.stat()
        key = (str(path), st.st_mtime_ns, st.st_size)
    except OSError as exc:
        raise HTTPException(status_code=503, detail=f"读取 {name} 失败：{exc}") from exc

    hit = _CACHE.get(name)
    if hit and hit[0] == key:
        return hit[1]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=503, detail=f"解析 {name} 失败：{exc}") from exc
    _CACHE[name] = (key, data)
    return data


def _load_lexicon():
    """读情感词典，返回 analysis.lexicon.Lexicon 对象。"""
    from analysis.lexicon import Lexicon

    data = _load_artifact("lexicon.json", "情感打分")
    return Lexicon(
        scores={str(k): float(v) for k, v in (data.get("scores") or {}).items()},
        lang=str(data.get("lang") or "en"),
        meta=data.get("meta") or {},
    )


# ============================================================
# 情感打分
# ============================================================


@router.post("/sentiment", response_model=ScoreResponse, summary="任意文本情感打分")
async def score_text(req: ScoreRequest) -> ScoreResponse:
    """给一段文本打情感分，并返回**每个命中的词**。

    这是阶段 4 的核心卖点：黑盒模型只能告诉你"这是负面"，
    我们能把"因为出现了 waste(-2.45)、poorly(-1.90) 所以判负面"摊开给人看。
    前端把 hits 渲染成高亮词，答辩时现场粘一条影评就能演示。
    """
    from analysis.sentiment import label_of, score_text as _score

    lex = _load_lexicon()
    lang = None if req.lang == "auto" else req.lang
    res = _score(req.text, lex, lang=lang)

    # ★ 只回报"有分量"的命中词。
    #   词典是从语料里归纳的，the / of / and 这类功能词也会入典（分数≈0）。
    #   全量返回的话，一句 "a total waste of time" 会报 19 个命中词，
    #   其中 12 个是虚词 —— 解释性反而变差。
    #   阈值 0.05 与 sentiment.py 的 neutral 判定阈值保持一致：
    #   一个词连 neutral 都判不出来，就没必要拿出来解释。
    hits = [
        WordHit(word=w, weight=weight, lexicon_score=round(lex.scores.get(w, 0.0), 4))
        for w, weight in res.hits
        if abs(weight) >= 0.05
    ]
    note = None
    if not hits:
        note = "文本里没有命中词典中有分量的情感词，分数接近 0 属正常结果"
    return ScoreResponse(
        score=res.score,
        label=label_of(res.score),
        lang=req.lang,
        hits=hits,
        matched_words=len(hits),
        note=note,
    )


@router.get("/sentiment", response_model=SentimentStats, summary="全局情感分布与类型口碑")
async def sentiment_stats() -> SentimentStats:
    """影评情感分布（ES 聚合）+ 各类型均分（电影侧）。

    ★ 缓存：这是大屏的心脏接口，两个 ES 聚合（reviews 情感分面 +
      movies 类型口碑）不随用户变，进 TTL 缓存（默认 5 分钟）。
      单片画像（/movies/{id}）内部也调它，顺带受益。
    """
    async def _produce() -> SentimentStats:
        try:
            es = get_es().options(request_timeout=15)
            # 影评情感分面：reviews 索引上的 terms 聚合。
            # ★ track_total_hits=True 不能省 —— ES 7+ 默认只精确统计到 1 万条，
            #   影评有 4.99 万条，不写这个 hits.total 会停在 10000，
            #   正面率直接算成 250%（25078/10000）。阶段 3 在影评检索上踩过一次。
            rev = await es.search(
                index=settings.es_index_reviews,
                size=0,
                track_total_hits=True,
                aggs={"sentiment": {"terms": {"field": "sentiment", "size": 10,
                                              "missing": "unknown"}}},
            )
            # 类型口碑：movies 索引上按类型分组求均分
            mov = await es.search(
                index=settings.es_index_movies,
                size=0,
                aggs={"genres": {
                    "terms": {"field": "genres_zh", "size": 12, "min_doc_count": 5},
                    "aggs": {
                        "avg_rating": {"avg": {"field": "vote_average"}},
                        "avg_votes": {"avg": {"field": "vote_count"}},
                    },
                }},
            )
        except Exception as exc:  # noqa: BLE001
            raise _guard(SearchUnavailable(f"{type(exc).__name__}: {exc}")) from exc

        rev_total = int((rev["hits"]["total"] or {}).get("value") or 0)
        buckets = [SentimentBucket(key=str(b["key"]), count=int(b["doc_count"]))
                   for b in rev["aggregations"]["sentiment"]["buckets"]]
        pos = sum(b.count for b in buckets if b.key == "positive")

        by_genre = []
        for b in mov.get("aggregations", {}).get("genres", {}).get("buckets", []):
            by_genre.append(GenreRating(
                genre=str(b["key"]),
                movies=int(b["doc_count"]),
                avg_rating=(round(b["avg_rating"]["value"], 2)
                            if b.get("avg_rating", {}).get("value") is not None else None),
                avg_votes=(int(b["avg_votes"]["value"])
                           if b.get("avg_votes", {}).get("value") is not None else None),
            ))
        by_genre.sort(key=lambda g: -(g.avg_rating or 0))

        return SentimentStats(
            total=rev_total,
            buckets=buckets,
            positive_ratio=round(pos / rev_total, 4) if rev_total else 0.0,
            by_genre=by_genre,
        )

    try:
        return await cache.get_or_set("insights:sentiment", _produce)
    except SearchUnavailable as exc:
        raise _guard(exc) from exc


@router.get("/trends", response_model=TrendsResponse, summary="年代趋势（影片数与均分）")
async def trends() -> TrendsResponse:
    """按十年一桶统计影片数与平均评分，替代原系统的「数据趋势分析」图位。

    聚合构造在 query_builder.build_decade_aggs()（纯函数，可离线自检），
    这里只负责执行 + 把 ES 的浮点桶 key 转成 int 年代。
    ★ 缓存：histogram 聚合扫全库，结果不随用户变，进 TTL 缓存。
    """
    async def _produce() -> TrendsResponse:
        try:
            es = get_es().options(request_timeout=15)
            resp = await es.search(
                index=settings.es_index_movies,
                size=0,
                track_total_hits=True,
                aggs=build_decade_aggs(),
            )
        except Exception as exc:  # noqa: BLE001
            raise _guard(SearchUnavailable(f"{type(exc).__name__}: {exc}")) from exc

        total = int((resp["hits"]["total"] or {}).get("value") or 0)
        buckets = [
            TrendBucket(
                decade=int(b["key"]),
                movies=int(b["doc_count"]),
                avg_rating=(round(b["avg_rating"]["value"], 2)
                            if b.get("avg_rating", {}).get("value") is not None else None),
            )
            for b in resp.get("aggregations", {}).get("by_decade", {}).get("buckets", [])
        ]
        with_year = sum(b.movies for b in buckets)
        note = None
        if total and with_year < total:
            note = f"{total - with_year} 部影片缺年份字段，未计入趋势"
        return TrendsResponse(total_movies=total, with_year=with_year,
                              buckets=buckets, note=note)

    try:
        return await cache.get_or_set("insights:trends", _produce)
    except SearchUnavailable as exc:
        raise _guard(exc) from exc


@router.get("/matrix", response_model=MatrixResponse, summary="类型×年代矩阵（动态图表数据源）")
async def genre_decade_matrix() -> MatrixResponse:
    """类型 × 年代二维矩阵，供大屏的 Flourish 式动态图表（条形竞赛 / 排名变化 / 桑基流向）。

    聚合构造在 query_builder.build_genre_decade_matrix()（纯函数，可离线自检），
    这里只负责执行 + 把嵌套桶摊平成行。
    ★ 缓存：与 trends 同性质的聚合，进 TTL 缓存（默认 5 分钟）。
    """
    async def _produce() -> MatrixResponse:
        try:
            es = get_es().options(request_timeout=15)
            resp = await es.search(
                index=settings.es_index_movies,
                size=0,
                track_total_hits=True,
                aggs=build_genre_decade_matrix(),
            )
        except Exception as exc:  # noqa: BLE001
            raise _guard(SearchUnavailable(f"{type(exc).__name__}: {exc}")) from exc

        rows: list[MatrixRow] = []
        decades: set[int] = set()
        for b in resp.get("aggregations", {}).get("by_genre", {}).get("buckets", []):
            cells: list[MatrixCell] = []
            for d in b.get("by_decade", {}).get("buckets", []):
                decade = int(d["key"])
                decades.add(decade)
                cells.append(MatrixCell(
                    decade=decade,
                    movies=int(d["doc_count"]),
                    avg_rating=(round(d["avg_rating"]["value"], 2)
                                if d.get("avg_rating", {}).get("value") is not None else None),
                ))
            rows.append(MatrixRow(genre=str(b["key"]), total=int(b["doc_count"]), cells=cells))
        # 按总片数倒序：竞赛图里强者在前，弱类型自然沉底
        rows.sort(key=lambda r: -r.total)
        return MatrixResponse(decades=sorted(decades), rows=rows)

    try:
        return await cache.get_or_set("insights:matrix", _produce)
    except SearchUnavailable as exc:
        raise _guard(exc) from exc


# ============================================================
# 票房分析（2026-10-22 新增展厅，替代原「类型竞赛」）
# ============================================================


@router.get("/box-office", response_model=BoxOfficeResponse, summary="票房分析（画廊相框 + 年度趋势）")
async def box_office(
    top: int = Query(default=24, ge=6, le=60, description="画廊相框取票房前多少部"),
) -> BoxOfficeResponse:
    """票房分析展厅数据源：TOP 影片画廊（相框）+ 年度票房趋势（右翼图）。

    数据口径：仅统计 TMDB 给出 revenue 的影片（当前库约 242 部）。
    roi = revenue / budget —— 缺预算的老片留 None，不编数。
    ★ 缓存：与 matrix 同性质的 ES 聚合，进 TTL 缓存（默认 5 分钟）。
    """
    async def _produce() -> BoxOfficeResponse:
        es = get_es().options(request_timeout=15)
        # 1) 票房 TOP N：画廊相框内容
        try:
            top_resp = await es.search(
                index=settings.es_index_movies,
                size=top,
                track_total_hits=True,
                query={"bool": {"filter": [{"exists": {"field": "revenue"}}]}},
                sort=[{"revenue": "desc"}],
                _source=[
                    "title", "title_zh", "title_en", "release_year",
                    "poster_url", "revenue", "budget", "vote_average", "genres_zh",
                ],
            )
        except Exception as exc:  # noqa: BLE001
            raise _guard(SearchUnavailable(f"{type(exc).__name__}: {exc}")) from exc

        gallery: list[BoxOfficeItem] = []
        for hit in top_resp.get("hits", {}).get("hits", []):
            s = hit["_source"]
            revenue = int(s.get("revenue") or 0)
            budget = int(s["budget"]) if s.get("budget") else None
            roi = round(revenue / budget, 2) if budget else None
            gallery.append(BoxOfficeItem(
                movie_id=str(hit["_id"]),
                title=str(s.get("title_zh") or s.get("title") or ""),
                title_en=s.get("title_en"),
                year=s.get("release_year"),
                # 走站内图片代理：否则画廊 24 张相框直连 TMDB 图床，
                # 网络一抖整页 ERR_CONNECTION_RESET、控制台一片红
                poster_url=rewrite_poster_url(s.get("poster_url")),
                revenue=revenue,
                budget=budget,
                roi=roi,
                vote_average=s.get("vote_average"),
                genres=list(s.get("genres_zh") or []),
            ))

        # 2) 年度票房趋势 + 总览（聚合构造在 query_builder，纯函数可离线自检）
        try:
            agg_resp = await es.search(
                index=settings.es_index_movies,
                **build_box_office_years(),
            )
        except Exception as exc:  # noqa: BLE001
            raise _guard(SearchUnavailable(f"{type(exc).__name__}: {exc}")) from exc

        aggs = agg_resp.get("aggregations", {})
        years: list[BoxOfficeYearBucket] = []
        for b in aggs.get("by_year", {}).get("buckets", []):
            key = b.get("key")
            if key is None or key == "":  # 缺年份的影片进 null 键桶，趋势图不画
                continue
            years.append(BoxOfficeYearBucket(
                year=int(key),
                revenue=int(b.get("rev", {}).get("value") or 0),
                movies=int(b.get("doc_count") or 0),
            ))
        years.sort(key=lambda y: y.year)

        total_movies = int(
            agg_resp.get("hits", {}).get("total", {}).get("value")
            or top_resp.get("hits", {}).get("total", {}).get("value")
            or 0
        )
        total_revenue = int(aggs.get("total_rev", {}).get("value") or 0)
        top_year = max(years, key=lambda y: y.revenue).year if years else None

        # 桶合计 vs 全局合计的差额 = 缺年份影片的票房，如实写进 note
        bucketed = sum(y.revenue for y in years)
        note = None
        if total_revenue and bucketed < total_revenue:
            no_year = total_revenue - bucketed
            note = (f"有 {no_year / 1e8:.2f} 亿美元票房来自缺年份字段的影片，"
                    f"未计入年度趋势图")

        return BoxOfficeResponse(
            total_movies=total_movies,
            total_revenue=total_revenue,
            top_year=top_year,
            gallery=gallery,
            years=years,
            note=note,
        )

    try:
        # key 里带上 top：不同 top 参数不能共用同一份缓存（旧实现串数据）
        return await cache.get_or_set(f"insights:box-office:{top}", _produce)
    except SearchUnavailable as exc:
        raise _guard(exc) from exc


# ============================================================
# 主题 / 词典
# ============================================================


@router.get("/topics", response_model=TopicsResponse, summary="主题词榜")
async def topics(
    top: int = Query(default=20, ge=1, le=100, description="返回前多少个词"),
) -> TopicsResponse:
    """全局主题词榜：按"收缩后的对数提升度 × 证据量"排序。

    排序键的用意见 analysis/topics.py 的说明 —— 单纯按 lift 排，
    榜首会被只出现几十次的角色名霸占。
    """
    data = _load_artifact("topics.json", "主题统计")
    keywords = [
        TopicItem(
            word=str(d["word"]), df=int(d.get("df", 0)),
            df_positive=int(d.get("df_positive", 0)),
            df_negative=int(d.get("df_negative", 0)),
            lift=float(d.get("lift", 1.0)), side=str(d.get("side", "neutral")),
            weight=float(d.get("weight", 0.0)),
        )
        for d in (data.get("keywords") or [])[:top]
    ]
    return TopicsResponse(
        docs=int(data.get("docs", 0)),
        positive_docs=int(data.get("positive_docs", 0)),
        negative_docs=int(data.get("negative_docs", 0)),
        keywords=keywords,
        positive_vocabulary=list(data.get("positive_vocabulary") or []),
        negative_vocabulary=list(data.get("negative_vocabulary") or []),
    )


@router.get("/lexicon", summary="学出来的情感词典")
async def lexicon(
    top: int = Query(default=30, ge=1, le=200, description="正/负各取多少个词"),
) -> dict:
    """返回词典本身：最正面 / 最负面的各 top 个词 + 归纳时的统计信息。

    答辩时直接打开这个接口的返回，就能讲清"这部词典是从哪来的、
    学到了什么、有多少词"。
    """
    lex = _load_lexicon()
    return {
        "meta": lex.meta,
        "size": len(lex),
        "top_positive": [{"word": w, "score": s} for w, s in lex.top(top, positive=True)],
        "top_negative": [{"word": w, "score": s} for w, s in lex.top(top, positive=False)],
    }


@router.get("/movies/{movie_id}", response_model=MovieInsight, summary="单片画像")
async def movie_insight(movie_id: str) -> MovieInsight:
    """单片画像：电影自身信息 + 从它文本里提的关键词。"""
    try:
        movie = await get_movie(movie_id)
    except SearchUnavailable as exc:
        raise _guard(exc) from exc
    if movie is None:
        raise HTTPException(status_code=404, detail=f"找不到 movie_id={movie_id} 的电影")

    data = _load_artifact("movie_keywords.json", "单片画像")
    raw_kw = (data.get("movies") or {}).get(movie_id) or []
    keywords = [
        KeywordItem(word=str(d["word"]), tf=int(d.get("tf", 0)),
                    df=int(d.get("df", 0)), score=float(d.get("tfidf", 0.0)))
        for d in raw_kw
    ]

    # 口碑参考：该片所属类型的全局均分。一部片常有多个类型，
    # 只取匹配到的第一个做参考，字段名也写明是"参考"而不是该片的口碑。
    hint = None
    genre_ref = None
    if movie.genres_zh:
        try:
            stats = await sentiment_stats()
        except HTTPException:
            stats = None
        for g in (stats.by_genre if stats else []):
            if g.genre in movie.genres_zh and g.avg_rating is not None:
                hint = f"「{g.genre}」类影片全局均分 {g.avg_rating}（{g.movies} 部）"
                genre_ref = GenreRef(
                    genre=g.genre, avg_rating=g.avg_rating, movies=g.movies)
                break

    return MovieInsight(
        movie_id=movie.movie_id,
        title=movie.title,
        title_zh=movie.title_zh,
        year=movie.year,
        genres_zh=movie.genres_zh,
        director=movie.director,
        rating=movie.rating,
        votes=movie.votes,
        sources=movie.sources,
        keywords=keywords,
        sentiment_hint=hint,
        genre_ref=genre_ref,
    )


# ============================================================
# 单片口碑短评（详情页「观众怎么说」）
# ============================================================

VOICE_LIMIT = 240          # 单条短评上屏字数上限
VOICE_MIN_CHARS = 12       # 洗完后短于这个长度不构成一条观点
PEER_POOL = 60             # 同类型兜底时最多看多少部片的短评

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def _cjk_ratio(text: str) -> float:
    """中文占比。中文站优先上中文短评，英文长评排后面（不是删掉）。"""
    if not text:
        return 0.0
    return len(_CJK_RE.findall(text)) / len(text)


def _clean_voice(text: str | None) -> str | None:
    """短评上屏前的清洗：去 markdown 标记、链接、推广尾巴，压掉多余空白。"""
    if not text:
        return None
    t = _URL.sub(" ", text)
    t = _MD.sub("", t)
    t = _SPAM.sub("", t)
    t = _WS.sub(" ", t).strip(" .,;:!—-·\t")
    if len(t) < VOICE_MIN_CHARS:
        return None
    return t[:VOICE_LIMIT]


def _voice_stats(resp: dict) -> VoiceStats:
    """从 ES 响应里取情感构成与均分。"""
    aggs = resp.get("aggregations") or {}
    buckets = {
        str(b.get("key")): int(b.get("doc_count") or 0)
        for b in ((aggs.get("sentiment") or {}).get("buckets") or [])
    }
    avg = (aggs.get("rating") or {}).get("value")
    return VoiceStats(
        total=int((resp.get("hits") or {}).get("total", {}).get("value") or 0),
        positive=buckets.get("positive", 0),
        neutral=buckets.get("neutral", 0),
        negative=buckets.get("negative", 0),
        avg_rating=round(float(avg), 2) if avg is not None else None,
    )


async def _fetch_voices(
    es, movie_ids: list[str], size: int, diversify: bool = False
) -> tuple[VoiceStats, list[VoiceItem]]:
    """按影片 id 取真实短评。

    sort=word_count desc：先拿写得长的（信息量大、不像"好看""难看"），
    diversify=True 时按影片去重 —— 同类型兜底不能让一部片的短评占满整屏。
    """
    if not movie_ids:
        return VoiceStats(), []
    query = ({"terms": {"movie_id": movie_ids}} if len(movie_ids) > 1
             else {"term": {"movie_id": movie_ids[0]}})
    resp = await es.search(
        index=settings.es_index_reviews,
        size=max(size * 6, 36),
        query=query,
        sort=[{"word_count": {"order": "desc"}}],
        aggs={
            "sentiment": {"terms": {"field": "sentiment", "size": 3}},
            "rating": {"avg": {"field": "rating"}},
        },
        track_total_hits=True,
        _source=["review_id", "movie_id", "movie_title", "sentiment",
                 "sentiment_score", "source", "rating", "word_count", "text",
                 "review_time", "douban_comment_time", "douban_sort"],
    )
    stats = _voice_stats(resp)

    # 候选池：先清洗，再按「中文语料优先 → 写得长优先」定序。
    # 为什么不按 ES 的顺序直接截前 N 条：按 word_count 排出来的头部
    # 常常是清一色长篇差评（或清一色好评），放到详情页像被带了节奏。
    pool: list[VoiceItem] = []
    per_movie: dict[str, int] = {}
    for h in (resp.get("hits") or {}).get("hits") or []:
        s = h.get("_source") or {}
        mid = s.get("movie_id")
        if diversify and per_movie.get(mid, 0) >= 2:
            continue
        text = _clean_voice(s.get("text"))
        if not text:
            continue
        if diversify:
            per_movie[mid] = per_movie.get(mid, 0) + 1
        pool.append(VoiceItem(
            review_id=str(s.get("review_id") or h.get("_id") or ""),
            text=text,
            sentiment=s.get("sentiment"),
            sentiment_score=s.get("sentiment_score"),
            source=s.get("source"),
            movie_id=mid,
            movie_title=s.get("movie_title"),
            rating=s.get("rating"),
            word_count=s.get("word_count"),
            review_time=s.get("review_time") or s.get("douban_comment_time"),
            douban_sort=s.get("douban_sort"),
        ))

    pool.sort(key=lambda v: (v.source != "douban",
                             -round(_cjk_ratio(v.text or ""), 2),
                             -(v.word_count or 0)))

    # 正 / 负 / 中性轮转取，保证一屏里既有夸的也有骂的 ——
    # 观众的真实分歧比"全是好评"更有信息量。
    buckets: dict[str, list[VoiceItem]] = {"positive": [], "negative": [], "neutral": []}
    leftovers: list[VoiceItem] = []
    for v in pool:
        (buckets[v.sentiment] if v.sentiment in buckets else leftovers).append(v)

    items: list[VoiceItem] = []
    while len(items) < size:
        picked = False
        for key in ("positive", "negative", "neutral"):
            if buckets[key] and len(items) < size:
                items.append(buckets[key].pop(0))
                picked = True
        if not picked:
            break
    if len(items) < size:
        items.extend(leftovers[: size - len(items)])
    return stats, items


async def _genre_weights() -> dict[str, float]:
    """类型的"稀有度"权重：越少见的类型权重越高（IDF 思路）。

    「剧情」这种大标签占了全库近一半，共享它说明不了任何相似性；
    「武侠」「历史」只有十来部，共享一个就非常说明问题。
    每次请求实时算一次 terms 聚合太浪费，结果进 TTL 缓存（类型分布几乎不变）。
    """
    async def _produce() -> dict[str, float]:
        resp = await get_es().options(request_timeout=10).search(
            index=settings.es_index_movies, size=0,
            aggs={"g": {"terms": {"field": "genres_zh", "size": 100}}},
        )
        buckets = {
            str(b["key"]): int(b["doc_count"])
            for b in (resp.get("aggregations", {}).get("g", {}) or {}).get("buckets", [])
        }
        if not buckets:
            return {}
        total = sum(buckets.values())
        return {k: total / max(v, 1) for k, v in buckets.items()}

    try:
        return await cache.get_or_set("insights:genre_weight", _produce, ttl=600)
    except Exception:  # noqa: BLE001 —— 权重算不出来就退回"共享即 1 分"
        return {}


async def _peer_movie_ids(es, movie) -> list[str]:
    """同类型的其它影片，按"共享类型的稀有度之和 + 热度"排序。

    为什么不能只按票数或只数共享类型个数：一部片的类型常是
    「剧情/动作/历史/武侠」，只按票数排会捞进《盗梦空间》《复仇者联盟》——
    它们也挂「剧情/动作」，但跟武侠片毫无关系。按稀有度加权后，
    共享「武侠」「历史」的《一代宗师》《卧虎藏龙》才会浮上来。
    """
    bool_query: dict = {"must_not": [{"term": {"movie_id": movie.movie_id}}]}
    if movie.genres_zh:
        bool_query["filter"] = [{"terms": {"genres_zh": list(movie.genres_zh)}}]
    resp = await es.search(
        index=settings.es_index_movies,
        size=200,
        query={"bool": bool_query},
        sort=[{"vote_count": {"order": "desc"}}],
        _source=["movie_id", "genres_zh", "vote_count"],
    )
    own = set(movie.genres_zh or [])
    weights = await _genre_weights()
    rare = max(weights.values()) if weights else 1.0
    cands: list[tuple[float, int, str]] = []
    for h in resp["hits"]["hits"]:
        s = h.get("_source") or {}
        mid = s.get("movie_id")
        if not mid:
            continue
        # 没进权重表说明全库都少见，按最稀有处理
        score = sum(weights.get(g, rare) for g in own & set(s.get("genres_zh") or []))
        cands.append((score, int(s.get("vote_count") or 0), mid))
    cands.sort(key=lambda c: (-c[0], -c[1]))
    return [c[2] for c in cands[:PEER_POOL]]


@router.get("/movies/{movie_id}/voices", response_model=MovieVoices,
            summary="单片观众短评（本片没有时退回同类型）")
async def movie_voices(
    movie_id: str,
    size: int = Query(default=8, ge=3, le=16, description="展示多少条短评"),
) -> MovieVoices:
    """这部片观众到底怎么说的。

    先找本片的真实短评（豆瓣 / TMDB / Kaggle 三个语料库都算）；
    本片确实一条都没有，就退回**同类型影片的真实短评**，
    并在 scope 里如实标成 peers —— 页面文案随之改成"同类型观众在聊什么"，
    不会把别的片的评价冒充成本片口碑。
    """
    try:
        movie = await get_movie(movie_id)
    except SearchUnavailable as exc:
        raise _guard(exc) from exc
    if movie is None:
        raise HTTPException(status_code=404, detail=f"找不到 movie_id={movie_id} 的电影")

    es = get_es().options(request_timeout=20)
    try:
        stats, items = await _fetch_voices(es, [movie_id], size)
        scope = "own"
        if not items:
            # 同类型兜底分两档：先试「类型高度重合」的少数几部（邻居更像），
            # 它们没人写短评再放开到更大的同类型池子。
            peer_ids = await _peer_movie_ids(es, movie)
            batches = [peer_ids[:12], peer_ids]
            if len(batches[0]) == len(batches[1]):
                batches = batches[:1]
            for batch in batches:
                if not batch:
                    continue
                stats, items = await _fetch_voices(es, batch, size, diversify=True)
                if items:
                    break
            scope = "peers" if items else "none"
    except SearchUnavailable as exc:
        raise _guard(exc) from exc
    except Exception as exc:  # noqa: BLE001
        raise _guard(SearchUnavailable(f"{type(exc).__name__}: {exc}")) from exc

    # 不进程级缓存：单条 term 查询本身只要几毫秒，
    # 而按 movie_id 建 key 会迅速挤掉首页大屏那几个昂贵的聚合缓存。
    return MovieVoices(
        movie_id=movie_id,
        scope=scope,
        genres_zh=list(movie.genres_zh or []),
        stats=stats,
        items=items,
    )


# ============================================================
# 口碑分化 / 地区画像 / 馆长洞察（2026-11-01 新增展厅分析）
# ============================================================

# 引文清洗：影评原文常带 markdown  emphasis / 链接推广，直接上大屏很脏。
_MD = re.compile(r"[*_>#`~]+")
_URL = re.compile(r"https?://\S+", re.I)
_SPAM = re.compile(r"check out my (full )?review|read my (full )?review|full review @", re.I)
_WS = re.compile(r"\s+")


def _clean_quote(text: str | None) -> str | None:
    """把一条影评原文洗成可上大屏的引文；太短则放弃。"""
    if not text:
        return None
    t = _MD.sub("", text)
    t = _URL.sub("", t)                 # 链接删掉（留着是一串乱码域名）
    t = _WS.sub(" ", t).strip(" .,;:!—-\t")
    if len(t) < 20:                      # 洗完后太短，不构成引文
        return None
    return t[:220]


def _pick_quote(hits: list[dict]) -> Quote | None:
    """top_hits 给了 3 条候选，挑第一条"干净"的（非推广文、清洗后够长）。"""
    for h in hits:
        s = h.get("_source") or {}
        if _SPAM.search(s.get("text") or ""):
            continue
        t = _clean_quote(s.get("text"))
        if t:
            return Quote(text=t, rating=s.get("rating"))
    return None


async def _movie_titles(ids: list[str]) -> dict[str, dict]:
    """按 movie_id 批量回 movies 索引取中英文名（分化榜的 id 是 IMDb tt 号）。"""
    if not ids:
        return {}
    try:
        es = get_es().options(request_timeout=15)
        resp = await es.search(
            index=settings.es_index_movies,
            size=len(ids),
            query={"terms": {"movie_id": ids}},
            _source=["movie_id", "title", "title_zh", "title_en", "release_year",
                     "director", "poster_url", "vote_average"],
        )
    except Exception:  # noqa: BLE001 —— 取名失败不致命，退回用 movie_id 显示
        return {}
    out: dict[str, dict] = {}
    for h in resp.get("hits", {}).get("hits", []):
        s = h.get("_source") or {}
        if s.get("movie_id"):
            out[s["movie_id"]] = s
    return out


@router.get("/polarizing", response_model=PolarizingResponse, summary="口碑分化榜（评分标准差 + 真实引文）")
async def polarizing() -> PolarizingResponse:
    """观众内部的分歧：同一部片，有人打满分有人打最低分。

    按评分标准差排序取前 10；每部附"评分最高的真实影评"（好评引文）与
    "评分最低的真实影评"（差评引文）——引文来自本片真实语料，非模板。
    ★ 缓存：扫全量关联影评的聚合，进 TTL 缓存（默认 5 分钟）。
    """
    async def _produce() -> PolarizingResponse:
        es = get_es().options(request_timeout=20)
        try:
            resp = await es.search(
                index=settings.es_index_reviews, **build_polarizing())
        except Exception as exc:  # noqa: BLE001
            raise _guard(SearchUnavailable(f"{type(exc).__name__}: {exc}")) from exc

        cand: list[dict] = []
        for b in resp.get("aggregations", {}).get("by_movie", {}).get("buckets", []):
            st = b.get("stats") or {}
            sd = st.get("std_deviation")
            cnt = int(st.get("count") or 0)
            if not sd or cnt < 8:
                continue
            pos_hits = (b.get("pos", {}).get("hit", {}).get("hits", {}).get("hits")) or []
            neg_hits = (b.get("neg", {}).get("hit", {}).get("hits", {}).get("hits")) or []
            cand.append({
                "movie_id": str(b["key"]), "review_count": cnt,
                "avg_rating": st.get("avg"), "std_dev": sd,
                "pos": _pick_quote(pos_hits), "neg": _pick_quote(neg_hits),
            })
        cand.sort(key=lambda c: -(c["std_dev"] or 0))

        total_qualified = len(cand)
        cand = cand[:10]
        titles = await _movie_titles([c["movie_id"] for c in cand])
        items = []
        for c in cand:
            t = titles.get(c["movie_id"]) or {}
            items.append(PolarizingItem(
                movie_id=c["movie_id"],
                title=str(t.get("title_zh") or t.get("title") or c["movie_id"]),
                title_en=t.get("title_en"),
                year=t.get("release_year"),
                director=t.get("director"),
                poster_url=rewrite_poster_url(t.get("poster_url")),
                vote_average=t.get("vote_average"),
                review_count=c["review_count"],
                avg_rating=(round(c["avg_rating"], 2)
                            if c["avg_rating"] is not None else None),
                std_dev=(round(c["std_dev"], 2)
                         if c["std_dev"] is not None else None),
                pos_quote=c["pos"], neg_quote=c["neg"],
            ))
        return PolarizingResponse(total_qualified=total_qualified, items=items)

    try:
        return await cache.get_or_set("insights:polarizing", _produce)
    except SearchUnavailable as exc:
        raise _guard(exc) from exc


@router.get("/regions", response_model=RegionsResponse, summary="地区画像（主出品国产量与口碑）")
async def regions() -> RegionsResponse:
    """各主出品国的影片数与均分对照（产量王 ≠ 口碑王的数据源）。

    ★ 缓存：全库 terms 聚合，进 TTL 缓存。
    """
    async def _produce() -> RegionsResponse:
        es = get_es().options(request_timeout=15)
        try:
            resp = await es.search(
                index=settings.es_index_movies, **build_regions())
        except Exception as exc:  # noqa: BLE001
            raise _guard(SearchUnavailable(f"{type(exc).__name__}: {exc}")) from exc

        items = [
            RegionItem(
                country=str(b["key"]),
                movies=int(b["doc_count"]),
                avg_rating=(round(b["avg_rating"]["value"], 2)
                            if b.get("avg_rating", {}).get("value") is not None else None),
                avg_votes=(int(b["avg_votes"]["value"])
                           if b.get("avg_votes", {}).get("value") is not None else None),
            )
            for b in resp.get("aggregations", {}).get("by_country", {}).get("buckets", [])
        ]
        items.sort(key=lambda i: -i.movies)
        return RegionsResponse(items=items)

    try:
        return await cache.get_or_set("insights:regions", _produce)
    except SearchUnavailable as exc:
        raise _guard(exc) from exc


@router.get("/story", response_model=StoryResponse, summary="馆长洞察卡（大厅结论卡叠）")
async def story() -> StoryResponse:
    """大厅入口的三张结论卡：每卡一个分析发现，数据全部由各分析接口实时算出。

    设计成"容错组合"：某一路分析挂了只跳过那张卡，不让整叠卡消失。
    ★ 缓存：依赖的 polarizing/regions/sentiment 都是缓存的，这里再包一层短缓存。
    """
    async def _produce() -> StoryResponse:
        cards: list[StoryCard] = []

        try:
            pol = await polarizing()
            if pol.items:
                top = pol.items[0]
                cards.append(StoryCard(
                    kind="polarizing", kicker="口碑分化",
                    question="观众吵得最凶的一部片",
                    answer="同一部片，有人打满分，有人打最低分",
                    facts=[
                        StoryFact(k="影片", v=top.title),
                        StoryFact(k="评分波动", v=f"{top.std_dev:.2f}", big=True),
                        StoryFact(k="样本评价", v=f"{top.review_count} 条"),
                    ],
                    room="diverge",
                ))
        except HTTPException:
            pass

        try:
            reg = await regions()
            rated = [r for r in reg.items if r.avg_rating is not None]
            # 口碑王要有像样样本（>=8 部），否则 4 部小样本的 9.2 分没有说服力
            rated_sig = [r for r in rated if r.movies >= 8] or rated
            if reg.items and rated_sig:
                by_count = max(reg.items, key=lambda r: r.movies)
                by_rating = max(rated_sig, key=lambda r: r.avg_rating or 0)
                cards.append(StoryCard(
                    kind="regions", kicker="地区画像",
                    question="产量王 ≠ 口碑王",
                    answer="片子最多的国家，均分并不是最高",
                    facts=[
                        StoryFact(k="产量王", v=f"{by_count.country} · {by_count.movies} 部"),
                        StoryFact(k="口碑王", v=f"{by_rating.country} · {by_rating.avg_rating:.1f} 分",
                                  big=True),
                        StoryFact(k=f"{by_count.country}均分",
                                  v=f"{by_count.avg_rating:.2f} 分"),
                    ],
                    room="flow",
                ))
        except HTTPException:
            pass

        try:
            stats = await sentiment_stats()
            topics_data = _load_artifact("topics.json", "主题统计")
            pos_vocab = list(topics_data.get("positive_vocabulary") or [])
            neg_vocab = list(topics_data.get("negative_vocabulary") or [])
            cards.append(StoryCard(
                kind="sentiment", kicker="好评风向",
                question="观众最常说的好评词",
                answer="好话和坏话，观众都讲得很直白",
                facts=[
                    StoryFact(k="正面率", v=f"{stats.positive_ratio * 100:.0f}%", big=True),
                    StoryFact(k="最热好评词", v=pos_vocab[0] if pos_vocab else "—"),
                    StoryFact(k="最热差评词", v=neg_vocab[0] if neg_vocab else "—"),
                ],
                room="galaxy",
            ))
        except HTTPException:
            pass

        return StoryResponse(cards=cards)

    try:
        return await cache.get_or_set("insights:story", _produce)
    except SearchUnavailable as exc:
        raise _guard(exc) from exc


# ============================================================
# 深度分析（2026-11-04）：走廊片单 / 知识图谱 / 相关性 / 三层流向
# ------------------------------------------------------------
# 用户要求「数据要是真的分析得出来，而不是把现成的数据直接放上去」。
# 这四个接口里没有一张写死的表：
#   · hall-posters     每类型用 filter + top_hits 真选出代表片，并算高出类型均分多少
#   · knowledge-graph  terms→terms 共现 + adjacency_matrix 交集，再算 lift 过滤噪声
#   · correlations     取回样本后现算 Pearson / 最小二乘 R² / ROI 四分位
#   · flows            类型→年代→口碑档三层桶，第三级是 range 聚合不是平均值贴图
# 聚合体在 query_builder.py（可离线自检），统计量在 insight_stats.py（纯函数）。
# ============================================================

_TIER_NAMES = {
    "under6": "6 分以下", "d6_7": "6–7 分", "d7_8": "7–8 分", "over8": "8 分以上",
}
_CORR_VARS = [
    ("budget", "预算"), ("revenue", "票房"), ("vote_average", "评分"),
    ("vote_count", "评价数"), ("runtime", "片长"),
]


def _num(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _list(value) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, (list, tuple)):
        return [str(v) for v in value if v]
    return []


def _title(src: dict) -> str:
    return str(src.get("title_zh") or src.get("title") or src.get("title_en") or "—")


def _pos(value) -> float | None:
    """预算/票房/片长里 0 代表「没采到」，必须当缺失而不是真的 0。"""
    f = _num(value)
    return f if f is not None and f > 0 else None


@router.get("/hall-posters", response_model=HallPostersResponse,
            summary="走廊悬挂片单（按类型真算出的代表影片）")
async def hall_posters() -> HallPostersResponse:
    """每个类型挑「票数达标的口碑代表」+「有票房的票房代表」，去重后给走廊挂。

    poster_url 走 rewrite_poster_url，前端拿到就是 /api/v1/img 代理路径。
    """
    async def _produce() -> HallPostersResponse:
        es = get_es().options(request_timeout=15)
        try:
            resp = await es.search(
                index=settings.es_index_movies, **build_hall_posters())
        except Exception as exc:  # noqa: BLE001
            raise _guard(SearchUnavailable(f"{type(exc).__name__}: {exc}")) from exc

        total = int(resp.get("hits", {}).get("total", {}).get("value") or 0)
        items: list[HallPoster] = []
        seen: set[str] = set()
        for b in resp.get("aggregations", {}).get("by_genre", {}).get("buckets", []):
            genre = str(b["key"])
            gm = int(b["doc_count"])
            ga = b.get("avg_rating", {}).get("value")
            ga = round(float(ga), 2) if ga is not None else None
            for role, sub in (("口碑代表", "rated"), ("票房代表", "grossing")):
                hits = (b.get(sub, {}).get("best", {}).get("hits", {}).get("hits") or [])
                # 每类型取前两名：一部片常常同时是多个类型的冠军，去重后
                # 才凑得满走廊的 14 个挂位，且每张海报都是不同的真影片。
                for rank, hit in enumerate(hits[:2]):
                    src = hit.get("_source") or {}
                    mid = str(src.get("movie_id") or hit.get("_id") or "")
                    if not mid or mid in seen or len(items) >= 14:
                        continue
                    seen.add(mid)

                    rating = _num(src.get("vote_average"))
                    revenue = _int(src.get("revenue")) if _pos(src.get("revenue")) else None
                    budget = _int(src.get("budget")) if _pos(src.get("budget")) else None
                    roi = (round((revenue - budget) / budget, 3)
                           if revenue and budget else None)
                    gap = (round(rating - ga, 2)
                           if rating is not None and ga is not None else None)
                    place = f"TOP{rank + 1}"
                    if role == "口碑代表":
                        note = (f"{genre} {gm} 部里，票数达标的口碑 {place}"
                                + (f" · 高出类型均分 {gap:.2f} 分" if gap is not None else ""))
                    else:
                        note = (f"{genre} 票房 {place}"
                                + (f" · 全球 {revenue / 1e8:.1f} 亿美元" if revenue else ""))
                    items.append(HallPoster(
                        movie_id=mid,
                        title=_title(src),
                        title_en=src.get("title_en"),
                        year=_int(src.get("release_year")),
                        poster_url=rewrite_poster_url(src.get("poster_url")),
                        genres=_list(src.get("genres_zh"))[:3],
                        director=src.get("director"),
                        cast=_list(src.get("cast"))[:2],
                        vote_average=round(rating, 2) if rating is not None else None,
                        vote_count=_int(src.get("vote_count")),
                        revenue=revenue, budget=budget, roi=roi,
                        genre=genre, role=role, genre_movies=gm,
                        genre_avg_rating=ga, rating_gap=gap, note=note,
                    ))
        return HallPostersResponse(
            total_movies=total, items=items,
            note="片单由 ES 按类型聚合实时选出；每条结论都来自该类型的桶统计",
        )

    return await cache.get_or_set("insights:hall-posters", _produce)


@router.get("/knowledge-graph", response_model=KnowledgeGraphResponse,
            summary="影人 × 类型知识图谱（共现 + 提升度）")
async def knowledge_graph() -> KnowledgeGraphResponse:
    """先用一次聚合取回主类型名，再用 adjacency_matrix 求它们两两的交集。

    ★ 只按共现次数排会被「剧情」这种大桶刷屏，所以每条边都算
      lift = P(目标|源) / P(目标)；lift ≤ 1.02 的关系直接丢掉。
    """
    async def _produce() -> KnowledgeGraphResponse:
        es = get_es().options(request_timeout=15)
        try:
            first = await es.search(
                index=settings.es_index_movies, **build_knowledge_graph([]))
            names = [str(b["key"]) for b in first.get("aggregations", {})
                     .get("by_genre", {}).get("buckets", [])][:9]
            resp = await es.search(
                index=settings.es_index_movies, **build_knowledge_graph(names))
        except Exception as exc:  # noqa: BLE001
            raise _guard(SearchUnavailable(f"{type(exc).__name__}: {exc}")) from exc

        aggs = resp.get("aggregations", {})
        total = int(resp.get("hits", {}).get("total", {}).get("value") or 0) or 1
        gcounts: dict[str, int] = {}
        gavg: dict[str, float | None] = {}
        for b in aggs.get("by_genre", {}).get("buckets", []):
            name = str(b["key"])
            gcounts[name] = int(b["doc_count"])
            v = b.get("avg_rating", {}).get("value")
            gavg[name] = round(float(v), 2) if v is not None else None

        def counts(key: str) -> dict[str, int]:
            return {str(b["key"]): int(b["doc_count"])
                    for b in aggs.get(key, {}).get("buckets", [])}

        def avgs(key: str) -> dict[str, float | None]:
            out = {}
            for b in aggs.get(key, {}).get("buckets", []):
                v = b.get("avg_rating", {}).get("value")
                out[str(b["key"])] = round(float(v), 2) if v is not None else None
            return out

        dcounts, acounts = counts("by_director"), counts("by_actor")
        davg, aavg = avgs("by_director"), avgs("by_actor")

        edges: list[GraphLink] = []
        for b in aggs.get("by_genre", {}).get("buckets", []):
            genre = str(b["key"])
            base = gcounts.get(genre, 0)
            for kind, sub, pool, prefix in (
                ("genre-director", "directors", dcounts, "d"),
                ("genre-actor", "actors", acounts, "a"),
            ):
                for t in b.get(sub, {}).get("buckets", []):
                    name = str(t["key"])
                    co = int(t["doc_count"])
                    global_n = pool.get(name)          # 该导演/演员全库影片数
                    if not global_n or co < 2:
                        continue
                    lv = calc_lift(co, base, global_n, total)
                    if lv is None or lv <= 1.02:
                        continue
                    edges.append(GraphLink(
                        source=f"g:{genre}", target=f"{prefix}:{name}",
                        weight=co, lift=round(lv, 3), kind=kind,
                    ))
        for b in aggs.get("pairs", {}).get("buckets", []):
            key = str(b["key"])
            if "&" not in key:                        # 单个 filter 自身，不是边
                continue
            a, c = key.split("&", 1)
            co = int(b["doc_count"])
            lv = calc_lift(co, gcounts.get(a, 0), gcounts.get(c, 0), total)
            if lv is None or lv <= 1.02 or co < 3:
                continue
            edges.append(GraphLink(
                source=f"g:{a}", target=f"g:{c}",
                weight=co, lift=round(lv, 3), kind="genre-genre",
            ))
        edges.sort(key=lambda e: (-e.lift, -e.weight))
        edges = edges[:72]

        used = {e.source for e in edges} | {e.target for e in edges}
        nodes: list[GraphNode] = []
        for name, cnt in gcounts.items():
            nodes.append(GraphNode(id=f"g:{name}", name=name, kind="genre",
                                   value=cnt, avg_rating=gavg.get(name)))
        for prefix, pool, avg_map, kind in (
            ("d", dcounts, davg, "director"), ("a", acounts, aavg, "actor"),
        ):
            for name, cnt in pool.items():
                if f"{prefix}:{name}" in used:
                    nodes.append(GraphNode(id=f"{prefix}:{name}", name=name,
                                           kind=kind, value=cnt,
                                           avg_rating=avg_map.get(name)))
        strongest = edges[0] if edges else None
        notes = [f"{total} 部影片 · {len(gcounts)} 个类型 · {len(edges)} 条显著共现边（lift>1.02）"]
        if strongest:
            def label(nid: str) -> str:
                return next((n.name for n in nodes if n.id == nid), nid)
            notes.append(f"最强关系：{label(strongest.source)} × {label(strongest.target)}"
                         f" 共现 {strongest.weight} 次，是随机撞见的 {strongest.lift:.2f} 倍")
        return KnowledgeGraphResponse(
            nodes=nodes, links=edges, total_movies=total,
            pair_count=len(edges), strongest=strongest, notes=notes,
        )

    return await cache.get_or_set("insights:knowledge-graph", _produce)


@router.get("/correlations", response_model=CorrelationResponse,
            summary="真实统计量：相关矩阵 / 回归 / ROI 四分位")
async def correlations() -> CorrelationResponse:
    """从 ES 取回全库样本，在 Python 里现算 Pearson、最小二乘 R²、ROI 分布。

    0 值按缺失处理（预算/票房/片长的 0 是「没采到」不是真的零），
    相关系数用 pairwise complete，样本不足 3 或方差为 0 返回 null。
    """
    async def _produce() -> CorrelationResponse:
        es = get_es().options(request_timeout=15)
        try:
            resp = await es.search(
                index=settings.es_index_movies, **build_correlations_sample())
        except Exception as exc:  # noqa: BLE001
            raise _guard(SearchUnavailable(f"{type(exc).__name__}: {exc}")) from exc

        rows = [h.get("_source") or {} for h in resp.get("hits", {}).get("hits", [])]
        cols: dict[str, list[float | None]] = {k: [] for k, _ in _CORR_VARS}
        profile_rows: dict[str, list[dict]] = {}
        for s in rows:
            vals = {
                "budget": _pos(s.get("budget")),
                "revenue": _pos(s.get("revenue")),
                "vote_average": _num(s.get("vote_average")),
                "vote_count": _num(s.get("vote_count")),
                "runtime": _pos(s.get("runtime")),
            }
            if vals["vote_average"] is not None and vals["vote_average"] <= 0:
                vals["vote_average"] = None
            for k, v in vals.items():
                cols[k].append(v)
            # 类型画像按「主类型」归组（genres_zh[0] 与 build_regions 口径一致）
            g = (_list(s.get("genres_zh")) or ["其他"])[0]
            profile_rows.setdefault(g, []).append({
                "rating": vals["vote_average"],
                "votes": vals["vote_count"],
                "runtime": vals["runtime"],
            })
        matrix = []
        for ka, _ in _CORR_VARS:
            row = []
            for kb, _ in _CORR_VARS:
                r = 1.0 if ka == kb else pearson(cols[ka], cols[kb])
                row.append(round(r, 3) if r is not None else None)
            matrix.append(row)

        pairs = [(b, r) for b, r in zip(cols["budget"], cols["revenue"])
                 if b is not None and r is not None]
        xs = [p[0] for p in pairs]
        ys = [p[1] for p in pairs]
        reg_raw = linear_regression(xs, ys)
        reg = RegressionInfo(**{k: round(v, 4) if isinstance(v, float) else v
                                for k, v in reg_raw.items()}) if reg_raw else None

        scatter = []
        for s in rows:
            b, r = _pos(s.get("budget")), _pos(s.get("revenue"))
            if b is None or r is None:
                continue
            scatter.append(CorrelationPoint(
                x=float(b), y=float(r), rating=_num(s.get("vote_average")),
                title=_title(s), movie_id=str(s.get("movie_id") or ""),
            ))
        scatter.sort(key=lambda p: -p.y)
        scatter = scatter[:600]

        by_genre: dict[str, list[float]] = {}
        for s in rows:
            b, r = _pos(s.get("budget")), _pos(s.get("revenue"))
            if b is None or r is None:
                continue
            roi = (r - b) / b
            if abs(roi) > 100:            # 预算极小导致的天文数字，口径上剔除
                continue
            g = (_list(s.get("genres_zh")) or ["其他"])[0]
            by_genre.setdefault(g, []).append(roi)
        boxes: list[RoiBox] = []
        for g, vals in by_genre.items():
            q = quantiles(vals)
            if not q or q["count"] < 5:
                continue
            boxes.append(RoiBox(
                genre=g, count=int(q["count"]),
                **{k: round(float(v), 3)
                   for k, v in q.items() if k != "count"},
            ))
        boxes.sort(key=lambda b: -b.median)

        notes = []
        best = None
        for i, (ka, la) in enumerate(_CORR_VARS):
            for j, (kb, lb) in enumerate(_CORR_VARS):
                if j <= i or matrix[i][j] is None:
                    continue
                if best is None or abs(matrix[i][j]) > abs(best[0]):
                    best = (matrix[i][j], la, lb)
        if best:
            notes.append(f"最强相关：{best[1]} × {best[2]}，r = {best[0]:+.2f}")
        if reg:
            notes.append(f"预算只能解释票房波动的 {reg.r2 * 100:.0f}%"
                         f"（{reg.n} 部有完整预算/票房的影片，最小二乘）")
        if boxes:
            notes.append(f"投资回报中位数最高：{boxes[0].genre} "
                         f"({boxes[0].median:.2f}×，{boxes[0].count} 部)")
        roi_median = {b.genre: b.median for b in boxes}

        def avg_of(rs: list[dict], key: str) -> float:
            vs = [r[key] for r in rs if r[key] is not None]
            return sum(vs) / len(vs) if vs else 0.0

        profiles: list[GenreProfile] = []
        for g, rs in profile_rows.items():
            if len(rs) < 5:
                continue
            rated = [r["rating"] for r in rs if r["rating"] is not None]
            profiles.append(GenreProfile(
                genre=g, movies=len(rs),
                avg_rating=round(avg_of(rs, "rating"), 2),
                avg_votes=round(avg_of(rs, "votes")),
                avg_runtime=round(avg_of(rs, "runtime")),
                hit_rate=(round(sum(1 for v in rated if v >= 8) / len(rated), 3)
                          if rated else 0.0),
                median_roi=roi_median.get(g),
            ))
        profiles.sort(key=lambda p: -p.movies)

        return CorrelationResponse(
            variables=[k for k, _ in _CORR_VARS],
            labels=[l for _, l in _CORR_VARS],
            matrix=matrix, sample_size=len(rows), scatter=scatter,
            regression=reg, roi_by_genre=boxes[:10],
            profiles=profiles[:8], notes=notes,
        )

    return await cache.get_or_set("insights:correlations", _produce)


@router.get("/flows", response_model=FlowLayersResponse,
            summary="类型 → 年代 → 口碑档三层流向 + 类型×年代热力")
async def flows() -> FlowLayersResponse:
    """比旧的 build_genre_decade_matrix 多切一层 range(vote_average)。

    桑基的第三级节点是「这一批片里有多少部进了 8 分档」，由 ES 桶给出，
    不是把平均分涂个颜色充数。
    """
    async def _produce() -> FlowLayersResponse:
        es = get_es().options(request_timeout=15)
        try:
            resp = await es.search(
                index=settings.es_index_movies, **build_flow_layers())
        except Exception as exc:  # noqa: BLE001
            raise _guard(SearchUnavailable(f"{type(exc).__name__}: {exc}")) from exc

        nodes: dict[str, FlowNode] = {}
        link_sums: dict[tuple[str, str], int] = {}
        heat: list[FlowHeat] = []
        decades: set[int] = set()
        genres: list[str] = []
        over8: dict[str, int] = {}
        totals: dict[str, int] = {}

        def ensure(name: str, kind: str) -> None:
            nodes.setdefault(name, FlowNode(name=name, kind=kind))

        def add_link(source: str, target: str, value: int) -> None:
            key = (source, target)
            link_sums[key] = link_sums.get(key, 0) + value

        for b in resp.get("aggregations", {}).get("by_genre", {}).get("buckets", []):
            g = str(b["key"])
            genres.append(g)
            gn = f"G·{g}"
            ensure(gn, "genre")
            for d in b.get("by_decade", {}).get("buckets", []):
                dec = int(float(d["key"]))
                decades.add(dec)
                # ★ 年代层跨类型共享：若按「类型×年代」各建一个节点，8 类型 ×7 年代
                #   会碎成 56 个节点，桑基只剩一团细线（实拍确认）。三层语义就是
                #   类型→年代→口碑档，细节由同接口的 heat 热力另给。
                dn = f"D·{dec}s"
                ensure(dn, "decade")
                cnt = int(d["doc_count"])
                add_link(gn, dn, cnt)
                totals[g] = totals.get(g, 0) + cnt
                avg = d.get("avg_rating", {}).get("value")
                heat.append(FlowHeat(
                    genre=g, decade=dec, movies=cnt,
                    avg_rating=round(float(avg), 2) if avg is not None else None,
                ))
                for t in d.get("tier", {}).get("buckets", []):
                    c = int(t["doc_count"])
                    if c <= 0:
                        continue
                    key = str(t["key"])
                    tn = f"T·{_TIER_NAMES.get(key, key)}"
                    ensure(tn, "tier")
                    add_link(dn, tn, c)
                    if key == "over8":
                        over8[g] = over8.get(g, 0) + c

        links = [FlowLink(source=s, target=t, value=v)
                 for (s, t), v in link_sums.items() if v > 0]
        notes = []
        ranked = [(g, c / totals[g]) for g, c in over8.items() if totals.get(g)]
        if ranked:
            g, p = max(ranked, key=lambda x: x[1])
            notes.append(f"8 分以上占比最高的类型：{g}（{p * 100:.1f}%，"
                         f"{over8[g]}/{totals[g]} 部）")
        notes.append(f"{len(genres)} 个类型 · {len(decades)} 个年代 · "
                     f"{len(links)} 条真实流向边")
        return FlowLayersResponse(
            nodes=list(nodes.values()), links=links, heat=heat,
            decades=sorted(decades), genres=genres, notes=notes,
        )

    return await cache.get_or_set("insights:flows", _produce)
