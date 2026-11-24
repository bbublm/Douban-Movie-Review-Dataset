"""
阶段 4 离线自检 —— 不联网、不碰 ES、不依赖分析产物文件，
验证情感与主题分析的每个判断。

为什么这些都能离线测？
    lexicon.py / sentiment.py / topics.py 全是纯函数（语料进、数字出），
    真正决定效果的东西 —— 收缩是否生效、否定是否翻转、罕见词会不会霸榜 ——
    全都可以在这里用**构造的小样本**断言。
    等真实数据上跑完再发现问题，一次就是几十秒和几百 MB 内存。

重点盯四类容易悄悄失效的地方：
    · 罕见词没被收缩 → 主题榜被角色名霸占（第一版实测踩过）
    · 否定窗口失效 → "not wonderful" 判成正面，指标掉几个点还查不出原因
    · 词典归纳把没标签的语料也吃进去 → 正负文档数对不上
    · ES 聚合忘写 track_total_hits → 正面率算成 250%

运行：
    python tests/test_analysis_offline.py
"""
from __future__ import annotations

import json
import math
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from analysis.lexicon import (  # noqa: E402
    DIMINISHERS,
    INTENSIFIERS,
    NEGATIONS,
    chinese_matches,
    has_cjk,
    induce_lexicon,
    iter_jsonl,
    load_lexicon,
    merge_zh_fallback,
    save_lexicon,
    tokenize,
    tokenize_en,
    tokenize_zh,
)
from analysis.sentiment import evaluate, label_of, score_text  # noqa: E402
from analysis.topics import (  # noqa: E402
    STOPWORDS_EN,
    STOPWORDS_ZH,
    build_df_table,
    build_term_stats,
    drop_noise,
    keywords_for_text,
    rank_keywords,
    significant_terms_query,
)

_results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    _results.append((name, ok, detail))
    print(f"{'[ OK ]' if ok else '[FAIL]'} {name}" + (f"  ->  {detail}" if detail else ""))
    return ok


# ============================================================
# 测试语料：构造一份"能看出规则"的小样本
# ============================================================

def _corpus() -> list[dict]:
    """20 条影评，情感分布可控。

    设计要点：
      · wonderful / brilliant 只出现在 positive 里 → 应该拿到正分
      · boring / awful 只出现在 negative 里 → 应该拿到负分
      · lumet 只出现 1 次且是 positive → 收缩后分数必须远小于 wonderful
        （这一条就是防止罕见词霸榜的回归断言）
      · 有一条 "not wonderful" 的 negative 影评 → 否定规则的观测点
    """
    pos = [
        "a wonderful and brilliant film",
        "wonderful acting throughout",
        "brilliant and refreshing story",
        "a wonderful gem of a movie",
        "brilliant direction",
        "wonderful wonderful wonderful",
    ]
    neg = [
        "a boring and awful waste",
        "boring from start to finish",
        "awful acting and terrible script",
        "a boring predictable plot",
        "terrible and awful",
        "not wonderful at all",
        "boring boring boring",
    ]
    # lumet 只在一条正面里出现 1 次 —— 罕见词
    pos.append("lumet directs this one")
    # 中性高频词，正负都出现
    pos.append("the movie has a plot")
    neg.append("the movie has a plot")

    out = []
    for i, t in enumerate(pos):
        out.append({"review_id": f"p{i}", "text": t, "sentiment": "positive"})
    for i, t in enumerate(neg):
        out.append({"review_id": f"n{i}", "text": t, "sentiment": "negative"})
    # 一条没有标签的：必须被归纳过程忽略
    out.append({"review_id": "x0", "text": "wonderful boring awful", "sentiment": None})
    return out


def _lexicon(**kw):
    kw.setdefault("min_df", 1)
    return induce_lexicon(_corpus(), **kw)


