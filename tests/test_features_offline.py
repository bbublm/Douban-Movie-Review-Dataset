"""
阶段 5 前 · 后端功能补全离线自检 —— 不联网、不碰 ES。

覆盖五个新模块的**纯逻辑**部分：
    1. trends   年代趋势聚合 DSL 构造 + 桶转换
    2. users    密码哈希 / JWT 签发与解析 / 角色判定
    3. users    用户映射与公开视图 / 注册入参校验
    4. recommend 口味画像 / 推荐理由 / 相似·热门·个性化查询构造
    5. fun      盲盒随机种子 / 混搭器入参 / 评分映射

为什么要离线测这些？
    密码与 JWT 是安全门卫，写错了不会报错、只会"永远登不上"或"谁都能登"；
    推荐与盲盒的打分公式是数值逻辑，一个符号错误结果就反了；
    查询构造 DSL 里少一个 must_not，推荐结果就会出现它自己。
    这些全都可以不起服务直接断言。

运行：
    python tests/test_features_offline.py
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import jwt as pyjwt  # noqa: E402

from backend.schemas.auth import RegisterRequest, UpdateProfileRequest  # noqa: E402
from backend.schemas.fun import MixRequest  # noqa: E402
from backend.schemas.insights import TrendBucket  # noqa: E402
from backend.schemas.recommend import RatingRequest  # noqa: E402
from backend.services.auth import (  # noqa: E402
    InvalidCredentials,
    create_access_token,
    decode_token,
    hash_password,
    verify_password,
)
from backend.services.query_builder import (  # noqa: E402
    build_decade_aggs,
    build_for_you_query,
    build_popular_query,
    build_random_query,
    build_similar_query,
)
from backend.services.recommend_service import (  # noqa: E402
    FAVORITE_THRESHOLD,
    POPULAR_MIN_VOTES,
    build_taste_profile,
    recommend_reason,
)
from backend.services.user_store import ROLE_ADMIN, public_view  # noqa: E402
from common.settings import settings  # noqa: E402
from index.mappings import RATINGS_MAPPING, USERS_MAPPING, WATCHLIST_MAPPING  # noqa: E402

_results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    _results.append((name, ok, detail))
    print(f"{'[ OK ]' if ok else '[FAIL]'} {name}" + (f"  ->  {detail}" if detail else ""))
    return ok


# ============================================================
def main() -> int:
    print("=" * 68)
    print("  后端功能补全 · 离线自检（trends / users / recommend / fun）")
    print("=" * 68)

    # ================= 1. trends 年代趋势 =================
    print("\n-- 1. 年代趋势聚合 --")

    aggs = build_decade_aggs()
    check("聚合键为 by_decade", "by_decade" in aggs)
    hist = aggs["by_decade"]["histogram"]
    check("histogram 作用于 release_year", hist["field"] == "release_year")
    check("区间为 10 年（年代语义）", hist["interval"] == 10)
    check("min_doc_count=0 补空桶（折线不断档）", hist["min_doc_count"] == 0)
    check("带 avg_rating 子聚合",
          "avg_rating" in aggs["by_decade"]["aggs"])

    # 桶转换：ES 的 histogram key 是浮点（1980.0）， decade 必须是 int
    bucket = TrendBucket(decade=1980, movies=10, avg_rating=7.5)
    check("TrendBucket.decade 是 int（前端图轴要整数年代）",
          isinstance(bucket.decade, int))
    check("空年代均分允许为 None（补零桶没有评分）",
          TrendBucket(decade=1990, movies=0, avg_rating=None).avg_rating is None)

    # ================= 2. users 密码与 JWT =================
    print("\n-- 2. 密码哈希 / JWT --")

    h1 = hash_password("admin123")
    h2 = hash_password("admin123")
    check("bcrypt 哈希带 $2b$ 标识与 cost=12",
          h1.startswith("$2b$12$"), h1[:10])
    check("同一口令两次哈希不同（随机盐，彩虹表失效）", h1 != h2)
    check("正确口令校验通过", verify_password("admin123", h1))
    check("错误口令校验拒绝", not verify_password("admin124", h1))
    check("哈希损坏时返回 False 而不是抛异常（坏数据不打爆登录接口）",
          not verify_password("admin123", "not-a-hash"))

    token = create_access_token("alice", "user")
    payload = decode_token(token)
    check("token 解析出 sub=用户名", payload["sub"] == "alice")
    check("token 解析出 role", payload["role"] == "user")
    exp_minutes = settings.jwt_expire_minutes
    lifetime = payload["exp"] - payload["iat"]
    check("有效期与配置一致（分钟级）", abs(lifetime - exp_minutes * 60) < 2,
          f"{lifetime}s vs {exp_minutes}min")

    forged = pyjwt.encode({"sub": "hacker", "role": "admin", "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
                          "wrong-secret-longer-than-32-bytes-too", algorithm="HS256")
    try:
        decode_token(forged)
        check("错误密钥签发的 token 必须拒绝", False)
    except InvalidCredentials:
        check("错误密钥签发的 token 必须拒绝", True)

    tampered = token[:-6] + ("abcdef" if not token.endswith("abcdef") else "aaaaaa")
    try:
        decode_token(tampered)
        check("篡改签名必须拒绝", False)
    except InvalidCredentials:
        check("篡改签名必须拒绝", True)

    expired = pyjwt.encode(
        {"sub": "alice", "role": "user",
         "iat": datetime.now(timezone.utc) - timedelta(hours=2),
         "exp": datetime.now(timezone.utc) - timedelta(hours=1)},
        settings.jwt_secret, algorithm="HS256")
    try:
        decode_token(expired)
        check("过期 token 必须拒绝", False)
    except InvalidCredentials:
        check("过期 token 必须拒绝", True)

    # ================= 3. users 映射与公开视图 =================
    print("\n-- 3. 用户映射 / 公开视图 --")

    props = USERS_MAPPING["properties"]
    check("password_hash 不建索引（只能按 id 整条取，不进倒排）",
          props["password_hash"].get("index") is False)
    check("username 是 keyword（精确匹配/id 直查）",
          props["username"]["type"] == "keyword")
    check("role 是 keyword（terms 聚合查管理员数）",
          props["role"]["type"] == "keyword")
    check("dynamic=strict（写错字段名直接报错，不静默丢弃）",
          USERS_MAPPING["dynamic"] == "strict")

    view = public_view({"username": "alice", "password_hash": "$2b$12$xxx",
                        "role": "user", "nickname": "Alice", "created_at": "2026-10-15T00:00:00+00:00"})
    check("公开视图不含 password_hash", "password_hash" not in view)
    check("公开视图含角色（前端权限渲染用）", view["role"] == "user")
    check("ROLE_ADMIN 常量为 admin", ROLE_ADMIN == "admin")

    # ================= 4. 注册入参校验 =================
    print("\n-- 4. 注册入参校验 --")

    try:
        RegisterRequest(username="ab", password="secret1")
        check("用户名短于 3 位必须拒绝", False)
    except Exception:
        check("用户名短于 3 位必须拒绝", True)
    try:
        RegisterRequest(username="中文名", password="secret1")
        check("用户名含中文必须拒绝（token/URL 安全字符集）", False)
    except Exception:
        check("用户名含中文必须拒绝（token/URL 安全字符集）", True)
    try:
        RegisterRequest(username="alice", password="12345")
        check("口令短于 6 位必须拒绝", False)
    except Exception:
        check("口令短于 6 位必须拒绝", True)
    ok = RegisterRequest(username="alice_01", password="secret1")
    check("合法注册请求通过", ok.username == "alice_01" and ok.nickname is None)

    # ================= 5. 推荐：口味画像与理由 =================
    print("\n-- 5. 口味画像 / 推荐理由 --")

    favorites = [
        {"movie_id": "m1", "title_zh": "星际穿越", "genres_zh": ["科幻", "冒险"], "director": "诺兰"},
        {"movie_id": "m2", "title_zh": "盗梦空间", "genres_zh": ["科幻", "悬疑"], "director": "诺兰"},
        {"movie_id": "m3", "title_zh": "疯狂动物城", "genres_zh": ["喜剧", "动画"], "director": "拜伦·霍华德"},
        {"movie_id": "m4", "title_zh": "海洋奇缘", "genres_zh": ["喜剧", "动画"], "director": "罗恩·克莱蒙兹"},
    ]
    profile = build_taste_profile(favorites)
    check("类型画像取 top3（科幻2、喜剧2、动画2 并列取前）",
          profile["genres"] == ["喜剧", "动画", "科幻"] or
          set(profile["genres"]) == {"喜剧", "动画", "科幻"},
          str(profile["genres"]))
    check("导演画像只取 top2（诺兰2次居首，细粒度身份信号）",
          profile["directors"][0] == "诺兰" and len(profile["directors"]) == 2,
          str(profile["directors"]))
    check("空列表不炸（新用户/全删评分时）", build_taste_profile([]) == {"genres": [], "directors": []})
    check("缺 genres_zh 字段的影片被跳过（脏数据不污染统计）",
          build_taste_profile([{"director": "诺兰"}, {}]) == {"genres": [], "directors": ["诺兰"]})

    nolan_film = {"movie_id": "m9", "title_zh": "信条", "genres_zh": ["科幻"], "director": "诺兰"}
    check("命中导演偏好 → 理由点出导演",
          recommend_reason(nolan_film, profile) == "你喜欢的导演 诺兰 的作品",
          recommend_reason(nolan_film, profile))
    genre_film = {"movie_id": "m8", "title_zh": "机器人总动员", "genres_zh": ["喜剧", "科幻"], "director": "安德鲁·斯坦顿"}
    reason = recommend_reason(genre_film, profile)
    check("命中类型偏好 → 理由点出类型（不硬编理由）",
          reason is not None and "喜剧" in reason and "科幻" in reason, str(reason))
    off_film = {"movie_id": "m7", "title_zh": "教父", "genres_zh": ["剧情", "犯罪"], "director": "科波拉"}
    check("口味不命中 → 理由为 None（宁缺毋滥，不编造）",
          recommend_reason(off_film, profile) is None)

    # ================= 6. 推荐：查询构造 =================
    print("\n-- 6. 相似 / 热门 / 个性化 查询构造 --")

    sq = build_similar_query("m1", "movies", 10)
    mlt = sq["query"]["bool"]["must"][0]["more_like_this"]
    check("MLT like 用 _index/_id 形式（ES 自取原文按分析器切词）",
          mlt["like"] == [{"_index": "movies", "_id": "m1"}])
    check("min_doc_freq=1（百余部的小片库，默认3会把多数词滤掉）",
          mlt["min_doc_freq"] == 1)
    check("must_not 排除它自己（推荐结果里出现参考片是最常见事故）",
          sq["query"]["bool"]["must_not"] == [{"ids": {"values": ["m1"]}}])

    pq = build_popular_query(100, 7.2, 20)
    script = pq["query"]["function_score"]["functions"][0]["script_score"]["script"]
    check("贝叶斯公式参数 m/c 传入 script params",
          script["params"] == {"m": 100, "c": 7.2})
    check("boost_mode=replace（WR 直接作为相关性分，不叠加原查询分）",
          pq["query"]["function_score"]["boost_mode"] == "replace")
    check("script 对缺字段做 size() 守卫（缺 vote_average 的文档不能让整个查询500）",
          "doc['vote_average'].size() == 0" in script["source"])
    check("公式分子分母形状正确（v/(v+m)·R + m/(v+m)·C）",
          "(v / (v + params.m)) * r" in script["source"]
          and "(params.m / (v + params.m)) * params.c" in script["source"])
    check("POPULAR_MIN_VOTES 与 build_popular_query 默认口径一致",
          POPULAR_MIN_VOTES == 100)

    fq = build_for_you_query(["科幻", "喜剧"], ["诺兰"], ["m1", "m2"], 20)
    should = fq["query"]["bool"]["should"]
    check("类型 should 带 boost 2.0", should[0] == {"terms": {"genres_zh": ["科幻", "喜剧"], "boost": 2.0}})
    check("导演 should 用 director.kw 精确匹配且 boost 3.0（导演是更强身份信号）",
          should[1] == {"term": {"director.kw": {"value": "诺兰", "boost": 3.0}}})
    check("minimum_should_match=1（至少中一个口味，不要求全中）",
          fq["query"]["bool"]["minimum_should_match"] == 1)
    check("已评分影片全部排除（推荐看过的片是最差体验）",
          fq["query"]["bool"]["must_not"] == [{"ids": {"values": ["m1", "m2"]}}])
    empty_fq = build_for_you_query([], [], [], 20)
    check("无口味画像时不产生 must_not 键（DSL 干净）",
          "must_not" not in empty_fq["query"]["bool"])

    # ================= 7. 趣味功能 =================
    print("\n-- 7. 盲盒 / 混搭器 --")

    rq = build_random_query(42, [{"terms": {"genres_zh": ["科幻"]}}], 1)
    fs = rq["query"]["function_score"]
    rnd = fs["functions"][0]["random_score"]
    check("random_score 带 seed（同种子同结果，可复现演示）", rnd["seed"] == 42)
    check("random_score 用 movie_id 而非 _id/_seq_no（_id 默认禁 fielddata 会 400；_seq_no 随更新漂移）",
          rnd["field"] == "movie_id")
    check("包 function_score + boost_mode=replace（ES 无独立 random_score 查询，实测400）",
          fs["boost_mode"] == "replace")
    check("筛选条件进内层 bool.filter（先圈池子再抽签）",
          fs["query"]["bool"]["filter"] == [{"terms": {"genres_zh": ["科幻"]}}])
    check("无筛选时内层退化为 match_all",
          build_random_query(1, None)["query"]["function_score"]["query"] == {"match_all": {}})

    # ================= 8. 评分映射与入参 =================
    print("\n-- 8. 评分映射 / 入参校验 --")

    rprops = RATINGS_MAPPING["properties"]
    check("username 是 keyword（按用户查评分）", rprops["username"]["type"] == "keyword")
    check("movie_id 是 keyword（_id=用户名:movie_id 幂等 upsert 的另一半）",
          rprops["movie_id"]["type"] == "keyword")
    check("score 是 float（0.5 粒度半分）", rprops["score"]["type"] == "float")

    ok_rating = RatingRequest(movie_id="m1", score=8.5)
    check("合法评分通过（半分粒度）", ok_rating.score == 8.5)
    for bad, why in [(0.4, "低于 0.5 分"), (10.1, "高于 10 分")]:
        try:
            RatingRequest(movie_id="m1", score=bad)
            check(f"评分 {bad} 必须拒绝（{why}）", False)
        except Exception:
            check(f"评分 {bad} 必须拒绝（{why}）", True)
    try:
        RatingRequest(movie_id="", score=8.0)
        check("空 movie_id 必须拒绝", False)
    except Exception:
        check("空 movie_id 必须拒绝", True)

    # ================= 9. 混搭器入参 =================
    print("\n-- 9. 混搭器入参校验 --")

    try:
        MixRequest(genres=["科幻"])
        check("单个类型必须拒绝（没有'混搭'的意义）", False)
    except Exception:
        check("单个类型必须拒绝（没有'混搭'的意义）", True)
    try:
        MixRequest(genres=["a", "b", "c", "d", "e", "f"])
        check("超过 5 个类型必须拒绝（防止空结果+手滑）", False)
    except Exception:
        check("超过 5 个类型必须拒绝（防止空结果+手滑）", True)
    ok_mix = MixRequest(genres=["科幻", "喜剧"], rating_min=7.0)
    check("合法混搭请求通过", ok_mix.genres == ["科幻", "喜剧"] and ok_mix.rating_min == 7.0)

    # ================= 10. 限流器窗口逻辑 =================
    print("\n-- 10. IP 限流器（滑动窗口）--")

    import asyncio

    from backend.middleware import RateLimiter, RequestStats, _is_exempt  # noqa: E402

    lim = RateLimiter()
    verdicts = [lim.hit("1.2.3.4", limit=10, window=60.0)[0] for _ in range(12)]
    check("窗口内前 10 次放行", all(verdicts[:10]))
    check("第 11 次起拒绝（超限挡在业务之前）", not any(verdicts[10:]))
    ok, retry = lim.hit("1.2.3.4", limit=10, window=60.0)
    check("被拒时给出 retry_after（0 < retry <= 60）",
          not ok and 0 < retry <= 60, f"retry_after={retry}")
    check("limit<=0 视为不限制（配置关闸）",
          lim.hit("9.9.9.9", limit=0, window=60.0)[0])
    check("不同 IP 互不影响（限流粒度是 IP）",
          lim.hit("5.6.7.8", limit=10, window=60.0)[0])
    lim.clear("1.2.3.4")
    check("clear 后重新放行（登录成功清零的语义）",
          lim.hit("1.2.3.4", limit=10, window=60.0)[0])

    short = RateLimiter()
    for _ in range(3):
        short.hit("10.0.0.1", limit=3, window=0.05)
    blocked, _ = short.hit("10.0.0.1", limit=3, window=0.05)
    check("窗口内记满即挡", not blocked)
    import time as _time
    _time.sleep(0.08)
    check("滑出窗口后自动恢复（过期时间戳惰性清理，无定时任务）",
          short.hit("10.0.0.1", limit=3, window=0.05)[0])

    # 接线语义：dispatch 对 auth 请求的判定方向（纯函数对不代表接线对 ——
    # 这里曾把 hit() 的「是否放行」返回值命名为 blocked 并 if blocked: 429，
    # 整个限流器反向工作，离线测 hit 本身抓不到，实测第一个请求就 429 才暴露）
    from starlette.requests import Request as StarletteRequest  # noqa: E402

    from backend.middleware import RateLimitMiddleware  # noqa: E402

    class _FakeResponse:
        def __init__(self, status: int) -> None:
            self.status_code = status
            self.headers: dict = {}

    def _make_request(path: str) -> StarletteRequest:
        scope = {"type": "http", "method": "POST", "path": path,
                 "headers": [], "client": ("10.9.9.9", 40000), "query_string": b""}
        return StarletteRequest(scope)

    async def _next_ok(_req):
        return _FakeResponse(200)

    async def _next_fail(_req):
        return _FakeResponse(401)

    mw = RateLimitMiddleware(app=None)
    r = asyncio.run(mw.dispatch(_make_request("/api/v1/auth/login"), _next_ok))
    check("接线语义：auth 请求应放行（返回 call_next 的 200，不是 429）",
          r.status_code == 200, f"got {r.status_code}")
    check("login 成功后 auth 失败计数被清零", len(mw._auth_fail) == 0)
    for _ in range(10):
        asyncio.run(mw.dispatch(_make_request("/api/v1/auth/login"), _next_fail))
    r = asyncio.run(mw.dispatch(_make_request("/api/v1/auth/login"), _next_fail))
    check("连续失败 10 次后第 11 次被 429 挡下（接线后方向正确）",
          r.status_code == 429, f"got {r.status_code}")
    r2 = asyncio.run(mw.dispatch(_make_request("/api/v1/search/movies"), _next_ok))
    check("被限流的只有 auth 路径，普通业务请求不受影响", r2.status_code == 200)

    # ================= 11. TTL 缓存 =================
    print("\n-- 11. TTL 缓存（single-flight / 过期 / 淘汰）--")

    from common.ttl_cache import TTLCache  # noqa: E402

    async def _cache_cases() -> None:
        # single-flight：并发同 key 只打一次 ES（缓存过期瞬间防雪崩）
        calls = 0

        async def producer():
            nonlocal calls
            calls += 1
            await asyncio.sleep(0.03)
            return {"v": 1}

        c = TTLCache(default_ttl=60)
        results = await asyncio.gather(*[c.get_or_set("k", producer) for _ in range(10)])
        check("single-flight：10 个并发同 key 只触发一次 producer", calls == 1, f"calls={calls}")
        check("并发等待者拿到同一份值", all(r == {"v": 1} for r in results))
        await c.get_or_set("k", producer)
        check("缓存命中后不再调 producer", calls == 1 and c.hits == 1,
              f"calls={calls} hits={c.hits}")

        # 异常不缓存：一次网络抖动不该被缓存 5 分钟
        async def bad():
            raise ValueError("boom")

        try:
            await c.get_or_set("bad", bad)
            check("producer 抛异常时向上传播（不伪装成功）", False)
        except ValueError:
            check("producer 抛异常时向上传播（不伪装成功）", True)
        check("异常不写缓存（下次照常重试）", "bad" not in c._store)
        await c.get_or_set("bad", lambda: _ok("recovered"))
        check("异常后可恢复正常取值", c._store["bad"][1] == "recovered")

        # TTL 过期
        c2 = TTLCache(default_ttl=0.05)
        await c2.get_or_set("t", lambda: _ok(1))
        await asyncio.sleep(0.08)
        await c2.get_or_set("t", lambda: _ok(2))
        check("TTL 到期后取新值（过期自动刷新）", c2._store["t"][1] == 2 and c2.misses == 2)

        # 有界淘汰
        c3 = TTLCache(default_ttl=60, maxsize=3)
        for i in range(5):
            await c3.get_or_set(f"k{i}", lambda: _ok(i))
        check("maxsize 淘汰最早的（FIFO，内存有界）",
              len(c3._store) == 3 and c3.evictions == 2 and "k0" not in c3._store,
              f"keys={sorted(c3._store)} evictions={c3.evictions}")
        n = c3.invalidate("k")
        check("按前缀 invalidate（重建索引后让旧榜单立刻失效）",
              n == 3 and len(c3._store) == 0, f"invalidated={n}")

    async def _ok(v):
        return v

    asyncio.run(_cache_cases())

    # ================= 12. 请求统计有界性 =================
    print("\n-- 12. 请求统计（有界，防内存泄漏）--")

    st = RequestStats()
    for i in range(300):
        st.record("GET", f"/api/v1/x{i}", 200 if i % 100 else 500, 0.01 * (i % 7))
    snap = st.snapshot()
    check("300 次请求全部计数", snap["requests"]["total"] == 300)
    check("5xx 单独计数", snap["requests"]["errors_5xx"] == 3)
    check("recent 外发上限 20 条（内部 deque maxlen=500，都不无限增长）",
          len(snap["recent"]) == 20, f"recent={len(snap['recent'])}")
    check("延迟统计有 avg/slowest", snap["latency_ms"]["slowest"] > 0 and snap["latency_ms"]["avg"] > 0)
    check("uptime 非负", snap["uptime_seconds"] >= 0)

    # ================= 13. 想看清单映射与资料更新 =================
    print("\n-- 13. 想看清单 / 资料更新 --")

    wprops = WATCHLIST_MAPPING["properties"]
    check("watchlist dynamic=strict（与 users/ratings 同一套严格性）",
          WATCHLIST_MAPPING["dynamic"] == "strict")
    check("username 是 keyword（按用户列清单）", wprops["username"]["type"] == "keyword")
    check("movie_id 是 keyword（_id=用户名:movie_id 幂等的另一半）",
          wprops["movie_id"]["type"] == "keyword")
    check("movie_title 带 kw 子字段（冗余标题展示 + 排序聚合两用）",
          wprops["movie_title"].get("fields", {}).get("kw", {}).get("type") == "keyword")

    from backend.services.ratings_store import _rating_id  # noqa: E402
    from backend.services.watchlist_store import _watch_id  # noqa: E402

    check("评分幂等键 = 用户名:movie_id（重复打分是覆盖不是追加）",
          _rating_id("alice", "tt1") == "alice:tt1")
    check("想看幂等键同构（连点星标不加出两行）", _watch_id("alice", "tt1") == "alice:tt1")

    try:
        UpdateProfileRequest(nickname="")
        check("空昵称必须拒绝", False)
    except Exception:
        check("空昵称必须拒绝", True)
    ok_profile = UpdateProfileRequest(nickname="阿鉴的观众")
    check("合法昵称通过", ok_profile.nickname == "阿鉴的观众")

    from backend.schemas.watchlist import WatchlistItem  # noqa: E402

    item = WatchlistItem(movie_id="tt1", movie_title="示例片", movie=None)
    check("影片被数据更新淘汰时 movie=None 合法（标题兜底，不整条消失）",
          item.movie is None and item.movie_title == "示例片")

    # ================= 14. 中间件豁免路径 =================
    print("\n-- 14. 探针/文档豁免限流 --")

    check("活体探针豁免（被限流会导致部署平台误杀容器）",
          _is_exempt("/api/v1/health/live"))
    check("就绪探针豁免", _is_exempt("/api/v1/health/ready"))
    check("文档路径豁免（答辩演示不能被 429 打断）", _is_exempt("/docs") and _is_exempt("/openapi.json"))
    check("主健康检查**不**豁免（语义上它是普通接口）", not _is_exempt("/api/v1/health"))
    check("业务接口**不**豁免（限流就是要挡它们）",
          not _is_exempt("/api/v1/search/movies") and not _is_exempt("/api/v1/auth/login"))

    print("\n" + "=" * 68)
    passed = sum(1 for _, ok, _ in _results if ok)
    failed = len(_results) - passed
    print(f"  合计 {len(_results)} 项：{passed} 通过，{failed} 失败")
    print("=" * 68)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
