"""
阶段 2 清洗融合入口（命令行）。

用法（在仓库根目录执行）：

    # 1. 电影融合：interim 各源 → processed/movies.jsonl（本层核心）
    python -m transform.run_transform movies

    # 2. 影评清洗 + 与电影弱关联：→ processed/reviews.jsonl
    python -m transform.run_transform reviews

    # 3. 一把跑完
    python -m transform.run_transform all

    # 4. 默认就只用真实采集产物（演示夹具常驻 data_lake/demo/，不在这个目录里）
    python -m transform.run_transform all

    # 4b. 离线演示/自检：显式把 data_lake/demo/ 里的 *.demo.jsonl 夹具带进来
    python -m transform.run_transform all --with-demo

    # 5. 先看看会读到什么、大概融合成多少部，**不写盘**
    python -m transform.run_transform movies --dry-run

    # 6. 调试：只取前 50 条输入
    python -m transform.run_transform movies --limit 50

参数：
    --from-dir    输入目录（默认 data_lake/interim）
    --out-dir     输出目录（默认 data_lake/processed）
    --with-demo   额外把 data_lake/demo/ 里的 *.demo.jsonl 演示夹具纳入融合
                  （默认排除 —— 2026-10-20 教训：demo 混进正式索引霸榜热门位）
    --no-demo     同默认（排除演示数据），仅为兼容旧命令保留
    --no-title-key  关闭「片名+年份」兜底键，只用 id 对齐
    --min-chars   影评清洗后短于此长度即丢弃（默认 20；豆瓣短评最低按 5 字）
    --limit       本次最多读入多少条（调试用）
    --force       允许较少/字段覆盖率更低的结果替换现有处理文件

产物：
    data_lake/processed/movies.jsonl      一部电影一条（多源已合并）
    data_lake/processed/reviews.jsonl     一篇影评一条（已清洗、已尝试关联）

★ 本命令不联网、不碰 ES，纯粹是「文件 → 文件」。
  所以它可以随时重跑、随便调参，不消耗任何 API 配额 ——
  这正是把融合层从采集层里拆出来的全部意义。
"""
from __future__ import annotations

import argparse
import sys
import tempfile
import time
from pathlib import Path

if __package__ in (None, ""):      # 允许 `python transform/run_transform.py`
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.meminfo import format_mem  # noqa: E402
from common.settings import settings  # noqa: E402
from ingest.jsonl_io import iter_jsonl, write_jsonl  # noqa: E402
from transform.movies import MovieMerger  # noqa: E402
from transform.reviews import (  # noqa: E402
    ReviewStats,
    build_title_index,
    iter_clean_reviews,
)


def _banner(title: str) -> None:
    print("\n" + "=" * 68)
    print(f"  {title}")
    print("=" * 68)


def _find_files(directory: Path, pattern: str, include_demo: bool) -> list[Path]:
    """找输入文件。

    默认（include_demo=False）只读 in_dir 里的真实采集产物，剔掉 *.demo.*。
    include_demo=True 时在 in_dir 基础上额外扫描 data_lake/demo/ —— 演示夹具的
    常驻目录，与 interim 平级，避免再被误当成正式数据（2026-10-20 污染事故根治）。
    兼容性：夹具若仍写在 in_dir 本地（离线测试的临时目录就是这么做的），照常纳入。
    """
    files = sorted(p for p in directory.glob(pattern) if p.is_file())
    if not include_demo:
        return [f for f in files if ".demo." not in f.name]
    demo_dir = directory.parent / "demo"
    if demo_dir.is_dir() and demo_dir.resolve() != directory.resolve():
        seen = {f.resolve() for f in files}
        files += [p for p in sorted(demo_dir.glob(pattern))
                  if p.is_file() and ".demo." in p.name and p.resolve() not in seen]
    return files


def _demo_notice(files: list[Path]) -> None:
    demo = [f.name for f in files if ".demo." in f.name]
    if demo:
        print(f"  ⚠ 输入里有 {len(demo)} 个**演示数据**（{', '.join(demo)}）——")
        print("    那是 --with-demo 显式带入的合成夹具，不是真实采集内容。")
        print("    正式融合请去掉 --with-demo 重跑。")


# ============================================================
# 电影融合
# ============================================================

