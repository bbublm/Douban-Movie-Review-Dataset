"""
阶段 1b 离线自检 —— 不联网、不下载 200 MB，也能验证 IMDb 采集链路。

思路：
    自己造两个**极小的** title.ratings.tsv.gz / title.basics.tsv.gz（含表头、
    \\N 空值、残缺行、成人片、剧集等边界），然后跑完整流程。
    这样在没网/不想下载的环境里也能验证「解析 → 过滤 → 归一化 → 落盘」。

    另外单独做一项「内存纪律」测试：造 5 万行数据流式扫一遍，
    用 tracemalloc 量出 Python 侧峰值分配，证明内存不随数据量增长。

运行：
    python tests/test_imdb_offline.py
"""
from __future__ import annotations

import gzip
import json
import shutil
import sys
import tempfile
import tracemalloc
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from common.settings import settings  # noqa: E402
from ingest.schema import CORE_FIELDS, validate_record  # noqa: E402
from ingest.seed import load_legacy_movies, normalize_legacy  # noqa: E402
from ingest.sources import imdb_datasets as imdb  # noqa: E402
from ingest.sources.tmdb import normalize_movie  # noqa: E402

TMDB_FIXTURE = ROOT / "tests" / "fixtures" / "tmdb_movie_550.json"

RATINGS_HEADER = "tconst\taverageRating\tnumVotes"
BASICS_HEADER = (
    "tconst\ttitleType\tprimaryTitle\toriginalTitle\tisAdult\t"
    "startYear\tendYear\truntimeMinutes\tgenres"
)

# 每一行都是刻意设计的边界样本，最后一列注释说明它考察什么
RATINGS_ROWS = [
    "tt0137523\t8.8\t2100000",     # 正常保留（票数最高）
    "tt0000001\t9.5\t3000000",     # 剧集，票数最高，但必须被 titleType 过滤掉
    "tt0000002\t7.0\t500000",      # 成人片，必须被 isAdult 过滤掉
    "tt0000003\t9.9\t120",         # 票数 120 < 1000，过滤
    "tt0000004\t8.0\t80000",       # 正常保留
    "tt0000005\t5.2\t60000",       # 正常保留（min_rating 会用到）
    "tt0000006\t7.9\t150000",      # 正常保留
    "tt0000007\t6.5\t40000",       # 正常保留（genres 为 \\N）
]

BASICS_ROWS = [
    "tt0137523\tmovie\tFight Club\tFight Club\t0\t1999\t\\N\t139\tDrama",
    "tt0000001\ttvSeries\tFake Show\tFake Show\t0\t2010\t2015\t45\tDrama",      # 类型不符
    "tt0000002\tmovie\tAdult Flick\tAdult Flick\t1\t2001\t\\N\t90\tDrama",      # 成人片
    "tt0000003\tmovie\tObscure Indie\tObscure Indie\t0\t2018\t\\N\t88\tDrama",  # 票数太少
    "tt0000004\tmovie\tNo Runtime\tNo Runtime\t0\t1995\t\\N\t\\N\tComedy",      # 时长缺失
    "tt0000005\tmovie\tLow Score\tLow Score\t0\t2012\t\\N\t100\tHorror",        # 低分
    "tt0000006\tmovie\tSpace Trip\tSpace Trip\t0\t2014\t\\N\t121\tSci-Fi,Adventure",
    "tt0000007\tmovie\tNo Genre\tNo Genre\t0\t2005\t\\N\t95\t\\N",              # 类型缺失
    "tt9999999\tmovie\tToo Few Columns\tX\t0\t2000",                            # 残缺行（列数不符）
    "tt0000008\tshort\tA Short\ta Short\t0\t2020\t\\N\t12\tShort",              # 非 movie 类型
]

CREW_HEADER = "tconst\tdirectors\twriters"
CREW_ROWS = [
    "tt0137523\tnm0000401\tnm0000401",
    "tt0000004\tnm0000999,nm0000888\t\\N",
]

NAMES_HEADER = "nconst\tprimaryName\tbirthYear\tdeathYear\tprimaryProfession\tknownForTitles"
NAMES_ROWS = [
    "nm0000401\tDavid Fincher\t1962\t\\N\tproducer,director\ttt0137523",
    "nm0000999\tSomeone Else\t1970\t\\N\tdirector\ttt0000004",
    "nm0000888\tAnother One\t1980\t\\N\tdirector\ttt0000004",
]

