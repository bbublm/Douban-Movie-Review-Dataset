"""
阶段 2 离线自检 —— 不联网、不碰 ES，验证清洗融合链路的每个判断。

为什么融合层最值得测？
    因为它是**唯一对数据做减法的地方**。采集只是搬运，融合会把 4 条记录变成 1 条 ——
    合错了没人立刻发现，等阶段 5 的可视化图上出现「一部电影两个海报」时才追回来，
    代价就大了。所以这里的断言都冲着「会被合错 / 没合上」的边界去：

    · 片名归一化：全角/消歧义括号/大小写/标点 —— 不归一就合不上
    · 三级主键的脏值过滤："N/A" 不能当 imdb_id
    · **桥接合并**：一条同时带 imdb_id 和 tmdb_id 的记录，得把两组连起来
    · **合并顺序无关**：六种顺序跑出来结果必须一致（幂等）
    · 字段优先级：中文片名不能被子源的英文名盖掉
    · vote_average=0.0 是「缺失」不是「0 分」—— 否则评分分布图会多一座山
    · 成品必须覆盖 CORE_FIELDS / REVIEW_FIELDS 合同（缺 key 会让 ES 列错位）
    · 端到端：写 interim → 跑 CLI → 读 processed，链路真的通

运行：
    python tests/test_transform_offline.py
"""
from __future__ import annotations

import argparse
import contextlib
import io
import itertools
import json
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ingest.schema import CORE_FIELDS, REVIEW_FIELDS, validate_record, validate_review  # noqa: E402
from transform.clean import is_missing, uniq_list, word_count, year_of  # noqa: E402
from transform.keys import film_keys, normalize_title  # noqa: E402
from transform.movies import MovieMerger, doc_id, finalize, merge_movies, source_of  # noqa: E402
from transform.reviews import (  # noqa: E402
    ReviewStats,
    build_title_index,
    iter_clean_reviews,
    process_review,
)
from transform.run_transform import run_movies, run_reviews  # noqa: E402

_results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    _results.append((name, ok, detail))
    print(f"{'[ OK ]' if ok else '[FAIL]'} {name}" + (f"  ->  {detail}" if detail else ""))
    return ok


def movie(**kw) -> dict:
    """造一条「字段齐全但值可空」的记录 —— 和真实采集产物同形状。"""
    base = {
        "tmdb_id": None, "imdb_id": None,
        "title": None, "title_zh": None, "title_en": None, "original_title": None,
        "release_date": None, "release_year": None, "runtime": None,
        "overview": "", "tagline": "", "status": "",
        "genres_zh": [], "genre_ids": [], "keywords": [], "director": None, "cast": [],
        "vote_average": 0.0, "vote_count": 0, "popularity": 0.0,
        "original_language": None, "spoken_languages": [],
        "production_countries": [], "production_country_codes": [],
        "poster_url": None, "backdrop_url": None,
        "source": None, "collected_at": "2026-10-14T00:00:00Z",
    }
    base.update(kw)
    return base


# ============================================================
# 1. 片名归一化与主键
# ============================================================

def test_keys() -> None:
    cases = [
        ("搏击俱乐部 (电影)", "搏击俱乐部"),
        ("Fight Club", "fightclub"),
        ("Ｆｉｇｈｔ　Ｃｌｕｂ", "fightclub"),          # 全角 → 半角
        ("Schindler's List", "schindlerslist"),
        ("Crash (2004 film)", "crash"),               # 消歧义括号
        ("  ", ""),
        (None, ""),
    ]
    bad = [f"{a!r}→{normalize_title(a)!r}（期望 {b!r}）"
           for a, b in cases if normalize_title(a) != b]
    check("片名归一化：全角/消歧义/大小写/标点", not bad, "；".join(bad) or "7 个用例全过")

    # 三级主键
    r = movie(imdb_id="tt0137523", tmdb_id=550,
              title="搏击俱乐部", release_year=1999)
    keys = film_keys(r)
    check("三级主键齐全且有序",
          keys == ["imdb:tt0137523", "tmdb:550", "title:搏击俱乐部|1999"], str(keys))

    # 脏值必须被过滤：采集端偶尔会把 "N/A" / 0 写进 id 字段
    dirty = film_keys(movie(imdb_id="N/A", tmdb_id=0, title="X", release_year=2001))
    check("脏 id 被过滤（N/A、0）", dirty == ["title:x|2001"], str(dirty))

    # 缺年份就不生成标题键（宁可漏合，也不能乱合）
    check("缺年份不生成标题键",
          film_keys(movie(title="英雄")) == [], str(film_keys(movie(title="英雄"))))

    # 关掉标题兜底键 → 没有 id 就一个键都没有
    check("--no-title-key 时无兜底键",
          film_keys(movie(title="英雄", release_year=2002), use_title_key=False) == [])

    check("source 归一化（复合标签）",
          source_of({"source": "imdb+crew"}) == "imdb"
          and source_of({"source": "wikidata+wikipedia"}) == "wikidata"
          and source_of({"source": "chinese-domestic"}) == "legacy")