def _move_stats(merger: MovieMerger) -> dict:
    """在写盘前扫一遍合并桶，统计融合质量。

    为什么要单独扫一遍？因为 results() 是生成器，边写盘边统计会让汇总数字
    出现在文件末尾之后 —— 人类读者要的是「先看到结论」。
    """
    buckets = merger.buckets.values()
    multi = sum(1 for b in buckets if len(b.get("_sources") or ()) > 1)
    return {"buckets": len(merger.buckets), "multi": multi}


def _movie_metadata_coverage(records: list[dict]) -> float:
    fields = ("release_year", "vote_average", "genres_zh", "director",
              "cast", "overview", "poster_url")
    total = len(records) * len(fields)
    if not total:
        return 0.0
    return sum(bool(record.get(field)) for record in records for field in fields) / total


def _jsonl_count(path: Path) -> int:
    return sum(1 for _ in iter_jsonl(path))


def run_movies(args) -> int:
    _banner("阶段 2 · 电影多源融合")
    t0 = time.time()

    in_dir = Path(args.from_dir) if args.from_dir else settings.lake("interim")
    out_dir = Path(args.out_dir) if args.out_dir else settings.lake("processed")
    files = _find_files(in_dir, "*movies*.jsonl", args.include_demo)

    if not files:
        print(f"\n  [中止] 在 {in_dir} 里没找到任何 *movies*.jsonl。")
        print("  提示：先跑采集命令产出 interim 记录，例如")
        print("        python -m ingest.run_collect seed")
        print("        python -m ingest.run_collect imdb --demo\n")
        return 1

    print(f"  输入目录   : {in_dir}")
    print(f"  输入文件   :")
    for f in files:
        print(f"      {f.name}")
    _demo_notice(files)
    if args.no_title_key:
        print("  对齐策略   : 只用 imdb_id / tmdb_id（已关闭片名兜底键）")
    else:
        print("  对齐策略   : imdb_id > tmdb_id > 片名+年份")

    # ---- 逐文件流式融合（不把原始记录攒进内存）----
    merger = MovieMerger(use_title_key=not args.no_title_key)
    per_file: dict[str, int] = {}
    total_in = 0
    stopped = False
    for f in files:
        cnt = 0
        for rec in iter_jsonl(f):
            if args.limit and total_in >= args.limit:
                stopped = True
                break
            merger.add(rec)
            cnt += 1
            total_in += 1
        per_file[f.name] = cnt
        if stopped:
            break

    print("-" * 68)
    for name, cnt in per_file.items():
        print(f"      {name:<32}{cnt:>7} 条")

    st = _move_stats(merger)
    print("-" * 68)
    print(f"  输入记录数    : {total_in:,}")
    print(f"  融合后电影数  : {st['buckets']:,}", end="")
    if st["buckets"]:
        print(f"      压缩比 {total_in / st['buckets']:.2f} : 1")
    else:
        print()
    print(f"  多源合并      : {st['multi']:,} 部（由 2 个以上源拼成）")
    print(f"  桥接合并      : {merger.bridges:,} 次"
          f"   ← 一条记录把原本分开的两组连接起来")
    if merger.keyless:
        print(f"  ⚠ 无主键孤儿  : {merger.keyless:,} 条"
              f"   ← 既没 id 也没「片名+年份」，采集端可能漏了字段")

    if not st["buckets"]:
        print("\n  [中止] 没有融合出任何电影，跳过写盘（不留空文件骗下游）。\n")
        return 1

    records = list(merger.results())
    out = out_dir / "movies.jsonl"
    if not args.dry_run and out.exists():
        existing = list(iter_jsonl(out))
        old_coverage = _movie_metadata_coverage(existing)
        new_coverage = _movie_metadata_coverage(records)
        if (len(records) < len(existing) and new_coverage < old_coverage
                and not getattr(args, "force", False)):
            print(
                f"\n  [中止] 新结果为 {len(records):,} 部，少于现有 {len(existing):,} 部，"
                "且基础字段覆盖率更低。为避免稀疏增量数据覆盖完整片库，"
                "原文件保持不变；确认要替换时请显式传入 --force。\n"
            )
            return 2
        if getattr(args, "force", False):
            print("  [警告] --force 已启用：允许覆盖现有电影处理文件。")

    # ---- 写盘 + 顺手统计字段覆盖率 ----
    acc = {"n": 0, "imdb": 0, "tmdb": 0, "zh": 0, "poster": 0,
           "rating": 0, "overview": 0, "place": 0, "multi": 0}
    years: list[int] = []

    def counting():
        for rec in records:
            acc["n"] += 1
            acc["imdb"] += bool(rec.get("imdb_id"))
            acc["tmdb"] += bool(rec.get("tmdb_id"))
            acc["zh"] += bool(rec.get("title_zh"))
            acc["poster"] += bool(rec.get("poster_url"))
            acc["rating"] += rec.get("vote_average") is not None
            acc["overview"] += bool(rec.get("overview"))
            acc["multi"] += bool(rec.get("is_multi_source"))
            acc["place"] += len(rec.get("locations_with_coords") or [])
            if rec.get("release_year"):
                years.append(rec["release_year"])
            yield rec

    if args.dry_run:
        # 空跑：只统计不落盘（上面 counting 是生成器，这里手动消费一次）
        for _ in counting():
            pass
        print(f"\n  [dry-run] 未写盘。若正式执行会输出到：{out}")
    else:
        write_jsonl(counting(), out)

    n = acc["n"]
    print("-" * 68)
    print(f"  输出记录数    : {n:,}")
    print(f"  含 imdb_id    : {acc['imdb']:,} ({acc['imdb'] / n:.0%})"
          f"   含 tmdb_id: {acc['tmdb']:,} ({acc['tmdb'] / n:.0%})")
    print(f"  含中文片名    : {acc['zh']:,} ({acc['zh'] / n:.0%})"
          f"   有海报: {acc['poster']:,} ({acc['poster'] / n:.0%})")
    print(f"  有评分        : {acc['rating']:,} ({acc['rating'] / n:.0%})"
          f"   有剧情简介: {acc['overview']:,} ({acc['overview'] / n:.0%})")
    print(f"  多源电影      : {acc['multi']:,}"
          f"   拍摄地(带坐标): {acc['place']:,} 处  → 阶段 6 足迹地图")
    if years:
        print(f"  年份区间      : {min(years)} ~ {max(years)}")
    if not args.dry_run:
        print(f"  输出文件      : {out}")
    print(f"  耗时          : {time.time() - t0:.1f}s")
    print(f"  {format_mem()}")
    print("=" * 68 + "\n")
    return 0


