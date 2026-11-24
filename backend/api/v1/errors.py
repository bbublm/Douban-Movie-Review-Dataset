"""
API 层共用的小工具：把"ES 不可用"这类领域异常翻译成 HTTP 响应。

为什么值得单开一个文件：
    检索、洞察、推荐、评分四个模块都会碰 ES，都会有"连不上"的那一刻。
    各自复制一份 503 构造逻辑，迟早会出现"提示文案不一致"——
    用户照着 insights 的 hint 去敲命令，发现 recommend 里写的是另一条。
"""
from __future__ import annotations

from fastapi import HTTPException


def es_unavailable(exc: Exception) -> HTTPException:
    """ES 连不上 / 查询失败 → 503，并给出可操作的排查提示。

    detail 用结构化 dict 而不是纯字符串：前端能分别取 message（展示）
    和 hint（展示成"点我排查"按钮），error 留给日志。
    """
    return HTTPException(
        status_code=503,
        detail={
            "message": "检索服务暂时不可用（Elasticsearch 未连接或查询失败）",
            "hint": "先执行 docker-compose up -d，再跑 python -m index.run_index build",
            "error": str(exc)[:300],
        },
    )
