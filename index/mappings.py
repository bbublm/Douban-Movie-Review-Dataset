"""
索引的 settings 与 mapping —— 检索能力的「设计图纸」。

★ 核心设计：mapping 恒定，只有 settings 变。

    中文分词器有 IK 和没 IK 两种环境，但**索引结构必须一模一样**，
    否则同一份代码在两台机器上建出来的索引不一样，检索结果也就对不上。
    做法是：mapping 里只引用两个自定义分析器名字 yj_zh_index / yj_zh_search，
    至于这两个名字背后是 IK 还是内置 cjk，由 settings 决定。
    这样换分词器不用改一行 mapping —— 部署时探测一次即可。

★ 为什么索引期和查询期要用不同的分析器？

    索引期用 ik_max_word（切得最碎：「科幻电影」→ 科幻 / 电影 / 科幻电影），
    召回率高；查询期用 ik_smart（切得干净：「科幻电影」→ 科幻电影），
    精度高。这是中文检索的标准做法 —— 细粒度存、粗粒度查。
    如果两头都用 ik_max_word，搜「科幻电影」会把只含「电影」的片子也捞回来。

★ 为什么几乎每个文本字段都挂一个 .kw 子字段？

    text 字段不能排序、不能聚合、不能精确匹配（"流浪地球" 会被切成词）。
    但前端既要"搜索片名"，也要"按片名排序 / 按类型分面统计"，
    所以同一个值存两遍：text 用于检索，keyword 用于聚合排序。
    这是 ES 里最常用也最容易被新手忽略的 Multi-fields 模式。
"""
from __future__ import annotations

# ---------- 自定义分析器名字（mapping 里统一引用这两个名字）----------
ZH_INDEX = "yj_zh_index"     # 写入时用：切得细
ZH_SEARCH = "yj_zh_search"   # 查询时用：切得粗

# 影评正文是英文，直接用 ES 内置 english 分析器（自带词干还原与停用词），
# 不占用我们的中文分析器。
EN_ANALYZER = "english"


def detect_ik(es) -> bool:
    """探测 ES 集群有没有装 IK 中文分词插件。

    用一次 _analyze 试分词来探测，而不是读插件列表 ——
    因为没装插件时索引创建会直接抛 "failed to find global tokenizer"，
    而插件列表在不同部署方式（Dockerfile 构建 vs 运行时 exec 安装）下口径不一。
    直接问"ik_max_word 能不能用"是最可靠的判断。

    探测失败一律按「没装」处理：降级到内置 cjk 分析器，索引照样能建、能搜。
    """
    try:
        es.options(request_timeout=5).indices.analyze(
            tokenizer="ik_max_word",
            text="电影盒子中文分词探测",
        )
        return True
    except Exception:  # noqa: BLE001 —— 探测失败不该中断建索引
        return False


def analysis_block(*, use_ik: bool) -> dict:
    """生成 settings 里的 analysis 段。

    use_ik=True  -> ik_max_word / ik_smart（需要插件）
    use_ik=False -> 内置 cjk 分析器（二元组切分，无需插件）
    """
    if use_ik:
        analyzers = {
            ZH_INDEX: {"type": "custom", "tokenizer": "ik_max_word", "filter": ["lowercase"]},
            ZH_SEARCH: {"type": "custom", "tokenizer": "ik_smart", "filter": ["lowercase"]},
        }
    else:
        # cjk 是 ES 内置分析器，按二元组切中文（"霸王别姬" → 霸王/王别/别姬）。
        # 效果不如 IK，但零依赖，保证任何环境都能跑起来。
        analyzers = {
            ZH_INDEX: {"type": "cjk"},
            ZH_SEARCH: {"type": "cjk"},
        }
    return {"analysis": {"analyzer": analyzers}}