# ============================================================
# 2. 字段优先级与合并
# ============================================================

def test_merge_priority() -> None:
    # legacy：中文名 + 导演（人工核过）
    legacy = movie(source="legacy", title="搏击俱乐部", title_zh="搏击俱乐部",
                   release_year=1999, director="大卫·芬奇",
                   overview="一个失眠的上班族……")
    # imdb：只有 imdb_id + 英文名 + 评分，且它是「桥」（同时带 tmdb_id）
    imdb_a = movie(source="imdb", imdb_id="tt0137523", title="Fight Club",
                   title_en="Fight Club", release_year=1999, vote_average=8.8,
                   vote_count=2200000, genres_zh=["剧情", "惊悚"], imdb_rating=8.8,
                   imdb_votes=2200000)
    # tmdb：有海报、官方简介
    tmdb = movie(source="tmdb", imdb_id="tt0137523", tmdb_id=550,
                 title="搏击俱乐部", title_zh="搏击俱乐部", title_en="Fight Club",
                 release_year=1999, overview="一名患有失眠症的上班族……",
                 poster_url="https://image.tmdb.org/x.jpg", vote_average=8.4,
                 genres_zh=["剧情"], runtime=139, production_countries=["美国"])
    # wikidata：唯一带拍摄地的源
    wiki = movie(source="wikidata+wikipedia", imdb_id="tt0137523", tmdb_id=550,
                 title="搏击俱乐部", release_year=1999,
                 filming_locations=[{"name": "洛杉矶", "lat": 34.05, "lon": -118.24},
                                    {"name": "无坐标地点", "lat": None, "lon": None}])

    merger, records = merge_movies([legacy, imdb_a, tmdb, wiki])
    check("四源合一 → 一部电影", len(records) == 1, f"得到 {len(records)} 部")
    check("四条记录全被吸收", len(merger.buckets) == 1 and not merger.keyless)

    m = records[0]
    check("中文片名胜出（title 为中文）", m["title"] == "搏击俱乐部", str(m["title"]))
    check("简介取 TMDB 的官方版",
          m["overview"].startswith("一名患有失眠症"), m["overview"][:20])
    check("导演取 legacy（人工录入）", m["director"] == "大卫·芬奇")
    check("海报取 TMDB", (m["poster_url"] or "").startswith("https://image.tmdb.org"))
    check("评分取 TMDB 而非 IMDb", m["vote_average"] == 8.4, str(m["vote_average"]))
    check("IMDb 原始评分单独保留", m["imdb_rating"] == 8.8, str(m.get("imdb_rating")))
    check("列表字段取并集（剧情+惊悚，去重）", m["genres_zh"] == ["剧情", "惊悚"], str(m["genres_zh"]))
    check("出品国带上", m["production_countries"] == ["美国"], str(m["production_countries"]))
    check("拍摄地按坐标过滤", len(m["filming_locations"]) == 2
          and len(m["locations_with_coords"]) == 1,
          f"{len(m['filming_locations'])} 处 / {len(m['locations_with_coords'])} 带坐标")
    check("血统：sources 齐全", m["sources"] == ["imdb", "legacy", "tmdb", "wikidata"], str(m["sources"]))
    check("血统：merged_from=4 / is_multi_source", m["merged_from"] == 4 and m["is_multi_source"])
    check("血统：source 是复合串", m["source"] == "imdb+legacy+tmdb+wikidata", str(m["source"]))
    check("合同字段无缺失（strict）", not validate_record(m, strict=False), "")
    try:
        validate_record(m, strict=True)
        check("validate_record(strict) 不抛异常", True)
    except ValueError as exc:
        check("validate_record(strict) 不抛异常", False, str(exc))

    check("movie_id 用 imdb_id", m["movie_id"] == "tt0137523", str(m["movie_id"]))


