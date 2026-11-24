"""
TMDB API 采集器 —— 阶段 1a。

四个能力：
    genre_map()      类型 id → 中文名（discover 结果里只有 id，没有名字）
    discover()       按热度/评分/年份分页发现影片，拿到候选 id 列表
    movie_detail()   拉单片全量详情（credits / keywords / external_ids / release_dates）
    search_movie()   按片名搜索，用来给旧片库补 TMDB id

落盘策略（这是本模块最值钱的部分）：
    data_lake/raw/tmdb/genre_list.json         类型字典
    data_lake/raw/tmdb/discover/page_{n}.json  发现结果，带请求参数指纹
    data_lake/raw/tmdb/movie/{tmdb_id}.json    单片详情
    data_lake/raw/tmdb/search/{关键词}.json    搜索结果
    已存在的原始文件默认直接读盘、不重发请求 —— 断点续跑；
    若缓存的请求参数与本次不一致，则自动失效重取（--force 可强制全量重取）。

输出：
    data_lake/interim/tmdb_movies.jsonl   一行一部电影的统一结构记录
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from pathlib import Path
from typing import Any, Iterable

from common.settings import settings
from ingest.http import CollectorHttpError, RateLimitedClient, dump_raw, load_raw
from ingest.schema import fill_review

POSTER_BASE = "https://image.tmdb.org/t/p/w500"
BACKDROP_BASE = "https://image.tmdb.org/t/p/w780"

# TMDB 的 append_to_response，一次请求把需要的关联数据全带回来，省配额
APPEND = "credits,keywords,external_ids,release_dates"


# ============================================================
# 归一化：把 TMDB 的嵌套响应压平成统一结构
# ============================================================


def _clean(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def normalize_movie(raw: dict, genre_map: dict[int, str] | None = None) -> dict:
    """TMDB 原始响应 → 统一电影记录。

    字段命名与旧系统 data/web_movies.json 保持兼容（title / release_year /
    genres_zh / tmdb_id / imdb_id …），这样阶段 2 融合时两批数据能直接对齐。
    """
    genre_map = genre_map or {}

    original = _clean(raw.get("original_title"))
    api_title = _clean(raw.get("title"))
    zh_title = ""
    if api_title and api_title != original:
        # 以 zh-CN 请求时，TMDB 有中文条目会直接返回中文名
        zh_title = api_title
    if not zh_title:
        # 回退到旧项目沉淀的英文→中文译名映射，不浪费已有的数据资产
        from data.chinese_title_map import to_chinese_title

        zh_title = _clean(to_chinese_title(original)) if original else ""
    display_title = zh_title or api_title or original

    genres_zh: list[str] = []
    for g in raw.get("genres") or []:
        name = _clean(g.get("name"))
        if name and name not in genres_zh:
            genres_zh.append(name)
    if not genres_zh:
        for gid in raw.get("genre_ids") or []:
            name = genre_map.get(gid)
            if name and name not in genres_zh:
                genres_zh.append(name)

    credits = raw.get("credits") or {}
    crew = credits.get("crew") or []
    cast = credits.get("cast") or []
    directors = [_clean(c.get("name")) for c in crew if c.get("job") == "Director"]
    directors = [d for d in directors if d]

    keywords = [_clean(k.get("name")) for k in (raw.get("keywords") or {}).get("keywords") or []]

    external = raw.get("external_ids") or {}
    release_date = _clean(raw.get("release_date"))
    year = int(release_date[:4]) if len(release_date) >= 4 and release_date[:4].isdigit() else None

    poster = raw.get("poster_path")
    backdrop = raw.get("backdrop_path")

    return {
        "tmdb_id": raw.get("id"),
        "imdb_id": _clean(external.get("imdb_id")) or None,
        "title": display_title,
        "title_zh": zh_title or None,
        "title_en": original or api_title or None,
        "original_title": original or None,
        "release_date": release_date or None,
        "release_year": year,
        "runtime": raw.get("runtime") or None,
        "overview": _clean(raw.get("overview")),
        "tagline": _clean(raw.get("tagline")),
        "status": _clean(raw.get("status")),
        "genres_zh": genres_zh or ["剧情"],
        "genre_ids": raw.get("genre_ids") or [g.get("id") for g in raw.get("genres") or []],
        "keywords": keywords[:20],
        "director": "、".join(directors[:2]) or None,
        "cast": [_clean(c.get("name")) for c in cast[:5]],
        "vote_average": round(float(raw.get("vote_average") or 0), 1),
        "vote_count": int(raw.get("vote_count") or 0),
        "popularity": round(float(raw.get("popularity") or 0), 2),
        # 票房与预算（美元）；TMDB 详情接口原样给出，缺或 0 归一为 None
        "revenue": int(raw["revenue"]) if (raw.get("revenue") or 0) > 0 else None,
        "budget": int(raw["budget"]) if (raw.get("budget") or 0) > 0 else None,
        "original_language": raw.get("original_language"),
        "spoken_languages": [_clean(l.get("name")) for l in raw.get("spoken_languages") or []],
        "production_countries": [_clean(c.get("name")) for c in raw.get("production_countries") or []],
        "production_country_codes": [c.get("iso_3166_1") for c in raw.get("production_countries") or []],
        "poster_url": f"{POSTER_BASE}{poster}" if poster else None,
        "backdrop_url": f"{BACKDROP_BASE}{backdrop}" if backdrop else None,
        "source": "tmdb",
        "collected_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }


# ============================================================
# 采集器
# ============================================================


class TmdbCollector:
    SOURCE = "tmdb"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        proxy: str | None = None,
        min_interval: float | None = None,
        force: bool = False,
    ) -> None:
        self.api_key = (api_key or settings.tmdb_api_key).strip()
        if not self.api_key:
            raise CollectorHttpError(
                "缺少 TMDB_API_KEY。请复制 .env.example 为 .env 并填入密钥"
                "（https://www.themoviedb.org/settings/api）"
            )
        self.force = force
        self.lang = settings.tmdb_lang
        self.client = RateLimitedClient(
            settings.tmdb_base,
            headers={"User-Agent": "YingJianZhiSou/0.1 (course project)"},
            min_interval=min_interval if min_interval is not None else settings.tmdb_min_interval,
            max_retries=settings.tmdb_max_retries,
            proxy=proxy if proxy is not None else settings.collector_proxy,
        )
        self._genre_map: dict[int, str] | None = None
        self.stats = {"api_calls": 0, "cache_hits": 0}

    # ---------------- 缓存层 ----------------

    def _raw(self, *parts: str) -> Path:
        return settings.lake("raw", "tmdb", *parts)

    def _cached(self, path: str, params: dict, raw_path: Path) -> dict:
        """命中缓存且请求参数一致 → 读盘；否则发请求并把「参数指纹」一起落盘。"""
        if not self.force:
            cached = load_raw(raw_path)
            if isinstance(cached, dict) and cached.get("_request", {}).get("params") == params:
                self.stats["cache_hits"] += 1
                return cached.get("_response", {})

        data = self.client.get_json(path, params)
        self.stats["api_calls"] += 1
        dump_raw({"_request": {"path": path, "params": params}, "_response": data}, raw_path)
        return data

    # ---------------- 基础接口 ----------------

    def genre_map(self) -> dict[int, str]:
        if self._genre_map is not None:
            return self._genre_map
        data = self._cached(
            "/genre/movie/list",
            {"api_key": self.api_key, "language": self.lang},
            self._raw("genre_list.json"),
        )
        self._genre_map = {int(g["id"]): _clean(g["name"]) for g in data.get("genres") or []}
        return self._genre_map

    def discover(
        self,
        page: int = 1,
        *,
        sort_by: str = "popularity.desc",
        min_vote_count: int | None = None,
        year_from: int | None = None,
        year_to: int | None = None,
    ) -> list[dict]:
        """发现影片，返回本页结果列表（含 genre_ids、poster_path 等摘要字段）。"""
        params: dict[str, Any] = {
            "api_key": self.api_key,
            "language": self.lang,
            "region": settings.tmdb_region,
            "sort_by": sort_by,
            "include_adult": "false",
            "include_video": "false",
            "vote_count.gte": min_vote_count if min_vote_count is not None else settings.tmdb_min_vote_count,
            "page": page,
        }
        if year_from:
            params["primary_release_date.gte"] = f"{year_from}-01-01"
        if year_to:
            params["primary_release_date.lte"] = f"{year_to}-12-31"

        data = self._cached("/discover/movie", params, self._raw("discover", f"page_{page}.json"))
        return data.get("results") or []

    def movie_detail(self, tmdb_id: int) -> dict:
        params = {
            "api_key": self.api_key,
            "language": self.lang,
            "append_to_response": APPEND,
        }
        return self._cached("/movie/%d" % int(tmdb_id), params, self._raw("movie", f"{int(tmdb_id)}.json"))

    def search_movie(self, query: str, year: int | None = None) -> list[dict]:
        safe = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", query)[:40] or "query"
        params: dict[str, Any] = {
            "api_key": self.api_key,
            "language": self.lang,
            "query": query,
            "include_adult": "false",
        }
        if year:
            params["year"] = year
        data = self._cached("/search/movie", params, self._raw("search", f"{safe}.json"))
        return data.get("results") or []

    # ---------------- 编排 ----------------

    def collect(
        self,
        *,
        pages: int | None = None,
        limit: int | None = None,
        sort_by: str = "popularity.desc",
        year_from: int | None = None,
        year_to: int | None = None,
        progress: bool = True,
    ) -> list[dict]:
        """发现 → 逐片取详情 → 归一化。返回统一结构记录列表。"""
        pages = pages if pages is not None else settings.tmdb_discover_pages
        genre_map = self.genre_map()

        ids: list[int] = []
        for page in range(1, pages + 1):
            results = self.discover(page, sort_by=sort_by, year_from=year_from, year_to=year_to)
            if not results:
                if progress:
                    print(f"  第 {page} 页无结果，提前结束发现阶段")
                break
            for item in results:
                mid = item.get("id")
                if mid and mid not in ids:
                    ids.append(mid)
            if progress:
                print(f"  发现第 {page} 页：{len(results)} 部，累计去重 {len(ids)} 部")

        if limit:
            ids = ids[:limit]

        records: list[dict] = []
        for idx, mid in enumerate(ids, 1):
            try:
                raw = self.movie_detail(mid)
            except CollectorHttpError as exc:
                print(f"  [跳过] tmdb_id={mid} 详情获取失败：{exc}")
                continue
            records.append(normalize_movie(raw, genre_map))
            if progress and idx % 10 == 0:
                print(f"  详情进度 {idx}/{len(ids)}")

        return records

    # ---------------- 影评（方案 #2 扩展） ----------------

    def movie_reviews_page(self, tmdb_id: int, page: int = 1) -> dict:
        """拉单片影评分页（TMDB /movie/{id}/reviews，返回完整响应含分页信息）。

        注意：影评端点按 `language` 过滤。TMDB 影评以英文 UGC 为主，用 zh-CN 过滤会
        几乎只命中中文片（外片 0 条），严重压缩覆盖。故影评一律用 en-US 拉全量，
        电影元数据仍用 self.lang（zh-CN）拿中文名——两张表各取所需。
        """
        params = {
            "api_key": self.api_key,
            "language": "en-US",
            "page": page,
        }
        return self._cached(
            "/movie/%d/reviews" % int(tmdb_id),
            params,
            self._raw("movie", f"{int(tmdb_id)}_reviews.json"),
        )

    def collect_reviews(
        self,
        movies: list[dict],
        *,
        max_pages: int = 1,
        progress: bool = True,
    ) -> list[dict]:
        """给定电影记录列表（需含 tmdb_id/title/release_year/imdb_id），
        逐片翻页拉影评并归一化到统一影评合同。返回影评记录列表。"""
        records: list[dict] = []
        total = len(movies)
        for idx, movie in enumerate(movies, 1):
            mid = movie.get("tmdb_id")
            if not mid:
                continue
            page = 1
            while page <= max_pages:
                try:
                    data = self.movie_reviews_page(mid, page)
                except CollectorHttpError as exc:
                    print(f"  [跳过] tmdb_id={mid} 影评获取失败：{exc}")
                    break
                results = data.get("results") or []
                if not results:
                    break
                for raw in results:
                    records.append(normalize_review(raw, movie))
                total_pages = data.get("total_pages") or 1
                if page >= total_pages:
                    break
                page += 1
            if progress and idx % 10 == 0:
                print(f"  影评进度 {idx}/{total}，累计 {len(records)} 条")
        return records

    # ---------------- 视频 / 预告片（阶段 1g · 视频数据） ----------------

    def movie_videos_page(self, tmdb_id: int) -> dict:
        """拉单片视频列表（TMDB /movie/{id}/videos）。

        视频端点基本不受 language 影响（返回各地区的官方/非官方片花），
        但 TMDB 仍要求带 language，统一用 en-US。我们只筛 YouTube 的
        Trailer / Teaser —— 这是「视频数据」的合法来源（官方预告片），
        与盗版片源直连无关。
        """
        params = {
            "api_key": self.api_key,
            "language": "en-US",
        }
        return self._cached(
            "/movie/%d/videos" % int(tmdb_id),
            params,
            self._raw("movie", f"{int(tmdb_id)}_videos.json"),
        )

    def collect_videos(
        self,
        movies: list[dict],
        *,
        progress: bool = True,
    ) -> list[dict]:
        """给定电影记录列表（需含 tmdb_id/title/title_zh/release_year），
        逐片拉官方预告片并归一化。返回每部「含预告片」的电影记录。

        输出结构（直接喂给 tmdb_videos 索引）：
            {tmdb_id, title, title_zh, release_year, trailers:[...], trailer_count, ...}
        trailers 内每条：{key, name, type, official, published_at, url}
        url 用 youtube embed 深链（前端 iframe 直接播，注明国内访问限制）。
        """
        records: list[dict] = []
        total = len(movies)
        for idx, movie in enumerate(movies, 1):
            mid = movie.get("tmdb_id")
            if not mid:
                continue
            try:
                data = self.movie_videos_page(mid)
            except CollectorHttpError as exc:
                print(f"  [跳过] tmdb_id={mid} 预告片获取失败：{exc}")
                continue
            trailers: list[dict] = []
            for v in data.get("results") or []:
                if v.get("site") != "YouTube":
                    continue
                if v.get("type") not in ("Trailer", "Teaser"):
                    continue
                youtube_key = v.get("key")
                if not youtube_key:
                    continue
                trailers.append({
                    "key": youtube_key,
                    "name": _clean(v.get("name")),
                    "type": _clean(v.get("type")),
                    "official": bool(v.get("official")),
                    "published_at": _clean(v.get("published_at")) or None,
                    "url": f"https://www.youtube.com/embed/{youtube_key}",
                })
            # 去重（按 key），官方 Trailer 优先
            seen: set[str] = set()
            uniq: list[dict] = []
            for t in sorted(
                trailers,
                key=lambda x: (not x["official"], x["type"] != "Trailer", x["name"] or ""),
            ):
                if t["key"] in seen:
                    continue
                seen.add(t["key"])
                uniq.append(t)
            if uniq:
                records.append({
                    "tmdb_id": str(mid),
                    "title": movie.get("title"),
                    "title_zh": movie.get("title_zh") or movie.get("title"),
                    "release_year": movie.get("release_year"),
                    "trailers": uniq,
                    "trailer_count": len(uniq),
                    "collected_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                    "source": "tmdb",
                })
            if progress and idx % 20 == 0:
                print(f"  预告片进度 {idx}/{total}，累计 {len(records)} 部含预告片")
        return records

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> "TmdbCollector":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()


# ============================================================
# 输出
# ============================================================


def write_jsonl(records: Iterable[dict], path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n += 1
    return n


# ============================================================
# 影评归一化（TMDB /movie/{id}/reviews → 统一影评合同）
# ============================================================

_TAG_RE = re.compile(r"<[^>]+>")
_CJK_RE = re.compile(r"[\u4e00-\u9fff]")


def _clean_review_text(text: Any) -> str:
    text = _TAG_RE.sub(" ", str(text or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _detect_lang(text: str) -> str | None:
    """轻量语言检测：CJK 字符占比高 → zh，否则 en。

    不引入额外依赖；TMDB 影评绝大多数是英文，少量中文用户影评靠此区分，
    直接服务于阶段 4 的跨文化（en/zh）对比，避免系统性误标。
    """
    if not text:
        return None
    cjk = len(_CJK_RE.findall(text))
    ratio = cjk / max(len(text), 1)
    return "zh" if ratio > 0.2 else "en"


def _word_count(text: str) -> int:
    """中英双语词数：CJK 按字计，拉丁字母/数字按词计（无 jieba 依赖）。"""
    cjk = len(_CJK_RE.findall(text))
    latin = len(re.findall(r"[A-Za-z0-9]+", text))
    return cjk + latin


def normalize_review(raw: dict, movie: dict | None = None) -> dict:
    """TMDB 单条影评 → 统一影评记录。

    合规：author 用户名只存 sha256 截断哈希（author_hash），不落明文 PII；
    影评本身是公开内容，但原文链接 review_url 可能含用户名，仍保留以便溯源，
    后续脱敏阶段可按需处理。
    """
    movie = movie or {}
    content = _clean_review_text(raw.get("content"))
    raw_len = len(str(raw.get("content") or ""))
    text_len = len(content)
    word_count = _word_count(content) if content else 0

    author = raw.get("author") or ""
    author_details = raw.get("author_details") or {}
    rating = author_details.get("rating")
    try:
        rating = float(rating) if rating is not None else None
    except (TypeError, ValueError):
        rating = None

    # TMDB 影评语言未标注，且不能简单用影片原始语言推断（常有中文用户影评写英文片）。
    # 基于正文本身做轻量检测，直接服务阶段 4 的跨文化（en/zh）对比。
    lang = _detect_lang(content)

    rec = {
        "review_id": hashlib.sha1(content.encode("utf-8")).hexdigest(),
        "text": content,
        "text_raw_len": raw_len,
        "text_len": text_len,
        "word_count": word_count,
        "sentiment": None,            # 留空，阶段 4 情感分析补全
        "sentiment_score": None,
        "rating": rating,             # TMDB 原始评分（0–10）
        "movie_title": movie.get("title"),
        "movie_year": movie.get("release_year"),
        "imdb_id": movie.get("imdb_id"),
        "lang": lang,
        "dataset": "tmdb",
        "source": "tmdb",
        "source_file": f"raw/tmdb/movie/{movie.get('tmdb_id')}_reviews.json",
        "row_index": None,
        "collected_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        # ---- 可选扩展字段 ----
        "review_url": raw.get("url"),
        "external_id": f"tmdb-{raw.get('id')}",
        "review_type": "user",        # TMDB 影评均为用户影评
        "contains_spoiler": None,     # TMDB 不提供剧透标记
        "author_hash": hashlib.sha256(author.encode("utf-8")).hexdigest()[:16] if author else None,
        "outlet": None,
        "score_norm": rating,         # TMDB 已是 0–10 量纲
        "movie_tmdb_id": movie.get("tmdb_id"),
    }
    return fill_review(rec)