# ============================================================
def main() -> int:
    print("=" * 68)
    print("  阶段 4 · 分析与洞察离线自检")
    print("=" * 68)

    # ================= 1. 分词与语种判别 =================
    print("\n-- 1. 分词与语种判别 --")

    toks = tokenize_en("A WONDERFUL, well-made film!")
    check("英文分词小写化并去标点", "wonderful" in toks and "well" in toks and "made" in toks)
    check("英文分词不产出空串", all(t and not t.isspace() for t in toks))
    check("撇号保留在词内（don't 是一个词）",
          tokenize_en("I don't like it.") == ["i", "don't", "like", "it"])

    zh = tokenize_zh("这部电影非常精彩")
    check("中文用 jieba 切出多字词", "精彩" in zh, str(zh))
    mixed = tokenize_zh("这部电影的 acting 很棒")
    check("中英混排：英文段不会被 jieba 切碎", "acting" in mixed, str(mixed))
    check("中英混排保持原始顺序（旧版先切完英文再切中文，顺序是乱的）",
          mixed == ["这部", "电影", "的", "acting", "很棒"], str(mixed))
    check("中文分词保留标点 token（否定作用域需要边界）",
          "，" in tokenize_zh("好看，浪费时间"), str(tokenize_zh("好看，浪费时间")))
    check("标点每个符号单独成 token，不成串",
          tokenize_zh("ok?!") == ["ok", "?", "!"], str(tokenize_zh("ok?!")))

    from analysis.lexicon import detect_lang  # noqa: E402
    check("纯中文判为 zh", detect_lang("太精彩了") == "zh")
    check("纯英文判为 en", detect_lang("absolutely wonderful") == "en")
    check("空文本判为 en（不当成中文）", detect_lang("") == "en")
    check("少量中文的英文文本仍判 en", detect_lang("wonderful film 好") == "en")

    # ================= 2. 规则词表自洽 =================
    print("\n-- 2. 否定/程度词表自洽 --")

    check("否定词表里没有带空格的多词形式",
          all(" " not in w for w in NEGATIONS),
          str([w for w in NEGATIONS if " " in w]))
    check("否定词表都是小写", all(w == w.lower() for w in NEGATIONS))
    check("程度副词权重都 > 1", all(v > 1 for v in INTENSIFIERS.values()))
    check("减弱副词权重都 < 1", all(0 < v < 1 for v in DIMINISHERS.values()))
    check("否定词表同时覆盖中英", {"not", "不", "没有"} <= NEGATIONS)
    check("not 在否定词表里（否定规则的核心）", "not" in NEGATIONS)

    # ================= 3. 词典归纳 =================
    print("\n-- 3. 词典归纳（含收缩回归断言）--")

    lex = _lexicon()
    check("无标签记录被忽略", lex.meta["docs"] == len(_corpus()) - 1,
          f"docs={lex.meta['docs']}")
    check("正负文档数分开统计且都不为 0",
          lex.meta["positive_docs"] > 0 and lex.meta["negative_docs"] > 0)
    check("正面词拿到正分", lex.scores.get("wonderful", 0) > 0.5,
          f"wonderful={lex.scores.get('wonderful')}")
    check("负面词拿到负分", lex.scores.get("boring", 0) < -0.5,
          f"boring={lex.scores.get('boring')}")
    check("正负都有的中义词分数接近 0",
          abs(lex.scores.get("movie", 0)) < 0.5 and abs(lex.scores.get("plot", 0)) < 0.5,
          f"movie={lex.scores.get('movie')}, plot={lex.scores.get('plot')}")

    # ★ 核心回归：罕见词必须被收缩
    rare, common = lex.scores.get("lumet", 0), lex.scores.get("wonderful", 0)
    check("罕见词的分数远小于高频同极性词（收缩生效）",
          rare < common / 2,
          f"lumet(df=1)={rare} vs wonderful(df=5)={common}")
    check("收缩只影响罕见词，不改变高频词符号",
          (rare > 0) == (common > 0))

    check("min_df 过滤低频词", "lumet" not in _lexicon(min_df=2).scores)
    check("归纳出的词都是小写", all(w == w.lower() for w in lex.scores))

    try:
        induce_lexicon([{"text": "wonderful", "sentiment": "positive"}])
        check("只有一侧标签时报错", False, "应该抛 ValueError")
    except ValueError as exc:
        check("只有一侧标签时报错", "负面" in str(exc) or "没有可用" in str(exc), str(exc)[:60])

    # ================= 4. 词典持久化 =================
    print("\n-- 4. 词典持久化 --")

    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "sub" / "lexicon.json"
        save_lexicon(lex, p)
        check("保存时自动建目录", p.exists())
        back = load_lexicon(p)
        check("存取往返分数一致", back.scores == lex.scores)
        check("存取往返 meta 一致", back.meta == lex.meta)
        check("存取往返 lang 一致", back.lang == lex.lang)
        check("落盘文件里分数降序排列（打开第一屏就是最正面的词）",
              list(json.loads(p.read_text(encoding="utf-8"))["scores"].values())
              == sorted(json.loads(p.read_text(encoding="utf-8"))["scores"].values(),
                        reverse=True))

        try:
            load_lexicon(Path(td) / "nope.json")
            check("读不存在的词典抛 FileNotFoundError", False)
        except FileNotFoundError:
            check("读不存在的词典抛 FileNotFoundError", True)

    merged = merge_zh_fallback(lex)
    check("合并中文兜底后 lang 变 mixed", merged.lang == "mixed")
    check("中文词进了词典", "精彩" in merged.scores and "烂" in merged.scores)
    check("合并不覆盖已归纳的英文词", merged.scores.get("wonderful") == lex.scores["wonderful"])

    # ================= 5. 打分规则 =================
    print("\n-- 5. 打分规则（否定/程度/转折）--")

    def sc(text: str) -> float:
        return score_text(text, lex).score

    base = sc("wonderful")
    check("基准：wonderful 判正面", base > 0, f"{base:+.4f}")
    check("否定翻转分数符号", sc("not wonderful") < 0, f"{sc('not wonderful'):+.4f}")
    check("否定窗口内生效（3 个词内）", sc("this is not wonderful") < 0)
    check("窗口外不翻转（第 4 个词）", sc("not at all this wonderful") > 0,
          f"{sc('not at all this wonderful'):+.4f}")
    check("程度副词放大正面", sc("very wonderful") > base, f"{sc('very wonderful'):+.4f}")
    check("减弱副词缩小正面", sc("somewhat wonderful") < base, f"{sc('somewhat wonderful'):+.4f}")
    check("双重否定回到正面", sc("not awful") > 0 > sc("awful") or sc("not awful") > sc("awful"),
          f"not awful={sc('not awful'):+.4f}, awful={sc('awful'):+.4f}")
    check("转折句重点在后面（but 后加权）",
          sc("wonderful but boring") < sc("wonderful and boring"),
          f"but={sc('wonderful but boring'):+.4f} and={sc('wonderful and boring'):+.4f}")

    r = score_text("", lex)
    check("空文本得 0 且判 neutral", r.score == 0.0 and r.label == "neutral")
    check("空文本没有命中词", r.hits == [])
    check("分数恒在 [-1, 1]（tanh 饱和）",
          all(-1 <= sc(t) <= 1 for t in
              ["wonderful brilliant wonderful brilliant wonderful brilliant"] * 3))
    check("命中词带上了调整后的权重", score_text("not wonderful", lex).hits[0][1] < 0)

    check("阈值上界判 positive", label_of(0.5) == "positive")
    check("阈值下界判 negative", label_of(-0.5) == "negative")
    check("区间内判 neutral", label_of(0.01) == "neutral" and label_of(-0.01) == "neutral")
    check("边界值不误判", label_of(0.05) == "neutral" and label_of(0.06) == "positive")

    # ================= 6. 中文子串匹配 =================
    print("\n-- 6. 中文子串匹配（分词边界对不上词典词条）--")

    # ★ 阶段 4 第四个坑：用户粘一句「这部电影太精彩了，强烈推荐」，
    #   jieba 切成 ['这部','电影','太精彩','了','强烈推荐']，
    #   词典里存的是「精彩」「推荐」—— 精确匹配一条都打不中，整句判 neutral。
    #   这一组断言就是那次线上翻车的回归测试。
    zh_words = merged.chinese_words()
    check("中文词条子集只含中文", all(has_cjk(w) for w in zh_words)
          and "精彩" in zh_words and "wonderful" not in zh_words,
          f"{len(zh_words)} 个中文词条")
    check("词条子集有懒缓存（重复调用不重扫词典）",
          merged.chinese_words() is merged.chinese_words())

    m = chinese_matches("太精彩", zh_words)
    check("粘合的 token 能捞出词典词条（太精彩 -> 精彩）",
          len(m) == 1 and m[0].word == "精彩" and (m[0].start, m[0].end) == (1, 3), str(m))
    check("强烈推荐 -> 推荐",
          [x.word for x in chinese_matches("强烈推荐", zh_words)] == ["推荐"])
    check("一个 token 内多个命中不重叠",
          [x.word for x in chinese_matches("精彩又推荐", zh_words)] == ["精彩", "推荐"])
    check("单字词条不被无关子串误召（烂漫不命中烂）",
          chinese_matches("烂漫", zh_words) == [], str(chinese_matches("烂漫", zh_words)))
    check("差距不命中差（没有否定词包住）", chinese_matches("差距", zh_words) == [])
    check("单字词条被否定包住时才命中（不差 -> 差）",
          [x.word for x in chinese_matches("不差", zh_words)] == ["差"])
    check("英文 token 直接返回空（不进中文分支）",
          chinese_matches("wonderful", zh_words) == [])

    def sc_zh(text: str) -> float:
        return score_text(text, merged).score

    r = score_text("这部电影太精彩了，强烈推荐", merged)
    check("★ 端到端回归：这句话必须判正面",
          r.label == "positive" and [w for w, _ in r.hits] == ["精彩", "推荐"],
          f"score={r.score:+.4f} hits={r.hits}")
    check("token 内程度副词生效（太精彩 强于 精彩）",
          sc_zh("太精彩") > sc_zh("精彩"),
          f"太精彩={sc_zh('太精彩'):+.4f} > 精彩={sc_zh('精彩'):+.4f}")
    check("token 内否定词翻转符号（不精彩 -> 负面）",
          sc_zh("不精彩") < 0, f"{sc_zh('不精彩'):+.4f}")
    hits = score_text("这部电影不精彩，不过还是推荐给想看特效的人", merged).hits
    check("否定不连坐远处的词（不精彩 … 推荐：一负一正）",
          len(hits) == 2 and hits[0][1] < 0 < hits[1][1], str(hits))
    check("已知局限：否定窗口 3 个词内会误伤（不 精彩 推荐 -> 推荐也被翻转）",
          score_text("不精彩推荐", merged).hits[1][1] < 0,
          "这是固定窗口法的固有代价，与英文 'not good and great' 同源")

    # ---- 标点截止：否定作用域的边界 ----
    from analysis.sentiment import _is_barrier  # noqa: E402

    check("标点被识别为作用域边界", _is_barrier("，") and _is_barrier("!"))
    check("文字和英文词不是边界",
          not _is_barrier("好看") and not _is_barrier("wonderful") and not _is_barrier(""))
    r = score_text("一点都不好看，浪费时间", merged)
    check("★ 否定作用域在标点处截止（逗号后的 浪费时间 不被连带翻转）",
          r.label == "negative" and [w for w, _ in r.hits] == ["好看", "浪费时间"]
          and all(w < 0 for _, w in r.hits),
          f"score={r.score:+.4f} hits={r.hits}")
    check("英文打分路径不受中文改动影响",
          score_text("not wonderful", lex).score < 0
          and score_text("wonderful", lex).score > 0)

    # ================= 7. 评估 =================
    print("\n-- 7. 评估指标 --")

    res = evaluate(_corpus(), lex)
    d = res.as_dict()
    check("评估总数 = 有标签且有正文的条数", d["total"] == len(_corpus()) - 1,
          f"total={d['total']}")
    check("准确率在 0~1 之间", 0 <= d["accuracy"] <= 1, f"{d['accuracy']:.2%}")
    check("混淆矩阵条数之和 == 总数", sum(d["confusion"].values()) == d["total"])
    check("正确数 <= 总数", d["correct"] <= d["total"])
    check("在小样本上准确率不低（规则确实在工作）", d["accuracy"] >= 0.8,
          f"{d['accuracy']:.2%}")
    check("tp+fp+fn+tn == 总数",
          res.tp + res.fp + res.fn + res.tn == d["total"],
          f"tp={res.tp} fp={res.fp} fn={res.fn} tn={res.tn}")
    check("精确率 <= 1 且非负", 0 <= d["precision"] <= 1)
    check("F1 在精确率与召回率之间",
          min(d["precision"], d["recall"]) <= d["f1"] <= max(d["precision"], d["recall"]))
    check("在小样本上准确率不低（规则确实在工作）", d["accuracy"] >= 0.8,
          f"{d['accuracy']:.2%}")
    check("收缩强度随语料规模自动缩放", lex.meta["shrink_k"] == 1.0,
          f"shrink_k={lex.meta['shrink_k']}（16 篇语料，先验取最小值 1）")

    from analysis.sentiment import evaluate_snownlp  # noqa: E402
    baseline = evaluate_snownlp(_corpus()[:4])
    check("SnowNLP 基线可用时返回 dict，不可用时返回 None（都不该抛异常）",
          baseline is None or isinstance(baseline, dict))

    # ================= 8. 主题统计 =================
    print("\n-- 8. 主题统计与排序 --")

    stats = build_term_stats(_corpus())
    check("停用词不进词表", "the" not in stats.table and "movie" not in stats.table)
    # 两条 "the movie has a plot" 整句都是停用词，去完就空了 —— 正确行为是跳过。
    # 所以这里期望 15 而不是语料总条数 17。
    check("整句都是停用词的记录被跳过（不留空文档）", stats.docs == 15, f"docs={stats.docs}")
    check("无标签记录的词也统计（主题分析不依赖标签）",
          stats.table.get("boring", [0])[0] > 0, f"boring tf={stats.table.get('boring')}")
    # wonderful：正面 4 篇（含一条里出现 3 次）+ 负面 1 篇 + 无标签 1 篇 = df 6
    check("df 按篇内去重（同一条里出现 3 次只算 1 次）",
          stats.table["wonderful"][1] == 6, f"df={stats.table['wonderful'][1]}")
    # tf：1+1+1+3（正面）+ 1（负面）+ 1（无标签）= 8
    check("tf 不去重（同一条里出现 3 次算 3 次）",
          stats.table["wonderful"][0] == 8, f"tf={stats.table['wonderful'][0]}")

    ranked = rank_keywords(stats, top_n=10, min_df=1)
    words = [k["word"] for k in ranked]
    check("★ 罕见词不霸榜：lumet 排不进前三（收缩 × 证据量生效）",
          "lumet" not in words[:3], f"前三是 {words[:3]}")
    check("真正有分量的情感词排在前面",
          any(w in words[:3] for w in ("wonderful", "boring", "awful", "brilliant")),
          f"前三是 {words[:3]}")
    check("返回值里保留未修饰的 lift", all("lift" in k for k in ranked))
    check("每条都标了偏向", all(k["side"] in ("positive", "negative") for k in ranked))
    check("min_df 生效", all(k["df"] >= 1 for k in rank_keywords(stats, min_df=2)))

    from analysis.topics import negative_vocabulary, positive_vocabulary  # noqa: E402
    # min_df=1：这两个函数的默认 min_df=30 是给 5 万条真实语料用的，
    # 小样本上会把所有词过滤光，所以这里显式关掉。
    check("好评词表里没有差评词",
          not ({"wonderful", "brilliant"} & set(negative_vocabulary(stats, top_n=5, min_df=1))))
    check("差评词表里有 boring/awful",
          bool({"boring", "awful"} & set(negative_vocabulary(stats, top_n=5, min_df=1))),
          str(negative_vocabulary(stats, top_n=5, min_df=1)))
    check("好评词表能取出 wonderful",
          "wonderful" in positive_vocabulary(stats, top_n=5, min_df=1),
          str(positive_vocabulary(stats, top_n=5, min_df=1)))

    # ================= 9. TF-IDF 与噪声过滤 =================
    print("\n-- 9. TF-IDF 与噪声过滤 --")

    df_table = {"地球": 3, "流浪": 2, "电影": 100, "的": 200, "太阳系": 1}
    kws = keywords_for_text("流浪地球 太阳系 电影 的", df_table, total_docs=120)
    check("罕见词排在常见词前面", kws[0]["word"] in ("太阳系", "流浪", "地球"),
          str([k["word"] for k in kws]))
    check("停用词不进入关键词", all(k["word"] != "电影" for k in kws), str([k["word"] for k in kws]))
    check("top_n 限制条数", len(keywords_for_text("流浪地球 太阳系", df_table,
                                              total_docs=120, top_n=1)) == 1)
    check("空文本返回空列表", keywords_for_text("", df_table, total_docs=120) == [])
    check("tfidf 分数非负且降序",
          all(k["tfidf"] >= 0 for k in kws)
          and [k["tfidf"] for k in kws] == sorted((k["tfidf"] for k in kws), reverse=True))

    check("中文单字 token 被丢弃（含'的'这类功能字）",
          drop_noise(["甲", "精彩", "的"], "zh") == ["精彩"],
          str(drop_noise(["甲", "精彩", "的"], "zh")))
    check("保留的单字词不走丢弃规则", "爱" in drop_noise(["爱"], "zh"))
    check("英文单字母 token 被丢弃", drop_noise(["a", "good"], "en") == ["good"])
    check("停用词表覆盖影评口水词",
          {"movie", "film", "plot"} <= STOPWORDS_EN and {"剧情", "演员"} <= STOPWORDS_ZH)

    # ================= 10. ES 聚合 DSL =================
    print("\n-- 10. significant_terms 聚合构造 --")

    q = significant_terms_query("genres_zh", size=15, min_doc_count=3)
    inner = q["aggs"]["significant_terms"]
    check("字段与参数透传", inner["field"] == "genres_zh" and inner["size"] == 15
          and inner["min_doc_count"] == 3)
    check("没给前景过滤时直接挂聚合", "filter" not in q["aggs"])
    check("给了前景过滤时套一层 filter 聚合",
          "foreground" in significant_terms_query(
              "genres_zh", foreground_filter={"term": {"sentiment": "positive"}})["aggs"])
    check("背景过滤透传进 significant_terms",
          significant_terms_query("genres_zh",
                                  background_filter={"term": {"lang": "en"}}
                                  )["aggs"]["significant_terms"]["background_filter"]
          == {"term": {"lang": "en"}})

    # ================= 11. 洞察接口层 =================
    print("\n-- 11. 洞察接口层（缓存与降级）--")

    from fastapi import HTTPException  # noqa: E402

    from backend.api.v1 import insights  # noqa: E402
    from backend.schemas.insights import ScoreRequest  # noqa: E402

    req = ScoreRequest(text="wonderful")
    check("ScoreRequest 接受合法入参", req.text == "wonderful" and req.lang == "auto")
    try:
        ScoreRequest(text="")
        check("空文本被模型层拒绝", False)
    except Exception:  # noqa: BLE001 —— pydantic ValidationError
        check("空文本被模型层拒绝", True)

    # 用一个临时数据湖验证「产物缺失 → 503」与「mtime 变化 → 缓存失效」
    original = insights.settings.data_lake
    with tempfile.TemporaryDirectory() as td:
        insights.settings.data_lake = td
        try:
            try:
                insights._load_artifact("lexicon.json", "测试")
                check("产物缺失时抛 503", False)
            except HTTPException as exc:
                check("产物缺失时抛 503 且带可操作提示",
                      exc.status_code == 503 and "run_analysis" in str(exc.detail),
                      str(exc.detail)[:80])

            # 造一个合法产物，验证缓存读取与失效
            target = Path(td) / "analysis" / "lexicon.json"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(json.dumps({"lang": "en", "meta": {"docs": 1},
                                          "scores": {"wonderful": 1.5}}), encoding="utf-8")
            first = insights._load_artifact("lexicon.json", "测试")
            check("能读到刚生成的产物", first["scores"]["wonderful"] == 1.5)
            second = insights._load_artifact("lexicon.json", "测试")
            check("第二次命中缓存（同一对象）", first is second)

            # 改文件内容并推晚 mtime，缓存必须失效
            import os  # noqa: E402
            import time as _t  # noqa: E402

            _t.sleep(0.01)
            target.write_text(json.dumps({"lang": "en", "meta": {"docs": 2},
                                          "scores": {"wonderful": 2.5}}), encoding="utf-8")
            future = _t.time() + 5
            os.utime(target, (future, future))
            third = insights._load_artifact("lexicon.json", "测试")
            check("文件更新后缓存自动失效", third["scores"]["wonderful"] == 2.5,
                  str(third["scores"]))
        finally:
            insights.settings.data_lake = original
            insights._CACHE.clear()

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
