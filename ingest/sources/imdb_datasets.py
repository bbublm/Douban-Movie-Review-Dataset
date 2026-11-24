"""
IMDb Datasets 采集器 —— 阶段 1b。

数据源：IMDb 官方公开数据集 https://datasets.imdbws.com/
    免费、无需 API Key、每天发布全量快照、明确允许科研与教学使用。
    IMDb 自己没有开放 API（官方 API 早已下线），但这份数据集比 API 更适合做分析。

=============================================================================
★ 内存纪律 —— 这是本模块最重要的设计约束，不是可选项
=============================================================================
    title.basics.tsv.gz 解压后约 900 MB、1200 万行；
    title.ratings.tsv.gz 解压后约 25 MB、150 万行。

    常见写法 `pd.read_csv("title.basics.tsv.gz")` 的峰值内存要 4~5 GB，
    普通笔记本直接卡死 —— 这也是很多同学做 IMDb 分析翻车的地方。

    本模块改用「两遍扫描 + 有界内存」，全程不把数据集读进内存：

        第 1 遍  扫 ratings（7 MB）→ 只留 投票数 ≥ 阈值 的条目，做成 dict
                 字典键用 int（int(tconst[2:])）而不是 'tt0137523' 字符串，
                 80 万条能省一半内存；再用 heapq 只留票数最高的 N 条
        第 2 遍  扫 basics（190 MB）→ 逐行判断是否命中，命中就立刻转记录、
                 立刻写 JSONL，从不攒成 list
        可选第 3 遍 扫 crew + names → 只给「已命中的影片」补导演名

    峰值内存 ≈ 过滤后的 ratings 字典（几万条，约 10~30 MB）+ 一行缓冲，
    **与数据集总行数无关**。跑完会打印实测峰值内存供核对。

=============================================================================
磁盘占用（结论：下载约 200 MB，不额外解压）
=============================================================================
    我们**从不把 .tsv.gz 解压到磁盘**，gzip.open 是流式解压、边解边丢，
    所以除了压缩包本身，不占额外磁盘。默认只下两个文件：
        title.ratings.tsv.gz   ~7 MB   （评分与票数）
        title.basics.tsv.gz    ~190 MB （片名、年份、时长、类型）
    其余文件（akas 400MB / principals 600MB / names 250MB）默认不下载，
    需要时用 --files 指定。

产物：
    data_lake/imdb_datasets/*.tsv.gz        原始数据集（压缩包，可复用/可删）
    data_lake/interim/imdb_movies.jsonl     归一化后的统一结构记录
"""
from __future__ import annotations

import csv
import gzip
import heapq
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

import httpx

from common.settings import PROJECT_ROOT, settings

# ============================================================
# 数据集登记表
# ============================================================


@dataclass(frozen=True)
class DatasetSpec:
    key: str
    filename: str
    size_mb: int
    required: bool
    note: str

    @property
    def url(self) -> str:
        return f"https://datasets.imdbws.com/{self.filename}"


# size_mb 是官方公布的大致体积，用来在下载前提示用户「要下多少」
DATASETS: dict[str, DatasetSpec] = {
    "ratings": DatasetSpec("ratings", "title.ratings.tsv.gz", 7, True, "评分与票数（第 1 遍扫描用）"),
    "basics": DatasetSpec("basics", "title.basics.tsv.gz", 190, True, "片名/年份/时长/类型（第 2 遍扫描用）"),
    "crew": DatasetSpec("crew", "title.crew.tsv.gz", 60, False, "导演与编剧 nconst（可选，补导演用）"),
    "names": DatasetSpec("names", "name.basics.tsv.gz", 250, False, "人物姓名（可选，配合 crew 用）"),
    "akas": DatasetSpec("akas", "title.akas.tsv.gz", 400, False, "各语言别名（可选，可补中文片名）"),
    "principals": DatasetSpec("principals", "title.principals.tsv.gz", 600, False, "演员表（体积大，本项目不用）"),
}

UA = "YingJianZhiSou/0.1 (course project; contact: local)"

# ============================================================
# IMDb 英文类型 → 中文类型
#   刻意对齐 TMDB zh-CN 的用词，阶段 2 融合时两边的分面值才能合并成一类，
#   否则会出现「剧情」和「Drama」两个分面桶。
# ============================================================