def test_bridge_merge() -> None:
    """桥接：A 只有 imdb_id、C 只有 tmdb_id，B 同时带两个 → 三段必须连成一条。"""
    a = movie(source="imdb", imdb_id="tt1000001", title="Bridge Movie", release_year=2005)
    c = movie(source="legacy", tmdb_id=90001, title="桥接电影", release_year=2005)
    b = movie(source="tmdb", imdb_id="tt1000001", tmdb_id=90001, title="桥接电影",
              overview="两把钥匙串起来", vote_average=7.7)

    merger = MovieMerger()
    for rec in (a, c, b):
        merger.add(rec)

    check("桥接后只剩一组", len(merger.buckets) == 1, f"{len(merger.buckets)} 组")
    check("记到 1 次桥接", merger.bridges == 1, str(merger.bridges))

    out = list(merger.results())[0]
    check("桥接后字段来自三方", out["title_zh"] == "桥接电影" and out["overview"] == "两把钥匙串起来"
          and out["imdb_id"] == "tt1000001" and out["tmdb_id"] == 90001)

    # 反向顺序（桥先来）：不该再触发一次桥接，但结果要一样
    merger2 = MovieMerger()
    for rec in (b, a, c):
        merger2.add(rec)
    check("桥先到时是普通吸收（0 次桥接）", merger2.bridges == 0, str(merger2.bridges))
    out2 = list(merger2.results())[0]
    a_ = {k: v for k, v in out.items()}
    b_ = {k: v for k, v in out2.items()}
    check("桥的顺序不影响最终结果", a_ == b_,
          "" if a_ == b_ else f"差异：{set(a_.items()) ^ set(b_.items())}")


def test_order_invariance() -> None:
    """六种输入顺序 → 结果必须完全一致（融合是幂等的）。"""
    recs = [
        movie(source="legacy", title="无间道", title_zh="无间道", release_year=2002,
              director="刘伟强", genres_zh=["犯罪", "剧情"]),
        movie(source="imdb", imdb_id="tt0338564", title="Infernal Affairs",
              title_en="Infernal Affairs", release_year=2002, vote_average=8.0),
        movie(source="tmdb", imdb_id="tt0338564", tmdb_id=10775, title="无间道",
              title_zh="无间道", release_year=2002, poster_url="p.jpg",
              overview="警匪卧底", vote_average=8.0),
    ]
    results = []
    for perm in itertools.permutations(recs):
        merger = MovieMerger()
        for r in perm:
            merger.add(r)
        got = list(merger.results())
        got[0].pop("collected_at", None)     # 时间戳天然会有秒级差异
        results.append(got)

    first = results[0]
    same = all(r == first for r in results)
    check("6 种输入顺序结果完全一致", same and len(first) == 1,
          f"{len(results)} 种顺序" + ("" if same else "：出现不一致"))


