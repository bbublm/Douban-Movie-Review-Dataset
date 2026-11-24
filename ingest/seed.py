"""
复用旧系统沉淀的片库资产 —— 这是「在原项目基础上改」的落点。

旧 Flask 系统已经攒下 120 部中文片库（`data/web_movies.json`），
里面带着中文片名、类型、导演、简介、海报。这批数据不重做，
而是当作**种子片库**并入新平台的数据湖：

    种子片库 ──► 补齐 tmdb_id / imdb_id ──► 与 TMDB 采集结果实体对齐（阶段 2）

旧片库里大部分条目没有 tmdb_id（因为当年写库时只做了标题层合并），
所以这里提供 resolve_ids()：拿片名去 TMDB 搜一次，把 id 补上。
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import TYPE_CHECKING

from common.settings import PROJECT_ROOT, settings
from ingest.sources.tmdb import normalize_movie

if TYPE_CHECKING:  # 仅用于类型提示，避免循环导入
    from ingest.sources.tmdb import TmdbCollector

LEGACY_MOVIES_JSON = PROJECT_ROOT / "data" / "web_movies.json"


# ============================================================
# 读取与结构对齐
# ============================================================


def load_legacy_movies(path: Path | None = None) -> list[dict]:
    """读取旧系统片库。缺文件时返回空列表并给出提示，不抛异常中断流程。"""
    path = path or LEGACY_MOVIES_JSON
    if not path.exists():
        print(f"  [警告] 未找到旧片库 {path}，跳过种子导入")
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    movies = payload.get("movies") or []
    print(f"  读取旧片库：{len(movies)} 部（生成于 {payload.get('generated_at', '未知')}）")
    return movies


def normalize_legacy(movie: dict) -> dict:
    """旧片库记录 → 与 TMDB 采集结果对齐的统一结构。

    字段名刻意和 `tmdb.normalize_movie()` 保持一致，
    这样阶段 2 的融合逻辑可以直接把两批记录 concat 起来。
    """
    title_en = (movie.get("title_en") or "").strip()
    title_zh = (movie.get("title_zh") or movie.get("title") or "").strip()
    language = (movie.get("language") or "").strip()

    return {
        "tmdb_id": movie.get("tmdb_id"),
        "imdb_id": movie.get("imdb_id"),
        "title": title_zh or title_en,
        "title_zh": title_zh or None,
        "title_en": title_en or None,
        "original_title": title_en or None,
        "release_date": None,  # 旧片库只有年份，没有精确日期
        "release_year": movie.get("release_year"),
        "runtime": movie.get("duration"),
        "overview": (movie.get("description") or "").strip(),
        "tagline": "",
        "status": "",
        "genres_zh": movie.get("genres_zh") or ["剧情"],
        "genre_ids": [],
        "keywords": [],
        "director": movie.get("director"),
        "cast": [],
        "vote_average": 0.0,
        "vote_count": 0,
        "popularity": 0.0,
        "original_language": None,
        "spoken_languages": [language] if language else [],
        "production_countries": [],
        "production_country_codes": [],
        "poster_url": movie.get("poster_url"),
        "backdrop_url": None,
        "source": "legacy",
        "upstream": movie.get("source"),  # 旧片库里的原始来源，保留数据血缘
        "id_resolved": False,
        "collected_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


# ============================================================
# 用 TMDB 反查缺失的 id
# ============================================================


def _norm_title(text: str) -> str:
    return "".join(ch for ch in (text or "").lower() if ch.isalnum())


def _pick_best(results: list[dict], query: str, year: int | None) -> dict | None:
    """从搜索结果里挑最可信的一条：片名归一化后完全一致优先，其次看年份。"""
    if not results:
        return None
    target = _norm_title(query)
    exact = [r for r in results if _norm_title(r.get("title")) == target
             or _norm_title(r.get("original_title")) == target]
    pool = exact or results
    if year:
        same_year = [
            r for r in pool
            if (r.get("release_date") or "")[:4] == str(year)
        ]
        if same_year:
            pool = same_year
    # 同分时让热门片胜出，降低「同名冷门片」误配概率
    return sorted(pool, key=lambda r: -(r.get("popularity") or 0))[0]


def resolve_ids(
    collector: "TmdbCollector",
    records: list[dict],
    *,
    limit: int | None = None,
    with_detail: bool = True,
    progress: bool = True,
) -> list[dict]:
    """给缺 tmdb_id 的种子记录补 id，可选再拉一次详情补全类别/海报/评分。

    limit 用来控制单次消耗的 API 配额，方便分多次慢慢补。
    """
    todo = [r for r in records if not r.get("tmdb_id")]
    if limit:
        todo = todo[:limit]
    if not todo:
        if progress:
            print("  所有种子记录都已有 tmdb_id，无需反查")
        return records

    by_title = {r["title"]: r for r in todo}
    genre_map = collector.genre_map()

    if progress:
        print(f"  开始反查 {len(todo)} 条缺失 id 的种子记录 …")

    for idx, rec in enumerate(todo, 1):
        query = rec.get("title_en") or rec.get("title") or ""
        year = rec.get("release_year")
        try:
            results = collector.search_movie(query, year)
        except Exception as exc:  # noqa: BLE001 —— 单条失败不应中断整批
            print(f"    [跳过] {query} 搜索失败：{exc}")
            continue

        best = _pick_best(results, query, year)
        if not best:
            if progress:
                print(f"    [未命中] {query}（{year}）")
            continue

        target = by_title[query]
        target["tmdb_id"] = best.get("id")
        target["id_resolved"] = True

        if with_detail:
            try:
                detail = collector.movie_detail(best["id"])
            except Exception as exc:  # noqa: BLE001
                print(f"    [详情失败] tmdb_id={best['id']}：{exc}")
                continue
            enriched = normalize_movie(detail, genre_map)
            # TMDB 的字段更全，用它覆盖；但保留旧片库的中文简介（人工/半人工整理过，质量更好）
            legacy_overview = target["overview"]
            legacy_genres = target["genres_zh"]
            target.update({k: v for k, v in enriched.items() if v not in (None, "", [], 0, 0.0)})
            if legacy_overview:
                target["overview"] = legacy_overview
            if legacy_genres and not enriched.get("genres_zh"):
                target["genres_zh"] = legacy_genres
            target["source"] = "tmdb+legacy"

        if progress and idx % 10 == 0:
            print(f"    反查进度 {idx}/{len(todo)}")

    hit = sum(1 for r in todo if r.get("tmdb_id"))
    print(f"  反查完成：命中 {hit}/{len(todo)}")
    return records
