"""
Wikidata SPARQL 采集器 —— 阶段 1c（上半）。

为什么需要它：
    TMDB 与 IMDb 都只有英文/原始片名，而且 IMDb 数据集里**完全没有**人物关系、
    出品国、拍摄地点。Wikidata 是结构化的开放知识库，一部电影条目上就挂着
    导演、类型、出品国、公映日期、片长、**拍摄地点坐标**。
    其中「拍摄地点坐标」是阶段 6「观影足迹地图」唯一的坐标来源 ——
    这个字段没有任何别的免费数据源能稳定提供，所以在 1c 里必须拿下。

════════════════════════════════════════════════════════════════════════
★ 本模块踩到的两个真实坑（已修，写在最前面备查）
════════════════════════════════════════════════════════════════════════
1. **`GROUP_CONCAT` + `wikibase:label` 会返回空串**
   直觉写法是把导演/类型/国家在 SPARQL 里用
   `(GROUP_CONCAT(DISTINCT ?directorLabel; separator="、") AS ?directors)`
   聚合好再返回。实测（query.wikidata.org 真实响应）：`?filmLabel` 正常返回
   「搏击俱乐部」，但 `?directors` / `?genres` / `?countries` 全是空字符串 ——
   标签服务生成的变量在聚合函数里取不到值。

   因此本模块改成 **「SPARQL 只做关联查询、返回多行；聚合放到 Python」**。
   代价是行数变多（一部电影 3 个导演 × 4 个类型 ≈ 12 行），
   一个批次 40 部 ≈ 500 行，完全可控；好处是聚合逻辑变成可离线自检的纯函数。

2. **WKT 的坐标顺序是 (经度 纬度)，不是 (纬度 经度)**
   Wikidata 的 `P625` 返回 `Point(-118.24368 34.05223)`，
   第一位是**经度**（洛杉矶 -118.24）、第二位是**纬度**（34.05）。
   顺序写反的话，整批坐标会落到南极洲 —— 地图上一眼能看出来，
   但躺在 JSON 里几乎发现不了。所以统一在 `parse_wkt_point()` 入口转成
   `(lat, lon)` 并配套一条自检。

════════════════════════════════════════════════════════════════════════
批量与缓存
════════════════════════════════════════════════════════════════════════
    - 一条 SPARQL 用 `VALUES (?prop ?key) { ... }` 一次问多部电影（默认 40 个），
      把几百次请求压到十几次 —— WDQS 对查询频率很敏感，这是必须的礼貌；
    - 原始响应落盘 `data_lake/raw/wikidata/{core,geo}/{指纹}.json`，
      信封与阶段 1a 一致（`{_request:{query}, _response:{...}}`），
      查询语句一致才命中缓存 → 断点续跑、改参数不会读到脏缓存。

产物：
    data_lake/raw/wikidata/core/*.json      核心信息原始响应
    data_lake/raw/wikidata/geo/*.json       拍摄地坐标原始响应
    （归一化结果由 ingest/sources/wiki.py 汇总后落 interim）
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Iterable, Iterator
from urllib.parse import unquote, urlsplit

from common.settings import settings
from ingest.http import CollectorHttpError, RateLimitedClient, dump_raw, load_raw

# WDQS 直接三元组前缀；用 IRI 而不是 wdt: 前缀，是为了能把属性名放进 VALUES 变量
WD_DIRECT = "http://www.wikidata.org/prop/direct"
WD_ENTITY = "http://www.wikidata.org/entity"

# 标签服务的语言回退链：优先简体 → 中文 → 英文。
# 注意：这样拿到的 ?filmLabel **可能是英文**（条目没有中文标签时回退），
# 所以判定「这是不是中文片名」要靠 has_han() 而不是靠盲信标签服务。
LABEL_LANGS = "zh-hans,zh,en"

# ============================================================
# Wikidata 属性 → 本项目字段 的对照表（答辩讲解 / 文档都用它）
# ============================================================

PROPERTY_MAP: dict[str, str] = {
    "P345": "IMDb 编号 → imdb_id（与阶段 1a/1b 对齐的主键）",
    "P4947": "TMDB 电影编号 → tmdb_id（备用主键，给只有 tmdb_id 的记录兜底）",
    "P57": "导演 → director",
    "P161": "演员 → cast（本阶段暂不采集，见文末说明）",
    "P136": "类型 → genres_zh（与 TMDB/IMDb 的分面值合并）",
    "P495": "出品国家/地区 → production_countries",
    "P577": "首次公映日期 → release_date / release_year",
    "P2047": "片长（分钟）→ runtime",
    "P915": "拍摄地点 → filming_locations（★ 观影足迹地图的数据源）",
    "P840": "故事发生地点 → filming_locations（同上，作为 P915 的补充）",
    "P625": "坐标 → lat / lon（WKT 格式，注意经纬度顺序）",
    "P18": "图像 → poster_url（Commons 原图，与 TMDB 海报互为补充）",
}

# 归一时保留的列表长度上限，避免个别条目带出几十个出品国把记录撑爆
MAX_LIST = 30

# ============================================================
# SPARQL 语句
# ============================================================

# 核心信息：身份 + 标签 + 标量字段
# 返回「一行一个组合」，由 Python 侧聚合（原因见文件头的坑 1）
CORE_QUERY = """SELECT ?film ?prop ?key ?filmLabel
       ?directorLabel ?genreLabel ?countryLabel ?pub ?dur ?image ?article
