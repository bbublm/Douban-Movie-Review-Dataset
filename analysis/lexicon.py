"""
情感词典：分词、规则词表、从标注语料归纳词典。

★ 这部词典是怎么"学"出来的？
    我们有 5 万条自带情感标签的影评（Kaggle / Stanford 数据集）。
    对每个词统计它出现在正面、负面影评里的**文档频次**，然后取对数几率：

        score(w) = log( (df(w, positive) + a) / (N_pos + 2a) )
                 - log( (df(w, negative) + a) / (N_neg + 2a) )

    · 为什么用文档频次（df）而不是词频（tf）？一篇文章里同一个词出现 10 次
      只是说明这篇长，不代表它更"情感强烈"。用 df 天然做了文档内归一化。
    · 为什么要加平滑 a？没出现过 10 次的词不能得 ±infinity，
      否则 "the"（几乎每篇都有）反而会因为数据噪声被当成强情感词。
    · 为什么要卡 min_df？只出现一两次的词 df 太小，得分基本是噪声，
      还会把词典撑到几十万条、内存白涨。默认 min_df=10。

    结果是：wonderful / brilliant 拿正分，boring / worst 拿负分，
    而 the / movie / film 这种中义词得分接近 0 —— **这就是"可解释"的体现**，
    答辩时直接打印词典前 20 名，比任何黑盒模型都好讲。

★ 内存纪律（用户明确要求过）
    归纳过程是流式的：一条一条读，只维护一个 dict[str, list[int]] 计数器，
    读完再一次性筛选落盘。实测峰值内存在 run_analysis 里打印。
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Iterator

# ============================================================
# 分词
# ============================================================

# 英文词：字母数字 + 内部撇号（don't / it's / oscar-worthy 里的连字符单独处理）
_EN_TOKEN = re.compile(r"[a-z][a-z']*")


def tokenize_en(text: str) -> list[str]:
    """英文分词：小写化后按非字母切。

    刻意不做词干还原（stemming）：还原会把 wonderful/wonderfully 合成一个词根，
    看似更准，但会让"每个词对应一个可读条目"这个优势打折，
    而且影评里 wonderful 和 wonderfully 的情感强度本就不同。
    真要提高召回，词典里自然会同时收录这两个词。
    """
    if not text:
        return []
    return _EN_TOKEN.findall(text.lower())


# 中文用 jieba 精确模式。jieba 是纯 Python 词典分词，几 MB 内存，不需要模型下载。
_CJK = re.compile(r"[\u4e00-\u9fff]+")

# 按 CJK / 非 CJK 交替切段，保持原始顺序（旧版先切完英文段再切中文段，顺序是乱的）
_SEGMENT = re.compile(r"[\u4e00-\u9fff]+|[^\u4e00-\u9fff]+")

# 非 CJK 段里的英文词或单个符号。标点保留成 token 是有用的 ——
# 它是否定/程度作用域的边界，详见 tokenize_zh 的说明。
_EN_OR_PUNCT = re.compile(r"[a-z][a-z']*|[^\sA-Za-z0-9\u4e00-\u9fff]")


def has_cjk(s: str) -> bool:
    """字符串里是否含 CJK 汉字。中文路径的快速守卫：英文 token 一律不走中文匹配。"""
    return any("\u4e00" <= ch <= "\u9fff" for ch in s)


def _jieba_cut(text: str) -> list[str]:
    try:
        import jieba

        return [w for w in jieba.lcut(text) if w and not w.isspace()]
    except Exception:  # noqa: BLE001 —— 没装 jieba 时退化成按字切，不该让整个流程挂掉
        return list(text)


def tokenize_zh(text: str) -> list[str]:
    """中文分词：CJK 段交给 jieba，其余段取英文词 + 标点，保持原始顺序。

    混排文本（"这部电影的 acting 很棒"）里英文段不送进 jieba ——
    jieba 对英文是一个字符一个词，只会产出噪声 token。

    ★ 和旧版的两个区别（都是修 bug）：
      1. 保持原始顺序。旧版先把所有英文段切完、再切所有中文段，
         "这部电影的 acting 很棒" 会得到 ['acting','这部','电影','的','很棒']，
         中英文交错时否定窗口、程度副词的全都不在正确的相对位置上。
      2. 保留标点 token。否定作用域需要边界：「一点都不好看，浪费时间」里
         「不」只管「好看」，逗号后面的「浪费时间」不该被连带翻转。
         旧版把标点直接丢掉，这个边界信息就没了，窗口法只能误伤。
         （英文分词本来就不产出标点 token，所以英文影评的指标不受影响。）
    """
    if not text:
        return []
    out: list[str] = []
    for seg in _SEGMENT.finditer(text):
        s = seg.group(0)
        if _CJK.fullmatch(s):
            out.extend(_jieba_cut(s))
        else:
            out.extend(_EN_OR_PUNCT.findall(s.lower()))
    return out


def tokenize(text: str, lang: str = "en") -> list[str]:
    """按语言分词。lang 只用来选中英文/中文分词器，不校验具体语种代码。"""
    return tokenize_zh(text) if str(lang or "").startswith("zh") else tokenize_en(text)


def detect_lang(text: str) -> str:
    """按文本内容猜语言（只分中/英）。

    ★ 为什么不直接用记录里的 lang 字段？
        实测踩过：本地 demo 片库的 lang 字段是空的，而片名是英文
        （"Demo Movie 0352"）。按字段走会当成中文 → 用中文停用词表 →
        漏不掉 movie 这种英文口水词，主题榜被污染。
        文本自己会说话：有足够多 CJK 字符就当中文，否则当英文。
    """
    if not text:
        return "en"
    cjk = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    return "zh" if cjk / len(text) > 1 / 3 else "en"


# ============================================================
# 规则词表：否定、程度、转折
# ============================================================

# 否定词：出现后 N 个词内的情感词要翻转符号（"not good" / "not a bad movie"）
NEGATIONS: frozenset[str] = frozenset({
    "not", "no", "never", "nothing", "nobody", "none", "neither", "nor",
    "cannot", "cant", "can't", "dont", "don't", "doesnt", "doesn't",
    "didnt", "didn't", "isnt", "isn't", "arent", "aren't", "wasnt",
    "wasn't", "werent", "weren't", "wont", "won't", "wouldnt",
    "wouldn't", "shouldnt", "shouldn't", "couldnt", "couldn't",
    "hardly", "barely", "rarely", "seldom", "without", "lack", "lacks",
    "不", "没", "没有", "无", "非", "未", "别", "毫无", "从不", "绝不",
})

# 程度副词：把后面情感词的权重放大/缩小
INTENSIFIERS: dict[str, float] = {
    "very": 1.5, "really": 1.4, "so": 1.3, "extremely": 1.8, "absolutely": 1.8,
    "totally": 1.5, "completely": 1.6, "incredibly": 1.6, "utterly": 1.7,
    "truly": 1.4, "highly": 1.4, "deeply": 1.4, "such": 1.2, "too": 1.2,
    "最": 1.7, "非常": 1.6, "超级": 1.8, "极其": 1.8, "太": 1.4, "十分": 1.5,
    "特别": 1.5, "格外": 1.5, "相当": 1.3, "真的": 1.3, "超": 1.5, "强烈": 1.5,
}

DIMINISHERS: dict[str, float] = {
    "slightly": 0.6, "somewhat": 0.7, "rather": 0.8, "a_bit": 0.6, "kind_of": 0.7,
    "sort_of": 0.7, "pretty": 0.9, "fairly": 0.8, "almost": 0.8, "maybe": 0.8,
    "有点": 0.6, "有些": 0.7, "稍微": 0.6, "略": 0.7, "还算": 0.8, "挺": 0.9,
}

# 转折词：后面的分句权重更高（"It looks good, but the plot is boring"）
# 实现上不切分句子，只做一件事：把转折词之后的情感词加权 1.3 倍。
CONTRAST_WEIGHT = 1.3

# ============================================================
# 中文子串匹配：分词边界对不上词典词条时的兜底
# ============================================================

# 子串匹配允许的最短词条长度。为什么单字词条默认不允许？
#   中文没有空格，单字词在子串里误伤率极高：「烂漫」会命中「烂」（意思正好相反），
#   「牛奶」会命中「牛」，「爽约」会命中「爽」。
#   唯一例外见 chinese_matches 里的单字规则。
MIN_SUBSTRING_WORD_LEN = 2

# 试词长度上限。词典里最长的中文词条是 4 个字（浪费时间 / 五毛特效），
# 留一倍余量；再长只可能是噪声，不值得扫。
MAX_SUBSTRING_WORD_LEN = 8


@dataclass(frozen=True)
class ChineseMatch:
    """中文子串匹配的一条命中。

    word   命中的词典词条（不是原始 token —— 「太精彩」命中「精彩」）
    start  word 在 token 里的起始下标
    end    结束下标（不含）
    """

    word: str
    start: int
    end: int


def chinese_matches(token: str, zh_words: frozenset[str]) -> list[ChineseMatch]:
    """在中文 token 里做简化版正向最大匹配，返回所有不重叠命中。

    ★ 为什么需要它？（阶段 4 实测踩过的第四个坑）
        jieba 的分词边界和词典词条经常对不上。用户粘一句
        「这部电影太精彩了，强烈推荐」，jieba 切成
        ['这部', '电影', '太精彩', '了', '强烈推荐']，
        而词典里存的是「精彩」「推荐」—— 精确匹配一条都打不中，
        整句判成 neutral，用户看到的就是"这系统不懂中文"。

    做法（正向最大匹配的简化版）：从左往右扫，每个位置先试尽量长的词条，
    命中就跳过整个词条继续扫（保证不重叠），不命中就前进一个字。
    token 一般 2~6 个字，每个位置最多试 7 个长度，开销可以忽略。

    单字规则：当前位置是单字情感词（差/烂/爱…），且它前面（同一 token 内）
    有否定词时才允许命中 —— 「不差」应当判正面，
    而「烂漫」没有否定词包着，不该命中「烂」。
    """
    if not token or not has_cjk(token):
        return []

    out: list[ChineseMatch] = []
    i, n = 0, len(token)
    while i < n:
        hit: ChineseMatch | None = None
        longest = min(n - i, MAX_SUBSTRING_WORD_LEN)
        for size in range(longest, MIN_SUBSTRING_WORD_LEN - 1, -1):
            cand = token[i:i + size]
            if cand in zh_words:
                hit = ChineseMatch(cand, i, i + size)
                break
        if hit is None and token[i] in zh_words:
            # 单字词条：仅当同一 token 内、该字之前出现否定词时才认
            prefix = token[:i]
            if prefix and any(neg in prefix for neg in NEGATIONS):
                hit = ChineseMatch(token[i], i, i + 1)
        if hit is not None:
            out.append(hit)
            i = hit.end
        else:
            i += 1
    return out

# ============================================================
# 内置中文兜底词典
# ============================================================

# 什么时候会用到它？
#   我们自己的影评语料是英文的，归纳出来的词典也是英文的。
#   但用户在前端粘一段中文影评进来时也得能打分 —— 总不能返回"不支持"。
#   所以内置一份手写中文情感词典（正负各几十个常见词），
#   中文文本走这份，英文文本走归纳词典。两条路都写在 sentiment.py 里。
ZH_POSITIVE: tuple[str, ...] = (
    "精彩", "经典", "完美", "出色", "优秀", "惊艳", "震撼", "动人", "感人",
    "好看", "不错", "很棒", "厉害", "牛", "神作", "巅峰", "杰作", "精品",
    "值得", "推荐", "喜欢", "爱", "捧腹", "笑点", "泪点", "治愈", "温暖",
    "细腻", "深刻", "真实", "自然", "流畅", "紧凑", "过瘾", "爽", "炸裂",
    "演技在线", "颜值", "良心", "惊喜", "期待", "回味", "耐看", "高质量",
)
ZH_NEGATIVE: tuple[str, ...] = (
    "烂", "垃圾", "糟糕", "差劲", "差", "难看", "无聊", "乏味", "枯燥", "拖沓",
    "离谱", "狗血", "套路", "俗套", "尴尬", "出戏", "违和", "做作", "浮夸",
    "失望", "后悔", "浪费时间", "退票", "劝退", "避雷", "翻车", "崩", "垮",
    "看不懂", "混乱", "逻辑硬伤", "剧情漏洞", "演技差", "面瘫", "配音出戏",
    "廉价", "五毛特效", "抠图", "注水", "冗长", "催眠", "折磨", "烂尾",
)

ZH_POSITIVE_SCORE = 1.0
ZH_NEGATIVE_SCORE = -1.0

# ============================================================
# 词典数据结构
# ============================================================


@dataclass
class Lexicon:
    """一部情感词典。

    scores  词 -> 情感分（正数偏正面，负数偏负面，约 -5 ~ +5 的 log-odds 量纲）
    lang    词典适用的主要语言（en / zh）
    meta    归纳时的统计信息（语料条数、正负文档数、min_df 等），
            一起存盘，答辩时可以直接念这些数字。
    """

    scores: dict[str, float] = field(default_factory=dict)
    lang: str = "en"
    meta: dict = field(default_factory=dict)

    # 中文词条子集的懒缓存。中文没有空格，分词边界常和词典词条对不上
    # （jieba 会把「太精彩了」切成「太精彩」），所以中文要走子串匹配，
    # 而子串匹配需要一份"只含中文的词条表"——每次调用都扫一遍 1.4 万条太浪费。
    # 缓存键带 len(scores)：词典内容变化（重新归纳）时自动重建。
    _zh_cache: tuple[int, frozenset[str]] | None = field(
        default=None, repr=False, compare=False)

    def chinese_words(self) -> frozenset[str]:
        """词典里所有含 CJK 字符的词条。"""
        cached = self._zh_cache
        if cached is not None and cached[0] == len(self.scores):
            return cached[1]
        words = frozenset(w for w in self.scores if has_cjk(w))
        self._zh_cache = (len(self.scores), words)
        return words

    def __len__(self) -> int:
        return len(self.scores)

    def __contains__(self, word: str) -> bool:
        return word in self.scores

    def get(self, word: str, default: float = 0.0) -> float:
        return self.scores.get(word, default)

    def top(self, n: int = 20, *, positive: bool = True) -> list[tuple[str, float]]:
        """取情感最强的 n 个词。答辩演示用：正负各打印一屏，一眼看出词典学到了什么。"""
        items = sorted(self.scores.items(), key=lambda kv: kv[1], reverse=positive)
        return items[:n]


# 平滑系数。写在模块级而不是埋在函数里 —— 调参时改一行就能重跑，
# 而且会被记进 lexicon.json 的 meta，答辩时可复现。
ALPHA = 1.0

# 收缩强度：df 等于 shrink_k 时，原始分数打五折。
# ★ 为什么默认不写死数字，而是按语料规模算？
#    第一版写死 50，在 2.5 万篇语料上效果好；但拿 16 条的小样本一跑，
#    wonderful 被压到 0.083 —— 因为 50 相对 16 篇来说"先验太强"，
#    直接把观测数据淹没了。收缩强度必须和语料规模同量级才有意义。
# 默认公式：每 500 篇文档提供 1 个单位的先验强度（下限 1，防 0 除）。
#    2.5 万篇 -> k≈25（与写死 50 时的效果几乎一致，因为此时 df 普遍上千）
#    16 篇    -> k=1   （先验几乎不起作用，小样本也能看出区分度）
SHRINK_PER_DOCS = 500.0


def default_shrink_k(n_pos: int, n_neg: int) -> float:
    """按语料规模算收缩强度。取正负两侧中较小的那个 —— 弱的一侧才决定证据量。"""
    return max(1.0, min(n_pos, n_neg) / SHRINK_PER_DOCS)


# ============================================================
# 归纳：从带标签的影评流里统计
# ============================================================


@dataclass
class _Counter:
    """词 -> [df_positive, df_negative, tf_positive, tf_negative]

    同时记 df 和 tf：df 用来算词典分数（不受文档长度影响），
    tf 用来在报告里说明"这个词总共出现多少次"。
    """

    counts: dict[str, list[int]] = field(default_factory=dict)

    def add(self, word: str, *, positive: bool, tf: int = 1) -> None:
        row = self.counts.get(word)
        if row is None:
            row = [0, 0, 0, 0]
            self.counts[word] = row
        if positive:
            row[0] += 1
            row[2] += tf
        else:
            row[1] += 1
            row[3] += tf

    def __len__(self) -> int:
        return len(self.counts)


def induce_lexicon(
    records: Iterable[dict],
    *,
    text_field: str = "text",
    label_field: str = "sentiment",
    min_df: int = 10,
    lang: str = "en",
    max_terms: int | None = None,
    shrink_k: float | None = None,
) -> Lexicon:
    """从带情感标签的记录流里归纳词典。

    records    迭代器，每条至少要有 text 和 sentiment（positive / negative）
    min_df     词在正/负任一侧至少出现的文档数，低于此值丢弃（去噪）
    max_terms  可选，只保留 |score| 最大的前 N 个词（进一步压缩体积）
    shrink_k   收缩强度。默认 None = 按语料规模自动算（default_shrink_k），
               只有想固定强度做对照实验时才显式传。

    ★ 这里刻意不读整个文件进内存：records 是生成器，处理完一条就丢一条。
      常驻的只有 _Counter.counts 这一个 dict —— 这也是整个流程的内存大头。
    """
    counter = _Counter()
    n_pos = n_neg = 0
    seen = 0

    for rec in records:
        label = str(rec.get(label_field) or "").lower()
        text = rec.get(text_field)
        if not text or label not in ("positive", "negative"):
            continue
        seen += 1
        positive = label == "positive"
        if positive:
            n_pos += 1
        else:
            n_neg += 1

        # 同一篇内重复出现的词只算一次 df —— 用 set 去重，这是 df 的定义
        for word in set(tokenize(text, lang)):
            # 纯符号 token（标点）不进词典：它们没有情感，入典只会稀释词表。
            # 英文 token 都以字母开头，这条判断对英文语料永远不触发。
            if any(ch.isalnum() for ch in word):
                counter.add(word, positive=positive)

    if n_pos == 0 or n_neg == 0:
        raise ValueError(
            f"没有可用的带标签语料（正面 {n_pos} 条 / 负面 {n_neg} 条）。"
            "先执行 python -m transform.run_transform reviews"
        )

    alpha = ALPHA
    # 收缩强度：默认按语料规模算，保证小样本上也有区分度
    k = default_shrink_k(n_pos, n_neg) if shrink_k is None else float(shrink_k)
    # 平滑后的类条件概率分母：每侧都加 2a（正负两侧）
    denom_pos = n_pos + 2 * alpha
    denom_neg = n_neg + 2 * alpha
    scored: list[tuple[str, float]] = []
    for word, (df_p, df_n, tf_p, tf_n) in counter.counts.items():
        if df_p < min_df and df_n < min_df:
            continue
        p = (df_p + alpha) / denom_pos
        q = (df_n + alpha) / denom_neg
        # 原始对数几率
        raw = math.log(p / q)
        # ★ 经验贝叶斯收缩（shrinkage）
        #   只出现十几篇、恰好全是同一个极性的词（lumet / uwe / manos 这种导演名、
        #   片中角色名）raw 能冲到 ±3.5，但它们只是"恰好"，
        #   并不能说明这个词本身带情感 —— 直接排榜首会把 wonderful / boring
        #   这种真正有信息量的词全挤下去。
        #   做法：按 df 把 raw 往 0 收缩，df 越大越信，
        #         df = k 时收缩一半，df >> k 几乎不收缩。
        #   这是 James–Stein 收缩思想的简化版，一行公式、可解释、可复现。
        df = df_p + df_n
        scored.append((word, round(raw * df / (df + k), 4)))

    if max_terms and len(scored) > max_terms:
        scored.sort(key=lambda kv: -abs(kv[1]))
        scored = scored[:max_terms]

    return Lexicon(
        scores=dict(scored),
        lang=lang,
        meta={
            "docs": seen,
            "positive_docs": n_pos,
            "negative_docs": n_neg,
            "unique_words": len(counter),
            "kept_words": len(scored),
            "min_df": min_df,
            "smoothing": alpha,
            "shrink_k": round(k, 2),
            "method": "shrunk log-odds: log(P(w|pos)/P(w|neg)) * df/(df+shrink_k)",
        },
    )


def merge_zh_fallback(lex: Lexicon) -> Lexicon:
    """把内置中文词典并进去（中文词按固定分），得到一部中英混排可用的词典。

    为什么不是"中文一部、英文一部"？因为打分器只认一部词典，
    两套词典要在 score_text 里分支，规则会变复杂。
    合起来之后中英文文本都能直接打分，前端也不用传 lang 参数。
    """
    merged = dict(lex.scores)
    for w in ZH_POSITIVE:
        merged.setdefault(w, ZH_POSITIVE_SCORE)
    for w in ZH_NEGATIVE:
        merged.setdefault(w, ZH_NEGATIVE_SCORE)
    return Lexicon(scores=merged, lang="mixed", meta={**lex.meta, "zh_fallback": True})


# ============================================================
# 持久化
# ============================================================


def save_lexicon(lex: Lexicon, path: str | Path) -> Path:
    """词典写成 JSON。几万条词，几百 KB，人也能直接打开看。"""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "lang": lex.lang,
        "meta": lex.meta,
        # 按分数排序存放：打开文件第一屏就是最正面的词，演示效果好
        "scores": dict(sorted(lex.scores.items(), key=lambda kv: -kv[1])),
    }
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    return p


def load_lexicon(path: str | Path) -> Lexicon:
    """读回词典。文件不存在时抛 FileNotFoundError，由调用方给出可操作提示。"""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(str(p))
    payload = json.loads(p.read_text(encoding="utf-8"))
    return Lexicon(
        scores={str(k): float(v) for k, v in payload.get("scores", {}).items()},
        lang=str(payload.get("lang", "en")),
        meta=payload.get("meta", {}) or {},
    )


def iter_jsonl(path: str | Path) -> Iterator[dict]:
    """流式读 jsonl：一行一条，空行跳过，坏行报错带行号。"""
    p = Path(path)
    with p.open(encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{p}:{lineno} 不是合法 JSON：{exc}") from exc
