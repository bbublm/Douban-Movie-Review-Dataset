"""从 ES movies 索引导出全部带 tmdb_id 的电影，作为 TMDB 影评采集的电影清单。

输出 data_lake/interim/tmdb_movies_all.jsonl，字段对齐 normalize_review 所需：
  tmdb_id / title / title_zh / title_en / original_title / release_year / imdb_id
"""
from __future__ import annotations
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from common.settings import settings

ES = "http://localhost:9200"


def es_search(body: dict) -> dict:
    req = urllib.request.Request(
        f"{ES}/movies/_search",
        data=json.dumps(body).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def main() -> None:
    # 487 < 1000，一次取完（带 tmdb_id 的电影）
    body = {
        "size": 1000,
        "query": {"exists": {"field": "tmdb_id"}},
        "_source": [
            "tmdb_id", "title_zh", "title_en", "original_title", "title",
            "release_year", "imdb_id",
        ],
    }
    resp = es_search(body)
    hits = resp["hits"]["hits"]
    out = settings.lake("interim") / "tmdb_movies_all.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)

    n = 0
    with out.open("w", encoding="utf-8") as fh:
        for h in hits:
            s = h["_source"]
            tid = s.get("tmdb_id")
            if not tid:
                continue
            # 显示名：优先中文，回退英文/原名
            title = s.get("title_zh") or s.get("title_en") or s.get("original_title") or s.get("title")
            rec = {
                "tmdb_id": int(tid),
                "title": title,
                "title_zh": s.get("title_zh"),
                "title_en": s.get("title_en"),
                "original_title": s.get("original_title"),
                "release_year": s.get("release_year"),
                "imdb_id": s.get("imdb_id"),
            }
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n += 1

    print(f"导出 {n} 部带 tmdb_id 的电影 → {out}")
    # 抽样验证
    import itertools
    with out.open(encoding="utf-8") as fh:
        for line in itertools.islice(fh, 3):
            print("  样例:", json.loads(line))


if __name__ == "__main__":
    main()
