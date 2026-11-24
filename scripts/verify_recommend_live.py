"""推荐 + 评分 + 趣味功能实测脚本：注册→打分→个性化→相似→盲盒 全链路。

每次运行用带时间戳的用户名，可重复执行不冲突。
覆盖：评分幂等 upsert / 404 / 422、for-you 降级与个性化、similar 排除自身、
盲盒种子可复现、混搭器入参校验、全部需登录接口的 401 行为。
"""
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

BASE = "http://127.0.0.1:8000/api/v1"
SUFFIX = str(int(time.time()))[-6:]
USER = f"bob_{SUFFIX}"
PWD = "secret1"

PASS = FAIL = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"[ OK ] {name}" + (f"  ->  {detail}" if detail else ""))
    else:
        FAIL += 1
        print(f"[FAIL] {name}" + (f"  ->  {detail}" if detail else ""))


def call(method: str, path: str, body: dict | None = None, token: str | None = None,
         query: dict | None = None):
    url = BASE + path
    if query:
        url += "?" + urllib.parse.urlencode(query, doseq=True)
    req = urllib.request.Request(
        url,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Content-Type": "application/json",
                 **({"Authorization": f"Bearer {token}"} if token else {})},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw)
        except json.JSONDecodeError:
            return e.code, {"raw": raw.decode("utf-8", "replace")[:200]}
    except urllib.error.URLError as e:
        return 0, {"error": str(e)}


# ---------- 准备：注册 + 拿两部真实影片 ----------
print(f"== 0. 注册 {USER} 并取候选影片 ==")
s, r = call("POST", "/auth/register", {"username": USER, "password": PWD, "nickname": "Bob"})
token = r.get("access_token", "")
check("注册并自动登录", s == 200 and bool(token), f"http {s}")

s, pop = call("GET", "/recommend/popular", query={"size": 5})
check("热门榜单可用（公式参数带回）", s == 200 and pop.get("formula", {}).get("m") == 100,
      f"m={pop.get('formula', {}).get('m')}, c={pop.get('formula', {}).get('c')}")
ids = [it["movie"]["movie_id"] for it in pop.get("items", [])][:2]
check("拿到两部候选影片", len(ids) >= 2, str(ids))
MOVIE_A, MOVIE_B = ids[0], ids[1]

# ---------- 1. 未登录访问需登录接口 ----------
print("\n== 1. 未登录访问（应 401 ×3）==")
for path in ("/recommend/for-you", "/ratings"):
    s, _ = call("GET", path)
    check(f"GET {path} 无 token", s == 401, f"http {s}")
s, _ = call("POST", "/ratings", {"movie_id": MOVIE_A, "score": 9})
check("POST /ratings 无 token", s == 401, f"http {s}")

# ---------- 2. 评分 CRUD ----------
print("\n== 2. 评分：写入 / 幂等覆盖 / 边界 ==")
s, r = call("GET", "/ratings", token=token)
check("新用户评分列表为空（启动时 ratings 索引已自举）", s == 200 and r == [], f"http {s}")

s, r = call("POST", "/ratings", {"movie_id": MOVIE_A, "score": 9.0}, token=token)
check("给影片 A 打 9 分", s == 200 and r.get("score") == 9.0, json.dumps(r, ensure_ascii=False)[:90])

s, r2 = call("POST", "/ratings", {"movie_id": MOVIE_A, "score": 8.5}, token=token)
s2, lst = call("GET", "/ratings", token=token)
check("重复打分是覆盖不是追加（幂等 upsert）",
      s2 == 200 and len(lst) == 1 and lst[0]["score"] == 8.5,
      f"列表长度={len(lst)}, score={lst[0]['score'] if lst else None}")

s, _ = call("POST", "/ratings", {"movie_id": "tt_no_such_movie", "score": 8}, token=token)
check("给不存在的影片打分 → 404（防污染口味画像）", s == 404, f"http {s}")

s, _ = call("POST", "/ratings", {"movie_id": MOVIE_A, "score": 11}, token=token)
check("超过 10 分 → 422", s == 422, f"http {s}")

s, r = call("POST", "/ratings", {"movie_id": MOVIE_B, "score": 7.0}, token=token)
check("给影片 B 打 7 分（低于喜好阈值，但应排除）", s == 200, f"http {s}")

s, lst = call("GET", "/ratings", token=token)
check("评分列表按分数倒序", s == 200 and len(lst) == 2 and lst[0]["score"] == 8.5,
      f"{[(x['movie_id'], x['score']) for x in lst]}")

