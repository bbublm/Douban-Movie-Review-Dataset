"""
RSS 影视新闻采集（方案 #4）—— 零依赖（标准库 xml + httpx）。

数据源：Variety / THR / Deadline 等公开 RSS（在 settings.rss_feeds 配置）。
合规：RSS 即授权再分发；保留 outlet 署名与原文 link；轮询间隔保守（默认 30min 级别，
      采集时按 --min-interval 控制相邻 feed 之间的礼貌节流）；绝不采集评论区用户 PII。

技术选型：feedparser 未安装且本沙箱无法联网安装，RSS 是简单 XML，用标准库
      xml.etree.ElementTree 直接解析即可，无额外依赖。

输出：data_lake/interim/news.jsonl（NEWS_FIELDS），按 article_id(sha1(link)) 幂等累加；
      配合 ES 独立索引 news（舆情时间线）使用，索引接入见 index/ 模块（阶段 5 后续）。
"""
from __future__ import annotations

import hashlib
import html
import json
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import httpx

from common.settings import settings
from ingest.schema import NEWS_FIELDS

# 项目统一 UA（robots / 礼貌标识）
PROJECT_USER_AGENT = (
    "Mozilla/5.0 (compatible; YingJianZhiSou/0.1; course project; "
    "+https://github.com/yingjian-zhisou)"
)


def default_feeds() -> list[tuple[str, str]]:
    """解析 settings.rss_feeds → [(outlet, url), ...]。"""
    feeds: list[tuple[str, str]] = []
    for part in (settings.rss_feeds or "").split(";"):
        part = part.strip()
        if not part or "|" not in part:
            continue
        name, url = part.split("|", 1)
        feeds.append((name.strip(), url.strip()))
    return feeds


# ============================================================
# 解析（标准库，RSS 2.0 + Atom）
# ============================================================

_TAG_RE = re.compile(r"<[^>]+>")


def _text(el: ET.Element | None) -> str:
    return (el.text or "").strip() if el is not None else ""


def _clean_html(raw: str) -> str:
    raw = _TAG_RE.sub(" ", raw or "")
    raw = html.unescape(raw)          # 解码 &#8220; &amp; 等 HTML 实体
    return re.sub(r"\s+", " ", raw).strip()


def _parse_date(s: str | None) -> str | None:
    """RFC 822 (RSS pubDate) / RFC 3339 (Atom) → ISO-8601 UTC。"""
    if not s:
        return None
    try:
        dt = parsedate_to_datetime(s)
        if dt is not None:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except (TypeError, ValueError):
        pass
    # 退化：尝试直接解析 ISO
    try:
        return datetime.fromisoformat(s).astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return None


def parse_feed(xml_text: str) -> list[dict]:
    """把 RSS/Atom XML 解析成统一的中介结构（与具体源无关）。"""
    root = ET.fromstring(xml_text)
    # RSS 2.0：rss/channel/item ；Atom：feed/entry
    items = root.findall(".//item") or root.findall(".//{http://www.w3.org/2005/Atom}entry")

    entries: list[dict] = []
    for it in items:
        # 标题
        title = _text(it.find("title")) or _text(
            it.find("{http://www.w3.org/2005/Atom}title")
        )
        # 链接：RSS 用 <link> 文本；Atom 用 <link href=...>
        link_el = it.find("link")
        if link_el is not None and link_el.get("href"):
            link = link_el.get("href")
        else:
            link = _text(link_el)
        # 摘要：RSS <description> 或 content:encoded；Atom <summary>/<content>
        desc = (
            _text(it.find("description"))
            or _text(it.find("{http://purl.org/rss/1.0/modules/content/}encoded"))
            or _text(it.find("{http://www.w3.org/2005/Atom}summary"))
            or _text(it.find("{http://www.w3.org/2005/Atom}content"))
        )
        # 发布时间
        pub = _text(it.find("pubDate")) or _text(
            it.find("{http://www.w3.org/2005/Atom}updated")
        )
        # 分类
        cats = []
        for c in it.findall("category"):
            txt = _text(c) or (c.get("term") or "")
            if txt:
                cats.append(txt)
        entries.append(
            {
                "title": title,
                "link": link,
                "summary": _clean_html(desc),
                "published_raw": pub,
                "categories": cats,
            }
        )
    return entries


