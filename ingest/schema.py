"""
统一电影记录 schema —— 多源融合的「合同」。

三个数据源（旧片库 legacy / TMDB / IMDb Datasets）各自归一化后，
字段名必须完全对齐，否则阶段 2 的融合逻辑就要为每个源写一套分支。

所以这里把「一部电影至少要有哪些字段」定成一个常量：
    - ingest/sources/tmdb.py 的 normalize_movie()    必须覆盖
    - ingest/seed.py 的 normalize_legacy()           必须覆盖
    - ingest/sources/imdb_datasets.py 的 normalize() 必须覆盖
三个模块都遵守 CORE_FIELDS，测试里有一条断言专门守护这件事 ——
以后谁改了某一个源却忘了同步，自检会立刻报错。

注意：CORE_FIELDS 只规定「字段名」，不规定「值必须非空」。
IMDb 数据没有中文名、没有海报，那就填 None，而不是把字段省掉。
留空与缺字段是两件事：前者可以参与合并，后者会导致 DataFrame 列错位。
"""
from __future__ import annotations

# 统一电影记录的核心字段（顺序即建议的落盘顺序，便于人工比对）
CORE_FIELDS: tuple[str, ...] = (
    # ---- 主键与实体对齐 ----
    "tmdb_id",          # TMDB 数字 id，跨源对齐的主键之一
    "imdb_id",          # IMDb tconst，如 tt0137523
    # ---- 片名 ----
    "title",            # 展示用片名（优先中文）
    "title_zh",         # 中文片名，可能为 None
    "title_en",         # 英文/原始片名
    "original_title",   # 出品国原始片名
    # ---- 时间与时长 ----
    "release_date",     # 精确到日，形如 1999-10-15，缺失为 None
    "release_year",     # 整数年份
    "runtime",          # 片长（分钟）
    # ---- 文本 ----
    "overview",         # 剧情简介
    "tagline",          # 宣传语
    "status",           # 上映状态
    # ---- 分类与人物 ----
    "genres_zh",        # 中文类型列表，用于分面筛选
    "genre_ids",        # TMDB 类型 id（其他源为空列表）
    "keywords",         # 关键词
    "director",         # 导演（多个用顿号连接）
    "cast",             # 主演列表
    # ---- 评分与热度 ----
    "vote_average",     # 平均分（10 分制，各源统一到同一量纲）
    "vote_count",       # 评分人数
    "popularity",       # 热度
    # ---- 票房与预算（票房分析展厅用；TMDB 单位为美元，缺为 None）----
    "revenue",          # 全球票房（美元）
    "budget",           # 制作预算（美元）
    # ---- 地域与语言（足迹地图要用）----
    "original_language",
    "spoken_languages",
    "production_countries",
    "production_country_codes",
    # ---- 图片 ----
    "poster_url",
    "backdrop_url",
    # ---- 数据血缘 ----
    "source",           # tmdb / legacy / imdb / imdb+tmdb …
    "collected_at",     # 采集时间戳（UTC）
)


# ============================================================
# 影评记录的「合同」（阶段 1e）
# ============================================================
# 为什么影评要单独一套字段，而不是塞进 CORE_FIELDS？
#     一部电影对应 1 条记录，一篇影评对应 1 条记录 —— 这是两个不同粒度的事实，
#     混在一张表里就会出现「电影字段大量重复 + 影评字段大量为空」的稀疏表。
#     阶段 2 建 ES 时它们分别是 movies / reviews 两个索引，各用各的 mapping。
#
# 与电影记录同样的约定：只规定字段名，不要求值非空。缺就填 None。
REVIEW_FIELDS: tuple[str, ...] = (
    # ---- 主键 ----
    # 用「清洗后正文」的 hash 做稳定 id：
    # 同一个数据集重复导入不会产生重复文档（ES 用 _id 幂等覆盖），
    # 而 r000123 这种行号主键换个排序就全乱了。
    "review_id",
    # ---- 正文 ----
    "text",             # 清洗后的影评正文（去 HTML / 归一空白）
    "text_raw_len",     # 清洗前字符数（用来展示"清洗掉了多少噪声"）
    "text_len",         # 清洗后字符数
    "word_count",       # 词数（阶段 4 统计与主题分析用）
    # ---- 情感标注 ----
    "sentiment",        # positive / negative / neutral / None
    "sentiment_score",  # +1.0 / -1.0 / 0.0 / None —— 统一量纲，便于聚合求均值
    "rating",           # 原始评分（若数据集给的是 1~10 分而非标签）
    # ---- 关联到电影（弱关联，多数影评数据集没有）----
    "movie_title",      # 片名，如 "Toy Story 2"
    "movie_year",
    "imdb_id",
    # ---- 数据血缘 ----
    "lang",             # 影评语言（本数据集为 en）
    "dataset",          # Kaggle handle，溯源用
    "source",           # 固定 "kaggle"
    "source_file",      # 原始文件名
    "row_index",        # 在原始文件中的行号，便于回溯原文
    "collected_at",
)


