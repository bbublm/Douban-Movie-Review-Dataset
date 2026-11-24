"""
robots.txt 合规工具 —— 所有爬虫的「第一道闸门」。

为什么单独抽出来：
    合规要求里第一条就是「遵守 robots.txt 和平台条款」。
    但每个源各自写一遍 robots 解析既重复又容易漏，所以统一成一个
    RobotsPolicy：拉取 + 解析 + 内存缓存 + can_fetch / crawl_delay。

实现要点：
    · 用标准库 urllib（无额外依赖），跟随系统代理设置；
    · 拉取失败（网络被拦 / 404）时**默认允许抓取但打印警告**，
      宁可多一句提醒，也不要因为 robots.txt 拉不到就把整批任务卡死；
    · crawl_delay 作为「平台自己声明的礼貌间隔」返回给上层，
      Letterboxd 等源把它与自己的 min_interval 取 max，双保险。
"""
from __future__ import annotations

import time
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from urllib.robotparser import RobotFileParser

# 项目统一 UA：能识别调用方 + 留联系方式，符合 Wikimedia / Letterboxd 的要求。
# 注意：纯 "Python-urllib/x" 经常被反爬直接挡，所以前面拼一段真实浏览器 UA 降低误杀。
PROJECT_USER_AGENT = (
    "Mozilla/5.0 (compatible; YingJianZhiSou/0.1; course project; "
    "+https://github.com/yingjian-zhisou) Python-urllib"
)


class RobotsPolicy:
    """按 netloc 缓存 robots.txt 的合规策略。"""

    def __init__(
        self,
        user_agent: str | None = None,
        *,
        cache_ttl: int = 86400,
        fail_closed: bool = False,
    ) -> None:
        self.user_agent = user_agent or PROJECT_USER_AGENT
        self.cache_ttl = cache_ttl
        self.fail_closed = fail_closed
        # netloc -> (fetched_at, RobotFileParser | None)
        self._cache: dict[str, tuple[float, RobotFileParser | None]] = {}

    def _fetch(self, netloc: str) -> RobotFileParser | None:
        cached = self._cache.get(netloc)
        now = time.time()
        if cached and now - cached[0] < self.cache_ttl:
            return cached[1]

        robots_url = f"https://{netloc}/robots.txt"
        rp = RobotFileParser()
        rp.set_url(robots_url)
        try:
            req = Request(robots_url, headers={"User-Agent": self.user_agent})
            with urlopen(req, timeout=10) as resp:
                rp.parse(resp.read().decode("utf-8", "replace").splitlines())
        except Exception as exc:  # noqa: BLE001 —— 任何拉取异常都降级为「允许 + 提醒」
            print(f"    [robots] 拉取 {robots_url} 失败（{type(exc).__name__}），"
                  f"{'按 fail-closed 策略禁止抓取' if self.fail_closed else '默认允许抓取，请人工复核该站 robots 条款'}")
            rp = None
        self._cache[netloc] = (now, rp)
        return rp

    def can_fetch(self, url: str) -> bool:
        netloc = urlparse(url).netloc
        rp = self._fetch(netloc)
        if rp is None:
            return not self.fail_closed
        return bool(rp.can_fetch(self.user_agent, url))

    def crawl_delay(self, url: str) -> float | None:
        netloc = urlparse(url).netloc
        rp = self._fetch(netloc)
        if rp is None:
            return None
        try:
            return rp.crawl_delay(self.user_agent)
        except Exception:  # noqa: BLE001
            return None
