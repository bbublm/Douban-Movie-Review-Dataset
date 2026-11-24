"""
中文公开影评数据集采集（方案 #5）。

合规红线（与项目总纲一致）：
    · **严禁采集豆瓣（douban）数据**；本项目只用公开、可授权再分发的中文语料
      （CC / 教学许可 / 公开数据集），请确保本地文件来源合规；
    · 不落明文 PII：用户名等只存 sha256 截断哈希（author_hash）。

为什么单独成模块（而不是复用 kaggle_reviews）：
    · 中文影评无空格分词，word_count 必须按 CJK 字计 + 拉丁词计（双语），
      与英文 kaggle 模块默认「按空格分词」不同；
    · 中文数据集列名常是中文（评论 / 情感 / 评分），需要 CJK 友好的列识别；
    · 语言标记固定 zh，直接服务阶段 4 的 en/zh 跨文化对比。

两种数据来源：
    1) 本地文件导入（推荐，沙箱无需联网）：CSV / TSV / JSONL，
       列名自适应识别（text / content / 评论内容 …；sentiment / 情感 / 标签 …）；
    2) Kaggle handle 下载（需 Kaggle 凭证）：给出 --handle 走 kagglehub 通道。

复用：文本清洗 / 情感归一 / 流式读行 直接复用 kaggle_reviews 的成熟实现，
     避免重复造轮子；只在「中文列识别」与「双语词数」上做中文特化。

产物：
    data_lake/interim/reviews.chinese.jsonl   归一化中文影评（transform 自动合并）
"""
from __future__ import annotations

import csv
import hashlib
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

import json

from common.settings import settings
from ingest.schema import fill_review

# 复用 Kaggle 模块的成熟实现（同工程内部模块，私有函数可直接 import）
from ingest.sources.kaggle_reviews import (  # noqa: E402
    ParseResult,
    _read_rows,
    clean_review_text,
    dataset_dir,
    download,
    find_data_files,
    normalize_sentiment,
    review_id,
    sentiment_from_rating,
)

# ============================================================
# 中文友好的列名识别（保留 CJK，支持前缀/后缀）
# ============================================================

TEXT_COL_CANDIDATES = (
    "review", "reviews", "review_text", "text", "content", "comment",
    "评论", "影评", "内容", "正文", "评价", "短评", "影评内容", "评论内容",
)
SENTIMENT_COL_CANDIDATES = (
    "sentiment", "label", "labels", "class", "target", "polarity",
    "情感", "标签", "极性", "分类", "评价倾向",
)
SCORE_COL_CANDIDATES = (
    "score", "rating", "stars", "分数", "评分", "星级", "星",
)
TITLE_COL_CANDIDATES = (
    "movie_title", "moviename", "movie_name", "movie", "film_title", "film",
    "title", "片名", "电影", "影片", "影视",
)
YEAR_COL_CANDIDATES = ("movie_year", "year", "release_year", "released", "年份", "年代")
IMDB_COL_CANDIDATES = ("imdb_id", "imdbid", "tconst")


@dataclass
class ColumnMap:
    header: list[str]
    text: int | None = None
    sentiment: int | None = None
    score: int | None = None
    title: int | None = None
    year: int | None = None
    imdb: int | None = None

    @property
    def ok(self) -> bool:
        return self.text is not None

    def describe(self) -> str:
        def name(i: int | None) -> str:
            return self.header[i] if i is not None else "—"

        roles = (self.text, self.sentiment, self.score, self.title, self.year, self.imdb)
        used = len([x for x in roles if x is not None])
        return (f"正文={name(self.text)}  情感={name(self.sentiment)}  "
                f"评分={name(self.score)}  片名={name(self.title)}  "
                f"共 {len(self.header)} 列（识别出 {used} 个用途）")


def _norm_col(name: str) -> str:
    """列名归一：保留 CJK + 字母数字 + 下划线，转小写、去 BOM/空白。

    与 kaggle 的 _norm_col 不同点：kaggle 版会用正则把 CJK 当非字母数字
    全部清掉，导致中文列名（评论 / 情感）变成空串、识别失败。
    这里显式保留 CJK，让中文数据集也能自适应识别。
    """
    s = (name or "").replace("\ufeff", "").strip().lower()
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", s)


