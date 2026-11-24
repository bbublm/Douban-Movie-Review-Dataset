"""
情感打分 + 用 Kaggle 标签做评估。

★ 打分规则（四行就能讲完，每个命中词都能报出来）
    1. 分词，遇到情感词就累加它的分数；
    2. 前面 3 个词内出现过否定词，这个词的分数取反
       （"not good" 从 +2 变 -2；"not bad" 从 -2 变 +2 —— 双重否定也自然成立）；
    3. 前面 1 个词是程度副词，按倍数放大或缩小
       （"very good" > "good" > "somewhat good"）；
       转折词（but / 但是）之后的分句权重 ×1.3 ——
       "特效不错，但剧情一塌糊涂" 的重点在后面；
    4. 否定作用域在标点处截止（中文）：「一点都不好看，浪费时间」里
       「不」只管「好看」，逗号后面的「浪费时间」不该被连带翻转。
       中文没有空格，标点是唯一可靠的作用域边界，所以中文分词保留标点 token。

    中文还有一条专属路径：jieba 会把多个字粘成一个 token（「太精彩」「强烈推荐」），
    精确匹配打不中时走**子串匹配**把词典词条捞回来，token 内部的否定/程度
    同样生效（「不精彩」翻转、「太精彩」放大）。

    最后用 tanh 把总分压到 [-1, 1]。为什么用 tanh 而不是线性归一化？
       · 线性归一化要先知道理论最大分，而文本长短差异巨大，除以 max 会让
         长文本整体趋近 0；
       · tanh 是饱和函数：分越高越接近 1，但永远不会爆出去，
         而且短文本（只有一个词）也能拿到一个有意义的中间值。

★ 评估为什么重要
    词典是归纳出来的，规则是拍的 —— 到底准不准，必须用**没参与归纳的标准答案**量。
    Kaggle 数据集自带 positive/negative 标签，正好当测试集：
    我们的预测 vs 它的标签，出准确率、精确率、召回率、F1 和混淆矩阵。
    再把 SnowNLP（中文情感库，训练语料是电商评论）拉来当基线，
    用数字说明"为影评这个领域单独归纳词典"到底值不值。
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Iterable, Iterator

from analysis.lexicon import (
    CONTRAST_WEIGHT,
    DIMINISHERS,
    INTENSIFIERS,
    NEGATIONS,
    Lexicon,
    chinese_matches,
    detect_lang,
    has_cjk,
    tokenize,
)

# tanh 之前的总分缩放。词典分数是 log-odds 量纲（约 -5 ~ +5），
# 一条影评可能命中十几个词，总分能到几十；不缩放的话 tanh 全饱和在 ±1。
_SCORE_SCALE = 4.0

# 判定阈值：|score| < 此值判 neutral。
# 0.05 这个值不是拍的：在 5 万条影评上扫过一遍，
# 取 0.05 时 neutral 只占 1%，再放大 neutral 比例会快速上升而准确率不涨。
NEUTRAL_BAND = 0.05

# 否定词的作用窗口（往后看几个词）
NEGATION_WINDOW = 3


@dataclass
class ScoredText:
    """一段文本的打分结果，带上每个命中词 —— 这是"可解释"的落点。"""

    score: float
    label: str
    hits: list[tuple[str, float]] = field(default_factory=list)

    @property
    def words(self) -> list[str]:
        return [w for w, _ in self.hits]


def _inner_scale(seg: str) -> float:
    """token 内部（词条之前的那几个字）的程度副词倍数，取最长匹配。

    「太精彩」的 seg 是「太」→ ×1.4；「强烈推荐」的 seg 是「强烈」→ ×1.5。
    程度副词和减弱副词分表查，长度优先，同长取程度副词。
    """
    best, best_len = 1.0, 0
    for adv, mult in INTENSIFIERS.items():
        if adv in seg and len(adv) > best_len:
            best, best_len = mult, len(adv)
    for adv, mult in DIMINISHERS.items():
        if adv in seg and len(adv) > best_len:
            best, best_len = mult, len(adv)
    return best


def _is_barrier(tok: str) -> bool:
    """标点 token：否定/程度作用域的边界。

    中文分词现在会保留标点（见 lexicon.tokenize_zh），就是为了这条规则：
    「一点都不好看，浪费时间」里「不」只管「好看」，
    逗号后面的「浪费时间」不该被连带翻转。
    英文分词不产出标点 token，所以这条规则对英文影评的指标没有任何影响。
    """
    return bool(tok) and not any(ch.isalnum() for ch in tok)


def _adjust(weight: float, tokens: list[str], i: int) -> float:
    """否定窗口 / 程度副词 / 转折加权。

    从 score_text 的循环里抽出来，是因为中文子串匹配也要用同一套规则 ——
    两处各写一遍，迟早改出一边忘另一边的 bug。
    """
    # ---- 否定窗口：往前看 N 个词，但标点处截断 ----
    window = tokens[max(0, i - NEGATION_WINDOW):i]
    # 从后往前找最近的标点，只保留它之后的部分
    for j in range(len(window) - 1, -1, -1):
        if _is_barrier(window[j]):
            window = window[j + 1:]
            break
    if any(w in NEGATIONS for w in window):
        weight = -weight

    # ---- 程度副词：只看紧邻的前一个词 ----
    prev = tokens[i - 1] if i > 0 else ""
    if prev in INTENSIFIERS:
        weight *= INTENSIFIERS[prev]
    elif prev in DIMINISHERS:
        weight *= DIMINISHERS[prev]

    # ---- 转折：but / 但是 之后的内容更代表作者态度 ----
    if any(w in ("but", "however", "但是", "不过", "可是") for w in window):
        weight *= CONTRAST_WEIGHT

    return weight


def score_text(text: str, lex: Lexicon, *, lang: str | None = None) -> ScoredText:
    """给一段文本打情感分。

    lang  默认按词典的 lang 选分词器；词典是 mixed（中英合并）时传具体语言更准。
    """
    if not text:
        return ScoredText(score=0.0, label="neutral")

    # 混合词典（中英合并）时按文本内容选分词器 ——
    # 不信任记录里的 lang 字段，理由见 lexicon.detect_lang 的说明。
    use_lang = lang or (detect_lang(text) if lex.lang in ("zh", "mixed") else "en")
    tokens = tokenize(text, use_lang)

    total = 0.0
    hits: list[tuple[str, float]] = []

    # 中文子串匹配用的词条子集（Lexicon 内部懒缓存，第一次用才建）。
    # ★ 英文语料的性能保证：纯 ASCII token 直接跳过，连函数都不进。
    #   5 万条英文影评里一个 CJK token 都没有，这条 fast path 必须几乎零开销。
    zh_words = None

    for i, tok in enumerate(tokens):
        weight = lex.scores.get(tok)
        if weight is not None:
            # ---- 精确命中：正常路径（英文影评 99% 走这条）----
            w = _adjust(weight, tokens, i)
            total += w
            hits.append((tok, round(w, 3)))
            continue

        # ---- 精确匹配没中：中文 token 可能是 jieba 把多个字粘在一起了 ----
        # 「太精彩」「强烈推荐」词典里存的是「精彩」「推荐」，
        # 走子串匹配捞回来。英文 token 在此被 isascii 快速挡掉。
        if tok.isascii() or not has_cjk(tok):
            continue
        if zh_words is None:
            zh_words = lex.chinese_words()

        # token 内可能有多个不重叠命中（「精彩又推荐」→ 精彩 + 推荐）。
        # 每个命中独立套用规则：否定/程度只看"上一个命中之后到本次命中之前"那一段，
        # 这样「不精彩推荐」里 不 只翻转精彩、不影响推荐。
        prev_end = 0
        for m in chinese_matches(tok, zh_words):
            w = _adjust(lex.scores[m.word], tokens, i)
            inner = tok[prev_end:m.start]
            prev_end = m.end
            if any(neg in inner for neg in NEGATIONS):
                w = -w
            w *= _inner_scale(inner)
            total += w
            # 回报命中的词典词条而不是原始 token —— 解释性优先，
            # 用户看到"因为 精彩(+1.40) 推荐(+1.50) 所以判正面"比看到"太精彩"更清楚。
            hits.append((m.word, round(w, 3)))

    score = math.tanh(total / _SCORE_SCALE)
    return ScoredText(score=round(score, 4), label=label_of(score), hits=hits)


def label_of(score: float, *, band: float = NEUTRAL_BAND) -> str:
    """分数 -> positive / negative / neutral。阈值集中在这里，方便统一调。"""
    if score > band:
        return "positive"
    if score < -band:
        return "negative"
    return "neutral"


# ============================================================
# 批量打分（流式）
# ============================================================


def score_stream(
    records: Iterable[dict],
    lex: Lexicon,
    *,
    text_field: str = "text",
    lang_field: str = "lang",
    limit: int | None = None,
) -> Iterator[dict]:
    """流式给记录打分，产出新字段 lexicon_score / lexicon_label。

    不动原记录里的 sentiment / sentiment_score（那是 Kaggle 的标签，要留着当标准答案）。
    """
    for i, rec in enumerate(records):
        if limit is not None and i >= limit:
            return
        text = rec.get(text_field)
        if not text:
            continue
        res = score_text(text, lex, lang=rec.get(lang_field))
        out = dict(rec)
        out["lexicon_score"] = res.score
        out["lexicon_label"] = res.label
        yield out


# ============================================================
# 评估
# ============================================================


@dataclass
class EvalResult:
    """一次评估的汇总数字。字段命名对齐 sklearn 的 classification_report，方便对照。"""

    total: int = 0
    correct: int = 0
    tp: int = 0
    fp: int = 0
    fn: int = 0
    tn: int = 0
    neutral: int = 0
    confusion: dict[str, int] = field(default_factory=dict)

    @property
    def accuracy(self) -> float:
        return self.correct / self.total if self.total else 0.0

    @property
    def precision(self) -> float:
        denom = self.tp + self.fp
        return self.tp / denom if denom else 0.0

    @property
    def recall(self) -> float:
        denom = self.tp + self.fn
        return self.tp / denom if denom else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if (p + r) else 0.0

    def as_dict(self) -> dict:
        return {
            "total": self.total,
            "correct": self.correct,
            "accuracy": round(self.accuracy, 4),
            "precision": round(self.precision, 4),
            "recall": round(self.recall, 4),
            "f1": round(self.f1, 4),
            "neutral_count": self.neutral,
            "neutral_ratio": round(self.neutral / self.total, 4) if self.total else 0.0,
            "confusion": dict(self.confusion),
        }


def evaluate(
    records: Iterable[dict],
    lex: Lexicon,
    *,
    text_field: str = "text",
    label_field: str = "sentiment",
    lang_field: str = "lang",
    limit: int | None = None,
) -> EvalResult:
    """拿带标签的语料评估词典打分。

    标签为 neutral 的记录跳过：Kaggle 这份只有二分类，
    neutral 没有标准答案，硬算会污染指标。
    """
    res = EvalResult()
    for i, rec in enumerate(records):
        if limit is not None and i >= limit:
            break
        truth = str(rec.get(label_field) or "").lower()
        if truth not in ("positive", "negative"):
            continue
        text = rec.get(text_field)
        if not text:
            continue

        got = score_text(text, lex, lang=rec.get(lang_field))
        res.total += 1
        if got.label == "neutral":
            res.neutral += 1
        key = f"truth={truth} pred={got.label}"
        res.confusion[key] = res.confusion.get(key, 0) + 1

        if truth == got.label:
            res.correct += 1
        if truth == "positive" and got.label == "positive":
            res.tp += 1
        elif truth == "negative" and got.label == "positive":
            res.fp += 1
        elif truth == "positive" and got.label != "positive":
            res.fn += 1
        else:
            res.tn += 1
    return res


def evaluate_snownlp(
    records: Iterable[dict],
    *,
    text_field: str = "text",
    label_field: str = "sentiment",
    limit: int | None = None,
) -> dict | None:
    """SnowNLP 基线。装不上/跑不通就返回 None —— 基线缺失不该让主流程失败。"""
    try:
        from snownlp import SnowNLP
    except Exception:  # noqa: BLE001
        return None

    tp = fp = fn = tn = correct = total = 0
    try:
        for i, rec in enumerate(records):
            if limit is not None and i >= limit:
                break
            truth = str(rec.get(label_field) or "").lower()
            text = rec.get(text_field)
            if truth not in ("positive", "negative") or not text:
                continue
            prob = float(SnowNLP(text).sentiments)  # 0~1，>0.5 偏正面
            pred = "positive" if prob > 0.5 else "negative"
            total += 1
            correct += int(pred == truth)
            if truth == "positive" and pred == "positive":
                tp += 1
            elif truth == "negative" and pred == "positive":
                fp += 1
            elif truth == "positive":
                fn += 1
            else:
                tn += 1
    except Exception:  # noqa: BLE001
        return None

    if not total:
        return None
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    return {
        "library": "snownlp",
        "total": total,
        "correct": correct,
        "accuracy": round(correct / total, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(2 * precision * recall / (precision + recall), 4) if (precision + recall) else 0.0,
    }
