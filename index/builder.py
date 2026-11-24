"""
索引生命周期与批量导入 —— 把 processed/*.jsonl 灌进 Elasticsearch。

三个关键设计（都写在函数名旁边了）：

1. **别名 + 版本化物理索引**
   线上永远只认 `movies` 这个别名，实际数据在 `movies_v1_20261014_215000`。
   重建索引时：先写新索引 → 导完 → **一次原子请求**把别名指过去 → 删旧索引。
   好处是重建期间查询不断、导失败了旧索引还在（可回滚）。
   直接 `DELETE movies` 再重建是新手最常见的线上事故之一。

2. **_id 用业务主键，天然幂等**
   `_id = movie_id / review_id`。同一份数据导两遍是**覆盖**不是追加，
   所以"改了融合规则 → 重跑 transform → 重跑导入"这个循环可以随便跑，
   不会把索引撑成两倍。

3. **流式 bulk，内存恒定**
   `streaming_bulk` 边读文件边分批提交，从不把 5 万条影评攒成 list。
   89 MB 的 reviews.jsonl 导完峰值内存 60 MB 上下，与文件大小无关。
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Callable, Iterator

from common.meminfo import format_mem
from common.settings import settings
from index.mappings import (
    INDEX_SPECS,
    MOVIES_MAPPING,
    PREPARERS,
    REVIEWS_MAPPING,
    detect_ik,
    index_settings,
)

# mapping 版本号。改了 mapping 结构就 +1，
# 物理索引名里会带上它，避免新旧结构混在同一个索引里。
#   v1 → 阶段 2b 初版
#   v2 → poster_url / backdrop_url 改为可索引。
#   v3 → reviews 增加豆瓣来源、排序、评论时间与 TMDB 关联字段。
SCHEMA_VERSION = 3

# 索引类型 → 默认文件名（processed/ 目录下）。
# news 是单源自包含数据（RSS），不经过跨源 transform 合并，
# 其终态就是 interim/news.jsonl，故单独指向 interim。
DEFAULT_FILES = {"movies": "movies.jsonl", "reviews": "reviews.jsonl", "news": "news.jsonl"}
NEWS_SOURCE_DIR = "interim"  # news 源文件实际位于 data_lake/interim/news.jsonl

_ES_TYPES = frozenset({
    "text", "keyword", "integer", "long", "short", "byte", "float", "double",
    "half_float", "scaled_float", "date", "boolean", "geo_point", "nested",
    "object", "ip", "completion", "rank_feature",
})


# ============================================================
# 索引名与创建
# ============================================================

def physical_name(alias: str) -> str:
    """生成版本化物理索引名，例如 movies_v1_20261014_215000。"""
    return f"{alias}_v{SCHEMA_VERSION}_{time.strftime('%Y%m%d%H%M%S')}"


def _alias_targets(es, alias: str) -> list[str]:
    """别名当前指向哪些物理索引（不存在返回空列表）。"""
    try:
        resp = es.options(request_timeout=10).indices.get_alias(name=alias)
        return list(resp.keys())
    except Exception:  # noqa: BLE001 —— 别名不存在会抛 NotFoundError
        return []


def create_index(
    es,
    name: str,
    kind: str,
    *,
    use_ik: bool,
    shards: int = 1,
    replicas: int = 0,
) -> None:
    """创建一个物理索引（不碰别名）。"""
    spec = INDEX_SPECS[kind]
    es.options(request_timeout=30).indices.create(
        index=name,
        settings=index_settings(use_ik=use_ik, shards=shards, replicas=replicas),
        mappings=spec["mapping"],
        wait_for_active_shards=1,
    )


def swap_alias(es, new_index: str, alias: str, *, remove: list[str] | None = None) -> None:
    """原子切换别名：新索引挂上、旧索引摘掉，一个请求完成，中间无空窗。"""
    actions: list[dict] = []
    for old in remove or []:
        if old != new_index:
            actions.append({"remove": {"index": old, "alias": alias}})
    actions.append({"add": {"index": new_index, "alias": alias}})
    es.options(request_timeout=30).indices.update_aliases(actions=actions)


def prepare_target(
    es,
    alias: str,
    kind: str,
    *,
    use_ik: bool,
    recreate: bool = False,
    shards: int = 1,
    replicas: int = 0,
) -> tuple[str, list[str]]:
    """决定"这次导入写进哪个索引"。

    返回 (写入的索引名, 切换别名时要摘掉的旧索引列表)。

    两种模式：
        增量（recreate=False）：别名已存在 → 直接复用，覆盖式更新；
                                不存在 → 新建物理索引并挂上别名。
        重建（recreate=True） ：新建一个空索引，导完由调用方 swap_alias 切换。
                                旧索引**仍然在线服务**，导入失败也不影响查询。
    """
    existing = _alias_targets(es, alias)
    if not recreate:
        if existing:
            return existing[0], []
        # 兼容早期版本：别名不存在，但可能有个同名裸索引
        if es.options(request_timeout=10).indices.exists(index=alias):
            return alias, []
        name = physical_name(alias)
        create_index(es, name, kind, use_ik=use_ik, shards=shards, replicas=replicas)
        swap_alias(es, name, alias)
        return name, []

    name = physical_name(alias)
    create_index(es, name, kind, use_ik=use_ik, shards=shards, replicas=replicas)
    return name, existing


# ============================================================
# 批量导入
# ============================================================

def iter_actions(
    path: Path,
    index: str,
    id_field: str,
    *,
    prepare: Callable[[dict], dict] | None = None,
    limit: int | None = None,
) -> Iterator[dict]:
    """逐行读 jsonl，产出 bulk 动作字典（生成器，不攒内存）。

    注意 _id 取自**整形后**的文档：万一 prepare 改写了主键，
    两边必须一致，否则重跑一次就变成两条文档。
    """
    emitted = 0
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            doc = prepare(record) if prepare else record
            doc_id = doc.get(id_field) or record.get(id_field)
            if not doc_id:
                # 没有业务主键就交给 ES 自动生成 —— 但这意味着不幂等，
                # 调用方应该保证 processed 产物一定带主键（自检里有这条断言）
                yield {"_index": index, "_source": doc}
            else:
                yield {"_index": index, "_id": str(doc_id), "_source": doc}
            emitted += 1
            if limit and emitted >= limit:
                return


def bulk_import(
    es,
    path: Path,
    index: str,
    kind: str,
    *,
    limit: int | None = None,
    chunk_size: int = 500,
    report_every: int = 5000,
    quiet: bool = False,
) -> dict:
    """流式 bulk 导入，返回统计字典。

    raise_on_error=False：单条文档失败（比如日期格式脏到 ignore_malformed 也救不了）
    不应该让整个导入中断 —— 记下来，最后汇总报给用户。
    """
    from elasticsearch.helpers import streaming_bulk

    spec = INDEX_SPECS[kind]
    id_field = spec["id_field"]
    prepare = PREPARERS.get(kind)

    stats: dict[str, Any] = {"read": 0, "ok": 0, "failed": 0, "errors": []}
    started = time.time()

    actions = iter_actions(path, index, id_field, prepare=prepare, limit=limit)

    for ok, info in streaming_bulk(
        es,
        actions,
        chunk_size=chunk_size,
        max_chunk_bytes=8 * 1024 * 1024,
        raise_on_error=False,
        raise_on_exception=False,
        request_timeout=120,
        # 网络抖动 / 分片暂时不可用时自动重试，指数退避
        max_retries=3,
        initial_backoff=1,
        max_backoff=8,
    ):
        stats["read"] += 1
        if ok:
            stats["ok"] += 1
        else:
            stats["failed"] += 1
            if len(stats["errors"]) < 5:
                # info 里是 {"index": {...}} 或 {"create": {...}}
                for _, payload in (info or {}).items():
                    stats["errors"].append(str(payload)[:300])
                    break
        if not quiet and stats["read"] % report_every == 0:
            print(f"    … 已提交 {stats['read']:,} 条（成功 {stats['ok']:,}）")

    # 让刚写进去的数据立即可查（默认是 1s 后才刷新）
    es.options(request_timeout=60).indices.refresh(index=index)
    stats["seconds"] = round(time.time() - started, 1)
    return stats


def drop_index(es, name: str) -> bool:
    """删除物理索引；不存在返回 False。"""
    try:
        es.options(request_timeout=30).indices.delete(index=name)
        return True
    except Exception:  # noqa: BLE001
        return False


# ============================================================
# 统计与冒烟检查
# ============================================================

def index_stats(es, alias: str, kind: str) -> dict:
    """取索引文档数 + 两个有代表性的分面（证明 mapping 建对了）。"""
    out: dict[str, Any] = {}
    try:
        out["docs"] = es.options(request_timeout=15).count(index=alias)["count"]
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)[:200]}

    agg_field = "genres_zh" if kind == "movies" else "sentiment" if kind == "reviews" else "outlet"
    try:
        resp = es.options(request_timeout=20).search(
            index=alias, size=0,
            aggs={"top": {"terms": {"field": agg_field, "size": 8}}},
        )
        out["facets"] = [
            (b["key"], b["doc_count"])
            for b in resp["aggregations"]["top"]["buckets"]
        ]
    except Exception as exc:  # noqa: BLE001
        out["facets"] = []
        out["facet_error"] = str(exc)[:200]
    return out


def _is_chinese(token: str) -> bool:
    """判断一个 token 是不是纯中文（用来识别"切出了真正的中文词"）。"""
    return bool(token) and all("\u4e00" <= ch <= "\u9fff" for ch in token)


def smoke_check(es) -> list[tuple[str, bool, str]]:
    """检索冒烟测试：分词器、中文检索、分面聚合、影评检索四条链路各验一次。

    ★ 为什么要"数据驱动"地选检索词？
        硬编码一个关键词（比如"科幻"）在这套数据里可能一条都搜不到，
        于是自检报失败，但其实是数据问题不是代码问题 —— 误报比漏报更烦人。
        所以这里先从索引里**真实取一条中文片名**，交给同一套分析器切词，
        再拿切出来的词去搜。既验证了分词器，也验证了索引与查询口径一致。
    """
    results: list[tuple[str, bool, str]] = []
    movies = settings.es_index_movies
    reviews = settings.es_index_reviews

    # 1. 分析器：中文有没有被切成"词"（而不是一字一token）
    try:
        resp = es.options(request_timeout=20).indices.analyze(
            index=movies,
            analyzer="yj_zh_index",
            text="流浪地球是一部中国科幻电影",
        )
        tokens = [t["token"] for t in resp["tokens"]]
        multi = [t for t in tokens if len(t) >= 2 and _is_chinese(t)]
        results.append((
            "中文分词器", bool(multi),
            f"切出 {len(multi)} 个多字词：" + "、".join(multi[:5]),
        ))
    except Exception as exc:  # noqa: BLE001
        results.append(("中文分词器", False, str(exc)[:160]))

    # 2. 中文检索：取真实片名 → 切词 → 回搜
    try:
        sample = es.options(request_timeout=20).search(
            index=movies, size=1,
            query={"exists": {"field": "title_zh"}},
            _source=["title_zh"],
        )["hits"]["hits"]
        if not sample:
            results.append(("中文检索（端到端）", False, "索引里没有中文片名，无法验证"))
        else:
            title = sample[0]["_source"]["title_zh"]
            cut = es.options(request_timeout=20).indices.analyze(
                index=movies, analyzer="yj_zh_search", text=title,
            )["tokens"]
            word = max((t["token"] for t in cut), key=len)
            hits = es.options(request_timeout=20).search(
                index=movies, size=3,
                query={"match": {"title_zh": word}},
            )
            total = hits["hits"]["total"]["value"]
            top = hits["hits"]["hits"][0]["_source"].get("title") if hits["hits"]["hits"] else ""
            results.append((
                "中文检索（端到端）", total > 0,
                f"《{title}》→ 词「{word}」→ {total} 命中，首位《{top}》",
            ))
    except Exception as exc:  # noqa: BLE001
        results.append(("中文检索（端到端）", False, str(exc)[:160]))

    # 3. 分面聚合：验证 keyword 子字段建对了（text 字段是做不了 terms 聚合的）
    try:
        resp = es.options(request_timeout=20).search(
            index=movies, size=0,
            aggs={"g": {"terms": {"field": "genres_zh", "size": 5}}},
        )
        buckets = resp["aggregations"]["g"]["buckets"]
        desc = "、".join(f"{b['key']}({b['doc_count']})" for b in buckets[:5])
        results.append(("类型分面聚合", bool(buckets), desc or "（无分面数据）"))
    except Exception as exc:  # noqa: BLE001
        results.append(("类型分面聚合", False, str(exc)[:160]))

    # 4. 嵌套地理查询：验证 nested + geo_point 的 mapping 能被查询解析
    try:
        resp = es.options(request_timeout=20).search(
            index=movies, size=0,
            query={"nested": {
                "path": "locations_with_coords",
                "query": {"geo_distance": {
                    "distance": "500km",
                    "locations_with_coords.location": {"lat": 31.23, "lon": 121.47},
                }},
            }},
        )
        total = resp["hits"]["total"]["value"]
        results.append((
            "嵌套地理查询（足迹地图）", True,
            f"查询可解析，命中 {total} 部（当前采集数据尚无坐标时为 0）",
        ))
    except Exception as exc:  # noqa: BLE001
        results.append(("嵌套地理查询（足迹地图）", False, str(exc)[:160]))

    # 5. 影评英文检索 + 情感分面
    try:
        resp = es.options(request_timeout=20).search(
            index=reviews, size=1,
            query={"match": {"text": "wonderful"}},
            aggs={"s": {"terms": {"field": "sentiment", "size": 3}}},
        )
        hits = resp["hits"]["total"]["value"]
        buckets = resp["aggregations"]["s"]["buckets"]
        desc = "、".join(f"{b['key']}({b['doc_count']})" for b in buckets)
        results.append(("影评检索 + 情感分面", hits > 0, f"{hits} 命中；情感分布 {desc}"))
    except Exception as exc:  # noqa: BLE001
        results.append(("影评检索 + 情感分面", False, str(exc)[:160]))

    return results


def report_mem(label: str) -> str:
    return f"{label}｜{format_mem()}"
