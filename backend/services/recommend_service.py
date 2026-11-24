"""
推荐服务：相似影片 / 热门榜单 / 个性化推荐。

三个接口对应三种推荐范式，都由 ES 查询完成，Python 侧只做编排：

| 接口 | 范式 | 做法 |
|---|---|---|
| similar/{id} | 基于内容 | more_like_this：用该片自己的文本找气质相近的 |
| popular | 全局统计 | 贝叶斯加权分 WR（IMDb Top 250 同款公式） |
| for-you | 个性化 | 用户打高分影片的类型/导演画像 → 候选召回 |

口味画像（build_taste_profile）是**纯函数**，离线可测：
喂它"用户打过高分的影片列表"，吐"类型偏好 + 导演偏好"。
"""
from __future__ import annotations

from collections import Counter

from backend.schemas.search import MovieHit
from backend.services.query_builder import (
    build_for_you_query,
    build_popular_query,
    build_similar_fallback_query,
    build_similar_query,
)
from backend.services.search_service import SearchUnavailable, _to_movie_hit, get_movie
from common.es_client import get_es
from common.settings import settings

# 进热门榜的最低票数门槛（贝叶斯公式里的 m）。
# 100 是按 IMDb 规模的 1/50 缩放的经验值 —— 片库小，门槛太高会只剩几部片。
POPULAR_MIN_VOTES = 100

# 口味画像：打几分以上算"喜欢"；取前几个类型/导演
FAVORITE_THRESHOLD = 8.0
TASTE_TOP_GENRES = 3
TASTE_TOP_DIRECTORS = 2


class RecommendError(Exception):
    """推荐领域异常基类。"""


class MovieNotFoundForRecommend(RecommendError):
    """被参考的电影不存在。"""


# ---------------- 口味画像（纯函数，离线自检）----------------

def build_taste_profile(favorite_movies: list[dict]) -> dict:
    """从用户打过高分的影片里统计口味。

    为什么导演权重隐含更高：类型是粗粒度（一部片常有 2-3 个类型），
    导演是细粒度身份信号 —— 同一个导演出现 2 次，比同一个类型出现 2 次
    更能说明"用户在追谁"。所以导演只取前 2，类型取前 3。
    """
    genre_counter: Counter = Counter()
    director_counter: Counter = Counter()
    for mv in favorite_movies:
        for g in mv.get("genres_zh") or []:
            genre_counter[g] += 1
        director = mv.get("director")
        if director:
            director_counter[director] += 1
    return {
        "genres": [g for g, _ in genre_counter.most_common(TASTE_TOP_GENRES)],
        "directors": [d for d, _ in director_counter.most_common(TASTE_TOP_DIRECTORS)],
    }


def recommend_reason(movie: dict, profile: dict) -> str | None:
    """给一部推荐影片生成人类可读的理由。命不中口味就返回 None（不硬编）。"""
    genres = set(movie.get("genres_zh") or [])
    director = movie.get("director")
    if director and director in profile.get("directors", []):
        return f"你喜欢的导演 {director} 的作品"
    hit = genres & set(profile.get("genres", []))
    if hit:
        return "贴合你偏好的「" + "、".join(sorted(hit)) + "」类型"
    return None


# ---------------- ES 编排 ----------------

async def _global_avg_rating(es: AsyncElasticsearch) -> float:
    """全局平均分（贝叶斯公式里的 C）。取不到（空库）时退回 6.0 ——
    10 分制的中位数附近，宁可用一个平庸的先验也不要 0。"""
    resp = await es.search(
        index=settings.es_index_movies, size=0,
        aggs={"avg": {"avg": {"field": "vote_average"}}},
    )
    value = (resp.get("aggregations", {}).get("avg", {}) or {}).get("value")
    return float(value) if value is not None else 6.0


