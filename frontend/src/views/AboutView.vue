<script setup>
// 项目说明页：平台定位、数据来源与合规、技术架构、阶段进度。
// 这是答辩时给老师/评委看的「一页读懂」——内容与 README 对应但更精简。
// 顶部天气剧场（WeatherScene）：点击切换 晴/夜/彩虹/雨，鼠标移动分层视差。
import WeatherScene from '../components/about/WeatherScene.vue'

const pipeline = [
  { stage: '采集', desc: '5 个公开数据源（TMDB / IMDb Datasets / Wikidata / Wikipedia / Kaggle 影评集），只走官方 API 与公开数据集，断点续跑 + 原始响应落盘' },
  { stage: '清洗融合', desc: '三级对齐主键（IMDb id > TMDB id > 片名+年份），字段优先级表明文可改，融合层不联网不碰库，可随时重跑' },
  { stage: '索引', desc: 'Elasticsearch 8.15 + IK 中文分词，索引期细切 / 查询期粗切，别名 + 版本化物理索引，原子切换零停机' },
  { stage: '分析', desc: '情感词典从语料归纳（对数似然比 + 文档频次收缩），主题按收缩 lift 排序，分析产物独立于主索引' },
  { stage: '检索与发现', desc: 'FastAPI 异步后端 27 个接口，多面检索 / 影评洞察 / 三路推荐 / 趣味发现，限流·缓存·探针生产三件套' },
]

const sources = [
  { name: 'TMDB API', role: '海报 / 关键词 / 主演 / 热度', compliance: '官方 API，属性署名' },
  { name: 'IMDb Datasets', role: '评分与票数（10 分制基准）', compliance: '官方 TSV 公开数据集' },
  { name: 'Wikidata', role: '中文片名 / 导演 / 出品国 / 拍摄地坐标', compliance: 'CC0 公共领域' },
  { name: 'Wikipedia', role: '剧情摘要（分析语料）', compliance: '官方 API，CC BY-SA' },
  { name: 'Kaggle 影评集', role: '5 万条影评 + 情感标签', compliance: '公开数据集' },
]

const phases = [
  { id: 1, name: '多源数据采集（断点续跑 + 流式内存纪律）', done: true },
  { id: 2, name: '清洗融合 + ES 索引（IK 分词 / 别名切换）', done: true },
  { id: 3, name: '混合检索（多面 / 高亮 / 影评检索）', done: true },
  { id: 4, name: 'NLP 分析（归纳词典 / 情感 / 主题）', done: true },
  { id: 5, name: 'Vue3 前端（棕灰主题 · 原系统信息架构承载）', done: true },
  { id: 6, name: '用户 / 推荐 / 趣味 API + 生产可用性加固', done: true },
  { id: 7, name: '全栈 Docker 化 + 交付', done: false },
]

const stack = [
  { layer: '前端', items: 'Vue 3.5 · Vite 7 · Vue Router 4 · ECharts 5（按需引入，无 UI 框架）' },
  { layer: '后端', items: 'FastAPI（异步）· bcrypt + JWT · IP 限流 · TTL 缓存 · liveness/readiness 探针' },
  { layer: '存储与检索', items: 'Elasticsearch 8.15（IK 分词）· 数据湖三层（raw → interim → processed）' },
  { layer: '大数据纪律', items: '流式解析 · 生成器不攒 list · heapq 选 Top-N · 全流程打印实测峰值内存' },
]
</script>