# ---------- 3. 个性化推荐 ----------
print("\n== 3. for-you：降级 → 个性化 ==")
# 用一个全新用户验证降级路径（bob 此时已有 2 条评分）
s, reg2 = call("POST", "/auth/register", {"username": f"carol_{SUFFIX}", "password": PWD})
token2 = reg2.get("access_token", "")
s, deg = call("GET", "/recommend/for-you", token=token2)
check("无评分用户 → 退化为热门且如实标注 degraded=True",
      s == 200 and deg.get("degraded") is True and "formula" in deg,
      f"degraded={deg.get('degraded')}")

s, fy = call("GET", "/recommend/for-you", token=token)
check("有评分用户 → 个性化（degraded=False）", s == 200 and fy.get("degraded") is False,
      f"degraded={fy.get('degraded')}")
check("口味画像非空（类型/导演）", bool((fy.get("profile") or {}).get("genres")),
      json.dumps(fy.get("profile"), ensure_ascii=False))
check("based_on 引用了 8.5 分的那条评分",
      any(b["movie_id"] == MOVIE_A for b in fy.get("based_on", [])),
      json.dumps(fy.get("based_on"), ensure_ascii=False)[:120])
hit_ids = {it["movie"]["movie_id"] for it in fy.get("items", [])}
check("已评分的影片不出现在推荐里（A 和 B 都被排除）",
      MOVIE_A not in hit_ids and MOVIE_B not in hit_ids)
reasons = [it.get("reason") for it in fy.get("items", []) if it.get("reason")]
check("推荐理由人类可读", bool(reasons), str(reasons[:2]))

# ---------- 4. 相似影片 ----------
print("\n== 4. similar：相似推荐 ==")
s, sim = call("GET", f"/recommend/similar/{MOVIE_A}")
check("相似影片 200 且 base 是参考片", s == 200 and sim.get("base", {}).get("movie_id") == MOVIE_A,
      f"http {s}")
sim_ids = {it["movie"]["movie_id"] for it in sim.get("items", [])}
check("相似结果不含参考片自己", MOVIE_A not in sim_ids)
check("相似条目带相关度分数", all(it.get("score") for it in sim.get("items", [])[:3]))

s, _ = call("GET", "/recommend/similar/tt_no_such_movie")
check("参考片不存在 → 404", s == 404, f"http {s}")

# ---------- 5. 删除评分 ----------
print("\n== 5. 删除评分 ==")
s, _ = call("DELETE", f"/ratings/{MOVIE_A}", token=token)
check("删除影片 A 的评分", s == 200, f"http {s}")
s, _ = call("DELETE", f"/ratings/{MOVIE_A}", token=token)
check("重复删除 → 404（不存在）", s == 404, f"http {s}")
s, lst = call("GET", "/ratings", token=token)
check("删除后列表只剩 B", len(lst) == 1 and lst[0]["movie_id"] == MOVIE_B)

# ---------- 6. 趣味功能 ----------
print("\n== 6. 混搭器 / 盲盒 ==")
s, mix = call("POST", "/fun/mix", {"genres": ["科幻", "喜剧"], "size": 5})
check("混搭器 200（可能 0 命中但带解释）", s == 200 and "meta" in mix,
      f"total={mix.get('meta', {}).get('total')}, note={mix.get('note')}")

s, _ = call("POST", "/fun/mix", {"genres": ["科幻"]})
check("混搭器单类型 → 422（没有混搭意义）", s == 422, f"http {s}")

s, box1 = call("GET", "/fun/box", query={"seed": 42})
s2, box2 = call("GET", "/fun/box", query={"seed": 42})
check("盲盒同种子抽同一部（可复现随机）",
      s == 200 and box1.get("movie", {}).get("movie_id") == box2.get("movie", {}).get("movie_id")
      and box1.get("movie") is not None,
      f"{box1.get('movie', {}).get('movie_id')} vs {box2.get('movie', {}).get('movie_id')}")
check("盲盒回传种子", box1.get("seed") == 42)

s, box3 = call("GET", "/fun/box", query={"seed": 42, "genres": ["科幻"]})
check("盲盒可按类型圈池", s == 200 and
      (box3.get("movie") is None or "科幻" in box3["movie"]["genres_zh"]),
      json.dumps(box3.get("movie", {}) or {}, ensure_ascii=False)[:80] or box3.get("note"))

print("\n" + "=" * 60)
print(f"  合计 {PASS + FAIL} 项：{PASS} 通过，{FAIL} 失败")
print("=" * 60)
sys.exit(1 if FAIL else 0)
