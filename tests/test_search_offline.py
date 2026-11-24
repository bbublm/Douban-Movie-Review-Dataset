"""
阶段 3 离线自检 —— 不联网、不碰 ES，验证检索逻辑的每个判断。

为什么检索逻辑要能离线测？
    query_builder.py 是纯函数（参数 → ES DSL），所以这些真正决定搜索质量的东西
    ——字段权重、分面排除、排序退化——全都可以在这里断言，
    不用先起 ES 再拿 curl 一条条试。改一个权重，几秒钟就知道有没有写错。

重点盯四类容易悄悄失效的地方：
    · 权重字段写错名 → 该字段永远搜不到（ES 不报错，只是没结果）
    · 分面把自己也算进去 → 筛选器自锁（点了科幻就看不到喜剧）
    · 无关键词还按相关性排 → _score 全是 1.0，等于随机排序
    · ES 返回类型与响应模型不符 → 接口 500（tmdb_id 是数字而非字符串，实测踩过）

运行：
    python tests/test_search_offline.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.schemas.search import (  # noqa: E402
    MovieSearchRequest,
    ReviewSearchRequest,
)
from backend.services.query_builder import (  # noqa: E402
    MOVIE_FACETS,
    MOVIE_HIGHLIGHT_FIELDS,
    MOVIE_TEXT_FIELDS,
    build_facet_aggs,
    build_filter_clauses,
    build_highlight,
    build_keyword_query,
    build_movie_query,
    build_post_filter,
    build_review_query,
    build_sort,
    build_suggest_query,
)
from backend.services.search_service import (  # noqa: E402
    _applied_filters,
    _is_selected,
    _to_movie_hit,
)
from index.mappings import MOVIES_MAPPING, REVIEWS_MAPPING  # noqa: E402

_results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    _results.append((name, ok, detail))
    print(f"{'[ OK ]' if ok else '[FAIL]'} {name}" + (f"  ->  {detail}" if detail else ""))
    return ok


def movie_req(**kw) -> MovieSearchRequest:
    return MovieSearchRequest(**kw)


# ============================================================
def main() -> int:
    print("=" * 68)
    print("  阶段 3 · 检索逻辑离线自检")
    print("=" * 68)

    # ================= 1. 关键词查询 =================
    print("\n-- 1. 关键词查询（召回 + 精度提升）--")

    check("q 为空 → match_all（浏览模式）", build_keyword_query(None) == {"match_all": {}})
    check("q 是纯空格 → 同样走 match_all",
          build_keyword_query("   ") == {"match_all": {}})

    best = build_keyword_query("流浪地球", "best")
    check("best 模式用 bool.should 组合多段信号", "bool" in best and "should" in best["bool"])
    should = best["bool"]["should"]
    check("含 multi_match 召回层", any("multi_match" in c for c in should))
    check("含 match_phrase 精度提升层",
          any("match_phrase" in c for c in should), f"共 {len(should)} 段")
    phrase = next(c for c in should if "match_phrase" in c)
    check("片名短语提升权重最高（boost=5）",
          phrase["match_phrase"]["title"]["boost"] == 5.0)

    check("phrase 模式用 phrase_prefix（联想场景）",
          build_keyword_query("流浪地", "phrase")["multi_match"]["type"] == "phrase_prefix")
    cross = build_keyword_query("诺兰 科幻", "cross")["bool"]["should"]
    check("cross 模式追加 cross_fields 子句",
          any(c.get("multi_match", {}).get("type") == "cross_fields" for c in cross))

    # 权重字段必须在 mapping 里 —— 否则该字段永远搜不到，且 ES 不报错
    mv_props = MOVIES_MAPPING["properties"]
    bad = [f for f, _ in MOVIE_TEXT_FIELDS if f not in mv_props]
    check("★ 检索字段全部存在于 mapping（写错字段名会静默失效）",
          not bad, "、".join(bad))
    check("片名权重高于简介（越短越具体的字段越可信）",
          dict(MOVIE_TEXT_FIELDS)["title"] > dict(MOVIE_TEXT_FIELDS)["overview"])
    check("中英文片名权重一致（用哪种语言搜都一样）",
          dict(MOVIE_TEXT_FIELDS)["title"] == dict(MOVIE_TEXT_FIELDS)["title_zh"])

    # ================= 2. 筛选条件 =================
    print("\n-- 2. 筛选条件（按分面分组）--")

    check("无筛选 → 空字典", build_filter_clauses(movie_req()) == {})

    c = build_filter_clauses(movie_req(genres=["科幻", "喜剧"]))
    check("genres 默认 or → 一条 terms", c["genres"][0].get("terms") is not None)

    c_and = build_filter_clauses(movie_req(genres=["科幻", "喜剧"], genre_op="and"))
    check("genre_op=and → 拆成多个 term（必须同时具备）",
          len(c_and["genres"]) == 2 and all("term" in x for x in c_and["genres"]))
    check("and 模式是阶段 6 类型混搭器的基础", len(c_and["genres"]) == len(["科幻", "喜剧"]))

    c = build_filter_clauses(movie_req(year_from=2000, year_to=2010))
    check("年份区间 → range on release_year",
          c["years"][0]["range"]["release_year"] == {"gte": 2000, "lte": 2010})
    c = build_filter_clauses(movie_req(year_from=2000))
    check("只有下界时也要能过滤", c["years"][0]["range"]["release_year"] == {"gte": 2000})

    c = build_filter_clauses(movie_req(rating_min=8.0))
    check("评分下限 → range on vote_average",
          c["rating"][0]["range"]["vote_average"] == {"gte": 8.0})

    c = build_filter_clauses(movie_req(require_poster=True, require_overview=True))
    check("数据质量筛选 → exists 查询",
          all("exists" in x for x in c["quality"]), str(c["quality"]))

    c = build_filter_clauses(movie_req(multi_source_only=True))
    check("只要多源融合成功的 → term on is_multi_source",
          c["quality"][0]["term"]["is_multi_source"] is True)

    # ================= 3. post_filter =================
    print("\n-- 3. post_filter（分面不自锁的关键）--")

    check("无筛选时不产出 post_filter（DSL 保持干净）",
          build_post_filter(build_filter_clauses(movie_req())) is None)

    clauses = build_filter_clauses(movie_req(genres=["科幻"], year_from=2010))
    post = build_post_filter(clauses)
    check("有筛选时 post_filter 摊平所有子句", len(post["bool"]["filter"]) == 2)

    body = build_movie_query(movie_req(q="地球", genres=["科幻"]))
    # 注意：不能傻搜 "genres_zh" 这个子串 —— 它同时是**检索字段**（带权重 1.5），
    # 在 query 里出现是正常的。要看的是**结构**：query 里只能有 should，不能有 filter。
    q_bool = body["query"].get("bool", {})
    check("★ 筛选进 post_filter 而不是 query（否则分面会自锁）",
          "post_filter" in body
          and set(q_bool) == {"should", "minimum_should_match"}
          and "genres_zh" in str(body["post_filter"]),
          f"query 的键={sorted(q_bool)}")

    # ================= 4. 分面聚合 =================
    print("\n-- 4. 分面聚合（互相排除 drill-down）--")

    clauses = build_filter_clauses(movie_req(genres=["科幻"], countries=["美国"]))
    aggs = build_facet_aggs(clauses, MOVIE_FACETS)

    check("每个分面都包在 filter + aggs.top 下（读结果路径统一）",
          all("filter" in v and "top" in v["aggs"] for v in aggs.values()))

    genres_filter = aggs["facet_genres"]["filter"]
    check("★ 类型分面统计时排除「类型」自己的条件",
          "genres_zh" not in str(genres_filter), str(genres_filter)[:80])
    check("★ 类型分面仍应用「国家」条件（这才是 drill-down）",
          "primary_country" in str(genres_filter))  # 2026-10-20 起国家口径改主出品国字段

    countries_filter = aggs["facet_countries"]["filter"]
    check("国家分面同理：排除自己、保留类型条件",
          "primary_country" not in str(countries_filter)
          and "genres_zh" in str(countries_filter))

    check("无筛选时 filter 退化成 match_all（结构不变，读法不变）",
          build_facet_aggs({}, MOVIE_FACETS)["facet_genres"]["filter"] == {"match_all": {}})

    check("评分分面用 range（浮点值用 terms 会碎成几百个桶）",
          "range" in aggs["facet_rating"]["aggs"]["top"])
    check("年份分面按年份倒序（不是按数量，否则年份顺序会被打乱）",
          aggs["facet_years"]["aggs"]["top"]["terms"]["order"] == {"_key": "desc"})

    facet_fields = [f for _, f, _, _, _ in MOVIE_FACETS]
    bad_facet = [f for f in facet_fields if f not in mv_props]
    check("★ 分面字段全部存在于 mapping", not bad_facet, "、".join(bad_facet))

    # ================= 5. 排序 =================
    print("\n-- 5. 排序（无关键词时的退化）--")

    s, used = build_sort("relevance", "desc", has_query=True)
    check("有关键词时按 _score 排", s[0] == {"_score": {"order": "desc"}} and used == "relevance")

    s, used = build_sort("relevance", "desc", has_query=False)
    check("★ 无关键词时 relevance 退化成按热度（_score 全是 1.0，等于随机排）",
          used == "votes" and "vote_count" in s[0], str(s[0]))

    s, _ = build_sort("rating", "desc", has_query=True)
    check("按评分排 → vote_average", "vote_average" in s[0])
    check("评分有兜底排序（同分时票多的在前，避免 3 人打 9.9 分压过肖申克）",
          "vote_count" in s[1], str(s[1]))
    check("缺失值排最后（missing=_last）", s[0]["vote_average"]["missing"] == "_last")

    s, _ = build_sort("title", "asc", has_query=False)
    check("按片名排走 keyword 子字段（text 不能排序）",
          "title.kw" in s[0], str(s[0]))

    # ================= 6. 高亮 =================
    print("\n-- 6. 高亮（含 XSS 防护）--")

    hl = build_highlight(MOVIE_HIGHLIGHT_FIELDS)
    check("★ encoder=html（默认不转义，前端 v-html 渲染就是 XSS 口子）",
          hl["encoder"] == "html")
    check("片名整段返回（number_of_fragments=0），不截断",
          MOVIE_HIGHLIGHT_FIELDS["title"]["number_of_fragments"] == 0)
    check("简介只截片段（整篇回传太大）",
          MOVIE_HIGHLIGHT_FIELDS["overview"]["number_of_fragments"] == 2)
    check("require_field_match=False（命中关键词时也要能高亮简介）",
          hl["require_field_match"] is False)

    # ================= 7. 完整 DSL =================
    print("\n-- 7. 完整 DSL 组装 --")

    body = build_movie_query(movie_req(q="地球", page=3, size=10))
    check("分页换算正确（第 3 页 × 10 条 → from=20）", body["from"] == 20)
    check("★ track_total_hits=True（ES 默认只精确统计到 1 万条，影评有 5 万）",
          body["track_total_hits"] is True)

    body = build_movie_query(movie_req(with_facets=False))
    check("with_facets=False 时不产出 aggs（省一次聚合开销）", "aggs" not in body)
    check("无筛选时 DSL 里没有 post_filter 键", "post_filter" not in body)

    # ================= 8. 影评检索 =================
    print("\n-- 8. 影评检索 --")

    body = build_review_query(ReviewSearchRequest(q="wonderful"))
    check("影评正文检索用 match + operator=and（词多时不至于召回过宽）",
          body["query"]["match"]["text"]["operator"] == "and")

    body = build_review_query(ReviewSearchRequest(sentiment=["positive"], min_words=100))
    check("情感筛选 → terms on sentiment",
          body["post_filter"]["bool"]["filter"][0]["terms"]["sentiment"] == ["positive"])
    check("篇幅筛选 → range on word_count",
          any("word_count" in str(c) for c in body["post_filter"]["bool"]["filter"]))

    rv_props = REVIEWS_MAPPING["properties"]
    check("★ 影评响应字段都在 mapping 里",
          all(f in rv_props for f in ("text", "sentiment", "word_count", "movie_id")))

    # ================= 9. 联想 =================
    print("\n-- 9. 搜索联想 --")

    body = build_suggest_query("流浪地")
    check("联想用 phrase_prefix（打一半也能出结果）",
          body["query"]["multi_match"]["type"] == "phrase_prefix")
    check("联想只搜片名，不搜简介（联想屏小，出简介命中没意义）",
          all(f.split("^")[0].startswith(("title", "original_title"))
              for f in body["query"]["multi_match"]["fields"]))
    check("_source 限定字段（少传数据）", "_source" in body)

    # ================= 10. 服务层纯函数 =================
    print("\n-- 10. 服务层（ES 结果 → 响应模型）--")

    # 这条断言直接对应实测踩到的 500 错误：ES 里 tmdb_id 是数字
    hit = _to_movie_hit({"_source": {"movie_id": "tt1", "tmdb_id": 798645,
                                     "imdb_id": "tt1", "genres_zh": ["剧情"]},
                         "_id": "tt1", "_score": 1.5})
    check("★ tmdb_id 数字被转成字符串（响应模型是 str，否则接口 500）",
          hit.tmdb_id == "798645" and isinstance(hit.tmdb_id, str))

    empty = _to_movie_hit({"_source": {}, "_id": "x"})
    check("空文档不崩，字段取默认值", empty.genres_zh == [] and empty.rating is None)
    check("缺 movie_id 时退回 _id", empty.movie_id == "x")

    req = movie_req(genres=["科幻"], year_from=2019, year_to=2019)
    check("已选类型被标为 selected（前端据此打勾）",
          _is_selected("genres", {"key": "科幻"}, req) is True)
    check("未选类型不标 selected", _is_selected("genres", {"key": "喜剧"}, req) is False)
    check("年份单选时标 selected",
          _is_selected("years", {"key": "2019"}, req) is True)
    check("年份区间（非单选）不标 selected",
          _is_selected("years", {"key": "2019"}, movie_req(year_from=2010, year_to=2019)) is False)
    check("评分区间能被识别为已选",
          _is_selected("rating", {"key": "8 ~ 9 分"}, movie_req(rating_min=8.0, rating_max=9.0)))

    applied = _applied_filters(movie_req(q="地球", genres=["科幻"], page=1))
    check("回显条件里去掉了空值与分页参数",
          applied == {"q": "地球", "genres": ["科幻"], "mode": "best",
                      "genre_op": "or", "sort": "relevance", "order": "desc",
                      "with_facets": True}
          or ("page" not in applied and "" not in applied.values()),
          str(applied))

    # ================= 11. GET 端点参数覆盖 =================
    # 踩过的坑：GET /movies 漏了 with_facets，前端传 with_facets=false 拿到的
    # 依然是分面 —— FastAPI 对未知查询参数不报错，直接用默认值顶上，
    # 表现为"参数传了没反应"，排查起来很费时间。所以这里用模型字段反查端点。
    from backend.api.v1.search import get_search_movies, get_search_reviews  # noqa: E402
    import inspect  # noqa: E402

    def _get_params(fn) -> set[str]:
        return set(inspect.signature(fn).parameters)

    movie_params = _get_params(get_search_movies)
    missing_movie = set(MovieSearchRequest.model_fields) - movie_params
    check("GET /movies 的参数覆盖了请求模型的每个字段",
          not missing_movie, f"缺少：{sorted(missing_movie)}")

    review_params = _get_params(get_search_reviews)
    missing_review = set(ReviewSearchRequest.model_fields) - review_params
    check("GET /reviews 的参数覆盖了请求模型的每个字段",
          not missing_review, f"缺少：{sorted(missing_review)}")

    check("with_facets 能在 GET 上关掉（不传就默认开）",
          "with_facets" in movie_params and "with_facets" in review_params)

    # ================= 汇总 =================
    passed = sum(1 for _, ok, _ in _results if ok)
    total = len(_results)
    print()
    print("=" * 68)
    print(f"  结果：{passed}/{total} 通过")
    if passed != total:
        print("  失败项：")
        for name, ok, detail in _results:
            if not ok:
                print(f"    - {name}  {detail}")
    print("=" * 68)
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
