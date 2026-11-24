"""
阶段 4 · 洞察接口的请求 / 响应模型。

分成三类：
    · 情感打分（POST /insights/sentiment）—— 前端粘一段文本进来拿情感分，
      返回**每个命中词**，这是"可解释"的直接体现；
    · 全局主题（GET /insights/topics）—— 读分析层产出的 topics.json；
    · 单片画像（GET /insights/movies/{id}）—— 电影自身信息 + 关键词画像。
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ScoreRequest(BaseModel):
    """任意文本情感打分请求。"""

    text: str = Field(..., min_length=1, description="要打分的文本（中英文均可）")
    lang: Literal["zh", "en", "auto"] = Field(
        default="auto", description="auto = 按文本内容自动判别中英文")


class WordHit(BaseModel):
    """一个命中词：词本身、它贡献的分数（已含否定/程度调整）、在词典里的原始分。"""

    word: str
    weight: float = Field(description="该词最终贡献的分数（正=偏正面）")
    lexicon_score: float = Field(description="词典里的原始分，方便对照")


class ScoreResponse(BaseModel):
    """打分结果。label 与 score 是给程序用的，hits 是给人看的。"""

    score: float = Field(description="[-1, 1]，正数偏正面")
    label: Literal["positive", "negative", "neutral"]
    lang: str
    hits: list[WordHit] = Field(default_factory=list)
    matched_words: int = 0
    note: str | None = Field(default=None, description="词典缺失等情况的说明")


class KeywordItem(BaseModel):
    """一个关键词：词 + TF-IDF 分（单片画像）或 分化权重（主题榜）。"""

    word: str
    tf: int = 0
    df: int = 0
    score: float = 0.0
    side: Literal["positive", "negative", "neutral"] = "neutral"


class TopicItem(BaseModel):
    """主题榜上的一项：词 + 它在好评/差评里的文档频次与 lift。"""

    word: str
    df: int
    df_positive: int
    df_negative: int
    lift: float = Field(description="P(w|好评) / P(w|差评)，>1 偏好评")
    side: Literal["positive", "negative"]
    weight: float = Field(description="收缩后的对数提升度 × 证据量，即排序依据")


class TopicsResponse(BaseModel):
    """全局主题统计。"""

    docs: int = Field(description="参与统计的影评篇数")
    positive_docs: int = 0
    negative_docs: int = 0
    keywords: list[TopicItem] = Field(default_factory=list)
    positive_vocabulary: list[str] = Field(default_factory=list)
    negative_vocabulary: list[str] = Field(default_factory=list)


class GenreRef(BaseModel):
    """同类型口碑参照：把这部片放回它自己的类型里看。"""

    genre: str
    avg_rating: float | None = None
    movies: int = 0


class MovieInsight(BaseModel):
    """单片画像：电影自身字段 + 关键词 + 与全局情感的对照。"""

    movie_id: str
    title: str | None = None
    title_zh: str | None = None
    year: int | None = None
    genres_zh: list[str] = Field(default_factory=list)
    director: str | None = None
    rating: float | None = None
    votes: int | None = None
    sources: list[str] = Field(default_factory=list)
    keywords: list[KeywordItem] = Field(default_factory=list)
    sentiment_hint: str | None = Field(
        default=None, description="基于该片类型的全局好评率给出的口碑参考")
    genre_ref: GenreRef | None = Field(
        default=None, description="同类型均分参照（前端画「本片 vs 类型均分」对比条）")


class VoiceItem(BaseModel):
    """一条观众短评（真实原文，非模板生成）。"""

    review_id: str
    text: str
    sentiment: str | None = None
    sentiment_score: float | None = None
    source: str | None = Field(default=None, description="douban / tmdb / kaggle")
    movie_id: str | None = None
    movie_title: str | None = Field(default=None, description="同类型短评时用来标出处影片")
    rating: float | None = None
    word_count: int | None = None
    review_time: str | None = None
    douban_sort: str | None = None


class VoiceStats(BaseModel):
    """短评的情感构成：正面 / 中性 / 负面各多少条。"""

    total: int = 0
    positive: int = 0
    neutral: int = 0
    negative: int = 0
    avg_rating: float | None = None


class MovieVoices(BaseModel):
    """单片口碑：本片短评；本片没有时退回同类型影片的真实短评。"""

    movie_id: str
    scope: str = Field(description="own=本片短评，peers=同类型影片短评，none=都没有")
    genres_zh: list[str] = Field(default_factory=list)
    stats: VoiceStats = Field(default_factory=VoiceStats)
    items: list[VoiceItem] = Field(default_factory=list)


class SentimentBucket(BaseModel):
    """情感分面的一个桶。"""

    key: str
    count: int


class GenreRating(BaseModel):
    """一个类型的口碑统计（电影侧评分，不是影评情感 —— 见 by_genre 的说明）。"""

    genre: str
    movies: int = 0
    avg_rating: float | None = None
    avg_votes: int | None = None


class SentimentStats(BaseModel):
    """全局情感分布 + 类型口碑。

    ★ 为什么 by_genre 用的是电影评分而不是影评情感？
        影评（Kaggle 那 5 万条）**没有电影 id**，无法按类型汇总影评情感 ——
        这是数据源本身的限制（Stanford 数据集只有正文和标签两列）。
        所以类型维度退一步用电影侧评分（IMDb/TMDB 的 vote_average），
        口径不同就明说，不假装它是影评情感。
    """

    total: int = 0
    buckets: list[SentimentBucket] = Field(default_factory=list)
    positive_ratio: float = 0.0
    by_genre: list[GenreRating] = Field(
        default_factory=list,
        description="各类型平均分与影片数，按均分倒序，供大屏画条形图")


class TrendBucket(BaseModel):
    """一个年代桶：decade 是年代起始年（2010 表示 2010s）。"""

    decade: int
    movies: int = 0
    avg_rating: float | None = None


class TrendsResponse(BaseModel):
    """年代趋势：替代原系统「数据趋势分析」图位的大数据版本。

    with_year 是带了年份字段的影片数（缺年份的影片进不了任何桶），
    与 total_movies 的差额就是年份缺失量 —— 数据稀疏是融合层的常态，
    如实报数，不偷偷归一成百分比假装 100% 覆盖。
    """

    total_movies: int = 0
    with_year: int = 0
    buckets: list[TrendBucket] = Field(default_factory=list)
    note: str | None = None


class MatrixCell(BaseModel):
    """矩阵里的一格：某类型在某年代的影片数与均分（均分可为 null）。"""

    decade: int
    movies: int = 0
    avg_rating: float | None = None


class MatrixRow(BaseModel):
    """矩阵里的一行：一个类型 + 它在各年代的格子（按年代升序）。"""

    genre: str
    total: int = 0
    cells: list[MatrixCell] = Field(default_factory=list)


class MatrixResponse(BaseModel):
    """类型 × 年代矩阵：Flourish 式动态图表（条形竞赛 / 排名变化 / 桑基流向）的数据源。

    decades 是全列坐标（合并所有行后去重升序）—— 前端画竞赛图 / 排名图
    都要按这条统一时间轴走，不然行与行的年代桶对不齐。
    注意：一部电影有多个类型，故各行 total 之和 > 影片总数，
    这不是 bug，是"混搭"语义本身（按类型透视必然重复计）。
    """

    decades: list[int] = Field(default_factory=list)
    rows: list[MatrixRow] = Field(default_factory=list)
    note: str | None = None


# ============================================================
# 票房分析（2026-10-22 新增，替代原「类型竞赛」展厅）
# ============================================================


class BoxOfficeItem(BaseModel):
    """票房画廊里的一部影片：相框内容 + 详情纸卡用的全部数字。

    revenue/budget 单位美元（TMDB 口径）；roi = revenue / budget，
    缺预算时为 None —— 老片普遍没有预算数据，如实留空不编。
    """

    movie_id: str
    title: str
    title_en: str | None = None
    year: int | None = None
    poster_url: str | None = None
    revenue: int
    budget: int | None = None
    roi: float | None = None
    vote_average: float | None = None
    genres: list[str] = Field(default_factory=list)


class BoxOfficeYearBucket(BaseModel):
    """年度票房桶：某年上映影片的票房合计（仅统计有票房数据的影片）。"""

    year: int
    revenue: int = 0
    movies: int = 0


class BoxOfficeResponse(BaseModel):
    """票房分析展厅数据源：画廊相框 + 年度趋势 + 总览数字。

    gallery 按票房倒序取前 N 部（相框沿晾衣绳排开）；
    years 按年份升序（右翼趋势图）。total_movies 是**有票房数据**的影片数，
    远小于片库总数 —— TMDB 只对部分影片给出 revenue，如实报数。
    """

    total_movies: int = 0
    total_revenue: int = 0
    top_year: int | None = None
    gallery: list[BoxOfficeItem] = Field(default_factory=list)
    years: list[BoxOfficeYearBucket] = Field(default_factory=list)
    note: str | None = None


# ============================================================
# 口碑分化 / 地区画像 / 馆长洞察（2026-11-01 新增展厅分析）
# ============================================================


class Quote(BaseModel):
    """一条真实影评引文：正文（后端已去 markdown / 链接 / 控长）+ 原作者评分。"""

    text: str
    rating: float | None = None


class PolarizingItem(BaseModel):
    """一部口碑两极分化的影片：评分标准差 + 正/负两条真实引文。

    为前端 A24 影片展补充：poster_url（真实圆盘海报）、director（credits）、
    vote_average（星级）。poster_url 已由 rewrite_poster_url 改写为代理路径。
    """

    movie_id: str
    title: str
    title_en: str | None = None
    year: int | None = None
    director: str | None = None
    poster_url: str | None = None
    vote_average: float | None = None
    review_count: int = 0
    avg_rating: float | None = None
    std_dev: float | None = Field(default=None, description="评分标准差，越大观众分歧越大")
    pos_quote: Quote | None = None
    neg_quote: Quote | None = None


class PolarizingResponse(BaseModel):
    """口碑分化榜。total_qualified = 库内有足够评分影评、可计算分化的影片总数。"""

    total_qualified: int = 0
    items: list[PolarizingItem] = Field(default_factory=list)


class RegionItem(BaseModel):
    country: str
    movies: int = 0
    avg_rating: float | None = None
    avg_votes: int | None = None


class RegionsResponse(BaseModel):
    """地区画像：主出品国产量与口碑对照（按片数倒序）。"""

    items: list[RegionItem] = Field(default_factory=list)


class StoryFact(BaseModel):
    """洞察卡上一行键值（A24 credits 式）：k 左对齐，v 右对齐。"""

    k: str
    v: str
    big: bool = Field(default=False, description="衬线大字渲染（该卡的核心数字）")


class StoryCard(BaseModel):
    """大厅「馆长洞察」卡：一句结论问句 + 若干键值行，点卡直达对应展厅。"""

    kind: str = Field(description="polarizing / regions / sentiment，决定图标与配色")
    kicker: str = Field(description="顶部小标签")
    question: str = Field(description="结论问句（大字）")
    answer: str = Field(description="辅助说明一句")
    facts: list[StoryFact] = Field(default_factory=list)
    room: str = Field(description="点卡进入的展厅 key（对齐前端 VIEWS）")


class StoryResponse(BaseModel):
    cards: list[StoryCard] = Field(default_factory=list)


# ============================================================
# 深度分析（2026-11-04）：走廊片单 / 知识图谱 / 相关性 / 三层流向
# ------------------------------------------------------------
# 与前面「把 ES 桶摊平成表」的模型不同：这一组字段里凡是带 gap / lift /
# r / q1 / roi / percentile 的，都是后端现场算出来的统计量，不是索引原字段。
# ============================================================


class HallPoster(BaseModel):
    """走廊里挂着的一部真实影片 + 它「为什么挂在这里」的分析结论。"""

    movie_id: str
    title: str
    title_en: str | None = None
    year: int | None = None
    poster_url: str | None = Field(default=None, description="已改写为 /api/v1/img 代理路径")
    genres: list[str] = Field(default_factory=list)
    director: str | None = None
    cast: list[str] = Field(default_factory=list)
    vote_average: float | None = None
    vote_count: int | None = None
    revenue: int | None = None
    budget: int | None = None
    roi: float | None = Field(default=None, description="(票房-预算)/预算，后端现算")
    genre: str = Field(description="它是哪个类型的代表")
    role: str = Field(description="口碑代表 / 票房代表")
    genre_movies: int = 0
    genre_avg_rating: float | None = None
    rating_gap: float | None = Field(default=None, description="该片评分 - 类型均分")
    note: str = Field(default="", description="一句由聚合结果生成的结论")


class HallPostersResponse(BaseModel):
    total_movies: int = 0
    items: list[HallPoster] = Field(default_factory=list)
    note: str | None = None


class GraphNode(BaseModel):
    id: str
    name: str
    kind: Literal["genre", "director", "actor"]
    value: int = Field(default=0, description="该节点涉及的影片数")
    avg_rating: float | None = None


class GraphLink(BaseModel):
    source: str
    target: str
    weight: int = Field(description="ES 聚合出的真实共现次数")
    lift: float = Field(description="P(目标|源)/P(目标)，>1 才是有效关系")
    kind: Literal["genre-director", "genre-actor", "genre-genre"]


class KnowledgeGraphResponse(BaseModel):
    nodes: list[GraphNode] = Field(default_factory=list)
    links: list[GraphLink] = Field(default_factory=list)
    total_movies: int = 0
    pair_count: int = 0
    strongest: GraphLink | None = None
    notes: list[str] = Field(default_factory=list)


class CorrelationPoint(BaseModel):
    x: float = Field(description="预算（美元）")
    y: float = Field(description="票房（美元）")
    rating: float | None = None
    title: str
    movie_id: str


class RegressionInfo(BaseModel):
    slope: float
    intercept: float
    r2: float
    n: int
    x_mean: float
    y_mean: float


class RoiBox(BaseModel):
    """某类型 ROI 的四分位分布（真算，不是平均值一根柱子）。"""

    genre: str
    count: int
    min: float
    q1: float
    median: float
    q3: float
    max: float
    iqr: float


class GenreProfile(BaseModel):
    """类型多维画像：全部由样本现算（均值 / 高分率 / ROI 中位数）。"""

    genre: str
    movies: int
    avg_rating: float
    avg_votes: float
    avg_runtime: float
    hit_rate: float = Field(description="评分 ≥8 的比例")
    median_roi: float | None = None


class CorrelationResponse(BaseModel):
    variables: list[str] = Field(default_factory=list)
    labels: list[str] = Field(default_factory=list)
    matrix: list[list[float | None]] = Field(default_factory=list)
    sample_size: int = 0
    scatter: list[CorrelationPoint] = Field(default_factory=list)
    regression: RegressionInfo | None = None
    roi_by_genre: list[RoiBox] = Field(default_factory=list)
    profiles: list[GenreProfile] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class FlowNode(BaseModel):
    name: str
    kind: Literal["genre", "decade", "tier"]
    value: int = 0


class FlowLink(BaseModel):
    source: str
    target: str
    value: int


class FlowHeat(BaseModel):
    genre: str
    decade: int
    movies: int
    avg_rating: float | None = None


class FlowLayersResponse(BaseModel):
    nodes: list[FlowNode] = Field(default_factory=list)
    links: list[FlowLink] = Field(default_factory=list)
    heat: list[FlowHeat] = Field(default_factory=list)
    decades: list[int] = Field(default_factory=list)
    genres: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
