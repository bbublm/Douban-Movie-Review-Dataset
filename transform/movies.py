"""
多源电影记录融合 —— 阶段 2 的核心。

输入：interim 里各源的记录（同一部电影可能散在 1~4 个源里，字段各有缺失）
输出：一部电影一条，每个字段取「各源中最可信的那个值」

================================================================
一、算法：一边扫一边合（并查集思路），不能先分组
================================================================
    一条记录可能同时带 imdb_id 和 tmdb_id —— 它是一座**桥**，
    把「只有 imdb_id 的 IMDb 记录」和「只有 tmdb_id 的 TMDB 记录」连起来。

    所以不能按主键分组（一旦先分组，桥就被丢掉了），必须边扫边合：

        keys = film_keys(rec)               # 这条记录有哪些键
        hit  = 这些键当前分别落在哪几组？
        0 组 → 新建一组
        1 组 → 直接并进去
        2+ 组 → 这几组原来是同一部电影！先互相合并，再并进去（bridge）

    实现上两个字典就够了：
        key2gid     key → 组号
        gid2bucket  组号 → 正在合并中的记录（bucket）
    合并 2+ 组时，把被吸收组的 key 全部改指到目标组，再把它的 bucket 并过来。

================================================================
二、字段优先级为什么是一张「明文表」
================================================================
    「哪个源的这个字段更可信」是业务判断，推不出来，只能写死：

        中文片名 → legacy(人工核过) ≈ TMDB(官方 zh-CN) > Wikidata > IMDb
        IMDb 根本没有中文名和海报，给它排最后不是歧视，是它真没有

    写死成 SCALAR_PRIORITY 的好处：评审时一眼看出依据，要改只动一处，
    而且可以拿它直接生成文档。代价是「新加一个源要记得来补表」——
    所以 tests 里有一条断言守护这张表的完备性。

================================================================
三、血缘必须留下
================================================================
    融合后一条记录是由哪几个源拼出来的、拼了几条原始记录，
    全部记进 sources / source_count / merged_from / match_keys。
    没有这层血缘，后面发现某条数据错了根本追不回是哪个源的锅。
"""
from __future__ import annotations

import hashlib
import time
from typing import Any, Iterable, Iterator

from ingest.schema import CORE_FIELDS
from transform.clean import (
    clean_str,
    has_han,
    is_missing,
    to_float,
    to_int,
    uniq_list,
    year_of,
)
from transform.keys import film_keys, normalize_title
from transform.normalize import (
    normalize_countries,
    normalize_genres,
    normalize_languages,
    normalize_places,
    pick_primary_country,
)

# 记录里的 source 可能是复合值（"imdb+crew" / "wikidata+wikipedia"），先归一
SOURCE_ALIASES: dict[str, str] = {
    "legacy": "legacy",
    "chinese-domestic": "legacy",
    "tmdb": "tmdb",
    "imdb": "imdb",
    "imdb+crew": "imdb",
    "wikidata": "wikidata",
    "wikidata+wikipedia": "wikidata",
    "wikipedia": "wikidata",
}