def test_zero_is_missing() -> None:
    check("vote_average=0.0 视为缺失", is_missing("vote_average", 0.0) is True)
    check("runtime=0 视为缺失", is_missing("runtime", 0) is True)
    check("rating=0 视为真值", is_missing("rating", 0) is False)
    check("空字符串视为缺失", is_missing("title", "  ") is True)
    check("空列表视为缺失", is_missing("cast", []) is True)
    check("year_of 抠年份", year_of("1999-10-15") == 1999 and year_of("2001") == 2001)

    # 一部只有 imdb 评分的电影：vote_average 应被 imdb 值填上而不是留 0
    merger, recs = merge_movies([
        movie(source="imdb", imdb_id="tt2000001", title="Zero Test", release_year=2010,
              vote_average=7.5, vote_count=100),
        movie(source="tmdb", imdb_id="tt2000001", tmdb_id=88001, title="Zero Test",
              vote_average=0.0, vote_count=0),      # TMDB 没有评分 → 不能盖掉 imdb 的 7.5
    ])
    check("0.0 分不覆盖已有评分", recs[0]["vote_average"] == 7.5, str(recs[0]["vote_average"]))

    check("uniq_list 去重保序", uniq_list(["剧情", "剧情", "", "  ", "犯罪"]) == ["剧情", "犯罪"])
    check("word_count 英文 = 词数",
          word_count("hello world foo") == 3, str(word_count("hello world foo")))
    check("word_count 中文不再恒为 1",
          word_count("这是一段没有空格的中文影评") > 5,
          str(word_count("这是一段没有空格的中文影评")))


def test_doc_id() -> None:
    a = doc_id(movie(imdb_id="tt0137523"))
    b = doc_id(movie(imdb_id="tt0137523", tmdb_id=550, title="搏击俱乐部"))
    check("有 imdb_id 时 movie_id 恒为 tconst", a == b == "tt0137523", f"{a} / {b}")
    check("只有 tmdb_id 时用 tmdb-<id>", doc_id(movie(tmdb_id=550)) == "tmdb-550")
    h1 = doc_id(movie(title="某部老片", release_year=1965))
    h2 = doc_id(movie(title="某部老片 ", release_year=1965))   # 多一个空格
    check("无名 id 时用「片名+年份」hash 且稳定", h1 == h2 and h1.startswith("m"), f"{h1} / {h2}")


# ============================================================
# 2.5 分面枚举归一化（transform/normalize.py）
#     防的是阶段 5.5 抓到的真实事故：类型分面 40+ 桶
# ============================================================

def test_normalize() -> None:
    from transform.normalize import (
        normalize_countries, normalize_country, normalize_genre,
        normalize_genres, normalize_language, normalize_languages,
        normalize_place,
    )

    # --- 类型：四种污染形态都要收敛 ---
    check("维基长名去后缀", normalize_genre("动作片") == "动作")
    check("细粒度中文分类映射", normalize_genre("超级英雄电影") == "动作")
    check("英文标签映射", normalize_genre("crime thriller film") == "惊悚")
    check("繁体先转简体再映射", normalize_genre("文明崩潰後世界題材電影") == "科幻")
    check("标准名原样返回", normalize_genre("科幻") == "科幻")
    check("噪音值丢弃", normalize_genre("Greatest Movie Hits") is None)
    check("非字符串安全", normalize_genre(None) is None and normalize_genre(42) is None)
    # 「纪录片」「电视电影」先查标准集，不能被去后缀误伤
    check("纪录片不被误切成纪录", normalize_genre("纪录片") == "纪录片")
    check("电视电影保持完整", normalize_genre("电视电影") == "电视电影")
    # 一部电影同时带短名和长名时，归一后只剩一个
    merged = normalize_genres(["剧情", "犯罪", "剧情片", "crime drama film"])
    check("同源异构值合并去重", merged == ["剧情", "犯罪"], str(merged))

    # --- 国家：中英双份归一 ---
    check("英文国名映射", normalize_country("United States of America") == "美国")
    check("正式国名映射", normalize_country("中华人民共和国") == "中国")
    check("地区映射", normalize_country("Hong Kong") == "中国香港")
    check("中文国名原样", normalize_country("法国") == "法国")
    check("空值丢弃", normalize_country("") is None)
    check("国家列表去重保序",
          normalize_countries(["美国", "United States of America", "英国"]) == ["美国", "英国"])

    # --- 语言：外文归一 + 空串丢弃（真实数据里混过 7 个空串）---
    check("英文语言映射", normalize_language("English") == "英语")
    check("西里尔 P 假英语", normalize_language("Pусский") == "俄语")
    check("韩语多写法", normalize_language("한국어/조선말") == "韩语")
    check("粤语映射", normalize_language("广州话 / 廣州話") == "粤语")
    check("空串丢弃", normalize_language("") is None and normalize_language("   ") is None)
    check("普通话归汉语", normalize_language("普通话") == "汉语")

    # --- finalize 接线：归一化必须真的挂在定稿流程里 ---
    rec = finalize({
        "imdb_id": "tt9999999", "title": "接线测试片", "release_year": 2020,
        "genres_zh": ["动作", "动作片", "crime thriller film"],
        "production_countries": ["United States of America", "美国"],
        "spoken_languages": ["English", "英语", ""],
    })
    check("finalize 后类型归一", rec["genres_zh"] == ["动作", "惊悚"], str(rec["genres_zh"]))
    check("finalize 后国家归一", rec["production_countries"] == ["美国"], str(rec["production_countries"]))
    check("finalize 后语言归一且去空", rec["spoken_languages"] == ["英语"], str(rec["spoken_languages"]))

    # --- 地名：繁体并排 + 全称短称并排（地点名归一化的重复来源）---
    check("地名繁体转简体", normalize_place("華納兄弟利維斯登製片廠") == "华纳兄弟利维斯登制片厂")
    check("地名全称归短名", normalize_place("中华人民共和国") == "中国")
    check("英文地名原样保留", normalize_place("Alabama Hills") == "Alabama Hills")
    check("虚构地名不翻译", normalize_place("Caladan") == "Caladan")
    check("地名空值", normalize_place("  ") is None)
    rec2 = finalize({
        "imdb_id": "tt9999998", "title": "地图测试片", "release_year": 2019,
        "filming_locations": [
            {"name": "長島", "lat": 40.7, "lon": -73.9, "kind": "filming"},
            {"name": "长岛", "lat": 40.7, "lon": -73.9},          # 繁简并排同坐标
            {"name": "中华人民共和国", "lat": 35.0, "lon": 105.0, "kind": "narrative"},
        ],
    })
    check("finalize 后地名归一且去重",
          [p["name"] for p in rec2["filming_locations"]] == ["长岛", "中国"],
          str(rec2["filming_locations"]))
    check("locations_with_coords 同步重算", len(rec2["locations_with_coords"]) == 2)


