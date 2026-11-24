"""
Kaggle 公开影评数据集采集器 —— 阶段 1e。

数据源：Kaggle 上的公开影评数据集（通过 kagglehub 下载）。
本项目的默认数据集是 Stanford Large Movie Review Dataset 的 Kaggle 镜像：
    lakshmi25npathi/imdb-dataset-of-50k-movie-reviews
    50,000 条 IMDb 影评 + 二分类情感标注（positive / negative），约 66 MB。
    它是情感分析领域最常用的公开基准，许可为 CC0 / 公开可再分发。

★ 为什么不用需求里给的那行代码（kunwarakash/imdbdatasets）？
    那个数据集**不是影评**，它是 IMDb 官方 TSV 数据集（title.basics.tsv 那一套）
    的第三方镜像，5.7 GB，描述里写得很清楚「Daily refreshed Dataset can
    downloaded from https://datasets.imdbws.com/」。
    它和阶段 1b（IMDb Datasets）拿的是同一份数据，却要多下 5.7 GB，
    而且里面**没有任何评论文本** —— 阶段 4 的情感分析与主题分析会直接断粮。
    仍然保留了它的登记项（见 KNOWN_DATASETS），执行 `kaggle --list` 能看到对比说明。

=============================================================================
★ 内存纪律（延续阶段 1b 的约束，用户明确在意内存）
=============================================================================
    66 MB 的 CSV，常见写法 `pd.read_csv(...)` 峰值内存要 400 MB 以上
    （pandas 会把 5 万个长字符串全驻留，还要额外做 dtype 推断）。
    本模块改用 csv.reader 逐行流式解析：
        - 读一行 → 清洗 → 归一化 → 立刻 yield → 调用方立刻写盘；
        - 从不把 5 万条记录攒成 list；
        - 唯一随数据量增长的是「已见 review_id 集合」（去重用），
          约 100 字节/条，5 万条约 6 MB —— 且可以用 --no-dedupe 关掉。
    实测峰值内存见命令输出末尾那行「峰值内存」。

=============================================================================
★ 这个数据集的一个硬限制（必须知道，别到阶段 3 才发现）
=============================================================================
    它**只有 review + sentiment 两列，没有片名、没有电影 id**。
    所以影评记录里的 movie_title / imdb_id 只能是 None，
    reviews 索引与 movies 索引之间**无法直接 JOIN**。
    这对本平台的定位没有致命影响：
        检索侧 —— 影评作为一个独立索引参与「混合检索」（按正文全文检索 + 情感筛选）；
        分析侧 —— 它是阶段 4 情感分析 / 主题分析的核心语料。
    如果以后想要「影评挂到具体电影下」，换用带片名列的数据集即可 ——
    本模块的列名识别是自适应的（TEXT/TITLE/SENTIMENT 候选表），
    数据集里只要有片名列，movie_title 就会自动填上，不用改代码。

产物：
    data_lake/kaggle_reviews/<handle 转义>/        数据集原始文件（含 .complete 标记）
    data_lake/interim/reviews.jsonl               归一化后的影评记录
"""
from __future__ import annotations

import csv
import os
import hashlib
import html
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from common.settings import PROJECT_ROOT, settings

# ============================================================
# 数据集登记表
# ============================================================


@dataclass(frozen=True)
class ReviewDatasetSpec:
    key: str
    handle: str          # Kaggle handle（owner/dataset）
    size_mb: int
    note: str
    column_hint: str = ""       # 已知列结构（有的话直接写死，省一次探测）
    has_movie_title: bool = False   # 是否含片名列（决定能否关联 movies 索引）

    @property
    def url(self) -> str:
        return f"https://www.kaggle.com/datasets/{self.handle}"


