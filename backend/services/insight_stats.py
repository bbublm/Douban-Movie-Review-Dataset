"""深度洞察的纯统计函数（2026-11-04）。

用户红线：「数据要是真的分析得出来，而不是把现成的数据直接放上去」。
这一层就是「分析」本身：相关系数、最小二乘回归、四分位数、共现提升度
全部从 ES 取回的样本现算，**没有任何硬编码的结论或常量表**。

设计成不依赖 FastAPI / ES 的纯函数，方便离线自检：
    python -c "from backend.services.insight_stats import pearson; ..."
"""
from __future__ import annotations

import math
from typing import Iterable, Sequence


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def pearson(xs: Iterable[float | None], ys: Iterable[float | None]) -> float | None:
    """Pearson 积差相关（pairwise complete：任一维缺失就丢掉这一对）。

    样本 <3 或任一维方差为 0 时返回 None —— 不返回 0 假装「不相关」。
    """
    pairs = [(float(x), float(y)) for x, y in zip(xs, ys)
             if x is not None and y is not None and math.isfinite(float(x)) and math.isfinite(float(y))]
    n = len(pairs)
    if n < 3:
        return None
    mx = _mean([p[0] for p in pairs])
    my = _mean([p[1] for p in pairs])
    sxy = sum((x - mx) * (y - my) for x, y in pairs)
    sxx = sum((x - mx) ** 2 for x, _ in pairs)
    syy = sum((y - my) ** 2 for _, y in pairs)
    if sxx <= 0 or syy <= 0:
        return None
    return max(-1.0, min(1.0, sxy / math.sqrt(sxx * syy)))


def linear_regression(xs: Iterable[float | None],
                      ys: Iterable[float | None]) -> dict | None:
    """一元最小二乘 y = slope·x + intercept，并给 R²（解释力）。

    R² 用 1 - SSres/SStot 现算，不是把 pearson 平方了事（两者在
    含截距的一元回归里数值相等，但这里保留真实残差计算，口径可解释）。
    """
    pairs = [(float(x), float(y)) for x, y in zip(xs, ys)
             if x is not None and y is not None and math.isfinite(float(x)) and math.isfinite(float(y))]
    n = len(pairs)
    if n < 3:
        return None
    mx = _mean([p[0] for p in pairs])
    my = _mean([p[1] for p in pairs])
    sxx = sum((x - mx) ** 2 for x, _ in pairs)
    if sxx <= 0:
        return None
    slope = sum((x - mx) * (y - my) for x, y in pairs) / sxx
    intercept = my - slope * mx
    ss_res = sum((y - (slope * x + intercept)) ** 2 for x, y in pairs)
    ss_tot = sum((y - my) ** 2 for _, y in pairs)
    r2 = max(0.0, 1 - ss_res / ss_tot) if ss_tot > 0 else 0.0
    return {"slope": slope, "intercept": intercept, "r2": r2, "n": n,
            "x_mean": mx, "y_mean": my}


def quantiles(values: Iterable[float]) -> dict | None:
    """四分位数（线性插值）+ 极值 + 样本数，箱线图/离散度对比用。"""
    vals = sorted(float(v) for v in values if v is not None and math.isfinite(float(v)))
    n = len(vals)
    if n == 0:
        return None

    def q(p: float) -> float:
        pos = (n - 1) * p
        lo, hi = int(math.floor(pos)), int(math.ceil(pos))
        return vals[lo] + (vals[hi] - vals[lo]) * (pos - lo)

    return {"count": n, "min": vals[0], "q1": q(0.25), "median": q(0.5),
            "q3": q(0.75), "max": vals[-1], "iqr": q(0.75) - q(0.25)}


def lift(co_count: int, base_a: int, base_b: int, total: int) -> float | None:
    """共现提升度：P(B|A) / P(B)。

    >1 表示「A 出现时 B 的概率高于总体」，才是知识图谱里值得连的边；
    只按 co_count 排会被高频类型/多产导演刷屏，那不是关系，是基数。
    """
    if base_a <= 0 or base_b <= 0 or total <= 0:
        return None
    return (co_count / base_a) / (base_b / total)
