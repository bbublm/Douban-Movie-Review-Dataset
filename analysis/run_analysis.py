"""
阶段 4 分析层入口（命令行）。

用法（在仓库根目录执行）：

    # 1. 归纳情感词典（默认用 row_index 为奇数的影评当训练集）
    python -m analysis.run_analysis lexicon

    # 2. 评估：在**没参与归纳**的影评（row_index 为偶数）上算准确率，
    #    并拉 SnowNLP 当基线对比。结果写 report.json
    python -m analysis.run_analysis report

    # 3. 主题 / 关键词：全局关键词榜 + 每部电影的关键词画像
    python -m analysis.run_analysis topics

    # 4. 给影评打情感分，产出 reviews_scored.jsonl（阶段 5 大屏用，可选）
    python -m analysis.run_analysis score --limit 5000

    # 5. 看产物现状
    python -m analysis.run_analysis check

    # 调试：只处理前 N 条
    python -m analysis.run_analysis lexicon --limit 2000

★ 为什么训练集和评估集要按 row_index 奇偶拆开？
    在同一批数据上"归纳完再考自己"，指标一定虚高 —— 那等于考试前发了答案。
    按行号奇偶切开，评估用的是词典从没见过的影评，
    报出来的准确率才是答辩时站得住脚的数字。

★ 内存
    全流程流式，常驻内存只有词典计数器 / df 表 / term 表三张 dict。
    每条子命令跑完都会打印峰值内存（用户明确要求过）。
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from common.meminfo import format_mem, peak_rss_mb
from common.settings import settings

ARTIFACTS = ("lexicon.json", "topics.json", "movie_keywords.json", "report.json")


def _print_header(title: str) -> None:
    print()
    print("=" * 68)
    print(f"  {title}")
    print("=" * 68)


def _artifact(name: str) -> Path:
    return settings.lake("analysis", name)


def _reviews_path() -> Path:
    return settings.lake("processed", "reviews.jsonl")


def _movies_path() -> Path:
    return settings.lake("processed", "movies.jsonl")


def _split_parity(value: str) -> int | None:
    """把 'odd' / 'even' / 'all' 变成 row_index 的奇偶要求。"""
    v = str(value).lower()
    if v == "odd":
        return 1
    if v == "even":
        return 0
    return None


def _iter_split(records, parity: int | None):
    """按 row_index 奇偶切分。row_index 缺失时用行号兜底。"""
    if parity is None:
        yield from records
        return
    for i, rec in enumerate(records):
        idx = rec.get("row_index")
        idx = i if not isinstance(idx, int) else idx
        if idx % 2 == parity:
            yield rec


# ============================================================
# 子命令
# ============================================================


def cmd_lexicon(args: argparse.Namespace) -> int:
    from analysis.lexicon import induce_lexicon, iter_jsonl, merge_zh_fallback, save_lexicon

    src = _reviews_path()
    if not src.exists():
        print(f"[×] 找不到 {src}")
        print("    先执行：python -m transform.run_transform reviews")
        return 1

    parity = _split_parity(args.train)
    _print_header("电影盒子 · 情感词典归纳")
    print(f"  语料       : {src.name}")
    print(f"  训练集     : row_index {'奇数' if parity == 1 else '偶数' if parity == 0 else '全部'}"
          f"（偶数{'留给评估，避免考前发答案' if parity == 1 else '留给评估' if parity == 0 else '也会用于评估，指标会偏乐观'}）")
    print(f"  min_df     : {args.min_df}（正/负任一侧出现少于此文档数的词丢弃）")

    t0 = time.perf_counter()
    lex = induce_lexicon(
        _iter_split(iter_jsonl(src), parity),
        min_df=args.min_df,
        max_terms=args.max_terms,
    )
    lex = merge_zh_fallback(lex)
    out = save_lexicon(lex, _artifact("lexicon.json"))
    secs = time.perf_counter() - t0

    meta = lex.meta
    print("-" * 68)
    print(f"  训练文档   : {meta.get('docs')} 条"
          f"（正面 {meta.get('positive_docs')} / 负面 {meta.get('negative_docs')}）")
    print(f"  见到词种   : {meta.get('unique_words')} 个 -> 入典 {meta.get('kept_words')} 个"
          f"（含内置中文 {len(lex) - int(meta.get('kept_words', 0))} 个）")
    print(f"  耗时       : {secs:.1f}s   {format_mem()}")

    print()
    print("  ── 词典学到的正面词 Top 10 ──")
    for w, s in lex.top(10, positive=True):
        print(f"    {w:<16} {s:+.3f}")
    print("  ── 词典学到的负面词 Top 10 ──")
    for w, s in lex.top(10, positive=False):
        print(f"    {w:<16} {s:+.3f}")
    print()
    print(f"  词典已写入 {out}")
    print("  下一步：python -m analysis.run_analysis report")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    from analysis.lexicon import induce_lexicon, iter_jsonl, merge_zh_fallback
    from analysis.sentiment import evaluate, evaluate_snownlp

    src = _reviews_path()
    if not src.exists():
        print(f"[×] 找不到 {src}")
        print("    先执行：python -m transform.run_transform reviews")
        return 1

    parity = _split_parity(args.train)
    eval_parity = None if parity is None else (0 if parity == 1 else 1)

    _print_header("电影盒子 · 情感打分评估（留出集）")
    print(f"  训练集     : row_index {'奇数' if parity == 1 else '偶数' if parity == 0 else '全部'}")
    print(f"  评估集     : row_index {'偶数' if eval_parity == 0 else '奇数' if eval_parity == 1 else '全部（与训练集相同，指标偏乐观）'}")

    t0 = time.perf_counter()
    lex = merge_zh_fallback(induce_lexicon(
        _iter_split(iter_jsonl(src), parity), min_df=args.min_df,
    ))
    res = evaluate(_iter_split(iter_jsonl(src), eval_parity), lex,
                   limit=args.limit)
    baseline = None
    if args.baseline:
        # ★ SnowNLP 默认不跑，两个原因：
        #   1. 它 import 一次就要 ~400 MB（实测 401 MB，我们全流程才 46 MB），
        #      用户明确要求过省内存；
        #   2. 它是用中文电商评论训练的，对英文影评本就吃亏，
        #      跑出来的数字只能当"参考下限"，不能当公平对比。
        print("  [i] 正在加载 SnowNLP 基线（内存会涨约 400 MB）…")
        baseline = evaluate_snownlp(_iter_split(iter_jsonl(src), eval_parity),
                                    limit=args.limit)
    secs = time.perf_counter() - t0

    d = res.as_dict()
    print("-" * 68)
    print(f"  评估条数   : {d['total']}   判为 neutral : {d['neutral_count']}"
          f"（{d['neutral_ratio']:.1%}）")
    print(f"  准确率     : {d['accuracy']:.2%}")
    print(f"  精确率     : {d['precision']:.2%}   （判为正面里真的是正面的比例）")
    print(f"  召回率     : {d['recall']:.2%}   （真正面里被判出来的比例）")
    print(f"  F1         : {d['f1']:.4f}")
    print("  混淆矩阵   :")
    for k, v in sorted(d["confusion"].items()):
        print(f"    {k:<34} {v}")

    print()
    if baseline:
        print(f"  基线参考   : SnowNLP 准确率 {baseline['accuracy']:.2%} / F1 {baseline['f1']:.4f}")
        print(f"              注意这是**不公平对比**：SnowNLP 用中文电商评论训练，")
        print(f"              英文影评对它几乎是随机猜。它的价值在于说明")
        print(f"              「通用情感库不等于领域可用」，正是我们要自建词典的理由。")
    else:
        print("  基线参考   : 未启用（加 --baseline 可跑 SnowNLP，内存约 +400 MB）")
    print(f"  耗时       : {secs:.1f}s   {format_mem()}")

    out = _artifact("report.json")
    out.write_text(json.dumps({
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "lexicon": lex.meta,
        "result": d,
        "baseline_snownlp": baseline,
        "memory_peak_mb": peak_rss_mb(),
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n  报告已写入 {out}")
    return 0


def cmd_topics(args: argparse.Namespace) -> int:
    from analysis.lexicon import iter_jsonl
    from analysis.topics import (
        build_df_table,
        build_term_stats,
        movie_keywords,
        negative_vocabulary,
        positive_vocabulary,
        rank_keywords,
    )

    reviews, movies = _reviews_path(), _movies_path()
    if not reviews.exists():
        print(f"[×] 找不到 {reviews}")
        print("    先执行：python -m transform.run_transform reviews")
        return 1

    _print_header("电影盒子 · 主题与关键词抽取")
    print(f"  影评语料   : {reviews.name}")
    print(f"  片库       : {movies.name if movies.exists() else '（不存在，跳过单片画像）'}")

    t0 = time.perf_counter()

    # ★ 先算单片画像、后算全局词项统计，算完立刻释放 df 表。
    #   两张表（片库 df + 影评 term stats）各占几十 MB，
    #   同时驻留会把峰值堆到 130 MB 左右；顺序执行 + del 可以砍掉一半。
    movie_kw: dict[str, list[dict]] = {}
    total_docs = 0
    movies_payload: dict = {}
    if movies.exists():
        from analysis.topics import build_df_table, movie_keywords
        movie_records = list(iter_jsonl(movies))
        total_docs = len(movie_records)
        df_table = build_df_table(movie_records)
        for m in movie_records:
            mid = m.get("movie_id")
            if not mid:
                continue
            movie_kw[mid] = movie_keywords(m, df_table, total_docs=total_docs)
        del df_table, movie_records
        movies_payload = {
            "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "total_docs": total_docs,
            "movies": movie_kw,
        }
        print(f"  单片画像   : {len(movie_kw)} 部电影")

    from analysis.topics import build_term_stats, rank_keywords
    stats = build_term_stats(iter_jsonl(reviews), limit=args.limit)
    keywords = rank_keywords(stats, top_n=args.top)
    from analysis.topics import negative_vocabulary, positive_vocabulary
    pos_vocab = positive_vocabulary(stats)
    neg_vocab = negative_vocabulary(stats)

    secs = time.perf_counter() - t0
    print("-" * 68)
    print(f"  影评篇目   : {stats.docs} 篇   词种 {len(stats)} 个")
    print(f"  耗时       : {secs:.1f}s   {format_mem()}")

    print()
    print("  ── 最能区分好评/差评的词 Top 10（收缩后的对数提升度 × 证据量）──")
    for d in keywords[:10]:
        print(f"    {d['word']:<14} df={d['df']:<6} lift={d['lift']:>6}  偏{d['side']}")
    print("  ── 观众在夸什么 ──")
    print("    " + "、".join(pos_vocab[:15]))
    print("  ── 观众在骂什么 ──")
    print("    " + "、".join(neg_vocab[:15]))

    _artifact("topics.json").write_text(json.dumps({
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "docs": stats.docs,
        "positive_docs": stats.pos_docs,
        "negative_docs": stats.neg_docs,
        "keywords": keywords,
        "positive_vocabulary": pos_vocab,
        "negative_vocabulary": neg_vocab,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    _artifact("movie_keywords.json").write_text(
        json.dumps(movies_payload, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n  已写入 {_artifact('topics.json').name} / {_artifact('movie_keywords.json').name}")
    return 0


def cmd_score(args: argparse.Namespace) -> int:
    from analysis.lexicon import iter_jsonl, load_lexicon
    from analysis.sentiment import score_stream

    src = _reviews_path()
    lex_path = _artifact("lexicon.json")
    if not src.exists():
        print(f"[×] 找不到 {src}")
        return 1
    if not lex_path.exists():
        print(f"[×] 找不到 {lex_path}")
        print("    先执行：python -m analysis.run_analysis lexicon")
        return 1

    lex = load_lexicon(lex_path)
    out = _artifact("reviews_scored.jsonl")

    _print_header("电影盒子 · 影评情感打分")
    print(f"  词典       : {lex_path.name}（{len(lex)} 词）")
    print(f"  输入       : {src.name}" + (f"（限 {args.limit} 条）" if args.limit else ""))

    t0 = time.perf_counter()
    n = 0
    agree = disagree = 0
    with out.open("w", encoding="utf-8") as fh:
        for rec in score_stream(iter_jsonl(src), lex, limit=args.limit):
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n += 1
            truth = str(rec.get("sentiment") or "").lower()
            if truth in ("positive", "negative"):
                if truth == rec["lexicon_label"]:
                    agree += 1
                else:
                    disagree += 1
    secs = time.perf_counter() - t0

    print("-" * 68)
    print(f"  已打分     : {n} 条 -> {out}")
    if agree + disagree:
        print(f"  与 Kaggle 标签一致 : {agree}（{agree / (agree + disagree):.2%}）"
              f"   不一致 : {disagree}")
    print(f"  耗时       : {secs:.1f}s   {format_mem()}")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    _print_header("电影盒子 · 分析产物现状")
    for name in ARTIFACTS:
        p = _artifact(name)
        if not p.exists():
            print(f"  [ ] {name:<24} 不存在（跑对应子命令生成）")
            continue
        size_kb = p.stat().st_size / 1024
        hint = ""
        if name == "lexicon.json":
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                hint = f"{len(data.get('scores', {}))} 词 / lang={data.get('lang')}"
            except Exception as exc:  # noqa: BLE001
                hint = f"读取失败：{exc}"
        elif name == "report.json":
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                hint = f"准确率 {data['result']['accuracy']:.2%}"
            except Exception as exc:  # noqa: BLE001
                hint = f"读取失败：{exc}"
        elif name == "topics.json":
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                hint = f"{data.get('docs')} 篇影评 / {len(data.get('keywords', []))} 个关键词"
            except Exception as exc:  # noqa: BLE001
                hint = f"读取失败：{exc}"
        elif name == "movie_keywords.json":
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                hint = f"{len(data.get('movies', {}))} 部电影"
            except Exception as exc:  # noqa: BLE001
                hint = f"读取失败：{exc}"
        print(f"  [x] {name:<24} {size_kb:>8.1f} KB   {hint}")
    print()
    print("  提示：/insights 接口依赖 lexicon.json 与 topics.json，缺失时会返回 503")
    return 0


# ============================================================
# 命令行
# ============================================================


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m analysis.run_analysis",
        description="电影盒子 · 阶段 4 分析层：情感分析 + 主题/关键词抽取",
    )
    sub = p.add_subparsers(dest="cmd", required=True)

    def common(sp: argparse.ArgumentParser) -> None:
        sp.add_argument("--limit", type=int, default=None, help="最多处理多少条（调试用）")
        sp.add_argument("--quiet", action="store_true", help="少打点日志")

    sp = sub.add_parser("lexicon", help="归纳情感词典")
    common(sp)
    sp.add_argument("--min-df", type=int, default=10, help="入典最小文档频次（默认 10）")
    sp.add_argument("--max-terms", type=int, default=None, help="只保留 |score| 最大的前 N 个词")
    sp.add_argument("--train", default="odd", choices=["odd", "even", "all"],
                    help="用 row_index 奇/偶/全部影评做训练集（默认 odd，偶数留给评估）")
    sp.set_defaults(func=cmd_lexicon)

    sp = sub.add_parser("report", help="在留出集上评估准确率")
    common(sp)
    sp.add_argument("--min-df", type=int, default=10)
    sp.add_argument("--train", default="odd", choices=["odd", "even", "all"])
    sp.add_argument("--baseline", action="store_true",
                    help="顺带跑 SnowNLP 基线（内存约 +400 MB，且对英文影评不公平，默认关）")
    sp.set_defaults(func=cmd_report)

    sp = sub.add_parser("topics", help="全局关键词榜 + 单片关键词画像")
    common(sp)
    sp.add_argument("--top", type=int, default=40, help="关键词榜取前 N 个")
    sp.set_defaults(func=cmd_topics)

    sp = sub.add_parser("score", help="给影评逐条打情感分，产出 reviews_scored.jsonl")
    common(sp)
    sp.set_defaults(func=cmd_score)

    sp = sub.add_parser("check", help="查看分析产物现状")
    sp.set_defaults(func=cmd_check)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