GENRE_EN_ZH: dict[str, str] = {
    "Action": "动作",
    "Adult": "成人",
    "Adventure": "冒险",
    "Animation": "动画",
    "Biography": "传记",
    "Comedy": "喜剧",
    "Crime": "犯罪",
    "Documentary": "纪录片",
    "Drama": "剧情",
    "Family": "家庭",
    "Fantasy": "奇幻",
    "Film-Noir": "黑色电影",
    "Game-Show": "游戏节目",
    "History": "历史",
    "Horror": "恐怖",
    "Music": "音乐",
    "Musical": "歌舞",
    "Mystery": "悬疑",
    "News": "新闻",
    "Reality-TV": "真人秀",
    "Romance": "爱情",
    "Sci-Fi": "科幻",
    "Short": "短片",
    "Sport": "运动",
    "Talk-Show": "脱口秀",
    "Thriller": "惊悚",
    "War": "战争",
    "Western": "西部",
}


# ============================================================
# 路径与下载
# ============================================================


def dataset_dir(override: str | Path | None = None) -> Path:
    """数据集存放目录。默认 <data_lake>/imdb_datasets，可用 .env 的 IMDB_DATASET_DIR 覆盖。"""
    if override:
        p = Path(override)
        return p if p.is_absolute() else (PROJECT_ROOT / p).resolve()
    if settings.imdb_dataset_dir.strip():
        p = Path(settings.imdb_dataset_dir.strip())
        return p if p.is_absolute() else (PROJECT_ROOT / p).resolve()
    return settings.lake("imdb_datasets")


def find_dataset(key: str, directory: Path | None = None) -> Path | None:
    """在目录里找某个数据集压缩包；找不到返回 None（调用方给提示，不抛异常）。"""
    spec = DATASETS.get(key)
    if spec is None:
        raise KeyError(f"未知数据集：{key}，可选 {list(DATASETS)}")
    path = (directory or dataset_dir()) / spec.filename
    return path if path.exists() and path.stat().st_size > 0 else None


def download_dataset(
    key: str,
    directory: Path | None = None,
    *,
    force: bool = False,
    proxy: str = "",
    progress: bool = True,
) -> Path:
    """流式下载数据集压缩包，支持断点续传（.part 临时文件 + Range 请求）。

    重点：用 httpx.stream 边下边写盘，不在内存里攒整个响应体
    （190 MB 的文件如果 resp.content 一把拿，内存直接多 190 MB）。
    """
    spec = DATASETS[key]
    directory = directory or dataset_dir()
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / spec.filename

    if target.exists() and target.stat().st_size > 0 and not force:
        if progress:
            print(f"  [跳过] {spec.filename} 已存在（{_mb(target.stat().st_size)}）")
        return target

    part = target.with_name(target.name + ".part")
    done = part.stat().st_size if part.exists() and not force else 0
    if force and part.exists():
        part.unlink()
        done = 0

    headers = {"User-Agent": UA}
    if done:
        headers["Range"] = f"bytes={done}-"

    kwargs: dict[str, Any] = {"timeout": 60.0, "follow_redirects": True}
    if proxy.strip().lower() == "direct":
        kwargs["trust_env"] = False
    elif proxy.strip():
        kwargs["proxy"] = proxy.strip()

    if progress:
        print(f"  [下载] {spec.filename}  约 {spec.size_mb} MB"
              + (f"  从 {_mb(done)} 处续传" if done else ""))

    mode = "ab" if done else "wb"
    written = done
    last_report = 0
    try:
        with httpx.stream("GET", spec.url, headers=headers, **kwargs) as resp:
            if resp.status_code == 416:
                # 服务端认为已下完，直接把 .part 改名
                resp.close()
                part.replace(target)
                return target
            if resp.status_code not in (200, 206):
                resp.raise_for_status()
            if done and resp.status_code == 200:
                # 服务端不支持 Range，从头重下
                if progress:
                    print("    服务端不支持断点续传，改为重新下载")
                mode, written = "wb", 0
            with part.open(mode) as fh:
                for chunk in resp.iter_bytes(1024 * 256):
                    fh.write(chunk)
                    written += len(chunk)
                    if progress and written - last_report >= 20 * 1024 * 1024:
                        last_report = written
                        print(f"    已下 {_mb(written)} …")
    except httpx.HTTPError as exc:
        raise RuntimeError(
            f"下载 {spec.filename} 失败：{type(exc).__name__} {exc}\n"
            f"  可先手动下载后放进 {directory}\n"
            f"  地址：{spec.url}"
        ) from exc

    part.replace(target)
    if progress:
        print(f"    完成 {spec.filename}（{_mb(target.stat().st_size)}）")
    return target