def index_settings(*, use_ik: bool, shards: int = 1, replicas: int = 0) -> dict:
    """索引级 settings。

    单分片 / 零副本是**刻意**的开发期配置：
    数据量只有几万条，多分片纯属浪费；副本在无第二节点的单机会让健康度变成 yellow，
    看着像坏了。上线前把 shards/replicas 调大即可，不用改代码。
    """
    return {
        "number_of_shards": shards,
        "number_of_replicas": replicas,
        "refresh_interval": "1s",
        # 阶段 5 大屏要做全量聚合，默认 10000 的翻页窗口不够用
        "max_result_window": 50000,
        **analysis_block(use_ik=use_ik),
    }


# ============================================================
# 字段片段（复用，避免 40 个字段抄 40 遍）
# ============================================================

def _cn_text() -> dict:
    """中英混排正文：索引期细切、查询期粗切。"""
    return {"type": "text", "analyzer": ZH_INDEX, "search_analyzer": ZH_SEARCH}


def _cn_text_kw() -> dict:
    """中英混排 + keyword 子字段（用于排序 / 聚合 / 精确匹配）。"""
    return {
        **_cn_text(),
        "fields": {"kw": {"type": "keyword", "ignore_above": 256}},
    }


def _en_text_kw() -> dict:
    """英文文本（片名、人名的原文）+ keyword 子字段。"""
    return {
        "type": "text",
        "analyzer": EN_ANALYZER,
        "fields": {"kw": {"type": "keyword", "ignore_above": 256}},
    }


def _kw() -> dict:
    """纯 keyword：分面筛选、精确过滤用。"""
    return {"type": "keyword"}


def _kw_noindex() -> dict:
    """只存不建索引的 keyword：URL 这类只用来展示、从不参与查询的字段。

    ★ 注意：这样设之后，该字段既进不了倒排索引也没有 doc_values，
      于是 **`exists` 查询永远返回 0 命中**（ES 无处可查）。
      实测踩过：poster_url 曾经这样设，结果"只要带海报的"这个筛选恒为空。
      → 凡是可能被 `exists` / 聚合 / 排序用到的字段，**不能**用这个。
      目前只剩 wikidata_url / wikipedia_url 这种纯展示外链用它。
    """
    return {"type": "keyword", "index": False, "doc_values": False}


def _date() -> dict:
    """日期字段。ignore_malformed=True 是**必须**的：

    融合数据里混着 None、"unknown"、"2019" 这类脏值，
    默认行为是整条文档写入失败。ignore_malformed 让脏日期被静默跳过，
    其余字段照常入库 —— 一条脏日期不该带走整部电影。
    """
    return {"type": "date", "format": "strict_date_optional_time||yyyy-MM-dd||epoch_millis",
            "ignore_malformed": True}


def _place() -> dict:
    """拍摄地 / 故事发生地（nested）。

    为什么用 nested 而不是 object？
        ES 默认把对象数组**打平**成多值字段，会丢掉「哪个名字配哪个坐标」的
        对应关系：查"名字叫香港 且 纬度>22"可能命中一部在上海取景、在香港叙事的片。
        nested 让每个地点独立成文档，跨字段条件才准确。
        代价是查询要写 nested 查询、聚合要多一层 —— 阶段 6 地图会用到。

    location 字段是 geo_point，由 prepare_movie_doc() 从 (lat, lon) 拼出来。
    """
    return {
        "type": "nested",
        "properties": {
            "name": _cn_text_kw(),
            "kind": _kw(),          # filming（取景地）/ narrative（故事发生地）
            "qid": _kw(),
            "lat": {"type": "float"},
            "lon": {"type": "float"},
            "location": {"type": "geo_point"},
        },
    }


# ============================================================
# movies 索引 mapping
# ============================================================

