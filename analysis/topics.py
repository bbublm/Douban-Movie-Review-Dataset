"""
主题 / 关键词抽取。

★ 为什么不用"词频最高的前 N 个词"当主题？
    在影评语料上试一次就死心了：前 20 名全是 movie / film / story / one /
    see / watch —— 这些词几乎每篇都有，它们高频是因为**常见**，不是因为**重要**。
    真正能代表主题的词，是"在这个子集里出现得特别频繁、在整个语料里却不频繁"的词。
    这就是 TF-IDF 的思想，也是 ES `significant_terms` 聚合的思想。

本模块提供三样东西：
    1. `build_term_stats` + `rank_keywords`
       —— 在影评语料上流式统计 tf/df/分情感 df，输出带 lift 的关键词榜。
          lift = P(w | 正面影评) / P(w | 负面影评)，>1 说明这个词更常出现在好评里。
          这条榜就是"观众夸它什么、骂它什么"，答辩时一屏就能讲完。
    2. `build_df_table` + `keywords_for_text`
       —— 在片库文本上统计 df，再对单部电影的文本做 TF-IDF，
          得到"这部片特有的关键词"（用于 /insights/movies/{id} 的单片画像）。
    3. `significant_terms_query`
       —— 纯函数，生成 ES 的 significant_terms 聚合 DSL。
          只对 keyword 字段有效（text 字段不支持），所以给的是构造器而不是调用。

★ 内存纪律
    两处统计都是流式的：一条记录进来、更新计数器、丢掉记录。
    常驻内存只有 df 表和 term 统计表两张 dict。实测峰值见 run_analysis 输出。
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable, Sequence

from analysis.lexicon import default_shrink_k, detect_lang, tokenize

# 排序键的收缩强度与情感词典同一套算法：按正负文档规模算。
# 两处用同一个公式，是为了让"罕见词往 0 收缩"这条规则只有一种解释口径。

# ============================================================
# 停用词
# ============================================================

# 英文停用词 = 通用功能词 + 影评语料的"口水词"。
# 后半部分是针对影评加的：这些词在本领域高频但无信息量，
# 不过滤掉就会霸占词频榜（第一阶段 20 个词里 14 个是它们，实测）。
STOPWORDS_EN: frozenset[str] = frozenset({
    # ---- 通用功能词 ----
    "the", "a", "an", "and", "or", "but", "if", "of", "at", "by", "for",
    "with", "about", "to", "from", "in", "on", "out", "over", "into", "as",
    "is", "am", "are", "was", "were", "be", "been", "being", "do", "does",
    "did", "have", "has", "had", "having", "i", "you", "he", "she", "it",
    "we", "they", "me", "him", "her", "us", "them", "my", "your", "his",
    "its", "our", "their", "this", "that", "these", "those", "there",
    "here", "what", "which", "who", "whom", "when", "where", "why", "how",
    "all", "each", "every", "both", "few", "more", "most", "other", "some",
    "such", "no", "nor", "not", "only", "own", "same", "so", "than", "too",
    "very", "just", "can", "will", "should", "would", "could", "may",
    "might", "must", "shall", "also", "any", "because", "while", "up",
    "down", "then", "once", "get", "got", "make", "made", "one", "two",
    "don", "now", "even", "still", "way", "thing", "things", "much",
    "many", "well", "back", "like", "really", "quite", "lot", "bit",
    # ---- 影评口水词 ----
    "movie", "movies", "film", "films", "watch", "watched", "watching",
    "see", "saw", "seen", "seeing", "story", "stories", "plot", "script",
    "scene", "scenes", "character", "characters", "actor", "actors",
    "acting", "actress", "role", "roles", "cast", "director", "directed",
    "screen", "show", "shows", "showing", "version", "minute", "minutes",
    "hour", "hours", "time", "times", "year", "years", "old", "new",
    "good", "bad", "great", "best", "worst", "better", "worse", "love",
    "loved", "hate", "hated", "like", "liked", "enjoy", "enjoyed",
    "recommend", "recommended", "think", "thought", "know", "knew",
    "want", "wanted", "need", "needed", "say", "said", "says", "going",
    "went", "come", "came", "take", "took", "taken", "put", "end",
    "ending", "beginning", "start", "started", "first", "last", "next",
    "people", "man", "woman", "guy", "guys", "girl", "boy", "kid",
    "life", "world", "part", "parts", "kind", "sort", "type", "fact",
    # ---- 本地演示数据集的噪声词（imdb --demo 合成片库专用）----
    "demo", "synthetic",
})

# 中文停用词：影评高频口水词 + 通用功能词
STOPWORDS_ZH: frozenset[str] = frozenset({
    "电影", "影片", "这部", "一部", "一个", "这个", "那个", "什么", "怎么",
    "可以", "没有", "就是", "还是", "但是", "因为", "所以", "如果", "虽然",
    "而且", "或者", "以及", "对于", "关于", "通过", "进行", "出现", "成为",
    "觉得", "感觉", "知道", "希望", "应该", "可能", "需要", "已经", "看",
    "看了", "看过", "讲述", "故事", "剧情", "角色", "演员", "表演", "导演",
    "片子", "作品", "内容", "时候", "真的", "确实", "比较", "非常", "特别",
    "有点", "一些", "这样", "那样", "之后", "之前", "最后", "开始", "结局",
    "个人", "观众", "网友", "评分", "分", "星", "颗星",
    # ---- 本地演示数据集的噪声词 ----
    # imdb --demo 生成的合成片库里，片名是 "Demo Movie 0359"、
    # 导演是 "示例导演·甲"。这些词在真实数据里不存在，
    # 但不清掉会把演示环境的主题榜整个占满。
    "示例", "demo",
})


def _clean_words(text: str, lang: str) -> list[str]:
    """分词 -> 去停用词 -> 去噪声。三处调用点共用，保证口径一致。"""
    stop = stopwords_for(lang)
    return [w for w in drop_noise(tokenize(text, lang), lang) if w not in stop]


def stopwords_for(lang: str) -> frozenset[str]:
    return STOPWORDS_ZH if str(lang or "").startswith("zh") else STOPWORDS_EN


# 中文单字 token 基本不表意（"示例导演·甲" 会被 jieba 切成 甲 这种单字）。
# 抽关键词时直接丢掉，只有极少数单字词保留。
_ZH_KEEP_SINGLE: frozenset[str] = frozenset({"爱", "恨", "梦", "家", "光", "火", "血", "雨", "夜"})


def drop_noise(words: Iterable[str], lang: str) -> list[str]:
    """丢掉无语义噪声 token：中文单字（少数保留）、长度 1 的英文缩写。"""
    zh = str(lang or "").startswith("zh")
    out = []
    for w in words:
        if zh and len(w) == 1 and w not in _ZH_KEEP_SINGLE:
            continue
        if not zh and len(w) == 1:
            continue
        out.append(w)
    return out


# ============================================================
# 影评语料的词项统计
# ============================================================


@dataclass
class TermStats:
    """词 -> [tf, df, tf_pos, df_pos, tf_neg, df_neg]

    tf / df 是全语料口径；带 _pos / _neg 的是分情感口径，用来算 lift。
    """

    table: dict[str, list[int]] = field(default_factory=dict)
    docs: int = 0
    pos_docs: int = 0
    neg_docs: int = 0

    def add(self, word: str, *, positive: bool | None, tf: int = 1) -> None:
        row = self.table.get(word)
        if row is None:
            row = [0, 0, 0, 0, 0, 0]
            self.table[word] = row
        row[0] += tf
        if positive is True:
            row[2] += tf
        elif positive is False:
            row[4] += tf

    def add_doc(self, words: Sequence[str], *, positive: bool | None) -> None:
        """登记一篇文档：tf 逐词累加，df 按篇内去重。"""
        self.docs += 1
        if positive is True:
            self.pos_docs += 1
        elif positive is False:
            self.neg_docs += 1
        for w in set(words):
            row = self.table.get(w)
            if row is None:
                row = [0, 0, 0, 0, 0, 0]
                self.table[w] = row
            row[1] += 1
            if positive is True:
                row[3] += 1
            elif positive is False:
                row[5] += 1

    def __len__(self) -> int:
        return len(self.table)


def build_term_stats(
    records: Iterable[dict],
    *,
    text_field: str = "text",
    label_field: str = "sentiment",
    lang_field: str = "lang",
    limit: int | None = None,
) -> TermStats:
    """流式统计影评语料的词项分布。停用词在这里就丢掉，不进表。"""
    stats = TermStats()
    for i, rec in enumerate(records):
        if limit is not None and i >= limit:
            break
        text = rec.get(text_field)
        if not text:
            continue
        # 语种按文本内容判，不读 lang 字段（理由见 lexicon.detect_lang）
        lang = detect_lang(text)
        words = _clean_words(text, lang)
        if not words:
            continue
        label = str(rec.get(label_field) or "").lower()
        positive = True if label == "positive" else (False if label == "negative" else None)
        stats.add_doc(words, positive=positive)
        for w in words:
            stats.add(w, positive=positive)
    return stats


def rank_keywords(
    stats: TermStats,
    *,
    top_n: int = 30,
    min_df: int = 30,
) -> list[dict]:
    """按"与情感的关联强度"给关键词排名。

    ★ 为什么不能直接按 lift 排？（踩过）
        第一版就是按 |lift-1| 排，结果榜首全是 ponyo / matthau's / gunga 这种
        只出现在二三十篇里的角色名、导演名 —— 它们的 lift 能冲到 50，
        但只是因为"恰好这几十篇都是好评"，证据量根本不够。
        wonderful 这种 df 上千、lift 只有 3 的真信号反而被挤到看不见。

    ★ 所以排序键是两个因子的乘积：
        distinctiveness = log(lift) * df / (df + k)
            —— 和情感词典同一套收缩：罕见词的提升度按比例往 0 收缩，
               k 按语料规模自动算（default_shrink_k），小样本上不会把一切都压成 0；
        evidence = log10(1 + df)
            —— 证据量对数加权：df 从 30 到 300 到 3000，权重递增但不爆炸。
        两者相乘，"又分化、又常见"的词才排得前。

    lift 本身仍然写进返回值（不做任何修饰），前端想按原始 lift 展示也拿得到。
    """
    k = default_shrink_k(stats.pos_docs, stats.neg_docs)
    out: list[dict] = []
    for word, (tf, df, _tp, df_p, _tn, df_n) in stats.table.items():
        if df < min_df:
            continue
        p = (df_p + 0.5) / max(1, stats.pos_docs + 1)
        q = (df_n + 0.5) / max(1, stats.neg_docs + 1)
        lift = p / q
        shrunk = math.log(lift) * df / (df + k)
        weight = shrunk * math.log10(1 + df)
        out.append({
            "word": word,
            "tf": tf,
            "df": df,
            "df_positive": df_p,
            "df_negative": df_n,
            "lift": round(lift, 3),
            "side": "positive" if lift > 1 else "negative",
            "weight": round(weight, 4),
        })
    out.sort(key=lambda d: -abs(d["weight"]))
    return out[:top_n]


def positive_vocabulary(stats: TermStats, *, top_n: int = 40, min_df: int = 30) -> list[str]:
    """好评侧特有词（lift 明显 > 1）。给前端做"观众在夸什么"词云。"""
    words = [d for d in rank_keywords(stats, top_n=top_n * 3, min_df=min_df) if d["lift"] > 1.15]
    return [d["word"] for d in words[:top_n]]


def negative_vocabulary(stats: TermStats, *, top_n: int = 40, min_df: int = 30) -> list[str]:
    """差评侧特有词（lift 明显 < 1）。给前端做"观众在骂什么"词云。"""
    words = [d for d in rank_keywords(stats, top_n=top_n * 3, min_df=min_df) if d["lift"] < 0.87]
    return [d["word"] for d in words[:top_n]]


# ============================================================
# 单片关键词（TF-IDF）
# ============================================================


def build_df_table(
    records: Iterable[dict],
    *,
    fields: Sequence[str] = ("title_zh", "title", "title_en", "original_title",
                             "genres_zh", "director", "cast", "keywords",
                             "overview", "tagline", "wikipedia_extract"),
    lang_field: str = "lang",
    limit: int | None = None,
) -> dict[str, int]:
    """在片库文本上统计 df，得到 idf 表。

    一部电影的文本 = 片名 + 类型 + 导演 + 主演 + 关键词 + 简介 + 维基摘要。
    所有这些字段拼起来算 df，因为下面给单部电影提关键词时用的也是这堆字段。
    """
    df: dict[str, int] = {}
    docs = 0
    for i, rec in enumerate(records):
        if limit is not None and i >= limit:
            break
        text = " ".join(str(rec.get(f) or "") for f in fields if rec.get(f))
        if not text.strip():
            continue
        docs += 1
        # 拼接后的整段文本一起判语种：一部电影的文本可能中英混排
        lang = detect_lang(text)
        for w in set(_clean_words(text, lang)):
            df[w] = df.get(w, 0) + 1
    return df


def keywords_for_text(
    text: str,
    df_table: dict[str, int],
    *,
    total_docs: int,
    top_n: int = 12,
    lang: str | None = None,
) -> list[dict]:
    """对单段文本做 TF-IDF，返回 top_n 个关键词。

    idf = log(N / df)。df 表里没有的词给 idf = log(N)（当成最罕见的词）——
    这种情况多半是拼写错误或专有名词，给它高分比直接丢掉更合理。

    lang 传 None 时按文本内容自动判别（默认行为）。
    """
    if not text or not text.strip():
        return []
    use_lang = lang or detect_lang(text)
    words = _clean_words(text, use_lang)
    if not words:
        return []

    tf: dict[str, int] = {}
    for w in words:
        tf[w] = tf.get(w, 0) + 1
    max_tf = max(tf.values())
    n = max(1, total_docs)

    scored = []
    for w, cnt in tf.items():
        df = df_table.get(w, 0)
        idf = math.log(n / (1 + df)) if df else math.log(n)
        # tf 用词频占比（augmented normalization），长文本不会因为词多而占优
        scored.append({"word": w, "tf": cnt, "df": df,
                       "tfidf": round(0.5 + 0.5 * cnt / max_tf, 4) * round(idf, 4)})
    scored.sort(key=lambda d: -d["tfidf"])
    return scored[:top_n]


def movie_keywords(
    movie: dict,
    df_table: dict[str, int],
    *,
    total_docs: int,
    top_n: int = 12,
) -> list[dict]:
    """一部电影的关键词画像：把它的文本字段拼起来提关键词。

    拼接顺序就是字段重要性顺序 —— 提的是"这部片是什么"，
    片名和类型必须排在最前（它们权重最高，也最可能被选中）。
    """
    parts: list[str] = []
    for f in ("title_zh", "title", "genres_zh", "director", "cast",
              "keywords", "overview", "tagline", "wikipedia_extract"):
        v = movie.get(f)
        if isinstance(v, list):
            v = " ".join(str(x) for x in v)
        if v:
            parts.append(str(v))
    # 不在这里判语种了，交给 keywords_for_text 里的 detect_lang
    return keywords_for_text(" ".join(parts), df_table,
                             total_docs=total_docs, top_n=top_n)


# ============================================================
# ES significant_terms 聚合（纯函数，只对 keyword 字段有效）
# ============================================================


def significant_terms_query(
    field: str,
    *,
    size: int = 20,
    min_doc_count: int = 5,
    foreground_filter: dict | None = None,
    background_filter: dict | None = None,
) -> dict:
    """生成 ES significant_terms 聚合的 DSL。

    用法示例（找出"好评里特有的类型"）：
        field="genres_zh"
        foreground_filter={"term": {"sentiment": "positive"}}
        background_filter=None            # 背景 = 全部影评

    ★ 为什么只对 keyword 字段有效？
        significant_terms 需要按词项聚合，text 字段的倒排是分词后的结果，
        ES 8 已不支持对 text 字段做这个聚合（会报 fielddata 相关错误）。
        我们的分面字段（genres_zh / sentiment / production_countries）都是 keyword，
        正好够用。
    """
    agg: dict = {
        "significant_terms": {
            "field": field,
            "size": size,
            "min_doc_count": min_doc_count,
        }
    }
    if background_filter:
        agg["significant_terms"]["background_filter"] = background_filter
    if foreground_filter:
        return {"aggs": {"foreground": {"filter": foreground_filter, "aggs": agg}}}
    return {"aggs": agg}