# ============================================================
# 归一化 → NEWS_FIELDS
# ============================================================


def normalize_news(entry: dict, outlet: str) -> dict:
    link = entry.get("link") or ""
    article_id = hashlib.sha1(link.encode("utf-8")).hexdigest()
    rec = {
        "article_id": article_id,
        "title": entry.get("title") or "",
        "link": link,
        "summary": (entry.get("summary") or "")[:4000],
        "published_at": _parse_date(entry.get("published_raw")),
        "outlet": outlet,
        "categories": entry.get("categories", [])[:10],
        "language": "en",
        "sentiment": None,        # 留空，阶段 4 舆情分析补全
        "source": "rss",
        "collected_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    # 补齐剩余 NEWS_FIELDS（缺则 None），下游 DataFrame 列不对齐
    for f in NEWS_FIELDS:
        rec.setdefault(f, None)
    return rec


# ============================================================
# 采集器（含条件 GET：ETag / Last-Modified，避免重复拉取）
# ============================================================


class RssCollector:
    SOURCE = "rss"

    def __init__(
        self,
        *,
        min_interval: float | None = None,
        timeout: int | None = None,
        proxy: str | None = None,
        feeds: list[tuple[str, str]] | None = None,
        user_agent: str | None = None,
    ) -> None:
        self.min_interval = min_interval if min_interval is not None else settings.rss_min_interval
        self.timeout = timeout if timeout is not None else settings.rss_timeout
        self.proxy = proxy if proxy is not None else settings.collector_proxy
        self.feeds = feeds if feeds is not None else default_feeds()
        self.user_agent = user_agent or PROJECT_USER_AGENT
        self.stats = {"feeds": 0, "entries": 0, "skipped_304": 0, "errors": 0}

    def _state_path(self, outlet: str) -> Path:
        return settings.lake("raw", "rss", f"{outlet}.state.json")

    def fetch_feed(self, outlet: str, url: str) -> list[dict]:
        state_path = self._state_path(outlet)
        state: dict[str, str] = {}
        if state_path.exists():
            try:
                state = json.loads(state_path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                state = {}

        headers = {"User-Agent": self.user_agent, "Accept": "application/rss+xml, application/xml, text/xml"}
        if state.get("etag"):
            headers["If-None-Match"] = state["etag"]
        if state.get("modified"):
            headers["If-Modified-Since"] = state["modified"]

        try:
            with httpx.Client(proxy=self.proxy or None, timeout=self.timeout,
                              follow_redirects=True) as client:
                r = client.get(url, headers=headers)
        except httpx.HTTPError as exc:
            print(f"  [跳过] {outlet} 抓取失败：{exc}")
            self.stats["errors"] += 1
            return []

        if r.status_code == 304:
            print(f"  {outlet}: 304 未修改，跳过（条件 GET 命中）")
            self.stats["skipped_304"] += 1
            return []

        # 更新条件 GET 凭证并落盘原始 XML（断点/审计）
        new_state = {
            "etag": r.headers.get("etag"),
            "modified": r.headers.get("last-modified"),
        }
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(new_state), encoding="utf-8")
        (settings.lake("raw", "rss", f"{outlet}.xml")).write_text(r.text or "", encoding="utf-8")

        if r.status_code != 200:
            print(f"  [跳过] {outlet} HTTP {r.status_code}")
            self.stats["errors"] += 1
            return []

        try:
            entries = parse_feed(r.text or "")
        except ET.ParseError as exc:
            print(f"  [跳过] {outlet} 解析失败：{exc}")
            self.stats["errors"] += 1
            return []
        print(f"  {outlet}: {len(entries)} 条（HTTP 200）")
        self.stats["feeds"] += 1
        self.stats["entries"] += len(entries)
        return entries

    def collect(self) -> list[dict]:
        records: list[dict] = []
        for i, (outlet, url) in enumerate(self.feeds):
            entries = self.fetch_feed(outlet, url)
            for e in entries:
                records.append(normalize_news(e, outlet))
            # 礼貌节流：相邻 feed 之间间隔
            if self.min_interval and i < len(self.feeds) - 1:
                time.sleep(self.min_interval)
        return records


def write_jsonl(records: list[dict], path: Path) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n += 1
    return n