MOVIES_MAPPING: dict = {
    # strict：出现 mapping 里没有的字段**直接报错**，而不是悄悄动态映射。
    # 融合层改了字段名却忘了同步 mapping，是最容易埋雷的地方 ——
    # 动态映射会让它看起来"能跑"，实际那个字段根本没建索引、永远搜不到。
    # 宁可导入时炸，也不要线上静默失效。
    "dynamic": "strict",
    "properties": {
        # ---- 主键 ----
        "movie_id": _kw(),
        "imdb_id": _kw(),
        "tmdb_id": _kw(),
        "wikidata_qid": _kw(),
        # ---- 片名 ----
        "title": _cn_text_kw(),
        "title_zh": _cn_text_kw(),
        "title_en": _en_text_kw(),
        "original_title": _en_text_kw(),
        "wikipedia_title": _cn_text_kw(),
        # ---- 正文 ----
        "overview": _cn_text(),
        "tagline": _cn_text(),
        "wikipedia_extract": _cn_text(),
        # ---- 时间 ----
        "release_date": _date(),
        "release_year": {"type": "integer"},
        "runtime": {"type": "integer"},
        "collected_at": _date(),
        # ---- 分类 ----
        "genres_zh": _kw(),          # 分面筛选主字段
        "genres_en": _kw(),
        "genre_ids": {"type": "integer"},
        "keywords": _cn_text_kw(),
        "status": _kw(),
        "title_type": _kw(),         # movie / tvMovie / short …
        "original_language": _kw(),
        # ---- 人物 ----
        "director": _cn_text_kw(),
        "cast": _cn_text_kw(),
        # ---- 评分 ----
        "vote_average": {"type": "float"},
        "vote_count": {"type": "integer"},
        "popularity": {"type": "float"},
        "imdb_rating": {"type": "float"},
        "imdb_votes": {"type": "integer"},
        # ---- 票房与预算（美元；票房分析展厅聚合用）----
        "revenue": {"type": "long"},
        "budget": {"type": "long"},
        # ---- 阶段 1f：豆瓣评分（解除「禁采集豆瓣」红线后新增）----
        "douban_id": _kw(),
        "douban_rating": {"type": "float"},
        "douban_score": {"type": "float"},
        "douban_votes": {"type": "integer"},
        "douban_comments": _cn_text_kw(),
        "douban_short_comments": _cn_text_kw(),
        "douban_long_comments": _cn_text_kw(),
        # ---- 地域 ----
        "spoken_languages": _kw(),
        "production_countries": _kw(),
        "production_country_codes": _kw(),
        # 主出品国（国家分面的筛选口径，只算主出品国不带合拍国）
        "primary_country": _kw(),
        # ---- 地图 ----
        "filming_locations": _place(),
        "locations_with_coords": _place(),
        # ---- 图片 / 外链 ----
        # poster_url / backdrop_url 用**可索引**的 keyword（不是 _kw_noindex）：
        # 前端要能筛「只看有海报的」，而 exists 查询依赖倒排索引或 doc_values。
        "poster_url": _kw(),
        "backdrop_url": _kw(),
        "wikidata_url": _kw_noindex(),
        "wikipedia_url": _kw_noindex(),
        # ---- 数据血缘（阶段 5 用来画"多源覆盖率"图）----
        "source": _kw(),
        "sources": _kw(),
        "upstream": _kw(),
        "source_count": {"type": "integer"},
        "merged_from": {"type": "integer"},
        "match_keys": _kw(),
        "is_multi_source": {"type": "boolean"},
        "id_resolved": {"type": "boolean"},
    },
}


# ============================================================
# reviews 索引 mapping
# ============================================================