# ============================================================
# 影评清洗 + 关联
# ============================================================

def _load_index(args):
    """用已融合的 movies.jsonl 建标题索引；没有就先不做关联。"""
    out_dir = Path(args.out_dir) if args.out_dir else settings.lake("processed")
    path = out_dir / "movies.jsonl"
    if not path.exists():
        print(f"  [提示] 没找到 {path.name}，本次影评不做电影关联。")
        print("         想让影评关联到电影，先跑：python -m transform.run_transform movies")
        return None
    movies = list(iter_jsonl(path))          # 索引需要全量片名，这里必须读进内存
    index = build_title_index(movies)
    print(f"  标题索引   : {len(movies):,} 部电影 → "
          f"精确键 {len(index.exact):,} 个，唯一片名键 {len(index.loose):,} 个")
    return index


def run_reviews(args) -> int:
    _banner("阶段 2 · 影评清洗与弱关联")
    t0 = time.time()

    in_dir = Path(args.from_dir) if args.from_dir else settings.lake("interim")
    out_dir = Path(args.out_dir) if args.out_dir else settings.lake("processed")
    files = _find_files(in_dir, "reviews*.jsonl", args.include_demo)

    if not files:
        print(f"\n  [中止] 在 {in_dir} 里没找到任何 reviews*.jsonl。")
        print("  提示：先跑 `python -m ingest.run_collect kaggle` 产出影评。\n")
        return 1

    print(f"  输入目录   : {in_dir}")
    print(f"  输入文件   : " + "，".join(f.name for f in files))
    _demo_notice(files)
    print(f"  正文下限   : {args.min_chars} 字（清洗后）")

    index = _load_index(args)

    stats = ReviewStats()
    total = 0
    stopped = False

    def reading():
        nonlocal total, stopped
        for f in files:
            print(f"    [处理] {f.name}")
            for rec in iter_jsonl(f):
                if args.limit and total >= args.limit:
                    stopped = True
                    return
                total += 1
                yield rec

    out = out_dir / "reviews.jsonl"
    if args.dry_run:
        for _ in iter_clean_reviews(reading(), index=index,
                                    min_chars=args.min_chars, stats=stats):
            pass
        print(f"\n  [dry-run] 未写盘。若正式执行会输出到：{out}")
    else:
        out.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=out.parent, prefix=".reviews-transform-") as temp_dir:
            candidate = Path(temp_dir) / "reviews.jsonl"
            write_jsonl(
                iter_clean_reviews(reading(), index=index,
                                   min_chars=args.min_chars, stats=stats),
                candidate,
            )
            candidate_count = _jsonl_count(candidate)
            existing_count = _jsonl_count(out) if out.exists() else 0
            if (candidate_count < existing_count
                    and not getattr(args, "force", False)):
                print(
                    f"\n  [中止] 新结果为 {candidate_count:,} 条，少于现有 "
                    f"{existing_count:,} 条。原文件保持不变；确认要替换时"
                    "请显式传入 --force。\n"
                )
                return 2
            if getattr(args, "force", False):
                print("  [警告] --force 已启用：允许覆盖现有影评处理文件。")
            candidate.replace(out)

    print("-" * 68)
    print(f"  读入行数      : {stats.rows:,}")
    print(f"  写出记录数    : {stats.kept:,}")
    if stats.skipped:
        parts = []
        if stats.skipped_dupe:
            parts.append(f"重复 {stats.skipped_dupe:,}")
        if stats.skipped_short:
            parts.append(f"过短 {stats.skipped_short:,}")
        if stats.skipped_empty:
            parts.append(f"空正文 {stats.skipped_empty:,}")
        print("  跳过          : " + "，".join(parts))
    if stats.kept:
        print(f"  关联到电影    : {stats.matched:,} ({stats.matched / stats.kept:.1%})"
              f"   ← Kaggle 影评集没有电影 id，这是数据源本身的限制")
        detail = "，".join(f"{k} {v:,}" for k, v in stats.match_by.most_common())
        if detail:
            print(f"  关联方式      : {detail}")
    if stats.sentiment:
        total_s = sum(stats.sentiment.values()) or 1
        print("  情感分布      : " + "，".join(
            f"{k} {v:,}({v / total_s:.0%})"
            for k, v in stats.sentiment.most_common()
        ))
    if stats.lengths:
        L = sorted(stats.lengths)
        print(f"  正文字符数    : 最短 {L[0]}，中位 {L[len(L) // 2]}，"
              f"平均 {sum(L) / len(L):.0f}，最长 {L[-1]}")
    if not args.dry_run:
        print(f"  输出文件      : {out}")
    print(f"  耗时          : {time.time() - t0:.1f}s")
    print(f"  {format_mem()}")
    print("=" * 68 + "\n")
    return 0


