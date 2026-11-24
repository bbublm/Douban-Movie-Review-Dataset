"""
Metacritic 影评采集（方案 #3）。

为什么没有官方 API：
    Metacritic 没有面向第三方的公开影评 API。本项目**只抓取公开可见的影评页**
    （/movie/{slug}/critic-reviews/ 与 /movie/{slug}/user-reviews/），并严格遵守合规红线：
      · 遵守 robots.txt —— 拉取 / 解析 / 缓存；can_fetch 不通过就跳过该 URL；
      · 礼貌限速 —— METACRITIC_MIN_INTERVAL=2.0s（≤0.5 req/s，反爬严的站更保守）；
      · 不采集个人身份信息 —— 作者名只做 sha256 截断哈希（author_hash），绝不落明文；
      · 不碰登录墙、不绕验证码；公开影评页即可；数据仅用于课程研究。

技术选型与反爬现实（重要）：
    Metacritic 站用了 PerimeterX/HUMAN 这类反爬，裸 httpx 抓公开页**大概率被拦**
    （返回挑战页或 403）。本模块因此提供两条路径：
      · 默认路径：RateLimitedClient + 标准库正则解析（零依赖，离线 fixture 可验证链路）；
      · --browser 兜底：Playwright 真实浏览器渲染后取 DOM（过反爬挑战；
        属正常采集手段，不绕登录墙 / 验证码；需先 `pip install playwright && playwright install chromium`）。

    ⚠ 选择器说明：下列正则针对 Metacritic 长期稳定的 `c-siteReview` 组件类命名，
      但反爬站点改版频繁。若实时抓取时命中率为 0（字段全空），请先用
      `python -m ingest.run_collect metacritic --slug <slug> --browser` 落一份真实页面到
      data_lake/raw/metacritic/ 下，再据此微调 `_RE_*` 常量 —— 这类「换标记」是预期维护。

产物：
    data_lake/raw/metacritic/film_{slug}.html           影片页原始落盘（断点续跑）
    data_lake/raw/metacritic/reviews_{slug}_{type}_p{n}.html  影评页原始落盘
    data_lake/interim/reviews.metacritic.jsonl          归一化影评（transform 自动合并）
"""
from __future__ import annotations

import hashlib
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

from common.settings import settings
from ingest.http import CollectorHttpError, RateLimitedClient
from ingest.robots import PROJECT_USER_AGENT, RobotsPolicy
from ingest.schema import REVIEW_FIELDS, fill_review

METACRITIC_BASE = "https://www.metacritic.com"
MOVIE_PATH = "/movie/{slug}/"
CRITIC_PATH = "/movie/{slug}/critic-reviews/"
USER_PATH = "/movie/{slug}/user-reviews/"


# ----- 解析：针对 Metacritic 的 c-siteReview 组件类（多组候选，标记变化有兜底） -----
_RE_CARD = re.compile(
    r'<(article|div)[^>]+class="[^"]*c-siteReview[^"]*"[^>]*>(.*?)</\1>',
    re.DOTALL | re.IGNORECASE,
)
_RE_TITLE = re.compile(
    r'<h1[^>]+class="[^"]*c-productHero__title[^"]*"[^>]*>(.*?)</h1>',
    re.DOTALL | re.IGNORECASE,
)
_RE_DATA_ID = re.compile(r'data-id="([^"]+)"')
_RE_AUTHOR = re.compile(
    r'class="[^"]*c-siteReview__author[^"]*"[^>]*>(.*?)</',
    re.DOTALL | re.IGNORECASE,
)
_RE_SCORE = re.compile(
    r'(?:data-score|data-metascore)="([\d.]+)"'
    r'|class="[^"]*c-siteReview__rating[^"]*"[^>]*>([\d.]+)'
    r'|class="[^"]*c-siteReview__score[^"]*"[^>]*>([\d.]+)',
    re.IGNORECASE,
)
_RE_DATE = re.compile(
    r'class="[^"]*c-siteReview__date[^"]*"[^>]*>(.*?)</',
    re.DOTALL | re.IGNORECASE,
)
_RE_BODY = re.compile(
    r'class="[^"]*c-siteReview__reviewBody[^"]*"[^>]*>(.*?)</div>',
    re.DOTALL | re.IGNORECASE,
)
_RE_TAG = re.compile(r"<[^>]+>")
_RE_WS = re.compile(r"\s+")
_RE_PAGENEXT = re.compile(r'class="[^"]*c-pagination[^"]*"', re.IGNORECASE)