def _mb(n: int) -> str:
    return f"{n / 1024 / 1024:.1f} MB"


# ============================================================
# 演示数据集：不下载 200 MB 也能把整条链路跑通
# ============================================================

BASICS_HEADER = (
    "tconst\ttitleType\tprimaryTitle\toriginalTitle\tisAdult\t"
    "startYear\tendYear\truntimeMinutes\tgenres"
)
RATINGS_HEADER = "tconst\taverageRating\tnumVotes"
CREW_HEADER = "tconst\tdirectors\twriters"
NAMES_HEADER = "nconst\tprimaryName\tbirthYear\tdeathYear\tprimaryProfession\tknownForTitles"

_DEMO_GENRES = [
    "Drama", "Action", "Comedy", "Sci-Fi,Adventure", "Horror",
    "Crime,Mystery", "Romance", "Animation,Family", "War", "Western",
]
_DEMO_DIRECTORS = [
    ("nm9000001", "示例导演·甲"),
    ("nm9000002", "示例导演·乙"),
    ("nm9000003", "示例导演·丙"),
    ("nm9000004", "示例导演·丁"),
]


def _write_gz(path: Path, header: str, rows: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, "wt", encoding="utf-8", newline="") as fh:
        fh.write(header + "\n")
        for r in rows:
            fh.write(r + "\n")
    return path


def build_demo_datasets(directory: str | Path | None = None, *, rows: int = 400) -> dict[str, Path]:
    """造一份极小的本地示例数据集（合成数据，非真实 IMDb 内容）。

    用途：在**不下载 200 MB、不联网**的前提下跑通「解析 → 过滤 → 归一化 → 落盘」，
    以及验证内存读数。前 6 行刻意埋了各类边界（剧集、成人片、票数不足、
    \\N 空值、列数残缺），这样一份演示数据就能把过滤逻辑全部覆盖到。

    合成 id 用 tt9xxxxxx 段，与真实 IMDb 的 tt0xxxxxx 不冲突，不会污染真实数据。
    """
    directory = Path(directory) if directory else dataset_dir()
    directory.mkdir(parents=True, exist_ok=True)

    basics: list[str] = []
    ratings: list[str] = []
    crew: list[str] = []
    names = [f"{n}\t{name}\t1960\t\\N\tdirector\ttt9000000" for n, name in _DEMO_DIRECTORS]

    def add(tid: str, title: str, *, ttype="movie", adult="0", year=2000,
            runtime="100", genres="Drama", rating="7.5", votes="5000") -> None:
        basics.append(
            f"{tid}\t{ttype}\t{title}\t{title}\t{adult}\t{year}\t\\N\t{runtime}\t{genres}"
        )
        ratings.append(f"{tid}\t{rating}\t{votes}")

    # ---- 前 6 行是边界样本，用来验证过滤规则 ----
    add("tt9000001", "Demo TV Series", ttype="tvSeries", year=2010, genres="Drama",
        rating="9.5", votes="9000000")            # 剧集：应被 titleType 过滤
    add("tt9000002", "Demo Adult Movie", adult="1", rating="7.0", votes="800000")  # 成人片：应被过滤
    add("tt9000003", "Demo Obscure", rating="9.9", votes="50")                    # 票数不足：应被过滤
    add("tt9000004", "Demo No Runtime", runtime="\\N", genres="Comedy")           # 时长/类型缺失
    basics.append("tt9000999\tmovie\tBroken Row\tB\t0\t2001")                     # 列数残缺：应被跳过
    add("tt9000005", "Demo Short Film", ttype="short", genres="Short")            # 短片：应被过滤

    # ---- 其余为正常样本 ----
    for i in range(6, rows):
        tid = f"tt9{i:06d}"
        add(
            tid,
            f"Demo Movie {i:04d}",
            year=1980 + (i % 45),
            runtime=str(80 + (i % 70)),
            genres=_DEMO_GENRES[i % len(_DEMO_GENRES)],
            rating=f"{4 + (i % 60) / 10:.1f}",
            votes=str(1000 + i * 137),
        )
        dn, dname = _DEMO_DIRECTORS[i % len(_DEMO_DIRECTORS)]
        crew.append(f"{tid}\t{dn}\t\\N")

    out = {
        "ratings": _write_gz(directory / "title.ratings.tsv.gz", RATINGS_HEADER, ratings),
        "basics": _write_gz(directory / "title.basics.tsv.gz", BASICS_HEADER, basics),
        "crew": _write_gz(directory / "title.crew.tsv.gz", CREW_HEADER, crew),
        "names": _write_gz(directory / "name.basics.tsv.gz", NAMES_HEADER, names),
    }
    (directory / "README_DEMO.txt").write_text(
        "本目录中的 *.tsv.gz 是【合成示例数据】，由 `run_collect imdb --demo` 生成，\n"
        "不是真实的 IMDb 数据集。仅用于离线跑通采集链路与验证内存占用。\n"
        "要换成真实数据：删掉这些文件，然后执行\n"
        "    python -m ingest.run_collect imdb --download\n",
        encoding="utf-8",
    )
    return out