WHERE {{
  VALUES (?prop ?key) {{ {values} }}
  ?film ?prop ?key .
  OPTIONAL {{ ?film wdt:P57 ?director . }}
  OPTIONAL {{ ?film wdt:P136 ?genre . }}
  OPTIONAL {{ ?film wdt:P495 ?country . }}
  OPTIONAL {{ ?film wdt:P577 ?pub . }}
  OPTIONAL {{ ?film wdt:P2047 ?dur . }}
  OPTIONAL {{ ?film wdt:P18 ?image . }}
  OPTIONAL {{ ?article schema:about ?film ; schema:isPartOf <https://zh.wikipedia.org/> . }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "{lang}". }}
}}
LIMIT {limit}
"""

# 拍摄地 / 故事发生地 + 坐标
# 用 UNION + BIND 保留「这是拍摄地还是故事发生地」这个区别，
# 地图弹窗里可以分别标注。P915 是真实取景地，P840 是剧情发生地。
GEO_QUERY = """SELECT ?film ?prop ?key ?loc ?locLabel ?coord ?kind
WHERE {{
  VALUES (?prop ?key) {{ {values} }}
  ?film ?prop ?key .
  {{ ?film wdt:P915 ?loc . BIND("filming" AS ?kind) }}
  UNION
  {{ ?film wdt:P840 ?loc . BIND("narrative" AS ?kind) }}
  OPTIONAL {{ ?loc wdt:P625 ?coord . }}
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "{lang}". }}
}}
LIMIT {limit}
"""

# 结果里我们要逐个取出的变量名（固定顺序，便于人工比对原始 JSON）
ROW_VARS = (
    "film", "prop", "key", "filmLabel",
    "directorLabel", "genreLabel", "countryLabel",
    "pub", "dur", "image", "article",
    "loc", "locLabel", "coord", "kind",
)

# ============================================================
# 纯函数：解析（可离线自检，不碰网络）
# ============================================================


def _esc(value: str) -> str:
    """把值塞进 SPARQL 字符串字面量前的转义。"""
    return str(value).replace("\\", "\\\\").replace('"', '\\"')


def build_values(pairs: Iterable[tuple[str, str]]) -> str:
    """把 [(P345, tt0137523), (P4947, 550)] 拼成 SPARQL 的 VALUES 子句。

    用 `VALUES (?prop ?key)` 这种**成对**形式，就能把「IMDb 主键」与
    「TMDB 主键」放在同一条查询里一起问，不必为两种主键各写一套查询。
    """
    items = [f"(<{WD_DIRECT}/{p}> \"{_esc(k)}\")" for p, k in pairs if p and k]
    return " ".join(items)


def _val(binding: dict, var: str) -> Any:
    item = binding.get(var)
    return item.get("value") if isinstance(item, dict) else None


def parse_rows(payload: dict | None) -> list[dict]:
    """把 SPARQL JSON 响应摊平成「每行一个 dict」。

    只认 results.bindings，并且把值统一取 .value ——
    这样上层完全不用关心 SPARQL 的 type / datatype / xml:lang 包装。
    """
    bindings = ((payload or {}).get("results") or {}).get("bindings") or []
    rows: list[dict] = []
    for binding in bindings:
        if isinstance(binding, dict):
            rows.append({v: _val(binding, v) for v in ROW_VARS})
    return rows


def prop_name(prop_uri: str | None) -> str:
    """http://www.wikidata.org/prop/direct/P345 → P345"""
    return prop_uri.rsplit("/", 1)[-1] if prop_uri else ""