# ---- 标量字段的取值优先级（左 → 右 = 可信度从高到低）----
SCALAR_PRIORITY: dict[str, tuple[str, ...]] = {
    # 片名：中文名信 legacy / TMDB
    "title_zh":          ("legacy", "tmdb", "wikidata", "imdb"),
    "title":             ("tmdb", "legacy", "wikidata", "imdb"),
    "title_en":          ("tmdb", "imdb", "wikidata", "legacy"),
    "original_title":    ("tmdb", "imdb", "wikidata", "legacy"),
    # 剧情文本：TMDB 的 overview 是官方简介；Wikidata 那份其实是维基摘要
    "overview":          ("tmdb", "legacy", "wikidata", "imdb"),
    "tagline":           ("tmdb", "legacy", "imdb", "wikidata"),
    "status":            ("tmdb", "legacy", "imdb", "wikidata"),
    # 时间：TMDB 精确到日、Wikidata 也到日，IMDb 只有年份
    "release_date":      ("tmdb", "wikidata", "imdb", "legacy"),
    "release_year":      ("tmdb", "wikidata", "imdb", "legacy"),
    "runtime":           ("tmdb", "wikidata", "imdb", "legacy"),
    # 评分与热度：同为 10 分制，TMDB 覆盖面更广
    "vote_average":      ("tmdb", "imdb", "legacy", "wikidata"),
    "vote_count":        ("tmdb", "imdb", "legacy", "wikidata"),
    "popularity":        ("tmdb", "imdb", "legacy", "wikidata"),
    # 票房与预算：仅 TMDB 有（美元），票房分析展厅的数据源
    "revenue":           ("tmdb",),
    "budget":            ("tmdb",),
    # 人物：老片库的导演是人工录的，比机器抽的准
    "director":          ("legacy", "tmdb", "wikidata", "imdb"),
    # 地域与语言
    "original_language": ("tmdb", "imdb", "wikidata", "legacy"),
    # 图片
    "poster_url":        ("tmdb", "legacy", "wikidata", "imdb"),
    "backdrop_url":      ("tmdb", "legacy", "wikidata", "imdb"),
}

# ---- 列表字段：各源取并集（去重保序）----
LIST_FIELDS: tuple[str, ...] = (
    "genres_zh", "genres_en", "genre_ids", "keywords", "cast",
    "spoken_languages", "production_countries", "production_country_codes",
)

# ---- 各源的「特色字段」：不属于统一合同，但融合时要带过去 ----
# 取第一个非空值（顺序 = 优先级），例如 imdb_rating 只有 IMDb 会给
EXTRA_FIELDS: tuple[str, ...] = (
    "wikidata_qid", "wikidata_url", "wikipedia_title", "wikipedia_url",
    "wikipedia_extract", "imdb_rating", "imdb_votes", "title_type",
    "upstream", "id_resolved",
    # 阶段 1f：豆瓣数据源（解除「禁采集豆瓣」红线后新增；公开页慢速采集、不挂账号）
    "douban_id", "douban_rating", "douban_score", "douban_votes",
    "douban_comments", "douban_short_comments", "douban_long_comments",
)


# ============================================================
# 源标签与优先级排序
# ============================================================

def source_of(record: dict) -> str:
    """把记录里的 source 归一成 'legacy' / 'tmdb' / 'imdb' / 'wikidata' 之一。"""
    raw = clean_str(record.get("source")).lower()
    if raw in SOURCE_ALIASES:
        return SOURCE_ALIASES[raw]
    base = raw.split("+")[0].strip()
    return SOURCE_ALIASES.get(base, base or "unknown")


def _rank(src: str | None, field: str) -> int:
    """越小越可信；未知源排 998，表外的字段排 999。"""
    order = SCALAR_PRIORITY.get(field)
    if not order:
        return 999
    try:
        return order.index(src)
    except ValueError:
        return 998


# ============================================================
# 合并：把「一条记录」或「另一个桶」并进 bucket
# ============================================================

def _absorb_locations(bucket: dict, source: dict) -> None:
    """拍摄地按 (地名, 纬度, 经度) 三元组去重后并集。

    足迹地图要吃 locations_with_coords，所以每次并完顺手重算一遍 ——
    让下游拿到的永远是「已经过滤好坐标的列表」，前端不用再判断一次。
    """
    new = [p for p in (source.get("filming_locations") or []) if isinstance(p, dict)]
    if not new:
        return
    cur = list(bucket.get("filming_locations") or [])
    seen = {(p.get("name"), p.get("lat"), p.get("lon")) for p in cur if isinstance(p, dict)}
    for p in new:
        sig = (p.get("name"), p.get("lat"), p.get("lon"))
        if sig in seen:
            continue
        seen.add(sig)
        cur.append(p)
    bucket["filming_locations"] = cur
    bucket["locations_with_coords"] = [
        p for p in cur if isinstance(p, dict) and p.get("lat") is not None
    ]