KNOWN_DATASETS: dict[str, ReviewDatasetSpec] = {
    "imdb50k": ReviewDatasetSpec(
        key="imdb50k",
        handle="lakshmi25npathi/imdb-dataset-of-50k-movie-reviews",
        size_mb=66,
        note="★ 本项目默认：5 万条 IMDb 影评 + 情感二分类（情感/主题分析的语料来源）",
        column_hint="review, sentiment",
    ),
    "rotten": ReviewDatasetSpec(
        key="rotten",
        handle="paweljankowiak/rotten-tomatoes-movies-and-critic-reviews",
        size_mb=210,
        note="烂番茄影评：**带片名**，可与 movies 索引做弱关联（可选）",
        has_movie_title=True,
    ),
    "imdb_mirror": ReviewDatasetSpec(
        key="imdb_mirror",
        handle="kunwarakash/imdbdatasets",
        size_mb=5460,
        note="⚠ 不是影评！是 IMDb 官方 TSV 数据集的镜像，"
             "与阶段 1b 重复且大 27 倍，无评论文本 —— 别用它做影评分析",
    ),
}

DEFAULT_DATASET_KEY = "imdb50k"

# ============================================================
# 列名自适应识别
# ============================================================
# Kaggle 上的影评数据集列名五花八门（review / text / content / comment ...），
# 硬编码列名等于把模块锁死在一个数据集上。这里用候选表 + 优先级匹配，
# 换数据集大概率不用改代码；实在识别不出来时，CLI 还能用 --text-col 手动指定。

TEXT_COL_CANDIDATES = (
    "review", "reviews", "review_text", "text", "content", "comment",
    "comments", "body", "sentence", "full_text", "reviewbody", "critic_review",
)
SENTIMENT_COL_CANDIDATES = (
    "sentiment", "label", "labels", "class", "target", "polarity", "emotion",
    "sentiment_label",
)
SCORE_COL_CANDIDATES = (
    "score", "rating", "stars", "polarity_score", "sentiment_score", "vote",
)
TITLE_COL_CANDIDATES = (
    "movie_title", "moviename", "movie_name", "movie", "film_title", "film",
    "title",
)
YEAR_COL_CANDIDATES = ("movie_year", "year", "release_year", "released")
IMDB_COL_CANDIDATES = ("imdb_id", "imdbid", "tconst")


@dataclass
class ColumnMap:
    """识别出来的「哪一列是什么」的映射。"""

    header: list[str]
    text: int | None = None
    sentiment: int | None = None
    score: int | None = None
    title: int | None = None
    year: int | None = None
    imdb: int | None = None
    extra: dict[str, int] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        # 只要认出了正文列就算可用 —— 情感列缺失的数据集（纯文本语料）也能收
        return self.text is not None

    def describe(self) -> str:
        def name(idx: int | None) -> str:
            return f"{self.header[idx]}" if idx is not None else "—"

        roles = (self.text, self.sentiment, self.score, self.title, self.year, self.imdb)
        used = len([i for i in roles if i is not None])
        return (
            f"正文={name(self.text)}  情感={name(self.sentiment)}  "
            f"评分={name(self.score)}  片名={name(self.title)}  "
            f"共 {len(self.header)} 列（识别出 {used} 个用途）"
        )


def _norm_col(name: str) -> str:
    """列名归一化：去掉 BOM / 空格 / 分隔符，转小写，便于模糊匹配。

    为什么要显式处理 \\ufeff？
        Kaggle 导出的 CSV 常带 UTF-8 BOM。用 utf-8-sig 打开时 BOM 会被吃掉，
        但如果文件是从别的编码兜底打开的（latin-1 分支），BOM 会残留成
        一个不可见字符挂在第一个列名前面 —— `\\ufeffreview` 匹配不上 `review`，
        结果整个数据集会因为「认不出正文列」被跳过，而且看不出原因。
        （这是自检里抓出来的：`str.strip()` 并不认为 \\ufeff 是空白。）
    """
    s = (name or "").replace("\ufeff", "").strip().lower()
    return re.sub(r"[\s_\-\.]+", "", s)


