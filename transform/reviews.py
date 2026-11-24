"""
影评再清洗 + 与电影弱关联。

★ 阶段 1e 已经洗过一遍了，这里为什么还要再洗？
    1e 做的是「硬清洗」—— 去 HTML、空白归一，那是把脏文本变成干净文本。
    阶段 2 要做的是「一致性 + 可关联」：

        · 用统一的 word_count 口径重算（阶段 4 主题分析按词统计）
        · 丢掉清洗后过短的（清洗前后长度差得离谱，说明原文大半是 HTML 噪声）
        · 跨数据集重复的影评按内容 hash 去重（同一篇影评在不同数据集里各存一份）
        · 按片名与 movies 做**弱关联**，能对上就补 movie_id

★ 弱关联为什么只能靠片名？
    Stanford 影评数据集只有 text + sentiment 两列，没有电影 id。
    所以只能拿 movie_title 去 movies 的标题索引里查 ——
    对不上就是 None。这是数据源本身的限制，不是实现偷懒。
    换用带 movie id 的影评集时，这里改成 id 直连即可，接口不用动。

★ 为什么先查「标题+年份」再查「纯标题」？
    「Crash」1996 与 2004 是同名不同片；影评若带年份，精确匹配才不会张冠李戴。
    没有年份时才退到纯标题，而且**只用那些在片库里唯一的标题** ——
    有歧义的标题（对应多部电影）宁可判为对不上，也不能乱指。
"""
from __future__ import annotations

import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable, Iterator

from ingest.schema import REVIEW_FIELDS
# 复用采集层的两件东西，保证与阶段 1e 的口径一致：
from ingest.sources.kaggle_reviews import clean_review_text, review_id
from transform.clean import to_float, to_int, word_count
from transform.keys import normalize_title

_SENTIMENT_SCORE = {"positive": 1.0, "negative": -1.0, "neutral": 0.0}


# ============================================================
# 标题索引：把影评对回电影
# ============================================================

@dataclass
class TitleIndex:
    """IMDb/TMDB id 与片名 → movie_id 索引。

    exact  (归一化片名, 年份) → movie_id   —— 精确、无歧义
    loose  归一化片名         → movie_id   —— 仅在「该标题在片库里唯一」时才收录
    """

    exact: dict[tuple[str, int], str] = field(default_factory=dict)
    loose: dict[str, str] = field(default_factory=dict)
    imdb: dict[str, str] = field(default_factory=dict)
    tmdb: dict[int, str] = field(default_factory=dict)

    def lookup(
        self, title, year, imdb_id=None, tmdb_id=None
    ) -> tuple[str | None, str]:
        """返回 (movie_id 或 None, 命中方式)。命中方式用于统计关联质量。"""
        imdb = str(imdb_id or "").strip().lower()
        if imdb and imdb in self.imdb:
            return self.imdb[imdb], "imdb_id"
        tmdb = to_int(tmdb_id)
        if tmdb is not None and tmdb in self.tmdb:
            return self.tmdb[tmdb], "tmdb_id"

        t = normalize_title(title)
        if not t:
            return None, "no-title"
        y = to_int(year)
        if y is not None and (t, y) in self.exact:
            return self.exact[(t, y)], "title+year"
        if t in self.loose:
            return self.loose[t], "title"
        return None, "unmatched"


def build_title_index(movies: Iterable[dict]) -> TitleIndex:
    """用融合后的电影列表建标题索引。

    对每部电影，把它的中文名/英文名/原始名**都**登记一遍 ——
    影评数据集里的片名可能是英文，而片库里 title 是中文名，
    不一并登记的话英文影评一条都对不上。
    """
    index = TitleIndex()
    ambiguous: set[str] = set()

    for m in movies:
        mid = m.get("movie_id")
        if not mid:
            continue
        imdb_id = str(m.get("imdb_id") or "").strip().lower()
        if imdb_id:
            index.imdb.setdefault(imdb_id, mid)
        tmdb_id = to_int(m.get("tmdb_id"))
        if tmdb_id is not None:
            index.tmdb.setdefault(tmdb_id, mid)

        titles = {
            normalize_title(m.get("title_zh")),
            normalize_title(m.get("title")),
            normalize_title(m.get("title_en")),
            normalize_title(m.get("original_title")),
        }
        year = to_int(m.get("release_year"))
        for t in titles:
            if not t:
                continue
            if year is not None:
                index.exact.setdefault((t, year), mid)
            if t in index.loose and index.loose[t] != mid:
                # 同一个片名对应了两部不同的电影 → 标记为有歧义，最后剔除
                ambiguous.add(t)
            else:
                index.loose[t] = mid

    for t in ambiguous:
        index.loose.pop(t, None)
    return index


# ============================================================
# 单条处理
# ============================================================