# ============================================================
# 3. 影评清洗与弱关联
# ============================================================

def test_reviews() -> None:
    movies = [
        {"movie_id": "tt0114709", "title": "玩具总动员", "title_zh": "玩具总动员",
         "title_en": "Toy Story", "original_title": "Toy Story", "release_year": 1995},
        {"movie_id": "tt0114709b", "title": "Crash", "title_zh": None,
         "title_en": "Crash", "original_title": "Crash", "release_year": 1996},
        {"movie_id": "tt0114709c", "title": "Crash", "title_zh": None,
         "title_en": "Crash", "original_title": "Crash", "release_year": 2004},
    ]
    index = build_title_index(movies)
    check("索引：精确键覆盖中英文名", ("toystory", 1995) in index.exact
          and ("玩具总动员", 1995) in index.exact, str(len(index.exact)))
    check("索引：有歧义的纯片名被剔除（Crash 1996/2004）", "crash" not in index.loose,
          str([k for k in index.loose if k == "crash"]))

    check("关联：带年份命中 title+year",
          index.lookup("Crash", 1996) == ("tt0114709b", "title+year"))
    check("关联：无年份且唯一时命中 title",
          index.lookup("Toy Story", None) == ("tt0114709", "title"))
    check("关联：有歧义时宁可判为对不上",
          index.lookup("Crash", None)[0] is None, str(index.lookup("Crash", None)))

    # ---- 单条处理 ----
    raw = {
        "review_id": "x", "text": "Great movie<br /><br />I loved &quot;it&quot;.",
        "text_raw_len": 45, "text_len": 40, "word_count": 999,
        "sentiment": "positive", "sentiment_score": None, "rating": None,
        "movie_title": "Toy Story", "movie_year": 1995, "imdb_id": None,
        "lang": "en", "dataset": "demo/x", "source": "kaggle",
        "source_file": "a.csv", "row_index": 7, "collected_at": "2026-10-14T00:00:00Z",
    }
    out, code = process_review(raw, index=index, min_chars=0)
    check("影评：HTML 与实体被清掉", code == "kept" and "<br" not in out["text"]
          and '"it"' in out["text"], out["text"])
    check("影评：text_len 重算", out["text_len"] == len(out["text"]), str(out["text_len"]))
    check("影评：word_count 沿用采集口径", out["word_count"] == 999, str(out["word_count"]))
    check("影评：sentiment_score 由标签补齐", out["sentiment_score"] == 1.0)
    check("影评：关联到电影", out["movie_id"] == "tt0114709" and out["matched_by"] == "title+year")
    check("影评合同字段无缺失", not validate_review(out), str(validate_review(out)))

    # ---- 过短 / 空 / 重复 ----
    short, c1 = process_review({**raw, "text": "ok"}, min_chars=20)
    check("影评：过短被丢弃", short is None and c1 == "short", c1)
    douban_short, douban_code = process_review(
        {**raw, "source": "douban", "text": "好看好看啊"}, min_chars=20
    )
    check("豆瓣短评：降低默认长度门槛后保留", douban_code == "kept" and douban_short is not None)
    douban_too_short, douban_too_short_code = process_review(
        {**raw, "source": "douban", "text": "不错"}, min_chars=20
    )
    check("豆瓣短评：极短内容仍丢弃",
          douban_too_short is None and douban_too_short_code == "short")
    empty, c2 = process_review({**raw, "text": "<br />&nbsp;"})
    check("影评：清完是空 → 丢弃", empty is None and c2 == "empty", c2)

    seen: set[str] = set()
    r1, _ = process_review(raw, seen=seen)
    r2, c3 = process_review(raw, seen=seen)
    check("影评：内容 hash 去重（同一篇只留一条）", r1 is not None and r2 is None and c3 == "dupe", c3)
    check("影评：review_id 以 r 开头且稳定",
          r1["review_id"].startswith("r") and process_review(raw)[0]["review_id"] == r1["review_id"])
    douban_raw = {
        **raw,
        "source": "douban",
        "review_id": "douban:subject-comment-1",
        "external_id": "douban:subject-comment-1",
        "douban_id": "subject-42",
        "douban_sort": "time",
        "douban_comment_time": "2024-01-02 12:30:00",
        "review_time": "2024-01-02T12:30:00",
        "movie_tmdb_id": 42,
    }
    douban_out, _ = process_review(douban_raw)
    check("豆瓣评论保留源 ID、影片、排序和评论时间",
          douban_out["review_id"] == "douban:subject-comment-1"
          and douban_out["douban_id"] == "subject-42"
          and douban_out["douban_sort"] == "time"
          and douban_out["review_time"] == "2024-01-02T12:30:00"
          and douban_out["movie_tmdb_id"] == 42)
    douban_legacy, _ = process_review({**douban_raw, "douban_sort": None})
    check("旧豆瓣评论按原热门排序计入配额",
          douban_legacy["douban_sort"] == "new_score")

    # ---- 流式 + 统计 ----
    bunch = [
        {**raw, "text": "first review " * 5},
        {**raw, "text": "first review " * 5},        # 重复
        {**raw, "text": "second " + "x" * 40},       # 保留
        {**raw, "text": "tiny"},                     # 过短
        {**raw, "text": ""},                         # 空
    ]
    stats = ReviewStats()
    kept = list(iter_clean_reviews(bunch, index=index, min_chars=20, stats=stats))
    check("流式统计自洽",
          stats.rows == 5 and stats.kept == 2 and stats.skipped_dupe == 1
          and stats.skipped_short == 1 and stats.skipped_empty == 1,
          f"rows={stats.rows} kept={stats.kept} dupe={stats.skipped_dupe} "
          f"short={stats.skipped_short} empty={stats.skipped_empty}")
    check("流式输出条数 = kept", len(kept) == stats.kept)