def qid_of(uri: str | None) -> str | None:
    """http://www.wikidata.org/entity/Q190050 → Q190050"""
    if not uri:
        return None
    tail = uri.rstrip("/").rsplit("/", 1)[-1]
    return tail if re.fullmatch(r"Q\d+", tail) else None


_WKT_POINT = re.compile(r"Point\(\s*(-?\d+(?:\.\d+)?)\s+(-?\d+(?:\.\d+)?)\s*\)", re.I)


def parse_wkt_point(wkt: str | None) -> tuple[float, float] | None:
    """WKT `Point(lon lat)` → `(lat, lon)`，越界返回 None。

    ⚠️ WKT 里是 (x y) = (经度 纬度)，与日常口语的「纬度,经度」相反。
    统一在这里翻转，只翻一次，别让这个顺序问题散落到各个调用点。
    """
    if not wkt:
        return None
    m = _WKT_POINT.search(str(wkt))
    if not m:
        return None
    lon, lat = float(m.group(1)), float(m.group(2))
    if not (-90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0):
        return None
    return lat, lon


_HAN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")


def has_han(text: Any) -> bool:
    """是否含汉字。用来判断一个标签「真的是中文名」还是回退成了英文。"""
    return bool(text) and bool(_HAN.search(str(text)))


def title_from_article(url: str | None) -> str | None:
    """从 zhwiki 条目 URL 反解出条目标题（百分号解码 + 下划线还原空格）。"""
    if not url:
        return None
    tail = str(url).rstrip("/").rsplit("/", 1)[-1]
    title = unquote(tail).replace("_", " ").strip()
    return title or None


def _int(value: Any) -> int | None:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def _date10(value: Any) -> str | None:
    """`1999-09-10T00:00:00Z` → `1999-09-10`。"""
    if not value:
        return None
    text = str(value)
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", text)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.match(r"(\d{4})", text)
    return f"{m.group(1)}-01-01" if m else None


def _clean(value: Any) -> str:
    return " ".join(str(value or "").split())


def _push(bucket: list[str], value: Any) -> None:
    """去重追加，并限制列表长度 —— 内存/记录体积都有界。"""
    text = _clean(value)
    if text and text not in bucket and len(bucket) < MAX_LIST:
        bucket.append(text)


