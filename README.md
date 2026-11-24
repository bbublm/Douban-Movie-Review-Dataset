# 电影盒子 · 多源影评大数据检索与趣味发现平台

> 课程项目 · 网络爬虫 + 大数据分析 + 可视化平台
> 技术栈：Python / FastAPI / Elasticsearch 8.x / Vue3 / ECharts / Leaflet / Docker

**数据源全部为公开 API 与开放数据集**（TMDB API、IMDb Datasets、Wikidata SPARQL、
Wikipedia API、Kaggle 公开影评），不涉及任何反爬平台。

## 与原有系统的关系

本平台是在 yuan 原有的**电影推荐系统（Flask + SQL Server + Jinja 模板 + Chart.js，
git 提交 `9723066`）** 基础上扩展的大数据版本：原系统作蓝本，新栈承载——
继承原系统的信息架构（导航分工、页面组织）与棕灰主题视觉，把底座换成
FastAPI + Elasticsearch + Vue3，数据源从关系库小批量数据换成多源开放大数据。
上一代系统的代码、SQL Server 脚本与界面蓝图快照已于 2026-10-22 整体清理出仓库，
仅保留仍在使用中的种子片库资产（`data/web_movies.json` 等，见下方目录结构）。

---

## 阶段进度

| 阶段 | 内容 | 状态 |
|---|---|---|
| 0 | 工程基建 + ES 环境打通 | ✅ 已完成 |
| 1a | TMDB API 采集（含复用已有 120 部片库） | ✅ 已完成 |
| 1b | IMDb Datasets 采集（全程流式，峰值内存 < 200 MB） | ✅ 已完成 |
| 1c | Wikidata SPARQL + Wikipedia API 采集（中文名/导演/摘要/拍摄地坐标） | ✅ 已完成 |
| 1e | Kaggle 公开影评采集（5 万条真实影评，全程流式） | ✅ 已完成 |
| 2a | 数据清洗融合（多源合一 + 影评清洗 + 弱关联） | ✅ 已完成 |
| 2b | ES 索引建设（IK 中文分词 + 别名切换 + 批量导入） | ✅ 已完成 |
| 3 | FastAPI 混合检索 / 分面 / 高亮 | ✅ 已完成 |
| 4 | 情感分析 + 主题分析（自归纳情感词典，留出集准确率 83.56%） | ✅ 已完成 |
| 5 | Vue3 + ECharts 可视化大屏（继承原系统仪表盘信息架构 + 棕灰主题） | ✅ 已完成（6 视图 + 21 组件，走查 13/13 全过） |
| 5.5 | 前端按功能清单重构（Hero 首页/混搭器/分析大屏）+ 真实数据重建 + 图片代理 | ✅ 已完成（488 部真实电影 · 781 处拍摄地坐标 · 走查 14/14） |
| 6 | 趣味功能 + 原系统功能迁移（登录/评分/推荐/想看）+ 生产可用性（限流/缓存/探针/监控） | ✅ 已完成（107 项离线自检 + 45 项后端实测 + 14 项前端走查全过） |
| 7 | 全栈 Docker 化 + 交付 | ✅ 已完成（三容器一键部署，干净卷实测自动导索引 + 走查 14/14） |

---

## 目录结构

```
movie-recommendation-system-main/
├── docker-compose.yml        全栈编排（ES + 后端 + 前端，见「Docker 一键部署」）
├── docker/                   镜像构建
│   ├── elasticsearch/        官方 ES + IK 中文分词插件
│   ├── backend/              FastAPI 镜像（运行时依赖子集 + 数据打进镜像 + 入口三段式）
│   └── frontend/             Vite 构建 + Nginx 托管（多阶段，SPA fallback + /api 反代）
├── .env / .env.example       本平台环境变量（.env 不入库）
├── requirements.txt          本平台 Python 依赖
│
├── common/                   共享层
│   ├── settings.py           全局配置（backend 与 ingest 共用一份）
│   ├── es_client.py          ES 客户端工厂（同步 / 异步）
│   └── meminfo.py            跨平台峰值内存读数（无额外依赖）
│
├── backend/                  FastAPI 服务
│   ├── main.py               应用入口
│   ├── schemas/search.py     检索请求 / 响应模型（Pydantic）
│   ├── services/
│   │   ├── query_builder.py  ★ 纯函数：检索参数 → ES DSL（可离线自检）
│   │   └── search_service.py 执行查询 + ES 结果 → 响应模型
│   ├── api/v1/
│   │   ├── router.py         v1 路由汇总
│   │   ├── health.py         健康检查
│   │   └── search.py         检索接口（电影 / 影评 / 联想 / 详情）
│   └── static/
│       ├── index.html        浏览器自检页
│       └── search.html       检索演示页（阶段 5 前端之前的可视化验证）
│
├── ingest/                   数据采集与治理
│   ├── http.py               限速 + 退避重试 + 原始响应落盘的 HTTP 客户端
│   ├── jsonl_io.py           数据湖 interim 层通用 JSONL 读写（流式）
│   ├── schema.py             统一记录 schema（电影 CORE_FIELDS + 影评 REVIEW_FIELDS）
│   ├── sources/douban_review_dataset.py  本地豆瓣评论 CSV 导入（不联网）
│   ├── seed.py               复用旧片库 data/web_movies.json（种子导入 + 反查 tmdb_id）
│   ├── wiki.py               维基结果归一化与合拢（纯函数，可离线测）
│   ├── run_collect.py        采集命令行入口（seed / tmdb / imdb / wiki / kaggle）
│   └── sources/
│       ├── tmdb.py           TMDB 采集器 + 归一化
│       ├── imdb_datasets.py  IMDb 官方数据集流式采集（两遍扫描）
│       ├── wikidata.py       Wikidata SPARQL 采集（批量 + 缓存 + 聚合）
│       ├── wikipedia.py      Wikipedia API 摘要采集（批量 + 别名映射）
│       └── kaggle_reviews.py Kaggle 影评流式采集（自适应列识别 + HTML 清洗）
│
├── transform/                清洗融合层（阶段 2，纯离线：文件 → 文件）
│   ├── keys.py               归一化主键（判断两条记录是不是同一部电影）
│   ├── clean.py              字段级清洗（空值判定 / 数值归一 / 列表去重）
│   ├── movies.py             多源电影记录融合（增量桥接合并 + 字段优先级）
│   ├── reviews.py            影评再清洗 + 与电影弱关联
│   └── run_transform.py      融合命令行入口（movies / reviews / all）
│
├── index/                    索引层（阶段 2b：文件 → ES）
│   ├── mappings.py           settings + mapping（分析器探测 / IK 降级 / 文档整形）
│   ├── builder.py            索引生命周期：版本化建索引、别名原子切换、流式 bulk
│   └── run_index.py          索引命令行入口（build / import / stats / check / drop）
│
├── analysis/                 分析层（阶段 4：processed → data_lake/analysis/）
│   ├── lexicon.py            分词、否定/程度规则、从标注语料归纳情感词典
│   ├── sentiment.py          情感打分 + 用 Kaggle 标签评估准确率
│   ├── topics.py             词项统计、关键词排名、TF-IDF、significant_terms DSL
│   └── run_analysis.py       分析命令行入口（lexicon / report / topics / score / check）
│
├── tests/                    离线自检（不联网也能验采集链路）
│   ├── fixtures/             真实 API 响应固件
│   ├── test_ingest_offline.py
│   ├── test_imdb_offline.py
│   ├── test_wiki_offline.py
│   ├── test_kaggle_offline.py
│   ├── test_transform_offline.py  阶段 2a 融合自检
│   ├── test_index_offline.py      阶段 2b 索引自检
│   ├── test_search_offline.py     阶段 3 检索自检
│   ├── test_analysis_offline.py   阶段 4 分析自检
│   └── test_features_offline.py   阶段 6 后端自检（trends/用户/推荐/趣味/运维，107 项）
│
├── frontend/                 Vue3.5 + Vite7（阶段 5 + 5.5 重构，11 视图，无 UI 框架）
│   └── src/
│       ├── api/index.js      fetch 封装（token 注入 / 401 事件 / 错误透传）
│       ├── composables/      useAuth 登录态单例 · useToast · useMovieActions · useSearchHistory · useBlindBox
│       ├── views/            Home 首页 / Search 检索 / Movie 详情 / Mix 混搭器 /
│       │                     Analytics 分析大屏 / Insights 影评洞察 / Discover 为你推荐 / Login / Me / About
│       └── components/       search 检索族 · insights 图表族 · box 盲盒 · layout 导航页脚
├── scripts/                  工具脚本
│   ├── check_env.py          环境自检
│   ├── verify_auth_live.py   用户模块实测（注册/登录/改密/权限，12 步）
│   ├── verify_recommend_live.py  推荐+评分+趣味实测（全链路，33 项）
│   ├── verify_ops_live.py    生产可用性实测（限流/缓存/探针/想看，36 项）
│   └── verify_frontend_walkthrough.js  前端 puppeteer 全流程走查（14 项，参数：目标 BASE URL）
│
├── data_lake/                数据湖
│   ├── raw/                  API 原始落盘，可重跑
│   ├── interim/              清洗中间结果
│   ├── processed/            可直接入库的最终数据
│   └── analysis/             阶段 4 分析产物（词典 / 主题榜 / 评估报告）
│
├── data/                     从上一代系统继承的片库资产
│   ├── web_movies.json       120 部中文片库（95 部带 tmdb_id），本平台种子片库
│   ├── chinese_title_map.py  英文片名 → 中文译名映射（ingest 在用）
│   └── chinese_domestic_movies.py  国产片补充数据
```

---

## 快速开始（本平台）

### 方式 A · Docker 一键部署（推荐，一条命令跑通全栈）

```bash
docker-compose up -d
```

一条命令起来三个容器（ES + 后端 + 前端），**首次启动自动完成**：

1. 等 ES 就绪（compose 健康检查 + 入口再兜一层等待）；
2. 检测到索引缺失时，用**镜像内 `data_lake/processed/` 的全量数据**自动建库导数据
   （492 部电影 + 52,223 条影评，幂等可重跑；另有 news / 院线热映 / 预告片三个小索引）；
3. 启动 uvicorn，nginx 托管前端并反代 `/api`。

然后打开：

| 入口 | 地址 | 说明 |
|---|---|---|
| 平台首页 | <http://localhost:8080> | 前端（nginx 托管，SPA 深链接不 404） |
| 后端文档 | <http://localhost:8000/docs> | Swagger UI |
| 健康检查 | <http://localhost:8000/api/v1/health> | 含 ES 连通性 |
| Kibana（可选） | <http://localhost:5601> | `--profile tools up -d` 才起 |

> 全量数据（processed 的 492 部 / 52,223 条 + analysis 打分明细 + 三个小索引源）**已随仓库入库**，
> 并在 build 时打进后端镜像：clone 后直接 `up` 就能用，**不需要**在宿主机准备数据文件或先跑采集管线。
> 仓库内 `reviews.jsonl` 约 93 MB，clone 体积因此较大；这是为了让别人一次跑通而做的取舍。
> 想清库重来：`docker-compose down -v && docker-compose up -d`，会重新自动导一遍。

### 方式 B · 本机开发（采集 / 改代码 / 调参）

#### 1. 启动 Elasticsearch

```bash
# 只起 ES（推荐，轻量）
docker-compose up -d elasticsearch

# 需要 Kibana 做数据探索时
docker-compose --profile tools up -d
```

首次会**构建镜像**：拉官方 ES 镜像（约 1.1 GB）+ 装 IK 中文分词插件（约 2 MB）。
插件写进了 `docker/elasticsearch/Dockerfile`，所以重建容器、换机器部署都不会丢。

> 本机已经用 `docker exec` 给运行中的容器装过 IK 了；
> 但那种装法只活在当前容器里，`down` 掉重建就没了 —— 所以又补了 Dockerfile。
> 想跳过构建（比如没网），把 `docker-compose.yml` 里的 `build:` 段换成 `image:` 即可，
> 索引层会自动降级到内置 cjk 分析器，功能不缺，只是中文分词质量下降。

