"""从 TMDB 原始详情缓存回填 revenue/budget 到 interim/tmdb_movies.jsonl。

背景：2026-10-22 给管线加票房字段时，collect 只重跑当前 discover 切片（60 部），
历史切片采的 332 部旧记录没被重新归一，票房全空——而它们的详情缓存里明明有数据
（392 部中 242 部的原始响应带 revenue）。本脚本离线复用原始缓存，只补两个新字段，
不动其他字段、不改变影片集合（避免引入无关 diff）。

用法：
    python scripts/backfill_revenue.py            # 回填并报告
    python scripts/backfill_revenue.py --dry-run  # 只看会改多少
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from ingest.sources.tmdb import normalize_movie  # noqa: E402

INTERIM = REPO / "data_lake" / "interim" / "tmdb_movies.jsonl"
RAW_DIR = REPO / "data_lake" / "raw" / "tmdb" / "movie"


def load_raw_revenue(tmdb_id: int) -> tuple[int | None, int | None]:
    """读原始详情缓存，取出 revenue/budget（美元，0/缺 → None）。"""
    f = RAW_DIR / f"{tmdb_id}.json"
    if not f.exists():
        return None, None
    try:
        resp = json.loads(f.read_text(encoding="utf-8")).get("_response") or {}
    except (json.JSONDecodeError, OSError):
        return None, None
    rev = resp.get("revenue") or 0
    bud = resp.get("budget") or 0
    return (int(rev) if rev > 0 else None), (int(bud) if bud > 0 else None)


def main() -> int:
    ap = argparse.ArgumentParser(description="从原始缓存回填票房/预算字段")
    ap.add_argument("--dry-run", action="store_true", help="只统计，不写文件")
    args = ap.parse_args()

    if not INTERIM.exists():
        print(f"找不到 {INTERIM}", file=sys.stderr)
        return 1

    rows = [json.loads(l) for l in INTERIM.read_text(encoding="utf-8").splitlines() if l.strip()]
    filled = missing_raw = already = 0
    for rec in rows:
        mid = rec.get("tmdb_id")
        if not mid:
            continue
        if rec.get("revenue"):
            already += 1
            continue
        rev, bud = load_raw_revenue(int(mid))
        if rev is None and bud is None:
            missing_raw += 1
            continue
        rec["revenue"] = rev
        rec["budget"] = bud
        filled += 1

    print(f"interim 共 {len(rows)} 行：已有票房 {already}，本次回填 {filled}，"
          f"缓存无票房数据 {missing_raw}")

    if args.dry_run:
        print("（dry-run，未写文件）")
        return 0

    # 原子写：先写临时文件再替换，避免半截文件污染管线
    tmp = INTERIM.with_suffix(".jsonl.tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        for rec in rows:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    tmp.replace(INTERIM)
    print(f"已写回 {INTERIM}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
