"""
阶段 1 采集入口（命令行）。

用法（在仓库根目录执行）：
    # ---- 阶段 1a：TMDB ----
    # 1. 先把旧系统的 120 部片库并进来（纯本地，不联网）
    python -m ingest.run_collect seed

    # 2. 再用 TMDB 给种子片库补 tmdb_id / 海报 / 评分（联网，按条数控制配额）
    python -m ingest.run_collect seed --resolve --limit 30

    # 3. TMDB 发现式采集（按热度拉取新片）
    python -m ingest.run_collect tmdb --pages 3 --limit 60

    # ---- 阶段 1b：IMDb Datasets ----
    # 4. 看数据集清单（不下载，只提示体积）
    python -m ingest.run_collect imdb --list

    # 5. 下载必要数据集并采集（默认只下 ratings + basics，约 200 MB）
    python -m ingest.run_collect imdb --download --min-votes 1000

    # 6. 演示用小样本（票数最高的 2 万部），并且额外补导演名
    python -m ingest.run_collect imdb --limit 20000 --with-directors

    # 参数：
    #   --force      忽略 raw 缓存 / 强制重新下载
    #   --proxy      覆盖代理策略（留空=跟随系统；direct=直连；或填 http://host:port）
    #   --sort       popularity | rating | release（TMDB 发现排序）
    #   --dir        数据集所在目录（配合已手动下载好的 tsv.gz）

    # ---- 阶段 1c：Wikidata + Wikipedia ----
    # 7. 看会从哪些文件里取主键（不联网）
    python -m ingest.run_collect wiki --list

    # 8. 离线跑通链路（用固件，不联网、不等 SPARQL）
    python -m ingest.run_collect wiki --demo

    # 9. 真实采集：从 interim 里已有的记录取主键，补中文名/导演/摘要/拍摄地坐标
    python -m ingest.run_collect wiki

    # 10. 只要 Wikidata，不要维基摘要（省一半请求）
    python -m ingest.run_collect wiki --no-wikipedia

    # 参数：
    #   --force      忽略 raw 缓存，强制重新请求
    #   --proxy      覆盖代理策略（留空=跟随系统；direct=直连；或填 http://host:port）
    #   --sort       popularity | rating | release（TMDB 发现排序）
    #   --dir        数据集所在目录（配合已手动下载好的 tsv.gz）

    # ---- 阶段 1e：Kaggle 公开影评 ----
    # 11. 看有哪些影评数据集可选（不下载）
    python -m ingest.run_collect kaggle --list

    # 12. 离线跑通链路（造一份合成影评，不下 66 MB）
    python -m ingest.run_collect kaggle --demo

    # 13. 真实采集（首次自动下载约 66 MB，公开数据集可匿名下载）
    python -m ingest.run_collect kaggle

    # 14. 只要前 5000 条、丢掉 20 字以下的短评、并把 1/0 标签翻转
    python -m ingest.run_collect kaggle --limit 5000 --min-chars 20 --swap-labels

    # 参数：
    #   --dataset    预置数据集 key（imdb50k / rotten / imdb_mirror）
    #   --handle     直接给 Kaggle handle，如 owner/dataset-name
    #   --dir        用本地已下载好的目录（不联网）
    #   --no-download  只解析本地已有文件，缺失就报错

    # ---- 阶段 1f：豆瓣短评（每片最近 100 + 最热 150；增量补齐，保存到 reviews 索引）----
    python -m ingest.run_collect douban --no-ratings --no-nowplaying

    # ---- 本地豆瓣评论数据集（只读 CSV，不访问网络）----
    python -m ingest.run_collect douban-dataset

产物：
    data_lake/raw/tmdb/**                     原始响应（断点续跑靠它）
    data_lake/raw/wikidata/{core,geo}/*.json  SPARQL 原始响应
    data_lake/raw/wikipedia/extract/*.json    维基摘要原始响应
    data_lake/interim/seed_movies.jsonl       旧片库统一结构
    data_lake/interim/tmdb_movies.jsonl       TMDB 采集结果
    data_lake/interim/imdb_movies.jsonl       IMDb 采集结果
    data_lake/interim/wiki_movies.jsonl       Wikidata + Wikipedia 采集结果
    data_lake/interim/reviews.jsonl           Kaggle 影评采集结果
    data_lake/imdb_datasets/*.tsv.gz          IMDb 官方数据集（压缩包，不解压）
    data_lake/kaggle_reviews/<handle>/        Kaggle 数据集原始文件

内存说明（重要）：
    imdb 与 kaggle 子命令全程流式解析，峰值内存与数据集行数无关。
    命令结束会打印「峰值内存」一行，可以自己核对。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import tempfile
import time
from pathlib import Path

# 允许 `python ingest/run_collect.py` 这种直接执行方式
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from common.meminfo import format_mem  # noqa: E402
from common.settings import PROJECT_ROOT, settings  # noqa: E402
from ingest import wiki as wiki_mod  # noqa: E402
from ingest.http import CollectorHttpError  # noqa: E402
from ingest.jsonl_io import iter_jsonl, write_jsonl  # noqa: E402
from ingest.schema import validate_review_full  # noqa: E402
from ingest.seed import load_legacy_movies, normalize_legacy, resolve_ids  # noqa: E402
from ingest.sources import imdb_datasets as imdb_mod  # noqa: E402
from ingest.sources import kaggle_reviews as kaggle_mod  # noqa: E402
from ingest.sources import tmdb as tmdb_mod  # noqa: E402
from ingest.sources import rss as rss_mod  # noqa: E402
from ingest.sources import wikidata as wd_mod  # noqa: E402
from ingest.sources import wikipedia as wp_mod  # noqa: E402
from ingest.sources.tmdb import TmdbCollector  # noqa: E402
from ingest.sources import letterboxd as lb_mod  # noqa: E402
from ingest.sources import metacritic as mc_mod  # noqa: E402
from ingest.sources import chinese_dataset as cn_mod  # noqa: E402
from ingest.sources import douban as douban_mod  # noqa: E402
from ingest.sources import douban_review_dataset as douban_dataset_mod  # noqa: E402

# 阶段 1c 的 --demo 直接复用离线自检用的固件（真实响应结构），
# 这样「不联网跑通链路」与「自动化自检」用的是同一份数据，不会两头漂移。
WIKI_FIXTURES = PROJECT_ROOT / "tests" / "fixtures"
# 默认从这些 interim 文件里抽取主键；按顺序找，文件不存在就跳过
DEFAULT_WIKI_INPUTS = ("tmdb_movies.jsonl", "imdb_movies.jsonl", "seed_movies.jsonl")

SORT_CHOICES = {
    "popularity": "popularity.desc",
    "rating": "vote_average.desc",
    "release": "primary_release_date.desc",
    "revenue": "revenue.desc",
}


def _demo_out_dir(args):
    """演示产出落 data_lake/demo/（与 interim 平级），与真实数据双向隔离。

    2026-10-20 事故复盘：demo 夹具曾被 transform 默认融合进正式索引，
    假评分 9.9 霸榜「大家都在看」。根治方案是两端同时隔离：
      · 采集端（本函数）：--demo 产出写 demo/，不进 interim；
      · 融合端（transform/run_transform.py）：默认排除 demo，--with-demo 才从 demo/ 读。
    """
    return settings.lake("demo") if getattr(args, "demo", False) else settings.lake("interim")


def _banner(title: str) -> None:
    print("\n" + "=" * 68)
    print(f"  {title}")
    print("=" * 68)


def _summary(records: list[dict], out_path: Path, elapsed: float) -> None:
    with_id = sum(1 for r in records if r.get("tmdb_id"))
    with_imdb = sum(1 for r in records if r.get("imdb_id"))
    with_poster = sum(1 for r in records if r.get("poster_url"))
    zh = sum(1 for r in records if r.get("title_zh"))
    years = [r["release_year"] for r in records if r.get("release_year")]
    genres: dict[str, int] = {}
    for r in records:
        for g in r.get("genres_zh") or []:
            genres[g] = genres.get(g, 0) + 1
    top_genres = sorted(genres.items(), key=lambda kv: -kv[1])[:6]

    print("-" * 68)
    print(f"  记录数        : {len(records)}")
    print(f"  含 tmdb_id    : {with_id}   含 imdb_id: {with_imdb}   有海报: {with_poster}")
    print(f"  含中文片名    : {zh}")
    if years:
        print(f"  年份区间      : {min(years)} ~ {max(years)}")
    if top_genres:
        print(f"  类型 Top6     : " + "，".join(f"{g}({c})" for g, c in top_genres))
    print(f"  输出文件      : {out_path}")
    print(f"  耗时          : {elapsed:.1f}s")
    print("=" * 68 + "\n")


# ---------------- 子命令 ----------------


def cmd_seed(args: argparse.Namespace) -> int:
    _banner("阶段 1a · 复用旧系统片库（data/web_movies.json）")
    t0 = time.time()

    legacy = load_legacy_movies()
    if not legacy:
        return 1
    records = [normalize_legacy(m) for m in legacy]
    print(f"  已转换为统一结构：{len(records)} 条")

    if args.resolve:
        _banner("用 TMDB 反查缺失的 tmdb_id（联网）")
        with TmdbCollector(force=args.force, proxy=args.proxy) as collector:
            records = resolve_ids(
                collector, records, limit=args.limit, with_detail=not args.no_detail
            )
            print(f"  API 调用 {collector.stats['api_calls']} 次，"
                  f"命中缓存 {collector.stats['cache_hits']} 次")
    elif args.limit:
        print("  提示：--limit 只在配合 --resolve 时生效")

    out = settings.lake("interim") / "seed_movies.jsonl"
    n = tmdb_mod.write_jsonl(records, out)
    _summary(records, out, time.time() - t0)
    print(f"  写出 {n} 行")
    return 0


def cmd_tmdb(args: argparse.Namespace) -> int:
    _banner("阶段 1a · TMDB 发现式采集")
    t0 = time.time()
    sort_by = SORT_CHOICES.get(args.sort, SORT_CHOICES["popularity"])

    print(f"  排序方式 : {sort_by}")
    print(f"  发现页数 : {args.pages}  上限条数 : {args.limit or '不限'}")
    print(f"  代理策略 : {args.proxy or settings.collector_proxy or '跟随系统'}")
    print(f"  原始落盘 : {settings.lake('raw', 'tmdb')}\n")

    with TmdbCollector(force=args.force, proxy=args.proxy) as collector:
        records = collector.collect(
            pages=args.pages,
            limit=args.limit,
            sort_by=sort_by,
            year_from=args.year_from,
            year_to=args.year_to,
        )
        print(f"\n  API 调用 {collector.stats['api_calls']} 次，"
              f"命中缓存 {collector.stats['cache_hits']} 次")

    out = settings.lake("interim") / "tmdb_movies.jsonl"

    # 增量合并：用不同切片（热门/高分/最新）多次采集应当**累加**，
    # 不是后一次覆盖前一次——阶段 7 扩充片库时真实踩过：
    # 连跑三个切片，最后一个把前两个冲掉，白采 320 部。
    # 合并键与 transform/keys.py 的主键思路一致：imdb_id → tmdb_id → 片名。

    def _key(rec: dict) -> str:
        return (rec.get("imdb_id") or "").strip() \
            or (f"tmdb-{rec.get('tmdb_id')}" if rec.get("tmdb_id") else "") \
            or (rec.get("title") or "").strip()

    merged: dict[str, dict] = {}
    if out.exists():
        for old in iter_jsonl(out):
            if _key(old):
                merged[_key(old)] = old
    before = len(merged)
    for rec in records:
        if _key(rec):
            merged[_key(rec)] = rec

    n = tmdb_mod.write_jsonl(merged.values(), out)
    _summary(list(merged.values()), out, time.time() - t0)
    print(f"  写出 {n} 行（本次新增 {len(merged) - before}，历史累计 {n}）")
    return 0


def cmd_tmdb_reviews(args: argparse.Namespace) -> int:
    """方案 #2：TMDB 影评采集 —— 复用已采集的电影清单，逐片拉 /movie/{id}/reviews。"""
    _banner("方案 #2 · TMDB 影评采集")
    t0 = time.time()

    movies_file = Path(args.movies_file)
    if not movies_file.is_absolute():
        movies_file = settings.lake("interim") / movies_file
    max_pages = args.max_pages

    # 1) 准备电影清单：优先读取既有 interim 电影文件，否则现场发现
    if movies_file.exists() and not args.rediscover:
        movies = [m for m in iter_jsonl(movies_file)]
        print(f"  电影清单 : 复用 {movies_file.name}（{len(movies)} 部）")
    else:
        if movies_file.exists() and args.rediscover:
            print(f"  [--rediscover] 忽略 {movies_file.name}，重新发现")
        with TmdbCollector(force=args.force, proxy=args.proxy) as c:
            movies = c.collect(limit=args.limit, progress=True)
        print(f"  电影清单 : 现场发现 {len(movies)} 部")

    if not movies:
        print("  [警告] 没有可用电影清单，退出")
        return 0

    # 2) 拉影评（复用电影详情的 raw 缓存，省配额）
    with TmdbCollector(force=args.force, proxy=args.proxy) as collector:
        records = collector.collect_reviews(movies, max_pages=max_pages)
        print(f"\n  API 调用 {collector.stats['api_calls']} 次，"
              f"命中缓存 {collector.stats['cache_hits']} 次")

    # 3) 增量合并到统一影评 interim（按 review_id 幂等累加）
    out = settings.lake("interim") / "reviews.tmdb.jsonl"

    def _rkey(r: dict) -> str:
        return r.get("external_id") or r.get("review_id") or ""

    merged: dict[str, dict] = {}
    if out.exists():
        for old in iter_jsonl(out):
            if _rkey(old):
                merged[_rkey(old)] = old
    before = len(merged)
    for r in records:
        if _rkey(r):
            merged[_rkey(r)] = r

    # 合同自检：核心字段必齐（strict 会抛错暴露脏数据）
    for r in merged.values():
        validate_review_full(r, strict=True)

    n = write_jsonl(merged.values(), out)
    _summary(list(merged.values()), out, time.time() - t0)
    print(f"  写出 {n} 条影评（本次新增 {len(merged) - before}，历史累计 {n}）")
    return 0


