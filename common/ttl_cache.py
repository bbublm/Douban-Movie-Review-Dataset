"""
轻量异步 TTL 缓存（单机内存版），给"重查询 + 结果不随用户变"的接口用。

原系统有 5 分钟缓存的思路，新栈继承。应用点（且只应用在这些点）：
    · GET /recommend/popular   热门榜（贝叶斯 WR 全库聚合）
    · GET /insights/trends     年代趋势（histogram 聚合）
    · GET /insights/sentiment  情感统计（读分析产物 + 统计）
用户维度数据（for-you / ratings / watchlist / auth）**一律不缓存**——
那些数据必须即时，缓存它们会展示别人的列表。

三个设计决定：

1. **single-flight（等锁不重复打）**。缓存过期瞬间，10 个并发请求如果
   同时发现"过期了"，会 10 个一起打 ES（缓存雪崩）。用 per-key 锁 +
   双重检查：第一个请求去生产，其余等锁后直接拿它生产好的值。
2. **不缓存异常**。producer 抛异常时不写缓存，下次请求重试——
   把一次网络抖动缓存 5 分钟，比不缓存更糟。
3. **有界内存**。maxsize 上限 + FIFO 淘汰（dict 保序，O(1)）。
   命中/未命中/淘汰计数外发给 /health/metrics，缓存有没有起作用用数字说话。

单实例有效：多实例部署要换 Redis（决策写在这里，别等踩坑才想起）。
"""
from __future__ import annotations

import asyncio
import time
from typing import Any, Awaitable, Callable

from common.settings import settings

Producer = Callable[[], Awaitable[Any]]


class TTLCache:
    """异步 TTL 缓存。用法：

        cache = TTLCache(default_ttl=300)
        value = await cache.get_or_set("popular:20", lambda: popular_movies(20))
    """

    def __init__(self, default_ttl: float = 300.0, maxsize: int = 256) -> None:
        self.default_ttl = default_ttl
        self.maxsize = maxsize
        self._store: dict[str, tuple[float, Any]] = {}   # key -> (过期时刻, 值)
        self._locks: dict[str, asyncio.Lock] = {}
        self._inflight: dict[str, asyncio.Task] = {}     # key -> 正在生产的任务
        # 统计（有界：全是标量）
        self.hits = 0
        self.misses = 0
        self.stores = 0
        self.evictions = 0

    def stats(self) -> dict:
        total = self.hits + self.misses
        return {
            "keys": len(self._store),
            "maxsize": self.maxsize,
            "default_ttl_seconds": self.default_ttl,
            "hits": self.hits,
            "misses": self.misses,
            "stores": self.stores,
            "evictions": self.evictions,
            "hit_rate": round(self.hits / total, 3) if total else None,
        }

    def _put(self, key: str, value: Any, ttl: float) -> None:
        now = time.monotonic()
        self._store[key] = (now + ttl, value)
        self.stores += 1
        while len(self._store) > self.maxsize:
            oldest, _ = next(iter(self._store.items()))  # dict 保序，最早的在最前
            del self._store[oldest]
            self._locks.pop(oldest, None)
            self.evictions += 1

    async def get_or_set(self, key: str, producer: Producer,
                         ttl: float | None = None) -> Any:
        """取缓存；未命中则调 producer() 生产并写入。

        同一 key 的并发调用只触发一次 producer（single-flight）：
        第一个请求持锁生产，其余请求等锁后拿到现成值。
        """
        now = time.monotonic()
        entry = self._store.get(key)
        if entry is not None and entry[0] > now:
            self.hits += 1
            return entry[1]
        self.misses += 1

        lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            # 双重检查：等锁期间可能已有协程填好（或刚好又过期了）
            entry = self._store.get(key)
            fresh = time.monotonic()
            if entry is not None and entry[0] > fresh:
                return entry[1]
            value = await producer()  # 异常不上缓存，直接抛给调用方
            self._put(key, value, ttl if ttl is not None else self.default_ttl)
            return value

    def invalidate(self, prefix: str = "") -> int:
        """清缓存（可按 key 前缀清）。返回清了几条。

        用法：写路径（如重新 build 索引）后调 invalidate("popular")
        让旧榜单立刻失效，而不是等 TTL 到期。
        """
        if not prefix:
            n = len(self._store)
            self._store.clear()
            self._locks.clear()
            return n
        victims = [k for k in self._store if k.startswith(prefix)]
        for k in victims:
            del self._store[k]
            self._locks.pop(k, None)
        return len(victims)


# 进程级共享缓存（中间件统计与各 service 共用同一个实例，命中数才准）。
# 默认 TTL 走 settings.cache_ttl_seconds（.env 可覆盖，默认 300 秒）。
cache = TTLCache(default_ttl=float(settings.cache_ttl_seconds))
