"""
阶段 1c 离线自检 —— 不联网、不等 SPARQL 往返，也能验证维基采集链路。

思路：
    SPARQL 与 MediaWiki 的响应都存成了 tests/fixtures/*.json（结构来自真实响应），
    然后直接调**纯函数**跑完「解析 → 聚合 → 别名映射 → 归一化 → 落盘」。

    这样做的价值在于：SPARQL 查询一次往返要好几秒、还容易被限流，
    而链路上真正会出错的地方（经纬度顺序、多值去重、标签回退成英文、
    重定向别名没解析）全都能在这里秒级验证。

运行：
    python tests/test_wiki_offline.py
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
from ingest.schema import CORE_FIELDS, validate_record  # noqa: E402
from ingest.wiki import build_wiki_records, iter_jsonl, normalize_wiki, write_jsonl  # noqa: E402
from ingest.sources import wikidata as wd  # noqa: E402
from ingest.sources import wikipedia as wp  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"

_results: list[tuple[str, bool, str]] = []


def load_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def check(name: str, ok: bool, detail: str = "") -> bool:
    _results.append((name, ok, detail))
    print(f"{'[ OK ]' if ok else '[FAIL]'} {name}" + (f"  ->  {detail}" if detail else ""))
    return ok


def main() -> int:
    print("=" * 68)
    print("  阶段 1c 离线自检 · Wikidata SPARQL + Wikipedia API")
    print("=" * 68)

    core_payload = load_fixture("wikidata_core.json")
    geo_payload = load_fixture("wikidata_geo.json")
    wiki_payload = load_fixture("wikipedia_extract.json")

    # ================= 1. WKT 坐标解析（经纬度顺序）=================
    print("\n-- WKT 坐标解析 --")
    point = wd.parse_wkt_point("Point(-118.24368 34.05223)")
    check("WKT 解析：经度在前、纬度在后（顺序没搞反）",
          point == (34.05223, -118.24368), f"(lat, lon) = {point}")
    check("WKT 解析：越界坐标被拒绝",
          wd.parse_wkt_point("Point(200 100)") is None)
    check("WKT 解析：非坐标文本返回 None",
          wd.parse_wkt_point("不是坐标") is None)
    check("WKT 解析：None 安全", wd.parse_wkt_point(None) is None)

    # ================= 2. 中文判定与条目标题反解 =================
    print("\n-- 中文判定 / 标题反解 --")
    check("has_han：中文标签判定为真", wd.has_han("搏击俱乐部") is True)
    check("has_han：英文标签判定为假（标签服务会静默回退成英文）",
          wd.has_han("Fight Club") is False)
    check("has_han：空值安全", wd.has_han(None) is False and wd.has_han("") is False)
    check("从 zhwiki URL 反解条目标题",
          wd.title_from_article("https://zh.wikipedia.org/wiki/%E6%90%8F%E5%87%BB%E4%BF%B1%E4%B9%90%E9%83%A8")
          == "搏击俱乐部")

    # ================= 3. SPARQL 语句拼装 =================
    print("\n-- SPARQL 语句拼装 --")
    values = wd.build_values([("P345", "tt0137523"), ("P4947", "550")])
    check("VALUES 成对拼装（两种主键可同一条查询）",
          "(<http://www.wikidata.org/prop/direct/P345> \"tt0137523\")" in values
          and "(<http://www.wikidata.org/prop/direct/P4947> \"550\")" in values)
    rendered = wd.CORE_QUERY.format(values=values, lang=wd.LABEL_LANGS, limit=3000)
    check("CORE_QUERY 渲染出合法的 SPARQL 骨架",
          all(k in rendered for k in ("VALUES (?prop ?key)", "SERVICE wikibase:label",
                                      "wdt:P57", "wdt:P577", "LIMIT 3000")))
    geo_rendered = wd.GEO_QUERY.format(values=values, lang=wd.LABEL_LANGS, limit=3000)
    check("GEO_QUERY 保留了拍摄地与故事发生地的区分",
          'P915 ?loc . BIND("filming" AS ?kind)' in geo_rendered
          and 'P840 ?loc . BIND("narrative" AS ?kind)' in geo_rendered)

    # ================= 4. 响应解析与聚合 =================
    print("\n-- Wikidata 响应解析与聚合 --")
    core_rows = wd.parse_rows(core_payload)
    check("SPARQL 响应摊平成行", len(core_rows) == 5, f"{len(core_rows)} 行")
    check("每一行都带 prop / key（能分辨主键类型）",
          all(r["prop"].endswith(("P345", "P4947")) for r in core_rows))

    core = wd.aggregate_core(core_rows)
    check("按主键聚合：3 部电影各自一条", len(core) == 3, f"键={sorted(core)}")

    fc = core["tt0137523"]
    check("聚合：主键与 QID 正确",
          fc["imdb_id"] == "tt0137523" and fc["qid"] == "Q190050",
          f"qid={fc['qid']}")
    check("聚合：中文标签（zh-hans）取到", fc["label"] == "搏击俱乐部")
    check("聚合：重复导演被去重", fc["directors"] == ["大卫·芬奇"], str(fc["directors"]))
    check("聚合：多类型按出现顺序保留", fc["genres"] == ["剧情", "惊悚"], str(fc["genres"]))
    check("聚合：多出品国保留", fc["countries"] == ["美国", "德国"], str(fc["countries"]))
    check("聚合：公映日期取最早（不是最后写入的那条）",
          fc["pubdate"] == "1999-09-10", fc["pubdate"])
    check("聚合：片长取最大", fc["duration"] == 139, str(fc["duration"]))
    check("聚合：zhwiki 条目 URL 保留", bool(fc["zh_article"]))

    demo = core["tt9000001"]
    check("聚合：无中文标签时保留英文原文（不伪造中文）",
          demo["label"] == "Synthetic Demo Movie" and not wd.has_han(demo["label"]))
    check("聚合：两位导演按顿号拼接的顺序稳定",
          demo["directors"] == ["示例导演·甲", "示例导演·乙"], str(demo["directors"]))

    tmdb_only = core["900550"]
    check("聚合：只有 TMDB 主键的记录也能落到 tmdb_id 上",
          tmdb_only["tmdb_id"] == "900550" and tmdb_only["imdb_id"] is None)

    # ================= 5. 拍摄地聚合 =================
    print("\n-- 拍摄地聚合 --")
    geo = wd.aggregate_geo(wd.parse_rows(geo_payload))
    places = geo["tt0137523"]
    check("拍摄地：重复行被去重（真实响应确实会返回重复）",
          len(places) == 2, f"{[p['name'] for p in places]}")
    check("拍摄地：区分 filming / narrative",
          {p["kind"] for p in places} == {"filming", "narrative"})
    la = next(p for p in places if p["name"] == "洛杉矶")
    check("拍摄地：坐标已按 (lat, lon) 落位（不是南极洲）",
          (la["lat"], la["lon"]) == (34.05223, -118.24368), f"{la}")
    nocoord = geo["tt9000001"][0]
    check("拍摄地：无坐标的地点保留名字、不打经纬度",
          nocoord["name"] == "示例取景地（无坐标）" and "lat" not in nocoord)

    # ================= 6. Wikipedia 摘要与别名映射 =================
    print("\n-- Wikipedia 摘要与别名映射 --")
    summaries = wp.parse_wikipedia_payload(
        wiki_payload, requested=["搏击俱乐部 ", "肖申克", "不存在的条目XYZ"]
    )
    check("摘要：正常条目取到正文",
          "搏击俱乐部" in summaries and len(summaries["搏击俱乐部"]["extract"]) > 40)
    check("摘要：缺失条目被跳过（不当成空摘要）",
          "不存在的条目XYZ" not in summaries)
    check("摘要：redirects 别名解析（肖申克 → 肖申克的救赎）",
          "肖申克" in summaries and summaries["肖申克"]["title"] == "肖申克的救赎",
          summaries.get("肖申克", {}).get("title", ""))
    check("摘要：normalized 别名解析",
          "搏击俱乐部 " in summaries)
    check("摘要：返回条目 URL", summaries["搏击俱乐部"]["url"].startswith("https://zh.wikipedia.org/"))
    check("摘要：截断参数生效",
          len(wp._clean_extract("一二三四五六七八九十", limit=4)) == 4)

    # ================= 7. 归一化 =================
    print("\n-- 归一化为统一记录 --")
    rec = normalize_wiki(
        core["tt0137523"],
        places=geo["tt0137523"],
        summary=summaries["搏击俱乐部"],
    )
    check("归一化：缺失核心字段为 0（严格模式不报错）",
          validate_record(rec, strict=True) == [],
          f"覆盖 {len(CORE_FIELDS)} 个核心字段")
    check("归一化：中文片名取自 zh 标签", rec["title_zh"] == "搏击俱乐部")
    check("归一化：展示名优先中文", rec["title"] == "搏击俱乐部")
    check("归一化：日期拆分到 日 / 年",
          rec["release_date"] == "1999-09-10" and rec["release_year"] == 1999)
    check("归一化：片长 / 导演 / 出品国落位",
          rec["runtime"] == 139 and rec["director"] == "大卫·芬奇"
          and rec["production_countries"] == ["美国", "德国"])
    check("归一化：剧情摘要写入 overview",
          rec["overview"].startswith("《搏击俱乐部》"), rec["overview"][:24] + "…")
    check("归一化：source 反映多源合成", rec["source"] == "wikidata+wikipedia")
    check("归一化：QID 与 Wikidata 链接",
          rec["wikidata_qid"] == "Q190050"
          and rec["wikidata_url"].endswith("/Q190050"))
    check("归一化：地图字段只保留有坐标的地点",
          len(rec["filming_locations"]) == 2 and len(rec["locations_with_coords"]) == 2)

    rec_en = normalize_wiki(core["tt9000001"], places=geo["tt9000001"])
    check("归一化：无中文名时 title_zh 留空（交给阶段 2 补），不硬填英文",
          rec_en["title_zh"] is None and rec_en["title"] == "Synthetic Demo Movie")
    check("归一化：无摘要时 source 退化为 wikidata、overview 为空串",
          rec_en["source"] == "wikidata" and rec_en["overview"] == "")
    check("归一化：无坐标地点不进入地图层", rec_en["locations_with_coords"] == [])

    rec_tmdb = normalize_wiki(core["900550"])
    check("归一化：TMDB 主键转成 int",
          rec_tmdb["tmdb_id"] == 900550 and isinstance(rec_tmdb["tmdb_id"], int))

    # ================= 8. 合拢与落盘 =================
    print("\n-- 合拢与落盘 --")
    records = build_wiki_records(core, geo, summaries)
    check("合拢：条数正确", len(records) == 3, f"{len(records)} 条")
    check("合拢：按年份倒序输出（diff 稳定）",
          [r["release_year"] for r in records] == [2010, 2005, 1999],
          str([r["release_year"] for r in records]))
    check("合拢：每条都覆盖全部核心字段",
          all(validate_record(r) == [] for r in records))

    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "wiki_movies.jsonl"
        n = write_jsonl(records, out)
        back = list(iter_jsonl(out))
        check("落盘：JSONL 行数与回读一致",
              n == 3 and len(back) == 3, f"{n} 行")
        check("落盘：中文不被转义成 \\uXXXX",
              "搏击俱乐部" in out.read_text(encoding="utf-8"))

    # ================= 9. 主键收集 =================
    print("\n-- 主键收集 --")
    pairs = wd.key_pairs([
        {"imdb_id": "tt0137523", "tmdb_id": 550},
        {"imdb_id": "tt0137523", "tmdb_id": 550},   # 重复
        {"imdb_id": None, "tmdb_id": 900550},       # 只有 tmdb
        {"imdb_id": "", "tmdb_id": None},           # 什么都没有
    ])
    check("主键收集：去重 + 优先 imdb + 跳过空记录",
          pairs == [("P345", "tt0137523"), ("P4947", "900550")], str(pairs))

    # ================= 汇总 =================
    passed = sum(1 for _, ok, _ in _results if ok)
    total = len(_results)
    print("\n" + "=" * 68)
    print(f"  结果：{passed}/{total} 项通过")
    if passed != total:
        print("  失败项：")
        for name, ok, detail in _results:
            if not ok:
                print(f"    - {name}  {detail}")
    print("=" * 68)
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