# ============================================================
# 流式 TSV 解析（内存纪律的落点）
# ============================================================

# 进度提示的默认粒度：按行数报，不预读总行数（预读要多扫一遍文件）
DEFAULT_REPORT_EVERY = {
    "title.ratings.tsv.gz": 500_000,
    "title.basics.tsv.gz": 2_000_000,
    "title.crew.tsv.gz": 2_000_000,
    "name.basics.tsv.gz": 2_000_000,
}


def iter_tsv(
    path: Path,
    *,
    report_every: int = 0,
    label: str = "",
    quiet: bool = False,
) -> Iterator[dict]:
    """逐行流式读取 IMDb 的 .tsv / .tsv.gz，每次只 yield 一行的 dict。

    三个细节决定了它「耐脏」：
        1. 列名从表头读，不硬编码列序号 —— IMDb 调整列顺序也不会解析错位；
        2. `\\N` 是 IMDb 的空值占位，统一转成 None，避免把字符串 "\\N" 当年份；
        3. 列数对不上的残缺行直接跳过 —— 下载被中断的文件不会污染结果。
    """
    opener = gzip.open if path.suffix == ".gz" else open
    if not report_every:
        report_every = DEFAULT_REPORT_EVERY.get(path.name, 1_000_000)

    with opener(path, "rt", encoding="utf-8", errors="replace", newline="") as fh:
        reader = csv.reader(fh, delimiter="\t", quoting=csv.QUOTE_NONE)
        try:
            header = [h.strip() for h in next(reader)]
        except StopIteration:
            return
        width = len(header)
        scanned = 0
        for row in reader:
            scanned += 1
            if not quiet and report_every and scanned % report_every == 0:
                print(f"    {label}已扫 {scanned:,} 行 …")
            if len(row) != width:
                continue
            # 惰性构造，且 y= 用 None 替代 "\N"
            yield {k: (None if v == r"\N" else v) for k, v in zip(header, row)}


def _int(value: Any) -> int | None:
    if value is None:  # 上游已把 \N 转成 None
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def _tid_key(tconst: str) -> int | None:
    """`tt0137523` → 137523。

    内存小技巧：字典键用 int 比用 9 字符字符串省一半以上内存。
    全量 ratings 有 150 万条，过滤后也有几十万条，这个差异挺可观。
    """
    if not tconst or not tconst.startswith("tt"):
        return None
    try:
        return int(tconst[2:])
    except ValueError:
        return None


# ============================================================
# 归一化：IMDb 行 → 统一电影记录
# ============================================================