查看状态与插件：

```bash
docker-compose ps
docker-compose logs -f elasticsearch
curl http://localhost:9200/_cat/plugins?v      # 应能看到 analysis-ik
```

#### 2. 创建虚拟环境并安装依赖

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

> 本项目要求 Python `>=3.10`。本机实测 3.13 可正常安装全部依赖。

#### 3. 配置环境变量

```bash
copy .env.example .env      # Linux/macOS: cp .env.example .env
```

然后在 `.env` 里填写 `TMDB_API_KEY`。

#### 4. 环境自检（推荐先跑这个）

```bash
python scripts/check_env.py
```

全绿（`N/N 项通过`）再往下走。

#### 5. 启动后端

```bash
uvicorn backend.main:app --reload --port 8000
```

- 自检页 <http://localhost:8000/>
- Swagger 文档 <http://localhost:8000/docs>
- 健康检查 <http://localhost:8000/api/v1/health>

---

## 阶段 0 验证清单

| # | 验证项 | 命令 / 操作 | 期望结果 |
|---|---|---|---|
| 1 | ES 容器健康 | `docker-compose ps` | `yjzs-es` 状态 `Up (healthy)` |
| 2 | ES 直连 | `curl http://localhost:9200` | 返回含 `"version":{"number":"8.15.3"}` |
| 3 | 集群状态 | `curl http://localhost:9200/_cluster/health?pretty` | `"status": "green"` |
| 4 | 依赖就绪 | `python scripts/check_env.py` | 全部 `[ OK ]` |
| 5 | 后端起来 | `curl http://localhost:8000/api/v1/health` | `"status":"ok"`，`elasticsearch.ok=true` |
| 6 | 自检页 | 浏览器打开 <http://localhost:8000/> | 指标全部绿色徽章 |

---

## 阶段 1a · TMDB 采集

### 命令

```bash
# 1. 先把旧系统的 120 部片库并进来（纯本地，不联网）
python -m ingest.run_collect seed

# 2. 用 TMDB 给缺 id 的种子记录补 tmdb_id / 海报 / 评分（联网）
python -m ingest.run_collect seed --resolve --limit 30

# 3. TMDB 发现式采集（按热度拉新片）
python -m ingest.run_collect tmdb --pages 3 --limit 60
python -m ingest.run_collect tmdb --pages 2 --sort rating --year-from 2015   # 换排序 / 限定年份

# 公共参数（写在子命令前后都可以）
#   --force                    忽略 raw 缓存，强制重新请求
#   --proxy direct             强制直连（无视系统代理）
#   --proxy http://127.0.0.1:7890   走指定代理
```

### 产物

```
data_lake/raw/tmdb/genre_list.json         类型字典（id → 中文名）
data_lake/raw/tmdb/discover/page_{n}.json  发现结果，文件里带请求参数指纹
data_lake/raw/tmdb/movie/{tmdb_id}.json    单片详情
data_lake/raw/tmdb/search/{关键词}.json    搜索结果
data_lake/interim/seed_movies.jsonl        旧片库统一结构
data_lake/interim/tmdb_movies.jsonl        TMDB 采集结果
```

### 断点续跑原理

每个 raw 文件都是一个信封：

```json
{ "_request": { "path": "/movie/550", "params": { ... } }, "_response": { ... } }
```

重跑时先比对 `params`：一致就直接读盘（不发请求），不一致才重新拉。
所以采集中途 Ctrl+C，下次接着跑即可；改排序参数也不会读到脏缓存。

### 阶段 1a 验证清单

| # | 验证项 | 命令 | 期望结果 |
|---|---|---|---|
| 1 | 采集链路离线自检 | `python tests/test_ingest_offline.py` | `20/20 项通过` |
| 2 | 种子片库导入 | `python -m ingest.run_collect seed` | `记录数: 120`，写出 120 行 |
| 3 | 原始响应落盘 | `ls data_lake/raw/tmdb/movie` | 出现 `{tmdb_id}.json` 文件 |
| 4 | 断点续跑 | 同一条采集命令再跑一次 | 打印 `命中缓存 N 次`，`API 调用 0 次` |
| 5 | 采集结果可读 | `head -1 data_lake/interim/tmdb_movies.jsonl` | 单行 JSON，含 `title_zh` / `genres_zh` / `poster_url` |

> 第 2~5 项需要能访问 `api.themoviedb.org`。若报 `ConnectTimeout`，加 `--proxy http://127.0.0.1:端口`。

---

## 阶段 1b · IMDb Datasets 采集

数据源是 IMDb 官方公开数据集 <https://datasets.imdbws.com/>：免费、无需 API Key、
每天更新全量快照，明确允许科研与教学使用。（IMDb 的官方 API 早已下线，
这份数据集反而比 API 更适合做分析。）

### 命令

```bash
# 0. 先看清单，明确各文件体积（不下载、不联网）
python -m ingest.run_collect imdb --list

# 1. 离线跑通链路：造一份合成小数据集，验证流程与内存占用
python -m ingest.run_collect imdb --demo

# 2. 真实采集：下载必要数据集（ratings 7 MB + basics 190 MB）
python -m ingest.run_collect imdb --download --min-votes 1000

# 3. 只要票数最高的 2 万部（演示用，输出更快、更小）
python -m ingest.run_collect imdb --limit 20000

# 4. 额外补导演名（要多下 crew 60 MB + names 250 MB）
python -m ingest.run_collect imdb --with-directors

# 5. 已手动下载好数据集时，直接指定目录
python -m ingest.run_collect imdb --dir D:\imdb_datasets

# 常用参数
#   --min-votes 1000     只保留评分人数≥此值的影片（默认 1000）
#   --min-rating 7.0     评分下限（默认不限）
#   --types movie,tvMovie  保留的作品类型（默认 movie，过滤掉剧集/短片）
#   --include-adult      保留成人片（默认过滤）
#   --force              忽略本地文件，强制重新下载
```

### 内存与磁盘（你关心的部分）

| 项 | 数值 |
|---|---|
| **采集峰值内存** | **实测 47 MB**（进程含解释器与依赖）；纯流式解析部分实测 **9.6 MB/5 万行** |
| 内存随数据量变化 | **不变**。从 5 万行到 1200 万行，占用基本恒定（架构决定的） |
| 磁盘：默认下载量 | **约 200 MB**（`title.ratings.tsv.gz` 7 MB + `title.basics.tsv.gz` 190 MB） |
| 磁盘：额外解压占用 | **0**。gzip 边读边丢，从不把 900 MB 的明文 tsv 落到盘上 |
| 磁盘：可选加装 | crew + names 再 310 MB；akas / principals 默认不下（400 / 600 MB） |
| 常驻内存大户 | 只有 Elasticsearch 容器（堆 1 GB，在 `.env` 的 `ES_JAVA_OPTS` 里可调） |

> 对比：用 `pd.read_csv("title.basics.tsv.gz")` 一把梭的峰值内存是 **4~5 GB**。
> 本项目改成两遍扫描，所以普通笔记本也跑得动。

### 为什么这样就不吃内存

```
第 1 遍  扫 ratings（解压后 25 MB / 150 万行）
         → 只留 票数≥阈值 的条目做成 dict，键用 int(tconst[2:]) 省一半内存
         → 若给了 --limit，用大小为 N 的小顶堆只留票数最高的 N 条（堆大小恒定）
         → 结果：几万条，约 10~30 MB

第 2 遍  扫 basics（解压后 900 MB / 1200 万行）
         → 逐行判断是否命中；命中就立刻转记录、立刻写 JSONL
         → 从不攒成 list，同时只存在一条记录
```

### 产物

```
data_lake/imdb_datasets/title.ratings.tsv.gz   评分与票数（压缩包，保留可复用）
data_lake/imdb_datasets/title.basics.tsv.gz    片名/年份/时长/类型
data_lake/interim/imdb_movies.jsonl            归一化后的统一结构记录
```

一条记录的字段示例（与 TMDB / 旧片库**字段名完全一致**，便于阶段 2 融合）：

```json
{"imdb_id":"tt0137523","tmdb_id":null,"title":"Fight Club","title_zh":null,
 "release_year":1999,"runtime":139,"genres_zh":["剧情"],"genres_en":["Drama"],
 "vote_average":8.8,"vote_count":2100000,"release_date":null,
 "source":"imdb","title_type":"movie","imdb_rating":8.8,"imdb_votes":2100000}
```

### 三个设计要点（答辩可以讲）

1. **列名从表头读，不硬编码列序号** —— IMDb 调整列顺序时解析不会错位（自检里有一条专门测乱序表头）。
2. **`\N` 统一转 None、列数不符的行跳过** —— 下载被中断的残缺文件不会污染结果。
3. **数据缺失就如实留空** —— IMDb 数据集只有年份没有精确上映日，`release_date` 填 `null` 而不是伪造成 `1999-01-01`，避免污染后续日期字段。

### 阶段 1b 验证清单

| # | 验证项 | 命令 | 期望结果 |
|---|---|---|---|
| 1 | 采集链路离线自检 | `python tests/test_imdb_offline.py` | `36/36 项通过` |
| 2 | 数据集清单 | `python -m ingest.run_collect imdb --list` | 列出 6 个文件及体积 |
| 3 | 缺数据集提示 | `python -m ingest.run_collect imdb` | 打印下载地址与三种可选做法，不报错 |
| 4 | 离线跑通全链路 | `python -m ingest.run_collect imdb --demo --with-directors` | 写出 `imdb_movies.demo.jsonl`，打印峰值内存 |
| 5 | 内存不随数据量涨 | 自检第 11 组 | `实测 9.6 MB`，两个规模都是这个量级 |
| 6 | 真实采集 | `python -m ingest.run_collect imdb --download --limit 20000` | 写出 2 万条，峰值内存仍 < 200 MB |
| 7 | 结构对齐 | `python tests/test_imdb_offline.py`（第 6 组） | TMDB / 旧片库 / IMDb 三个源都覆盖 `CORE_FIELDS` |

> 第 6 项需要能访问 `datasets.imdbws.com`（约 200 MB 下载）。
> 本机沙箱无法直连外网，这一步需要你在本机执行验证。

> **耗时预期**：真实的 `title.basics.tsv.gz` 有 1200 万行，两遍扫描大约 **3~6 分钟**
> （瓶颈是 gzip 解压 + Python 逐行解析，不是内存）。跑一次存下来就不必再跑。

---

## 阶段 1c · Wikidata + Wikipedia 采集

前两个源都缺同一批东西：**中文片名、导演、剧情摘要、拍摄地坐标**。
TMDB 的中文覆盖不全，IMDb 数据集里**完全没有**人物关系与地理信息。
阶段 1c 从两个公开开放数据源把它们补齐：

| 源 | 补什么 | 为什么非它不可 |
|---|---|---|
| **Wikidata**（SPARQL） | 中文标签、导演、类型、出品国、公映日期、片长、拍摄地坐标等扩展元数据 | 免费稳定的结构化元数据来源 |
| **Wikipedia**（MediaWiki API） | 剧情摘要（首段纯文本） | TMDB 的 overview 只有一两句，做阶段 4 主题分析太薄 |

> 原路线图把 1c / 1d 分成「Wikidata」「Wikipedia」两阶段，
> 实际实现合并为 1c：因为 Wikipedia 的条目名要靠 Wikidata 的 zhwiki sitelink 才能精确定位，
> 拆开反而要重复一遍实体对齐。1e（Kaggle 影评）仍独立。

### 命令

```bash
# 0. 看会读哪些 interim 文件、预计多少批请求（不联网）
python -m ingest.run_collect wiki --list

# 1. 离线跑通链路（用固件，不联网、不等 SPARQL 往返）
python -m ingest.run_collect wiki --demo

# 2. 真实采集：自动从已有 interim 记录里取主键
python -m ingest.run_collect wiki

# 3. 只要 Wikidata（中文名/导演/拍摄地），跳过维基摘要（省一半请求）
python -m ingest.run_collect wiki --no-wikipedia

# 4. 只补前 30 部，控制请求量
python -m ingest.run_collect wiki --limit 30 --batch 20

# 5. 指定输入文件（默认按 tmdb → imdb → seed 顺序自动找）
python -m ingest.run_collect wiki --from tmdb_movies.jsonl,imdb_movies.jsonl
```