def _match(header_norm: list[str], candidates: tuple[str, ...]) -> int | None:
    """按候选表顺序找第一个命中的列（候选表本身有序 = 优先级）。"""
    for cand in candidates:
        c = _norm_col(cand)
        if c in header_norm:
            return header_norm.index(c)
    return None


def detect_columns(header: list[str]) -> ColumnMap:
    """从表头推断各列语义。

    顺序有讲究：先定正文列，再从**剩下的**列里找情感/评分列，
    避免把一列同时当成两种用途（有的数据集列名叫 `label`，
    既可能被情感候选表命中，也可能被评分候选表命中）。
    """
    hn = [_norm_col(h) for h in header]
    cm = ColumnMap(header=list(header))

    cm.text = _match(hn, TEXT_COL_CANDIDATES)
    cm.sentiment = _match(hn, SENTIMENT_COL_CANDIDATES)
    cm.score = _match(hn, SCORE_COL_CANDIDATES)
    cm.title = _match(hn, TITLE_COL_CANDIDATES)
    cm.year = _match(hn, YEAR_COL_CANDIDATES)
    cm.imdb = _match(hn, IMDB_COL_CANDIDATES)

    # 已经用作正文/情感/评分的列不再复用
    used = {i for i in (cm.text, cm.sentiment, cm.score) if i is not None}
    for attr in ("title", "year", "imdb"):
        idx = getattr(cm, attr)
        if idx is not None and idx in used:
            setattr(cm, attr, None)
        elif idx is not None:
            used.add(idx)

    # 片名列的防误判：如果列名叫 title 但同时存在更明确的正文列，
    # 那 title 很可能是「评论标题」而不是「电影名」（很多数据集这么设计）。
    # 这种情况下不把它当片名，避免污染 movie_title。
    if cm.title is not None and hn[cm.title] == "title" and cm.text is not None:
        cm.extra["comment_title"] = cm.title
        cm.title = None

    return cm


# ============================================================
# 文本清洗
# ============================================================

# 真实数据里最常见的脏东西就这三样（这是拿到 66 MB 真实 CSV 之后实测出来的）：
#   1. <br /><br />   —— 段落分隔，占了绝大多数噪声
#   2. &quot; &amp;     —— HTML 实体
#   3. 连续空白/换行   —— 影响分词与长度统计
_TAG_RE = re.compile(r"<[^>]{1,200}>")
_WS_RE = re.compile(r"\s+")


def clean_review_text(raw: Any) -> str:
    """HTML 实体解码 + 去标签 + 空白归一。

    顺序很关键：**先 unescape 再 strip tags**。
    如果反过来，`&lt;br /&gt;` 这种被转义过的标签会躲过标签正则，
    留在正文里变成 "<br />" 字面量 —— 分词时会多出一堆 "br" 词项。
    """
    if raw is None:
        return ""
    s = html.unescape(str(raw))
    s = s.replace("\u00a0", " ")          # 不换行空格
    s = s.replace("\u200b", "")           # 零宽空格
    s = _TAG_RE.sub(" ", s)
    s = _WS_RE.sub(" ", s)
    return s.strip()


def review_id(text: str) -> str:
    """用正文 hash 生成稳定主键 `r<16 位十六进制>`。

    为什么不用行号？
        行号主键在「数据集更新、行序变化、加过滤条件」时会全量错位，
        而且重复导入会产生重复文档。
        内容 hash 则天然幂等 —— 同一篇影评无论跑多少次都是同一个 _id，
        写进 ES 时直接覆盖，不会翻倍。
    """
    return "r" + hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


# ============================================================
# 情感归一化
# ============================================================

_POS_WORDS = {"positive", "pos", "p", "good", "正面", "好评", "积极", "推荐", "1"}
_NEG_WORDS = {"negative", "neg", "n", "bad", "负面", "差评", "消极", "不推荐", "0"}
_NEU_WORDS = {"neutral", "neu", "中性", "中评", "mixed"}