async def similar_movies(
    movie_id: str, size: int = 10
) -> tuple[MovieHit | None, list[MovieHit], list[MovieHit]]:
    """相似影片。返回 (参考片, 文本相似, 同类型补充)。

    两段召回：
        more_like_this  —— 文本层面的"气质相近"（首选，理由最硬）
        同类型兜底      —— MLT 召回不足时补齐 + 文本太稀疏时保底

    ★ 为什么要补齐而不是只做兜底：MLT 常常只召回 1-2 条（片库只有几百部，
      简介短、类型单一），详情页就只剩两张卡，看起来像坏了。
      先给 MLT 的强相关结果，再用同类型补齐到 size 张 ——
      两段在原因为不同的 reason 里分别说明，前端不会混为一谈。
    """
    base = await get_movie(movie_id)
    if base is None:
        return None, [], []
    es = get_es()
    try:
        resp = await es.search(index=settings.es_index_movies,
                               **build_similar_query(movie_id, settings.es_index_movies, size))
        contents = [_to_movie_hit(h) for h in resp["hits"]["hits"]]
        if len(contents) >= size:
            return base, contents, []

        seen = {m.movie_id for m in contents} | {base.movie_id}
        extra_size = size - len(contents) + len(seen)
        resp = await es.search(
            index=settings.es_index_movies,
            **build_similar_fallback_query(
                movie_id,
                genres=list(base.genres_zh or []),
                rating=base.rating,
                year=base.year,
                size=extra_size,
            ),
        )
    except Exception as exc:  # noqa: BLE001
        raise SearchUnavailable(f"{type(exc).__name__}: {exc}") from exc

    extras: list[MovieHit] = []
    for h in resp["hits"]["hits"]:
        m = _to_movie_hit(h)
        if m.movie_id in seen:
            continue
        seen.add(m.movie_id)
        extras.append(m)
        if len(contents) + len(extras) >= size:
            break
    return base, contents, extras


async def popular_movies(size: int = 20) -> tuple[list[MovieHit], dict]:
    """热门榜单。返回 (影片列表, 公式参数) —— 参数一起返回，
    前端能把"WR = (v/(v+m))·R + (m/(v+m))·C，m=100, C=7.2"原样展示给用户。"""
    es = get_es()
    try:
        c = await _global_avg_rating(es)
        resp = await es.search(index=settings.es_index_movies,
                               **build_popular_query(POPULAR_MIN_VOTES, c, size))
    except Exception as exc:  # noqa: BLE001
        raise SearchUnavailable(f"{type(exc).__name__}: {exc}") from exc
    return [_to_movie_hit(h) for h in resp["hits"]["hits"]], {"m": POPULAR_MIN_VOTES, "c": round(c, 2)}


async def for_you_movies(username: str, size: int = 20) -> dict:
    """个性化推荐。用户没打过分 → 退化为热门榜（并如实告知 degraded=True）。"""
    from backend.services.ratings_store import list_user_ratings

    es = get_es()
    ratings = await list_user_ratings(es, username, min_score=FAVORITE_THRESHOLD)
    if not ratings:
        hits, params = await popular_movies(size)
        return {
            "items": [{"movie": m, "reason": "还没有评分记录，先看大家都爱看的", "score": None}
                      for m in hits],
            "based_on": [],
            "degraded": True,
            "formula": params,
        }

    # 拿用户喜欢影片的完整信息，统计口味
    favorite_ids = [r["movie_id"] for r in ratings]
    favorites: list[dict] = []
    for mid in favorite_ids[:20]:      # 口味统计不需要全部历史，前 20 部足够
        mv = await get_movie(mid)
        if mv is not None:
            favorites.append(mv.model_dump())
    profile = build_taste_profile(favorites)

    # 排除用户打过分（不管高低分）的全部影片 —— 推荐看过的片是最差体验
    all_rated = [r["movie_id"] for r in await list_user_ratings(es, username)]
    try:
        resp = await es.search(index=settings.es_index_movies,
                               **build_for_you_query(profile["genres"], profile["directors"],
                                                     all_rated, size))
    except Exception as exc:  # noqa: BLE001
        raise SearchUnavailable(f"{type(exc).__name__}: {exc}") from exc

    items = []
    for h in resp["hits"]["hits"]:
        movie = _to_movie_hit(h)
        items.append({
            "movie": movie,
            "reason": recommend_reason(movie.model_dump(), profile),
            "score": round(h.get("_score") or 0.0, 4),
        })

    # 候选不足时用热门补齐，并如实标注 —— 半页结果的体验比"理由不匹配"更糟。
    # 宁可在理由里写"热门补位"，也不假装这些片贴合了用户口味。
    if len(items) < size:
        needed = size - len(items)
        shown_ids = {it["movie"].movie_id for it in items}
        exclude = set(all_rated) | shown_ids
        try:
            fill_hits, _params = await popular_movies(size + len(all_rated))
        except SearchUnavailable:
            fill_hits = []  # 补齐失败不影响主列表，降级为"只有这么多"
        for m in fill_hits:
            if len(items) >= size:
                break
            if m.movie_id in exclude:
                continue
            items.append({
                "movie": m,
                "reason": "热门补位：贴合你口味的新片暂时不够，先用大家都爱看的填满",
                "score": None,
            })

    return {
        "items": items,
        "based_on": [{"movie_id": r["movie_id"], "title": r.get("movie_title"),
                      "score": r["score"]} for r in ratings[:5]],
        "degraded": False,
        "profile": profile,
    }
