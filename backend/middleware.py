"""
安全与运维中间件：限流、请求日志、全局异常兜底。

为什么放一个文件？
    这三件事都横切所有请求（每个请求都要过），放各自的 router 里管不到。
    原 Flask 系统就有 IP 限流与全局错误页，新栈在中间件层继承同样的意识。

三个部件（都可离线单测，不起服务）：

1. `RateLimiter`   —— 内存滑动窗口计数器。两个窗口：
   · general：单 IP 每分钟总请求数（SPA 一页十几个请求，240 够用不误伤）
   · auth_fail：单 IP 每分钟**失败**的登录/注册次数（成功即清零——
     正常用户登录不受限，爆破者 10 次/分钟就被挡；bcrypt cost=12 再叠一层）
   **内存纪律**：每个 IP 一个 deque 存时间戳，过期即弹出，长度天然有界；
   全局 IP 表设 MAX_TRACKED_IPS 上限，超出整体清空（课程项目单机部署，
   被 DDoS 到 1 万个 IP 时，限流表本身不该成为内存炸弹）。
   **单实例有效**：多实例水平扩容要换 Redis，决策写在这里备查。

2. `RequestStats` —— 进程内请求统计。计数器 + 最近 N 条摘要（deque maxlen=500）。
   给 /health/metrics 用：演示"服务真的在跑"比空口说更有说服力。
   同样有界，绝不无限增长。

3. `RequestLogMiddleware` —— 每条 API 请求打一行日志（方法/路径/状态/耗时），
   并生成 X-Request-ID 贯穿响应头与 500 错误体（出问题时用户报 ID 就能定位）。
   debug=False 或探针请求不打日志（健康探针每秒一次，打日志会刷爆）。

4. `RateLimitMiddleware` —— 把 RateLimiter 挂到请求链上。429 带 Retry-After。
   探针路径（/health/live、/health/ready）与文档路径豁免——
   健康检查被限流会导致部署平台误杀服务，文档被限流会挡掉答辩演示。
"""
from __future__ import annotations

import time
import traceback
import uuid
from collections import deque
from dataclasses import dataclass, field

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from common.settings import settings

# 参与「登录失败计次」的路径前缀（响应 401/409 记一次失败，200 清零）
_AUTH_PATHS = ("/api/v1/auth/login", "/api/v1/auth/register")

# 探针、文档与「缓存型静态资源」：不限流、不打请求日志。
# ★ /api/v1/img 是海报代理：白名单域名 + 1 天浏览器缓存，本身不是业务 API。
#   走廊一屏就挂 14 张海报，画廊还会再拉一批；若和业务接口共用
#   rate_limit_general_per_minute 这一个桶，用户快速逛几间展厅就会把
#   自己的图片打成 429（控制台一片红、海报裂图）。这里单独放行，
#   安全边界仍由 img.py 的域名白名单 + 响应体大小限制守住。
_EXEMPT_PREFIXES = (
    "/api/v1/health/live",
    "/api/v1/health/ready",
    "/api/v1/img",
    "/docs",
    "/redoc",
    "/openapi.json",
    "/static",
    "/favicon.ico",
)


class RateLimiter:
    """滑动窗口限流器（纯内存逻辑，可离线单测）。

    用法：
        limiter = RateLimiter()
        ok, retry_after = limiter.hit("1.2.3.4", limit=10, window=60)
    """

    MAX_TRACKED_IPS = 10_000  # 全局 IP 表上限，超出整体清空（见文件头内存纪律）

    def __init__(self) -> None:
        # key -> deque[float]（该 key 在窗口内的请求时间戳）
        self._hits: dict[str, deque[float]] = {}

    def hit(self, key: str, limit: int, window: float) -> tuple[bool, float]:
        """记一次访问。返回 (是否放行, 被拒时需等待的秒数)。

        limit <= 0 视为不限制（配置关闸用）。
        过期时间戳在每次 hit 时惰性清理，不需要额外定时任务。
        """
        if limit <= 0:
            return True, 0.0
        now = time.monotonic()
        bucket = self._hits.get(key)
        if bucket is None:
            if len(self._hits) >= self.MAX_TRACKED_IPS:
                self._hits.clear()  # 有界性优先于精确性：被清后从头计数
            bucket = deque()
            self._hits[key] = bucket
        cutoff = now - window
        while bucket and bucket[0] <= cutoff:
            bucket.popleft()
        if len(bucket) >= limit:
            retry_after = max(0.0, bucket[0] + window - now)
            return False, round(retry_after, 3)
        bucket.append(now)
        return True, 0.0

    def clear(self, key: str) -> None:
        """清零某个 key（登录成功时清掉它的失败计数）。"""
        self._hits.pop(key, None)

    def __len__(self) -> int:
        return len(self._hits)


