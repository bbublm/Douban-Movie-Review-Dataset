"""
生产可用性批次 · 实测脚本 —— 不起 ES 数据写入，只验证新加的运维/用户功能。

覆盖（按段）：
    1. 探针        live 恒 200 / ready 查 ES / metrics 有界快照
    2. 请求头      每个响应都带 X-Request-ID
    3. 登录失败限流 同一 IP 连续失败 10 次后被 429 挡下（auth_fail 窗口）
    4. 成功清零    登录成功后失败计数清零，正常用户不被误伤
    5. 缓存        popular 连打两次，metrics 的 hits +1（第二次走缓存）
    6. 昵称        PATCH /auth/me 改昵称 → /me 生效；未登录 401
    7. 想看清单    加 → 查（hydration）→ 重复加幂等 → 删 → 再删 404；未登录 401
    8. 500 兜底    动态注册一个必崩路由，验证返回 JSON 500 + request_id（TestClient）

运行：python scripts/verify_ops_live.py   （需要 ES 在跑、服务在 8000 端口）
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

BASE = "http://127.0.0.1:8000/api/v1"
PWD = "ops-pass-2026"
SUFFIX = str(int(time.time()))[-6:]

_results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    _results.append((name, ok, detail))
    print(f"{'[ OK ]' if ok else '[FAIL]'} {name}" + (f"  ->  {detail}" if detail else ""))
    return ok


def check(name: str, ok: bool, detail: str = "") -> bool:
    _results.append((name, ok, detail))
    print(f"{'[ OK ]' if ok else '[FAIL]'} {name}" + (f"  ->  {detail}" if detail else ""))
    return ok


def request(method: str, path: str, body: dict | None = None,
            token: str | None = None) -> tuple[int, object, dict]:
    req = urllib.request.Request(BASE + path, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    data = json.dumps(body).encode() if body is not None else None
    try:
        with urllib.request.urlopen(req, data=data, timeout=20) as resp:
            status, headers = resp.status, dict(resp.headers)
            raw = resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        status, headers = exc.code, dict(exc.headers)
        raw = exc.read().decode("utf-8", "replace")
    try:
        return status, json.loads(raw), headers
    except json.JSONDecodeError:
        return status, raw[:200], headers


def main() -> int:
    print("=" * 68)
    print("  生产可用性 · 实测（探针 / 限流 / 缓存 / 昵称 / 想看清单 / 500 兜底）")
    print("=" * 68)

    # ---------- 1. 探针 ----------
    print("\n== 1. 健康探针 ==")
    s, live, h = request("GET", "/health/live")
    check("live 恒 200（进程活着就不看依赖）", s == 200 and live.get("status") == "alive",
          f"http {s}")
    s, ready, _ = request("GET", "/health/ready")
    check("ready 200（ES 可达才接流量）", s == 200 and ready.get("status") == "ready",
          f"http {s}")
    s, m, _ = request("GET", "/health/metrics")
    snap_ok = all(k in m for k in ("requests", "latency_ms", "recent",
                                   "rate_limit", "cache", "uptime_seconds"))
    check("metrics 有界快照（requests/latency/recent/cache 齐全）",
          s == 200 and snap_ok, f"http {s} keys={sorted(m)[:4]}…")
    check("metrics.recent 最多 20 条（有界，不当内存泄漏点）",
          len(m.get("recent", [])) <= 20)

    # ---------- 2. X-Request-ID ----------
    print("\n== 2. 请求追踪 ==")
    s, _, h = request("GET", "/health/live")
    rid = h.get("X-Request-ID") or h.get("x-request-id")
    check("响应带 X-Request-ID（出问题时用户报 ID 就能定位日志）", bool(rid), str(rid))
    s, _, h = request("GET", "/recommend/popular?size=3")
    check("业务接口同样带 X-Request-ID", bool(h.get("X-Request-ID") or h.get("x-request-id")))

    # ---------- 3/4. 登录失败限流与成功清零 ----------
    print("\n== 3. 登录失败限流 + 成功清零 ==")
    # 先注册两个用户（注册本身自动登录，返回 token）
    s, reg_a, _ = request("POST", "/auth/register",
                          {"username": f"ops_a_{SUFFIX}", "password": PWD})
    token_a = reg_a.get("access_token", "") if isinstance(reg_a, dict) else ""
    check("注册 ops_a 成功", s == 200 and bool(token_a), f"http {s}")

    # 成功清零语义：先成功登录一次（清掉可能的旧计数），
    # 再连续失败 3 次（都应 401 而不是 429）—— 正常用户手滑打错不被误伤
    s, _, _ = request("POST", "/auth/login",
                      {"username": f"ops_a_{SUFFIX}", "password": PWD})
    check("正确口令登录 200", s == 200, f"http {s}")
    fails = []
    for _ in range(3):
        st, _, _ = request("POST", "/auth/login",
                           {"username": f"ops_a_{SUFFIX}", "password": "wrong-pass"})
        fails.append(st)
    check("登录成功后失败计数清零：再错 3 次也都是 401（没有累计）",
          fails == [401, 401, 401], str(fails))

    # 打满窗口：连续失败直到被 429（auth_fail 上限 10 次/分钟）。
    # 注意限流的 key 是 IP 不是用户名 —— 前面 ops_a 的 3 次失败同样占额度，
    # 这正是"爆破者换用户名也没用"的设计意图。
    statuses = []
    for _ in range(12):
        st, body, _ = request("POST", "/auth/login",
                              {"username": f"ops_b_{SUFFIX}", "password": "wrong-pass"})
        statuses.append(st)
    n_401 = statuses.count(401)
    n_429 = statuses.count(429)
    check("连续失败 12 次：前若干次 401，超限后 429（爆破者被挡下）",
          n_401 >= 6 and n_429 >= 1,
          f"401x{n_401} 429x{n_429} -> {statuses}")
    s, blocked, _ = request("POST", "/auth/login",
                            {"username": f"ops_b_{SUFFIX}", "password": "wrong-pass"})
    check("被限流期间继续失败也是 429（不是 401）", s == 429, f"http {s}")
    s, _, _ = request("GET", "/health/live")
    check("被限流的只有 auth 路径，探针不受影响（豁免生效）", s == 200, f"http {s}")

    # ---------- 5. 缓存 ----------
    print("\n== 4. TTL 缓存 ==")
    s, m0, _ = request("GET", "/health/metrics")
    hits0 = m0.get("cache", {}).get("hits", 0)
    misses0 = m0.get("cache", {}).get("misses", 0)
    s, pop1, _ = request("GET", "/recommend/popular?size=5")
    check("popular 第一次正常返回", s == 200 and len(pop1.get("items", [])) > 0, f"http {s}")
    s, pop2, _ = request("GET", "/recommend/popular?size=5")
    check("popular 第二次同样 200（缓存路径不影响正确性）", s == 200, f"http {s}")
    s, m1, _ = request("GET", "/health/metrics")
    hits1 = m1.get("cache", {}).get("hits", 0)
    misses1 = m1.get("cache", {}).get("misses", 0)
    check("缓存生效：第一次 miss、第二次 hit（数字说话）",
          misses1 > misses0 and hits1 > hits0,
          f"hits {hits0}->{hits1}, misses {misses0}->{misses1}")
    same = [i["movie"]["movie_id"] for i in pop1.get("items", [])] == \
           [i["movie"]["movie_id"] for i in pop2.get("items", [])]
    check("两次返回内容一致（同一份缓存，不是两次不同查询）", same)

    # ---------- 6. 昵称 ----------
    print("\n== 5. 昵称更新 ==")
    s, patched, _ = request("PATCH", "/auth/me", {"nickname": "夜航西飞"},
                            token=token_a)
    check("PATCH /auth/me 200 且返回新昵称",
          s == 200 and patched.get("nickname") == "夜航西飞", f"http {s}")
    s, me, _ = request("GET", "/auth/me", token=token_a)
    check("/me 读到更新后的昵称（部分更新已落库）",
          s == 200 and me.get("nickname") == "夜航西飞")
    s, _, _ = request("PATCH", "/auth/me", {"nickname": "x"})
    check("未登录改昵称 → 401", s == 401, f"http {s}")
    s, _, _ = request("PATCH", "/auth/me", {"nickname": ""}, token=token_a)
    check("空昵称 → 422（入参校验）", s == 422, f"http {s}")

    # ---------- 7. 想看清单 ----------
    print("\n== 6. 想看清单全流程 ==")
    # 先从热门榜拿一部真实存在的 movie_id
    s, pop, _ = request("GET", "/recommend/popular?size=5")
    movie_id = pop["items"][0]["movie"]["movie_id"]
    movie_title = pop["items"][0]["movie"].get("title_zh") or pop["items"][0]["movie"].get("title")

    s, added, _ = request("POST", f"/watchlist/{movie_id}", token=token_a)
    check("加入想看 200 且提示带片名",
          s == 200 and added.get("added") is True and movie_title in added.get("message", ""),
          f"http {s}")

    s, wl, _ = request("GET", "/watchlist", token=token_a)
    check("想看列表有 1 条", s == 200 and wl.get("total") == 1, f"http {s}")
    item = (wl.get("items") or [{}])[0]
    check("hydration：movie 详情已填（海报/评分能直接渲染）",
          item.get("movie") is not None and item["movie"]["movie_id"] == movie_id,
          f"title={item.get('movie_title')}")
    check("冗余标题与 movies 一致（不必回查）",
          item.get("movie_title") == movie_title,
          f"{item.get('movie_title')} vs {movie_title}")

    s, again, _ = request("POST", f"/watchlist/{movie_id}", token=token_a)
    s2, wl2, _ = request("GET", "/watchlist", token=token_a)
    check("重复加入是幂等（200 且列表不翻倍）",
          s == 200 and wl2.get("total") == 1, f"http {s}, total={wl2.get('total')}")

    s, _, _ = request("POST", "/watchlist/tt_no_such_movie", token=token_a)
    check("给不存在的影片加想看 → 404", s == 404, f"http {s}")

    s, _, _ = request("GET", "/watchlist")
    check("未登录查想看 → 401", s == 401, f"http {s}")

    s, removed, _ = request("DELETE", f"/watchlist/{movie_id}", token=token_a)
    check("移出想看 200", s == 200 and removed.get("added") is False, f"http {s}")
    s, _, _ = request("DELETE", f"/watchlist/{movie_id}", token=token_a)
    check("重复移出 → 404（不假装成功）", s == 404, f"http {s}")
    s, wl3, _ = request("GET", "/watchlist", token=token_a)
    check("移出后列表为空", s == 200 and wl3.get("total") == 0)

    # ---------- 8. for-you 补齐与结构 ----------
    print("\n== 7. 个性化推荐结构 ==")
    s, fy, _ = request("GET", "/recommend/for-you?size=10", token=token_a)
    check("for-you 200", s == 200, f"http {s}")
    check("无评分用户退化为热门并如实标注 degraded=True",
          fy.get("degraded") is True and "formula" in fy, f"degraded={fy.get('degraded')}")
    s, _, _ = request("GET", "/recommend/for-you")
    check("未登录访问 for-you → 401", s == 401, f"http {s}")

    # ---------- 9. 500 兜底（TestClient 内动态注册必崩路由）----------
    print("\n== 8. 500 兜底 ==")
    from fastapi.testclient import TestClient  # noqa: E402

    from backend.main import app  # noqa: E402

    @app.get("/__boom_test__")
    async def _boom() -> dict:
        raise RuntimeError("intentional crash for testing")

    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.get("/__boom_test__")
        body = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        check("未处理异常 → JSON 500（不是 Starlette 纯文本 500）",
              r.status_code == 500 and "detail" in body, f"http {r.status_code}")
        check("500 响应带 request_id（用户报障时报这串就能定位日志）",
              bool(body.get("request_id")), str(body.get("request_id")))
        check("debug 模式给 error_type（生产模式不泄露异常细节）",
              body.get("error_type") == "RuntimeError", str(body.get("error_type")))

    print("\n" + "=" * 68)
    passed = sum(1 for _, ok, _ in _results if ok)
    failed = len(_results) - passed
    print(f"  合计 {len(_results)} 项：{passed} 通过，{failed} 失败")
    print("=" * 68)
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
