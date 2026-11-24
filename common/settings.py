"""
全局配置：从工程根目录的 .env 读取，backend / ingest / scripts 共用同一份。

为什么集中在这里？
    采集脚本和后端服务必须连同一个 ES、用同一个索引名。
    配置只写一份，就不会出现"采集写进 A 索引、查询读 B 索引"的经典事故。
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# yingjian-zhisou/ 工程根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---------- 应用 ----------
    app_name: str = "电影盒子"
    debug: bool = True
    api_port: int = 8000
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # ---------- Elasticsearch ----------
    es_hosts: str = "http://localhost:9200"
    es_username: str = ""
    es_password: str = ""
    es_index_movies: str = "movies"
    es_index_reviews: str = "reviews"
    es_index_news: str = "news"           # 影视新闻 / 舆情时间线（RSS 采集，见 ingest/sources/rss.py）
    es_index_douban_nowplaying: str = "douban_nowplaying"  # 豆瓣院线热映榜（阶段 1f，独立实体）
    es_index_tmdb_videos: str = "tmdb_videos"        # TMDB 预告片（视频数据，阶段 1g）
    es_index_users: str = "users"          # 用户模块（注册/登录/JWT），见 backend/services/user_store.py
    es_index_ratings: str = "ratings"      # 用户评分（个性化推荐的输入），见 backend/services/ratings_store.py
    es_index_watchlist: str = "watchlist"  # 想看清单，见 backend/services/watchlist_store.py

    # ---------- 用户认证（JWT）----------
    # 生产必须改 secret 并写进 .env（不入库）；开发默认值仅用于本地演示。
    # 长度 ≥32 字节：HS256 的 RFC 7518 最低要求，短了 PyJWT 会持续告警。
    jwt_secret: str = "dev-only-secret-please-override-in-env-file"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 720          # 12 小时，课程演示一节课够用
    admin_password: str = "admin123"       # 演示管理员播种口令（仅本机开发用，.env 可覆盖）

    # ---------- 访问控制（中间件，见 backend/middleware.py）----------
    # 原系统有 IP 限流，新栈继承这个安全意识：
    #   · general：单 IP 每分钟总请求上限（SPA 一页十来个请求，240 够用不误伤）
    #   · auth_fail：单 IP 每分钟**失败**的登录/注册次数（成功即清零——
    #     正常用户登录不受限，爆破者 10 次/分钟就被挡，bcrypt cost=12 再叠一层）
    # 内存计数器 = 单实例有效；多实例水平扩容要换 Redis（决策写在 middleware 注释里）。
    rate_limit_enabled: bool = True
    rate_limit_general_per_minute: int = 240
    rate_limit_auth_fail_per_minute: int = 10
    # 信任 X-Forwarded-For 吗？直连部署（本课程默认）不需要；
    # 套反向代理（Nginx/云LB）且由代理覆写该头时打开，否则客户端可伪造 IP 绕过限流。
    rate_limit_trust_forwarded_for: bool = False

    # ---------- 响应缓存（原系统同款 5 分钟缓存思路）----------
    # 只缓存"重查询 + 结果不随用户变"的端点：热门榜/年代趋势/情感统计。
    # TTL 到期自然刷新；用户维度数据（for-you/评分/想看）一律不缓存。
    cache_ttl_seconds: int = 300

    # ---------- 数据源 ----------
    tmdb_api_key: str = ""
    tmdb_lang: str = "zh-CN"
    tmdb_region: str = "CN"
    tmdb_base: str = "https://api.themoviedb.org/3"

    # ---------- 数据源：IMDb Datasets（阶段 1b）----------
    # IMDb 官方公开数据集，无需 Key，每天更新：https://datasets.imdbws.com/
    imdb_dataset_dir: str = ""          # 留空 = <data_lake>/imdb_datasets
    imdb_min_votes: int = 1000          # 只保留评分人数≥此值的影片（内存与数据量的总闸门）
    imdb_min_rating: float = 0.0        # 评分下限，0 = 不限制
    imdb_title_types: str = "movie"     # 逗号分隔：movie / tvMovie / short …
    imdb_scan_report_every: int = 0     # >0 时每扫 N 行报一次进度，0 = 用内置默认值

    # ---------- 数据源：Wikidata / Wikipedia（阶段 1c）----------
    # 两者都是公开开放数据，无需 Key。Wikimedia 要求带可识别的 User-Agent。
    wikidata_endpoint: str = "https://query.wikidata.org/sparql"
    wikipedia_api: str = "https://zh.wikipedia.org/w/api.php"
    wikidata_user_agent: str = "YingJianZhiSou/0.1 (course project)"
    wikidata_batch: int = 40          # 每条 SPARQL 塞多少个 id（VALUES 太多会触发查询超时）
    wikidata_sparql_limit: int = 3000  # SPARQL 结果的 LIMIT 保护，防止某个条目爆出上万行
    # WDQS 的 429 多半是「出口 IP 被临时封禁」，重试再多也没用，
    # 所以重试次数刻意压到 2，避免白白等上几分钟（失败时会给可操作提示）
    wikidata_max_retries: int = 2
    wiki_extract_chars: int = 1500    # 维基摘要截断长度（阶段 4 情感/主题分析要留够文本）
    wiki_min_interval: float = 0.5    # Wikimedia 限速更严，给 2 req/s

    # ---------- 数据源：Kaggle 公开影评（阶段 1e）----------
    # 默认是 Stanford Large Movie Review Dataset 的 Kaggle 镜像：
    # 5 万条 IMDb 影评 + 情感二分类，约 66 MB，公开可匿名下载。
    # 注意：需求里那行 kagglehub 代码给的 kunwarakash/imdbdatasets
    # **不是影评**，是 IMDb 官方 TSV 数据集的镜像（5.7 GB，与阶段 1b 重复）。
    # 执行 `python -m ingest.run_collect kaggle --list` 可以看到对比说明。
    kaggle_dataset: str = "lakshmi25npathi/imdb-dataset-of-50k-movie-reviews"
    kaggle_dataset_dir: str = ""      # 留空 = <data_lake>/kaggle_reviews/<handle 转义>
    kaggle_min_chars: int = 0         # 正文短于此长度就丢弃（0 = 不丢）
    kaggle_lang: str = "en"           # 影评语言，写进记录便于后续分语言检索
    kaggle_text_col: str = ""         # 手动指定正文列名（留空 = 自动识别）
    # Kaggle 凭证：仅本机用，不入库。优先读 .env，其次 ~/.kaggle/kaggle.json，
    # 再次 KAGGLE_USERNAME/KAGGLE_KEY 环境变量。公开数据集可留空匿名下载。
    kaggle_username: str = ""
    kaggle_key: str = ""

    # ---------- 数据源：Letterboxd（阶段 2 主力爬虫）----------
    # 无官方公开 API，只抓取「公开可见影评页」；合规红线：
    # 遵守 robots.txt、≤1 req/s、不采 PII（用户名只存哈希）、不碰登录墙。
    letterboxd_min_interval: float = 1.0   # 每次请求最小间隔（秒），即 ≤1 req/s
    letterboxd_max_pages: int = 5          # 每部电影最多翻几页影评
    letterboxd_max_reviews: int = 0        # 单次采集最多影评数（0 = 不限）
    letterboxd_max_films: int = 0          # 最多采几部电影（0 = 不限）
    letterboxd_seed_file: str = ""         # 种子文件（jsonl，含 tmdb_id 或 slug 字段）
    letterboxd_user_agent: str = (
        "Mozilla/5.0 (compatible; YingJianZhiSou/0.1; course project; "
        "+https://github.com/yingjian-zhisou) Python-urllib"
    )

    # ---------- 数据源：RSS 影视新闻（方案 #4）----------
    # 公开 RSS，即授权再分发；保留 outlet 署名与原文 link 即可。
    # 轮询间隔保守：默认 30 分钟（1800s）级别，采集时按 --min-interval 控制礼貌节流。
    rss_min_interval: float = 5.0    # 相邻 feed 之间最小间隔（秒），礼貌限速
    rss_timeout: int = 30
    rss_feeds: str = (
        "Variety|https://variety.com/feed/;"
        "THR|https://www.hollywoodreporter.com/feed/;"
        "Deadline|https://deadline.com/feed/"
    )

    # ---------- 数据源：Metacritic 影评（方案 #3）----------
    # 无官方公开 API，只抓取「公开可见的影评页」（critic-reviews / user-reviews）。
    # 合规红线：遵守 robots.txt、礼貌限速、不采 PII（用户名只存哈希）、不碰登录墙。
    # ⚠ Metacritic 反爬很强（PerimeterX/HUMAN），裸 httpx 大概率被拦；
    #   实时采集请用 --browser 走 Playwright 真实浏览器（属正常采集手段，不绕验证码）。
    metacritic_min_interval: float = 2.0  # 每次请求最小间隔（秒），Metacritic 反爬严，给 0.5 req/s
    metacritic_max_pages: int = 5         # 每部电影每个类型（critic/user）最多翻几页
    metacritic_max_reviews: int = 0       # 单次采集最多影评数（0 = 不限）
    metacritic_max_films: int = 0         # 最多采几部电影（0 = 不限）
    metacritic_user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    )

    # ---------- 数据源：中文公开影评数据集（方案 #5，禁豆瓣）----------
    # 复用 Kaggle 解析能力（CSV/TSV/JSONL 自适应列名 + 流式），语言固定 zh。
    # 严禁采集豆瓣数据；只收公开、可授权再分发的中文语料（CC / 教学许可 / 公开数据集）。
    # 默认走「本地文件导入」（沙箱无需联网）；给出 --handle 才走 Kaggle 下载（需凭证）。
    chinese_reviews_dir: str = ""   # 本地中文影评文件/目录；留空 = 由 CLI --dir 指定
    chinese_min_chars: int = 5      # 中文正文短于此长度（字）就丢弃（中文无空格，按字计）
    chinese_lang: str = "zh"        # 影评语言标记，写进记录便于阶段 4 的 en/zh 跨文化对比

    # ---------- 采集行为 ----------
    # 代理策略：留空 = 跟随系统环境变量；填 direct = 强制直连不走代理；填 URL = 走指定代理
    collector_proxy: str = ""
    # 图片代理出口：后端 /api/v1/img 转发 TMDB 海报时走的代理。
    # image.tmdb.org 直连不通（被墙），浏览器自己没有代理时海报会全部 404，
    # 所以让后端代取。留空 = 直连；填 URL = 走指定代理。
    image_fetch_proxy: str = ""
    tmdb_min_interval: float = 0.25   # 每次请求最小间隔（秒），礼貌限速，约 4 req/s
    tmdb_max_retries: int = 4
    tmdb_discover_pages: int = 3      # 每次 discover 拉几页（每页 20 部）
    tmdb_min_vote_count: int = 50     # 过滤掉无人评分的冷门片

    # ---------- 数据湖 ----------
    data_lake: str = "./data_lake"

    # ---------------- 派生属性 ----------------

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def es_host_list(self) -> list[str]:
        return [h.strip() for h in self.es_hosts.split(",") if h.strip()]

    @property
    def data_lake_path(self) -> Path:
        p = Path(self.data_lake)
        return p if p.is_absolute() else (PROJECT_ROOT / p).resolve()

    def lake(self, *parts: str) -> Path:
        """取数据湖下的路径，并自动建好它需要的目录。

        同时支持目录与文件两种用法：
            settings.lake("raw", "tmdb")                  -> 建目录 raw/tmdb/
            settings.lake("raw", "tmdb", "movie_1.json")  -> 只建父目录 raw/tmdb/，返回文件路径

        判断规则：最后一段带后缀名（如 .json / .jsonl）就当成文件。
        早期版本无条件 mkdir，会把 genre_list.json 建成一个同名目录，
        采集时读盘报 PermissionError —— 已修。
        """
        path = self.data_lake_path.joinpath(*parts)
        if path.suffix:
            path.parent.mkdir(parents=True, exist_ok=True)
        else:
            path.mkdir(parents=True, exist_ok=True)
        return path


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