### 产物

```
data_lake/raw/wikidata/core/{md5}.json        SPARQL 核心信息原始响应（按查询语句指纹命名）
data_lake/raw/wikidata/geo/{md5}.json         SPARQL 拍摄地坐标原始响应
data_lake/raw/wikipedia/extract/{md5}.json    维基摘要原始响应（按标题集合指纹命名）
data_lake/interim/wiki_movies.jsonl           归一化结果（含 filming_locations）
```

一条记录的「维基特色字段」（其余字段与 TMDB / IMDb / 旧片库完全同名）：

```json
{"imdb_id":"tt0137523","tmdb_id":550,"title":"搏击俱乐部","title_zh":"搏击俱乐部",
 "release_date":"1999-09-10","release_year":1999,"runtime":139,
 "director":"大卫·芬奇","overview":"《搏击俱乐部》是一部 1999 年上映的美国剧情片…",
 "wikidata_qid":"Q190050","wikipedia_url":"https://zh.wikipedia.org/wiki/搏击俱乐部",
 "filming_locations":[{"name":"洛杉矶","kind":"filming","qid":"Q65","lat":34.05223,"lon":-118.24368},
                      {"name":"纽约","kind":"narrative","qid":"Q1297","lat":40.7127,"lon":-74.006}],
 "locations_with_coords":[…两处…],"source":"wikidata+wikipedia"}
```

### 三个设计要点（答辩可以讲）

1. **聚合放在 Python，不放在 SPARQL**。
   直觉写法是用 `GROUP_CONCAT` 在 SPARQL 里把导演/类型/国家拼成一个字段，
   但实测（query.wikidata.org 真实响应）**`GROUP_CONCAT` 配合 `wikibase:label` 会返回空字符串** ——
   标签服务生成的变量在聚合函数里取不到值。改成「SPARQL 只做关联查询返回多行，
   Python 侧按主键聚合」后，聚合逻辑还顺带变成了可离线自检的纯函数。

2. **WKT 坐标是 `(经度 纬度)`，不是 `(纬度 经度)`**。
   Wikidata 返回 `Point(-118.24368 34.05223)`，第一位是经度。
   顺序写反整批坐标会落到南极洲 —— 地图上一眼能看出来，躺在 JSON 里几乎发现不了。
   统一在解析入口翻转成 `(lat, lon)`，并配一条自检守着。

3. **中文片名不能盲信标签服务**。
   `bd:serviceParam wikibase:language "zh-hans,zh,en"` 在条目**没有中文标签时会静默回退成英文**。
   所以归一化时用 `has_han()` 判断「这个标签真的是中文吗」，
   不是中文就留 `null` 交给阶段 2 用 TMDB 中文名 / 旧片库译名补，绝不把英文当中文写进去。

另外两个工程细节：
- **批量 `VALUES (?prop ?key)`** —— 把「用 IMDb 主键查」和「用 TMDB 主键查」合并成同一条 SPARQL，
  主键成对放进 VALUES，几百部电影只需十几次请求（WDQS 对请求频率很敏感）。
- **`exlimit=max` 必须显式写** —— MediaWiki 默认 `exlimit=1`，
  一次问 20 个标题只会给**第一个**返回正文，另外 19 个是空串。不写这个参数会得到一个静默的大坑。

### 与其它源的衔接

Wikidata 里**刻意不采演员**（P161）：一个条目动辄二三十位演员，
拉进来会让 SPARQL 结果膨胀数倍，而 TMDB 的 credits 已经把主演给全了。
缺的演员、精确上映日、海报，阶段 2 融合时从 TMDB / IMDb 记录里按 `imdb_id` 回填。

### 阶段 1c 验证清单

| # | 验证项 | 命令 | 期望结果 |
|---|---|---|---|
| 1 | 采集链路离线自检 | `python tests/test_wiki_offline.py` | `54/54 项通过` |
| 2 | 输入来源与请求量预估 | `python -m ingest.run_collect wiki --list` | 列出文件就绪状态与预计批次数 |
| 3 | 离线跑通全链路 | `python -m ingest.run_collect wiki --demo` | 写出 `wiki_movies.demo.jsonl`，打印拍摄地统计 |
| 4 | 坐标顺序正确 | 自检第 1 组 | `(lat, lon) == (34.05223, -118.24368)` |
| 5 | 拍摄地有坐标 | `python -c "import json;[print(r['locations_with_coords']) for r in map(json.loads,open('data_lake/interim/wiki_movies.jsonl',encoding='utf-8'))]"` | 打印带经纬度的地点列表 |
| 6 | 格式对齐 | 自检「合拢」组 | 每条记录都覆盖全部 `CORE_FIELDS` |
| 7 | 真实采集 | `python -m ingest.run_collect wiki --limit 40` | 写出 `wiki_movies.jsonl`，非零中文名/导演/摘要 |
| 8 | 断点续跑 | 同一条命令再跑一次 | `SPARQL 请求 0 次，命中缓存 N 次` |

> 第 7 项需要能访问 `query.wikidata.org` 与 `zh.wikipedia.org`。
> 本机沙箱无法直连外网，这一步需要你在本机执行验证。

> **耗时预期**：每批 SPARQL 往返约 2~5 秒（WDQS 排队），40 个主键一批。
> 120 部电影 ≈ 3 批 × 2 轮（core + geo）≈ **30~60 秒**，维基摘要另加几秒。
> 采集结果全部落盘缓存，第二次跑是**秒级**。

---

## 阶段 1e · Kaggle 公开影评采集

影评是阶段 4 情感分析与主题分析的**唯一语料来源**。本阶段通过 kagglehub
下载公开数据集并归一化。

### ⚠️ 一个必须纠正的数据源问题

需求文档里给的那行代码用的是 `kunwarakash/imdbdatasets`，但**它不是影评数据集**。
查过它的官方元信息（`kaggle.com/api/v1/datasets/view/...`）后确认：

| | 需求里给的那个 | 本项目实际使用的 |
|---|---|---|
| handle | `kunwarakash/imdbdatasets` | `lakshmi25npathi/imdb-dataset-of-50k-movie-reviews` |
| 内容 | IMDb 官方 TSV 数据集的**第三方镜像**<br>（`title.basics.tsv` 那一套，描述原文：「Daily refreshed Dataset can downloaded from https://datasets.imdbws.com/」） | 5 万条 IMDb 影评 + `positive`/`negative` 情感标注 |
| 体积 | **5.46 GB** | **66 MB** |
| 有评论文本吗 | **没有** | 有 |
| 与已做阶段的关系 | 与**阶段 1b 完全重复**（同一份数据，还大 27 倍） | 与其它阶段互补 |

也就是说，用它既会把阶段 1b 白做一遍，又会让阶段 4 断粮。
所以换成了 Stanford Large Movie Review Dataset 的 Kaggle 镜像（情感分析领域最常用的公开基准）。
原来的那个 handle 没有删掉，登记在 `kaggle --list` 里并标注了原因 —— 便于答辩时讲清楚这个判断。

### 命令

```bash
# 0. 看有哪些影评数据集可选（不下载、不联网）
python -m ingest.run_collect kaggle --list

# 1. 离线跑通链路（造一份合成影评，不下 66 MB）
python -m ingest.run_collect kaggle --demo

# 2. 真实采集：首次自动下载约 66 MB（公开数据集可匿名下载，无需 Kaggle 账号）
python -m ingest.run_collect kaggle

# 3. 只要前 5000 条，并丢掉 20 字以下的短评
python -m ingest.run_collect kaggle --limit 5000 --min-chars 20

# 4. 换成别的数据集（带片名的烂番茄影评，可与 movies 索引弱关联）
python -m ingest.run_collect kaggle --dataset rotten
python -m ingest.run_collect kaggle --handle owner/dataset-name

# 5. 用本地已下载好的文件（不联网）
python -m ingest.run_collect kaggle --dir D:\kaggle_reviews --no-download

# 6. 导入项目根目录的本地豆瓣评论 CSV（不联网，仅匹配唯一片名）
python -m ingest.run_collect douban-dataset
python -m transform.run_transform reviews
python -m index.run_index import reviews

# 常用参数
#   --text-col review   手动指定正文列名（默认按候选表自动识别）
#   --no-dedupe         关闭按正文去重（默认开启）
#   --swap-labels       翻转 positive/negative（数据集用 0=positive 时用）
```

### 产物

```
data_lake/kaggle_reviews/<handle 转义>/IMDB Dataset.csv   数据集原始文件（66 MB）
data_lake/interim/reviews.jsonl                          49,578 条归一化影评（85 MB）
```

一条记录（`REVIEW_FIELDS` 共 17 个字段）：

```json
{"review_id":"rad4338936ec35683","text":"One of the other reviewers has mentioned…",
 "text_raw_len":1761,"text_len":1728,"word_count":304,
 "sentiment":"positive","sentiment_score":1.0,"rating":null,
 "movie_title":null,"movie_year":null,"imdb_id":null,
 "lang":"en","dataset":"lakshmi25npathi/imdb-dataset-of-50k-movie-reviews",
 "source":"kaggle","source_file":"IMDB Dataset.csv","row_index":0,
 "collected_at":"2026-10-14T13:29:24Z"}
```

### 实测结果（真实数据，非估算）

```
原始行数      : 50,000
写出记录数    : 49,578
跳过          : 重复 422
情感分布      : positive 24,882(50%)，negative 24,696(50%)
正文字符数    : 最短 32，中位 956，平均 1288，最长 13593
耗时          : 6.7s
峰值内存 53.4 MB   ← 流式解析，与数据集行数无关
```

**这 422 条重复是怎么来的？** 数据集里确实存在**正文完全相同**的影评（Kaggle 上传时没去重）。
本模块用「正文 sha1 → `review_id`」做主键，所以重复条目被自动合并成一条 ——
顺带解决了「重跑一次会不会把数据翻倍」这个所有采集脚本都会遇到的问题。

### 内存与磁盘（你关心的部分）

| 项 | 数值 |
|---|---|
| **采集峰值内存** | **实测 53 MB**（整进程含解释器 + 全部依赖） |
| 纯流式解析部分 | **3.7 MB / 3 万行**（自检第 9 组，tracemalloc 实测） |
| 内存随数据量变化 | **不变**。唯一随行数增长的是去重用的 hash 集合，约 100 字节/条（5 万条 ≈ 6 MB） |
| 磁盘：下载 | **66 MB**（一个 CSV） |
| 磁盘：归一化输出 | **85 MB**（JSONL） |
| 对比：`pd.read_csv` 一把读 | 峰值 **400 MB+**（5 万条长字符串全驻留 + dtype 推断） |

### 四个设计要点（答辩可以讲）

1. **列名自适应识别，不硬编码**。
   Kaggle 数据集列名五花八门（`review`/`text`/`content`/`comment`…，情感列有
   `sentiment`/`label`/`polarity`/`rating`…）。模块用候选表 + 优先级匹配自动推断，
   换数据集大概率不用改代码；实在认不出来还能 `--text-col` 手动指定。
   （`title` 这个列名有歧义 —— 影评语境里它更可能是**评论标题**而不是电影名，
   所以只要同时存在明确的正文列，就不把它当片名，宁可 `movie_title` 留空。）

2. **HTML 清洗的顺序不能反**。
   真实数据里 99% 的噪声是 `<br /><br />`，还有 `&quot;` `&amp;` 这类实体。
   必须**先 `html.unescape` 再去标签** —— 反过来的话，`&lt;b&gt;` 这种被转义过的标签
   会躲过标签正则，留在正文里变成 `"<b>"` 字面量，分词时多出一堆 `br`/`b` 词项。
   清洗效果实测：49,578 条正文中**真正的 HTML 标签残留 0 条**。
   （顺带一个有趣的发现：数据里有一句 `…see this movie EVER!</3` ——
   `</3` 是网络用语「心碎」，粗筛会把它误判成标签。标签正则要求有闭合的 `>`，
   正好避开了这个坑。）