# ============================================================
# 4. 端到端：写 interim → 跑 CLI → 读 processed
# ============================================================

def test_end_to_end(tmp_path: Path) -> None:
    in_dir = tmp_path / "interim"
    out_dir = tmp_path / "processed"
    in_dir.mkdir(parents=True, exist_ok=True)

    def dump(name: str, records: list[dict]) -> None:
        with (in_dir / name).open("w", encoding="utf-8") as fh:
            for r in records:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    dump("seed_movies.jsonl", [
        movie(source="legacy", title="无间道", title_zh="无间道", release_year=2002,
              director="刘伟强", genres_zh=["犯罪"]),
        movie(source="legacy", title="独行孤片", title_zh="独行孤片", release_year=1978),
    ])
    dump("imdb_movies.demo.jsonl", [
        movie(source="imdb+crew", imdb_id="tt0338564", title="Infernal Affairs",
              title_en="Infernal Affairs", release_year=2002, vote_average=8.0,
              vote_count=100, genres_zh=["剧情", "犯罪"], genres_en=["Crime"]),
    ])
    dump("wiki_movies.demo.jsonl", [
        movie(source="wikidata+wikipedia", imdb_id="tt0338564", tmdb_id=10775,
              title="无间道", release_year=2002,
              filming_locations=[{"name": "香港", "lat": 22.32, "lon": 114.17}]),
    ])
    dump("reviews.jsonl", [
        {**{"review_id": "x", "text": "A long enough great review about the movie. " * 3,
            "text_raw_len": 200, "text_len": 180, "word_count": 30,
            "sentiment": "positive", "sentiment_score": 1.0, "rating": None,
            "movie_title": "Infernal Affairs", "movie_year": 2002, "imdb_id": None,
            "lang": "en", "dataset": "demo/x", "source": "kaggle",
            "source_file": "a.csv", "row_index": 0,
            "collected_at": "2026-10-14T00:00:00Z"}},
        {**{"review_id": "y", "text": "Too short", "text_raw_len": 9, "text_len": 9,
            "word_count": 2, "sentiment": "negative", "sentiment_score": -1.0,
            "rating": None, "movie_title": None, "movie_year": None, "imdb_id": None,
            "lang": "en", "dataset": "demo/x", "source": "kaggle",
            "source_file": "a.csv", "row_index": 1,
            "collected_at": "2026-10-14T00:00:00Z"}},
    ])

    ns = argparse.Namespace(from_dir=str(in_dir), out_dir=str(out_dir),
                            include_demo=True, dry_run=False, limit=None,
                            no_title_key=False, min_chars=20)

    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc1 = run_movies(ns)
        rc2 = run_reviews(ns)
    log = buf.getvalue()

    check("端到端：movies 子命令返回 0", rc1 == 0, log[-300:] if rc1 else "")
    check("端到端：reviews 子命令返回 0", rc2 == 0, log[-300:] if rc2 else "")

    movies_path = out_dir / "movies.jsonl"
    reviews_path = out_dir / "reviews.jsonl"
    check("端到端：产出了两个文件", movies_path.exists() and reviews_path.exists())

    movies = [json.loads(l) for l in movies_path.read_text("utf-8").splitlines() if l.strip()]
    reviews = [json.loads(l) for l in reviews_path.read_text("utf-8").splitlines() if l.strip()]

    check("端到端：3 条 → 2 部电影（无间道被合并）", len(movies) == 2, f"{len(movies)} 部")
    wu = next((m for m in movies if m.get("imdb_id") == "tt0338564"), None)
    check("端到端：合出来的这条跨 3 个源",
          wu is not None and wu["source_count"] == 3, str(wu["sources"] if wu else None))
    check("端到端：中文名 + 英文名都在",
          wu and wu["title"] == "无间道" and wu["title_en"] == "Infernal Affairs",
          f"{wu['title']} / {wu['title_en']}" if wu else "")
    check("端到端：拍摄地坐标带过来", wu and wu["locations_with_coords"][0]["name"] == "香港")
    orphan = next((m for m in movies if m["title"] == "独行孤片"), None)
    check("端到端：孤儿记录单独成条（没被硬塞进别的组）",
          orphan is not None and orphan["source_count"] == 1)

    check("端到端：影评过短的被丢掉 → 剩 1 条", len(reviews) == 1, f"{len(reviews)} 条")
    check("端到端：影评关联回电影",
          reviews and reviews[0]["movie_id"] == "tt0338564", str(reviews[0]["movie_id"]) if reviews else "")

    # --no-demo 时应该只看得到 seed 那一条源
    with contextlib.redirect_stdout(io.StringIO()):
        ns2 = argparse.Namespace(from_dir=str(in_dir), out_dir=str(out_dir),
                                 include_demo=False, dry_run=False, limit=None,
                                 no_title_key=False, min_chars=20)
        run_movies(ns2)
    alone = [json.loads(l) for l in movies_path.read_text("utf-8").splitlines() if l.strip()]
    check("端到端：--no-demo 只剩 seed 的两部",
          len(alone) == 2 and all(m["sources"] == ["legacy"] for m in alone),
          f"{len(alone)} 部")