# ⚠️ 已知歧义：数值标签 1/0 在不同数据集里语义可能相反
#    （多数约定 1=positive，也有 0=positive 的）。
#    本模块采用「1=positive」这一更常见的约定，
#    但采集结束会打印情感分布 —— 如果分布严重失衡（例如 99% negative），
#    那就是映射反了，用 --swap-labels 翻转一次即可。
_NUM_TO_LABEL = {"1": "positive", "0": "negative", "2": "positive", "4": "positive"}

# 评分制（如 1~10 分）→ 情感标签的阈值
RATING_POS_THRESHOLD = 7.0
RATING_NEG_THRESHOLD = 4.0


def normalize_sentiment(
    value: Any,
    *,
    swap: bool = False,
) -> tuple[str | None, float | None]:
    """把五花八门的情感标注统一成 (sentiment, sentiment_score)。

    sentiment ∈ {positive, negative, neutral, None}
    sentiment_score ∈ {+1.0, -1.0, 0.0, None}
    """
    if value is None:
        return None, None
    raw = str(value).strip().lower()
    if not raw:
        return None, None

    label = _NUM_TO_LABEL.get(raw, raw)
    if swap:
        label = {"positive": "negative", "negative": "positive"}.get(label, label)

    if label in _POS_WORDS:
        return "positive", 1.0
    if label in _NEG_WORDS:
        return "negative", -1.0
    if label in _NEU_WORDS:
        return "neutral", 0.0
    return None, None


def sentiment_from_rating(rating: float | None) -> tuple[str | None, float | None]:
    """评分制 → 情感。10 分制下 ≥7 正向、≤4 负向，中间算中性。

    score 做线性映射到 [-1, 1]，让「评分制」和「标签制」两个数据集
    能放进同一个字段做聚合（比如算全库平均情感倾向）。
    """
    if rating is None:
        return None, None
    if rating >= RATING_POS_THRESHOLD:
        label = "positive"
    elif rating <= RATING_NEG_THRESHOLD:
        label = "negative"
    else:
        label = "neutral"
    # 以 5.5 分为中性点，4.5 分跨度映射到 ±1
    score = max(-1.0, min(1.0, (rating - 5.5) / 4.5))
    return label, round(score, 3)


# ============================================================
# 文件定位与下载
# ============================================================


def safe_dirname(handle: str) -> str:
    """`owner/name` → `owner__name`（handle 里的斜杠不能当目录名）。"""
    return handle.replace("/", "__")


def dataset_dir(handle: str = "", override: str | Path | None = None) -> Path:
    """数据集存放目录。

    刻意不走 kagglehub 的默认缓存（~/.cache/kagglehub）：
    那份缓存用户看不见、也不好清理；统一落在 data_lake 下，
    「磁盘上占了多少」一眼可查，删掉也安心。
    """
    if override:
        p = Path(override)
        return p if p.is_absolute() else (PROJECT_ROOT / p).resolve()
    if settings.kaggle_dataset_dir.strip():
        p = Path(settings.kaggle_dataset_dir.strip())
        return p if p.is_absolute() else (PROJECT_ROOT / p).resolve()
    handle = handle or KNOWN_DATASETS[DEFAULT_DATASET_KEY].handle
    return settings.lake("kaggle_reviews", safe_dirname(handle))


# 这些后缀才是「数据文件」；其余（.complete、.zip、.7z、README）都跳过
DATA_SUFFIXES = {".csv", ".tsv", ".jsonl", ".json", ".txt", ".gz"}


def find_data_files(directory: Path, *, max_depth: int = 3) -> list[Path]:
    """在数据集目录里找可解析的数据文件，按体积从大到小排序。

    跳过 kagglehub 自己写的 `.complete/` 标记目录与归档包 ——
    否则会试图去解析一个 zip，白白浪费一次 IO。
    """
    if not directory.exists():
        return []
    found: list[Path] = []
    for p in directory.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(directory)
        if len(rel.parts) > max_depth + 1:
            continue
        if ".complete" in rel.parts:
            continue
        if p.suffix.lower() in {".zip", ".7z", ".rar", ".tar"}:
            continue
        if p.name.startswith(("README", "readme")):
            continue
        if p.suffix.lower() in DATA_SUFFIXES:
            found.append(p)
    found.sort(key=lambda p: -p.stat().st_size)
    return found