def absorb_record(bucket: dict, record: dict, src: str, *, use_title_key: bool = True) -> None:
    """把一条**原始记录**并进合并桶：逐字段按优先级择优。"""
    field_src: dict[str, str] = bucket.setdefault("_field_src", {})

    for field in SCALAR_PRIORITY:
        val = record.get(field)
        if is_missing(field, val):
            continue
        if is_missing(field, bucket.get(field)) or _rank(src, field) < _rank(field_src.get(field), field):
            bucket[field] = val
            field_src[field] = src

    # ★ 主键字段单独处理：它们不在 SCALAR_PRIORITY 里（没有「谁更可信」的问题，
    #   只有「有 / 没有」的区别），但**必须留下来** ——
    #   丢了 imdb_id / tmdb_id 等于丢了融合的锚点，后面 ES 的 _id 就只能退化成 hash。
    for field in ("imdb_id", "tmdb_id"):
        if not bucket.get(field) and record.get(field):
            bucket[field] = record[field]

    for field in LIST_FIELDS:
        bucket[field] = uniq_list(list(bucket.get(field) or []) + list(record.get(field) or []))

    for field in EXTRA_FIELDS:
        if is_missing(field, bucket.get(field)) and not is_missing(field, record.get(field)):
            bucket[field] = record[field]

    _absorb_locations(bucket, record)

    bucket["_sources"].add(src)
    bucket["_raw_count"] += 1
    bucket["_keys"].update(film_keys(record, use_title_key=use_title_key))


def merge_buckets(dst: dict, src_bucket: dict) -> None:
    """把另一个**合并桶**整个并进 dst。

    用于「一条记录同时命中两组」的情形 —— 那两组其实是同一部电影。
    这里比较的是双方各自的 _field_src（该字段来自哪个源），
    而不是「谁先来」，所以合并顺序不影响最终结果（幂等）。
    """
    dst_fs: dict[str, str] = dst.setdefault("_field_src", {})
    src_fs: dict[str, str] = src_bucket.get("_field_src") or {}

    for field in SCALAR_PRIORITY:
        val = src_bucket.get(field)
        if is_missing(field, val):
            continue
        if is_missing(field, dst.get(field)) or _rank(src_fs.get(field), field) < _rank(dst_fs.get(field), field):
            dst[field] = val
            dst_fs[field] = src_fs.get(field)

    # 主键同样要带过来（见 absorb_record 里的同款说明）
    for field in ("imdb_id", "tmdb_id"):
        if not dst.get(field) and src_bucket.get(field):
            dst[field] = src_bucket[field]

    for field in LIST_FIELDS:
        dst[field] = uniq_list(list(dst.get(field) or []) + list(src_bucket.get(field) or []))

    for field in EXTRA_FIELDS:
        if is_missing(field, dst.get(field)) and not is_missing(field, src_bucket.get(field)):
            dst[field] = src_bucket[field]

    _absorb_locations(dst, src_bucket)

    dst["_sources"] |= src_bucket.get("_sources") or set()
    dst["_raw_count"] += src_bucket.get("_raw_count") or 0
    dst["_keys"] |= src_bucket.get("_keys") or set()


# ============================================================
# 合并器
# ============================================================

