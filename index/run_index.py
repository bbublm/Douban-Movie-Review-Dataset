"""
阶段 2b 索引层入口（命令行）。

用法（在仓库根目录执行，先确保 ES 已启动：docker-compose up -d）：

    # 1. 建索引 + 导入（最常用；已有索引就增量覆盖，幂等可重跑）
    python -m index.run_index build

    # 2. 改了 mapping 之后重建：写新索引 → 导完 → 原子切换别名 → 删旧索引
    python -m index.run_index build --recreate

    # 3. 只导一个索引 / 只导前 1000 条（调试用）
    python -m index.run_index import movies
    python -m index.run_index import reviews --limit 1000

    # 4. 看索引现状（文档数 + 类型/情感分面）
    python -m index.run_index stats

    # 5. 检索冒烟测试：中文分词、分面聚合、影评检索三条链路
    python -m index.run_index check

    # 6. 删库重来（保留数据湖产物，只清 ES）
    python -m index.run_index drop --yes

参数：
    --only {movies,reviews,news}   只处理其中一个（默认 movies+reviews；news 单独跑）
    --recreate                重建模式：新索引 + 别名原子切换
    --keep-old                重建后保留旧索引不删（想留一份对照时用）
    --limit N                 每个索引最多导入 N 条
    --chunk N                 bulk 每批条数（默认 500，网络差可调小）
    --from-dir DIR            输入目录（默认 data_lake/processed）

★ 与 transform 层的分工：
    transform 是「文件 → 文件」，本层是「文件 → ES」。
    改融合规则不用重跑采集，改 mapping 不用重跑融合 —— 三层各自可独立重来。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from common.es_client import close_sync_es, get_sync_es
from common.meminfo import format_mem
from common.settings import settings
from index.builder import (
    bulk_import,
    drop_index,
    index_stats,
    prepare_target,
    smoke_check,
    swap_alias,
)
from index.mappings import detect_ik

KINDS = ("movies", "reviews", "news", "douban_nowplaying", "tmdb_videos")


def _index_alias(kind: str) -> str:
    if kind == "news":
        return settings.es_index_news
    if kind == "douban_nowplaying":
        return settings.es_index_douban_nowplaying
    if kind == "tmdb_videos":
        return settings.es_index_tmdb_videos
    return settings.es_index_movies if kind == "movies" else settings.es_index_reviews


def _print_header(title: str) -> None:
    print()
    print("=" * 68)
    print(f"  {title}")
    print("=" * 68)


# ============================================================
# 子命令：build / import
# ============================================================

def cmd_build(args: argparse.Namespace) -> int:
    es = get_sync_es()
    try:
        # 先探一次 ES 通不通，别等导了一半才报连接错误
        try:
            info = es.options(request_timeout=8).info()
            version = info["version"]["number"]
        except Exception as exc:  # noqa: BLE001
            print(f"\n[×] 连不上 Elasticsearch（{settings.es_hosts}）：{str(exc)[:200]}")
            print("    先执行：docker-compose up -d")
            return 1

        use_ik = detect_ik(es)
        kinds = [args.only] if args.only else list(KINDS)

        _print_header(f"电影盒子 · 索引构建（ES {version}）")
        print(f"  中文分词器 : {'IK（ik_max_word / ik_smart）' if use_ik else '内置 cjk（未装 IK 插件）'}")
        if not use_ik:
            print("              提示：docker exec yjzs-es bin/elasticsearch-plugin install \\")
            print("                    https://get.infini.cloud/elasticsearch/analysis-ik/8.15.3")
            print("                    装完 docker restart yjzs-es 即可生效")
        print(f"  模式       : {'重建（别名原子切换）' if args.recreate else '增量（幂等覆盖）'}")
        print(f"  输入目录   : {args.from_dir}")
        print("-" * 68)

        total = {"ok": 0, "failed": 0}
        for kind in kinds:
            alias = _index_alias(kind)
            src = Path(args.from_dir) / f"{kind}.jsonl"
            # news 是单源数据，终态落在 interim/news.jsonl（不经过跨源 transform 合并）
            if not src.exists() and kind == "news":
                interim_src = settings.lake("interim", "news.jsonl")
                if interim_src.exists():
                    src = interim_src
            # douban_nowplaying 同理：阶段 1f 采集后落在 interim，不经 processed 合并
            if not src.exists() and kind == "douban_nowplaying":
                interim_src = settings.lake("interim", "douban_nowplaying.jsonl")
                if interim_src.exists():
                    src = interim_src
            # tmdb_videos 同理：阶段 1g 采集后落在 interim，不经 processed 合并
            if not src.exists() and kind == "tmdb_videos":
                interim_src = settings.lake("interim", "tmdb_videos.jsonl")
                if interim_src.exists():
                    src = interim_src
            if not src.exists():
                print(f"\n  [!] 跳过 {kind}：找不到 {src}")
                if kind == "news":
                    print(f"      先执行：python -m ingest.run_collect rss")
                elif kind == "douban_nowplaying":
                    print(f"      先执行：python -m ingest.run_collect douban")
                else:
                    print(f"      先执行：python -m transform.run_transform {kind}")
                continue

            write_index, old = prepare_target(
                es, alias, kind, use_ik=use_ik, recreate=args.recreate,
            )
            print(f"\n  [{kind}] 写入索引 {write_index}"
                  + (f"（旧：{old}）" if old else ""))
            print(f"         来源 {src.name}")

            stats = bulk_import(
                es, src, write_index, kind,
                limit=args.limit, chunk_size=args.chunk, quiet=args.quiet,
            )
            total["ok"] += stats["ok"]
            total["failed"] += stats["failed"]

            print(f"         导入 {stats['ok']:,} 条"
                  + (f"，失败 {stats['failed']:,}" if stats["failed"] else "")
                  + f"，耗时 {stats['seconds']}s")

            if stats["errors"]:
                print("         前几条错误：")
                for err in stats["errors"]:
                    print(f"           - {err}")

            # 重建模式：导完才切别名，切换前旧索引一直在正常服务
            if args.recreate:
                swap_alias(es, write_index, alias, remove=old)
                print(f"         别名 {alias} → {write_index}（已原子切换）")
                for name in old:
                    if args.keep_old:
                        print(f"         保留旧索引 {name}")
                    elif drop_index(es, name):
                        print(f"         已删除旧索引 {name}")

        _print_header("构建完成")
        print(f"  成功 {total['ok']:,} 条，失败 {total['failed']:,} 条")
        print(f"  {format_mem()}")
        return 0 if total["failed"] == 0 else 2
    finally:
        close_sync_es()


# ============================================================
# 子命令：stats / check / drop
# ============================================================

def cmd_stats(args: argparse.Namespace) -> int:
    es = get_sync_es()
    try:
        _print_header("索引现状")
        kinds = [args.only] if args.only else list(KINDS)
        for kind in kinds:
            alias = _index_alias(kind)
            info = index_stats(es, alias, kind)
            print(f"\n  [{kind}] 索引名 {alias}")
            if "error" in info:
                print(f"         {info['error']}")
                continue
            print(f"         文档数 {info['docs']:,}")
            label = ("类型分布" if kind == "movies"
                     else "情感分布" if kind == "reviews" else "媒体分布")
            if info.get("facets"):
                print(f"         {label}：" + "、".join(
                    f"{k}({v:,})" for k, v in info["facets"]))
            if info.get("facet_error"):
                print(f"         分面查询失败：{info['facet_error']}")
        print()
        return 0
    finally:
        close_sync_es()


def cmd_check(args: argparse.Namespace) -> int:
    es = get_sync_es()
    try:
        _print_header("检索冒烟测试")
        rows = smoke_check(es)
        ok = 0
        for name, passed, detail in rows:
            print(f"  [{'√' if passed else '×'}] {name:<22} {detail}")
            ok += bool(passed)
        print("-" * 68)
        print(f"  {ok}/{len(rows)} 项通过")
        if ok < len(rows):
            print("  提示：索引里可能还没数据，先跑 python -m index.run_index build")
        print()
        return 0 if ok == len(rows) else 1
    finally:
        close_sync_es()


def cmd_drop(args: argparse.Namespace) -> int:
    es = get_sync_es()
    try:
        if not args.yes:
            print("\n  这是危险操作，会删掉 ES 里的全部索引（数据湖产物不受影响）。")
            print("  确认请加 --yes：python -m index.run_index drop --yes\n")
            return 1
        removed = 0
        for kind in KINDS:
            alias = _index_alias(kind)
            for name in _all_indices_of(es, alias):
                if drop_index(es, name):
                    print(f"  已删除 {name}")
                    removed += 1
        print(f"\n  共删除 {removed} 个索引。数据湖产物仍在 data_lake/processed/。\n")
        return 0
    finally:
        close_sync_es()


def _all_indices_of(es, alias: str) -> list[str]:
    """列出别名指向的索引 + 同名裸索引。"""
    names: list[str] = []
    try:
        names += list(es.options(request_timeout=10).indices.get_alias(name=alias).keys())
    except Exception:  # noqa: BLE001
        pass
    try:
        if es.options(request_timeout=10).indices.exists(index=alias):
            names.append(alias)
    except Exception:  # noqa: BLE001
        pass
    return sorted(set(names))


# ============================================================
# argparse
# ============================================================

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m index.run_index",
        description="电影盒子 · ES 索引构建与导入",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    default_dir = str(settings.lake("processed"))

    def add_common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--only", choices=KINDS, help="只处理指定索引")
        p.add_argument("--from-dir", default=default_dir, help="输入目录")
        p.add_argument("--limit", type=int, default=None, help="每个索引最多导入多少条")
        p.add_argument("--chunk", type=int, default=500, help="bulk 每批条数")
        p.add_argument("--recreate", action="store_true", help="重建模式（别名原子切换）")
        p.add_argument("--keep-old", action="store_true", help="重建后保留旧索引")
        p.add_argument("--quiet", action="store_true", help="不打进度")

    p_build = sub.add_parser("build", help="建索引并导入")
    add_common(p_build)
    p_build.set_defaults(func=cmd_build)

    p_import = sub.add_parser("import", help="导入到已有索引（不存在则创建）")
    add_common(p_import)
    p_import.set_defaults(func=cmd_build)

    p_stats = sub.add_parser("stats", help="查看索引文档数与分面")
    p_stats.add_argument("--only", choices=KINDS)
    p_stats.set_defaults(func=cmd_stats)

    p_check = sub.add_parser("check", help="检索冒烟测试")
    p_check.set_defaults(func=cmd_check)

    p_drop = sub.add_parser("drop", help="删除索引")
    p_drop.add_argument("--yes", action="store_true", help="确认删除")
    p_drop.set_defaults(func=cmd_drop)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