# ============================================================
# 影评记录的「可选扩展字段」（阶段 2 · 多源影评统一合同）
# ============================================================
# 为什么核心字段之外还要一套「可选」字段？
#     Letterboxd / Metacritic / RSS 等新源会补充一些 Kaggle 没有的维度
#     （原文链接、源原生 id、critic/user 区分、剧透标记、匿名作者、媒体名、归一评分）。
#     如果直接塞进 REVIEW_FIELDS，老的 kaggle_reviews.py 生产者就会被 strict 自检判缺字段。
#     所以新增字段走「可选扩展」：REVIEW_FIELDS 保持不动（不破坏既有自检），
#     归一化时用 fill_review() 把核心 + 扩展都补齐（缺则 None），下游 DataFrame 列对齐。
REVIEW_OPTIONAL_FIELDS: tuple[str, ...] = (
    "review_url",       # 影评原文链接（溯源 / 去重辅助；合规起见不含用户名 PII）
    "external_id",      # 源原生 id（如 lb-123456），ES 幂等覆盖用
    "review_type",      # critic / user / audience / None
    "contains_spoiler", # 是否含剧透
    "author_hash",      # 匿名化的作者标识（sha256 截断），绝不存明文用户名 / 邮箱（合规）
    "outlet",           # 媒体 / 平台名（critic / RSS 用），如 Metacritic / Variety
    "score_norm",       # 归一化评分（0–10），与 sentiment_score（+1/-1/0）区分开
    "movie_tmdb_id",    # 关联电影的主键（优先于 imdb_id）
    "douban_id",        # 豆瓣 subject id
    "douban_sort",      # time / new_score：采集时的评论排序
    "douban_comment_time",  # 豆瓣页面显示的原始时间文本
    "review_time",      # 可解析时转换为 ISO 时间，供数据库排序与展示
)


# ============================================================
# 新闻 / 舆情记录合同（阶段 2 · RSS 用，独立 entity）
# ============================================================
# RSS 影评资讯不是「影评」，是「文章」，粒度不同，单独一套字段，
# 对应 ES 的独立索引 news（舆情时间线用）。
NEWS_FIELDS: tuple[str, ...] = (
    "article_id",       # sha256(link) 稳定主键
    "title",
    "link",
    "summary",          # RSS description（纯文本）
    "published_at",     # ISO 时间
    "outlet",           # 媒体名：Variety / THR / Deadline
    "categories",       # 分类标签列表
    "language",         # 语言标记（如 en）
    "sentiment",        # 采集时为空，阶段 4 舆情分析再补
    "source",           # 固定 "rss"
    "collected_at",
)


def fill_review(record: dict) -> dict:
    """把一条影评记录补齐到「核心 + 可选扩展」全集，缺字段填 None。

    下游建 DataFrame / 写 ES 时列才不会错位；幂等（已存在的字段不动）。
    """
    out = {f: None for f in REVIEW_FIELDS}
    out.update(record)
    for f in REVIEW_OPTIONAL_FIELDS:
        out.setdefault(f, None)
    return out


def validate_review_full(record: dict, *, strict: bool = False) -> list[str]:
    """校验影评记录「核心字段」是否齐全；strict 时缺核心字段直接抛错。

    可选扩展字段缺失不报警（那是各源可选的），只在 strict 下守核心。
    """
    missing = [f for f in REVIEW_FIELDS if f not in record]
    if missing and strict:
        raise ValueError(f"影评记录缺少核心字段：{missing}")
    return missing


def validate_review(record: dict, *, strict: bool = False) -> list[str]:
    """检查一条影评记录是否覆盖了 REVIEW_FIELDS（语义同 validate_record）。"""
    missing = [f for f in REVIEW_FIELDS if f not in record]
    if missing and strict:
        raise ValueError(f"影评记录缺少核心字段：{missing}")
    return missing


def validate_record(record: dict, *, strict: bool = False) -> list[str]:
    """检查一条记录是否覆盖了 CORE_FIELDS。

    返回缺失的字段名列表；strict=True 时直接把「缺字段」当异常抛出
    （阶段 2 融合时用 strict，避免脏数据悄悄流进 ES）。
    """
    missing = [f for f in CORE_FIELDS if f not in record]
    if missing and strict:
        raise ValueError(f"记录缺少核心字段：{missing}")
    return missing