class MovieMerger:
    """增量式融合器：来一条收一条，不把原始记录堆在内存里。

    内存估算：一个 bucket ≈ 一条电影记录（约 1 KB）。
    12 万条原始记录融合成 8 万部电影 ≈ 80 MB —— 这是本层的内存上限，
    与「原始记录条数」无关，只与「电影部数」有关。

    用法：
        merger = MovieMerger()
        for rec in records:
            merger.add(rec)
        for movie in merger.results():
            ...
    """

    def __init__(self, *, use_title_key: bool = True):
        self.use_title_key = use_title_key
        self.key2gid: dict[str, int] = {}
        self.buckets: dict[int, dict] = {}
        self._next_gid = 0
        # 统计：有多少条记录起了「桥」的作用（把原本分开的两组连起来）
        self.bridges = 0
        # 统计：完全没有主键、只能孤独成组的记录（数据质量问题，要报出来）
        self.keyless = 0

    # ---- 写入 ----

    def add(self, record: dict) -> None:
        keys = film_keys(record, use_title_key=self.use_title_key)
        src = source_of(record)

        if not keys:
            # 既没 id 也没「片名+年份」→ 无法与任何东西对齐，只能单独成组。
            # 这种情况必须计数上报：它意味着采集端漏了字段。
            self.keyless += 1
            gid = self._new_bucket()
            absorb_record(self.buckets[gid], record, src, use_title_key=self.use_title_key)
            return

        hits = {self.key2gid[k] for k in keys if k in self.key2gid}
        if not hits:
            gid = self._new_bucket()
        elif len(hits) == 1:
            gid = next(iter(hits))
        else:
            # 桥：这条记录把 2 个以上原本独立的组连成了一部电影
            gid = min(hits)
            for other in sorted(hits):
                if other != gid:
                    merge_buckets(self.buckets[gid], self.buckets.pop(other))
            self.bridges += 1

        absorb_record(self.buckets[gid], record, src, use_title_key=self.use_title_key)
        for k in keys:
            self.key2gid[k] = gid

    def _new_bucket(self) -> int:
        gid = self._next_gid
        self._next_gid += 1
        self.buckets[gid] = {
            "_field_src": {},      # 字段 → 该字段当前取自哪个源
            "_sources": set(),     # 参与合并的源标签
            "_raw_count": 0,       # 拼了几条原始记录
            "_keys": set(),        # 这条记录用过的所有对齐主键
        }
        return gid

    # ---- 输出 ----

    def __len__(self) -> int:
        return len(self.buckets)

    def results(self) -> Iterator[dict]:
        """按「组建立顺序」逐条产出成品记录（顺序稳定，不需要额外排序）。"""
        stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        for bucket in self.buckets.values():
            yield finalize(bucket, collected_at=stamp)


# ============================================================
# 定稿：把合并桶整理成「可以直接灌进 ES」的成品
# ============================================================

def doc_id(record: dict) -> str:
    """生成稳定的文档 id（ES 的 _id），供幂等导入使用。

    优先级：imdb_id → tmdb-<id> → m<hash>
        用内容 hash 兜底而不是行号，是因为行号换个排序就全乱了；
        而「片名+年份」的 hash 无论跑多少次都是同一个值 —— 重复导入直接覆盖。
    """
    imdb = clean_str(record.get("imdb_id")).lower()
    if imdb:
        return imdb
    tmdb = to_int(record.get("tmdb_id"))
    if tmdb:
        return f"tmdb-{tmdb}"
    seed = f"{normalize_title(record.get('title') or record.get('title_zh'))}|{record.get('release_year') or ''}"
    return "m" + hashlib.sha1(seed.encode("utf-8")).hexdigest()[:12]


