"""
阶段 1a 离线自检 —— 不联网也能验证采集链路。

为什么要这个：
    采集模块的价值 80% 在「归一化 + 缓存命中 + 落盘」这条链路上，
    而这部分完全可以用一份真实 API 响应固件跑通，不需要网络。
    真机上的网络问题（代理 / 限流）就交给 run_collect 的报错提示去处理。

运行：
    python tests/test_ingest_offline.py
"""
from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from common.settings import settings  # noqa: E402
from ingest.http import dump_raw  # noqa: E402
from ingest.seed import load_legacy_movies, normalize_legacy  # noqa: E402
from ingest.sources.tmdb import APPEND, TmdbCollector, normalize_movie, write_jsonl  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "tmdb_movie_550.json"
TEST_KEY = "TEST_KEY"
_results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    _results.append((name, ok, detail))
    print(f"{'[ OK ]' if ok else '[FAIL]'} {name}" + (f"  ->  {detail}" if detail else ""))
    return ok


def main() -> int:
    print("=" * 68)
    print("  阶段 1a · 采集链路离线自检")
    print("=" * 68)

    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    tmp = Path(tempfile.mkdtemp(prefix="yjzs_test_"))
    original_lake = settings.data_lake
    settings.data_lake = str(tmp)
    print(f"  临时数据湖：{tmp}\n")

    try:
        # ---------- 1. 归一化 ----------
        rec = normalize_movie(raw, genre_map={18: "剧情", 53: "悬疑"})
        check("tmdb_id", rec["tmdb_id"] == 550)
        check("imdb_id", rec["imdb_id"] == "tt0137523", rec["imdb_id"])
        check("中文片名", rec["title"] == "搏击俱乐部", rec["title"])
        check("原始片名", rec["title_en"] == "Fight Club", rec["title_en"])
        check("上映年份", rec["release_year"] == 1999, str(rec["release_year"]))
        check("片长", rec["runtime"] == 139)
        check("类型（含剧情/悬疑）", {"剧情", "悬疑"} <= set(rec["genres_zh"]), str(rec["genres_zh"]))
        check("导演（从 crew 提取 job=Director）", rec["director"] == "大卫·芬奇", str(rec["director"]))
        check("主演（取前 5 位）", len(rec["cast"]) == 3, str(rec["cast"]))
        check(
            "海报直链",
            (rec["poster_url"] or "").startswith("https://image.tmdb.org/t/p/w500"),
            str(rec["poster_url"]),
        )
        check("关键词", "nihilism" in rec["keywords"], str(rec["keywords"]))
        check("制片国家", "美国" in rec["production_countries"], str(rec["production_countries"]))

        # ---------- 2. 缓存命中（关键：断点续跑）----------
        collector = TmdbCollector(api_key=TEST_KEY, force=False)
        params = {"api_key": TEST_KEY, "language": collector.lang, "append_to_response": APPEND}
        dump_raw(
            {"_request": {"path": "/movie/550", "params": params}, "_response": raw},
            settings.lake("raw", "tmdb", "movie", "550.json"),
        )
        cached = collector.movie_detail(550)
        check("缓存命中不重发请求", collector.stats["api_calls"] == 0 and collector.stats["cache_hits"] == 1,
              f"api_calls={collector.stats['api_calls']} cache_hits={collector.stats['cache_hits']}")
        check("缓存内容正确", cached.get("id") == 550)

        # ---------- 3. 请求参数变了 → 缓存自动失效 ----------
        changed = {"api_key": TEST_KEY, "language": "en-US", "append_to_response": APPEND}
        dump_raw(
            {"_request": {"path": "/movie/550", "params": changed}, "_response": {"id": 999}},
            settings.lake("raw", "tmdb", "movie", "550.json"),
        )
        # 这一步本来就是要失败（缓存失效后去联网），把重试次数压到 1 免得白等 30 秒
        collector.client.max_retries = 1
        try:
            collector.movie_detail(550)
            stale_ok = False  # 参数不一致却直接返回了缓存 = bug
        except Exception:
            # 参数不匹配 → 判定缓存失效 → 尝试联网 → 沙箱里必然失败，这正是预期行为
            stale_ok = True
        collector.client.max_retries = settings.tmdb_max_retries
        check("请求参数变化时缓存自动失效", stale_ok)

        # ---------- 4. 类型字典缓存 ----------
        collector2 = TmdbCollector(api_key=TEST_KEY, force=False)
        dump_raw(
            {"_request": {"path": "/genre/movie/list", "params": {"api_key": TEST_KEY, "language": collector2.lang}},
             "_response": {"genres": [{"id": 18, "name": "剧情"}, {"id": 53, "name": "悬疑"}]}},
            settings.lake("raw", "tmdb", "genre_list.json"),
        )
        gmap = collector2.genre_map()
        check("类型字典（id → 中文名）", gmap.get(18) == "剧情" and collector2.stats["api_calls"] == 0, str(gmap))

        # ---------- 5. JSONL 落盘 ----------
        out = settings.lake("interim") / "tmdb_movies.jsonl"
        n = write_jsonl([rec, rec], out)
        lines = out.read_text(encoding="utf-8").strip().splitlines()
        back = json.loads(lines[0])
        check("JSONL 行数与可回读", n == 2 and len(lines) == 2 and back["tmdb_id"] == 550, f"{n} 行")

        # ---------- 6. 旧片库复用 ----------
        legacy = load_legacy_movies()
        check("旧片库可读", len(legacy) == 120, f"{len(legacy)} 部")
        if legacy:
            lrec = normalize_legacy(legacy[0])
            need = {"tmdb_id", "imdb_id", "title", "release_year", "genres_zh", "source", "upstream"}
            check("旧记录字段与 TMDB 结构对齐", need <= set(lrec), f"缺：{need - set(lrec)}")
            check("旧记录保留数据血缘", lrec["source"] == "legacy" and bool(lrec["upstream"]),
                  f"source={lrec['source']} upstream={lrec['upstream']}")

        collector.close()
        collector2.close()
    finally:
        settings.data_lake = original_lake
        shutil.rmtree(tmp, ignore_errors=True)

    passed = sum(1 for _, ok, _ in _results if ok)
    total = len(_results)
    print("-" * 68)
    print(f"  结果：{passed}/{total} 项通过")
    print("  ✅ 采集链路离线自检全部通过" if passed == total else "  ⚠️  存在失败项，请检查上面的 [FAIL]")
    print("=" * 68)
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
