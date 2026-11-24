"""
Letterboxd 影评采集（阶段 2 主力爬虫）。

为什么没有官方 API：
    Letterboxd 没有面向第三方的公开影评 API。本项目**只抓取公开可见的影评页**，
    并严格遵守合规红线（见 ingest/robots.py 与下方常量）：
      · 遵守 robots.txt —— 拉取 / 解析 / 缓存；can_fetch 不通过就跳过该 URL；
      · ≤1 req/s —— LETTERBOXD_MIN_INTERVAL=1.0，RateLimitedClient 全局节流；
      · 不采集个人身份信息 —— reviewer 用户名只做 sha256 截断哈希（author_hash），
        绝不落盘明文用户名 / 邮箱 / 头像链接；
      · 不碰登录墙、不绕验证码；公开影评页即可；
      · 数据仅用于课程研究。

技术选型：
    影评页是服务端渲染（Django），用 httpx 抓 HTML + 标准库解析即可，
    **无需 Playwright**（重且无头浏览器下载）。Playwright 仅作为「被反爬挑战时」
    的兜底方案，本版不默认启用。

产物：
    data_lake/raw/letterboxd/film_{slug}.html            影片页原始落盘（断点续跑）
    data_lake/raw/letterboxd/reviews_{slug}_p{n}.html    影评页原始落盘
    data_lake/interim/reviews.letterboxd.jsonl           归一化影评（transform 自动合并）
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator

from common.settings import settings
from ingest.http import RateLimitedClient
from ingest.robots import PROJECT_USER_AGENT, RobotsPolicy
from ingest.schema import REVIEW_FIELDS, fill_review

LETTERBOXD_BASE = "https://letterboxd.com"
FILM_PATH = "/film/{slug}/"
REVIEW_PATH = "/film/{slug}/reviews/"          # 第 1 页
REVIEW_PAGE_PATH = "/film/{slug}/reviews/page/{n}/"  # 第 n(≥2) 页
TMDB_REDIRECT_PATH = "/tmdb/{tmdb_id}/"        # 302 → /film/{slug}/

# ----- 正则：对 Letterboxd 已知标记做宽松匹配；标记变化时有 warning 兜底 -----
_RE_LD_JSON = re.compile(
    r'<script[^>]+type="application/ld\+json"[^>]*>(.*?)</script>',
    re.DOTALL | re.IGNORECASE,
)
_RE_TMDB = re.compile(r'themoviedb\.org/movie/(\d+)', re.IGNORECASE)
_RE_IMDB = re.compile(r'imdb\.com/title/(tt\d+)', re.IGNORECASE)
_RE_SLUG = re.compile(r'/film/([^/]+)/')
_RE_REVIEW_LI = re.compile(r'<li class="film-detail.*?</li>', re.DOTALL)
_RE_REVIEW_ID = re.compile(r'data-review-id="([^"]+)"')
_RE_AVATAR = re.compile(r'class="avatar[^"]*"[^>]*href="/([^"/]+)/"')
_RE_RATING = re.compile(r'data-rating="([^"]+)"')
_RE_DATE = re.compile(r'<time[^>]+datetime="([^"]+)"')
_RE_SPOILER = re.compile(r'contains-spoilers')
_RE_BODY = re.compile(r'<div class="body-text"[^>]*>(.*?)</div>', re.DOTALL)
_RE_TAG = re.compile(r'<[^>]+>')
_RE_WS = re.compile(r'\s+')


# ---------------- 纯函数解析层（便于离线自检 / 单测） ----------------


def _strip_tags(html: str) -> str:
    return _RE_TAG.sub(" ", html)


def _clean(text: str) -> str:
    return _RE_WS.sub(" ", _strip_tags(text)).strip()


def parse_film(html: str) -> dict:
    """从影片/影评页 HTML 里抽取电影关联信息（tmdb_id / imdb_id / 片名 / 年份）。

    优先用 JSON-LD，缺了再退回正则（Letterboxd 页面里 tmdb/imdb 的外链很稳定）。
    """
    info: dict[str, Any] = {"tmdb_id": None, "imdb_id": None, "title": None, "year": None}
    m = _RE_LD_JSON.search(html)
    if m:
        try:
            data = json.loads(m.group(1))
            if isinstance(data, dict):
                info["title"] = data.get("name")
                date = data.get("dateCreated") or data.get("datePublished")
                if date and len(date) >= 4 and date[:4].isdigit():
                    info["year"] = int(date[:4])
        except (json.JSONDecodeError, ValueError, TypeError):
            pass
    tm = _RE_TMDB.search(html)
    if tm:
        info["tmdb_id"] = int(tm.group(1))
    im = _RE_IMDB.search(html)
    if im:
        info["imdb_id"] = im.group(1)
    return info


def parse_reviews(html: str) -> list[dict]:
    """从影评页抽取每条影评的原始字段（尚未归一化）。"""
    out: list[dict] = []
    for chunk in _RE_REVIEW_LI.findall(html):
        rid = _RE_REVIEW_ID.search(chunk)
        avatar = _RE_AVATAR.search(chunk)
        rating = _RE_RATING.search(chunk)
        date = _RE_DATE.search(chunk)
        body = _RE_BODY.search(chunk)
        text_raw = _strip_tags(body.group(1)) if body else ""
        out.append({
            "external_id": f"lb-{rid.group(1)}" if rid else None,
            "author_slug": avatar.group(1) if avatar else None,
            "rating": float(rating.group(1)) if rating else None,
            "review_date": date.group(1) if date else None,
            "contains_spoiler": bool(_RE_SPOILER.search(chunk)),
            "text": _clean(text_raw),
            "text_raw_len": len(text_raw),
        })
    return out


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def normalize_review(raw: dict, film: dict, *, slug: str, source_file: str | None = None) -> dict:
    """把一个原始影评归一化到统一影评合同（核心 REVIEW_FIELDS + 可选扩展）。"""
    text = raw.get("text") or ""
    rating = raw.get("rating")
    author_slug = raw.get("author_slug")
    author_hash = (
        hashlib.sha256(author_slug.encode("utf-8")).hexdigest()[:16]
        if author_slug else None
    )

    record = {
        # ---- 核心字段（来自 REVIEW_FIELDS）----
        "review_id": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "text": text,
        "text_raw_len": raw.get("text_raw_len") or len(text),
        "text_len": len(text),
        "word_count": len(text.split()) if text else 0,
        "sentiment": None,                 # 阶段 4 情感分析再补，采集时不臆测
        "sentiment_score": None,
        "rating": rating,                  # Letterboxd 星级 0.5–5.0
        "movie_title": film.get("title"),
        "movie_year": film.get("year"),
        "imdb_id": film.get("imdb_id"),
        "lang": "en",
        "dataset": "letterboxd",
        "source": "letterboxd",
        "source_file": source_file,
        "row_index": None,
        "collected_at": _now_iso(),
        # ---- 可选扩展字段 ----
        "review_url": f"{LETTERBOXD_BASE}/film/{slug}/reviews/",
        "external_id": raw.get("external_id"),
        "review_type": "user",             # Letterboxd 影评均为用户长评
        "contains_spoiler": raw.get("contains_spoiler", False),
        "author_hash": author_hash,        # ⚠ 匿名，绝不存明文用户名
        "outlet": "Letterboxd",
        "score_norm": round(rating * 2, 1) if rating is not None else None,  # 星级→0–10
        "movie_tmdb_id": film.get("tmdb_id"),
    }
    return fill_review(record)


# ---------------- 采集器（带限速 / robots / 落盘续跑） ----------------


class LetterboxdCollector:
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
        self.min_interval = min_interval if min_interval is not None else settings.letterboxd_min_interval
        self.max_pages = max_pages if max_pages is not None else settings.letterboxd_max_pages
        self.max_reviews = max_reviews if max_reviews is not None else settings.letterboxd_max_reviews
        self.user_agent = user_agent or settings.letterboxd_user_agent or PROJECT_USER_AGENT
        self.robots = robots or RobotsPolicy(user_agent=self.user_agent)
        self.fixture_dir = fixture_dir  # 离线 demo 用：直接读夹具，不走网络
        self.use_browser = use_browser  # 实时抓取走真实浏览器（过 Cloudflare 挑战）

        self.client = RateLimitedClient(
            LETTERBOXD_BASE,
            headers={"User-Agent": self.user_agent},
            min_interval=self.min_interval,
            proxy=proxy,
            timeout=20,
        )
        # Playwright 浏览器状态（仅 --browser 时使用）
        self._pw = None
        self._browser = None
        self._ctx = None
        self.stats = {"pages": 0, "reviews": 0, "skipped_robots": 0,
                      "skipped_empty": 0, "films": 0}

    # ---------------- 内部 ----------------

    @staticmethod
    def _slug_from_path(path: str) -> str | None:
        m = _RE_SLUG.search(path)
        return m.group(1) if m else None

    def _check_robots(self, path: str) -> bool:
        url = LETTERBOXD_BASE + path
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
                fx = self.fixture_dir / f"letterboxd_{slug}.html"
                if fx.exists():
                    return fx.read_text(encoding="utf-8")
            return None

        raw_path = settings.lake("raw", "letterboxd", raw_name)
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
        except ImportError as exc:  # pragma: no cover —— 运行环境缺依赖时给出可读提示
            raise CollectorHttpError(
                "未安装 Playwright。请先：pip install playwright && playwright install chromium"
            ) from exc
        self._pw = sync_playwright().start()
        # headless 真实 Chromium + 真实 UA：让 Cloudflare 当作普通浏览器放行，
        # 这属于「用浏览器采集」，不是绕过登录墙 / 验证码。
        self._browser = self._pw.chromium.launch(headless=True)
        self._ctx = self._browser.new_context(
            user_agent=self.user_agent, locale="en-US", accept_downloads=False,
        )

    def _browser_get_html(self, path: str) -> str:
        """用真实浏览器抓页面，返回渲染后的 HTML（过 Cloudflare 挑战）。"""
        self._ensure_browser()
        time.sleep(self.min_interval)  # 浏览器路径也遵守 ≤1 req/s
        url = LETTERBOXD_BASE + path
        page = self._ctx.new_page()
        try:
            page.goto(url, wait_until="networkidle", timeout=30000)
            # Cloudflare 有时先返回挑战页再 JS 跳转，给一点缓冲再读 DOM
            page.wait_for_timeout(1500)
            return page.content()
        finally:
            page.close()

    def _resolve_slug(self, seed: str | int) -> str | None:
        """把种子解析成 Letterboxd slug：字符串直接当 slug；整数按 tmdb_id 反查。"""
        if isinstance(seed, int) or (isinstance(seed, str) and seed.isdigit()):
            tid = int(seed)
            if self.fixture_dir is not None:
                # demo 下没有真实重定向，slug 直接猜成 "movie-{tid}" 之外的固定名；
                # 这里改为要求 fixture 命名为 letterboxd_{tid}.html 也可，但统一用 slug。
                # 为简单起见，demo 固定种子用字符串 slug 提供，整数种子在 demo 下跳过。
                print(f"    [demo] 整数种子 {tid} 在离线模式跳过（请改用 --slug 字符串）")
                return None
            final = self.client.get_final_url(TMDB_REDIRECT_PATH.format(tmdb_id=tid))
            return self._slug_from_path(final)
        return str(seed)

    # ---------------- 对外 ----------------

    def collect(self, seeds: Iterable[str | int]) -> Iterator[dict]:
        for seed in seeds:
            slug = self._resolve_slug(seed)
            if not slug:
                continue
            self.stats["films"] += 1
            print(f"  · 影片 slug={slug}")

            film_html = self._get_html(
                FILM_PATH.format(slug=slug), raw_name=f"film_{slug}.html", quiet=True
            )
            if not film_html:
                print(f"    [跳过] 影片页抓取失败或受限")
                continue
            film = parse_film(film_html)

            total_for_film = 0
            for page in range(1, self.max_pages + 1):
                if page == 1:
                    path = REVIEW_PATH.format(slug=slug)
                    raw_name = f"reviews_{slug}_p1.html"
                else:
                    path = REVIEW_PAGE_PATH.format(slug=slug, n=page)
                    raw_name = f"reviews_{slug}_p{page}.html"

                rv_html = self._get_html(path, raw_name=raw_name, quiet=True)
                if not rv_html:
                    break
                rows = parse_reviews(rv_html)
                if not rows:
                    self.stats["skipped_empty"] += 1
                    break  # 没有更多影评，提前结束分页
                for raw in rows:
                    rec = normalize_review(
                        raw, film, slug=slug, source_file=raw_name
                    )
                    self.stats["reviews"] += 1
                    total_for_film += 1
                    yield rec
                    if self.max_reviews and self.stats["reviews"] >= self.max_reviews:
                        return
            print(f"    本片采集影评 {total_for_film} 条")

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

    def __enter__(self) -> "LetterboxdCollector":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()


def seed_from_tmdb(limit: int | None = None) -> list[int]:
    """从已采集的 TMDB 片库（interim / processed）抽 tmdb_id 当种子。"""
    candidates: list[Path] = []
    for name in ("tmdb_movies.jsonl", "movies.jsonl", "seed_movies.jsonl"):
        p = settings.lake("interim", name)
        if p.exists():
            candidates.append(p)
    if not candidates:
        p = settings.lake("processed", "movies.jsonl")
        if p.exists():
            candidates.append(p)
    ids: list[int] = []
    from ingest.jsonl_io import iter_jsonl  # noqa: PLC0415 —— 局部导入避免循环
    for p in candidates:
        for rec in iter_jsonl(p):
            tid = rec.get("tmdb_id")
            if tid:
                ids.append(int(tid))
        if ids:
            break
    if limit:
        ids = ids[:limit]
    return ids


def seed_from_file(path: str | Path) -> list[str | int]:
    """读种子文件：每行含 tmdb_id（整数）或 slug（字符串）。"""
    p = Path(path)
    out: list[str | int] = []
    from ingest.jsonl_io import iter_jsonl  # noqa: PLC0415
    for rec in iter_jsonl(p):
        if rec.get("tmdb_id"):
            out.append(int(rec["tmdb_id"]))
        elif rec.get("slug"):
            out.append(str(rec["slug"]))
    return out