def download(
    handle: str,
    *,
    directory: Path | None = None,
    force: bool = False,
    progress: bool = True,
) -> Path:
    """用 kagglehub 下载数据集到指定目录，返回目录路径。

    跟其他采集源不同，这里不自己写 HTTP 客户端 —— kagglehub 已经把
    认证（~/.kaggle/kaggle.json 或 KAGGLE_USERNAME/KAGGLE_KEY）、
    断点续传、校验、解压都处理好了，自己再写一遍是纯浪费。
    公开数据集**可以匿名下载**，没有凭证也能跑通（实测过）。
    """
    directory = directory or dataset_dir(handle)
    directory.mkdir(parents=True, exist_ok=True)
    marker = directory / ".complete"

    if marker.exists() and not force:
        if progress:
            size = sum(f.stat().st_size for f in directory.rglob("*") if f.is_file())
            print(f"  [跳过] 已下载过（{size / 1024 / 1024:.1f} MB）：{directory}")
        return directory

    try:
        import kagglehub
    except ImportError:  # pragma: no cover - 依赖缺失时改用标准库直连
        return _download_stdlib(handle, directory, force=force, progress=progress)

    if progress:
        print(f"  [下载] {handle}  →  {directory}")
        print("         首次下载约需 1~2 分钟（公开数据集可匿名下载）")
    try:
        kagglehub.dataset_download(handle, force_download=force, output_dir=str(directory))
    except Exception as exc:  # kagglehub 的异常类型跨版本会变，统一兜住给可读提示
        raise RuntimeError(
            f"下载 {handle} 失败：{type(exc).__name__}: {exc}\n"
            "  常见原因与处理：\n"
            "    1) 网络不通 —— 换网络或加代理（kagglehub 读 HTTPS_PROXY 环境变量）\n"
            "    2) 该数据集需要登录 —— 去 kaggle.com 账号设置里 Create New Token，\n"
            "       把 kaggle.json 放到 %USERPROFILE%\\.kaggle\\ 下，或设置环境变量\n"
            "       KAGGLE_USERNAME / KAGGLE_KEY\n"
            "    3) 干脆手动下载后解压，再用 --dir 指定目录：\n"
            f"       {KNOWN_DATASETS.get(_key_of(handle), ReviewDatasetSpec('', handle, 0, '')).url}"
        ) from exc

    if progress:
        files = find_data_files(directory)
        total = sum(f.stat().st_size for f in files)
        print(f"         完成：{len(files)} 个数据文件，共 {total / 1024 / 1024:.1f} MB")
    return directory


def _key_of(handle: str) -> str:
    for key, spec in KNOWN_DATASETS.items():
        if spec.handle == handle:
            return key
    return ""


# ============================================================
# 凭证解析（stdlib 降级路径用，kagglehub 不可用时）
# ============================================================
def resolve_credentials() -> tuple[str, str]:
    """按优先级取 Kaggle 凭证：(username, key)。

    优先级：settings(.env) > ~/.kaggle/kaggle.json > 环境变量。
    都拿不到就返回 ("", "")，由下载函数决定是否匿名（公开数据集可匿名）。
    """
    uname, key = settings.kaggle_username.strip(), settings.kaggle_key.strip()
    if uname and key:
        return uname, key
    # ~/.kaggle/kaggle.json
    cfg = Path.home() / ".kaggle" / "kaggle.json"
    if cfg.exists():
        try:
            data = json.loads(cfg.read_text(encoding="utf-8"))
            uname = data.get("username", "").strip()
            key = data.get("key", "").strip()
            if uname and key:
                return uname, key
        except (json.JSONDecodeError, OSError):
            pass
    # 环境变量
    uname = os.environ.get("KAGGLE_USERNAME", "").strip()
    key = os.environ.get("KAGGLE_KEY", "").strip()
    return uname, key