def cmd_rss(args: argparse.Namespace) -> int:
    """方案 #4：RSS 影视新闻采集 —— 公开 feed，条件 GET 节流，舆情时间线素材。"""
    _banner("方案 #4 · RSS 影视新闻采集")
    t0 = time.time()

    feeds = None
    if args.feeds:
        feeds = [
            (p.split("|", 1)[0].strip(), p.split("|", 1)[1].strip())
            for p in args.feeds.split(";") if "|" in p
        ]
    print(f"  Feed 数 : {len(feeds) if feeds else '默认配置'}")
    print(f"  节流间隔 : {args.min_interval or settings.rss_min_interval}s（相邻 feed）")
    print(f"  原始落盘 : {settings.lake('raw', 'rss')}\n")

    collector = rss_mod.RssCollector(min_interval=args.min_interval, proxy=args.proxy, feeds=feeds)
    records = collector.collect()

    # 增量合并：按 article_id(sha1 link) 幂等累加，重跑不重复
    out = settings.lake("interim") / "news.jsonl"

    def _nkey(r: dict) -> str:
        return r.get("article_id") or ""

    merged: dict[str, dict] = {}
    if out.exists():
        for old in iter_jsonl(out):
            if _nkey(old):
                merged[_nkey(old)] = old
    before = len(merged)
    for r in records:
        if _nkey(r):
            merged[_nkey(r)] = r

    n = rss_mod.write_jsonl(list(merged.values()), out)
    _summary(list(merged.values()), out, time.time() - t0)
    print(f"  写出 {n} 条新闻（本次新增 {len(merged) - before}，历史累计 {n}）")
    print(f"  统计：feeds={collector.stats['feeds']} entries={collector.stats['entries']} "
          f"304跳过={collector.stats['skipped_304']} 错误={collector.stats['errors']}")
    return 0