def aggregate_core(rows: Iterable[dict]) -> dict[str, dict]:
    """把「一行一个组合」的多行结果，按主键聚合成一部电影一条。

    这是模块里唯一做聚合的地方。放在 Python 而不是 SPARQL，是为了：
        1. 绕开 label service 在聚合函数里取不到值的坑（见文件头）；
        2. 聚合逻辑可以直接喂 fixture 做离线自检，不用联网。
    """
    merged: dict[str, dict] = {}
    for row in rows:
        key = row.get("key")
        if not key:
            continue
        entry = merged.get(key)
        if entry is None:
            entry = merged[key] = {
                "qid": None, "wikidata_key": key,
                "imdb_id": None, "tmdb_id": None,
                "label": None, "directors": [], "genres": [], "countries": [],
                "pubdate": None, "duration": None,
                "image": None, "zh_article": None,
            }

        qid = qid_of(row.get("film"))
        if qid and not entry["qid"]:
            entry["qid"] = qid

        prop = prop_name(row.get("prop"))
        if prop == "P345":
            entry["imdb_id"] = key
        elif prop == "P4947":
            entry["tmdb_id"] = key

        label = _clean(row.get("filmLabel"))
        if label and not entry["label"]:
            entry["label"] = label

        _push(entry["directors"], row.get("directorLabel"))
        _push(entry["genres"], row.get("genreLabel"))
        _push(entry["countries"], row.get("countryLabel"))

        if row.get("image") and not entry["image"]:
            entry["image"] = row["image"]
        if row.get("article") and not entry["zh_article"]:
            entry["zh_article"] = row["article"]

        pub = _date10(row.get("pub"))
        if pub and (entry["pubdate"] is None or pub < entry["pubdate"]):
            entry["pubdate"] = pub          # 取最早的公映日期
        dur = _int(row.get("dur"))
        if dur and (entry["duration"] is None or dur > entry["duration"]):
            entry["duration"] = dur         # 同一部片可能有多个时长，取最大的

    return merged


def aggregate_geo(rows: Iterable[dict]) -> dict[str, list[dict]]:
    """拍摄地/故事发生地 → {主键: [{name, kind, qid, lat, lon}, ...]}。

    没有坐标的地点也保留（名字本身对「取景地一览」有价值），
    只是不打 lat/lon，前端地图按有没有坐标决定要不要落点。
    """
    merged: dict[str, list[dict]] = {}
    for row in rows:
        key = row.get("key")
        name = _clean(row.get("locLabel") or row.get("loc"))
        if not key or not name:
            continue
        place: dict[str, Any] = {
            "name": name,
            "kind": _clean(row.get("kind")) or "place",
            "qid": qid_of(row.get("loc")),
        }
        point = parse_wkt_point(row.get("coord"))
        if point:
            place["lat"], place["lon"] = point

        bucket = merged.setdefault(key, [])
        signature = (place["qid"] or name, place["kind"])
        if len(bucket) < MAX_LIST and all(
            (p.get("qid") or p["name"], p["kind"]) != signature for p in bucket
        ):
            bucket.append(place)
    return merged


# ============================================================
# 采集器
# ============================================================