def _match(header_norm: list[str], candidates: tuple[str, ...]) -> int | None:
    """优先精确匹配；再退化为「表头包含候选」（兼容 评论内容/情感标签 这类带后缀的中文列）。"""
    for cand in candidates:
        c = _norm_col(cand)
        if not c:
            continue
        if c in header_norm:
            return header_norm.index(c)
    for cand in candidates:
        c = _norm_col(cand)
        if not c:
            continue
        for i, h in enumerate(header_norm):
            if c and (h == c or c in h or h in c):
                return i
    return None


def detect_columns(header: list[str]) -> ColumnMap:
    hn = [_norm_col(h) for h in header]
    cm = ColumnMap(header=list(header))
    cm.text = _match(hn, TEXT_COL_CANDIDATES)
    cm.sentiment = _match(hn, SENTIMENT_COL_CANDIDATES)
    cm.score = _match(hn, SCORE_COL_CANDIDATES)
    cm.title = _match(hn, TITLE_COL_CANDIDATES)
    cm.year = _match(hn, YEAR_COL_CANDIDATES)
    cm.imdb = _match(hn, IMDB_COL_CANDIDATES)

    # 已用作正文/情感/评分的列不再复用（避免一列多义）
    used = {i for i in (cm.text, cm.sentiment, cm.score) if i is not None}
    for attr in ("title", "year", "imdb"):
        idx = getattr(cm, attr)
        if idx is not None and idx in used:
            setattr(cm, attr, None)
    return cm


# ============================================================
# 双语词数（中文：CJK 按字计 + 拉丁按词计，无 jieba 依赖）
# ============================================================

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")
_LATIN_RE = re.compile(r"[A-Za-z0-9]+")


def word_count(text: str) -> int:
    cjk = len(_CJK_RE.findall(text))
    latin = len(_LATIN_RE.findall(text))
    return cjk + latin


# ============================================================
# 流式解析（复用 kaggle 的 _read_rows 做编码/表头/引号处理）
# ============================================================


def iter_records(
    path: Path,
    *,
    text_col: int | None = None,
    sentiment_col: int | None = None,
    score_col: int | None = None,
    title_col: int | None = None,
    year_col: int | None = None,
    imdb_col: int | None = None,
    limit: int | None = None,
    min_chars: int = 0,
    dedupe: bool = True,
    swap_labels: bool = False,
    lang: str = "zh",
    dataset: str = "",
    result: ParseResult | None = None,
    seen: set[str] | None = None,
    quiet: bool = False,
) -> Iterator[dict]:
    """流式把中文影评数据集解析成统一记录（lang=zh）。

    返回生成器：读一行、清洗一条、yield 一条，调用方立刻写盘；内存恒定。
    """
    result = result or ParseResult()
    rows = _read_rows(path)
    try:
        header = next(rows)
    except StopIteration:
        return
    header = [h.strip().lstrip("\ufeff") for h in header]

    if text_col is None:
        cm = detect_columns(header)
        if not cm.ok:
            if not quiet:
                print(f"    [跳过] {path.name}：认不出正文列（表头 {header[:8]}）")
            return
        text_col, sentiment_col = cm.text, cm.sentiment
        score_col, title_col = cm.score, cm.title
        year_col, imdb_col = cm.year, cm.imdb
        if not quiet:
            print(f"    识别列：{cm.describe()}")

    width_min = max(
        i for i in (text_col, sentiment_col, score_col, title_col, year_col, imdb_col)
        if i is not None
    ) + 1

    seen = seen if seen is not None else set()
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    for idx, row in enumerate(rows):
        result.rows += 1
        if len(row) < width_min:
            result.malformed += 1
            continue

        def cell(i: int | None) -> str | None:
            if i is None or i >= len(row):
                return None
            return row[i]

        raw_text = cell(text_col) or ""
        cleaned = clean_review_text(raw_text)
        if not cleaned:
            result.skipped_empty += 1
            continue
        if min_chars and len(cleaned) < min_chars:
            result.skipped_short += 1
            continue

        rid = review_id(cleaned)
        if dedupe:
            if rid in seen:
                result.skipped_dupe += 1
                continue
            seen.add(rid)

        label, score = normalize_sentiment(cell(sentiment_col), swap=swap_labels)
        rating: float | None = None
        raw_score = cell(score_col)
        if raw_score not in (None, ""):
            try:
                rating = float(str(raw_score).strip())
            except ValueError:
                rating = None
        if label is None and rating is not None:
            label, score = sentiment_from_rating(rating)

        result.sentiment_dist[label or "未标注"] = (
            result.sentiment_dist.get(label or "未标注", 0) + 1
        )
        result.written += 1

        yield {
            "review_id": rid,
            "text": cleaned,
            "text_raw_len": len(str(raw_text)),
            "text_len": len(cleaned),
            "word_count": word_count(cleaned),       # 双语词数（CJK 按字计）
            "sentiment": label,
            "sentiment_score": score,
            "rating": rating,
            "movie_title": (
                clean_review_text(cell(title_col)) or None
            ) if title_col is not None else None,
            "movie_year": _to_int(cell(year_col)) if year_col is not None else None,
            "imdb_id": (cell(imdb_col) or None) if imdb_col is not None else None,
            "lang": lang,
            "dataset": dataset,
            "source": "chinese-dataset",
            "source_file": path.name,
            "row_index": idx,
            "collected_at": now,
        }

        if limit and result.written >= limit:
            return