def _download_stdlib(
    handle: str,
    directory: Path,
    *,
    force: bool = False,
    progress: bool = True,
) -> Path:
    """无 kagglehub 时用标准库直接走 Kaggle REST API 下载数据集 zip。

    端点：GET https://www.kaggle.com/api/v1/datasets/download/{owner}/{dataset}
    - HTTP Basic Auth（username:key）—— 凭证缺失时也能试匿名（公开数据集）。
    - 该端点返回 302 跳到 CDN 上的 zip，urllib 默认跟随重定向。
    - 流式写盘，不把 66 MB 全读进内存。
    """
    import base64
    import urllib.request
    import zipfile

    directory.mkdir(parents=True, exist_ok=True)
    marker = directory / ".complete"
    if marker.exists() and not force:
        if progress:
            size = sum(f.stat().st_size for f in directory.rglob("*") if f.is_file())
            print(f"  [跳过] 已下载过（{size / 1024 / 1024:.1f} MB）：{directory}")
        return directory

    url = f"https://www.kaggle.com/api/v1/datasets/download/{handle}"
    uname, key = resolve_credentials()
    headers = {"User-Agent": "kaggle/1.0 (电影盒子 ingest)"}
    if uname and key:
        token = base64.b64encode(f"{uname}:{key}".encode("utf-8")).decode("ascii")
        headers["Authorization"] = f"Basic {token}"

    if progress:
        auth_note = f"（账号 {uname}）" if uname else "（匿名）"
        print(f"  [下载] {handle}  →  {directory} {auth_note}")

    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=120) as resp:
            # 取文件名（Content-Disposition 优先，否则按 handle 命名）
            cd = resp.headers.get("Content-Disposition", "")
            fname = None
            if "filename=" in cd:
                fname = cd.split("filename=")[-1].strip().strip('"')
            if not fname or not fname.lower().endswith(".zip"):
                fname = safe_dirname(handle) + ".zip"
            zip_path = directory / fname

            total = int(resp.headers.get("Content-Length", "0") or "0")
            written = 0
            last_print = 0.0
            with zip_path.open("wb") as out:
                while True:
                    chunk = resp.read(1 << 20)  # 1 MB 一块
                    if not chunk:
                        break
                    out.write(chunk)
                    written += len(chunk)
                    if progress and total:
                        pct = written / total * 100
                        now = time.time()
                        if now - last_print > 1.0 or written == total:
                            print(f"           {pct:5.1f}%  {written / 1024 / 1024:.1f}/{total / 1024 / 1024:.1f} MB")
                            last_print = now
            if progress:
                print(f"          完成下载：{zip_path.name}（{written / 1024 / 1024:.1f} MB）")

            # 解压（保留目录结构，跳过已存在的同名文件）
            with zipfile.ZipFile(zip_path) as zf:
                zf.extractall(directory)
            if progress:
                files = find_data_files(directory)
                tot = sum(f.stat().st_size for f in files)
                print(f"          解压完成：{len(files)} 个数据文件，共 {tot / 1024 / 1024:.1f} MB")
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", "replace")[:300]
        except Exception:
            pass
        raise RuntimeError(
            f"下载 {handle} 失败：HTTP {e.code}\n"
            f"  Kaggle 返回：{body}\n"
            "  常见原因：\n"
            "    1) 凭证无效/缺失 —— 检查 .env 的 KAGGLE_USERNAME/KAGGLE_KEY 或 ~/.kaggle/kaggle.json\n"
            "    2) 该数据集需先「Accept Competition Rules」或登录后才能下\n"
            "    3) 网络被拦 —— 设置 HTTPS_PROXY 环境变量"
        ) from e
    except urllib.error.URLError as e:
        raise RuntimeError(
            f"下载 {handle} 失败：网络不可达（{e.reason}）\n"
            "  设置 HTTPS_PROXY 环境变量后重试。"
        ) from e

    return directory


