"""图片代理路由：`GET /api/v1/img?url=<图片完整URL>`。

为什么要有这个接口：
    海报图片存在 image.tmdb.org，这个域名直连不通（被墙）。
    用户浏览器没有代理时，前端所有 <img> 会全部裂图——数据再全也白搭。
    所以让后端代浏览器取图：服务端按 IMAGE_FETCH_PROXY 走代理出口，
    前端引用本地路径，对用户完全透明。

安全边界：
    只允许代理白名单域名（image.tmdb.org），防止被当成开放代理滥用。
    响应带 Cache-Control，浏览器缓存 1 天，TMDB 图片 URL 本身内容不变。

磁盘缓存（2026-11-05 加）：
    TMDB 图床在当前网络里**间歇性不可达**（SNI 阻断，时通时断）。
    只靠浏览器 1 天缓存不够——容器重启 / 换浏览器就全裂。
    所以成功取到的图永久落盘 `data_lake/cache/posters/`（docker 挂卷），
    之后无论网络通不通都读本地；取不到的才返回手绘占位 SVG（短缓存 60s）。
"""
from __future__ import annotations

import asyncio
import hashlib
import os
from pathlib import Path
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, HTTPException, Query, Response

from common.settings import settings

router = APIRouter()

# 允许代理的图片域名白名单（精确域名 + 后缀域名两种写法）
ALLOWED_IMAGE_HOSTS = {"image.tmdb.org"}
# 后缀匹配：豆瓣图床按 img1~img9.doubanio.com 分片，用后缀统一放行
ALLOWED_IMAGE_SUFFIXES = ("doubanio.com",)
# 部分图床校验防盗链 Referer（豆瓣 418），按后缀注入对应来源页
REFERER_BY_SUFFIX = {"doubanio.com": "https://movie.douban.com/"}


# 上游图床偶发 502（容器出网抖动 / 单张图临时不可达）。
# 与其把 5xx 甩给浏览器（控制台红字、<img> 裂图、3D 走廊挂画空白），
# 不如降级成一张本地自绘占位海报：HTTP 200 + 只缓存 60 秒，
# 网络恢复后浏览器自动重新取回真图，页面永远不出现「破图」。
_FALLBACK_POSTER = """<svg xmlns="http://www.w3.org/2000/svg" width="500" height="750" viewBox="0 0 500 750">
<rect width="500" height="750" fill="#F6F1E6"/>
<rect x="18" y="18" width="464" height="714" fill="#FBF7EE" stroke="#4A3C2C" stroke-width="3"/>
<rect x="30" y="30" width="440" height="470" fill="#E7D7B8" stroke="#4A3C2C" stroke-width="1.5"/>
<circle cx="250" cy="250" r="118" fill="none" stroke="#8B5E1C" stroke-width="14"/>
<circle cx="250" cy="250" r="30" fill="#8B5E1C"/>
<circle cx="250" cy="146" r="20" fill="#FBF7EE" stroke="#8B5E1C" stroke-width="5"/>
<circle cx="354" cy="250" r="20" fill="#FBF7EE" stroke="#8B5E1C" stroke-width="5"/>
<circle cx="250" cy="354" r="20" fill="#FBF7EE" stroke="#8B5E1C" stroke-width="5"/>
<circle cx="146" cy="250" r="20" fill="#FBF7EE" stroke="#8B5E1C" stroke-width="5"/>
<text x="250" y="560" text-anchor="middle" font-family="KaiTi,serif" font-size="42" fill="#3A2E20">海报暂缺</text>
<line x1="150" y1="582" x2="350" y2="582" stroke="#A67C2E" stroke-width="2"/>
<text x="250" y="628" text-anchor="middle" font-family="Georgia,serif" font-size="17" letter-spacing="3" fill="#8B5E1C">MOVIE BOX · ARCHIVE</text>
<text x="250" y="672" text-anchor="middle" font-family="Georgia,serif" font-size="13" fill="#7D6B52">POSTER TEMPORARILY UNAVAILABLE</text>
</svg>"""