def _to_int(value: Any) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


# ============================================================
# 演示数据：离线合成中文影评，把解析链路跑通（不联网、不下载）
# ============================================================

DEMO_HEADER = ["评论内容", "情感标签"]
DEMO_ROWS = [
    ["这部电影的镜头语言太惊艳了，节奏紧凑，结尾反转令人震撼。", "正面"],
    ["剧情拖沓，逻辑漏洞百出，看了一半就睡着了。", "负面"],
    ["演员演技在线，但剧本稍显单薄，整体中规中矩。", "中性"],
    ["", "正面"],                                   # 空正文：应跳过
    ["烂片", "负面"],                                # 过短：min_chars 会过滤
    ["画面美不胜收，配乐更是点睛之笔，强烈推荐。", "正面"],
    ["期待越高失望越大，所谓神作不过如此。", "负面"],
]


def build_demo_dataset(directory: str | Path | None = None, *, rows: int = 120) -> Path:
    """造一份极小的合成中文影评 CSV（非真实数据），用于离线跑通链路。

    表头用中文列名，顺便验证 CJK 列识别；合成正文是真实形态的中文短评，
    分词、词数、情感分布等环节表现与真实数据一致。
    """
    directory = Path(directory) if directory else dataset_dir("demo/chinese")
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / "demo_chinese_reviews.csv"

    pos_templates = [
        "导演功力深厚，人物刻画细腻，是一部值得反复品味的佳作。",
        "节奏明快，笑点与泪点都恰到好处，看完意犹未尽。",
        "摄影构图极具美感，配乐与情绪完美贴合，推荐观影。",
    ]
    neg_templates = [
        "剧情散乱，角色动机不明，两个小时像在熬时间。",
        "特效堆砌却毫无灵魂，台词尴尬到让人出戏。",
        "名不副实，所谓口碑不过是营销的功劳。",
    ]
    with target.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(DEMO_HEADER)
        for row in DEMO_ROWS:
            writer.writerow(row)
        for i in range(len(DEMO_ROWS), rows):
            pos = i % 2 == 0
            body = (pos_templates[i % len(pos_templates)] if pos else neg_templates[i % len(neg_templates)])
            writer.writerow([f"{body}（样本 {i}）", "正面" if pos else "负面"])

    (directory / "README_DEMO.txt").write_text(
        "本目录 demo_chinese_reviews.csv 是【合成示例数据】，由 `run_collect chinese --demo` 生成，\n"
        "不是真实的中文影评数据集。仅用于离线跑通采集链路与验证 CJK 列识别。\n"
        "要换成真实数据：执行\n"
        "    python -m ingest.run_collect chinese --dir <本地文件或目录>\n"
        "（严禁使用豆瓣数据；请用公开、可授权再分发的中文语料）\n",
        encoding="utf-8",
    )
    return target


# ============================================================
# 落盘
# ============================================================


def write_jsonl_stream(records: Iterator[dict], path: Path) -> int:
    """流式写 JSONL：来一条写一条（与 kaggle / imdb 模块同一范式）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n += 1
    return n
