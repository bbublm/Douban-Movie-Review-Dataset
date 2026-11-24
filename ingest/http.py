"""
采集层统一的 HTTP 客户端：限速 + 重试 + 原始响应落盘。

为什么不用裸 requests / httpx？
    1. 各数据源都有速率限制（TMDB 官方约 50 req/s，礼貌起见我们压到 4 req/s），
       需要一个全局节流器，否则容易被临时封禁，答辩演示时直接翻车；
    2. 采集最怕「跑了一半挂了」，所以每个原始响应都要落盘，
       重跑时命中缓存直接读盘 —— 这就是断点续跑；
    3. 429 / 5xx 要按 Retry-After 退避重试，而不是直接抛错中断整批任务。
"""
from __future__ import annotations

import json
import random
import threading
import time
from pathlib import Path
from typing import Any

import httpx

# 这些状态码值得重试；其余 4xx 基本是参数写错或 Key 失效，重试没意义
RETRY_STATUS = {408, 429, 500, 502, 503, 504}


def _hint(status: int | None) -> str:
    """重试耗尽后按状态码给一句可操作的提示。

    为什么要这个：WDQS（query.wikidata.org）对数据中心/共享出口 IP
    经常直接返回 429，重试 4 次、每次退避 30 秒就是白等两分钟，
    而错误信息只有一句 "HTTP 429"，用户完全不知道下一步该干什么。
    """
    if status == 429:
        return (
            "\n    [提示] 服务端限流（HTTP 429），通常是出口 IP 被临时封禁或请求过于频繁。"
            "\n           继续重试一般无效，建议："
            "\n             ① 等几分钟再跑（限额会自动恢复）；"
            "\n             ② 用 --proxy http://127.0.0.1:端口 走本机代理换出口 IP；"
            "\n             ③ 先跑 --demo 离线验证链路，等网络恢复再采真实数据。"
        )
    if status in (500, 502, 503, 504):
        return "\n    [提示] 服务端 5xx，多为临时故障，稍后重试通常即可恢复。"
    return ""


class CollectorHttpError(RuntimeError):
    """采集过程中无法自动恢复的错误。"""