3. **`review_id` 用内容 hash 而不是行号**。
   行号主键在「数据集更新、行序变化」时会全量错位，重复导入还会产生重复文档。
   内容 hash 天然幂等：同一篇影评永远是同一个 `_id`，写 ES 时直接覆盖。
   阶段 2 用它做 `_id`，重复导入不会让 `reviews` 索引翻倍。

4. **全链路流式，与内存纪律一致**。
   读一行 → 清洗 → 归一化 → 立刻 yield → 立刻写盘，从不把 5 万条记录攒成 list。
   这与 1b 的 IMDb 模块是同一套思路，整个工程不出现「把所有数据读进内存再处理」的写法。

### 阶段 1e 验证清单

| # | 验证项 | 命令 | 期望结果 |
|---|---|---|---|
| 1 | 采集链路离线自检 | `python tests/test_kaggle_offline.py` | `79/79 项通过` |
| 2 | 数据集清单 | `python -m ingest.run_collect kaggle --list` | 列出 3 个数据集，并标注 `kunwarakash/imdbdatasets` 不是影评 |
| 3 | 离线跑通全链路 | `python -m ingest.run_collect kaggle --demo` | 写出 `reviews.demo.jsonl`，打印峰值内存 |
| 4 | 真实采集 | `python -m ingest.run_collect kaggle` | `写出记录数 49,578`，情感各占 50% |
| 5 | HTML 清洗干净 | 见下方一行命令 | 输出 `真正的 HTML 标签残留 0 条` |
| 6 | 幂等性 | 同一条命令再跑一次 | 输出条数一致，不翻倍 |
| 7 | 内存不随数据量涨 | 自检第 9 组 | 3 万行实测 3.7 MB |

清洗效果自查：

```bash
python -c "import json,re;t=re.compile(r'<[a-zA-Z/][^>]{0,300}>')
n=bad=0
for l in open('data_lake/interim/reviews.jsonl',encoding='utf-8'):
    s=json.loads(l)['text'];n+=1;bad+=bool(t.search(s))
print(f'{n:,} 条正文中，真正的 HTML 标签残留：{bad} 条')"
```

### 与其它源的衔接

这份数据集**只有 `review` + `sentiment` 两列，没有片名、没有电影 id**（再次实测确认）。
所以 `reviews` 索引与 `movies` 索引之间**无法直接 JOIN**，这对本平台的影响是：

- **检索侧**：影评作为独立索引参与混合检索（正文全文检索 + 情感筛选 + 正负例对比），
  这是可用的，也是「多源影评检索」这个题目的核心。
- **分析侧**：它是阶段 4 情感分析 / 主题分析的核心语料 —— 5 万条带标注的真实影评，
  足够跑通朴素贝叶斯 / 词典法 / LDA 主题模型。
- **若以后要「影评挂到具体电影下」**：换用带片名列的数据集即可（`--dataset rotten`），
  本模块的列识别是自适应的，会自动填 `movie_title`，**不用改代码**。

---

## 阶段 2a · 数据清洗融合

### 这一步在解决什么问题

阶段 1 采完四个源之后，同一部电影会在 `interim` 里散成好几条：

```
seed_movies.jsonl   搏击俱乐部 / 无 tmdb_id / 有中文名和导演
imdb_movies.jsonl   Fight Club / tt0137523 / 只有评分
wiki_movies.jsonl   搏击俱乐部 / tt0137523 / 有维基摘要和拍摄地
```

每条都缺东西，但缺的**不是同一批**。阶段 2a 要做的就是：判断哪些记录其实
是同一部电影，然后每个字段取各源里最可信的那个值，合出一条完整记录。

### 为什么单独抽一层（而不是采集时顺手合并）

采集要联网、跑十几分钟、还可能被限流；融合是纯 CPU、几秒跑完。
两者揉在一起的话，改一条合并规则就得重跑整条采集链路 —— 根本没法迭代。

分开之后，`transform/` **不联网、不碰 ES、纯文件 → 文件**，可以随时重跑、
随便调参、离线单测，不消耗任何 API 配额。

### 命令

```bash
# 1. 电影融合：interim 各源 → processed/movies.jsonl（本层核心）
python -m transform.run_transform movies

# 2. 影评清洗 + 与电影弱关联 → processed/reviews.jsonl
python -m transform.run_transform reviews

# 3. 一把跑完
python -m transform.run_transform all

# 4. 先看看会读到什么、大概融合成多少部，不写盘
python -m transform.run_transform movies --dry-run

# 5. 只用真实采集产物（排除 --demo 造出来的演示数据）
python -m transform.run_transform all --no-demo

# 常用参数
#   --from-dir     输入目录（默认 data_lake/interim）
#   --out-dir      输出目录（默认 data_lake/processed）
#   --no-title-key 关闭「片名+年份」兜底键，只用 id 对齐（更严格，融合率更低）
#   --min-chars    影评清洗后短于此长度即丢弃（默认 20）
#   --limit        本次最多读入多少条（调试用）
```

### 产物

| 文件 | 内容 |
|---|---|
| `data_lake/processed/movies.jsonl` | 一部电影一条，多源字段已合并 |
| `data_lake/processed/reviews.jsonl` | 一篇影评一条，已清洗、已尝试关联到电影 |

成品记录在原有字段之外，多出这几项**血缘信息**：

| 字段 | 含义 |
|---|---|
| `movie_id` | 文档 id：优先 `imdb_id`，其次 `tmdb-<id>`，最后 `片名+年份` 的 hash |
| `sources` / `source` | 由哪几个源拼成（如 `["imdb","legacy","tmdb"]` / `"imdb+legacy+tmdb"`） |
| `source_count` / `is_multi_source` | 合并了几个源 |
| `merged_from` | 一共吸收了几条原始记录 |
| `match_keys` | 这条记录用过的所有对齐主键（排查「为什么这两条没合上」时直接看它） |

### 融合规则

**① 三级对齐主键**（可信度从高到低）

```
imdb:tt0137523          IMDb tconst —— 跨源最稳
tmdb:550                TMDB 数字 id
title:搏击俱乐部|1999    片名归一化 + 年份 —— 兜底
```

片名归一化会做：全角转半角、去消歧义括号（`Crash (2004 film)` → `crash`）、
转小写、去标点与空白。**标题键必须带年份** —— 不带的话《英雄》2002 和
《英雄》2018 会被合成一部；带上年份，误合并率降一个数量级。

**② 增量「桥接」合并**（不能先分组）

一条记录可能同时带 `imdb_id` 和 `tmdb_id`，它就是一座**桥**，把
「只有 imdb_id 的那组」和「只有 tmdb_id 的那组」连起来。
所以算法是边扫边合：命中 0 组就新建、命中 1 组就并入、命中 2 组以上
说明这几组本来就是同一部电影，先互相合并再并入。

**③ 字段优先级**（写在 `transform/movies.py` 的 `SCALAR_PRIORITY` 里，明文可查）

```
中文片名  legacy（人工核过） → tmdb（官方 zh-CN） → wikidata → imdb
剧情简介  tmdb → legacy → wikidata（其实是维基摘要） → imdb
海报/背景 tmdb → legacy → wikidata → imdb
评分热度  tmdb → imdb → legacy → wikidata
导演      legacy（人工录入） → tmdb → wikidata → imdb
拍摄地    仅 wikidata 提供，按 (地名,纬度,经度) 去重后并集
```

列表字段（类型/演员/关键词/出品国）取**并集且保序**；
`vote_average = 0.0` 视为「缺失」而不是「0 分」——
不区分的话，阶段 5 的评分分布图上会凭空多出一座 0 分的山。

### 实测结果（本机跑真实 interim 数据）

```
输入记录数    : 171（seed 120 + imdb demo 48 + wiki demo 3）
融合后电影数  : 171
含 imdb_id    : 145 (85%)   含 tmdb_id: 96 (56%)
含中文片名    : 121 (71%)   有海报: 16 (9%)
有评分        : 48 (28%)    有剧情简介: 121 (71%)
年份区间      : 1980 ~ 2025
耗时          : 0.0s        峰值内存 46.6 MB
```

> 压缩比 1.00 : 1（0 部多源合并）是**正常的**：本机 `imdb` / `wiki` 产物是
> `--demo` 造的合成数据，id 与 120 部真实片库毫无交集，自然合不上。
> 在你本机跑完真实采集后（`imdb --download` + `wiki`），这一步才会开始
> 把真实的多源记录并起来。

影评侧：

```
读入行数      : 49,874
写出记录数    : 49,873     跳过：过短 1
情感分布      : positive 25,078(50%)，negative 24,794(50%)
正文字符数    : 最短 32，中位 951，平均 1281，最长 13593
耗时          : 5.8s       峰值内存 52.9 MB
```

关联到电影 0 条 —— 因为 Stanford 影评集**只有正文和情感两列，没有片名**
（阶段 1e 已实测确认）。这不是实现问题，是数据源本身的限制；
换用带片名的数据集（`--dataset rotten`）后，同一套代码就会开始产出
`title` / `title+year` 两种关联。有歧义的片名（如 Crash 1996 / 2004）
会被**主动剔除**，宁可判为对不上，也不乱指。

### 阶段 2a 验证清单

```bash
# 1. 离线自检：融合 / 优先级 / 桥接 / 幂等 / 端到端 全部覆盖
python tests/test_transform_offline.py
#    期望：结果：70/70 通过

# 2. 干跑：不写盘，先看融合率
python -m transform.run_transform movies --dry-run

# 3. 正式融合
python -m transform.run_transform movies

# 4. 检查成品有没有合同字段缺失（0 表示全部字段齐全）
python -c "import json;print([k for k in json.loads(open('data_lake/processed/movies.jsonl',encoding='utf-8').readline()) if k.endswith('_id')])"

# 5. 影评清洗 + 关联
python -m transform.run_transform reviews --min-chars 20
```

### 五个设计要点（答辩可以讲）

1. **三级主键 + 标题带年份**：只用 id 会漏掉 120 部老片库（大半个 id 是空的）；
   只用片名会乱合并。三级兜底 + 年份约束，是漏合与错合之间的平衡点。
2. **桥接式合并**：先按主键分组会丢掉「同时带两个 id」的桥接记录，
   正确做法是边扫边合（并查集思路）—— 一条记录能连通两组。
3. **字段优先级明文成表**：不用 if-else 散落各处，而是 `SCALAR_PRIORITY` 一张表，
   评审时一眼看出依据，改只动一处，测试还守着表的完备性。
4. **合并顺序无关（幂等）**：比较的是「该字段来自哪个源」而不是「谁先来」，
   6 种输入顺序跑出来结果完全一致 —— 重跑不会让数据漂移。
5. **血缘必须留**：`sources` / `merged_from` / `match_keys` 全部保留。
   没有这层信息，后面发现某条数据错了根本追不回是哪个源的锅。

---

## 阶段 2b · ES 索引构建与导入

### 这一步在解决什么问题

阶段 2a 产出了干净的 `processed/movies.jsonl`（171 部）和 `reviews.jsonl`（49,873 条），
但它们只是磁盘上的文本 —— 还没法被"检索"。这一步把文件变成**可查询、可分面、可聚合**的
Elasticsearch 索引，也决定了后面所有功能的天花板：

> mapping 设计错了，阶段 3 的接口再漂亮也搜不准。
> 比如把片名建成 `text` 却没有 `keyword` 子字段，前端就永远没法"按片名排序"。

### 命令