def normalize_title(row: dict, rating: tuple[float, int] | None = None) -> dict:
    """title.basics 的一行 + 对应的评分 → 统一结构记录。

    字段名严格覆盖 ingest/schema.py 的 CORE_FIELDS，
    缺失的信息（中文名、海报、导演、简介）一律填 None / 空列表 ——
    这些由阶段 1a 的 TMDB 与阶段 1c/1d 的维基数据在融合阶段补齐。
    """
    tconst = _clean(row.get("tconst"))
    title_type = _clean(row.get("titleType")) or None
    primary = _clean(row.get("primaryTitle"))
    original = _clean(row.get("originalTitle")) or primary

    genres_en = [g.strip() for g in _clean(row.get("genres")).split(",") if g.strip()]
    genres_zh = [GENRE_EN_ZH.get(g, g) for g in genres_en]

    rating_avg, rating_votes = (rating if rating else (None, None))

    return {
        # ---- 主键与实体对齐 ----
        "tmdb_id": None,                 # 由 TMDB 侧在阶段 2 融合时回填
        "imdb_id": tconst or None,       # 保留 tt 前缀，这是 IMDb 官方主键写法
        # ---- 片名 ----
        "title": primary or original,
        "title_zh": None,                # IMDb 无中文名，阶段 2 用维基/别名补
        "title_en": primary or original,
        "original_title": original,
        # ---- 时间与时长 ----
        # IMDb 数据集不含精确上映日（只有年份），要精确到日得用 title.akas，
        # 这里诚实地填 None，不伪造 "1999-01-01" 污染后续日期字段。
        "release_date": None,
        "release_year": _int(row.get("startYear")),
        "runtime": _int(row.get("runtimeMinutes")),
        # ---- 文本 ----
        "overview": "",
        "tagline": "",
        "status": "",
        # ---- 分类与人物 ----
        "genres_zh": genres_zh or ["剧情"],
        "genres_en": genres_en,
        "genre_ids": [],
        "keywords": [],
        "director": None,
        "cast": [],
        # ---- 评分与热度（IMDb 是 10 分制，与 TMDB 同量纲，可直接比）----
        "vote_average": rating_avg if rating_avg is not None else 0.0,
        "vote_count": rating_votes if rating_votes is not None else 0,
        "popularity": 0.0,
        # ---- 地域与语言 ----
        "original_language": None,
        "spoken_languages": [],
        "production_countries": [],
        "production_country_codes": [],
        # ---- 图片 ----
        "poster_url": None,
        "backdrop_url": None,
        # ---- IMDb 特有字段（融合时作交叉校验用）----
        "imdb_rating": rating_avg,
        "imdb_votes": rating_votes,
        "title_type": title_type,
        "is_adult": row.get("isAdult") == "1",
        # ---- 数据血缘 ----
        "source": "imdb",
        "collected_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


# ============================================================
# 编排：两遍扫描
# ============================================================


def load_rating_index(
    ratings_path: Path,
    *,
    min_votes: int = 1000,
    min_rating: float = 0.0,
    top_n: int | None = None,
    quiet: bool = False,
) -> dict[int, tuple[float, int]]:
    """第 1 遍：扫 ratings，产出「值得保留的影片」索引。

    返回 {tconst_int: (平均分, 票数)}。

    内存控制：
        - 先用 min_votes / min_rating 把 150 万条砍到几万条；
        - 若给了 top_n（对应 CLI 的 --limit），用 heapq.nlargest 只保留
          票数最高的 top_n 条，堆大小恒定，不会因为数据量上涨而变胖。
    """
    kept: dict[int, tuple[float, int]] = {}
    if top_n:
        # 维护一个「大小为 top_n 的小顶堆」：堆顶永远是当前入选者里票数最低的，
        # 新来一条比堆顶强就替换掉它 —— 堆大小恒定，内存有界。
        # ⚠️ 必须用 heappush：直接 list.append 会破坏堆不变量，
        #    之后 heappop 弹出的就不是真正的最小值（曾因此淘汰错记录，已修）。
        heap: list[tuple[int, int, float]] = []
        for row in iter_tsv(ratings_path, label="评分表 ", quiet=quiet):
            votes = _int(row.get("numVotes"))
            if votes is None or votes < min_votes:
                continue
            avg = _float(row.get("averageRating"))
            if avg is None or avg < min_rating:
                continue
            key = _tid_key(_clean(row.get("tconst")))
            if key is None:
                continue
            heapq.heappush(heap, (votes, key, avg))
            if len(heap) > top_n:
                heapq.heappop(heap)  # 弹掉当前最小的，堆里始终是票数最高的一批
        kept = {k: (a, v) for v, k, a in heap}
    else:
        for row in iter_tsv(ratings_path, label="评分表 ", quiet=quiet):
            votes = _int(row.get("numVotes"))
            if votes is None or votes < min_votes:
                continue
            avg = _float(row.get("averageRating"))
            if avg is None or avg < min_rating:
                continue
            key = _tid_key(_clean(row.get("tconst")))
            if key is None:
                continue
            kept[key] = (avg, votes)
    return kept


def collect(
    basics_path: Path,
    rating_index: dict[int, tuple[float, int]],
    *,
    title_types: set[str] | None = None,
    exclude_adult: bool = True,
    limit: int | None = None,
    quiet: bool = False,
) -> Iterator[dict]:
    """第 2 遍：扫 basics，命中的行**立刻 yield**，调用方立刻写盘。

    这个函数返回生成器而不是 list —— 这是内存纪律的关键：
    12 万条记录如果攒成 list，光 Python dict 的开销就要 200 MB 以上；
    流式 yield 的话，同时只存在一条记录。
    """
    title_types = title_types or {"movie"}
    emitted = 0
    for row in iter_tsv(basics_path, label="影片表 ", quiet=quiet):
        if exclude_adult and row.get("isAdult") == "1":
            continue
        ttype = _clean(row.get("titleType"))
        if title_types and ttype not in title_types:
            continue
        key = _tid_key(_clean(row.get("tconst")))
        if key is None:
            continue
        rating = rating_index.get(key)
        if rating is None:
            continue
        yield normalize_title(row, rating)
        emitted += 1
        if limit and emitted >= limit:
            return


# ============================================================
# 可选：补导演（crew + names）
# ============================================================


def enrich_directors(
    records_path: Path,
    crew_path: Path,
    names_path: Path,
    *,
    max_names: int = 3,
    quiet: bool = False,
) -> int:
    """给已经落盘的 JSONL 补导演名，返回补上的条数。

    为什么要额外两步：
        basics 里没有人物信息，导演在 title.crew（nconst 列表），
        名字还要再去 name.basics 里查 —— 这是典型的「多源实体对齐」，
        答辩时讲这条链路比讲"我调了个 API"有含量得多。

    内存：只把「已保留影片所需的那几个 nconst」装进字典，
    而不是把 1300 万条 name.basics 全读进来。
    """
    if not records_path.exists():
        return 0

    # 1) 先读一遍我们已经采集的记录，收集需要的 tconst 与对应位置
    offsets: dict[int, int] = {}
    with records_path.open(encoding="utf-8") as fh:
        for idx, line in enumerate(fh):
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            key = _tid_key(rec.get("imdb_id") or "")
            if key is not None:
                offsets[key] = idx
    if not offsets:
        return 0

    # 2) 扫 crew，只留住命中的影片 → directors 的 nconst 列表
    wanted_nconst: dict[int, list[str]] = {}
    for row in iter_tsv(crew_path, label="剧组表 ", quiet=quiet):
        key = _tid_key(_clean(row.get("tconst")))
        if key not in offsets:
            continue
        dirs = [d.strip() for d in _clean(row.get("directors")).split(",") if d.strip()]
        if dirs:
            wanted_nconst[key] = dirs[:max_names]

    nconst_ids = {n for dirs in wanted_nconst.values() for n in dirs}
    if not nconst_ids:
        return 0

    # 3) 扫 names，只留需要的 nconst → 姓名
    name_of: dict[str, str] = {}
    for row in iter_tsv(names_path, label="人物表 ", quiet=quiet):
        nconst = _clean(row.get("nconst"))
        if nconst in nconst_ids:
            name_of[nconst] = _clean(row.get("primaryName"))

    # 4) 回写：整文件重写一次（记录量在十万级，几百 MB，一次性可接受）
    tmp = records_path.with_suffix(".jsonl.tmp")
    filled = 0
    with records_path.open(encoding="utf-8") as src, tmp.open("w", encoding="utf-8") as dst:
        for idx, line in enumerate(src):
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            key = _tid_key(rec.get("imdb_id") or "")
            dirs = wanted_nconst.get(key) if key is not None else None
            if dirs:
                names = [name_of[n] for n in dirs if n in name_of]
                if names:
                    rec["director"] = "、".join(names)
                    rec["source"] = "imdb+crew"
                    filled += 1
            dst.write(json.dumps(rec, ensure_ascii=False) + "\n")
    tmp.replace(records_path)
    return filled


# ============================================================
# 落盘
# ============================================================


def write_jsonl_stream(records: Iterator[dict], path: Path) -> int:
    """流式写 JSONL：来一条写一条，永不把结果攒在内存里。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n += 1
    return n