_results: list[tuple[str, bool, str]] = []


def tid(tconst: str) -> int:
    """tt0137523 → 137523，与采集模块内部的内存优化键保持一致。"""
    return int(tconst[2:])


def check(name: str, ok: bool, detail: str = "") -> bool:
    _results.append((name, ok, detail))
    print(f"{'[ OK ]' if ok else '[FAIL]'} {name}" + (f"  ->  {detail}" if detail else ""))
    return ok


# ============================================================
# 造样本数据
# ============================================================


def write_gz(path: Path, header: str, rows: list[str]) -> Path:
    """按 IMDb 原始格式落盘：表头 + 制表符分隔、行尾 \\n、gzip 压缩。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8", newline="") as fh:
        fh.write(header + "\n")
        for r in rows:
            fh.write(r + "\n")
    return path


def build_sample(dir_path: Path) -> dict[str, Path]:
    return {
        "ratings": write_gz(dir_path / "title.ratings.tsv.gz", RATINGS_HEADER, RATINGS_ROWS),
        "basics": write_gz(dir_path / "title.basics.tsv.gz", BASICS_HEADER, BASICS_ROWS),
        "crew": write_gz(dir_path / "title.crew.tsv.gz", CREW_HEADER, CREW_ROWS),
        "names": write_gz(dir_path / "name.basics.tsv.gz", NAMES_HEADER, NAMES_ROWS),
    }


def main() -> int:
    print("=" * 68)
    print("  阶段 1b · IMDb Datasets 采集链路离线自检")
    print("=" * 68)

    tmp = Path(tempfile.mkdtemp(prefix="yjzs_imdb_"))
    original_lake = settings.data_lake
    original_dir = settings.imdb_dataset_dir
    settings.data_lake = str(tmp / "lake")
    settings.imdb_dataset_dir = str(tmp / "ds")
    ds = build_sample(tmp / "ds")
    print(f"  临时数据集目录：{tmp / 'ds'}\n")

    try:
        # ---------- 1. 流式 TSV 解析 ----------
        rows = list(imdb.iter_tsv(ds["ratings"], quiet=True))
        check("表头映射为 dict（不硬编码列序）",
              rows and rows[0]["tconst"] == "tt0137523" and rows[0]["numVotes"] == "2100000",
              json.dumps(rows[0], ensure_ascii=False) if rows else "解析结果为空")
        basic_rows = list(imdb.iter_tsv(ds["basics"], quiet=True))
        # 原始 10 行，其中 1 行列数不符被跳过 → 9 行
        check("列数不符的残缺行被跳过", len(basic_rows) == 9, f"解析出 {len(basic_rows)} 行（原始 10 行）")
        nr = next(r for r in basic_rows if r["tconst"] == "tt0000004")
        check("\\N 占位转成 None", nr["runtimeMinutes"] is None and nr["endYear"] is None,
              f"runtime={nr['runtimeMinutes']!r} endYear={nr['endYear']!r}")

        # ---------- 2. 表头乱序也能正确解析 ----------
        # 造一份「列顺序被打乱」的文件：表头换序，数据行也跟着换序，
        # 模拟 IMDb 调整列顺序的情况 —— 靠列序号硬编码的解析器会在这里错位。
        shuffled = tmp / "shuffled"
        shuffled.mkdir()
        reordered = ("titleType\ttconst\tgenres\truntimeMinutes\tprimaryTitle\t"
                     "isAdult\tstartYear\toriginalTitle\tendYear")
        orig_cols = BASICS_HEADER.split("\t")
        perm = [orig_cols.index(c) for c in reordered.split("\t")]
        shuffled_rows = [
            "\t".join(row.split("\t")[i] for i in perm) for row in BASICS_ROWS[:2]
        ]
        write_gz(shuffled / "title.basics.tsv.gz", reordered, shuffled_rows)
        srows = list(imdb.iter_tsv(shuffled / "title.basics.tsv.gz", quiet=True))
        check("表头乱序仍能正确取值",
              srows[0]["tconst"] == "tt0137523" and srows[0]["genres"] == "Drama"
              and srows[0]["runtimeMinutes"] == "139",
              json.dumps(srows[0], ensure_ascii=False))

        # ---------- 3. 纯文本 tsv 也支持（不解压直接用）----------
        plain = tmp / "plain.tsv"
        plain.write_text(RATINGS_HEADER + "\n" + "\n".join(RATINGS_ROWS) + "\n", encoding="utf-8")
        prows = list(imdb.iter_tsv(plain, quiet=True))
        check("纯文本 .tsv 与 .tsv.gz 都能读", len(prows) == len(RATINGS_ROWS), f"{len(prows)} 行")

        # ---------- 4. 第 1 遍：评分索引与过滤 ----------
        idx = imdb.load_rating_index(ds["ratings"], min_votes=1000, quiet=True)
        # 8 条评分里只有 tt0000003（120 票）不达标，其余 7 条都留下
        check("评分表过滤：票数阈值生效", len(idx) == 7, f"保留 {len(idx)} 条（总 8 条）")
        check("评分表过滤：票数不足的被剔除", tid("tt0000003") not in idx)
        check("索引键用 int 省内存（不是 'tt...' 字符串）",
              all(isinstance(k, int) for k in idx))
        idx2 = imdb.load_rating_index(ds["ratings"], min_votes=1000, min_rating=7.5, quiet=True)
        check("评分表过滤：评分下限生效",
              tid("tt0000005") not in idx2 and tid("tt0137523") in idx2,
              f"评分≥7.5 保留 {len(idx2)} 条")

        # ---------- 5. 第 2 遍：类型 / 成人片过滤 + 归一化 ----------
        recs = list(imdb.collect(ds["basics"], idx, title_types={"movie"}, quiet=True))
        got = {r["imdb_id"] for r in recs}
        # 7 条评分候选里：tt0000001 是剧集、tt0000002 是成人片、tt0000008 是短片 →
        # 分别被 titleType / isAdult / titleType 三道闸门剔除
        check("类型过滤：剧集/短片被剔除",
              "tt0000001" not in got and "tt0000008" not in got, str(sorted(got)))
        check("成人片被过滤", "tt0000002" not in got)
        check("命中条数正确", len(recs) == 5, f"{len(recs)} 条 → {sorted(got)}")

        fc = next(r for r in recs if r["imdb_id"] == "tt0137523")
        check("imdb_id 保留 tt 前缀", fc["imdb_id"] == "tt0137523")
        check("片名与原始片名", fc["title"] == "Fight Club" and fc["original_title"] == "Fight Club")
        check("年份转成 int", fc["release_year"] == 1999 and isinstance(fc["release_year"], int))
        check("片长转成 int", fc["runtime"] == 139 and isinstance(fc["runtime"], int))
        check("英文类型 → 中文类型", fc["genres_zh"] == ["剧情"], str(fc["genres_zh"]))
        check("评分与票数（10 分制，与 TMDB 同量纲）",
              fc["vote_average"] == 8.8 and fc["vote_count"] == 2100000,
              f"{fc['vote_average']} / {fc['vote_count']}")
        check("精确上映日如实留空（IMDb 数据集不含）", fc["release_date"] is None)

        st = next(r for r in recs if r["imdb_id"] == "tt0000006")
        check("多类型映射（Sci-Fi,Adventure → 科幻,冒险）",
              st["genres_zh"] == ["科幻", "冒险"], str(st["genres_zh"]))

        nrt = next(r for r in recs if r["imdb_id"] == "tt0000004")
        check("时长 \\N → None（不是 0，也不是字符串）", nrt["runtime"] is None)

        # ---------- 6. 与另外两个源的结构对齐（阶段 2 融合的前提）----------
        missing = validate_record(fc)
        check("IMDb 记录覆盖 CORE_FIELDS", not missing, f"缺：{missing}")

        tmdb_rec = normalize_movie(json.loads(TMDB_FIXTURE.read_text(encoding="utf-8")))
        legacy = load_legacy_movies()
        legacy_rec = normalize_legacy(legacy[0]) if legacy else {}
        for label, rec in (("TMDB", tmdb_rec), ("旧片库", legacy_rec), ("IMDb", fc)):
            miss = validate_record(rec)
            check(f"{label} 记录覆盖 CORE_FIELDS", not miss, f"缺：{miss}")

        # ---------- 7. --limit：只保留票数最高的 N 部 ----------
        top2 = imdb.load_rating_index(ds["ratings"], min_votes=1000, top_n=2, quiet=True)
        check("--limit 用 heapq 取票数最高的 N 条",
              set(top2) == {tid("tt0137523"), tid("tt0000001")},
              f"取出 {sorted(top2)}")
        limited = list(imdb.collect(ds["basics"], top2, title_types={"movie"}, limit=1, quiet=True))
        check("--limit 在输出阶段同样生效", len(limited) == 1, f"{len(limited)} 条")

        # ---------- 8. 流式落盘 ----------
        out = settings.lake("interim") / "imdb_movies.jsonl"
        n = imdb.write_jsonl_stream(iter(recs), out)
        lines = out.read_text(encoding="utf-8").strip().splitlines()
        back = json.loads(lines[0])
        check("JSONL 流式落盘且可回读",
              n == 5 and len(lines) == 5 and back["imdb_id"] == "tt0137523", f"{n} 行")

        # ---------- 9. 可选：crew + names 补导演 ----------
        filled = imdb.enrich_directors(out, ds["crew"], ds["names"], quiet=True)
        after = [json.loads(x) for x in out.read_text(encoding="utf-8").strip().splitlines()]
        nrt2 = next(r for r in after if r["imdb_id"] == "tt0000004")
        fc2 = next(r for r in after if r["imdb_id"] == "tt0137523")
        check("补导演：多人用顿号连接", nrt2["director"] == "Someone Else、Another One",
              str(nrt2["director"]))
        check("补导演：单人也正确", fc2["director"] == "David Fincher" and filled == 2,
              f"filled={filled} director={fc2['director']}")
        check("补导演后数据血缘更新", fc2["source"] == "imdb+crew", fc2["source"])

        # ---------- 10. 缺数据集时给出可读结果，不抛异常 ----------
        missing_dir = tmp / "nowhere"
        check("找不到数据集时返回 None（不抛异常）",
              imdb.find_dataset("ratings", missing_dir) is None)
        check("数据集清单包含必要项与可选项",
              imdb.DATASETS["ratings"].required and imdb.DATASETS["basics"].required
              and not imdb.DATASETS["akas"].required)
        check("下载地址拼接正确",
              imdb.DATASETS["basics"].url == "https://datasets.imdbws.com/title.basics.tsv.gz",
              imdb.DATASETS["basics"].url)

        # ---------- 11. 内存纪律：5 万行流式解析，峰值分配有界 ----------
        # 造 5 万行合法的 movie 记录 + 对应评分，模拟真实数据集的结构
        big_ratings = [f"tt{i:07d}\t8.{i % 10}\t{1000 + i}" for i in range(50_000)]
        big_basics = [
            f"tt{i:07d}\tmovie\tMovie {i}\tMovie {i}\t0\t{1980 + i % 45}\t\\N\t{90 + i % 60}\tDrama"
            for i in range(50_000)
        ]
        big_dir = tmp / "big"
        b_ratings = write_gz(big_dir / "title.ratings.tsv.gz", RATINGS_HEADER, big_ratings)
        b_basics = write_gz(big_dir / "title.basics.tsv.gz", BASICS_HEADER, big_basics)

        tracemalloc.start()
        big_idx = imdb.load_rating_index(b_ratings, min_votes=1000, quiet=True)
        big_out = settings.lake("interim") / "big.jsonl"
        big_n = imdb.write_jsonl_stream(
            imdb.collect(b_basics, big_idx, title_types={"movie"}, quiet=True), big_out
        )
        _, py_peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

        peak_mb = py_peak / 1024 / 1024
        check("5 万行两遍扫描：Python 侧峰值分配 < 40 MB",
              peak_mb < 40, f"实测 {peak_mb:.1f} MB（内存不随数据量线性增长）")
        check("大数据集也正确处理", big_n == 50_000, f"输出 {big_n:,} 条")

    finally:
        settings.data_lake = original_lake
        settings.imdb_dataset_dir = original_dir
        shutil.rmtree(tmp, ignore_errors=True)

    passed = sum(1 for _, ok, _ in _results if ok)
    total = len(_results)
    print("-" * 68)
    print(f"  结果：{passed}/{total} 项通过")
    print("  ✅ IMDb 采集链路离线自检全部通过" if passed == total
          else "  ⚠️  存在失败项，请检查上面的 [FAIL]")
    print("=" * 68)
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