```bash
# 1. 建索引 + 导入（最常用；已有索引就增量覆盖，幂等可重跑）
python -m index.run_index build

# 2. 改了 mapping 之后重建：写新索引 → 导完 → 原子切换别名 → 删旧索引
python -m index.run_index build --recreate

# 3. 只导一个 / 只导前 1000 条（调试用）
python -m index.run_index import movies
python -m index.run_index import reviews --limit 1000

# 4. 看索引现状（文档数 + 类型/情感分面）
python -m index.run_index stats

# 5. 检索冒烟测试：分词器 / 中文检索 / 分面 / 地理查询 / 影评 五条链路
python -m index.run_index check

# 6. 删库重来（只清 ES，数据湖产物不受影响）
python -m index.run_index drop --yes
```

常用参数：`--only {movies,reviews}`、`--recreate`、`--keep-old`、`--limit N`、
`--chunk N`（bulk 每批条数，网络差调小）、`--from-dir DIR`。

### 索引设计

| 决策 | 做法 | 不这么做会怎样 |
|---|---|---|
| 中文分词 | 索引期 `ik_max_word`（细切）、查询期 `ik_smart`（粗切） | 两头都细切 → 搜"科幻电影"捞回所有含"电影"的片 |
| 排序 / 聚合 | 文本字段一律挂 `.kw` keyword 子字段 | `text` 不能排序也不能做 terms 聚合，分面直接报错 |
| 分面字段 | 类型 / 国家 / 语言 / 情感 用纯 `keyword` | 建成 text 会被切成词，"剧情"分面变成"剧"+"情" |
| 脏日期 | `ignore_malformed=True` | 一条 `release_date="unknown"` 会让整部电影写入失败 |
| 拍摄地 | `nested` + `geo_point` | 用默认 object 会打平，"香港取景 且 纬度>22" 会误命中上海片 |
| 未知字段 | `dynamic: strict` | 动态映射会让新字段**静默建不上索引**，线上永远搜不到 |
| 影评正文 | 内置 `english` 分析器（自动词干还原 + 去停用词） | 用 standard，"wonderful" 搜不到 "wonderfully" |
| 分片 | 单分片 / 零副本 | 几万条数据多分片纯属浪费；副本在无第二节点时会让健康度变 yellow |

### IK 中文分词器

Plugins：官方镜像不带任何中文插件，默认 `standard` 对中文是**一字一 token**：

```
standard   → 流浪 / 地球 / 是 / 中 / 国 / 科 / 幻 / 电 / 影    ← 全是单字，召回噪声大
ik_max_word → 流浪 / 地球 / 一部 / 中国 / 科幻电影 / 科幻 / 电影
ik_smart    → 流浪 / 地球 / 一部 / 中国 / 科幻电影
```

插件写进了 `docker/elasticsearch/Dockerfile`（跟着镜像走，重建容器不丢）。
索引层还有一层**降级保护**：`detect_ik()` 探不到插件就自动退回内置 `cjk` 分析器，
索引照样能建能搜 —— 所以换机器部署不会直接崩。

### 三个关键设计（答辩重点）

**1. 别名 + 版本化物理索引 —— 重建索引不中断服务**

线上永远只认 `movies` 这个别名，真实数据在 `movies_v1_20261014_215800`。
改了 mapping 要重建时：新建空索引 → 灌数据 → **一个原子请求**把别名指过去 → 删旧索引。

```
旧索引 movies_v1_...215616  ←── 导入全程仍在这里正常服务
新索引 movies_v1_...215800  ←── 数据灌完
           ↓ update_aliases（原子，无空窗）
别名 movies → 新索引；旧索引删除
```

直接 `DELETE movies` 再重建是新手最常见的线上事故 —— 中间那几分钟是**没有索引**的。

**2. `_id` 用业务主键 —— 天然幂等**

`_id = movie_id / review_id`。同一份数据导两遍是**覆盖**不是追加，
所以"改融合规则 → 重跑 transform → 重跑导入"这个循环可以随便跑，索引不会翻倍。
实测连跑两次，文档数稳定在 171 / 49,873。

**3. 流式 bulk —— 内存与文件大小无关**

`streaming_bulk` 边读边分批提交，从不把 5 万条影评攒成 list。

### 实测结果（本机真实数据）

```
[movies]  171 条        0.6s
[reviews] 49,873 条     13.6s
合计 50,044 条，失败 0 条，峰值内存 99.0 MB

stats:
  movies  文档数 171      类型分布：剧情(57)、冒险(55)、动作(54)、悬疑(47)、喜剧(42)、科幻(36)
  reviews 文档数 49,873   情感分布：positive(25,078)、negative(24,794)、neutral(1)

check: 5/5 通过
  中文分词器        切出 7 个多字词：流浪、地球、一部、中国、科幻电影
  中文检索（端到端）  《流浪地球》→ 词「流浪」→ 2 命中，首位《流浪地球》
  类型分面聚合       剧情(57)、冒险(55)、动作(54)、悬疑(47)、喜剧(42)
  嵌套地理查询       查询可解析，命中 0 部（当前采集数据尚无坐标）
  影评检索 + 情感分面 5551 命中；情感分布 positive(3315)、negative(2236)
```

> 地理查询 0 命中是正常的：本机 `imdb` / `wiki` 产物还是 `--demo` 合成数据，
> 拍摄地坐标要等你跑完真实 Wikidata 采集才有。

### 阶段 2b 验证清单

| # | 验证项 | 命令 | 期望结果 |
|---|---|---|---|
| 1 | 索引层离线自检 | `python tests/test_index_offline.py` | `47/47 项通过` |
| 2 | IK 插件已装 | `curl localhost:9200/_cat/plugins?v` | 出现 `analysis-ik` |
| 3 | 建索引 + 导入 | `python -m index.run_index build` | 成功 50,044 条，失败 0 |
| 4 | 幂等（重跑不翻倍） | 再跑一次 `build` | 文档数仍是 171 / 49,873 |
| 5 | 重建 + 别名切换 | `build --recreate` | 打印"已原子切换"，旧索引被删 |
| 6 | 中文分词生效 | `python -m index.run_index check` | `5/5 项通过` |
| 7 | 别名指向正确 | `curl localhost:9200/_cat/aliases?v` | `movies → movies_v1_*` |

### 四个设计要点（答辩可以讲）

1. **mapping 恒定，只有 settings 变**。mapping 里只引用 `yj_zh_index` / `yj_zh_search`
   两个自定义分析器名，背后是 IK 还是 cjk 由 settings 决定 —— 换分词器不用改一行 mapping，
   换机器部署也不会出现"两台机器索引结构不一样"的诡异问题。自检里有一条断言专门守这件事。
2. **数据驱动的冒烟测试**。硬编码关键词（比如"科幻"）在某份数据里可能一条都搜不到，
   于是自检报失败 —— 但那是数据问题不是代码问题，误报比漏报更烦。
   所以 `check` 先从索引里**真实取一条中文片名**，交给同一套分析器切词，再拿切出来的词回搜。
3. **geo_point 用 `{lat,lon}` 对象写法**，不用 `[lon,lat]` 数组 —— 后者和直觉相反，
   本项目在阶段 1c 解析 WKT `Point(lon lat)` 时已经踩过一次。
4. **文档整形留在索引层**。geo_point 是纯 ES 概念，融合产物保持"数据源中立"——
   将来换成 PostgreSQL / Milvus，不用重写融合逻辑。

---

## 阶段 3 · FastAPI 混合检索

### 这一步在解决什么问题

阶段 2b 把数据灌进了 ES，但用户碰不到它。这一层把 ES 能力包装成 HTTP 接口：
关键词检索、分面筛选、高亮、排序、分页、影评检索、搜索联想。

新增文件：

| 文件 | 职责 |
|---|---|
| `backend/schemas/search.py` | 请求 / 响应模型（Pydantic） |
| `backend/services/query_builder.py` | ★ 纯函数：参数 → ES DSL。**不联网、不碰 ES，可离线自检** |
| `backend/services/search_service.py` | 执行查询 + 把 ES 结果翻译成响应模型 |
| `backend/api/v1/search.py` | HTTP 接口（每个检索都提供 POST 全参数版 + GET 简化版） |
| `backend/static/search.html` | 浏览器可直接开的检索演示页 |
| `tests/test_search_offline.py` | **61 项**离线自检 |

### 接口一览

| 接口 | 用途 |
|---|---|
| `POST /api/v1/search/movies` | 电影混合检索（全参数） |
| `GET  /api/v1/search/movies` | 简化版，浏览器/curl 直接试 |
| `GET  /api/v1/search/suggest` | 搜索框联想（输「流浪地」→ 出《流浪地球》） |
| `GET  /api/v1/search/movies/{movie_id}` | 单部电影详情 |
| `POST /api/v1/search/reviews` | 影评检索（含情感 / 篇幅分面） |
| `GET  /api/v1/search/reviews` | 简化版 |

```bash
# 启动
uvicorn backend.main:app --reload --port 8000
# 然后打开 http://localhost:8000/docs 或直接
#      http://localhost:8000/static/search.html
```

### 三个核心设计（答辩重点）

**1. 混合检索 = 召回 + 精度提升**

只写一句 `multi_match` 的话，「流浪地球」会被切成 流浪 / 地球 分别匹配，
一部叫《地球脉动》的纪录片可能排在《流浪地球》前面。所以用 `bool.should` 叠两段信号：

```
召回层：multi_match best_fields（任一字段命中即算，tie_breaker 0.3）
精度层：match_phrase 整句连续命中，boost 5.0 —— 把真正命中的顶到最前
```

字段权重按「越短越具体的字段越可信」配：片名 6.0 > 导演 3.0 > 主演 2.0 > 简介 1.0。

**2. 分面用 post_filter，而不是塞进 query**

塞进 query 的话，聚合只统计「筛选之后」的文档 —— 用户点了「科幻」之后，
类型分面里就再也看不到「喜剧」了，筛选器把自己锁死（facet self-locking）。

**3. 分面之间互相排除（drill-down）**

光有 post_filter 还不够：选了「科幻」之后，类型分面里「喜剧」的计数会被
「必须含科幻」压掉，看不到「换成喜剧会有多少部」。所以每个分面统计时，
只应用**其它分面**的条件，排除它自己那条。实测：

```
搜「科幻」且筛「喜剧」→ 命中 2 部
类型分面（仍显示全部类型，喜剧标记为已选）：
   [ ] 科幻: 36   [ ] 冒险: 30   [ ] 动作: 20   [ ] 悬疑: 14   [√] 喜剧: 2
```

**4. 无关键词时相关性排序自动退化**

没有关键词时所有文档的 `_score` 都是 1.0，按「相关度」排等于随机排。
所以当 `sort=relevance` 且 `q` 为空时，自动退化成按票数（热度）排，
并在响应的 `meta.sort_used` 里如实告知前端 —— 不装作在按相关度排。

### 其它值得一提的取舍

| 决策 | 原因 |
|---|---|
| 高亮 `encoder: html` | 默认不转义，影评正文带 HTML 片段时，前端 `v-html` 就是 XSS 口子 |
| `track_total_hits: true` | ES 7+ 默认只精确统计到 1 万条，影评有 5 万条，不开会算错页数 |
| 评分排序带兜底（票数） | 否则一部 3 人打 9.9 分的片会压过 250 万人评的《肖申克》 |
| 年份分面按 `_key` 倒序 | 按数量排会把年份顺序打乱，用户找不到"最新的是哪年" |
| 评分/篇幅用 range 分面 | 浮点值用 terms 会碎成几百个桶 |
| 联想单独一个查询 | 联想要 prefix 且只搜片名，正式检索要召回更多 —— 目标不同，不混用 |

### 实测结果

```
GET  /search/movies?q=科幻        → 36 部，97 ms，类型分面 12 项
GET  /search/movies?q=科幻&genres=喜剧 → 2 部，类型分面仍显示 科幻:36（drill-down 生效）
GET  /search/movies               → 171 部，sort_used=votes（相关性自动退化）
GET  /search/suggest?q=流浪地      → 流浪地球(2019)、流浪地球2(2023)
GET  /search/movies/{id}          → 流浪地球，来源 legacy
POST /search/movies genre_op=and  → 科幻+喜剧 2 部：死侍、银河系漫游指南
GET  /search/reviews?q=wonderful  → 5,551 条，情感 positive 3315 / negative 2236
                                    高亮：…comment on this <em>wonderful</em>, exciting…
GET  /search/movies?require_poster=true → 16 部（exists 修复生效）
GET  /search/movies/not-exist     → 404
```