# ---------------- 纯函数解析层（便于离线自检 / 单测） ----------------


def _strip_tags(html: str) -> str:
    return _RE_TAG.sub(" ", html)


def _clean(text: str) -> str:
    return _RE_WS.sub(" ", _strip_tags(text)).strip()


def parse_title(html: str) -> str | None:
    """从影片页 H1 抽出电影名。"""
    m = _RE_TITLE.search(html)
    return _clean(m.group(1)) if m else None


def parse_reviews(html: str) -> list[dict]:
    """从影评页抽每条影评的原始字段（尚未归一化）。"""
    out: list[dict] = []
    for block in _RE_CARD.findall(html):
        # findall 第二组是卡片内部 HTML（某些 Python 版本返回 tuple）
        inner = block[1] if isinstance(block, tuple) else block
        data_id = _RE_DATA_ID.search(inner)
        author = _RE_AUTHOR.search(inner)
        score = _RE_SCORE.search(inner)
        date = _RE_DATE.search(inner)
        body = _RE_BODY.search(inner)

        raw_score: str | None = None
        if score:
            raw_score = (score.group(1) or score.group(2) or score.group(3))
        raw_text = _strip_tags(body.group(1)) if body else ""
        text = _clean(raw_text)
        if not text:
            # 兜底：取卡片全文（会带噪声，但能保住一条；实时跑建议据此微调选择器）
            text = _clean(inner)
        out.append({
            "external_id": f"mc-{data_id.group(1)}" if data_id else None,
            "author": _clean(author.group(1)) if author else None,
            "score": float(raw_score) if raw_score else None,
            "review_date": _clean(date.group(1)) if date else None,
            "text": text,
            "text_raw_len": len(raw_text),
        })
    return out


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def score_to_sentiment(score_0_100: float | None) -> tuple[str | None, float | None]:
    """Metacritic 0–100 分 → (sentiment, sentiment_score)。

    score_norm（0–10）已归一；这里在其上做情感判定：≥70 正向、≤40 负向，中间中性；
    sentiment_score 以 50 为中性点线性映射到 [-1, 1]。
    """
    if score_0_100 is None:
        return None, None
    s = score_0_100
    if s >= 70:
        label = "positive"
    elif s <= 40:
        label = "negative"
    else:
        label = "neutral"
    score = max(-1.0, min(1.0, (s - 50.0) / 50.0))
    return label, round(score, 3)


def normalize_review(
    raw: dict,
    *,
    slug: str,
    review_type: str,
    movie_title: str | None = None,
    source_file: str | None = None,
) -> dict:
    """把一个原始影评归一化到统一影评合同（core + 可选扩展）。"""
    text = raw.get("text") or ""
    author = raw.get("author")
    score = raw.get("score")
    score_norm = round(score / 10.0, 1) if score is not None else None

    sentiment, sentiment_score = score_to_sentiment(score)
    author_hash = (
        hashlib.sha256(author.encode("utf-8")).hexdigest()[:16] if author else None
    )

    record = {
        # ---- 核心字段 ----
        "review_id": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "text": text,
        "text_raw_len": raw.get("text_raw_len") or len(text),
        "text_len": len(text),
        "word_count": len(text.split()) if text else 0,   # 英文 user 评为主，按词计
        "sentiment": sentiment,                            # 由分数推（Metacritic 不标情感）
        "sentiment_score": sentiment_score,
        "rating": score,                                   # Metacritic 原始 0–100 分
        "movie_title": movie_title,
        "movie_year": None,
        "imdb_id": None,
        "lang": "en",
        "dataset": "metacritic",
        "source": "metacritic",
        "source_file": source_file,
        "row_index": None,
        "collected_at": _now_iso(),
        # ---- 可选扩展字段 ----
        "review_url": f"{METACRITIC_BASE}/movie/{slug}/"
                      f"{'critic' if review_type == 'critic' else 'user'}-reviews/",
        "external_id": raw.get("external_id"),
        "review_type": review_type,           # critic / user
        "contains_spoiler": None,             # Metacritic 不提供剧透标记
        "author_hash": author_hash,           # ⚠ 匿名，绝不存明文作者
        "outlet": "Metacritic",
        "score_norm": score_norm,             # 0–10 归一
        "movie_tmdb_id": None,
    }
    return fill_review(record)