def test_shrink_guard(tmp_path: Path) -> None:
    in_dir = tmp_path / "interim"
    out_dir = tmp_path / "processed"
    in_dir.mkdir(parents=True)
    out_dir.mkdir()
    sparse = movie(source="douban", imdb_id="tt0000001", title="稀疏增量")
    (in_dir / "douban_movies.jsonl").write_text(
        json.dumps(sparse, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    existing_movies = [
        finalize({
            **movie(source="legacy", title=f"完整影片{i}", title_zh=f"完整影片{i}",
                    release_year=2000 + i, vote_average=7.5, vote_count=100,
                    genres_zh=["剧情"], director="导演", cast=["演员"],
                    overview="完整简介", poster_url="https://example.test/poster.jpg"),
            "_sources": {"legacy"}, "_raw_count": 1, "_keys": set(),
        })
        for i in range(2)
    ]
    movies_path = out_dir / "movies.jsonl"
    movies_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in existing_movies),
        encoding="utf-8",
    )
    original_movies = movies_path.read_text(encoding="utf-8")
    ns = argparse.Namespace(from_dir=str(in_dir), out_dir=str(out_dir),
                            include_demo=False, dry_run=False, limit=None,
                            no_title_key=False, min_chars=0, force=False)
    with contextlib.redirect_stdout(io.StringIO()):
        movie_rc = run_movies(ns)
    check("安全保护：稀疏电影增量不能覆盖更完整片库",
          movie_rc == 2 and movies_path.read_text("utf-8") == original_movies)

    review = {
        "text": "这是一条足够长的本地测试评论，用来验证影评文件不会被少量新数据覆盖。",
        "movie_title": "完整影片0", "movie_year": 2000, "source": "douban",
        "dataset": "test", "sentiment": "positive",
    }
    (in_dir / "reviews.douban.jsonl").write_text(
        json.dumps(review, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    reviews_path = out_dir / "reviews.jsonl"
    original_reviews = '{"review_id":"old-1"}\n{"review_id":"old-2"}\n'
    reviews_path.write_text(original_reviews, encoding="utf-8")
    with contextlib.redirect_stdout(io.StringIO()):
        review_rc = run_reviews(ns)
    check("安全保护：较少影评不能覆盖现有评论库",
          review_rc == 2 and reviews_path.read_text("utf-8") == original_reviews)

    ns.force = True
    with contextlib.redirect_stdout(io.StringIO()):
        forced_movie_rc = run_movies(ns)
    check("显式 --force 可执行片库覆盖", forced_movie_rc == 0)
    with contextlib.redirect_stdout(io.StringIO()):
        forced_review_rc = run_reviews(ns)
    check("显式 --force 可执行影评覆盖", forced_review_rc == 0)


# ============================================================

def main() -> int:
    print("=" * 68)
    print("  阶段 2 · 清洗融合 离线自检")
    print("=" * 68)

    test_keys()
    test_merge_priority()
    test_bridge_merge()
    test_order_invariance()
    test_zero_is_missing()
    test_doc_id()
    test_normalize()
    test_reviews()

    tmp = Path(tempfile.mkdtemp(prefix="yjzs_transform_"))
    try:
        test_end_to_end(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    guard_tmp = Path(tempfile.mkdtemp(prefix="yjzs_transform_guard_"))
    try:
        test_shrink_guard(guard_tmp)
    finally:
        shutil.rmtree(guard_tmp, ignore_errors=True)

    passed = sum(1 for _, ok, _ in _results if ok)
    total = len(_results)
    print("-" * 68)
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