# ============================================================
# 流式解析
# ============================================================

# 文本列的探测行数：读前 N 行来判断「这一列是不是正文」，
# 不预读全文件（预读要多扫一遍 66 MB）
SNIFF_ROWS = 200


@dataclass
class ParseResult:
    """解析统计，用于最后的汇总输出。"""

    rows: int = 0            # 扫过的原始行数
    written: int = 0         # 写出的记录数
    skipped_short: int = 0   # 因正文过短被跳过
    skipped_dupe: int = 0    # 因内容重复被跳过
    skipped_empty: int = 0   # 正文清洗后为空
    malformed: int = 0       # 列数对不上的残缺行
    sentiment_dist: dict[str, int] = field(default_factory=dict)
    charset_fixed: int = 0   # 编码兜底修复的行数


def _read_rows(path: Path) -> Iterator[list[str]]:
    """逐行读 CSV / TSV（流式），自动处理编码与表头。

    两个容易被忽略的点：
        1. 编码：Kaggle 数据集常带 BOM，用 utf-8-sig 读；
           个别文件不是 UTF-8，兜底 latin-1（总比整个任务崩掉好）；
        2. 影评正文里**含换行和引号**，必须交给 csv 模块处理 ——
           `for line in fh: line.split(",")` 这种写法遇到多行字段会直接错位。
    """
    opener = csv.reader
    delimiter = "\t" if path.suffix.lower() == ".tsv" else ","

    for encoding in ("utf-8-sig", "latin-1"):
        try:
            with path.open(encoding=encoding, newline="") as fh:
                reader = opener(fh, delimiter=delimiter, quotechar='"')
                for row in reader:
                    yield row
            return
        except UnicodeDecodeError:
            # 换编码重来：前面已 yield 的行会被上层去重逻辑吃住（hash 幂等）
            continue
        except csv.Error:
            # csv 模块对畸形引号会抛错；跳过该文件由调用方统计
            return


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
    lang: str = "en",
    dataset: str = "",
    result: ParseResult | None = None,
    seen: set[str] | None = None,
    quiet: bool = False,
) -> Iterator[dict]:
    """流式把影评数据集解析成统一记录。

    返回生成器：读一行、清洗一条、yield 一条，调用方立刻写盘。
    整个过程只在内存里保留「当前这一条」+ 去重用的 hash 集合。

    seen 可以从外部传入，这样多个文件之间也能共享去重（同一篇影评
    在两个文件里出现时不会被写两次）。
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

        # ---- 情感：标签优先，没有标签就用评分推 ----
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
            # ---- 主键 ----
            "review_id": rid,
            # ---- 正文 ----
            "text": cleaned,
            "text_raw_len": len(str(raw_text)),
            "text_len": len(cleaned),
            "word_count": len(cleaned.split()),
            # ---- 情感 ----
            "sentiment": label,
            "sentiment_score": score,
            "rating": rating,
            # ---- 电影关联（本数据集没有，留 None 而不是省字段）----
            "movie_title": (clean_review_text(cell(title_col)) or None) if title_col is not None else None,
            "movie_year": _to_int(cell(year_col)) if year_col is not None else None,
            "imdb_id": (cell(imdb_col) or None) if imdb_col is not None else None,
            # ---- 血缘 ----
            "lang": lang,
            "dataset": dataset,
            "source": "kaggle",
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
# 演示数据：不下载 66 MB 也能把链路跑通
# ============================================================

DEMO_HEADER = ["review", "sentiment"]
# 前 10 行是刻意埋的边界样本，覆盖真实数据里会遇到的坑
DEMO_ROWS = [
    ["A wonderful little production. <br /><br />The filming technique is very unassuming.", "positive"],
    ["Basically there's a family where a little boy is afraid of everything.", "negative"],
    ["Terrible movie. &quot;Worst&quot; acting I have ever seen. &amp; I want my money back.", "negative"],
    ["This film has a <b>brilliant</b> script and the acting is superb.", "POSITIVE"],
    ["A decent enough way to spend two hours, nothing more.", "neutral"],
    ["", "positive"],                                   # 空正文：应跳过
    ["   \n  \t ", "negative"],                          # 纯空白：应跳过
    ["ok", "positive"],                                  # 过短：min_chars 会过滤
    ["Great movie"],                                     # 缺列：malformed
    ["Repeated review text that appears twice in the file.", "positive"],  # 与下一行重复
    ["Repeated review text that appears twice in the file.", "positive"],
]


def build_demo_dataset(directory: str | Path | None = None, *, rows: int = 300) -> Path:
    """造一份极小的合成影评 CSV（非真实数据），用于离线跑通链路。

    合成正文里带 "DEMO" 前缀的没有 —— 保持英文语料形态，
    这样分词、词数统计、情感分布这些环节的表现与真实数据一致。
    """
    directory = Path(directory) if directory else dataset_dir("demo/offline")
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / "demo_reviews.csv"

    with target.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(DEMO_HEADER)
        for row in DEMO_ROWS:
            writer.writerow(row)
        for i in range(11, rows):
            pos = i % 3 != 0
            body = (
                f"I watched this film on a rainy afternoon and it turned out to be "
                f"one of the better ones I have seen this year, entry number {i}."
                if pos else
                f"Sadly the plot made no sense at all and I fell asleep twice, "
                f"cannot recommend it to anyone, entry number {i}."
            )
            writer.writerow([body, "positive" if pos else "negative"])

    (directory / "README_DEMO.txt").write_text(
        "本目录中的 demo_reviews.csv 是【合成示例数据】，由 `run_collect kaggle --demo` 生成，\n"
        "不是真实的影评数据集。仅用于离线跑通采集链路与验证内存占用。\n"
        "要换成真实数据：执行\n"
        "    python -m ingest.run_collect kaggle\n",
        encoding="utf-8",
    )
    return target


# ============================================================
# 落盘
# ============================================================


def write_jsonl_stream(records: Iterator[dict], path: Path) -> int:
    """流式写 JSONL：来一条写一条（与 imdb 模块同一范式）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n += 1
    return n


