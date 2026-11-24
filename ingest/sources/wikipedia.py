"""
Wikipedia API 采集器 —— 阶段 1c（下半）。

Wikidata 给的是「结构化事实」（导演是谁、哪年上映、在哪拍），
但**没有可读的剧情文本**。剧情摘要来自维基百科条目首段，
它是阶段 4「情感分析 / 主题分析」的唯一自然语言语料来源
（TMDB 的 overview 普遍只有一两句话，做主题分析太薄）。

三个实现要点：
    1. **批量**：MediaWiki 允许 `titles=A|B|C` 一次问多页。
       但默认 `exlimit=1` 只会给**第一个**页面返回正文 ——
       必须显式写 `exlimit=max`（非机器人账号上限 20 页/次），
       否则你会以为"取到了 20 条"，实际只有 1 条有内容、19 条是空串。
    2. **标题映射**：请求里的标题可能被 `normalized`（下划线/首字母）
       或 `redirects`（重定向）改掉，响应里返回的是**改后**的标题。
       所以响应里同时带有 normalized / redirects 两张映射表，
       本模块用它们把结果映射回「你请求时用的标题」，
       否则调用方按原标题去查会全部 miss。
    3. **`missing: true`**：条目不存在时该 page 只有 title 和 missing，
       要跳过而不是当成「摘要是空字符串」。

产物：
    data_lake/raw/wikipedia/extract/*.json   原始响应（按标题集合的 md5 命名）
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Iterable, Iterator
from urllib.parse import urlsplit

from common.settings import settings
from ingest.http import CollectorHttpError, RateLimitedClient, dump_raw, load_raw

# 非机器人账号一次最多 20 个标题（exlimit=max 的上限）
BATCH_TITLES = 20


def _split_api(url: str) -> tuple[str, str]:
    """把 https://zh.wikipedia.org/w/api.php 拆成 (base, path)。

    RateLimitedClient 需要 base_url + path 两段，而 .env 里配的是一个完整 URL。
    """
    parts = urlsplit(url)
    base = f"{parts.scheme}://{parts.netloc}"
    path = parts.path or "/w/api.php"
    if parts.query:
        path = f"{path}?{parts.query}"
    return base, path


def _clean_extract(text: Any, limit: int | None = None) -> str:
    """摘要清洗：压掉多余空白，并按字数截断。

    截断是为了控制索引体积；1500 字对「首段摘要」几乎不会截到，
    真需要全文时把 .env 的 WIKI_EXTRACT_CHARS 调大即可。
    """
    if not text:
        return ""
    cleaned = re.sub(r"[ \t\u00a0]+", " ", str(text))
    cleaned = re.sub(r"\n{2,}", "\n", cleaned).strip()
    cap = limit if limit is not None else settings.wiki_extract_chars
    return cleaned[:cap] if cap and cap > 0 else cleaned


def parse_wikipedia_payload(
    payload: dict | None, requested: Iterable[str] | None = None
) -> dict[str, dict]:
    """解析 MediaWiki `action=query&prop=extracts` 的响应。

    返回 {标题: {pageid, title, extract, url}}。
    键既包含响应里的实际标题，也包含 `requested` 里传进来的**原始标题**
    （通过 normalized / redirects 映射还原）—— 调用方用哪个标题都能取到。
    """
    query = (payload or {}).get("query") or {}
    pages = query.get("pages") or []
    if isinstance(pages, dict):            # 未加 formatversion=2 时是字典
        pages = list(pages.values())

    found: dict[str, dict] = {}
    for page in pages:
        if not isinstance(page, dict) or page.get("missing"):
            continue                       # 条目不存在：跳过，不当成"空摘要"
        title = page.get("title")
        if not title:
            continue
        found[title] = {
            "pageid": page.get("pageid"),
            "title": title,
            "extract": _clean_extract(page.get("extract")),
            "url": page.get("fullurl"),
        }

    # 建立 原始标题 → 实际标题 的映射
    alias: dict[str, str] = {}
    for table in ("normalized", "redirects"):
        for item in query.get(table) or []:
            if isinstance(item, dict) and item.get("from") and item.get("to"):
                alias[item["from"]] = item["to"]

    def resolve(title: str) -> str:
        # normalized 和 redirects 可能连环两级（先规范化再重定向），所以循环解
        for _ in range(5):
            nxt = alias.get(title)
            if not nxt or nxt == title:
                break
            title = nxt
        return title

    out = dict(found)
    for title in requested or []:
        real = resolve(title)
        if real in found:
            out[title] = found[real]
    return out


class WikipediaCollector:
    SOURCE = "wikipedia"

    def __init__(
        self,
        *,
        api_url: str | None = None,
        proxy: str | None = None,
        min_interval: float | None = None,
        force: bool = False,
    ) -> None:
        self.base, self.path = _split_api(api_url or settings.wikipedia_api)
        self.force = force
        self.client = RateLimitedClient(
            self.base,
            headers={"User-Agent": settings.wikidata_user_agent},
            min_interval=min_interval if min_interval is not None else settings.wiki_min_interval,
            max_retries=settings.tmdb_max_retries,
            proxy=proxy if proxy is not None else settings.collector_proxy,
        )
        self.stats = {"api_calls": 0, "cache_hits": 0, "titles": 0}

    # ---------------- 缓存层 ----------------

    def _raw(self, titles: list[str]) -> Path:
        digest = hashlib.md5("|".join(titles).encode("utf-8")).hexdigest()[:16]
        return settings.lake("raw", "wikipedia", "extract", f"{digest}.json")

    def _cached(self, params: dict, titles: list[str], *, quiet: bool = False) -> dict:
        raw_path = self._raw(titles)
        if not self.force:
            cached = load_raw(raw_path)
            if isinstance(cached, dict) and cached.get("_request", {}).get("params") == params:
                self.stats["cache_hits"] += 1
                return cached.get("_response") or {}
        payload = self.client.get_json(self.path, params, quiet=quiet)
        self.stats["api_calls"] += 1
        dump_raw({"_request": {"path": self.path, "params": params}, "_response": payload}, raw_path)
        return payload

    # ---------------- 对外 ----------------

    def extract_batch(self, titles: list[str], *, quiet: bool = False) -> dict[str, dict]:
        """一批取条目首段摘要。"""
        uniq = [t for t in dict.fromkeys(t.strip() for t in titles) if t][:BATCH_TITLES]
        if not uniq:
            return {}
        params: dict[str, Any] = {
            "action": "query",
            "format": "json",
            "formatversion": "2",
            "prop": "extracts|info",
            "exintro": "1",          # 只要首段，不要全文（全文动辄几十 KB）
            "explaintext": "1",      # 纯文本，不带 HTML 标签，便于做文本分析
            "exlimit": "max",        # ★ 不写这个只会返回第一条的正文
            "redirects": "1",        # 自动跟重定向
            "inprop": "url",         # 顺带返回条目完整 URL
            "titles": "|".join(uniq),
        }
        payload = self._cached(params, uniq, quiet=quiet)
        self.stats["titles"] += len(uniq)
        return parse_wikipedia_payload(payload, requested=uniq)

    def collect(self, titles: Iterable[str], *, progress: bool = True) -> dict[str, dict]:
        """按批取摘要，合并成一个 {标题: 摘要} 字典。"""
        uniq = [t for t in dict.fromkeys(titles) if t]
        out: dict[str, dict] = {}
        total = len(uniq)
        for start in range(0, total, BATCH_TITLES):
            chunk = uniq[start:start + BATCH_TITLES]
            try:
                out.update(self.extract_batch(chunk, quiet=not progress))
            except CollectorHttpError as exc:
                print(f"    [跳过一批] 维基摘要取失败：{exc}")
                continue
            if progress:
                print(f"    维基摘要 {min(start + BATCH_TITLES, total)}/{total} 条")
        return out

    def close(self) -> None:
        self.client.close()

    def __enter__(self) -> "WikipediaCollector":
        return self

    def __exit__(self, *exc_info) -> None:
        self.client.close()
