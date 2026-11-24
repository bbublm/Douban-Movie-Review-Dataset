"""
电影盒子 FastAPI 应用入口。

启动：
    uvicorn backend.main:app --reload --port 8000     （在 yingjian-zhisou/ 目录下执行）

文档：
    http://localhost:8000/docs      Swagger UI
    http://localhost:8000/redoc     ReDoc
"""
from __future__ import annotations

import traceback
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from backend.api.v1.router import api_router
from backend.middleware import RateLimitMiddleware, RequestLogMiddleware
from backend.services.auth import hash_password
from backend.services.ratings_store import ensure_ratings_index
from backend.services.user_store import ensure_users_index, seed_demo_admin
from backend.services.watchlist_store import ensure_watchlist_index
from common.es_client import close_es, get_es
from common.settings import settings

STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """启动时不再预热 ES，避免 ES 未就绪时服务直接起不来；
    连通性交给 /api/v1/health 按需探测。

    用户索引与演示管理员在这里自举：ES 未就绪时不阻塞启动
    （课程演示常常先起后端再起 ES，这里失败只打印警告）。
    ratings / watchlist 索引同理自举 —— 新用户进页面时
    GET /ratings、GET /watchlist 就该能返回空列表，
    而不是 index_not_found_exception。
    """
    print(f"[{settings.app_name}] 启动中 … ES={settings.es_host_list}")
    try:
        es = get_es()
        await ensure_users_index(es)
        await ensure_ratings_index(es)
        await ensure_watchlist_index(es)
        seeded = await seed_demo_admin(es, hash_password(settings.admin_password))
        if seeded:
            print(f"[{settings.app_name}] 已播种演示管理员 admin（口令见 .env 的 ADMIN_PASSWORD）")
    except Exception as exc:  # noqa: BLE001 —— 自举失败不阻塞启动，登录时按未登录处理
        print(f"[{settings.app_name}] 用户索引自举跳过：{type(exc).__name__}: {exc}")
    yield
    await close_es()
    print(f"[{settings.app_name}] 已关闭")


app = FastAPI(
    title=settings.app_name,
    description="多源影评大数据检索与趣味发现平台 —— 网络爬虫 + 大数据分析 + 可视化",
    version="0.1.0",
    lifespan=lifespan,
)


# ---------- 中间件（add 顺序 = 从内到外，最后 add 的在最外层）----------
# 从内到外：RequestLog（贴近路由，记真实处理耗时）
#         → RateLimit（先于路由挡掉超额请求）
#         → CORS（最外层，保证 429 等响应也带 CORS 头，浏览器才读得到）
app.add_middleware(RequestLogMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix="/api/v1")


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """全局兜底：任何漏网的异常都返回 JSON 500，而不是 Starlette 的纯文本 500。

    三件事：
    1. traceback 进服务端日志（排查看完整堆栈）；
    2. 响应体**不泄露**异常细节（生产安全），debug 模式下给类型名方便定位；
    3. 带上 X-Request-ID 的 request_id——用户报障时报这串就能在日志里定位。
    """
    traceback.print_exc()
    request_id = getattr(request.state, "request_id", None)
    return JSONResponse(
        status_code=500,
        content={
            "detail": "服务器内部错误，请稍后重试；若持续出现请带上 request_id 反馈",
            "request_id": request_id,
            **({"error_type": type(exc).__name__} if settings.debug else {}),
        },
    )


@app.get("/", include_in_schema=False)
async def index():
    """浏览器直接访问根路径时，给出一个极简自检页。"""
    page = STATIC_DIR / "index.html"
    if page.exists():
        return FileResponse(page)
    return {
        "app": settings.app_name,
        "docs": "/docs",
        "health": "/api/v1/health",
    }


if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
