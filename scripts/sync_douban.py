"""独立豆瓣增量同步任务：采集 → 清洗 → 重建索引，可定时调用。

用法：
  python scripts/sync_douban.py
  python scripts/sync_douban.py --interval-hours 24
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def run(command: list[str]) -> None:
    subprocess.run(command, cwd=PROJECT_ROOT, check=True)


def append_comment_fields_to_es() -> tuple[int, int]:
    """把豆瓣短评、长评追加到对应 ES 电影文档。"""
    from common.es_client import close_sync_es, get_sync_es
    from common.settings import settings
    import json

    es = get_sync_es()
    grouped: dict[str, dict[str, list[str]]] = defaultdict(
        lambda: {"short": [], "long": []}
    )
    reviews_path = settings.lake("processed") / "reviews.jsonl"
    if not reviews_path.exists():
        return 0, 0

    with reviews_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("source") != "douban":
                continue
            movie_id = row.get("movie_id")
            text = str(row.get("text") or "").strip()
            if not movie_id or not text:
                continue
            bucket = "long" if row.get("review_type") == "long" else "short"
            if text not in grouped[movie_id][bucket]:
                grouped[movie_id][bucket].append(text)

    updated = 0
    failed = 0
    for movie_id, comments in grouped.items():
        short_comments = comments["short"][:20]
        long_comments = comments["long"][:10]
        all_comments = short_comments + long_comments
        try:
            es.update(
                index=settings.es_index_movies,
                id=movie_id,
                doc={
                    "douban_comments": all_comments,
                    "douban_short_comments": short_comments,
                    "douban_long_comments": long_comments,
                },
            )
            updated += 1
        except Exception:
            failed += 1
    close_sync_es()
    return updated, failed


def sync_once(limit: int | None) -> None:
    python = sys.executable
    command = [
        python, "-m", "ingest.run_collect", "douban",
        "--pages", "2",
        "--long-pages", "1",
        "--delay", "2.5",
    ]
    if limit:
        command += ["--limit", str(limit)]
    run(command)
    run([python, "-m", "transform.run_transform", "all"])
    run([python, "-m", "index.run_index", "build", "--recreate"])
    updated, failed = append_comment_fields_to_es()
    print(f"[豆瓣同步] 电影评论追加完成：成功 {updated} 部，失败 {failed} 部")


def main() -> int:
    parser = argparse.ArgumentParser(description="豆瓣数据独立增量同步")
    parser.add_argument("--once", action="store_true", help="只运行一次（默认）")
    parser.add_argument("--interval-hours", type=float, default=0,
                        help="定时间隔小时数；大于 0 时循环运行")
    parser.add_argument("--limit", type=int, default=0,
                        help="最多采集多少条短评/长评；0 表示不限")
    args = parser.parse_args()

    if args.interval_hours <= 0:
        sync_once(args.limit or None)
        return 0

    print(f"[豆瓣同步] 定时模式已启动，每 {args.interval_hours:g} 小时同步一次")
    while True:
        try:
            sync_once(args.limit or None)
        except Exception as exc:
            print(f"[豆瓣同步] 本轮失败：{type(exc).__name__}: {exc}", file=sys.stderr)
        time.sleep(args.interval_hours * 3600)


if __name__ == "__main__":
    raise SystemExit(main())
