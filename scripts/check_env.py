"""
环境自检脚本（不依赖后端服务，纯命令行）。

用途：在跑任何采集/建索引之前，一次性确认
    Python 版本 / .env / 依赖 / ES 连通性 / 数据湖目录 / TMDB Key
都就位。出问题会给出具体修复建议。

运行（在 yingjian-zhisou/ 目录下）：
    python scripts/check_env.py
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

PASS, FAIL, WARN = "[ OK ]", "[FAIL]", "[WARN]"
_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool, detail: str = "", hint: str = "") -> bool:
    _results.append((name, ok))
    line = f"{PASS if ok else FAIL} {name}"
    if detail:
        line += f"  ->  {detail}"
    print(line)
    if not ok and hint:
        print(f"       修复建议：{hint}")
    return ok


def main() -> int:
    print("=" * 68)
    print("  电影盒子 · 环境自检")
    print("=" * 68)

    # ---------- 1. Python 版本 ----------
    ver = sys.version_info
    check(
        "Python 版本",
        ver >= (3, 10),
        f"{ver.major}.{ver.minor}.{ver.micro}",
        "本项目要求 Python >= 3.10",
    )

    # ---------- 2. .env ----------
    env_file = PROJECT_ROOT / ".env"
    check(
        ".env 配置文件",
        env_file.exists(),
        str(env_file) if env_file.exists() else "未找到",
        f"复制 .env.example 为 .env：copy .env.example .env",
    )

    # ---------- 3. 依赖 ----------
    try:
        import elasticsearch  # noqa: F401
        import fastapi  # noqa: F401
        import pandas  # noqa: F401
        import pydantic_settings  # noqa: F401

        check("核心依赖", True, "fastapi / pydantic-settings / elasticsearch / pandas 均已安装")
    except ImportError as exc:
        check(
            "核心依赖",
            False,
            f"缺少 {exc.name}",
            "python -m venv .venv && .venv\\Scripts\\pip install -r requirements.txt",
        )

    # ---------- 4. 配置读取 ----------
    try:
        from common.settings import settings

        check("配置加载", True, f"ES={settings.es_host_list}  data_lake={settings.data_lake_path}")

        check(
            "TMDB API Key",
            bool(settings.tmdb_api_key),
            "已配置" if settings.tmdb_api_key else "为空",
            "在 .env 里填 TMDB_API_KEY（https://www.themoviedb.org/settings/api）",
        )
    except Exception as exc:  # noqa: BLE001
        check("配置加载", False, f"{type(exc).__name__}: {exc}")
        _summary()
        return 1

    # ---------- 5. 数据湖目录 ----------
    lake_ok = True
    for sub in ("raw", "interim", "processed"):
        p = settings.lake(sub)
        if not p.exists():
            lake_ok = False
    check("数据湖目录", lake_ok, str(settings.data_lake_path))

    # ---------- 6. Elasticsearch 连通性 ----------
    try:
        from common.es_client import close_sync_es, get_sync_es

        es = get_sync_es().options(request_timeout=5)
        info = es.info()
        health = es.cluster.health()
        check(
            "Elasticsearch 连接",
            True,
            f"v{info['version']['number']}  集群={info['cluster_name']}  "
            f"状态={health['status']}  节点数={health['number_of_nodes']}",
        )
        count = es.cat.indices(format="json", h="index,docs.count")
        biz = [i for i in count if not i["index"].startswith(".")]
        check("业务索引", True, f"已存在 {len(biz)} 个：{[i['index'] for i in biz] or '（暂无，阶段 2 创建）'}")
        close_sync_es()
    except Exception as exc:  # noqa: BLE001
        check(
            "Elasticsearch 连接",
            False,
            f"{type(exc).__name__}: {str(exc)[:160]}",
            "在 yingjian-zhisou/ 下执行 docker-compose up -d，然后 docker-compose logs -f elasticsearch",
        )

    return _summary()


def _summary() -> int:
    total = len(_results)
    passed = sum(1 for _, ok in _results if ok)
    print("-" * 68)
    print(f"  结果：{passed}/{total} 项通过")
    if passed == total:
        print("  ✅ 环境已就绪，可以进入阶段 1（数据采集）")
    else:
        print("  ⚠️  请先按上面的修复建议处理失败项")
    print("=" * 68)
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