@dataclass
class ReviewStats:
    """影评处理的计数器（等价于采集层的 ParseResult，字段对齐便于对比）。"""

    rows: int = 0
    kept: int = 0
    skipped_empty: int = 0
    skipped_short: int = 0
    skipped_dupe: int = 0
    matched: int = 0
    match_by: Counter = field(default_factory=Counter)
    sentiment: Counter = field(default_factory=Counter)
    lengths: list[int] = field(default_factory=list)

    @property
    def skipped(self) -> int:
        return self.skipped_empty + self.skipped_short + self.skipped_dupe


def process_review(
    record: dict,
    *,
    index: TitleIndex | None = None,
    min_chars: int = 0,
    seen: set[str] | None = None,
    dedupe: bool = True,
) -> tuple[dict | None, str]:
    """处理一条影评。

    返回 (成品记录 或 None, 结果码)。
    结果码 kept / empty / short / dupe —— 调用方据此计数，不用猜。
    """
    raw = record.get("text")
    text = clean_review_text(raw)          # 二次清洗（对已清洗过的文本是幂等的）

    if not text:
        return None, "empty"
    source = str(record.get("source") or "").lower()
    is_douban_source = source in {"douban", "douban_dataset"}
    minimum_chars = min(min_chars, 5) if is_douban_source else min_chars
    if minimum_chars and len(text) < minimum_chars:
        return None, "short"

    external_id = str(record.get("external_id") or record.get("review_id") or "")
    rid = (
        external_id
        if is_douban_source and external_id.startswith("douban:")
        else review_id(text)
    )
    if dedupe and seen is not None:
        if rid in seen:
            return None, "dupe"
        seen.add(rid)

    # 词数：优先沿用采集时算好的（口径一致），缺了才现算
    wc = to_int(record.get("word_count"))
    if wc is None:
        wc = word_count(text)

    sentiment = record.get("sentiment") or None
    score = to_float(record.get("sentiment_score"))
    if score is None and sentiment:
        score = _SENTIMENT_SCORE.get(str(sentiment).lower())

    # ---- 弱关联 ----
    movie_id, how = (None, "no-title")
    if index is not None:
        movie_id, how = index.lookup(
            record.get("movie_title"),
            record.get("movie_year"),
            record.get("imdb_id"),
            record.get("movie_tmdb_id") or record.get("tmdb_id"),
        )

    out = {
        # ---- 主键与正文 ----
        "review_id": rid,
        "text": text,
        "text_raw_len": to_int(record.get("text_raw_len")) or len(str(raw or "")),
        "text_len": len(text),
        "word_count": wc,
        # ---- 情感 ----
        "sentiment": sentiment,
        "sentiment_score": score,
        "rating": to_float(record.get("rating")),
        # ---- 关联 ----
        "movie_id": movie_id,
        "matched_by": how,
        "movie_title": record.get("movie_title"),
        "movie_year": to_int(record.get("movie_year")),
        "imdb_id": record.get("imdb_id"),
        "movie_tmdb_id": record.get("movie_tmdb_id") or record.get("tmdb_id"),
        # ---- 血统 ----
        "lang": record.get("lang"),
        "dataset": record.get("dataset"),
        "source": record.get("source") or "kaggle",
        "source_file": record.get("source_file"),
        "row_index": to_int(record.get("row_index")),
        "collected_at": record.get("collected_at"),
        "douban_id": record.get("douban_id"),
        "douban_sort": (
            record.get("douban_sort") or ("new_score" if source == "douban" else None)
        ),
        "douban_comment_time": record.get("douban_comment_time"),
        "review_time": record.get("review_time"),
        "transformed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }

    # 补齐合同字段：缺的一律 None，不留 key 空档（否则 ES 批量导入会列错位）
    for f in REVIEW_FIELDS:
        out.setdefault(f, None)

    return out, "kept"


def iter_clean_reviews(
    records: Iterable[dict],
    *,
    index: TitleIndex | None = None,
    min_chars: int = 0,
    dedupe: bool = True,
    stats: ReviewStats | None = None,
) -> Iterator[dict]:
    """流式处理影评：读一条、出一条，不把结果攒成 list。

    统计对象由调用方传入 —— 生成器被消费完之后 stats 才有完整数据，
    这个约定写在签名里，比「返回一个带 stats 的包装对象」更省事也更好测。
    """
    stats = stats if stats is not None else ReviewStats()
    seen: set[str] = set()

    for rec in records:
        stats.rows += 1
        out, code = process_review(
            rec, index=index, min_chars=min_chars, seen=seen, dedupe=dedupe
        )
        if out is None:
            if code == "empty":
                stats.skipped_empty += 1
            elif code == "short":
                stats.skipped_short += 1
            else:
                stats.skipped_dupe += 1
            continue

        stats.kept += 1
        if out["movie_id"]:
            stats.matched += 1
        stats.match_by[out["matched_by"]] += 1
        if out["sentiment"]:
            stats.sentiment[str(out["sentiment"])] += 1
        stats.lengths.append(out["text_len"])
        yield out