<template>
  <div class="container page">
    <h1 class="page-title">项目说明</h1>
    <p class="page-subtitle">
      电影盒子 —— 多源影评大数据检索与发现平台。本页是给评委与同学的一页速览。
    </p>

    <!-- 天气剧场：晴 / 夜 / 彩虹 / 雨，点击画面或下方标签切换 -->
    <WeatherScene />

    <!-- 平台定位 -->
    <section class="about-section">
      <h2 class="about-section__title">这个平台是什么</h2>
      <p class="about-p">
        电影盒子是一个<strong>检索与发现</strong>平台：搜影片、搜影评、看数据洞察、
        得到「为什么推荐给你」可解释的推荐结果。它承载了上一代电影推荐系统
        （Flask + SQL Server）的信息架构与棕灰主题视觉，底座全面升级为
        大数据技术栈，数据规模从百级扩展到 <strong>5 万级影评</strong>。
      </p>
    </section>

    <!-- 数据流水线 -->
    <section class="about-section">
      <h2 class="about-section__title">数据流水线</h2>
      <ol class="pipeline">
        <li v-for="(p, i) in pipeline" :key="p.stage" class="pipeline__item">
          <span class="pipeline__num">{{ i + 1 }}</span>
          <div>
            <div class="pipeline__stage">{{ p.stage }}</div>
            <div class="pipeline__desc">{{ p.desc }}</div>
          </div>
        </li>
      </ol>
    </section>

    <!-- 数据来源 -->
    <section class="about-section">
      <h2 class="about-section__title">数据来源与合规</h2>
      <table class="about-table">
        <thead>
          <tr><th>数据源</th><th>贡献的字段</th><th>合规性</th></tr>
        </thead>
        <tbody>
          <tr v-for="s in sources" :key="s.name">
            <td class="about-table__name">{{ s.name }}</td>
            <td>{{ s.role }}</td>
            <td class="about-table--muted">{{ s.compliance }}</td>
          </tr>
        </tbody>
      </table>
      <p class="about-note">
        ⚖️ 合规红线：只使用官方开放接口与公开数据集，不抓取豆瓣等受保护站点；
        影评数据仅用于统计分析与算法演示，不代表平台观点。
      </p>
    </section>

    <!-- 技术栈 -->
    <section class="about-section">
      <h2 class="about-section__title">技术栈</h2>
      <table class="about-table">
        <tbody>
          <tr v-for="row in stack" :key="row.layer">
            <td class="about-table__name" style="width:120px">{{ row.layer }}</td>
            <td>{{ row.items }}</td>
          </tr>
        </tbody>
      </table>
    </section>

    <!-- 进度 -->
    <section class="about-section">
      <h2 class="about-section__title">阶段进度</h2>
      <ul class="phase-list">
        <li v-for="p in phases" :key="p.id" class="phase-list__item">
          <span class="phase-list__badge" :class="p.done ? 'phase-list__badge--done' : 'phase-list__badge--todo'">
            {{ p.done ? '✓' : '…' }}
          </span>
          <span :class="{ 'phase-list__name--todo': !p.done }">{{ p.name }}</span>
        </li>
      </ul>
    </section>

    <!-- 接口速览 -->
    <section class="about-section">
      <h2 class="about-section__title">接口速览（27 个）</h2>
      <p class="about-p">
        混合检索 <code>/search/movies</code> · <code>/search/reviews</code>｜洞察
        <code>/insights/sentiment</code> · <code>/trends</code> ·
        <code>/topics</code> · <code>/lexicon</code>｜推荐
        <code>/recommend/popular</code> · <code>/similar/&#123;id&#125;</code> ·
        <code>/for-you</code>｜用户 <code>/auth/*</code> · <code>/ratings</code> ·
        <code>/watchlist</code>｜趣味 <code>/fun/mix</code> · <code>/fun/box</code>｜
        运维 <code>/health/live|ready|metrics</code>
        —— 完整定义见 Swagger：<code>/docs</code>。
      </p>
    </section>
  </div>
</template>

<style scoped>
.about-section { margin-top: 34px; }
.about-section__title {
  font-size: 18px;
  font-weight: 700;
  color: var(--text-main);
  margin-bottom: 14px;
  padding-left: 10px;
  border-left: 4px solid var(--primary-brown);
}
.about-p { font-size: 14.5px; line-height: 1.9; color: var(--text-2); }
.about-p code {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 4px;
  padding: 1px 6px;
  font-size: 12.5px;
  color: var(--primary-brown);
}

/* 流水线 */
.pipeline { list-style: none; padding: 0; margin: 0; }
.pipeline__item {
  display: flex;
  gap: 12px;
  padding: 10px 0;
  border-bottom: 1px dashed var(--border);
  align-items: flex-start;
}
.pipeline__item:last-child { border-bottom: none; }
.pipeline__num {
  flex: none;
  width: 26px; height: 26px;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--primary-brown), var(--primary-gray));
  color: #fff;
  font-size: 13px; font-weight: 700;
  display: grid; place-items: center;
}
.pipeline__stage { font-size: 14.5px; font-weight: 700; color: var(--text-main); }
.pipeline__desc { font-size: 13px; color: var(--text-3); line-height: 1.7; margin-top: 2px; }

/* 表格 */
.about-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13.5px;
  background: var(--surface);
  border-radius: 10px;
  overflow: hidden;
  box-shadow: var(--shadow-sm);
}
.about-table th, .about-table td {
  text-align: left;
  padding: 10px 14px;
  border-bottom: 1px solid var(--border);
  color: var(--text-2);
  line-height: 1.6;
}
.about-table th {
  background: var(--page-bg);
  font-size: 12.5px;
  color: var(--text-3);
  font-weight: 600;
}
.about-table tr:last-child td { border-bottom: none; }
.about-table__name { font-weight: 700; color: var(--text-main); }
.about-table--muted { color: var(--text-3); font-size: 12.5px; }
.about-note {
  margin-top: 10px;
  font-size: 12.5px;
  color: var(--text-3);
  background: var(--surface);
  border-left: 3px solid var(--gold);
  padding: 8px 12px;
  border-radius: 0 8px 8px 0;
}

/* 进度 */
.phase-list { list-style: none; padding: 0; margin: 0; }
.phase-list__item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 0;
  font-size: 14px;
  color: var(--text-main);
  border-bottom: 1px dashed var(--border);
}
.phase-list__item:last-child { border-bottom: none; }
.phase-list__badge {
  flex: none;
  width: 22px; height: 22px;
  border-radius: 50%;
  display: grid; place-items: center;
  font-size: 12px; font-weight: 700;
  color: #fff;
}
.phase-list__badge--done { background: var(--negative); }
.phase-list__badge--todo { background: var(--primary-gray); opacity: 0.6; }
.phase-list__name--todo { color: var(--text-3); }
</style>