class WikidataCollector:
    SOURCE = "wikidata"

    def __init__(
        self,
        *,
        endpoint: str | None = None,
        proxy: str | None = None,
        min_interval: float | None = None,
        batch_size: int | None = None,
        force: bool = False,
    ) -> None:
        self.batch_size = batch_size or settings.wikidata_batch
        self.force = force
        # endpoint 是完整 URL（https://query.wikidata.org/sparql），
        # 必须拆成 base + path：RateLimitedClient 以 base_url + "" 调用时
        # httpx 会拼出 /sparql/（尾斜杠），WDQS 对该路径返回 404 —— 阶段 1c 踩过。
        _ep = endpoint or settings.wikidata_endpoint
        _parts = urlsplit(_ep)
        _base = f"{_parts.scheme}://{_parts.netloc}"
        _path = _parts.path or "/sparql"
        self.sparql_path = _path
        self.client = RateLimitedClient(
            _base,
            headers={
                "User-Agent": settings.wikidata_user_agent,
                "Accept": "application/sparql-results+json",
            },
            # WDQS 对频率很敏感，默认放慢到 0.6s/次
            min_interval=min_interval if min_interval is not None else 0.6,
            max_retries=settings.wikidata_max_retries,
            proxy=proxy if proxy is not None else settings.collector_proxy,
        )
        self.stats = {"api_calls": 0, "cache_hits": 0, "batches": 0}

    # ---------------- 缓存层（与阶段 1a 同一套信封格式）----------------

    def _raw(self, kind: str, query: str) -> Path:
        """原始响应路径。查询语句很长，用它的 md5 当文件名（可复现、无非法字符）。"""
        digest = hashlib.md5(query.encode("utf-8")).hexdigest()[:16]
        return settings.lake("raw", "wikidata", kind, f"{digest}.json")

    def sparql(self, query: str, *, kind: str, quiet: bool = False) -> dict:
        """执行一条 SPARQL；命中缓存（且查询语句完全一致）则直接读盘。"""
        raw_path = self._raw(kind, query)
        if not self.force:
            cached = load_raw(raw_path)
            if isinstance(cached, dict) and cached.get("_request", {}).get("query") == query:
                self.stats["cache_hits"] += 1
                return cached.get("_response") or {}

        payload = self.client.get_json(
            self.sparql_path, {"query": query, "format": "json"}, quiet=quiet
        )
        self.stats["api_calls"] += 1
        dump_raw({"_request": {"query": query}, "_response": payload}, raw_path)
        return payload

    # ---------------- 批量查询 ----------------

    def _run_batches(
        self, pairs: list[tuple[str, str]], template: str, *, kind: str, progress: bool
    ) -> Iterator[dict]:
        """把 (属性, 主键) 切成小批，逐批查询并把结果逐行 yield 出去。"""
        total = len(pairs)
        for start in range(0, total, self.batch_size):
            chunk = pairs[start:start + self.batch_size]
            query = template.format(
                values=build_values(chunk),
                lang=LABEL_LANGS,
                limit=settings.wikidata_sparql_limit,
            )
            try:
                payload = self.sparql(query, kind=kind, quiet=not progress)
            except CollectorHttpError as exc:
                # 一整批失败不该让整个任务崩掉 —— 记一笔，继续下一批
                print(f"    [跳过一批] {kind} 查询失败：{exc}")
                continue
            self.stats["batches"] += 1
            rows = parse_rows(payload)
            if progress:
                print(f"    {kind} {min(start + self.batch_size, total)}/{total} 个主键"
                      f" → 返回 {len(rows)} 行")
            yield from rows

    def query_core(self, pairs: list[tuple[str, str]], *, progress: bool = True) -> dict[str, dict]:
        rows = list(self._run_batches(pairs, CORE_QUERY, kind="core", progress=progress))
        return aggregate_core(rows)

    def query_geo(self, pairs: list[tuple[str, str]], *, progress: bool = True) -> dict[str, list[dict]]:
        rows = list(self._run_batches(pairs, GEO_QUERY, kind="geo", progress=progress))
        return aggregate_geo(rows)

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> "WikidataCollector":
        return self

    def __exit__(self, *exc_info) -> None:
        self.client.close()


# ============================================================
# 主键收集工具
# ============================================================


def key_pairs(records: Iterable[dict]) -> list[tuple[str, str]]:
    """从已有记录里抽出 (属性, 主键) 对，供 SPARQL 批量查询。

    优先用 imdb_id（Wikidata 上 P345 的覆盖率与规范化程度都更好），
    同一部电影有 imdb_id 时就**不再**用 tmdb_id 重复问一遍。
    """
    pairs: list[tuple[str, str]] = []
    seen: set[str] = set()
    for rec in records:
        imdb = _clean(rec.get("imdb_id"))
        tmdb = rec.get("tmdb_id")
        if imdb:
            token = f"tt{imdb}"
            if token not in seen:
                seen.add(token)
                pairs.append(("P345", imdb))
            continue
        if tmdb:
            token = f"tm{tmdb}"
            if token not in seen:
                seen.add(token)
                pairs.append(("P4947", str(int(tmdb))))
    return pairs