REVIEWS_MAPPING: dict = {
    "dynamic": "strict",
    "properties": {
        # ---- 主键 ----
        "review_id": _kw(),
        "movie_id": _kw(),          # 与 movies.movie_id 同值 → 阶段 3 做跨索引关联
        "imdb_id": _kw(),
        "movie_tmdb_id": _kw(),
        "douban_id": _kw(),
        "douban_sort": _kw(),
        "douban_comment_time": _kw(),
        "review_time": _date(),
        # ---- 正文 ----
        # 影评是英文语料，用 english 分析器（自动词干还原：wonderful → wonder，
        # 并剔除 the/a/is 这类停用词），比标准分析器检索质量高。
        "text": {"type": "text", "analyzer": EN_ANALYZER},
        "text_raw_len": {"type": "integer"},
        "text_len": {"type": "integer"},
        "word_count": {"type": "integer"},
        # ---- 情感 ----
        "sentiment": _kw(),          # positive / negative / neutral → 分面统计
        "sentiment_score": {"type": "float"},
        "rating": {"type": "float"},
        # ---- 关联信息 ----
        "movie_title": _en_text_kw(),
        "movie_year": {"type": "integer"},
        "matched_by": _kw(),         # imdb_id / title / no-title —— 关联质量可审计
        # ---- 血缘 ----
        "lang": _kw(),
        "dataset": _kw(),
        "source": _kw(),
        "source_file": _kw(),
        "row_index": {"type": "long"},
        "collected_at": _date(),
        "transformed_at": _date(),
    },
}


# ============================================================
# news 索引 mapping（影视新闻 / 舆情时间线）
# ============================================================
# 新闻来自 RSS（Variety / THR / Deadline），标题与摘要以英文为主，
# 故正文类字段用 EN_ANALYZER（english 分析器，自带词干还原与停用词）。
# link 是长 URL，只展示不检索 → _kw_noindex（沿用 poster_url 的教训：
# 凡是不会被 exists/聚合/排序用的字段才用这个）。
NEWS_MAPPING: dict = {
    "dynamic": "strict",
    "properties": {
        # ---- 主键 ----
        "article_id": _kw(),          # sha256(link) 稳定主键 → 幂等导入
        # ---- 标题 / 摘要（英文分析器）----
        "title": _en_text_kw(),       # 检索 + 精确匹配（按标题去重/定位）
        "summary": _en_text_kw(),     # RSS description（纯文本，已去标签/解码实体）
        # ---- 外链（只展示）----
        "link": _kw_noindex(),        # 原文链接，过长且不参与查询
        # ---- 时间 ----
        "published_at": _date(),      # 新闻发布时间（舆情时间线主轴）
        "collected_at": _date(),      # 采集入库时间
        # ---- 分类 / 来源（分面筛选）----
        "outlet": _kw(),              # 媒体：Variety / THR / Deadline
        "categories": _kw(),          # 分类标签数组：Box Office / TV 等
        "language": _kw(),            # 语言标记：en
        # ---- 舆情（阶段 4 情感分析再补，采集时留空）----
        "sentiment": _kw(),
        # ---- 血缘 ----
        "source": _kw(),              # 固定 "rss"
    },
}


# ============================================================
# douban_nowplaying 索引 mapping（阶段 1f · 院线热映榜，独立实体）
# ============================================================
# 这跟 movies 索引是**两套东西**：热映榜里的片大多是院线新片，
# 绝大多数不在库内 266 部里，且没有 tmdb_id / imdb_id 锚点，硬并进去会污染库内片库。
# 所以单独建索引，前端用一个独立接口拉取展示。
DOUBAN_NOWPLAYING_MAPPING: dict = {
    "dynamic": "strict",
    "properties": {
        # ---- 主键 ----
        "douban_id": _kw(),              # 豆瓣 subject id → 稳定主键
        # ---- 片名 / 展示 ----
        "title": _cn_text_kw(),
        "poster": _kw_noindex(),         # 豆瓣海报原图 URL（只展示，走 /api/v1/img 代理）
        # ---- 评分 ----
        "douban_rating": {"type": "float"},
        "douban_votes": {"type": "integer"},
        # ---- 元信息 ----
        "release_year": {"type": "integer"},
        "region": _cn_text_kw(),         # 出品地区：德国 法国 美国
        "director": _cn_text_kw(),       # 导演
        "actors": _cn_text_kw(),         # 主演
        "duration": _cn_text_kw(),       # 片长，如 94分钟
        # ---- 血缘 ----
        "collected_at": _date(),
        "source": _kw(),                 # 固定 "douban"
    },
}