# ============================================================
# CLI
# ============================================================

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m transform.run_transform",
        description="电影盒子 · 阶段 2 清洗融合（不联网、不碰 ES）",
    )
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--from-dir", default=None, help="输入目录（默认 data_lake/interim）")
    common.add_argument("--out-dir", default=None, help="输出目录（默认 data_lake/processed）")
    common.add_argument("--with-demo", dest="include_demo", action="store_true",
                        help="纳入 data_lake/demo/ 里的 *.demo.jsonl 演示夹具（默认排除）")
    common.add_argument("--no-demo", dest="include_demo", action="store_false",
                        help="排除演示数据（默认即排除，仅为兼容旧命令保留）")
    common.add_argument("--dry-run", action="store_true", help="只统计、不写盘")
    common.add_argument("--limit", type=int, default=None, help="最多读入多少条（调试用）")
    common.add_argument(
        "--force", action="store_true",
        help="允许用较少/字段覆盖率更低的结果替换现有处理文件",
    )
    common.set_defaults(include_demo=False)

    sub = p.add_subparsers(dest="command", required=True)

    s_m = sub.add_parser("movies", parents=[common], help="多源电影记录融合")
    s_m.add_argument("--no-title-key", action="store_true",
                     help="关闭「片名+年份」兜底键，只用 imdb_id / tmdb_id 对齐")
    s_m.set_defaults(func=run_movies)

    s_r = sub.add_parser("reviews", parents=[common], help="影评清洗 + 与电影弱关联")
    s_r.add_argument("--min-chars", type=int, default=20,
                     help="默认 20 字；豆瓣短评最低按 5 字，0=不丢")
    s_r.set_defaults(func=run_reviews)

    s_a = sub.add_parser("all", parents=[common], help="先融合电影，再处理影评")
    s_a.add_argument("--no-title-key", action="store_true", help="同 movies 子命令")
    s_a.add_argument("--min-chars", type=int, default=20, help="同 reviews 子命令")
    s_a.set_defaults(func=None)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "all":
        rc = run_movies(args)
        if rc != 0:
            return rc
        return run_reviews(args)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