# ---------------- 采集器（带限速 / robots / 落盘续跑） ----------------


class MetacriticCollector:
    def __init__(
        self,
        *,
        force: bool = False,
        proxy: str = "",
        min_interval: float | None = None,
        max_pages: int | None = None,
        max_reviews: int | None = None,
        user_agent: str | None = None,
        robots: RobotsPolicy | None = None,
        fixture_dir: Path | None = None,
        use_browser: bool = False,
    ) -> None:
        self.force = force
        self.min_interval = (
            min_interval if min_interval is not None else settings.metacritic_min_interval
        )
        self.max_pages = (
            max_pages if max_pages is not None else settings.metacritic_max_pages
        )
        self.max_reviews = (
            max_reviews if max_reviews is not None else settings.metacritic_max_reviews
        )
        self.user_agent = (
            user_agent or settings.metacritic_user_agent or PROJECT_USER_AGENT
        )
        self.robots = robots or RobotsPolicy(user_agent=self.user_agent)
        self.fixture_dir = fixture_dir  # 离线 demo：直接读夹具，不走网络
        self.use_browser = use_browser  # 实时抓取走真实浏览器（过反爬挑战）

        self.client = RateLimitedClient(
            METACRITIC_BASE,
            headers={"User-Agent": self.user_agent},
            min_interval=self.min_interval,
            proxy=proxy,
            timeout=25,
        )
        self._pw = None
        self._browser = None
        self._ctx = None
        self.stats = {
            "pages": 0, "reviews": 0, "skipped_robots": 0,
            "skipped_empty": 0, "films": 0, "fields_missing": 0,
        }

    # ---------------- 内部 ----------------

    def _check_robots(self, path: str) -> bool:
        url = METACRITIC_BASE + path
        if not self.robots.can_fetch(url):
            self.stats["skipped_robots"] += 1
            print(f"    [robots] 禁止抓取 {url}，跳过")
            return False
        return True

    def _get_html(self, path: str, *, raw_name: str, quiet: bool = False) -> str | None:
        # 离线 demo：直接读夹具，跳过网络与 robots
        if self.fixture_dir is not None:
            slug = self._slug_from_path(path)
            if slug:
                # 路径相关夹具：影片页 / critic 页 / user 页 各不相同，避免同一份
                # 综合夹具被三个路径反复解析导致重复计数；缺某个就退化到通用文件。
                movie_base = MOVIE_PATH.format(slug=slug).rstrip("/")
                critic_base = CRITIC_PATH.format(slug=slug).rstrip("/")
                user_base = USER_PATH.format(slug=slug).rstrip("/")
                if path.rstrip("/") == movie_base:
                    name = f"metacritic_{slug}_film.html"
                elif path.startswith(critic_base):
                    name = f"metacritic_{slug}_critic.html"
                elif path.startswith(user_base):
                    name = f"metacritic_{slug}_user.html"
                else:
                    name = f"metacritic_{slug}.html"
                fx = self.fixture_dir / name
                if fx.exists():
                    return fx.read_text(encoding="utf-8")
            return None

        raw_path = settings.lake("raw", "metacritic", raw_name)
        if not self.force and raw_path.exists():
            return raw_path.read_text(encoding="utf-8")
        if not self._check_robots(path):
            return None

        if self.use_browser:
            html = self._browser_get_html(path)
        else:
            html = self.client.get_text(path, quiet=quiet)

        raw_path.parent.mkdir(parents=True, exist_ok=True)
        raw_path.write_text(html, encoding="utf-8")
        self.stats["pages"] += 1
        return html

    def _ensure_browser(self) -> None:
        """惰性启动 Playwright + Chromium（仅 --browser 时）。"""
        if self._browser is not None:
            return
        try:
            from playwright.sync_api import sync_playwright  # noqa: PLC0415
        except ImportError as exc:  # pragma: no cover
            raise CollectorHttpError(
                "未安装 Playwright。请先：pip install playwright && playwright install chromium"
            ) from exc
        self._pw = sync_playwright().start()
        self._browser = self._pw.chromium.launch(headless=True)
        self._ctx = self._browser.new_context(
            user_agent=self.user_agent, locale="en-US", accept_downloads=False,
        )

    def _browser_get_html(self, path: str) -> str:
        """用真实浏览器抓页面，返回渲染后的 HTML（过反爬挑战）。"""
        self._ensure_browser()
        time.sleep(self.min_interval)
        url = METACRITIC_BASE + path
        page = self._ctx.new_page()
        try:
            page.goto(url, wait_until="networkidle", timeout=30000)
            page.wait_for_timeout(1500)
            return page.content()
        finally:
            page.close()

    @staticmethod
    def _slug_from_path(path: str) -> str | None:
        m = re.search(r"/movie/([^/]+)/", path)
        return m.group(1) if m else None

    # ---------------- 对外 ----------------

    def collect(
        self,
        seeds: Iterable[str],
        *,
        types: tuple[str, ...] = ("critic", "user"),
    ) -> Iterator[dict]:
        for seed in seeds:
            slug = str(seed).strip().lstrip("/")
            if slug.endswith("/"):
                slug = slug[:-1]
            if not slug:
                continue
            self.stats["films"] += 1
            print(f"  · 影片 slug={slug}")

            film_html = self._get_html(
                MOVIE_PATH.format(slug=slug), raw_name=f"film_{slug}.html", quiet=True
            )
            movie_title = parse_title(film_html) if film_html else None

            for rtype in types:
                if rtype == "critic":
                    base = CRITIC_PATH.format(slug=slug)
                else:
                    base = USER_PATH.format(slug=slug)

                total_for_type = 0
                for page in range(1, self.max_pages + 1):
                    path = base if page == 1 else f"{base.rstrip('/')}/page-{page}/"
                    raw_name = f"reviews_{slug}_{rtype}_p{page}.html"
                    rv_html = self._get_html(path, raw_name=raw_name, quiet=True)
                    if not rv_html:
                        break
                    rows = parse_reviews(rv_html)
                    if not rows:
                        self.stats["skipped_empty"] += 1
                        break
                    for raw in rows:
                        if not raw.get("score") or not raw.get("author"):
                            self.stats["fields_missing"] += 1
                        rec = normalize_review(
                            raw, slug=slug, review_type=rtype,
                            movie_title=movie_title, source_file=raw_name,
                        )
                        self.stats["reviews"] += 1
                        total_for_type += 1
                        yield rec
                        if self.max_reviews and self.stats["reviews"] >= self.max_reviews:
                            return
                print(f"    {rtype} 影评 {total_for_type} 条")
            print(f"    本片累计采集影评 {self.stats['reviews']} 条（含其它片）")

    def close(self) -> None:
        if self._browser is not None:
            try:
                self._browser.close()
                self._pw.stop()
            except Exception:  # noqa: BLE001
                pass
            self._browser = None
            self._ctx = None
        self.client.close()

    def __enter__(self) -> "MetacriticCollector":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()