# ============================================================
# tmdb_videos 索引 mapping（阶段 1g · 视频数据：TMDB 官方预告片）
# ============================================================
# 这是「电影」的从属数据（每部电影一组预告片），但单独建索引而不是塞进 movies：
#   · 预告片是经常追加/更新的（新出 Teaser、官方 Trailer），独立索引可单独重建；
#   · movies 索引已经很宽，且 dynamic:strict，往里加 nested 数组要同步 mapping；
#   · 按 tmdb_id 取，详情页直接 `GET /trailers/{tmdb_id}`，不参与 movies 检索。
TMDB_VIDEOS_MAPPING: dict = {
    "dynamic": "strict",
    "properties": {
        # ---- 主键 ----
        "tmdb_id": _kw(),                  # 与 movies.tmdb_id 同值 → 关联键
        # ---- 片名（展示用，冗余存一份免回查 movies）----
        "title": _cn_text_kw(),
        "title_zh": _cn_text_kw(),
        "release_year": {"type": "integer"},
        # ---- 预告片数组（nested：每条独立，跨字段条件才准确）----
        "trailers": {
            "type": "nested",
            "properties": {
                "key": _kw(),              # YouTube video id
                "name": _cn_text_kw(),
                "type": _kw(),             # Trailer / Teaser
                "official": {"type": "boolean"},
                "published_at": _date(),
                "url": _kw_noindex(),      # https://www.youtube.com/embed/<key>（只展示）
            },
        },
        "trailer_count": {"type": "integer"},
        # ---- 血缘 ----
        "collected_at": _date(),
        "source": _kw(),                   # 固定 "tmdb"
    },
}


# 索引类型 → mapping / 主键字段。CLI 与 builder 都从这张表取，避免各写一份。
INDEX_SPECS: dict[str, dict] = {
    "movies": {"mapping": MOVIES_MAPPING, "id_field": "movie_id"},
    "reviews": {"mapping": REVIEWS_MAPPING, "id_field": "review_id"},
    "news": {"mapping": NEWS_MAPPING, "id_field": "article_id"},
    "douban_nowplaying": {"mapping": DOUBAN_NOWPLAYING_MAPPING, "id_field": "douban_id"},
    "tmdb_videos": {"mapping": TMDB_VIDEOS_MAPPING, "id_field": "tmdb_id"},
}


# ============================================================
# 用户索引（阶段 5 前功能补全）
# ============================================================

# 用户为什么也放 ES，而不是引入 SQLite/Postgres？
#   本平台的底座就是 ES，用户量小（课程演示几十人），
#   再引一个关系库意味着"两套客户端、两套备份、两份运维"，
#   对课程项目是纯负担。代价（ES 无事务、无外键）在这个量级可以接受，
#   唯一性用 op_type=create 原子保证（见 user_store.create_user）。
USERS_MAPPING: dict = {
    "dynamic": "strict",
    "properties": {
        "username": _kw(),               # 同时作为 ES 文档 _id（唯一性由 create 冲突保证）
        "password_hash": _kw_noindex(),  # bcrypt 哈希；不进倒排、不被检索，只按 id 取
        "role": _kw(),                   # admin / user —— 继承原系统的角色二分
        "nickname": _en_text_kw(),       # 展示名，缺省等同 username
        "created_at": _date(),
    },
}


# ============================================================
# 用户评分索引（阶段 5 前功能补全，个性化推荐的输入）
# ============================================================

# 评分是"用户 × 电影"的关系表，ES 文档 _id = "用户名:movie_id"：
#   · 天然幂等 —— 同一个人对同一部片重复打分是更新，不会刷出两行
#   · "某人打过分哪些片"一次 term 查询就有，不用 join
# 代价：用户名里不能有冒号（注册规则已限定 ^[a-zA-Z0-9_]+$，见 schemas/auth.py）。
RATINGS_MAPPING: dict = {
    "dynamic": "strict",
    "properties": {
        "username": _kw(),        # 打分者
        "movie_id": _kw(),        # 与 movies.movie_id 同值
        "movie_title": _en_text_kw(),   # 冗余存一份标题，推荐理由里要展示
        "score": {"type": "float"},     # 1~10，与 IMDb/TMDB 同量纲
        "created_at": _date(),
    },
}


