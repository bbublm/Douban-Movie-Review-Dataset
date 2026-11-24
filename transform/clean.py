"""
字段级清洗 —— 融合前先把「值」弄干净。

这一层就三个判断，但每一个都直接决定阶段 4/5 的统计准不准：

    1. 什么算「空」？
       —— 0.0 分的电影不存在，所以 vote_average=0.0 是「缺失」而不是「真的是 0 分」。
          不区分的话，阶段 5 的评分分布图上会凭空多出一座 0 分的山。
    2. 列表怎么并？
       —— 类型/演员/出品国取并集，但必须**去重且保序**。
          顺序影响前端分面展示的第一位，也影响「主类型」的判断。
    3. 文本怎么算长度/词数？
       —— 影评的 word_count 阶段 4 要用来做主题分析，
          口径必须和采集时完全一致，否则同一个指标会出现两个互相矛盾的数字。

关于复用：
    影评清洗（去 HTML / 空白归一）与「是否含汉字」这两件事，
    本模块**直接复用采集层的实现**，不另写一份 —— 双份实现必然漂移。
"""
from __future__ import annotations

from typing import Any, Iterable

# 影评清洗复用采集层 —— 口径必须与阶段 1e 完全一致
from ingest.sources.kaggle_reviews import clean_review_text  # noqa: F401
# 「是否含汉字」复用维基层 —— 判断标签是否回退成了英文时用的就是它
from ingest.sources.wikidata import has_han  # noqa: F401

__all__ = [
    "ZERO_IS_MISSING", "is_empty", "is_missing", "to_int", "to_float",
    "clean_str", "uniq_list", "year_of", "word_count",
    "clean_review_text", "has_han",
]

# 这些数值字段的 0 表示「没有数据」而不是「真的是 0」
#   vote_average 0.0 —— TMDB 对无评分影片就返回 0.0，当成 0 分会污染评分分布图
#   release_year 0    —— 不存在公元 0 年的电影，0 必然是脏值
ZERO_IS_MISSING = frozenset(
    {"vote_average", "vote_count", "popularity", "runtime", "release_year"}
)


def is_empty(value: Any) -> bool:
    """通用空值判断（不知道字段名时用）。"""
    if value is None:
        return True
    if isinstance(value, str):
        return not value.strip()
    if isinstance(value, (list, tuple, set, dict)):
        return len(value) == 0
    if isinstance(value, bool):
        return False          # False 是合法值（比如 is_adult=False）
    if isinstance(value, (int, float)):
        # 通用判断里 0 是**合法值**（评分 0 分、票房 0 —— 都是真实数据）。
        # 「0 到底算不算缺失」是字段语义问题，交给 is_missing 用 ZERO_IS_MISSING 判。
        return False
    return False


def is_missing(field: str, value: Any) -> bool:
    """带字段语义的空值判断。

    与 is_empty 的区别只在数值上：
        vote_average = 0.0  → 缺失（没人评分的片子 TMDB 就返回 0.0）
        rating       = 0    → 真值（某数据集用 0 分制时 0 是有效评分）
    """
    if field in ZERO_IS_MISSING and isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value) == 0.0
    return is_empty(value)


def to_int(value: Any) -> int | None:
    """能转整数就转；None / "未知" / "" / 布尔 一律 → None。"""
    if value is None or isinstance(value, bool):
        return None
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return None


def to_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def clean_str(value: Any) -> str:
    """把任意值压成「单行、无多余空白」的字符串。

    注意是压空白不是吞换行 —— 片名、导演名这类字段本来就不该有换行。
    """
    if value is None:
        return ""
    return " ".join(str(value).split())


def uniq_list(values: Iterable[Any]) -> list[str]:
    """去空、去重、**保序**的字符串列表。

    保序不是洁癖：IMDb 的类型是字母序、TMDB 是「主类型在前」，
    若这里用 set 拍平，前端分面筛选的第一位就变成随机的了。
    """
    seen: set[str] = set()
    out: list[str] = []
    for v in values or []:
        s = clean_str(v)
        if not s or s in seen:
            continue
        seen.add(s)
        out.append(s)
    return out


def year_of(date_str: Any) -> int | None:
    """从 "1999-10-15" / "1999" / "1999/10/15" 里抠出年份。"""
    s = clean_str(date_str)
    if len(s) >= 4 and s[:4].isdigit():
        return int(s[:4])
    return None


def word_count(text: str) -> int:
    """词数：英文按空白切，中文按「约 1.5 字 = 1 词」估算。

    为什么中英文要分开算？
        阶段 4 的主题分析要在同一个字段上做统计。
        若只按空白切，一整段没有空格的中文影评只会得到 1 —— 这个字段就废了。
        反过来对纯英文语料，估算公式不会触发（han 计数为 0），结果与 len(split) 一致。
    """
    if not text:
        return 0
    latin = sum(1 for w in text.split() if any(c.isascii() and c.isalnum() for c in w))
    han = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
    return latin + int(han / 1.5)
