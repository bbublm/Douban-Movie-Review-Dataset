"""
阶段 1e 离线自检 —— 不下载 66 MB 也能验证 Kaggle 影评采集链路。

思路与 1b/1c 一致：自己造**极小的**影评 CSV（含真实数据里会遇到的各类脏东西），
跑完整流程，断言每一步的行为。

这里刻意覆盖了几个「不测就会踩」的边界：
    · 影评正文里含换行/引号/逗号 —— 必须靠 csv 模块正确处理（手写 split 必错）
    · <br /> 与 &lt;br /&gt; —— 转义与未转义的标签都要清掉
    · 列名是别名（text/label）时能否识别，title 列该不该被当成片名
    · 情感标签 1/0 的歧义，以及 --swap-labels 的效果
    · 内存纪律：流式解析 3 万行，tracemalloc 实测峰值
    · review_id 幂等：同一篇影评重复出现只留一条，重跑不会翻倍

运行：
    python tests/test_kaggle_offline.py
"""
from __future__ import annotations

import csv
import json
import shutil
import sys
import tempfile
import tracemalloc
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ingest.schema import REVIEW_FIELDS, validate_review  # noqa: E402
from ingest.sources import kaggle_reviews as kg  # noqa: E402

_results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    _results.append((name, ok, detail))
    print(f"{'[ OK ]' if ok else '[FAIL]'} {name}" + (f"  ->  {detail}" if detail else ""))
    return ok


def section(title: str) -> None:
    print(f"\n--- {title} ---")