def cmd_imdb(args: argparse.Namespace) -> int:
    """阶段 1b：IMDb Datasets 采集（两遍流式扫描，内存恒定）。"""
    _banner("阶段 1b · IMDb Datasets 采集")

    # --types 是逗号分隔字符串，转成集合方便判断
    type_set = {t.strip() for t in (args.types or "").split(",") if t.strip()}

    # ---- --list：只列清单，不下载 ----
    if args.list:
        print("  IMDb 官方公开数据集（https://datasets.imdbws.com/）\n")
        print(f"  {'key':<12}{'文件':<28}{'体积':>9}  说明")
        print("  " + "-" * 74)
        for spec in imdb_mod.DATASETS.values():
            flag = "必下" if spec.required else "可选"
            print(f"  {spec.key:<12}{spec.filename:<28}{spec.size_mb:>6} MB  [{flag}] {spec.note}")
        print("\n  说明：本项目全程流式读 .tsv.gz，不落地解压，除压缩包外不占额外磁盘。")
        print("        默认只下 ratings + basics（约 200 MB），其余按需 --files 指定。\n")
        return 0

    directory = imdb_mod.dataset_dir(args.dir)
    if args.demo and not args.dir:
        # 演示数据单独放一个目录，避免下次真实采集「命中」到合成数据 —— 这是个隐患
        directory = settings.lake("imdb_datasets_demo")
    print(f"  数据集目录 : {directory}")
    print(f"  筛选条件   : 票数≥{args.min_votes}  评分≥{args.min_rating}  "
          f"类型={sorted(type_set)}")
    print(f"  条数上限   : {args.limit or '不限'}"
          + ("（按票数取最高的若干部）" if args.limit else ""))
    print(f"  代理策略   : {args.proxy or settings.collector_proxy or '跟随系统'}\n")

    t0 = time.time()
    paths: dict[str, Path] = {}

    # ---- 0) 演示模式：造一份合成小数据集，不联网不下载也能跑通全链路 ----
    if args.demo:
        print("  [演示模式] 生成合成示例数据集（非真实 IMDb 数据，仅供离线跑通链路）")
        built = imdb_mod.build_demo_datasets(directory)
        for v in built.values():
            print(f"    {v.name:<26}{v.stat().st_size / 1024:>8.0f} KB")
        print("    提示：要换成真实数据，删掉这些文件后执行 `imdb --download`\n")
        paths = dict(built)
        if not args.with_directors:
            paths.pop("crew", None)
            paths.pop("names", None)

    # ---- 1) 确保数据集就位（缺失且给了 --download 才下载；否则给出可读提示）----
    if not paths:
        wanted = ["ratings", "basics"]
        if args.with_directors:
            wanted += ["crew", "names"]
        if args.files:
            wanted = [f.strip() for f in args.files.split(",") if f.strip()]

        for key in wanted:
            if key not in imdb_mod.DATASETS:
                print(f"  [跳过] 未知数据集 key：{key}（可选 {list(imdb_mod.DATASETS)}）")
                continue
            found = imdb_mod.find_dataset(key, directory)
            if found and not args.force:
                print(f"  [命中] {found.name}（{found.stat().st_size / 1024 / 1024:.1f} MB）")
                paths[key] = found
                continue
            if not args.download:
                spec = imdb_mod.DATASETS[key]
                print(f"  [缺失] {spec.filename}（约 {spec.size_mb} MB）")
                print(f"         下载地址：{spec.url}")
                if key in ("ratings", "basics"):
                    print("         或加 --download 由脚本代下；"
                          "也可手动下载后放进上面那个目录，再加 --dir 指定")
                continue
            try:
                paths[key] = imdb_mod.download_dataset(
                    key, directory, force=args.force, proxy=args.proxy
                )
            except RuntimeError as exc:
                print(f"\n  [下载失败] {exc}\n")
                return 2

    missing_required = [k for k in ("ratings", "basics") if k not in paths]
    if missing_required:
        print(f"\n  [中止] 缺少必要数据集：{missing_required}")
        print("  提示：以下任一方式都行 ——")
        print("        1) 离线先跑通链路：python -m ingest.run_collect imdb --demo")
        print("        2) 让脚本下载：    python -m ingest.run_collect imdb --download")
        print("        3) 自己下载后放进数据集目录，再加 --dir 指定目录\n")
        return 1

    # ---- 2) 第 1 遍：扫 ratings，建「值得保留」索引 ----
    print(f"\n  [1/2] 扫描评分表（流式，内存恒定）…")
    rating_index = imdb_mod.load_rating_index(
        paths["ratings"],
        min_votes=args.min_votes,
        min_rating=args.min_rating,
        top_n=args.limit,
    )
    print(f"        入选影片 {len(rating_index):,} 部")

    # ---- 3) 第 2 遍：扫 basics，命中即写盘 ----
    print(f"  [2/2] 扫描影片表并写盘 …")
    out_name = "imdb_movies.demo.jsonl" if args.demo else "imdb_movies.jsonl"
    out = _demo_out_dir(args) / out_name
    stream = imdb_mod.collect(
        paths["basics"],
        rating_index,
        title_types=type_set,
        exclude_adult=not args.include_adult,
        limit=args.limit,
    )
    n = imdb_mod.write_jsonl_stream(stream, out)
    print(f"        写出 {n:,} 条 → {out}")

    # ---- 4) 可选：补导演 ----
    filled = 0
    if args.with_directors and "crew" in paths and "names" in paths:
        print("  [可选] 用 crew + names 补导演名 …")
        filled = imdb_mod.enrich_directors(out, paths["crew"], paths["names"])
        print(f"        补上导演 {filled:,} 条")

    # ---- 5) 汇总 ----
    years: list[int] = []
    vote_sum = 0
    with out.open(encoding="utf-8") as fh:
        for line in fh:
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            if rec.get("release_year"):
                years.append(rec["release_year"])
            vote_sum += int(rec.get("vote_count") or 0)

    print("-" * 68)
    print(f"  输出文件    : {out}")
    print(f"  记录数      : {n:,}")
    if years:
        print(f"  年份区间    : {min(years)} ~ {max(years)}")
    if n:
        print(f"  平均票数    : {vote_sum / n:,.0f}")
    if filled:
        print(f"  含导演      : {filled:,}")
    print(f"  耗时        : {time.time() - t0:.1f}s")
    print(f"  {format_mem()}   ← 流式解析，与数据集行数无关")
    print("=" * 68 + "\n")
    return 0


def _wiki_input_records(names: tuple[str, ...]) -> tuple[list[dict], list[str]]:
    """从 interim 里读已有记录，用来决定「要补哪些电影」。

    返回 (记录列表, 实际读到的文件名列表)。
    """
    records: list[dict] = []
    used: list[str] = []
    for name in names:
        path = settings.lake("interim") / name
        if not path.exists():
            continue
        used.append(name)
        records.extend(wiki_mod.iter_jsonl(path))
    return records, used


def cmd_wiki(args: argparse.Namespace) -> int:
    """阶段 1c：Wikidata SPARQL + Wikipedia API 采集（补中文名/导演/摘要/拍摄地坐标）。"""
    _banner("阶段 1c · Wikidata SPARQL + Wikipedia API 采集")
    t0 = time.time()

    names = tuple(
        n.strip() for n in (args.from_files or "").split(",") if n.strip()
    ) or DEFAULT_WIKI_INPUTS
    inputs, used = _wiki_input_records(names)

    # ---- --list：只说明会读哪些文件、能补多少，不联网 ----
    if args.list:
        print("  输入来源（data_lake/interim/）：")
        for name in names:
            path = settings.lake("interim") / name
            mark = f"{'✓ 已就绪' if path.exists() else '✗ 不存在'}"
            print(f"    {name:<26}{mark}")
        pairs_preview = wd_mod.key_pairs(inputs)
        print(f"\n  汇总可查询主键：{len(pairs_preview)} 个"
              f"（含 imdb_id 优先，其余用 tmdb_id 兜底）")
        print(f"  预计 SPARQL 请求：{-(-len(pairs_preview) // settings.wikidata_batch)} 批"
              f"（每批 {settings.wikidata_batch} 个主键，core + geo 各一轮）")
        print("\n  说明：Wikidata 补中文名/导演/类型/出品国/公映日期/片长/拍摄地坐标，")
        print("        Wikipedia 补剧情摘要（阶段 4 情感与主题分析的语料来源）。\n")
        return 0

    print(f"  输入来源   : {', '.join(used) if used else '（无，改走演示模式）'}"
          f"  共 {len(inputs)} 条记录")
    print(f"  代理策略   : {args.proxy or settings.collector_proxy or '跟随系统'}")
    print(f"  维基摘要   : {'跳过（--no-wikipedia）' if args.no_wikipedia else '采集'}")

    # ---- 0) 演示模式：用固件跑通全链路，不联网 ----
    if args.demo:
        print("  [演示模式] 使用 tests/fixtures 里的真实响应固件，不联网\n")
        core = wd_mod.aggregate_core(
            wd_mod.parse_rows(json.loads((WIKI_FIXTURES / "wikidata_core.json").read_text("utf-8")))
        )
        geo = wd_mod.aggregate_geo(
            wd_mod.parse_rows(json.loads((WIKI_FIXTURES / "wikidata_geo.json").read_text("utf-8")))
        )
        summaries = wp_mod.parse_wikipedia_payload(
            json.loads((WIKI_FIXTURES / "wikipedia_extract.json").read_text("utf-8"))
        )
        print(f"    Wikidata 命中 {len(core)} 部，拍摄地 {sum(len(v) for v in geo.values())} 处，"
              f"维基摘要 {len(summaries)} 条")
    else:
        pairs = wd_mod.key_pairs(inputs)
        if not pairs:
            print("\n  [中止] 没有可用的主键。")
            print("  提示：先跑 `seed` / `tmdb` / `imdb` 任意一个采集命令产出 interim 记录，")
            print("        或加 --demo 用固件跑通链路。\n")
            return 1
        if args.limit:
            pairs = pairs[: args.limit]
            print(f"  条数上限   : {args.limit} 个主键")

        print(f"  待查主键   : {len(pairs)} 个"
              f"（分 {-(-len(pairs) // args.batch)} 批，每批 {args.batch} 个）\n")

        with wd_mod.WikidataCollector(
            batch_size=args.batch, force=args.force, proxy=args.proxy
        ) as wd_collector:
            print("  [1/2] Wikidata 核心信息 …")
            core = wd_collector.query_core(pairs)
            print(f"        命中 {len(core)} 部")
            print("  [2/2] Wikidata 拍摄地坐标 …")
            geo = wd_collector.query_geo(pairs)
            print(f"        命中 {sum(len(v) for v in geo.values())} 处地点")
            print(f"\n  SPARQL 请求 {wd_collector.stats['api_calls']} 次，"
                  f"命中缓存 {wd_collector.stats['cache_hits']} 次")

        summaries: dict[str, dict] = {}
        if not args.no_wikipedia:
            titles = [
                wd_mod.title_from_article(entry.get("zh_article"))
                for entry in core.values()
                if entry.get("zh_article")
            ]
            titles = [t for t in titles if t]
            if titles:
                print(f"\n  Wikipedia 摘要（{len(titles)} 个条目）…")
                with wp_mod.WikipediaCollector(force=args.force, proxy=args.proxy) as wp_collector:
                    summaries = wp_collector.collect(titles)
                    print(f"        取到 {sum(1 for v in summaries.values() if v.get('extract'))} 条正文，"
                          f"请求 {wp_collector.stats['api_calls']} 次，"
                          f"命中缓存 {wp_collector.stats['cache_hits']} 次")
            else:
                print("\n  提示：Wikidata 里没有这批电影的 zhwiki 条目，跳过摘要采集")

    # ---- 合拢 + 落盘 ----
    records = wiki_mod.build_wiki_records(core, geo, summaries)
    if not records:
        # 不要写出 0 字节的输出文件：那会让阶段 2 误以为「维基这步已经跑完了、只是没有数据」。
        # 宁可什么都不写，让下游一眼看出这一步没成功。
        print("\n  [中止] 没有取到任何维基记录，已跳过写盘（不产生空输出文件）。")
        print("  常见原因：")
        print("    1) SPARQL 被限流（HTTP 429）→ 看上面提示，稍后重试或加 --proxy")
        print("    2) interim 里还没有任何带 imdb_id / tmdb_id 的记录 → 先跑 seed / tmdb / imdb")
        print("    3) 想先验证链路 → 加 --demo 用固件跑\n")
        return 1

    out_name = "wiki_movies.demo.jsonl" if args.demo else "wiki_movies.jsonl"
    out = _demo_out_dir(args) / out_name
    n = wiki_mod.write_jsonl(records, out)

    zh = sum(1 for r in records if r.get("title_zh"))
    with_dir = sum(1 for r in records if r.get("director"))
    with_abs = sum(1 for r in records if r.get("overview"))
    with_qid = sum(1 for r in records if r.get("wikidata_qid"))
    places = sum(len(r.get("filming_locations") or []) for r in records)
    on_map = sum(len(r.get("locations_with_coords") or []) for r in records)
    years = [r["release_year"] for r in records if r.get("release_year")]

    print("-" * 68)
    print(f"  记录数        : {n}")
    print(f"  含中文片名    : {zh}")
    print(f"  含导演        : {with_dir}")
    print(f"  含剧情摘要    : {with_abs}")
    print(f"  含 Wikidata 号 : {with_qid}")
    print(f"  拍摄地/发生地 : {places} 处，其中 {on_map} 处带坐标（→ 阶段 6 足迹地图）")
    if years:
        print(f"  年份区间      : {min(years)} ~ {max(years)}")
    print(f"  输出文件      : {out}")
    print(f"  耗时          : {time.time() - t0:.1f}s")
    print("=" * 68 + "\n")
    return 0