@dataclass
class RequestStats:
    """进程内请求统计（有界）。snapshot() 给 /health/metrics。"""

    started_at: float = field(default_factory=time.time)
    total: int = 0
    errors: int = 0          # 5xx
    client_errors: int = 0   # 4xx
    rate_limited: int = 0    # 429
    _recent: deque = field(default_factory=lambda: deque(maxlen=500))
    _slowest: float = 0.0
    _total_seconds: float = 0.0

    def record(self, method: str, path: str, status: int, seconds: float) -> None:
        self.total += 1
        self._total_seconds += seconds
        self._slowest = max(self._slowest, seconds)
        if status >= 500:
            self.errors += 1
        elif status >= 400:
            self.client_errors += 1
            if status == 429:
                self.rate_limited += 1
        self._recent.append({
            "method": method,
            "path": path,
            "status": status,
            "ms": round(seconds * 1000, 1),
            "at": round(time.time(), 3),
        })

    def snapshot(self) -> dict:
        uptime = max(0.0, time.time() - self.started_at)
        return {
            "uptime_seconds": round(uptime, 1),
            "requests": {
                "total": self.total,
                "errors_5xx": self.errors,
                "client_errors_4xx": self.client_errors,
                "rate_limited_429": self.rate_limited,
            },
            "latency_ms": {
                "avg": round(self._total_seconds / self.total * 1000, 1) if self.total else 0.0,
                "slowest": round(self._slowest * 1000, 1),
            },
            "recent": list(self._recent)[-20:],  # 只外发最近 20 条
        }


# 进程级单例（中间件与 /health/metrics 共享）
stats = RequestStats()


def _client_ip(request: Request) -> str:
    """取客户端 IP。默认不信任 X-Forwarded-For（直连部署无法验证该头，
    信了就等于把限流钥匙交给客户端）。套代理且由代理覆写该头时才在 .env 打开。
    """
    if settings.rate_limit_trust_forwarded_for:
        fwd = request.headers.get("x-forwarded-for", "")
        if fwd:
            return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _is_exempt(path: str) -> bool:
    return any(path.startswith(p) for p in _EXEMPT_PREFIXES)


class RequestLogMiddleware(BaseHTTPMiddleware):
    """请求日志 + X-Request-ID + 统计。"""

    async def dispatch(self, request: Request, call_next):
        request_id = uuid.uuid4().hex[:12]
        request.state.request_id = request_id
        path = request.url.path
        log_it = settings.debug and not _is_exempt(path)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            # 兜底日志：异常交给 app 级 handler 出 JSON，这里只保证有迹可查
            stats.record(request.method, path, 500, time.perf_counter() - started)
            raise
        elapsed = time.perf_counter() - started
        stats.record(request.method, path, response.status_code, elapsed)
        response.headers["X-Request-ID"] = request_id
        if log_it:
            print(f"[api] {request_id} {request.method} {path} "
                  f"-> {response.status_code} {elapsed * 1000:.0f}ms")
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """IP 限流 + 登录失败计次。"""

    def __init__(self, app) -> None:
        super().__init__(app)
        self._general = RateLimiter()
        self._auth_fail = RateLimiter()

    @staticmethod
    def _too_many(retry_after: float, request_id: str | None) -> JSONResponse:
        return JSONResponse(
            status_code=429,
            content={
                "detail": "请求过于频繁，请稍后再试",
                "retry_after": retry_after,
                "request_id": request_id,
            },
            headers={"Retry-After": str(max(1, int(retry_after) + 1))},
        )

    async def dispatch(self, request: Request, call_next):
        if not settings.rate_limit_enabled or _is_exempt(request.url.path):
            return await call_next(request)

        ip = _client_ip(request)
        request_id = getattr(request.state, "request_id", None)

        # 1) 总请求限流
        ok, retry_after = self._general.hit(
            f"general:{ip}", settings.rate_limit_general_per_minute, 60.0)
        if not ok:
            return self._too_many(retry_after, request_id)

        # 2) 认证失败计次：请求前先看是否已被挡
        # ★ 变量名教训：hit() 第一个返回值是「是否放行」（True=放行）。
        #   这里曾写成 blocked = hit(...) + if blocked: 429 —— 语义整个反了，
        #   表现为"正常请求被 429、真爆破者反而放行"。离线测 hit 本身抓不到
        #   这种接线错误（纯函数语义是对的），是实测第一个 register 就 429 暴露的。
        is_auth = request.url.path in _AUTH_PATHS
        if is_auth:
            allowed, retry_after = self._auth_fail.hit(
                f"auth:{ip}", settings.rate_limit_auth_fail_per_minute, 60.0)
            if not allowed:
                return self._too_many(retry_after, request_id)

        response = await call_next(request)

        # 3) 请求后按结果更新失败计数
        if is_auth:
            if response.status_code < 400:
                self._auth_fail.clear(f"auth:{ip}")       # 登录成功即清零
            elif response.status_code in (401, 409):
                # 失败已由请求前的 hit 记入；这里只保证"成功才清"的语义完整
                pass
        return response