# ============================================================
# 想看清单索引（阶段 6 生产可用性补全）
# ============================================================

# 想看清单 = "用户 × 电影"的收藏关系，与评分同构（_id = "用户名:movie_id"，幂等）。
# 为什么和评分分成两个索引而不是合成一张"行为表"加 type 字段：
#   · 两者的字段几乎不重叠（评分有 score，想看没有），合成表要为一个 type
#     放弃 dynamic:strict 的严格性，或者在应用层自己校验字段组合；
#   · "我的想看"就是一次 term 查询，分索引后每个查询都只扫自己要的字段。
# 想看清单的消费方是原系统"观看记录/收藏"的迁移位：用户标记想看的片，
# 阶段 5 前端在影片卡上给一颗星，for-you 的候选召回也可以加权（后续）。
WATCHLIST_MAPPING: dict = {
    "dynamic": "strict",
    "properties": {
        "username": _kw(),        # 收藏者
        "movie_id": _kw(),        # 与 movies.movie_id 同值
        "movie_title": _en_text_kw(),   # 冗余标题，列表页不必回查 movies
        "created_at": _date(),
    },
}


# 会被 `exists` 查询用到的字段（阶段 3 的"只看有海报的 / 有简介的"筛选）。
# 这些字段**绝对不能**是 index:false + doc_values:false ——
# 否则 ES 无处可查，exists 永远返回 0 命中，且不报错，只会静默地筛不出东西。
# 自检里有一条断言专门守护这件事（阶段 2b 实测踩过这个坑）。
EXISTS_QUERY_FIELDS: frozenset[str] = frozenset({
    "poster_url", "backdrop_url", "overview", "director", "cast",
    "genres_zh", "release_year", "vote_average", "filming_locations",
})


# ============================================================
# 文档整形：把融合产物改成 ES 认识的形状
# ============================================================

def _shape_place(place) -> dict | None:
    """把一处拍摄地补上 geo_point。

    ES 的 geo_point 认三种写法：{"lat","lon"} 对象、"lat,lon" 字符串、[lon, lat] 数组。
    我们只选第一种 —— 它是唯一不会让人把经纬度顺序搞反的写法
    （数组写法是 [经度, 纬度]，和直觉相反，本项目在阶段 1c 已经踩过一次坑）。
    """
    if not isinstance(place, dict):
        return None
    lat, lon = place.get("lat"), place.get("lon")
    if lat is None or lon is None:
        return dict(place)
    return {**place, "location": {"lat": lat, "lon": lon}}


def prepare_movie_doc(record: dict) -> dict:
    """电影文档整形：给拍摄地补 geo_point。

    为什么这件事放在索引层而不是融合层？
        geo_point 是纯 ES 概念，融合产物应该保持"数据源中立"——
        将来要换成 PostgreSQL / Milvus，不需要为它们重写融合逻辑。
    """
    doc = dict(record)
    for key in ("filming_locations", "locations_with_coords"):
        places = doc.get(key)
        if isinstance(places, list):
            doc[key] = [p for p in (_shape_place(x) for x in places) if p is not None]
    return doc


def prepare_review_doc(record: dict) -> dict:
    """影评文档整形：目前无需改写，保留入口是为了和电影侧对称。

    保留一个空操作函数看似多余，但它把"文档整形"这个扩展点显式化了 ——
    将来要在这里加情感词典打分、截断超长文本，不用去改 builder 的主循环。
    """
    return dict(record)


PREPARERS = {"movies": prepare_movie_doc, "reviews": prepare_review_doc}