class RateLimitedClient:
    """带全局限速与指数退避的同步 HTTP 客户端。

    同步而非异步：采集是顺序 IO + 落盘的脚本任务，同步代码更好读、好调试。
    真需要并发时，在外面套一层 ThreadPoolExecutor 即可，限速器是线程安全的。
    """

    def __init__(
        self,
        base_url: str,
        *,
        headers: dict[str, str] | None = None,
        min_interval: float = 0.25,
        max_retries: int = 4,
        timeout: float = 20.0,
        proxy: str = "",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        proxy = proxy or ""
        self.min_interval = min_interval
        self.max_retries = max_retries
        self._lock = threading.Lock()
        self._last_call = 0.0

        kwargs: dict[str, Any] = {
            "base_url": self.base_url,
            "headers": headers or {},
            "timeout": timeout,
            "follow_redirects": True,
        }
        if proxy.strip().lower() == "direct":
            # 强制直连：忽略系统里的 HTTP_PROXY / HTTPS_PROXY
            kwargs["trust_env"] = False
        elif proxy.strip():
            kwargs["proxy"] = proxy.strip()

        self._client = httpx.Client(**kwargs)

    # ---------------- 内部 ----------------

    def _throttle(self) -> None:
        """全局最小请求间隔，保证整进程的请求速率不超过上限。"""
        with self._lock:
            gap = self.min_interval - (time.monotonic() - self._last_call)
            if gap > 0:
                time.sleep(gap)
            self._last_call = time.monotonic()

    @staticmethod
    def _backoff(attempt: int, retry_after: str | None = None) -> float:
        if retry_after:
            try:
                return min(float(retry_after), 30.0)
            except ValueError:
                pass
        # 2, 4, 8, 16 秒，加一点抖动避免多进程共振
        return min(2.0 ** attempt, 30.0) + random.uniform(0, 0.5)

    # ---------------- 对外 ----------------

    def get_json(self, path: str, params: dict | None = None, *, quiet: bool = False) -> dict:
        """GET 并解析 JSON，失败按退避策略重试。"""
        last_err: Exception | None = None
        last_status: int | None = None

        for attempt in range(1, self.max_retries + 1):
            self._throttle()
            try:
                resp = self._client.get(path, params=params)
            except httpx.HTTPError as exc:
                last_err = exc
                last_status = None
                delay = self._backoff(attempt)
                if not quiet:
                    print(f"    [网络异常] {type(exc).__name__}，{delay:.1f}s 后重试 {attempt}/{self.max_retries}")
                time.sleep(delay)
                continue

            if resp.status_code == 200:
                return resp.json()

            if resp.status_code in RETRY_STATUS:
                last_status = resp.status_code
                last_err = CollectorHttpError(f"HTTP {resp.status_code} {path}")
                delay = self._backoff(attempt, resp.headers.get("Retry-After"))
                if not quiet:
                    print(f"    [限流/服务端异常] HTTP {resp.status_code}，{delay:.1f}s 后重试 {attempt}/{self.max_retries}")
                time.sleep(delay)
                continue

            # 401 / 404 之类，直接失败并给出可读信息
            raise CollectorHttpError(
                f"HTTP {resp.status_code} {self.base_url}{path} -> {resp.text[:300]}"
            )

        raise CollectorHttpError(
            f"{self.base_url}{path} 重试 {self.max_retries} 次仍失败：{last_err}{_hint(last_status)}"
        )

    def get_text(self, path: str, params: dict | None = None, *, quiet: bool = False) -> str:
        """GET 并返回文本（HTML 源），失败按退避策略重试。

        与 get_json 共用同一套全局节流与指数退避——HTML 源（Letterboxd 影评页、
        Metacritic 页面等）和 JSON API 走同一个限速器，保证整进程速率可控。
        """
        last_err: Exception | None = None
        last_status: int | None = None

        for attempt in range(1, self.max_retries + 1):
            self._throttle()
            try:
                resp = self._client.get(path, params=params)
            except httpx.HTTPError as exc:
                last_err = exc
                last_status = None
                delay = self._backoff(attempt)
                if not quiet:
                    print(f"    [网络异常] {type(exc).__name__}，{delay:.1f}s 后重试 {attempt}/{self.max_retries}")
                time.sleep(delay)
                continue

            if resp.status_code == 200:
                return resp.text

            if resp.status_code in RETRY_STATUS:
                last_status = resp.status_code
                last_err = CollectorHttpError(f"HTTP {resp.status_code} {path}")
                delay = self._backoff(attempt, resp.headers.get("Retry-After"))
                if not quiet:
                    print(f"    [限流/服务端异常] HTTP {resp.status_code}，{delay:.1f}s 后重试 {attempt}/{self.max_retries}")
                time.sleep(delay)
                continue

            raise CollectorHttpError(
                f"HTTP {resp.status_code} {self.base_url}{path} -> {resp.text[:300]}"
            )

        raise CollectorHttpError(
            f"{self.base_url}{path} 重试 {self.max_retries} 次仍失败：{last_err}{_hint(last_status)}"
        )

    def get_final_url(self, path: str, params: dict | None = None) -> str:
        """GET 并返回最终 URL（处理 3xx 重定向后）。

        Letterboxd 没有「按 tmdb_id 查影片」的官方接口，但有
        https://letterboxd.com/tmdb/{id}/ 这个会 302 跳转到 /film/{slug}/ 的入口。
        顺着重定向拿到最终 URL 就能反查出 slug，免去「片名搜索」的不确定性。
        同样走全局节流。
        """
        self._throttle()
        resp = self._client.get(path, params=params, follow_redirects=True)
        return str(resp.url)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "RateLimitedClient":
        return self

    def __exit__(self, *exc_info) -> None:
        self.close()


# ---------------- 原始响应落盘工具 ----------------


def dump_raw(payload: Any, path: Path) -> None:
    """把原始响应写盘，供断点续跑与「数据可追溯」答辩讲解使用。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_raw(path: Path) -> Any | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        # 上次写盘写到一半被 Ctrl+C 打断，当作没有缓存
        return None