### 阶段 3 验证清单

| # | 验证项 | 命令 | 期望结果 |
|---|---|---|---|
| 1 | 检索逻辑离线自检 | `python tests/test_search_offline.py` | `64/64 项通过` |
| 2 | 服务启动 | `uvicorn backend.main:app --port 8000` | 启动无报错 |
| 3 | 路由注册 | 打开 `/docs` | 5 个检索接口都在 |
| 4 | 中文检索 | `curl "localhost:8000/api/v1/search/movies?q=科幻"` | 有命中 + 有高亮 |
| 5 | 分面不自锁 | 加 `&genres=喜剧` | 类型分面仍显示「科幻: 36」 |
| 6 | 排序退化 | 不带 `q` 请求 | `meta.sort_used == "votes"` |
| 7 | 联想 | `curl "…/suggest?q=流浪地"` | 出《流浪地球》 |
| 8 | 影评检索 | `curl "…/search/reviews?q=wonderful"` | 5,551 条 + 情感分面 |
| 9 | 演示页 | 打开 `/static/search.html` | 可搜、可点分面、有高亮 |

### ★ 本阶段修掉的一个真 Bug（阶段 2b 埋的）

阶段 2b 为了省空间，把 `poster_url` 设成了 `index: false, doc_values: false`。
结果 **`exists` 查询永远返回 0 命中，而且不报错** ——
"只看有海报的"这个筛选会静默失效，查半天都查不出原因。

```
实测：exists:poster_url → 0 部（实际有 16 部）
      exists:overview   → 121 部（正常 text 字段）
```

修复：`poster_url` / `backdrop_url` 改回可索引的 keyword，mapping 版本升到 v2，
重建索引。并在 `index/mappings.py` 里加了 `EXISTS_QUERY_FIELDS` 清单 +
自检断言，防止以后再犯。**纯展示外链**（wikidata_url）才继续用 noindex。

### 另一个坑：`tmdb_id` 类型不一致导致 500

ES 里 `tmdb_id` 是数字，响应模型声明 `str | None`，pydantic 严格模式直接拒绝，
接口返回 500。修复：在服务层统一 `str()` 转换 —— 前端拿它拼 TMDB 链接，
字符串更顺手，也不会出现"有时候是数字有时候是字符串"的摇摆类型。

### 第三个坑：GET 端点漏参数，前端传了没反应

`GET /movies` 只挑了几个常用参数写，漏掉 `with_facets` / `languages` /
`rating_max` / 片长区间等。**FastAPI 对未声明的查询参数不报错，用默认值顶上**，
于是 `with_facets=false` 被静默忽略 —— 分面照算，白白多一次聚合开销，
而前端只会觉得"这参数怎么没用"。

修复：GET 参数与请求模型逐字段对齐，并加了一条自检断言 ——
用 `inspect.signature` 反查端点参数，要求覆盖模型的每个字段。
以后再加字段忘了同步，测试立刻红。

---

## 阶段 4 · 情感分析 + 主题分析

### 这一步在解决什么问题

影评索引里已经有一个 `sentiment` 字段，但那是 **Kaggle 数据集自带的二分类标签** ——
别人打好的、只有正负两档、覆盖不了中文。阶段 4 要做的是**自己的分析能力**：

1. 用这 5 万条标注影评**归纳一部情感词典**（数据驱动、每个词可解释）；
2. 给任意文本打分级情感分（中英文都行），并说出"因为哪些词所以是这个分"；
3. 从影评语料里抽出**主题关键词** —— 观众在夸什么、骂什么。

### 新增文件

| 文件 | 职责 |
|---|---|
| `analysis/lexicon.py` | 分词、否定/程度规则、**从标注语料归纳词典**、持久化 |
| `analysis/sentiment.py` | 打分（否定窗口/程度副词/转折加权）、用 Kaggle 标签评估 |
| `analysis/topics.py` | 词项统计、关键词排名、TF-IDF、significant_terms DSL |
| `analysis/run_analysis.py` | CLI：`lexicon` / `report` / `topics` / `score` / `check` |
| `backend/schemas/insights.py`、`backend/api/v1/insights.py` | 洞察接口 |
| `tests/test_analysis_offline.py` | **114 项**离线自检 |

产物落在 `data_lake/analysis/`：`lexicon.json`（词典）、`topics.json`（主题榜）、
`movie_keywords.json`（单片关键词画像）、`report.json`（评估报告）。

### 接口一览

| 接口 | 用途 |
|---|---|
| `POST /api/v1/insights/sentiment` | 任意文本情感打分，**返回每个命中词** |
| `GET  /api/v1/insights/sentiment` | 全局情感分布 + 各类型均分（大屏用） |
| `GET  /api/v1/insights/topics` | 主题词榜：观众在夸什么 / 骂什么 |
| `GET  /api/v1/insights/lexicon` | 学出来的词典本身（答辩演示） |
| `GET  /api/v1/insights/movies/{id}` | 单片画像：关键词 + 类型口碑参考 |

### 核心设计（答辩重点）

**1. 词典不是抄的，是从 5 万条标注影评里归纳的。**

对每个词统计它在正面/负面影评里的文档频次，取对数几率，再做**经验贝叶斯收缩**：

```
score(w) = log( P(w|好评) / P(w|差评) ) * df / (df + k)
```

- 为什么用 df 不用 tf？一篇文章里同一个词出现 10 次只说明这篇长，
  不代表它情感更强。df 天然做了文档内归一化。
- 为什么要收缩？只出现十几篇、恰好全是同一个极性的词（导演名、角色名）
  log-odds 能冲到 ±3.5，但它们只是"恰好"。按 df 往 0 收缩后，
  `wonderfully / flawless / superb` 才排到榜首，而不是 `lumet / uwe / manos`。
- 为什么 k 按语料规模算？第一版写死 50，在 2.5 万篇上效果好，
  换到 16 条小样本把 `wonderful` 压成 0.083。改成 `min(正,负)/500` 后
  大小语料都适用（自检里有对应断言）。

**2. 训练集与评估集必须分开 —— 不能考前发答案。**

按 `row_index` 奇偶切分：奇数篇归纳词典，偶数篇做评估。
24,950 篇留出集上：**准确率 83.56% / 精确率 88.30% / 召回 78.83% / F1 0.8330**，
峰值内存 53 MB。

**3. 打分规则四行讲完，每个命中词都报得出来。**

分词 → 情感词累加；前 3 词内有否定词则翻转（`not good` → 负，`not bad` → 正）；
前 1 词是程度副词则缩放（`very wonderful` > `wonderful`）；
`but` 之后的分句加权 1.3（"特效不错，但剧情一塌糊涂"重点在后面）；
否定作用域在标点处截止（「一点都不好看，浪费时间」—— 逗号后的「浪费时间」不被连带翻转）。
最后 tanh 压到 [-1,1]。前端把命中词高亮，答辩时现场粘一条影评就能演示。

中文还有一条专属路径：jieba 会把多个字粘成一个 token（「太精彩」「强烈推荐」），
精确匹配打不中时走**子串匹配**把词典词条捞回来，token 内部的否定/程度同样生效
（「不精彩」翻转、「太精彩」放大）。单字词条只在被否定词包住时才允许子串命中
（「不差」→ 正面），否则「烂漫」会误中「烂」。

**4. 主题榜不能按词频排，也不能直接按 lift 排。**

- 按词频排：前 20 名全是 movie / film / story / one（它们高频是因为**常见**）；
- 按 lift 排：榜首全是只出现二三十次的角色名（证据量不够）。

排序键取两个因子的乘积：**收缩后的对数提升度 × log10(1+df)** ——
"又分化、又常见"的词才排前面。实测：

| 观众在夸什么 | 观众在骂什么 |
|---|---|
| superb、beautifully、wonderfully、excellent、delightful、underrated、flawless、touching、outstanding、gem | waste、awful、poorly、terrible、laughable、lame、redeeming、pointless、unfunny、stinker |

### 实测结果（本机真实数据）

| 项 | 数值 |
|---|---|
| 归纳语料 | 24,922 篇（正面 12,496 / 负面 12,426） |
| 词典规模 | 14,381 词（85,151 个候选词按 min_df=10 筛得，含内置中文 87 个） |
| 留出集准确率 | **83.56%**（24,950 篇） |
| 精确率 / 召回率 / F1 | 88.30% / 78.83% / 0.8330 |
| 主题统计 | 49,873 篇影评、115,427 个词种 |
| 单片画像 | 171 部电影（如《流浪地球》→ 地球、流浪、太阳、太阳系、寻找新家园、郭帆） |
| 峰值内存 | 词典 53 MB / 主题 122 MB |

### 数据驱动的一个有意思发现

`decent` 归纳出 **−0.81**、`okay` **−0.63**、`good` **−0.02** ——
在影评语境里"还凑合"就是委婉的差评，"好"只配当个中义词。
这是通用情感词典给不出来的领域适配，也是"为这个领域单独做词典"最直接的证据。

### 已知限制（如实说明）

- **中文打分走内置手写词典**（87 词），因为我们的影评语料是英文的。
  中文真要做好，需要中文标注语料 —— 而豆瓣等中文源有反爬限制，本项目合规红线内不可采。
- **中文分词边界与词典词条对不齐**：jieba 把「演技在线」切成「演技/在线」，
  这类"词典词比分词长"的情况子串匹配也救不回来（已用子串匹配解决反过来的情况，
  即分词比词条长，如「太精彩」「强烈推荐」）。
- **否定窗口是固定 3 个词**：无标点隔开时会误伤（「不 精彩 推荐」里推荐也被翻转）。
  中文已用标点截止缓解，英文没有标点 token，属于该方法的固有代价。
- **影评与电影无法按类型关联**：Kaggle 数据集只有正文和标签两列，没有电影 id。
  所以 `/insights/sentiment` 的类型维度退一步用电影侧评分（IMDb/TMDB 均分），
  口径不同已在接口文档里写明。
- **召回率（78.83%）低于精确率（88.30%）**：词典法天然偏保守 ——
  没命中词典的词就判不出来。这是可解释性换来的代价，用数字说明比藏着好。
- SnowNLP 基线默认不跑：它 import 一次要 ~400 MB（我们全流程 53 MB），
  且用中文电商评论训练，对英文影评接近随机猜测，不是公平对比。加 `--baseline` 可跑。

### 阶段 4 验证清单

| # | 验证项 | 命令 | 期望结果 |
|---|---|---|---|
| 1 | 分析逻辑离线自检 | `python tests/test_analysis_offline.py` | `114/114 项通过` |
| 2 | 归纳词典 | `python -m analysis.run_analysis lexicon` | 14,381 词，榜首是 wonderfully / waste |
| 3 | 留出集评估 | `python -m analysis.run_analysis report` | 准确率 83.56%，F1 0.8330 |
| 4 | 主题抽取 | `python -m analysis.run_analysis topics` | 夸/骂两张词表都非空 |
| 5 | 文本打分 | `curl -X POST …/insights/sentiment -d '{"text":"not wonderful"}'` | 判 negative |
| 6 | 否定规则 | `POST …/insights/sentiment` 传 "not bad" | 判 positive（双重否定） |
| 7 | 中文打分 | 传「太精彩了，演技在线」 | 判 positive |
| 8 | 中文子串匹配回归 | 传「这部电影太精彩了，强烈推荐」 | 判 positive，命中 精彩(+1.4) / 推荐(+1.5) |
| 9 | 中文否定作用域 | 传「一点都不好看，浪费时间」 | 判 negative，两个命中词都是负的 |
| 10 | 主题榜接口 | `curl …/insights/topics` | waste 排第一，lift 0.074 |
| 11 | 词典接口 | `curl …/insights/lexicon` | 返回 top 正负词 + meta |
| 12 | 单片画像 | `curl …/insights/movies/mf444fcde9d4b` | 《流浪地球》关键词画像 |
| 13 | 产物缺失降级 | 删掉 lexicon.json 再请求 | 503 + 提示该跑哪条命令 |
| 14 | 缓存失效 | 重新生成词典后再请求 | 拿到新词典（mtime 缓存自动失效） |

