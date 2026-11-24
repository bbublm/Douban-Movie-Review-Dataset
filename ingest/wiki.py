"""
维基数据的归一化与合并 —— 阶段 1c（合拢层）。

把两条独立链路的结果拼成一部电影一条记录：
    Wikidata 核心信息  (ingest/sources/wikidata.py)
    Wikidota 拍摄地坐标 (同上的 GEO_QUERY)
    Wikipedia 剧情摘要  (ingest/sources/wikipedia.py)
        ↓
    ingest/wiki.py: normalize_wiki() / build_wiki_records()
        ↓
    data_lake/interim/wiki_movies.jsonl

为什么单独一个文件、而且全是纯函数：
    这一层是「阶段 1c 里唯一有业务判断的地方」，也是最容易出错的地方：

    · 中文片名到底取哪个？Wikidata 的 zh 标签？还是 zhwiki 条目标题？
      —— 标签服务会静默回退成英文，所以必须用 has_han() 判断而不是盲信；
    · 同一部电影在 Wikidata 上可能有多个「公映日期」「片长」，取哪个？
      —— 由 aggregate_core 定：日期取最早、片长取最大；
    · 坐标的经纬度顺序？—— 由 parse_wkt_point 在入口处翻转一次。

    把这些判断做成纯函数，就能用 fixture 离线跑测试，
    不必联网、不必等 40 秒一次的 SPARQL 往返。

★ 关于 P161（演员）
    Wikidata 上演员列表动辄二三十人，全量拉取会让 SPARQL 结果膨胀好几倍，
    而主演信息 TMDB 的 credits 已经给得很全（阶段 1a 已采）。
    所以本阶段**刻意不采演员**，避免为一个已有字段付两倍查询代价。
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Iterable, Iterator

from ingest.schema import CORE_FIELDS
from ingest.sources.wikidata import has_han, title_from_article

# Wikipedia 摘要来源标记（写进 source 字段，交代这条记录由哪几个源拼成）
SRC_WD = "wikidata"
SRC_WD_WIKI = "wikidata+wikipedia"


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def _year_of(date_str: str | None) -> int | None:
    if date_str and len(date_str) >= 4 and date_str[:4].isdigit():
        return int(date_str[:4])
    return None


def normalize_wiki(
    entry: dict,
    *,
    places: list[dict] | None = None,
    summary: dict | None = None,
) -> dict:
    """一条 Wikidata 聚合结果（+ 拍摄地 + 摘要）→ 统一结构记录。

    输出严格覆盖 ingest/schema.py 的 CORE_FIELDS，
    并且额外携带本源的特色字段（wikidata_qid / filming_locations / wikipedia_*），
    供阶段 2 融合、阶段 6 地图直接使用。
    """
    label = _clean(entry.get("label"))
    article_title = title_from_article(entry.get("zh_article"))

    # 中文片名的选择顺序：
    #   1) Wikidata 的标签，但必须真的含汉字（否则它是回退成英文的）
    #   2) zhwiki 条目标题（同样要求含汉字）
    #   3) 都没有 → None，留给阶段 2 用 TMDB 的中文名或旧片库译名补
    title_zh: str | None = None
    if has_han(label):
        title_zh = label
    elif article_title and has_han(article_title):
        title_zh = article_title

    display = title_zh or label or article_title
    pubdate = entry.get("pubdate")
    countries = list(entry.get("countries") or [])
    genres = list(entry.get("genres") or [])

    record: dict[str, Any] = {
        # ---- 主键与实体对齐 ----
        "tmdb_id": int(entry["tmdb_id"]) if str(entry.get("tmdb_id") or "").isdigit() else None,
        "imdb_id": _clean(entry.get("imdb_id")) or None,
        # ---- 片名 ----
        "title": display or None,
        "title_zh": title_zh,
        "title_en": label or None,
        "original_title": label or None,
        # ---- 时间与时长 ----
        "release_date": pubdate,
        "release_year": _year_of(pubdate),
        "runtime": entry.get("duration"),
        # ---- 文本 ----
        "overview": (summary or {}).get("extract") or "",
        "tagline": "",
        "status": "",
        # ---- 分类与人物 ----
        "genres_zh": genres or ["剧情"],
        "genre_ids": [],
        "keywords": [],
        "director": "、".join(entry.get("directors") or []) or None,
        "cast": [],                      # 见文件头说明：刻意不采 P161
        # ---- 评分与热度（维基不提供，全部留给 TMDB/IMDb）----
        "vote_average": 0.0,
        "vote_count": 0,
        "popularity": 0.0,
        # ---- 地域与语言 ----
        "original_language": None,
        "spoken_languages": [],
        "production_countries": countries,
        "production_country_codes": [],
        # ---- 图片 ----
        "poster_url": entry.get("image") or None,
        "backdrop_url": None,
        # ---- 数据血缘 ----
        "source": SRC_WD_WIKI if (summary or {}).get("extract") else SRC_WD,
        "collected_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    # ---- 本源特色字段（不属于 CORE_FIELDS，融合时是"额外养分"）----
    record["wikidata_qid"] = entry.get("qid")
    record["wikidata_url"] = (
        f"https://www.wikidata.org/wiki/{entry['qid']}" if entry.get("qid") else None
    )
    record["wikipedia_title"] = article_title
    record["wikipedia_url"] = (summary or {}).get("url") or entry.get("zh_article")
    record["wikipedia_extract"] = (summary or {}).get("extract") or ""
    # 观影足迹地图直接吃 filming_locations；同时把「有坐标的地点」单独列出来，
    # 前端拿 locations_with_coords 就能直接喂 Leaflet，不用再过滤一遍。
    places = places or []
    record["filming_locations"] = places
    record["locations_with_coords"] = [p for p in places if p.get("lat") is not None]
    return record


def missing_core_fields(record: dict) -> list[str]:
    """暴露给调用方/自检：这条记录还缺哪些核心字段名。"""
    return [f for f in CORE_FIELDS if f not in record]


def build_wiki_records(
    core: dict[str, dict],
    geo: dict[str, list[dict]] | None = None,
    summaries: dict[str, dict] | None = None,
) -> list[dict]:
    """把三份结果合并成记录列表。这是「合拢」的全部逻辑。

    core       {主键: 聚合条目}
    geo        {主键: [拍摄地...]}
    summaries  {条目标题: {extract, url, ...}}

    摘要的查表键有两级兜底：
        先用 zhwiki 条目标题查；查不到再退回用中文片名 / Wikidata 标签查 ——
        因为有些条目标题带消歧义括号（如「搏击俱乐部 (电影)」），
        而 Wikidata 标签是干净的「搏击俱乐部」，两级兜底能多命中一批。
    """
    geo = geo or {}
    summaries = summaries or {}
    records: list[dict] = []

    for key, entry in core.items():
        summary = None
        for candidate in (
            title_from_article(entry.get("zh_article")),
            entry.get("label"),
        ):
            if candidate and candidate in summaries:
                summary = summaries[candidate]
                break
        records.append(normalize_wiki(entry, places=geo.get(key), summary=summary))

    # 输出顺序稳定：按年份倒序、再按主键排 —— 便于人工比对与 diff
    records.sort(key=lambda r: (-(r.get("release_year") or 0), r.get("imdb_id") or ""))
    return records


# ============================================================
# 落盘
# ============================================================


def write_jsonl(records: Iterable[dict], path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n += 1
    return n


def iter_jsonl(path: Path) -> Iterator[dict]:
    """流式读 JSONL；坏行跳过而不是整文件失败。"""
    if not path.exists():
        return
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue
