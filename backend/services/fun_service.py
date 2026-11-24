"""
趣味功能服务：混搭器 / 随机盲盒。

这两个功能都不引入新算法，是已有能力的玩具化包装：
混搭器 = 检索（genre_op=and 强制AND）、盲盒 = 检索（random_score）。
逻辑轻，但每个都踩过一个真坑，注释里写清楚，免得后来人"优化"回去。
"""
from __future__ import annotations

import time

from backend.schemas.fun import BlindBoxResponse
from backend.schemas.search import MovieSearchRequest, MovieSearchResponse
from backend.services.query_builder import build_random_query
from backend.services.search_service import SearchUnavailable, _to_movie_hit, search_movies
from common.es_client import get_es
from common.settings import settings

# 盲盒默认只抽 7 分以上的 —— "随机"负责惊喜，"门槛"负责底线。
# 纯随机的盲盒会抽到 3 分烂片，demo 现场抽一次冷场一次。
BLIND_BOX_MIN_RATING = 7.0


async def mix_movies(req_genres: list[str], rating_min: float | None,
                     year_from: int | None, year_to: int | None,
                     size: int) -> MovieSearchResponse:
    """类型混搭器：同时具备所有类型的影片。

    直接复用检索服务，只做一件事：把 genre_op 硬编码成 "and"。
    ★ 为什么在服务层强制而不是信任客户端传 genre_op？
        混搭器的定义就是 AND。客户端传 "or" 上来，语义就成了普通筛选，
        页面标题却还写着"混搭"——接口要对得起自己的名字。
    """
    search_req = MovieSearchRequest(
        genres=req_genres,
        genre_op="and",
        rating_min=rating_min,
        year_from=year_from,
        year_to=year_to,
        size=size,
        with_facets=True,
    )
    resp = await search_movies(search_req)
    if resp.meta.total == 0:
        resp.note = (f"没有同时具备「{'、'.join(req_genres)}」全部类型的影片"
                     f"（可减少一个类型再试，或放宽评分/年代限制）")
    return resp


async def blind_box(
    seed: int | None = None,
    genres: list[str] | None = None,
    min_rating: float | None = BLIND_BOX_MIN_RATING,
) -> BlindBoxResponse:
    """随机盲盒：抽一部片。seed 缺省用当前毫秒时间戳。

    筛选（类型 / 最低分）作用于候选池：先圈定池子，再在池子里随机。
    顺序反了（先随机再筛）在 ES 里表达不了，而且结果分布也不对。
    """
    if seed is None:
        seed = int(time.time() * 1000) % (2**31)

    filters: list[dict] = []
    if genres:
        filters.append({"terms": {"genres_zh": genres}})
    if min_rating is not None:
        filters.append({"range": {"vote_average": {"gte": min_rating}}})

    try:
        es = get_es().options(request_timeout=10)
        resp = await es.search(index=settings.es_index_movies,
                               **build_random_query(seed, filters, 1))
    except Exception as exc:  # noqa: BLE001
        raise SearchUnavailable(f"{type(exc).__name__}: {exc}") from exc

    hits = resp["hits"]["hits"]
    if not hits:
        scope = "、".join(genres) + "类 " if genres else ""
        return BlindBoxResponse(
            movie=None, seed=seed,
            note=f"{scope}{min_rating} 分以上的影片一部都没抽到——条件太苛刻了，降降门槛试试",
        )
    return BlindBoxResponse(movie=_to_movie_hit(hits[0]), seed=seed)