def header_of(path: Path) -> list[str]:
    """只读第一行拿表头（用于 --text-col 手动指定列）。"""
    for encoding in ("utf-8-sig", "latin-1"):
        try:
            with path.open(encoding=encoding, newline="") as fh:
                row = next(csv.reader(fh, delimiter="\t" if path.suffix.lower() == ".tsv" else ","))
            return [h.strip().lstrip("\ufeff") for h in row]
        except (UnicodeDecodeError, StopIteration):
            continue
    return []


def column_index(path: Path, name: str) -> int | None:
    """按列名（忽略大小写/下划线）找列号，找不到返回 None。"""
    if not name:
        return None
    hn = [_norm_col(h) for h in header_of(path)]
    target = _norm_col(name)
    return hn.index(target) if target in hn else None


def list_datasets() -> None:
    """打印数据集清单（对应 CLI 的 --list）。"""
    print("  Kaggle 公开影评数据集（https://www.kaggle.com/datasets）\n")
    print(f"  {'key':<12}{'体积':>9}  {'handle':<56}说明")
    print("  " + "-" * 128)
    for spec in KNOWN_DATASETS.values():
        mark = " ★默认" if spec.key == DEFAULT_DATASET_KEY else ""
        print(f"  {spec.key:<12}{spec.size_mb:>6} MB  {spec.handle:<56}{spec.note}{mark}")
    print("\n  用法：python -m ingest.run_collect kaggle [--dataset imdb50k]")
    print("        也可以直接给任意 handle：--handle owner/dataset-name")
    print("\n  说明：")
    print("    · 公开数据集可匿名下载，无需 Kaggle 账号；")
    print("    · 原始文件落在 data_lake/kaggle_reviews/<handle> 下，不用 kagglehub 的隐藏缓存；")
    print("    · 解析全程流式，峰值内存与数据集行数无关。\n")