def write_csv(path: Path, header: list[str], rows: list[list[str]]) -> Path:
    """用 csv.writer 写测试文件 —— 它负责转义，保证我们测的是解析侧而不是构造侧。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(header)
        for r in rows:
            w.writerow(r)
    return path


# ============================================================
# 1. 列名识别
# ============================================================


def test_detect_columns(tmp_path: Path) -> None:
    section("1. 列名自适应识别")

    cm = kg.detect_columns(["review", "sentiment"])
    check("标准列名 review/sentiment",
          cm.text == 0 and cm.sentiment == 1 and cm.ok, cm.describe())

    cm = kg.detect_columns(["Text", "Label"])
    check("别名 + 大小写：Text / Label",
          cm.text == 0 and cm.sentiment == 1, cm.describe())

    cm = kg.detect_columns(["movie_title", "review_text", "pol_arity".replace("_", "")])
    check("别名 movie_title / review_text",
          cm.title == 0 and cm.text == 1, cm.describe())

    cm = kg.detect_columns(["id", "review", "rating"])
    check("评分列被识别为 score",
          cm.text == 1 and cm.score == 2, cm.describe())

    # title 列在同时存在明确正文列时，应视为「评论标题」而不是片名
    cm = kg.detect_columns(["title", "review", "sentiment"])
    check("title 存在时不被误当片名（当作评论标题）",
          cm.title is None and cm.extra.get("comment_title") == 0, cm.describe())

    # ★ 歧义记录：列名只叫 `title` 时，影评语境里它更可能是「评论标题」而非片名
    #   （电影名一般会写成 movie_title / movie / film）。
    #   所以只要同时存在明确的正文列，就保守地不填 movie_title —— 宁可留空，
    #   也不要把 "A must-watch!" 这种评论标题当成电影名污染下游。
    cm = kg.detect_columns(["title", "content", "polarity"])
    check("泛化 title + 正文列 → 当评论标题（保守，不污染 movie_title）",
          cm.text == 1 and cm.title is None and cm.extra.get("comment_title") == 0,
          cm.describe())

    # 明确写出来的片名列不受上面那条保守规则影响
    cm = kg.detect_columns(["movie", "review", "sentiment"])
    check("明确片名列 movie 一定被当片名", cm.title == 0 and cm.text == 1, cm.describe())
    cm = kg.detect_columns(["film_title", "text", "label"])
    check("明确片名列 film_title 一定被当片名", cm.title == 0 and cm.text == 1, cm.describe())

    cm = kg.detect_columns(["foo", "bar"])
    check("认不出正文列时 ok=False（上层跳过而不是瞎猜）", not cm.ok, cm.describe())

    # 表头带 BOM 与空格也要能认
    cm = kg.detect_columns(["\ufeffreview ", " sentiment"])
    check("表头带 BOM 也能识别", cm.text == 0 and cm.sentiment == 1, cm.describe())


# ============================================================
# 2. 文本清洗
# ============================================================


def test_clean_text() -> None:
    section("2. 文本清洗（真实数据实测脏点）")

    check("<br /> 被清掉",
          kg.clean_review_text("A<br /><br />B") == "A B",
          repr(kg.clean_review_text("A<br /><br />B")))

    check("HTML 实体被解码",
          kg.clean_review_text("&quot;Worst&quot; &amp; boring")
          == '"Worst" & boring',
          repr(kg.clean_review_text("&quot;Worst&quot; &amp; boring")))

    # ★ 顺序坑：先 unescape 再 strip tags，否则 &lt;b&gt; 会残留成字面 <b>
    check("转义过的标签也不残留（先 unescape 再去标签）",
          kg.clean_review_text("A &lt;b&gt;bold&lt;/b&gt; B") == "A bold B",
          repr(kg.clean_review_text("A &lt;b&gt;bold&lt;/b&gt; B")))

    check("nbsp / 零宽字符被处理",
          kg.clean_review_text("A\u00a0\u200bB") == "A B",
          repr(kg.clean_review_text("A\u00a0\u200bB")))

    check("换行与连续空白归一成单空格",
          kg.clean_review_text("A\n\n   B\t\tC") == "A B C",
          repr(kg.clean_review_text("A\n\n   B\t\tC")))

    check("首尾空白被去掉",
          kg.clean_review_text("   padded   ") == "padded")

    check("None / 空值安全",
          kg.clean_review_text(None) == "" and kg.clean_review_text("") == "")

    # 文本中间本来就有 < 号（比如 "rating < 5"）不该被吞掉太多
    out = kg.clean_review_text("I rated it 4 < 5 stars")
    check("非标签的尖括号不会被误删", "5 stars" in out and "4 < 5" in out, repr(out))


# ============================================================
# 3. review_id 幂等
# ============================================================


def test_review_id() -> None:
    section("3. review_id 稳定性")

    a = kg.review_id("same text")
    b = kg.review_id("same text")
    c = kg.review_id("same text ")
    check("相同文本 → 相同 id（重跑不产生重复文档）", a == b, a)
    check("不同文本 → 不同 id", a != c)
    check("id 带 r 前缀且长度固定", a.startswith("r") and len(a) == 17, f"{a} len={len(a)}")


# ============================================================
# 4. 情感归一化
# ============================================================


def test_sentiment() -> None:
    section("4. 情感归一化")

    check("positive → (+1)", kg.normalize_sentiment("positive") == ("positive", 1.0))
    check("POSITIVE 大小写不敏感", kg.normalize_sentiment("POSITIVE") == ("positive", 1.0))
    check("negative → (-1)", kg.normalize_sentiment("negative") == ("negative", -1.0))
    check("中性词 → neutral/0", kg.normalize_sentiment("neutral") == ("neutral", 0.0))
    check("1 → positive", kg.normalize_sentiment("1") == ("positive", 1.0))
    check("0 → negative", kg.normalize_sentiment("0") == ("negative", -1.0))
    check("swap 能把 1/0 的语义翻过来",
          kg.normalize_sentiment("1", swap=True) == ("negative", -1.0))
    check("未知标签 → (None, None)", kg.normalize_sentiment("???") == (None, None))
    check("空值安全", kg.normalize_sentiment(None) == (None, None)
          and kg.normalize_sentiment("") == (None, None))

    # 评分制 → 情感（10 分制）
    check("评分 9.0 → positive", kg.sentiment_from_rating(9.0)[0] == "positive")
    check("评分 7.0（边界）→ positive", kg.sentiment_from_rating(7.0)[0] == "positive")
    check("评分 5.5 → neutral", kg.sentiment_from_rating(5.5)[0] == "neutral")
    check("评分 4.0（边界）→ negative", kg.sentiment_from_rating(4.0)[0] == "negative")
    check("评分 2.0 → negative", kg.sentiment_from_rating(2.0)[0] == "negative")
    check("评分分数归一化到 [-1,1] 且 5.5 分≈0",
          abs(kg.sentiment_from_rating(5.5)[1]) < 0.01
          and kg.sentiment_from_rating(10.0)[1] == 1.0
          and kg.sentiment_from_rating(1.0)[1] == -1.0,
          f"10分→{kg.sentiment_from_rating(10.0)[1]}, 1分→{kg.sentiment_from_rating(1.0)[1]}")
    check("评分 None → (None, None)", kg.sentiment_from_rating(None) == (None, None))


# ============================================================
# 5. CSV 解析：真实脏数据
# ============================================================


def test_parse_csv(tmp_path: Path) -> None:
    section("5. CSV 流式解析（换行/引号/残缺/去重）")

    d = tmp_path / "csv"
    # 第 1 条：正文里含换行 + 引号 + 逗号 —— 手写 split(",") 必错
    rows = [
        ['First line\nSecond line with "quotes", and, commas.', "positive"],
        ["<b>Great</b> film &amp; nice music.", "negative"],
        ["", "positive"],            # 空正文
        ["ok", "positive"],          # 过短
        ["Great film"],              # 缺列（sentiment 没有）
        ["Duplicate text here.", "positive"],
        ["Duplicate text here.", "positive"],
    ]
    # 补足 20 行正常数据
    for i in range(20):
        rows.append([f"Normal review number {i} with enough words to pass filters.", 
                     "positive" if i % 2 else "negative"])
    f = write_csv(d / "reviews.csv", ["review", "sentiment"], rows)

    res = kg.ParseResult()
    recs = list(kg.iter_records(f, result=res, quiet=True))

    check("多行/引号/逗号字段被完整保留",
          any('First line Second line with "quotes", and, commas.' == r["text"] for r in recs),
          [r["text"][:40] for r in recs[:1]])
    check("HTML 标签与实体在解析阶段就被清掉",
          any(r["text"] == "Great film & nice music." for r in recs))
    check("空正文被跳过并计数", res.skipped_empty == 1, f"skipped_empty={res.skipped_empty}")
    check("缺列行被跳过并计数", res.malformed == 1, f"malformed={res.malformed}")
    check("重复正文只留一条", res.skipped_dupe == 1 and
          sum(1 for r in recs if r["text"] == "Duplicate text here.") == 1,
          f"skipped_dupe={res.skipped_dupe}")
    check("总行数统计正确", res.rows == len(rows), f"{res.rows} vs {len(rows)}")
    check("写出条数 = 总行数 - 各类跳过",
          res.written == len(rows) - res.skipped_empty - res.malformed - res.skipped_dupe,
          f"{res.written}")

    first = recs[0]
    check("记录覆盖 REVIEW_FIELDS 全部字段",
          validate_review(first) == [], str(validate_review(first)))
    check("word_count / text_len 与正文一致",
          first["word_count"] == len(first["text"].split())
          and first["text_len"] == len(first["text"]))
    # 用那条含 HTML 的记录来验证「清洗前更长」——
    # 纯换行样本的 raw 与 clean 长度相同（\n 换成空格是 1:1），断言会误判
    html_rec = next(r for r in recs if r["text"] == "Great film & nice music.")
    check("text_raw_len 记的是清洗前的长度（HTML 清掉后变短）",
          html_rec["text_raw_len"] > html_rec["text_len"],
          f"raw={html_rec['text_raw_len']} clean={html_rec['text_len']}")
    check("数据集没有片名列 → movie_title 为 None（不省字段）",
          first["movie_title"] is None and "movie_title" in first)
    check("来源血缘字段完整",
          first["source"] == "kaggle" and first["source_file"] == "reviews.csv"
          and first["lang"] == "en")
    check("情感计数被统计", res.sentiment_dist.get("positive", 0) > 0, str(res.sentiment_dist))

    # ---- min_chars 过滤 ----
    res2 = kg.ParseResult()
    recs2 = list(kg.iter_records(f, min_chars=30, result=res2, quiet=True))
    check("--min-chars 生效", all(len(r["text"]) >= 30 for r in recs2) and res2.skipped_short >= 1,
          f"保留 {len(recs2)}，过滤 {res2.skipped_short}")

    # ---- limit ----
    res3 = kg.ParseResult()
    recs3 = list(kg.iter_records(f, limit=5, result=res3, quiet=True))
    check("--limit 生效（提前停止）", len(recs3) == 5, f"{len(recs3)}")

    # ---- 关闭去重 ----
    res4 = kg.ParseResult()
    recs4 = list(kg.iter_records(f, dedupe=False, result=res4, quiet=True))
    check("--no-dedupe 时重复正文都保留",
          sum(1 for r in recs4 if r["text"] == "Duplicate text here.") == 2,
          f"skipped_dupe={res4.skipped_dupe}")

    # ---- 跨文件共享去重 ----
    f2 = write_csv(d / "reviews2.csv", ["review", "sentiment"],
                   [["Duplicate text here.", "positive"],
                    ["A brand new review text for file two.", "negative"]])
    shared: set[str] = set()
    a = list(kg.iter_records(f, seen=shared, quiet=True))
    b = list(kg.iter_records(f2, seen=shared, quiet=True))
    check("跨文件共享去重（同一篇影评不写两次）",
          sum(1 for r in a + b if r["text"] == "Duplicate text here.") == 1,
          f"文件1={len(a)} 文件2={len(b)}")


# ============================================================
# 6. 别名列 / 评分制数据集 / swap-labels
# ============================================================


def test_alt_schema(tmp_path: Path) -> None:
    section("6. 别的数据集形态（别名列 / 评分制 / 标签翻转）")

    d = tmp_path / "alt"
    f = write_csv(d / "alt.csv", ["Text", "Label", "movie_title", "year"],
                  [["A truly excellent film overall.", "1", "Toy Story 2", "1999"],
                   ["A boring and pointless sequel.", "0", "Toy Story 3", "2010"]])
    res = kg.ParseResult()
    recs = list(kg.iter_records(f, result=res, quiet=True))
    check("别名列 Text/Label 能识别", len(recs) == 2, f"{len(recs)}")
    check("1 → positive（默认约定）", recs[0]["sentiment"] == "positive")
    check("有片名列时自动填 movie_title", recs[0]["movie_title"] == "Toy Story 2",
          str(recs[0]["movie_title"]))
    check("年份列自动填 movie_year", recs[0]["movie_year"] == 1999)
    check("有片名时记录仍覆盖 REVIEW_FIELDS", validate_review(recs[0]) == [])

    recs_swapped = list(kg.iter_records(f, swap_labels=True, quiet=True))
    check("--swap-labels 翻转标签",
          recs_swapped[0]["sentiment"] == "negative"
          and recs_swapped[0]["sentiment_score"] == -1.0)

    # 评分制数据集：没有情感列，只有 1~10 分
    f2 = write_csv(d / "rated.csv", ["review", "rating"],
                   [["Absolutely stunning cinematography throughout.", "9"],
                    ["Dull, lifeless and far too long.", "3"],
                    ["It was fine, nothing special.", "5"]])
    recs2 = list(kg.iter_records(f2, quiet=True))
    check("评分制数据集：情感由评分推出",
          [r["sentiment"] for r in recs2] == ["positive", "negative", "neutral"],
          str([(r["rating"], r["sentiment"]) for r in recs2]))
    check("原始评分被保留在 rating 字段", recs2[0]["rating"] == 9.0)


# ============================================================
# 7. 表头工具与文件发现
# ============================================================


def test_helpers(tmp_path: Path) -> None:
    section("7. 表头工具 / 文件发现")

    d = tmp_path / "helpers"
    f = write_csv(d / "x.csv", ["review", "sentiment"], [["hello world", "positive"]])
    check("header_of 读到表头", kg.header_of(f) == ["review", "sentiment"], str(kg.header_of(f)))
    check("column_index 按名找列号", kg.column_index(f, "sentiment") == 1)
    check("column_index 忽略大小写与下划线", kg.column_index(f, "SENTIMENT") == 1)
    check("column_index 找不到返回 None", kg.column_index(f, "nope") is None)
    check("column_index 空名返回 None", kg.column_index(f, "") is None)

    # find_data_files 要跳过 kagglehub 的 .complete 标记与归档包
    (d / ".complete" / "datasets" / "x").mkdir(parents=True, exist_ok=True)
    (d / ".complete" / "datasets" / "x" / "bundle.complete").write_text("", encoding="utf-8")
    (d / "data.zip").write_bytes(b"PK\x03\x04")
    found = kg.find_data_files(d)
    names = {p.name for p in found}
    check("find_data_files 跳过 .complete 与 zip", names == {"x.csv"}, str(sorted(names)))
    check("safe_dirname 把斜杠转成双下划线",
          kg.safe_dirname("owner/name") == "owner__name")


# ============================================================
# 8. 演示数据集
# ============================================================


def test_demo(tmp_path: Path) -> None:
    section("8. 演示数据集（--demo 用）")

    demo_dir = tmp_path / "demo"
    csv_path = kg.build_demo_dataset(demo_dir, rows=200)
    check("演示 CSV 被创建", csv_path.exists() and csv_path.stat().st_size > 0,
          f"{csv_path.stat().st_size} bytes")
    check("目录里有 README_DEMO.txt（防止误当真实数据）",
          (demo_dir / "README_DEMO.txt").exists())

    res = kg.ParseResult()
    recs = list(kg.iter_records(csv_path, result=res, quiet=True))
    check("演示数据能完整解析", len(recs) > 100, f"{len(recs)} 条")
    check("演示数据里埋的边界都被处理（空/重复/缺列）",
          res.skipped_empty == 2 and res.skipped_dupe == 1 and res.malformed == 1,
          f"empty={res.skipped_empty} dupe={res.skipped_dupe} malformed={res.malformed}")
    check("演示数据同时含正负样本",
          res.sentiment_dist.get("positive", 0) > 0 and res.sentiment_dist.get("negative", 0) > 0,
          str(res.sentiment_dist))
    check("演示记录也覆盖 REVIEW_FIELDS",
          all(validate_review(r) == [] for r in recs[:50]))


# ============================================================
# 9. 内存纪律
# ============================================================


def test_memory(tmp_path: Path) -> None:
    section("9. 内存纪律（流式解析 3 万行）")

    d = tmp_path / "big"
    n = 30_000
    rows = []
    for i in range(n):
        body = (f"Review number {i}: " +
                ("this was a genuinely enjoyable piece of filmmaking with strong performances " * 3
                 if i % 2 else
                 "a tedious and poorly written mess that wasted two hours of my life " * 3))
        rows.append([body, "positive" if i % 2 else "negative"])
    f = write_csv(d / "big.csv", ["review", "sentiment"], rows)
    size_mb = f.stat().st_size / 1024 / 1024
    print(f"    测试文件：{n:,} 行，{size_mb:.1f} MB")

    out = d / "out.jsonl"
    tracemalloc.start()
    res = kg.ParseResult()
    written = kg.write_jsonl_stream(kg.iter_records(f, result=res, quiet=True), out)
    _, py_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    peak_mb = py_peak / 1024 / 1024
    check(f"3 万行流式解析：Python 侧峰值分配 < 40 MB", peak_mb < 40,
          f"实测 {peak_mb:.1f} MB（内存不随行数线性增长）")
    check("全部写出", written == n, f"{written:,} 条")
    check("输出文件行数与记录数一致",
          sum(1 for _ in out.open(encoding="utf-8")) == n)

    # 逐行回读验证 JSONL 可解析且字段完整
    with out.open(encoding="utf-8") as fh:
        first = json.loads(fh.readline())
    check("落盘 JSONL 可回读且字段完整",
          validate_review(first) == [] and first["source"] == "kaggle")


# ============================================================


def main() -> int:
    print("=" * 68)
    print("  阶段 1e · Kaggle 影评采集链路离线自检")
    print("=" * 68)

    tmp = Path(tempfile.mkdtemp(prefix="yjzs_kaggle_"))
    try:
        test_detect_columns(tmp)
        test_clean_text()
        test_review_id()
        test_sentiment()
        test_parse_csv(tmp)
        test_alt_schema(tmp)
        test_helpers(tmp)
        test_demo(tmp)
        test_memory(tmp)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

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