### 本阶段修掉的五个真问题

**1. 罕见词霸榜（词典第一版）**
榜首是 `lumet / vance / veidt / uwe / manos` —— 只出现十几篇、恰好单极性的导演名。
修复：经验贝叶斯收缩，`score * df/(df+k)`。

**2. 收缩强度写死，换语料规模就失效**
`SHRINK_K=50` 是按 2.5 万篇标定的；16 条小样本上 `wonderful` 被压到 0.083，
所有分数趋近 0，准确率掉到 18.75%（离线自检第一时间抓到）。
修复：`k = min(正负文档数)/500`，随语料规模自动缩放，并加断言锁住。

**3. 正面率算成 250.78%**
`/insights/sentiment` 的 ES 聚合漏写 `track_total_hits=True` ——
ES 7+ 默认只精确统计到 1 万条，影评有 4.99 万条，`hits.total` 停在 10000，
于是 25078/10000 = 250.78%。阶段 3 在影评检索上踩过一次同款坑，
这次是在聚合上又踩了一遍 —— 已加断言：分面合计必须等于 total。

**4. 中文整句判 neutral：分词边界对不上词典词条**
收尾联调时粘了一句「这部电影太精彩了，强烈推荐」，返回 neutral、零命中。
查下去是 jieba 切成 `['这部','电影','太精彩','了','强烈推荐']`，
而词典里存的是「精彩」「推荐」—— 精确匹配一条都打不中。
修复：中文走**子串匹配**（简化版正向最大匹配），token 内部的否定/程度同样生效。
两条配套约束：单字词条只在被否定词包住时才允许子串命中
（否则「烂漫」会误中「烂」）；命中回报词典词条而不是原始 token，
解释时用户看到的是「精彩 +1.4」而不是「太精彩」。

**5. 否定作用域没有边界，误伤后半句**
修完第 4 个马上又暴露一个：「一点都不好看，浪费时间」里「浪费时间」被翻转成 +1.0 ——
「不」在 3 个词的否定窗口内，而 jieba 把逗号丢了，窗口法根本看不到边界。
修复：中文分词保留标点 token（否定作用域在标点处截止），
同时补掉了旧版 tokenize_zh 把中英文顺序打乱的 bug。
英文分词不产出标点 token，所以英文指标一动不动（83.56% 复测一致）。

---

## 阶段 5 · Vue3 前端 ✅ 已完成

**信息架构按 yuan 要求落地：数据面板不放在首页。** 首页 = 混合检索
（电影盒子是检索与发现平台，不是管理后台）；数据面板独立为「影评洞察」页。
技术选型 Vue3.5 + Vite 7 + Vue Router 4 + ECharts 5（按需引入，**不引 UI 框架**，
手写 CSS 继承棕灰主题）。

### 页面清单（6 视图 / 21 组件）

| 路由 | 内容 |
|---|---|
| `/` 混合检索 | SearchBox（防抖+键盘导航）· FacetRail 双面栏（影片 6 分面/影评 3 分面）· ActiveChips · SortBar（影片/影评双 Tab）· MovieGrid（骨架/空态/分页）· MovieDetail 弹窗（评分 1-10 / 想看 / 找相似） |
| `/insights` 影评洞察 | 四统计卡 · 情感环图 · 类型口碑条形 · 年代趋势双轴 · 主题榜 · 词典 · 情感打分演示（ECharts 按需引入，独立分包 183KB gzip） |
| `/discover` 发现 | 热门榜（WR 公式说明条+排名徽章）· 为你推荐（口味画像/降级提示/热门补位标注）· 趣味实验室（混搭器/盲盒同种子复现） |
| `/login` 登录注册 | 双卡布局，注册即登录；演示管理员提示 |
| `/me` 我的 | 我的评分（删除）· 想看清单（hydration 完整影片卡+移出）· 资料昵称 · 改密码 |
| `/about` 项目说明 | 数据流水线 / 数据来源合规 / 技术栈 / 阶段进度 / 接口速览（答辩一页速览） |

### 前端架构要点

- **共享状态只有登录态一处**：`composables/useAuth.js` 单例（reactive + localStorage），
  不引 Pinia；`init()` 用共享 promise 保证 App 与视图并发初始化时序安全
- **api 层原生 fetch 封装**：token 自动注入、401 统一派发 `yj:auth-expired`、
  后端 detail.message/detail.hint 透传到 Toast
- **样式分层**：`theme.css`（主题变量）→ `components.css`（影片卡/弹窗等跨视图共享）→
  `pages.css`（页面布局）→ `search.css`（检索页专属）
- **`useMovieActions` 组合式函数**：评分/想看/详情弹窗逻辑首页与发现页共用，零重复

### 验证（全部实测）

- `npm run build` 通过（631 模块，首屏 JS 115KB / gzip 45KB，ECharts 独立分包按需加载）
- **puppeteer 全流程走查 14/14 通过**（`scripts/verify_frontend_walkthrough.js`，
  阶段 5.5 后页面结构有扩充，Docker 部署态复测仍 14/14）：
  注册→自动登录→首页检索→详情弹窗打 8 分→加想看→我的页数据核对→
  为你推荐口味画像→盲盒抽签→洞察页→说明页→全程零控制台错误
- 走查抓到并修复 1 个真 bug：`useAuth.init()` 并发时序
  （App 与视图同时调 init，后调者拿到未完成状态 → 我的页加载被跳过）

---

## 阶段 5.5 · 清单重构 + 真实数据修复 ✅ 已完成

### 前端按功能清单重构（保留原系统风格）

- 页面结构按新清单划分：`/` Hero 首页（大搜索框+热门词+随机盲盒）·
  `/search` 检索结果页（三栏）· `/mix` 混搭器 ·
  `/analytics` 深色分析大屏 · `/insights` 影评洞察 · `/for-you` 为你推荐 ·
  `/movie/:id` 详情页 · `/me` 个人中心
- 顶导航（首页/检索/混搭器/盲盒/分析）+ 全局搜索框 +
  固定「🎲 随便看看」按钮 + 全局盲盒弹窗（开盒动画 + 推荐理由）
- 原系统风格完整保留：棕灰主题、背景图（pattern.jpg / login-bg.jpg）、
  品牌 slogan、胶囊按钮、玻璃拟态登录卡、统计卡圆形渐变图标

### 真实数据重建（阶段 5.5 核心修复）

发现演示数据（Demo Movie 49 部）混进了正式索引、原始采集产物丢失。
全链路重跑修复：

| 步骤 | 结果 |
|---|---|
| seed --resolve | 120 部种子片库，TMDB 反查 25/25 命中 |
| tmdb 发现式采集 | +160 部（100% 带海报），168 次 API |
| wiki 采集（尾斜杠 bug 修复后） | 265 条记录 · **863 处带坐标拍摄地** · 252 条维基摘要 |
| transform movies --no-demo | **266 部真实电影**，265 部多源合并，峰值内存 47.9 MB |
| index build --recreate | 266 部电影 + 49,873 条影评，别名原子切换，0 失败 |

### 三个真 bug（都在这次抓到并修复）

1. **Wikidata 全部 404 的根因**：`RateLimitedClient` 以 `base_url + 空 path`
   调用时，httpx 会拼出 `/sparql/`（尾斜杠），WDQS 对该路径 404。
   之前以为是限流/被墙——实际是 URL 拼接 bug。wikipedia.py 早就用
   `_split_api` 拆 base+path 避开了，wikidata.py 漏了同样处理。
2. **TMDB 海报直连不通**（image.tmdb.org 被墙）→ 新增后端图片代理
   `GET /api/v1/img?url=...`（域名白名单 + 服务端走 IMAGE_FETCH_PROXY 代理出口 +
   浏览器缓存 1 天），序列化层统一改写 poster_url，前端零改动。
3. **盲盒详情页崩溃**：`BlindBox.vue` 模板里 `blindBox.history.find(...)`——
   history 是 ref，嵌在对象里不会自动解包。改为解构后在模板顶层使用。

### 验证（阶段 5.5 全部实测）

- **puppeteer 全流程走查 14/14 通过**（更新后含检索页独立断言）
- **海报渲染校验**（`scripts/verify_posters.js`，按 img.complete 区分
  lazy 待加载与真裂图）：首页 12/20（8 张视口外 lazy）· 检索页 16/16 · 全程无 4xx
- 顺手修复：首页热门列表没解包 `{movie}` 包装结构、
  DiscoverView 成为孤儿视图（恢复 /for-you 入口）

---

## 常用运维命令

```bash
# 停止（保留数据）
docker-compose down

# 停止并清空 ES 数据（谨慎，会删掉所有已建索引）
docker-compose down -v

# 查看 ES 索引
curl "http://localhost:9200/_cat/indices?v"

# 查看别名指向了哪个物理索引（重建后确认切换成功）
curl "http://localhost:9200/_cat/aliases?v"

# 重建镜像（改了 Dockerfile 或升级 ES 版本之后）
docker-compose build elasticsearch && docker-compose up -d
```

### 全流程一条龙

```bash
python -m ingest.run_collect seed          # 1. 种子片库
python -m ingest.run_collect tmdb          # 2. TMDB 补齐
python -m ingest.run_collect imdb          # 3. IMDb 数据集
python -m ingest.run_collect wiki          # 4. Wikidata + Wikipedia
python -m ingest.run_collect kaggle        # 5. Kaggle 影评
python -m transform.run_transform all      # 6. 清洗融合 → processed/
python -m index.run_index build            # 7. 灌进 ES
python -m index.run_index check            # 8. 验证能搜
python -m analysis.run_analysis lexicon    # 9. 归纳情感词典（阶段 4）
python -m analysis.run_analysis report     # 10. 留出集评估准确率
python -m analysis.run_analysis topics     # 11. 主题词榜 + 单片关键词
```

改任何一层的规则，只需从**该层**开始重跑，不用从头再来。

### 常用运维命令

```bash
# 全量回归（不联网、不碰 ES，几秒钟跑完）
for f in tests/test_*.py; do python "$f"; done

# 分析层调试：只处理前 2000 条
python -m analysis.run_analysis lexicon --limit 2000
python -m analysis.run_analysis report --limit 2000

# 固定收缩强度做对照实验（默认按语料规模自动算）
python -m analysis.run_analysis lexicon --min-df 20
python -c "from analysis.lexicon import induce_lexicon, iter_jsonl; \
print(induce_lexicon(iter_jsonl('data_lake/processed/reviews.jsonl'), shrink_k=50).meta)"

# 看看分析产物现状
python -m analysis.run_analysis check

# 给影评逐条打情感分（阶段 5 大屏用，可选）
python -m analysis.run_analysis score --limit 5000
```

---

## 阶段 6 · 后端功能补全（trends / 用户 / 推荐 / 趣味）

原系统的登录、评分、推荐、趣味功能在新栈上全部重建，数据落在 Elasticsearch
（`users` / `ratings` 索引 + movies 索引），前端留待阶段 5 统一接入。

### 新增文件

| 文件 | 职责 |
|---|---|
| `backend/services/user_store.py` | 用户 CRUD（用户名即 `_id`，`op_type=create` 原子防重） |
| `backend/services/auth.py` | bcrypt 哈希 / PyJWT 签发解析 / 登录防枚举 / 角色守卫 |
| `backend/services/ratings_store.py` | 评分 CRUD（`_id=用户名:movie_id` 幂等 upsert） |
| `backend/services/recommend_service.py` | 口味画像（纯函数）/ 相似 / 热门 / 个性化 |
| `backend/services/fun_service.py` | 混搭器 / 盲盒 |
| `backend/api/v1/errors.py` | 共用的「ES 不可用 → 503」翻译器 |
| `backend/schemas/{auth,recommend,fun}.py` | 请求 / 响应模型 |
| `tests/test_features_offline.py` | **104 项**离线自检 |

