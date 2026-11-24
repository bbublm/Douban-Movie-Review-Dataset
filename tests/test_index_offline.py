"""
阶段 2b 离线自检 —— 不联网、不碰 ES，验证索引层的每个判断。

为什么索引层也要离线自检？
    最容易埋雷的地方不是"导不进去"，而是"导进去了但搜不到"：

    · 融合层加了个字段，mapping 没同步 → dynamic:strict 会直接报错，
      但如果哪天有人把它改成默认动态映射，那个字段就**静默地建不上索引**，
      线上表现为"搜这个词永远 0 结果"，查一天都查不出来。
    · 分面字段被建成了 text → terms 聚合直接抛异常（text 不能聚合）。
    · 主键字段缺失 → _id 交给 ES 自动生成 → 重跑一次导进两份，索引翻倍。

    所以这里的断言专门盯这三件事：**覆盖度、字段类型、幂等前提**。

运行：
    python tests/test_index_offline.py
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from common.settings import settings  # noqa: E402
from index.builder import SCHEMA_VERSION, iter_actions, physical_name  # noqa: E402
from index.mappings import (  # noqa: E402
    EXISTS_QUERY_FIELDS,
    INDEX_SPECS,
    MOVIES_MAPPING,
    PREPARERS,
    REVIEWS_MAPPING,
    ZH_INDEX,
    ZH_SEARCH,
    analysis_block,
    detect_ik,
    index_settings,
    prepare_movie_doc,
    prepare_review_doc,
)

_results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    _results.append((name, ok, detail))
    print(f"{'[ OK ]' if ok else '[FAIL]'} {name}" + (f"  ->  {detail}" if detail else ""))
    return ok


# ============================================================
# 融合层产物的字段全集（权威清单）
# ============================================================
# 这份清单是「融合层承诺会产出哪些字段」的契约。
# 融合层加了新字段却没同步到这里和 mapping，自检会立刻报错 ——
# 这正是 dynamic:strict 想保护、但保护不到的那一类漂移（改了 mapping 才算数）。
MOVIES_EXPECTED_FIELDS = {
    "backdrop_url", "cast", "collected_at", "director", "filming_locations",
    "genre_ids", "genres_en", "genres_zh", "id_resolved", "imdb_id",
    "imdb_rating", "imdb_votes", "is_multi_source", "keywords",
    "locations_with_coords", "match_keys", "merged_from", "movie_id",
    "original_language", "original_title", "overview", "popularity",
    "poster_url", "production_countries", "production_country_codes",
    "release_date", "release_year", "runtime", "source", "source_count",
    "sources", "spoken_languages", "status", "tagline", "title", "title_en",
    "title_type", "title_zh", "tmdb_id", "upstream", "vote_average",
    "vote_count", "wikidata_qid", "wikidata_url", "wikipedia_extract",
    "wikipedia_title", "wikipedia_url",
}

REVIEWS_EXPECTED_FIELDS = {
    "collected_at", "dataset", "imdb_id", "lang", "matched_by", "movie_id",
    "movie_title", "movie_year", "rating", "review_id", "row_index",
    "sentiment", "sentiment_score", "source", "source_file", "text",
    "text_len", "text_raw_len", "transformed_at", "word_count",
    "movie_tmdb_id", "douban_id", "douban_sort", "douban_comment_time", "review_time",
}

# ES 允许的字段类型白名单 —— 拼错类型名会在建索引时才炸，这里提前拦
_ES_TYPES = {
    "text", "keyword", "integer", "long", "short", "byte", "float", "double",
    "half_float", "scaled_float", "date", "boolean", "geo_point", "nested",
    "object", "ip", "completion", "rank_feature",
}

# 必须能分面聚合的字段（建成 text 就聚合不了）
_FACET_FIELDS = {
    "movies": ["genres_zh", "genres_en", "production_countries", "sources",
               "status", "title_type", "original_language", "source"],
    "reviews": ["sentiment", "lang", "source", "matched_by", "dataset"],
}


class _FakeIndices:
    def __init__(self, ok: bool) -> None:
        self.ok = ok

    def analyze(self, **kwargs):
        if not self.ok:
            raise RuntimeError("failed to find global tokenizer under [ik_max_word]")
        return {"tokens": [{"token": "影鉴"}]}


class _FakeES:
    """最小假客户端：只想验证 detect_ik 的成败分支，不想真的起 ES。"""

    def __init__(self, ok: bool = True) -> None:
        self._indices = _FakeIndices(ok)

    def options(self, **kwargs):
        return self

    @property
    def indices(self):
        return self._indices


# ============================================================
def main() -> int:
    print("=" * 68)
    print("  阶段 2b · ES 索引层离线自检")
    print("=" * 68)

    # ================= 1. mapping 覆盖度 =================
    print("\n-- 1. mapping 覆盖度（字段漂移守卫）--")

    mv_props = MOVIES_MAPPING["properties"]
    rv_props = REVIEWS_MAPPING["properties"]

    missing_mv = sorted(MOVIES_EXPECTED_FIELDS - set(mv_props))
    check("movies：融合层每个字段都有 mapping", not missing_mv, "、".join(missing_mv))

    missing_rv = sorted(REVIEWS_EXPECTED_FIELDS - set(rv_props))
    check("reviews：融合层每个字段都有 mapping", not missing_rv, "、".join(missing_rv))

    check("movies：dynamic=strict（未知字段要炸，不能静默吞掉）",
          MOVIES_MAPPING.get("dynamic") == "strict", str(MOVIES_MAPPING.get("dynamic")))
    check("reviews：dynamic=strict", REVIEWS_MAPPING.get("dynamic") == "strict",
          str(REVIEWS_MAPPING.get("dynamic")))

    # 拿真实产物再核一遍：如果 processed 里冒出清单外的新字段，说明融合层变了
    processed = Path(settings.lake("processed"))
    movies_path = processed / "movies.jsonl"
    if movies_path.exists():
        real = set()
        for line in movies_path.read_text("utf-8").splitlines():
            if line.strip():
                real |= set(json.loads(line).keys())
        drift = sorted(real - MOVIES_EXPECTED_FIELDS)
        check("真实产物没有超出清单的新字段（有则说明融合层改了）",
              not drift, "、".join(drift))
    else:
        check("真实产物没有超出清单的新字段（有则说明融合层改了）", True,
              f"（跳过：{movies_path.name} 不存在）")

    # ================= 2. 字段类型 =================
    print("\n-- 2. 字段类型（拼错类型名要在这里炸，不是建索引时）--")

    def bad_types(props: dict) -> list[str]:
        bad = []
        for name, spec in props.items():
            if not isinstance(spec, dict):
                bad.append(f"{name}: 不是 dict")
                continue
            if spec.get("type") not in _ES_TYPES:
                bad.append(f"{name}: {spec.get('type')}")
            for sub in (spec.get("fields") or {}).values():
                if sub.get("type") not in _ES_TYPES:
                    bad.append(f"{name}.子字段: {sub.get('type')}")
            for sub in (spec.get("properties") or {}).values():
                if sub.get("type") not in _ES_TYPES:
                    bad.append(f"{name}.嵌套: {sub.get('type')}")
        return bad

    check("movies：所有字段类型合法", not bad_types(mv_props), "、".join(bad_types(mv_props)[:4]))
    check("reviews：所有字段类型合法", not bad_types(rv_props), "、".join(bad_types(rv_props)[:4]))

    for kind, fields in _FACET_FIELDS.items():
        props = mv_props if kind == "movies" else rv_props
        not_kw = [f for f in fields if f in props and props[f].get("type") != "keyword"]
        check(f"{kind}：分面字段都是 keyword", not not_kw, "、".join(not_kw))

    # 中文文本字段必须挂自定义分析器，否则中文检索退化成一字一 token
    cn_text_fields = ["title", "title_zh", "overview", "tagline", "director", "cast"]
    wrong = [f for f in cn_text_fields
             if mv_props[f].get("analyzer") != ZH_INDEX
             or mv_props[f].get("search_analyzer") != ZH_SEARCH]
    check("movies：中文文本字段使用 yj_zh_index / yj_zh_search", not wrong, "、".join(wrong))

    check("reviews：正文用内置 english 分析器（英文语料，自带词干还原）",
          rv_props["text"].get("analyzer") == "english", str(rv_props["text"].get("analyzer")))

    # 需要排序/聚合/高亮的文本字段必须有 keyword 子字段
    for f in ["title", "title_zh", "director"]:
        check(f"movies：{f} 带 .kw 子字段（用于排序/聚合）",
              "kw" in (mv_props[f].get("fields") or {}), "")

    unusable = []
    for f in sorted(EXISTS_QUERY_FIELDS):
        spec = mv_props.get(f) or rv_props.get(f)
        if spec is None:
            unusable.append(f"{f}: 不在 mapping")
        elif spec.get("index") is False and spec.get("doc_values") is False:
            unusable.append(f"{f}: index 与 doc_values 都被关掉了")
    check("★ exists 查询用到的字段都可索引（否则筛选恒为空，且不报错）",
          not unusable, "、".join(unusable))

    check("movies：geo_point 存在于拍摄地嵌套字段",
          mv_props["filming_locations"]["properties"]["location"]["type"] == "geo_point")
    check("movies：日期字段开了 ignore_malformed（脏日期不能带走整条文档）",
          mv_props["release_date"].get("ignore_malformed") is True)

    # ================= 3. settings 与分析器 =================
    print("\n-- 3. settings 与分析器（核心设计：mapping 恒定，settings 变）--")

    ik_block = analysis_block(use_ik=True)["analysis"]["analyzer"]
    check("有 IK 时：索引期 ik_max_word",
          ik_block[ZH_INDEX]["tokenizer"] == "ik_max_word", str(ik_block[ZH_INDEX]))
    check("有 IK 时：查询期 ik_smart（细粒度存、粗粒度查）",
          ik_block[ZH_SEARCH]["tokenizer"] == "ik_smart", str(ik_block[ZH_SEARCH]))

    cjk_block = analysis_block(use_ik=False)["analysis"]["analyzer"]
    check("无 IK 时：降级到内置 cjk（零依赖也能建索引）",
          cjk_block[ZH_INDEX]["type"] == "cjk" and cjk_block[ZH_SEARCH]["type"] == "cjk",
          str(cjk_block[ZH_INDEX]))

    # 这条是本文件最重要的断言：换分词器不该动到 mapping。
    # 只看 analyzer / search_analyzer / tokenizer 的**取值**，
    # 不能傻乎乎地全文搜 "ik" 两个字母 —— wikidata_qid 里就有 ik，会误报。
    def analyzer_values(props: dict) -> set[str]:
        found: set[str] = set()
        for spec in props.values():
            for key in ("analyzer", "search_analyzer", "tokenizer"):
                if key in spec:
                    found.add(spec[key])
            for sub in (spec.get("properties") or {}).values():
                found |= analyzer_values({"x": sub})
        return found

    used = analyzer_values(mv_props) | analyzer_values(rv_props)
    allowed = {ZH_INDEX, ZH_SEARCH, "english"}
    check("★ mapping 只引用分析器名字，不含任何具体分词器（换 IK/cjk 不用改 mapping）",
          used <= allowed, f"实际引用 {sorted(used)}")

    st = index_settings(use_ik=True)
    check("settings：单分片零副本（开发期配置）",
          st["number_of_shards"] == 1 and st["number_of_replicas"] == 0)
    check("settings：max_result_window 放大到 50000（阶段 5 大屏要全量聚合）",
          st["max_result_window"] == 50000)
    check("settings：analysis 段随 use_ik 切换",
          "analysis" in index_settings(use_ik=False))

    check("detect_ik：探测成功返回 True", detect_ik(_FakeES(ok=True)) is True)
    check("detect_ik：探测失败返回 False（降级，不抛异常）",
          detect_ik(_FakeES(ok=False)) is False)

    # ================= 4. 文档整形 =================
    print("\n-- 4. 文档整形（geo_point 只在索引层出现）--")

    rec = {"movie_id": "tt1", "title": "无间道",
           "filming_locations": [{"name": "香港", "kind": "filming", "qid": "Q8646",
                                  "lat": 22.3193, "lon": 114.1694},
                                 {"name": "无坐标地", "kind": "narrative", "qid": "Q1",
                                  "lat": None, "lon": None}],
           "locations_with_coords": []}
    doc = prepare_movie_doc(rec)
    loc = doc["filming_locations"][0].get("location")
    check("有坐标的地点补上 geo_point", loc == {"lat": 22.3193, "lon": 114.1694}, str(loc))
    check("geo_point 用 {lat,lon} 对象写法（不用易错的 [lon,lat] 数组）",
          isinstance(loc, dict) and "lat" in loc)
    check("无坐标的地点不补 location", "location" not in doc["filming_locations"][1])
    check("整形不改原记录（融合产物保持数据源中立）",
          "location" not in rec["filming_locations"][0])

    doc2 = prepare_movie_doc({"movie_id": "x", "filming_locations": ["不是dict", None]})
    check("脏数据（非 dict 地点）被安全丢弃", doc2["filming_locations"] == [])

    src = {"review_id": "r1", "text": "hi"}
    check("影评整形返回副本（不改动入参）",
          prepare_review_doc(src) == src and prepare_review_doc(src) is not src)
    check("两种索引都有整形函数", set(PREPARERS) == {"movies", "reviews"})

    # ================= 5. 导入动作流 =================
    print("\n-- 5. bulk 动作流（流式、幂等）--")

    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "movies.jsonl"
        p.write_text(
            json.dumps({"movie_id": "tt1", "title": "A"}) + "\n"
            + "\n"                                        # 空行要被跳过
            + json.dumps({"movie_id": "tt2", "title": "B"}) + "\n"
            + json.dumps({"movie_id": "tt1", "title": "A2"}) + "\n",   # 重复主键
            encoding="utf-8",
        )
        acts = list(iter_actions(p, "movies_x", "movie_id"))
        check("空行被跳过，产出 3 个动作", len(acts) == 3, f"{len(acts)} 个")
        check("_index 正确", all(a["_index"] == "movies_x" for a in acts))
        check("_id 取自业务主键（幂等的前提）",
              [a["_id"] for a in acts] == ["tt1", "tt2", "tt1"],
              str([a["_id"] for a in acts]))
        check("重复主键产生相同 _id → 重跑是覆盖不是追加",
              acts[0]["_id"] == acts[2]["_id"])

        limited = list(iter_actions(p, "movies_x", "movie_id", limit=2))
        check("--limit 生效（调试时不用导全量）", len(limited) == 2)

        # 缺主键：不能让整批挂掉，交给 ES 自动生成
        p2 = Path(td) / "r.jsonl"
        p2.write_text(json.dumps({"text": "no id"}) + "\n", encoding="utf-8")
        noid = list(iter_actions(p2, "reviews_x", "review_id"))
        check("缺少主键时不带 _id（交 ES 生成，而不是崩溃）", "_id" not in noid[0])

        # 整形函数在流里生效
        p3 = Path(td) / "geo.jsonl"
        p3.write_text(json.dumps({"movie_id": "tt9", "filming_locations": [
            {"name": "香港", "lat": 22.3, "lon": 114.2}]}) + "\n", encoding="utf-8")
        prepared = list(iter_actions(p3, "movies_x", "movie_id", prepare=prepare_movie_doc))
        check("流式中整形生效（geo_point 已注入）",
              "location" in prepared[0]["_source"]["filming_locations"][0])

    # ================= 6. 幂等前提（真实数据）=================
    print("\n-- 6. 幂等前提（主键必须齐全且唯一）--")

    for kind, id_field, path in (("movies", "movie_id", movies_path),
                                 ("reviews", "review_id", processed / "reviews.jsonl")):
        if not path.exists():
            check(f"{kind}：每条都有 {id_field}", True, f"（跳过：{path.name} 不存在）")
            continue
        ids: list[str] = []
        empty = 0
        for line in path.read_text("utf-8").splitlines():
            if not line.strip():
                continue
            rec = json.loads(line)
            v = rec.get(id_field)
            if not v:
                empty += 1
            else:
                ids.append(str(v))
        check(f"{kind}：每条都有非空 {id_field}", empty == 0, f"{empty} 条缺失")
        check(f"{kind}：{id_field} 唯一（否则导入会互相覆盖）",
              len(ids) == len(set(ids)),
              f"{len(ids)} 条 / {len(set(ids))} 个不同值")

    # ================= 7. 索引命名 =================
    print("\n-- 7. 索引命名与规格 --")

    name = physical_name("movies")
    check("物理索引名带版本号（新旧结构不混在一起）",
          name.startswith(f"movies_v{SCHEMA_VERSION}_"), name)
    check("物理索引名带时间戳（同秒内重跑也不会撞名）", len(name) > len("movies_v1_"), name)
    check("两种索引的规格齐全（mapping + 主键字段）",
          all("mapping" in s and "id_field" in s for s in INDEX_SPECS.values()))
    check("movies 主键是 movie_id / reviews 主键是 review_id",
          INDEX_SPECS["movies"]["id_field"] == "movie_id"
          and INDEX_SPECS["reviews"]["id_field"] == "review_id")

    # ================= 汇总 =================
    passed = sum(1 for _, ok, _ in _results if ok)
    total = len(_results)
    print()
    print("=" * 68)
    print(f"  结果：{passed}/{total} 通过")
    if passed != total:
        print("  失败项：")
        for name, ok, detail in _results:
            if not ok:
                print(f"    - {name}  {detail}")
    print("=" * 68)
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