def finalize(bucket: dict, *, collected_at: str | None = None) -> dict:
    """把一个合并桶定稿成成品记录。

    定稿做四件事：
        1. 补齐 CORE_FIELDS —— 缺的字段填 None / []，而不是把 key 省掉
           （留空与缺字段是两回事：前者能参与合并，后者会让 ES 的列错位）
        2. 片名收尾 —— title 必须是「人看的」，有中文名就不能留英文
        3. 年份与数值归一 —— release_date 是权威；评分留 1 位小数
        4. 写血统 —— movie_id / sources / merged_from / match_keys
    """
    rec: dict[str, Any] = {k: v for k, v in bucket.items() if not k.startswith("_")}

    # 1) 补齐合同字段
    for field in CORE_FIELDS:
        if field not in rec:
            rec[field] = [] if field in LIST_FIELDS else None

    # 2) 片名收尾：title 是展示用的，有中文就用中文
    if rec.get("title_zh") and not has_han(rec.get("title")):
        rec["title"] = rec["title_zh"]
    # 中英文字段互相兜底，避免前端出现「有片名但英文列为空」的破图
    if not rec.get("title_en") and rec.get("title") and not has_han(rec.get("title")):
        rec["title_en"] = rec["title"]
    if not rec.get("title_zh") and has_han(rec.get("title")):
        rec["title_zh"] = rec["title"]

    # 3) 年份与数值归一
    y = year_of(rec.get("release_date"))
    if y:
        rec["release_year"] = y
    rec["release_year"] = to_int(rec.get("release_year"))
    rec["runtime"] = to_int(rec.get("runtime"))
    rec["vote_count"] = to_int(rec.get("vote_count"))
    # 票房/预算：美元整额；0/缺失归一 None（ES 里不参与聚合）
    rec["revenue"] = to_int(rec.get("revenue")) or None
    rec["budget"] = to_int(rec.get("budget")) or None
    va = to_float(rec.get("vote_average"))
    rec["vote_average"] = round(va, 1) if va else None
    pop = to_float(rec.get("popularity"))
    rec["popularity"] = round(pop, 2) if pop else None
    rec["imdb_rating"] = to_float(rec.get("imdb_rating"))

    # 3.5) 分面枚举归一化：类型/国家/语言收敛成标准中文短名
    # （多源并集把 TMDB 短名、Wikidata 维基分类长名、英文标签、繁体混在
    #  一个列表里，导致检索页出现 40+ 个类型桶——详见 normalize.py 顶部说明）
    rec["genres_zh"] = normalize_genres(rec.get("genres_zh"))
    rec["production_countries"] = normalize_countries(rec.get("production_countries"))
    # 主出品国：国家分面的筛选口径（只算主出品国，不带合拍国）。
    # 全量制片国列表仍保留（详情页/数据面用），分面走 primary_country。
    rec["primary_country"] = pick_primary_country(
        rec["production_countries"], rec.get("original_language")
    )
    rec["spoken_languages"] = normalize_languages(rec.get("spoken_languages"))
    # 拍摄地/故事发生地归一：繁体简体并排（「長島」「长岛」）与
    # 全称短称并排（「中华人民共和国」「中国」）会让足迹地图出现
    # 重复点位，用户以为数据错了。归一后重算带坐标列表。
    rec["filming_locations"] = normalize_places(rec.get("filming_locations"))
    rec["locations_with_coords"] = [
        p for p in rec["filming_locations"] if p.get("lat") is not None
    ]

    # 4) 血统
    rec["movie_id"] = doc_id(rec)
    rec["sources"] = sorted(bucket.get("_sources") or [])
    rec["source_count"] = len(rec["sources"])
    # CORE_FIELDS 里的 source 保留成复合串（"imdb+tmdb"），
    # 一眼能看出这条是拼出来的；sources 列表则给程序用，两者不冲突。
    rec["source"] = "+".join(rec["sources"]) or None
    rec["merged_from"] = int(bucket.get("_raw_count") or 1)
    rec["match_keys"] = sorted(bucket.get("_keys") or [])
    rec["is_multi_source"] = rec["source_count"] > 1
    rec["collected_at"] = collected_at or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    return rec


# ============================================================
# 便捷入口
# ============================================================

def merge_movies(records: Iterable[dict], *, use_title_key: bool = True) -> tuple[MovieMerger, list[dict]]:
    """一次性把记录列表融合成电影列表（小数据量 / 测试用）。

    生产路径（run_transform）走的是流式：边读边 add，不经过这个函数。
    """
    merger = MovieMerger(use_title_key=use_title_key)
    for rec in records:
        merger.add(rec)
    return merger, list(merger.results())