### 接口一览

| 接口 | 用途 |
|---|---|
| `POST /api/v1/auth/register` | 注册（自动登录，直接返回 token） |
| `POST /api/v1/auth/login` | 登录（用户不存在与口令错误同报错，防枚举） |
| `GET  /api/v1/auth/me` | 当前登录用户（Bearer token） |
| `POST /api/v1/auth/change-password` | 修改密码（需旧口令） |
| `POST /api/v1/ratings` | 给电影打分 / 改分（覆盖式，重复打不追加） |
| `GET  /api/v1/ratings` | 我的评分列表（按分数倒序） |
| `DELETE /api/v1/ratings/{movie_id}` | 删除一条评分 |
| `GET  /api/v1/recommend/similar/{movie_id}` | 相似影片（more_like_this 内容相似，排除自身） |
| `GET  /api/v1/recommend/popular` | 热门榜（贝叶斯加权分 WR，公式参数随响应带回） |
| `GET  /api/v1/recommend/for-you` | 个性化推荐（口味画像 + 可解释理由；无评分退化为热门并如实标注） |
| `GET  /api/v1/insights/trends` | 年代趋势（十年一桶的影片数与均分） |
| `POST /api/v1/fun/mix` | 类型混搭器（必须同时具备全部类型，服务层强制 AND） |
| `GET  /api/v1/fun/box` | 随机盲盒（种子可传，同种子抽同一部） |

### 核心设计（答辩重点）

**1. 推荐必须可解释。** 每条推荐都带人类可读理由：「你喜欢的导演 诺兰 的作品」
「贴合你偏好的「科幻、喜剧」类型」——命不中口味就返回 None，不编造。
for-you 无评分时退化为热门榜，并用 `degraded=True` 如实标注，不假装"懂你"。

**2. 热门榜不能按均分排。** 贝叶斯加权分 `WR = (v/(v+m))·R + (m/(v+m))·C`
（IMDb Top 250 同款）：一部 3 人打过 9.9 分的片会被 m 往全局均分 C 拉。
公式参数随响应返回，前端可以把公式本身画给用户看。

**3. 口味画像导演权重高于类型。** 类型是粗粒度（一部片常有 2-3 个），
导演是细粒度身份信号——同一个导演出现 2 次比同一个类型出现 2 次更能说明
"用户在追谁"。所以导演只取 top 2，类型取 top 3，boost 3.0 vs 2.0。

**4. 三个 ES 真坑（都已写进注释和自检）**：

- ES **没有独立的 `random_score` 查询**（直接写会 400 unknown query）——盲盒必须包 function_score；
- random_score 引用 **`_id` 会被 fielddata 拒绝**（400）——改用 keyword 字段 `movie_id`（与 _id 同值且稳定）。

### 实测结果（本机真实数据）

| 项 | 结果 |
|---|---|
| 离线自检 | `tests/test_features_offline.py` **104/104 通过** |
| 用户模块实测 | `scripts/verify_auth_live.py` **12/12 通过**（注册 409 / 登录 401 / 改密 / 防枚举 / 非法载荷 422） |
| 推荐全链路实测 | `scripts/verify_recommend_live.py` **30/30 通过**（评分幂等 / 404 / 422、for-you 降级与个性化、similar 排除自身、盲盒同种子复现、混搭器 422） |
| 演示管理员 | 启动自动播种 `admin`（口令见 `.env` 的 `ADMIN_PASSWORD`） |

---

## 阶段 6 续 · 生产可用性（限流 / 缓存 / 探针 / 监控 / 想看清单）

上一步把功能做全了，这一步让服务**敢开着不关**：限流防爆破、缓存省 ES、
探针接部署、500 有兜底、想看清单补上原系统的收藏位。

### 新增文件与改动

| 文件 | 职责 |
|---|---|
| `backend/middleware.py` | IP 限流（general + auth 失败双窗口）/ 请求日志 / X-Request-ID / 请求统计 |
| `common/ttl_cache.py` | 异步 TTL 缓存（single-flight 防雪崩 + 异常不缓存 + FIFO 有界淘汰） |
| `backend/services/watchlist_store.py` | 想看清单（`_id=用户名:movie_id` 幂等，与 ratings 同构） |
| `backend/api/v1/watchlist.py` | `POST/GET/DELETE /watchlist`（需登录，写前校验影片存在） |
| `backend/api/v1/auth.py` | 新增 `PATCH /auth/me`（改昵称；用户名是主键不给改，角色防自助提权） |
| `backend/api/v1/health.py` | 新增 `/health/live`（活体）/ `/health/ready`（就绪）/ `/health/metrics`（有界快照） |
| `backend/main.py` | 中间件注册（RequestLog → RateLimit → CORS 由内到外）+ 全局 500 JSON 兜底 |
| `index/mappings.py` | 新增 `WATCHLIST_MAPPING`（dynamic=strict，与 users/ratings 同款严格性） |
| `scripts/verify_ops_live.py` | 生产可用性实测（36 项） |

### 接口一览（新增）

| 接口 | 用途 |
|---|---|
| `GET  /api/v1/health/live` | 活体探针：进程能响应就 200，**不看依赖**（ES 抖动不连环重启容器） |
| `GET  /api/v1/health/ready` | 就绪探针：ES 连不上 503（部署平台先摘流量） |
| `GET  /api/v1/health/metrics` | 请求计数 / 延迟 / 最近 20 条 / 限流配置 / 缓存命中率 |
| `PATCH /api/v1/auth/me` | 更新昵称（部分更新，并发改密码不互相覆盖） |
| `POST   /api/v1/watchlist/{movie_id}` | 加入想看（幂等，连点星标不加出两行） |
| `GET    /api/v1/watchlist` | 我的想看（mget 一次批量 hydration 影片详情） |
| `DELETE /api/v1/watchlist/{movie_id}` | 移出想看（没加过 → 404，不假装成功） |

### 核心设计（答辩重点）

**1. 限流双窗口，语义不同。** general（240 次/分钟/IP）防刷；
auth_fail（10 次/分钟/IP）只数**失败**的登录/注册，成功即清零——
正常用户手滑打错几次毫无感觉，爆破者换用户名也没用（key 是 IP 不是账号）。
计数器是内存滑动窗口（deque 时间戳 + 惰性清理），IP 表有 1 万上限；
多实例水平扩容要换 Redis，决策写在注释里。

**2. 缓存只缓存"不随用户变"的重查询。** 热门榜 / 年代趋势 / 情感统计端点进 TTL 缓存（默认 300 秒，.env 可调）；for-you、评分、
想看、认证**一律不缓存**（那些数据必须即时）。三个决定：
single-flight（并发同 key 只打一次 ES，防缓存过期瞬间雪崩）、
异常不缓存（一次网络抖动不该被缓存 5 分钟）、FIFO 有界淘汰。

**3. liveness 与 readiness 分开。** ES 挂时 ready 失败（摘流量）但 live 成功
（不重启容器）——否则 ES 一挂全容器被连环重启，永远起不来。两个探针路径
同时被限流与日志豁免（探针被限流 = 部署平台误杀服务）。

**4. 500 不裸奔。** 全局兜底把未处理异常翻成 JSON 500：traceback 进服务端日志，
响应体不泄露异常细节（debug 模式才给类型名），并带上 X-Request-ID——
用户报障时报那 12 位串就能在日志里定位。

### 实测结果（本机真实数据）

| 项 | 结果 |
|---|---|
| 离线自检 | `tests/test_features_offline.py` **107/107 通过**（新增限流窗口 / 缓存 single-flight·淘汰 / 统计有界 / 想看映射 / 接线语义 5 组） |
| 运维实测 | `scripts/verify_ops_live.py` **36/36 通过**（探针 / X-Request-ID / 限流与清零 / 缓存 miss→hit / 昵称 / 想看全流程 / 500 兜底） |
| for-you 补齐实测 | 纪录片口味（全库仅 1 部且已评分）→ 20 条全部热门补位，理由如实标注，已评分的片被排除 |
| 全量回归 | 9 个测试套件全绿（累计 600+ 项） |

### ★ 本阶段抓到的一个真 Bug（写在 README 里备查）

限流中间件的 auth 分支把 `hit()` 的返回值（语义是「**是否放行**」）命名为
`blocked` 并写 `if blocked: 429`——**整个限流器反向工作**：正常请求被 429，
真爆破者（打满窗口后 hit 返回 False）反而放行。
离线测试全过（`RateLimiter.hit` 纯函数语义是对的），是实测第一个 register
就 429 暴露的。修复后补了 4 条**接线级**断言（直接调 `dispatch`），
并把教训写进注释：**纯函数对不代表接线对**。

---

## 阶段 7 · 全栈 Docker 化 + 交付 ✅ 已完成

一条命令把整套系统跑起来：`docker-compose up -d` → <http://localhost:8080>。

### 架构（三容器）

```
浏览器 ──8080──> frontend(nginx) ──/api 反代──> backend(uvicorn:8000) ──> elasticsearch:9200
                  托管 dist/                    入口三段式：等ES→索引缺失自动导入→起服务
                  SPA fallback                  镜像内已打进 processed 数据 + analysis 产物
```

### 三个镜像的设计决策

| 镜像 | 关键设计 | 为什么 |
|---|---|---|
| `es-ik:8.15.3` | 官方镜像 + IK 插件写进 Dockerfile | 插件跟镜像走，重建容器/换机器不丢；mapping 恒定，探测不到 IK 自动降级 cjk |
| `backend:1.0.0` | ① 运行时依赖子集（不装 pandas/sklearn 等采集期库）② processed + analysis 数据 bake 进镜像 ③ 入口等 ES → 索引缺失才自动导入 → exec uvicorn | ① 镜像 ~400MB 而非 ~1.2GB ② 干净机器无需先跑采集管线 ③ `up -d` 即是可用系统；`_id` 即业务主键，导入幂等 |
| `frontend:1.0.0` | node:22 多阶段构建 → nginx:alpine 托管；SPA fallback + `/api` 反代 + 指纹资产 immutable 缓存 | 运行镜像 ~80MB 无 node；深链接刷新不 404；前端零环境判断（API 走相对路径） |

### 干净卷实测（交付验证，不是纸上谈兵）

`docker-compose down -v && docker-compose up -d` 模拟全新机器：

| 步骤 | 实测 |
|---|---|
| ES 就绪等待 | 健康检查 + 入口双重等待，通过 |
| 自动索引导入 | 检测到 movies/reviews 缺失 → 从镜像内数据导入：**266 部（1.6s）+ 49,873 条影评（13.3s），0 失败，峰值内存 67.3 MB** |
| 接口回归（经 nginx） | 登录（JWT）· 电影检索 · 影评检索 · 情感洞察 · 年代趋势 · 主题榜 · **图片代理（200 · 真实 JPEG 102,464 B）** 全过 |
| 前端走查 | puppeteer 全流程 **14/14**，全程零控制台错误 |
| 文档数核对 | 与删卷前基线一致（movies 266 / reviews 49,873） |

### 常用命令

```bash
docker-compose up -d                 # 一键起全栈（首次自动导索引）
docker-compose ps                    # 看容器与健康状态
docker-compose logs -f backend       # 跟后端日志（含索引导入进度）
docker-compose down -v               # 清库（下次启动重新自动导）
docker-compose build                 # 改了代码/Dockerfile 后重建
docker-compose --profile tools up -d # 额外起 Kibana
```

> 换端口、宿主机代理（容器内访问宿主机要用 `host.docker.internal`），
> 数据更新流程见上方「数据更新」小节。

---

## 合规说明

- 仅使用官方公开 API 与开放数据集：TMDB API、IMDb Datasets（官方发布文件）、
  Wikidata SPARQL、Wikipedia API、Kaggle 公开数据集。
- **不采集**豆瓣等存在反爬限制或未授权抓取的平台。
- 所有采集请求遵守各平台的服务条款与速率限制（脚本内置限速与重试）。
- API Key 一律通过 `.env` 注入，不硬编码、不入库。