def _resolve_handle(raw: str) -> str:
    """把 --dataset 的 key（imdb50k）或直接给的 handle（owner/name）统一成 handle。"""
    raw = (raw or "").strip()
    if raw in kaggle_mod.KNOWN_DATASETS:
        return kaggle_mod.KNOWN_DATASETS[raw].handle
    return raw


def cmd_kaggle(args: argparse.Namespace) -> int:
    """阶段 1e：Kaggle 公开影评采集（流式解析，内存与行数无关）。"""
    _banner("阶段 1e · Kaggle 公开影评采集")
    t0 = time.time()

    # ---- --list：只列清单，不下载 ----
    if args.list:
        kaggle_mod.list_datasets()
        return 0

    handle = _resolve_handle(args.handle or args.dataset or settings.kaggle_dataset)
    if not handle:
        print("\n  [中止] 没有指定数据集。用 --dataset imdb50k 或 --handle owner/name\n")
        return 1

    # ---- 0) 演示模式：造一份合成影评，不联网不下载也能跑通全链路 ----
    if args.demo:
        demo_dir = settings.lake("kaggle_reviews_demo")
        print(f"  [演示模式] 生成合成影评数据集（非真实数据，仅供离线跑通链路）")
        csv_path = kaggle_mod.build_demo_dataset(demo_dir)
        print(f"    {csv_path.name}{'':<18}{csv_path.stat().st_size / 1024:>8.0f} KB")
        print("    提示：要换成真实数据，执行 `python -m ingest.run_collect kaggle`\n")
        directory = demo_dir
        files = [csv_path]
        handle = "demo/offline"
    else:
        directory = kaggle_mod.dataset_dir(handle, args.dir)
        print(f"  数据集     : {handle}")
        print(f"  存放目录   : {directory}")
        print(f"  正文列     : {args.text_col or settings.kaggle_text_col or '自动识别'}")
        print(f"  条数上限   : {args.limit or '不限'}"
              f"   正文下限: {args.min_chars} 字"
              f"   去重: {'开' if not args.no_dedupe else '关'}\n")

        files = kaggle_mod.find_data_files(directory)
        if files:
            print(f"  [命中] 目录里已有 {len(files)} 个数据文件，跳过下载")
        elif args.no_download:
            print("\n  [中止] 本地没有数据文件，且指定了 --no-download。")
            print(f"  处理方式：把数据集文件放进 {directory} 后重跑，")
            print("            或去掉 --no-download 让脚本下载，")
            print("            或先离线跑通链路：python -m ingest.run_collect kaggle --demo\n")
            return 1
        else:
            try:
                kaggle_mod.download(handle, directory=directory, force=args.force)
            except RuntimeError as exc:
                print(f"\n  [下载失败] {exc}\n")
                return 2
            files = kaggle_mod.find_data_files(directory)

    if not files:
        print(f"\n  [中止] 在 {directory} 里没有找到可解析的数据文件。")
        print("  支持 .csv / .tsv / .jsonl / .json / .txt。\n")
        return 1

    # ---- 1) 流式解析 + 落盘 ----
    out_name = "reviews.demo.jsonl" if args.demo else "reviews.jsonl"
    out = _demo_out_dir(args) / out_name
    result = kaggle_mod.ParseResult()
    seen: set[str] = set()      # 跨文件共享去重
    lengths: list[int] = []     # 正文长度，仅用于最后的分布统计
    # 手动指定正文列（留空则自动识别）
    manual_col = args.text_col or settings.kaggle_text_col

    def generate():
        emitted = 0
        for f in files:
            if args.limit and emitted >= args.limit:
                break
            remaining = (args.limit - emitted) if args.limit else None
            col = kaggle_mod.column_index(f, manual_col) if manual_col else None
            if manual_col and col is None:
                print(f"    [警告] {f.name} 里没有列 {manual_col!r}，改为自动识别")
            print(f"    [解析] {f.name}")
            for rec in kaggle_mod.iter_records(
                f,
                text_col=col,
                limit=remaining,
                min_chars=args.min_chars,
                dedupe=not args.no_dedupe,
                swap_labels=args.swap_labels,
                lang=args.lang,
                dataset=handle,
                result=result,
                seen=seen,
            ):
                lengths.append(rec["text_len"])
                emitted += 1
                yield rec

    n = kaggle_mod.write_jsonl_stream(generate(), out)

    # ---- 2) 空输出守卫：一条都没解析出来就别留个 0 字节文件骗下游 ----
    if n == 0:
        out.unlink(missing_ok=True)
        print("\n  [中止] 没有解析出任何影评，已删除空输出文件。")
        print("  常见原因：")
        print("    1) 正文列认错了 —— 用 --text-col 指定列名，先看一眼表头")
        print("    2) --min-chars 设得太大，把短评全过滤了")
        print("    3) 文件其实不是影评表格（比如下成了 IMDb 的 TSV 数据集）\n")
        return 1

    # ---- 3) 汇总 ----
    lengths.sort()
    dist = result.sentiment_dist
    print("-" * 68)
    print(f"  原始行数      : {result.rows:,}")
    print(f"  写出记录数    : {n:,}")
    skipped = {
        "重复": result.skipped_dupe,
        "空正文": result.skipped_empty,
        "过短": result.skipped_short,
        "残缺行": result.malformed,
    }
    skip_txt = "，".join(f"{k} {v:,}" for k, v in skipped.items() if v)
    if skip_txt:
        print(f"  跳过          : {skip_txt}")
    if dist:
        total = sum(dist.values()) or 1
        print("  情感分布      : " + "，".join(
            f"{k} {v:,}({v / total:.0%})" for k, v in sorted(dist.items(), key=lambda kv: -kv[1])
        ))
        # 标签映射可能反了 —— 失衡到这种程度基本可以断定
        pos, neg = dist.get("positive", 0), dist.get("negative", 0)
        if pos + neg > 100 and min(pos, neg) / max(pos + neg, 1) < 0.05:
            print("  ⚠ 情感严重失衡 —— 若数据集本该均衡，说明 1/0 标签映射反了，"
                  "加 --swap-labels 重跑")
    if lengths:
        mid = lengths[len(lengths) // 2]
        print(f"  正文字符数    : 最短 {lengths[0]}，中位 {mid}，"
              f"平均 {sum(lengths) / len(lengths):.0f}，最长 {lengths[-1]}")
    print(f"  输出文件      : {out}")
    print(f"  耗时          : {time.time() - t0:.1f}s")
    print(f"  {format_mem()}   ← 流式解析，与数据集行数无关")
    print("=" * 68 + "\n")
    return 0


def cmd_letterboxd(args: argparse.Namespace) -> int:
    """阶段 2：Letterboxd 公开影评采集（遵守 robots / ≤1 req/s / 不采 PII）。"""
    _banner("阶段 2 · Letterboxd 影评采集")
    t0 = time.time()

    # ---- 收集种子 ----
    if args.demo:
        fixture_dir = PROJECT_ROOT / "tests" / "fixtures"
        seeds: list = ["parasite-2019"]   # 离线夹具 slug
        print(f"  [演示模式] 直接用内置夹具 {fixture_dir}（不联网、不查 robots）")
    else:
        fixture_dir = None
        if args.slug:
            seeds = [args.slug]
            print(f"  种子       : 单部 slug={args.slug}")
        elif args.from_tmdb:
            seeds = lb_mod.seed_from_tmdb(limit=args.films or None)
            print(f"  种子       : 从 TMDB 片库取前 {args.films or '全部'} 部（tmdb_id）")
        elif args.seed_file:
            seeds = lb_mod.seed_from_file(args.seed_file)
            print(f"  种子       : 文件 {args.seed_file}（{len(seeds)} 条）")
        else:
            print("\n  [中止] 请指定种子来源：--slug / --from-tmdb / --seed-file\n")
            return 1
        if not seeds:
            print("\n  [中止] 没有可用种子（TMDB 片库可能还没采，先跑 `tmdb` 或给 --slug）\n")
            return 1

    print(f"  代理策略   : {args.proxy or settings.collector_proxy or '跟随系统'}")
    print(f"  限速       : ≤{settings.letterboxd_min_interval}s/req  每片最多 {args.max_pages} 页\n")

    out_name = "reviews.letterboxd.demo.jsonl" if args.demo else "reviews.letterboxd.jsonl"
    out = _demo_out_dir(args) / out_name

    from ingest.jsonl_io import write_jsonl  # noqa: PLC0415
    from ingest.http import CollectorHttpError  # noqa: PLC0415

    try:
        with lb_mod.LetterboxdCollector(
            force=args.force, proxy=args.proxy, fixture_dir=fixture_dir,
            max_reviews=args.limit, max_pages=1 if args.demo else args.max_pages,
            use_browser=args.browser,
        ) as collector:
            def gen():
                for r in collector.collect(seeds):
                    validate_review_full(r, strict=True)  # 合同自检：核心字段必齐
                    yield r
            n = write_jsonl(gen(), out)
            st = collector.stats
    except CollectorHttpError as exc:
        print(f"\n[采集失败] {exc}")
        print("  Letterboxd 提示：若看到 Cloudflare 'Just a moment' / HTTP 403，")
        print("  说明被反爬挑战拦截（非代码错误）。改用真实浏览器抓取：")
        print("    pip install playwright && playwright install chromium")
        print("    再运行：python -m ingest.run_collect letterboxd --slug <slug> --browser")
        print("  （用浏览器属于正常采集手段，不绕过登录墙/验证码；请同时遵守 robots 与平台条款）\n")
        return 2
    print("-" * 68)
    print(f"  写出影评   : {n:,}")
    print(f"  抓取页数   : {st.get('pages', 0)}  影片数: {st.get('films', 0)}  "
          f"跳过(robots): {st.get('skipped_robots', 0)}  空页: {st.get('skipped_empty', 0)}")
    print(f"  输出文件   : {out}")
    print(f"  耗时       : {time.time() - t0:.1f}s")
    print("=" * 68 + "\n")
    return 0


def cmd_metacritic(args: argparse.Namespace) -> int:
    """方案 #3：Metacritic 影评采集（critic + user，遵守 robots / 限速 / 不采 PII）。"""
    _banner("方案 #3 · Metacritic 影评采集")
    t0 = time.time()

    if args.demo:
        fixture_dir = PROJECT_ROOT / "tests" / "fixtures"
        seeds: list = ["parasite-2019"]   # 离线夹具 slug
        print(f"  [演示模式] 直接用内置夹具 {fixture_dir}（不联网、不查 robots）")
    else:
        fixture_dir = None
        if args.slug:
            seeds = [s.strip() for s in args.slug.split(",") if s.strip()]
            print(f"  种子       : 单/多部 slug={seeds}")
        elif args.seed_file:
            seeds = lb_mod.seed_from_file(args.seed_file)
            print(f"  种子       : 文件 {args.seed_file}（{len(seeds)} 条）")
        else:
            print("\n  [中止] 请指定种子来源：--slug / --seed-file\n")
            return 1
        if not seeds:
            print("\n  [中止] 没有可用种子\n")
            return 1

    types = ()
    if args.type in ("critic", "both"):
        types += ("critic",)
    if args.type in ("user", "both"):
        types += ("user",)
    print(f"  影评类型   : {', '.join(types) or args.type}")
    print(f"  代理策略   : {args.proxy or settings.collector_proxy or '跟随系统'}")
    print(f"  限速       : ≤{settings.metacritic_min_interval}s/req  每片每类最多 {args.max_pages} 页")
    print(f"  反爬提示   : 裸 httpx 大概率被拦；若命中率为 0 请加 --browser 走 Playwright\n")

    out_name = "reviews.metacritic.demo.jsonl" if args.demo else "reviews.metacritic.jsonl"
    out = _demo_out_dir(args) / out_name

    from ingest.http import CollectorHttpError  # noqa: PLC0415

    try:
        with mc_mod.MetacriticCollector(
            force=args.force, proxy=args.proxy, fixture_dir=fixture_dir,
            max_reviews=args.limit, max_pages=1 if args.demo else args.max_pages,
            use_browser=args.browser,
        ) as collector:
            def gen():
                for r in collector.collect(seeds, types=types):
                    validate_review_full(r, strict=True)
                    yield r
            n = write_jsonl(gen(), out)
            st = collector.stats
    except CollectorHttpError as exc:
        print(f"\n[采集失败] {exc}")
        print("  Metacritic 提示：若看到反爬挑战页 / HTTP 403，说明被 PerimeterX 拦截（非代码错误）。")
        print("  改用真实浏览器抓取：")
        print("    pip install playwright && playwright install chromium")
        print("    再运行：python -m ingest.run_collect metacritic --slug <slug> --browser")
        print("  （用浏览器属于正常采集手段，不绕过登录墙/验证码；请同时遵守 robots 与平台条款）\n")
        return 2

    print("-" * 68)
    print(f"  写出影评   : {n:,}")
    print(f"  抓取页数   : {st.get('pages', 0)}  影片数: {st.get('films', 0)}  "
          f"跳过(robots): {st.get('skipped_robots', 0)}  空页: {st.get('skipped_empty', 0)}")
    if st.get("fields_missing"):
        print(f"  ⚠ 字段缺失 : {st['fields_missing']} 条（作者/分数为空，可能需微调选择器）")
    print(f"  输出文件   : {out}")
    print(f"  耗时       : {time.time() - t0:.1f}s")
    print("=" * 68 + "\n")
    return 0


def cmd_chinese(args: argparse.Namespace) -> int:
    """方案 #5：中文公开影评数据集采集（禁豆瓣；本地导入 / Kaggle / 离线 demo）。"""
    _banner("方案 #5 · 中文公开影评数据集采集")
    t0 = time.time()

    if args.demo:
        demo_dir = settings.lake("kaggle_reviews", "demo", "chinese")
        print(f"  [演示模式] 生成合成中文影评（非真实数据，仅供离线跑通链路）")
        csv_path = cn_mod.build_demo_dataset(demo_dir)
        print(f"    {csv_path.name}{'':<18}{csv_path.stat().st_size / 1024:>8.0f} KB")
        directory = demo_dir
        print("    提示：要换成真实数据，执行 `python -m ingest.run_collect chinese --dir <目录>`\n")
    elif args.handle:
        directory = cn_mod.dataset_dir(args.handle, args.dir)
        print(f"  数据集     : {args.handle}（Kaggle，需凭证）")
        print(f"  存放目录   : {directory}")
        try:
            cn_mod.download(args.handle, directory=directory, force=args.force)
        except RuntimeError as exc:
            print(f"\n  [下载失败] {exc}\n")
            return 2
    else:
        directory = Path(args.dir) if args.dir else (
            Path(settings.chinese_reviews_dir) if settings.chinese_reviews_dir else None
        )
        if not directory:
            print("\n  [中止] 未指定数据来源。三选一：")
            print("    ① 离线验证：  python -m ingest.run_collect chinese --demo")
            print("    ② 本地文件：  python -m ingest.run_collect chinese --dir <文件或目录>")
            print("    ③ Kaggle：    python -m ingest.run_collect chinese --handle owner/dataset-name\n")
            return 1
        print(f"  本地目录   : {directory}")
        if not directory.exists():
            print(f"\n  [中止] 目录不存在：{directory}\n")
            return 1

    if not args.demo:
        files = cn_mod.find_data_files(directory)
        if not files:
            print(f"\n  [中止] 在 {directory} 里没有找到可解析的数据文件（.csv/.tsv/.jsonl/.json/.txt）。\n")
            return 1
        print(f"  数据文件   : {len(files)} 个")
    else:
        files = [csv_path]

    print(f"  正文下限   : {args.min_chars} 字   去重: {'开' if not args.no_dedupe else '关'}")
    print(f"  条数上限   : {args.limit or '不限'}\n")

    out_name = "reviews.chinese.demo.jsonl" if args.demo else "reviews.chinese.jsonl"
    out = _demo_out_dir(args) / out_name
    result = cn_mod.ParseResult()
    seen: set[str] = set()
    lengths: list[int] = []
    manual_col = args.text_col

    def generate():
        emitted = 0
        for f in files:
            if args.limit and emitted >= args.limit:
                break
            remaining = (args.limit - emitted) if args.limit else None
            print(f"    [解析] {f.name}")
            for rec in cn_mod.iter_records(
                f,
                text_col=manual_col or None,
                limit=remaining,
                min_chars=args.min_chars,
                dedupe=not args.no_dedupe,
                swap_labels=args.swap_labels,
                lang=settings.chinese_lang,
                dataset=args.handle or "chinese-local",
                result=result,
                seen=seen,
            ):
                validate_review_full(rec, strict=True)  # 合同自检：核心字段必齐
                lengths.append(rec["text_len"])
                emitted += 1
                yield rec

    n = cn_mod.write_jsonl_stream(generate(), out)

    if n == 0:
        out.unlink(missing_ok=True)
        print("\n  [中止] 没有解析出任何中文影评，已删除空输出文件。")
        print("  常见原因：")
        print("    1) 正文列认错了 —— 用 --text-col 指定列名，先看一眼表头")
        print("    2) --min-chars 设得太大，把短评全过滤了\n")
        return 1

    lengths.sort()
    dist = result.sentiment_dist
    print("-" * 68)
    print(f"  原始行数      : {result.rows:,}")
    print(f"  写出记录数    : {n:,}")
    skipped = {
        "重复": result.skipped_dupe,
        "空正文": result.skipped_empty,
        "过短": result.skipped_short,
        "残缺行": result.malformed,
    }
    skip_txt = "，".join(f"{k} {v:,}" for k, v in skipped.items() if v)
    if skip_txt:
        print(f"  跳过          : {skip_txt}")
    if dist:
        total = sum(dist.values()) or 1
        print("  情感分布      : " + "，".join(
            f"{k} {v:,}({v / total:.0%})" for k, v in sorted(dist.items(), key=lambda kv: -kv[1])
        ))
    if lengths:
        mid = lengths[len(lengths) // 2]
        print(f"  正文字数      : 最短 {lengths[0]}，中位 {mid}，"
              f"平均 {sum(lengths) / len(lengths):.0f}，最长 {lengths[-1]}")
    print(f"  输出文件      : {out}")
    print(f"  耗时          : {time.time() - t0:.1f}s")
    print("=" * 68 + "\n")
    return 0


def cmd_douban(args: argparse.Namespace) -> int:
    """阶段 1f · 豆瓣数据源（解除「禁采集豆瓣」红线后新增）：短评 + 热映榜 + 评分。

    合规要点（详见 ingest/sources/douban.py 文件头）：
      - 库内电影 → 豆瓣 ID 靠 Wikidata P4529 批量映射（公开开放数据，零逐片请求）；
      - 短评走本机 Chrome 抓公开页，未登录即可取，绝不挂账号、不碰登录墙；
      - 慢速采集：每次请求至少间隔 3 秒、按每片配额逐页补齐；作者名只存匿名 hash；
      - 热映榜走公开页，作为「院线新片」独立实体（单独 ES 索引，不并入库内片库）。
    """
    _banner("阶段 1f · 豆瓣数据源采集（公开页慢速 / 不挂账号 / 作者匿名）")
    t0 = time.time()

    # ---- 1) 读库内电影（processed 成品），拿标识符去映射豆瓣 ID ----
    movies_path = settings.lake("processed") / "movies.jsonl"
    if not movies_path.exists():
        print(f"\n  [中止] 没找到 {movies_path}。请先跑完采集 + transform：")
        print("    python -m ingest.run_collect <源>  →  python -m transform.run_transform movies\n")
        return 1
    library = [m for m in iter_jsonl(movies_path)]
    print(f"  库内电影   : {len(library)} 部（来自 processed/movies.jsonl）")
    print(f"  代理策略   : {args.proxy or settings.collector_proxy or '跟随系统'}")
    print(f"  每片页数   : {args.pages}   请求间隔: {args.delay}s")
    print(f"  热映城市   : {args.city}")
    print(f"  跳过的步骤 :"
          f"{' 评分' if args.no_ratings else ''}"
          f"{' 评论' if args.no_reviews else ''}"
          f"{' 热映榜' if args.no_nowplaying else ''}"
          f"{'（无）' if not (args.no_ratings or args.no_reviews or args.no_nowplaying) else ''}\n")

    out_ratings = settings.lake("interim") / "douban_movies.jsonl"
    out_reviews = settings.lake("interim") / "reviews.douban.jsonl"
    out_long_reviews = settings.lake("interim") / "reviews.douban_long.jsonl"
    out_np = settings.lake("interim") / "douban_nowplaying.jsonl"

    n_long = 0
    from ingest.jsonl_io import write_jsonl  # noqa: PLC0415

    try:
        with douban_mod.DoubanCollector(force=args.force, proxy=args.proxy) as collector:
            # ---- 2) 批量映射豆瓣 ID ----
            print("  [1/4] Wikidata P4529 映射豆瓣 ID …")
            mapped = collector.map_douban_ids(library)
            movies_by_id = {}
            external_to_mid: dict[str, str] = {}
            for movie in library:
                mid_value = movie.get("movie_id") or movie.get("imdb_id") or movie.get("tmdb_id")
                if not mid_value:
                    continue
                mid = str(mid_value)
                movies_by_id[mid] = movie
                for external_id in (movie.get("movie_id"), movie.get("imdb_id"), movie.get("tmdb_id")):
                    if external_id is not None:
                        external_to_mid[str(external_id)] = mid
            for record in iter_jsonl(out_ratings):
                douban_id = str(record.get("douban_id") or "").strip()
                if not douban_id:
                    continue
                mid = (
                    external_to_mid.get(str(record.get("imdb_id") or ""))
                    or external_to_mid.get(str(record.get("tmdb_id") or ""))
                )
                if mid:
                    mapped.setdefault(mid, douban_id)
            print(f"        命中豆瓣 ID：{len(mapped)} / {len(library)} 部")
            unmapped = [
                movie for mid, movie in movies_by_id.items()
                if mid not in mapped
            ]
            pending_path = settings.lake("interim") / "douban_unmapped_movies.jsonl"
            write_jsonl(unmapped, pending_path)
            if unmapped:
                print(
                    f"        未取得豆瓣 ID：{len(unmapped)} 部，记录到 {pending_path.name}；"
                    "不会跳过不报，也不会用 robots 禁止的搜索页绕过限制。"
                )

            # ---- 3) 抓豆瓣评分（并入库内电影）----
            if not args.no_ratings:
                print("  [2/4] 抓豆瓣评分（本机 Chrome，公开页）…")
                n_rating = write_jsonl(
                    collector.collect_ratings(mapped, movies_by_id=movies_by_id),
                    out_ratings,
                )
                print(f"        写出 {n_rating} 部豆瓣评分 → {out_ratings}")
            else:
                n_rating = 0

            # ---- 4) 抓豆瓣短评 ----
            if not args.no_reviews:
                existing_reviews = list(iter_jsonl(out_reviews))
                existing_douban = [
                    row for row in existing_reviews if row.get("source") == "douban"
                ]
                existing_by_movie: dict[str, dict[str, set[str]]] = {}
                for row in existing_douban:
                    mid = (
                        str(row.get("movie_id") or "")
                        or external_to_mid.get(str(row.get("imdb_id") or ""))
                        or external_to_mid.get(str(row.get("movie_tmdb_id") or ""))
                    )
                    if not mid:
                        continue
                    row["movie_id"] = mid
                    state = existing_by_movie.setdefault(
                        mid, {"ids": set(), "texts": set(), "time": set(), "new_score": set()}
                    )
                    for field in ("external_id", "review_id"):
                        value = str(row.get(field) or "")
                        if value.startswith("douban:"):
                            state["ids"].add(value.split(":", 1)[1])
                    text = str(row.get("text") or "").strip()
                    if text:
                        state["texts"].add(hashlib.sha1(text.encode("utf-8")).hexdigest())
                    # The prior Douban collector used the default popular ordering.
                    # Keep those legacy rows and count them toward that movie's quota.
                    sort = str(row.get("douban_sort") or "new_score")
                    if sort not in ("time", "new_score"):
                        sort = "new_score"
                    if row.get("douban_sort") is None:
                        row["douban_sort"] = sort
                    if row.get("review_id"):
                        state[sort].add(str(row["review_id"]).removeprefix("douban:"))

                recent_limit = max(0, args.recent_limit)
                print("  [3/4] 抓豆瓣短评（最近排序 + 热门排序，去重）…")
                print(
                    f"        每片目标：最近 {recent_limit} 条 + 最热 {args.popular_limit} 条；"
                    f"已映射影片 {len(mapped)} / {len(library)} 部"
                )
                out_reviews.parent.mkdir(parents=True, exist_ok=True)
                with tempfile.TemporaryDirectory(
                    dir=out_reviews.parent, prefix=".douban-reviews-"
                ) as temp_dir:
                    collected_path = Path(temp_dir) / "collected.jsonl"
                    merged_path = Path(temp_dir) / "merged.jsonl"
                    n_new = write_jsonl(
                        collector.collect_reviews(
                            mapped,
                            movies_by_id=movies_by_id,
                            pages=args.pages,
                            delay=args.delay,
                            limit=args.limit,
                            recent_limit=recent_limit,
                            popular_limit=max(0, args.popular_limit),
                            existing_by_movie=existing_by_movie,
                        ),
                        collected_path,
                    )

                    merged_by_id: dict[str, dict] = {}
                    for row in (*existing_reviews, *iter_jsonl(collected_path)):
                        key = str(
                            row.get("external_id") or row.get("review_id")
                            or hashlib.sha1(str(row.get("text") or "").encode("utf-8")).hexdigest()
                        )
                        merged_by_id.setdefault(key, row)
                    n_rev = write_jsonl(merged_by_id.values(), merged_path)
                    merged_path.replace(out_reviews)

                print(
                    f"        本轮新增 {n_new} 条（最近 {collector.stats.get('comments_time', 0)}，"
                    f"最热 {collector.stats.get('comments_new_score', 0)}），"
                    f"累计去重后 {n_rev} 条 → {out_reviews}"
                )
                incomplete = []
                for mid, douban_id in mapped.items():
                    state = existing_by_movie.get(
                        mid, {"time": set(), "new_score": set()}
                    )
                    counts = {"time": 0, "new_score": 0}
                    for row in merged_by_id.values():
                        if row.get("source") == "douban" and str(row.get("movie_id") or "") == mid:
                            sort = str(row.get("douban_sort") or "new_score")
                            if sort in counts:
                                counts[sort] += 1
                    if counts["time"] < recent_limit or counts["new_score"] < args.popular_limit:
                        incomplete.append((movies_by_id.get(mid, {}).get("title") or mid,
                                           counts["time"], counts["new_score"]))
                print(
                    f"        配额完成：{len(mapped) - len(incomplete)} / {len(library)} 部；"
                    f"未完成/未映射：{len(incomplete) + len(unmapped)} 部"
                )
                if incomplete:
                    print("        尚未达到配额的影片（前 10 部）：")
                    for title, recent_count, popular_count in incomplete[:10]:
                        print(
                            f"          - {title}: 最新 {recent_count}/{recent_limit}，"
                            f"最热 {popular_count}/{args.popular_limit}"
                        )
                n_long = write_jsonl(
                    collector.collect_long_reviews(
                        mapped,
                        movies_by_id=movies_by_id,
                        pages=getattr(args, "long_pages", 0),
                        delay=args.delay,
                        limit=args.limit,
                    ),
                    out_long_reviews,
                )
                if n_long:
                    print(f"        写出 {n_long} 条豆瓣长评 → {out_long_reviews}")
            else:
                n_rev = 0

            # ---- 5) 抓正在热映榜 ----
            if not args.no_nowplaying:
                print("  [4/4] 抓豆瓣正在热映榜（公开页）…")
                np_rows = collector.collect_nowplaying(city=args.city)
                n_np = write_jsonl(np_rows, out_np)
                print(f"        写出 {n_np} 条热映影片 → {out_np}")
            else:
                n_np = 0
    except Exception as exc:  # 浏览器/网络异常不应让整批崩
        print(f"\n  [采集异常] {exc}")
        print("  排查：豆瓣短评/热映榜需 Playwright + 本机 Chrome；")
        print("        若网络需代理，加 --proxy http://127.0.0.1:7890\n")
        return 2

    print("-" * 68)
    print(f"  豆瓣 ID 命中 : {len(mapped)} 部")
    print(f"  豆瓣评分     : {n_rating} 部")
    print(f"  豆瓣短评     : {n_rev} 条")
    print(f"  热映影片     : {n_np} 条")
    print(f"  耗时         : {time.time() - t0:.1f}s")
    print("=" * 68 + "\n")
    return 0


def cmd_douban_dataset(args: argparse.Namespace) -> int:
    """Import locally supplied Douban review CSVs for unambiguously matched films."""
    from transform.reviews import build_title_index  # noqa: PLC0415

    movies_path = settings.lake("processed") / "movies.jsonl"
    if not movies_path.exists():
        print(f"\n[中止] 找不到电影库文件：{movies_path}")
        return 1

    movies = list(iter_jsonl(movies_path))
    if not movies:
        print(f"\n[中止] 电影库为空：{movies_path}")
        return 1

    title_index = build_title_index(movies)
    movies_by_id = {str(m["movie_id"]): m for m in movies if m.get("movie_id")}
    stats = douban_dataset_mod.ImportStats()
    out = settings.lake("interim") / "reviews.douban_dataset.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)

    print("本地数据集导入（不联网、不请求豆瓣）")
    print(f"  输入目录 : {args.dir}")
    print(f"  电影库   : {movies_path}（{len(movies):,} 部）")

    with tempfile.TemporaryDirectory(dir=out.parent, prefix=".douban-dataset-") as temp_dir:
        candidate = Path(temp_dir) / out.name
        try:
            count = write_jsonl(
                douban_dataset_mod.iter_reviews(
                    Path(args.dir), title_index, movies_by_id, stats
                ),
                candidate,
            )
        except (FileNotFoundError, UnicodeDecodeError) as exc:
            print(f"\n[导入失败] {exc}")
            return 2

        if count == 0:
            print("\n[中止] 没有得到可关联的评论；保留原有导入文件不变。")
            return 2
        candidate.replace(out)

    print(f"  CSV 文件 : {stats.files_seen} 个，匹配电影 {stats.matched_files} 部，"
          f"未匹配 {len(stats.unmatched_titles)} 个")
    print(f"  评论行数 : {stats.rows_seen:,}，写入 {count:,}，"
          f"空评论跳过 {stats.skipped_empty:,}，无效行跳过 {stats.skipped_invalid:,}")
    if stats.unmatched_titles:
        print("  未匹配片名示例: " + "、".join(stats.unmatched_titles[:10]))
    print(f"  输出文件 : {out}")
    print("  下一步   : python -m transform.run_transform reviews")
    print("             python -m index.run_index import reviews")
    return 0


def cmd_tmdb_videos(args: argparse.Namespace) -> int:
    """阶段 1g · TMDB 官方预告片（视频数据）采集：库内电影逐片拉 YouTube Trailer/Teaser。

    合规要点（详见 ingest/sources/tmdb.py）：
      - 只取 TMDB 官方接口的 YouTube 预告片，**不碰任何盗版片源直连**；
      - 复用 processed/movies.jsonl 的 tmdb_id 当种子，零重复发现；
      - 限速随 TMDB 客户端（约 4 req/s），落盘走 raw 缓存可断点续跑。
    """
    _banner("阶段 1g · TMDB 官方预告片（视频数据）采集")
    t0 = time.time()

    movies_path = settings.lake("processed") / "movies.jsonl"
    if not movies_path.exists():
        print(f"\n  [中止] 没找到 {movies_path}。请先跑完采集 + transform：")
        print("    python -m ingest.run_collect <源>  →  python -m transform.run_transform movies\n")
        return 1
    library = [m for m in iter_jsonl(movies_path)]
    with_tmdb = [m for m in library if m.get("tmdb_id")]
    print(f"  库内电影   : {len(library)} 部，其中含 tmdb_id : {len(with_tmdb)} 部")
    print(f"  代理策略   : {args.proxy or settings.collector_proxy or '跟随系统'}\n")

    out = settings.lake("interim") / "tmdb_videos.jsonl"
    from ingest.jsonl_io import write_jsonl  # noqa: PLC0415

    try:
        with tmdb_mod.TmdbCollector(force=args.force, proxy=args.proxy) as collector:
            records = collector.collect_videos(with_tmdb)
            n = write_jsonl(records, out)
            print(f"        写出 {n} 部含预告片 → {out}")
    except CollectorHttpError as exc:
        print(f"\n  [采集失败] {exc}\n")
        return 2

    print("-" * 68)
    print(f"  含预告片   : {n} 部")
    print(f"  耗时       : {time.time() - t0:.1f}s")
    print("=" * 68 + "\n")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m ingest.run_collect",
        description="电影盒子 · 阶段 1a 数据采集",
    )
    # 公共参数：让 --force / --proxy 在子命令前后都能写
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--force", action="store_true", help="忽略 raw 缓存，强制重新请求")
    common.add_argument(
        "--proxy", default=None,
        help="代理策略：留空=跟随系统；direct=直连；或 http://host:port",
    )

    sub = p.add_subparsers(dest="command", required=True)

    s_seed = sub.add_parser("seed", parents=[common], help="导入旧系统片库（data/web_movies.json）")
    s_seed.add_argument("--resolve", action="store_true", help="用 TMDB 反查缺失的 tmdb_id")
    s_seed.add_argument("--limit", type=int, default=None, help="本次最多反查多少条（控制配额）")
    s_seed.add_argument("--no-detail", action="store_true", help="只反查 id，不拉详情")
    s_seed.set_defaults(func=cmd_seed)

    s_tmdb = sub.add_parser("tmdb", parents=[common], help="TMDB 发现式采集")
    s_tmdb.add_argument("--pages", type=int, default=settings.tmdb_discover_pages, help="发现页数，每页 20 部")
    s_tmdb.add_argument("--limit", type=int, default=None, help="最多取多少部详情")
    s_tmdb.add_argument("--sort", choices=list(SORT_CHOICES), default="popularity", help="发现排序")
    s_tmdb.add_argument("--year-from", type=int, default=None, help="起始年份")
    s_tmdb.add_argument("--year-to", type=int, default=None, help="结束年份")
    s_tmdb.set_defaults(func=cmd_tmdb)

    s_tmdbr = sub.add_parser("tmdb-reviews", parents=[common],
                             help="TMDB 影评采集（方案 #2）：复用电影清单拉 /movie/{id}/reviews")
    s_tmdbr.add_argument("--limit", type=int, default=None,
                         help="现场发现电影的上限（默认复用既有 interim 电影文件）")
    s_tmdbr.add_argument("--max-pages", type=int, default=1,
                         help="每部电影最多翻几页影评（TMDB 每页 20 条）")
    s_tmdbr.add_argument("--movies-file", default="tmdb_movies.jsonl",
                         help="电影清单 interim 文件名（默认 tmdb_movies.jsonl）")
    s_tmdbr.add_argument("--rediscover", action="store_true",
                         help="忽略既有电影文件，现场重新发现")
    s_tmdbr.set_defaults(func=cmd_tmdb_reviews)

    s_rss = sub.add_parser("rss", parents=[common],
                           help="RSS 影视新闻采集（方案 #4）：Variety/THR/Deadline 舆情时间线")
    s_rss.add_argument("--min-interval", type=float, default=None,
                       help="相邻 feed 之间最小间隔（秒），默认 settings.rss_min_interval")
    s_rss.add_argument("--feeds", default=None,
                       help="覆盖 feeds，格式 'Name|url;Name2|url2'")
    s_rss.set_defaults(func=cmd_rss)

    s_imdb = sub.add_parser("imdb", parents=[common], help="IMDb Datasets 采集（阶段 1b）")
    s_imdb.add_argument("--list", action="store_true", help="只打印数据集清单与体积，不下载")
    s_imdb.add_argument("--dir", default=None, help="数据集目录（默认 <data_lake>/imdb_datasets）")
    s_imdb.add_argument("--download", action="store_true", help="缺失时自动下载数据集（支持断点续传）")
    s_imdb.add_argument("--demo", action="store_true",
                        help="生成合成示例数据集并跑通链路（不联网、不下载，先验证流程用）")
    s_imdb.add_argument("--files", default=None,
                        help="指定要用的数据集 key，逗号分隔，如 ratings,basics,crew,names")
    s_imdb.add_argument("--min-votes", type=int, default=settings.imdb_min_votes,
                        help="只保留评分人数≥此值的影片（默认 %(default)s）")
    s_imdb.add_argument("--min-rating", type=float, default=settings.imdb_min_rating,
                        help="评分下限（默认 %(default)s，即不限）")
    s_imdb.add_argument("--types", default=settings.imdb_title_types,
                        help="保留的作品类型，逗号分隔（默认 %(default)s）")
    s_imdb.add_argument("--limit", type=int, default=None,
                        help="最多输出多少条；会优先保留票数最高的若干部")
    s_imdb.add_argument("--include-adult", action="store_true", help="保留成人片（默认过滤掉）")
    s_imdb.add_argument("--with-directors", action="store_true",
                        help="额外用 crew+names 补导演名（要多下 310 MB 数据集）")
    s_imdb.set_defaults(func=cmd_imdb)

    s_wiki = sub.add_parser("wiki", parents=[common],
                            help="Wikidata SPARQL + Wikipedia API 采集（阶段 1c）")
    s_wiki.add_argument("--list", action="store_true",
                        help="只说明会读哪些 interim 文件与预计请求数，不联网")
    s_wiki.add_argument("--from", dest="from_files", default=None,
                        help="指定输入文件（逗号分隔，位于 data_lake/interim/），"
                             "默认自动找 tmdb/imdb/seed 的产物")
    s_wiki.add_argument("--batch", type=int, default=settings.wikidata_batch,
                        help="每条 SPARQL 塞多少个主键（默认 %(default)s）")
    s_wiki.add_argument("--limit", type=int, default=None, help="本次最多查多少个主键")
    s_wiki.add_argument("--no-wikipedia", action="store_true",
                        help="只采 Wikidata，跳过维基摘要（省一半请求）")
    s_wiki.add_argument("--demo", action="store_true",
                        help="用内置固件跑通链路（不联网、不等 SPARQL，先验证流程用）")
    s_wiki.set_defaults(func=cmd_wiki)

    s_kaggle = sub.add_parser("kaggle", parents=[common],
                              help="Kaggle 公开影评采集（阶段 1e）")
    s_kaggle.add_argument("--list", action="store_true",
                          help="只列可选数据集与说明，不下载")
    s_kaggle.add_argument("--dataset", default=None,
                          help=f"预置数据集 key（{'/'.join(kaggle_mod.KNOWN_DATASETS)}），"
                               f"默认 {settings.kaggle_dataset}")
    s_kaggle.add_argument("--handle", default=None,
                          help="直接给 Kaggle handle，如 owner/dataset-name")
    s_kaggle.add_argument("--dir", default=None,
                          help="数据集目录（默认 <data_lake>/kaggle_reviews/<handle>）")
    s_kaggle.add_argument("--no-download", action="store_true",
                          help="只解析本地已有文件，缺失就报错（不联网）")
    s_kaggle.add_argument("--demo", action="store_true",
                          help="造一份合成影评跑通链路（不联网、不下载）")
    s_kaggle.add_argument("--text-col", default=None,
                          help="手动指定正文列名（留空 = 自动识别）")
    s_kaggle.add_argument("--limit", type=int, default=None, help="最多输出多少条")
    s_kaggle.add_argument("--min-chars", type=int, default=settings.kaggle_min_chars,
                          help="正文短于此长度就丢弃（默认 %(default)s，即不丢）")
    s_kaggle.add_argument("--no-dedupe", action="store_true",
                          help="关闭按正文去重（默认开启，重复影评只留一条）")
    s_kaggle.add_argument("--swap-labels", action="store_true",
                          help="翻转 positive/negative（数据集用 0=positive 时用）")
    s_kaggle.add_argument("--lang", default=settings.kaggle_lang, help="影评语言标记")
    s_kaggle.set_defaults(func=cmd_kaggle)

    s_lb = sub.add_parser("letterboxd", parents=[common],
                          help="Letterboxd 公开影评采集（阶段 2 主力爬虫）")
    s_lb.add_argument("--slug", default=None, help="单部电影的 Letterboxd slug，如 parasite-2019")
    s_lb.add_argument("--from-tmdb", action="store_true",
                      help="从已采集的 TMDB 片库取 tmdb_id 当种子（反查 slug）")
    s_lb.add_argument("--seed-file", default=None,
                      help="种子文件（jsonl，含 tmdb_id 或 slug 字段）")
    s_lb.add_argument("--films", type=int, default=0,
                      help="--from-tmdb 时最多取多少部（0=全部）")
    s_lb.add_argument("--limit", type=int, default=0,
                      help="本次最多采集多少条影评（0=不限）")
    s_lb.add_argument("--max-pages", type=int, default=settings.letterboxd_max_pages,
                      help="每部电影最多翻几页影评（默认 %(default)s）")
    s_lb.add_argument("--demo", action="store_true",
                      help="用内置夹具离线跑通链路（不联网、不查 robots）")
    s_lb.add_argument("--browser", action="store_true",
                      help="用 Playwright 真实浏览器抓取（过 Cloudflare 挑战；需先装 playwright+chromium）")
    s_lb.set_defaults(func=cmd_letterboxd)

    s_mc = sub.add_parser("metacritic", parents=[common],
                          help="Metacritic 影评采集（方案 #3）：critic/user 公开影评页")
    s_mc.add_argument("--slug", default=None,
                      help="单部/多部电影 slug，逗号分隔，如 parasite-2019,joker-2019")
    s_mc.add_argument("--seed-file", default=None,
                      help="种子文件（jsonl，含 slug 字段）")
    s_mc.add_argument("--type", choices=["critic", "user", "both"], default="both",
                      help="采 critic / user / 两者（默认两者）")
    s_mc.add_argument("--limit", type=int, default=0,
                      help="本次最多采集多少条影评（0=不限）")
    s_mc.add_argument("--max-pages", type=int, default=settings.metacritic_max_pages,
                      help="每部电影每个类型最多翻几页（默认 %(default)s）")
    s_mc.add_argument("--demo", action="store_true",
                      help="用内置夹具离线跑通链路（不联网、不查 robots）")
    s_mc.add_argument("--browser", action="store_true",
                      help="用 Playwright 真实浏览器抓取（过 Metacritic 反爬；需先装 playwright+chromium）")
    s_mc.set_defaults(func=cmd_metacritic)

    s_cn = sub.add_parser("chinese", parents=[common],
                          help="中文公开影评数据集采集（方案 #5，禁豆瓣）：本地导入/Kaggle/demo")
    s_cn.add_argument("--dir", default=None,
                      help="本地中文影评文件或目录（CSV/TSV/JSONL，列名自适应识别）")
    s_cn.add_argument("--handle", default=None,
                      help="Kaggle handle（owner/dataset-name），需 Kaggle 凭证")
    s_cn.add_argument("--demo", action="store_true",
                      help="造一份合成中文影评跑通链路（不联网、不下载）")
    s_cn.add_argument("--text-col", default=None,
                      help="手动指定正文列名（留空 = 自动识别，含中文列名）")
    s_cn.add_argument("--limit", type=int, default=None, help="最多输出多少条")
    s_cn.add_argument("--min-chars", type=int, default=settings.chinese_min_chars,
                      help="中文正文短于此字数就丢弃（默认 %(default)s，即 5 字）")
    s_cn.add_argument("--no-dedupe", action="store_true",
                      help="关闭按正文去重（默认开启）")
    s_cn.add_argument("--swap-labels", action="store_true",
                      help="翻转 positive/negative（数据集标签映射相反时用）")
    s_cn.set_defaults(func=cmd_chinese)

    s_db = sub.add_parser("douban", parents=[common],
                          help="豆瓣数据源（阶段 1f）：短评 + 热映榜 + 评分（公开页慢速/不挂账号）")
    s_db.add_argument("--pages", type=int, default=20,
                      help="每部电影、每种排序最多翻几页（每页 20 条；默认 %(default)s）")
    s_db.add_argument("--delay", type=float, default=3.0,
                      help="相邻豆瓣请求之间最小间隔（秒，默认 %(default)s）")
    s_db.add_argument("--limit", type=int, default=None,
                      help="兼容的额外硬上限（限制本轮新采集条数）")
    s_db.add_argument("--recent-limit", type=int, default=100,
                      help="每部电影按时间排序的目标条数（默认 %(default)s）")
    s_db.add_argument("--popular-limit", type=int, default=150,
                      help="每部电影按热度排序的目标条数（默认 %(default)s）")
    s_db.add_argument("--long-pages", type=int, default=0,
                      help="每部电影最多采集多少页豆瓣长评（默认 %(default)s）")
    s_db.add_argument("--city", default="hangzhou",
                      help="正在热映榜城市（默认 %(default)s）")
    s_db.add_argument("--no-ratings", action="store_true", help="跳过豆瓣评分抓取")
    s_db.add_argument("--no-reviews", action="store_true", help="跳过豆瓣短评抓取")
    s_db.add_argument("--no-nowplaying", action="store_true", help="跳过热映榜抓取")
    s_db.set_defaults(func=cmd_douban)

    s_db_dataset = sub.add_parser(
        "douban-dataset", parents=[common],
        help="导入本地豆瓣影评 CSV（纯离线，不访问网站）",
    )
    s_db_dataset.add_argument(
        "--dir",
        default=str(PROJECT_ROOT / "Douban-Movie-Review-Dataset-master" / "data_all"),
        help="无表头 CSV 文件目录",
    )
    s_db_dataset.set_defaults(func=cmd_douban_dataset)

    s_tv = sub.add_parser("tmdb-videos", parents=[common],
                          help="TMDB 官方预告片采集（阶段 1g · 视频数据）：库内电影逐片拉 YouTube Trailer/Teaser")
    s_tv.add_argument("--only-with-tmdb", action="store_true",
                      help="只处理已解析出 tmdb_id 的电影（默认即是此行为，保留开关兼容）")
    s_tv.set_defaults(func=cmd_tmdb_videos)

    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except CollectorHttpError as exc:
        print(f"\n[采集失败] {exc}\n")
        print("排查建议：")
        print("  1. 确认 .env 里的 TMDB_API_KEY 已填写且有效")
        print("  2. 若本机需要代理，执行时加 --proxy http://127.0.0.1:7890")
        print("  3. 若公司网络直连正常但被系统代理干扰，加 --proxy direct")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