def _host_allowed(host: str) -> bool:
    return host in ALLOWED_IMAGE_HOSTS or host.endswith(ALLOWED_IMAGE_SUFFIXES)


# ---- 磁盘缓存：取到一次就永久离线可用 ----
_CACHE_DIR = Path(os.environ.get("IMAGE_CACHE_DIR", "data_lake/cache/posters"))
_CT_BY_EXT = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".webp": "image/webp", ".gif": "image/gif",
}


def _cache_path(url: str) -> Path:
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:24]
    ext = Path(urlsplit(url).path).suffix.lower()
    if ext not in _CT_BY_EXT:
        ext = ".jpg"
    return _CACHE_DIR / f"{digest}{ext}"


def _read_cache(path: Path) -> bytes | None:
    try:
        return path.read_bytes() if path.exists() else None
    except OSError:
        return None


def _write_cache(path: Path, data: bytes) -> None:
    """原子写：先写临时文件再改名，避免半张图被当成缓存命中。"""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, path)
    except OSError as exc:
        print(f"[img] 缓存写盘失败（不影响本次响应）：{exc}")


def rewrite_poster_url(url: str | None) -> str | None:
    """把 TMDB 图片 URL 改写成本地代理路径，其他域名原样返回。

    在序列化层（_to_movie_hit）统一调用，前端拿到的 poster_url
    已经是 /api/v1/img?...，零改动兼容。
    """
    if not url:
        return url
    try:
        host = (urlsplit(url).hostname or "").lower()
    except ValueError:
        return url
    if _host_allowed(host):
        from urllib.parse import quote

        return f"/api/v1/img?url={quote(url, safe='')}"
    return url


@router.get("")
async def image_proxy(url: str = Query(..., description="要代理的图片完整 URL")) -> Response:
    parts = urlsplit(url)
    scheme = (parts.scheme or "").lower()
    host = (parts.hostname or "").lower()
    if scheme not in ("http", "https") or not _host_allowed(host):
        raise HTTPException(status_code=400, detail=f"仅允许代理 {', '.join(sorted(ALLOWED_IMAGE_HOSTS))} 等白名单图床的图片")

    # 0) 磁盘缓存命中：离线也能出真图（网络间歇不可达时的根本解法）
    cache_path = _cache_path(url)
    cached = await asyncio.to_thread(_read_cache, cache_path)
    if cached is not None:
        return Response(
            content=cached,
            media_type=_CT_BY_EXT.get(cache_path.suffix, "image/jpeg"),
            headers={"Cache-Control": "public, max-age=86400", "X-Img-Cache": "hit"},
        )

    # 先走配置的代理出口，失败再试直连（机器有直连能力时不因代理挂了而裂图）
    candidates: list[str | None] = []
    if settings.image_fetch_proxy and settings.image_fetch_proxy.lower() != "direct":
        candidates.append(settings.image_fetch_proxy)
    candidates.append(None)

    last_exc: Exception | None = None
    # 防盗链：命中后缀规则的图床需要带来源页 Referer，否则 418
    headers = {}
    for suffix, ref in REFERER_BY_SUFFIX.items():
        if host.endswith(suffix):
            headers["Referer"] = ref
            break

    for proxy in candidates:
        try:
            async with httpx.AsyncClient(proxy=proxy, timeout=20.0, follow_redirects=True) as client:
                resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            # 成功：落盘持久缓存（原子写），之后离线也出真图
            await asyncio.to_thread(_write_cache, cache_path, resp.content)
            return Response(
                content=resp.content,
                media_type=resp.headers.get("content-type", "image/jpeg"),
                headers={"Cache-Control": "public, max-age=86400", "X-Img-Cache": "store"},
            )
        except (httpx.HTTPError, httpx.StreamError) as exc:  # noqa: PERF203
            last_exc = exc

    print(f"[img] 上游不可用，返回手绘占位海报：{host}{parts.path} ({type(last_exc).__name__})")
    return Response(
        content=_FALLBACK_POSTER.encode("utf-8"),
        media_type="image/svg+xml",
        # 短缓存：别让一次瞬时抖动把占位图钉在浏览器里一整天
        headers={"Cache-Control": "public, max-age=60"},
    )
