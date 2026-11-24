<script setup>
import { nextTick, onUnmounted, ref } from 'vue'

const running = ref(false)
const activeNode = ref(-1)
const completedNodes = ref([])
const logs = ref([])
const metrics = ref({
  collected: 0,
  parsed: 0,
  discarded: 0,
  stored: 0,
})

const logPanel = ref(null)
let timers = []

const nodes = [
  {
    icon: '📡',
    title: '数据源',
    subtitle: '豆瓣榜单 / TMDB / 国产电影脚本',
    tooltip: '多源读取公开榜单、接口与本地电影脚本，作为采集入口。',
  },
  {
    icon: '🕸️',
    title: '请求与解析',
    subtitle: '页面请求 / 字段解析',
    tooltip: '发起演示请求并解析标题、评分、年份、导演等字段。',
  },
  {
    icon: '🧹',
    title: '清洗转换',
    subtitle: '去重 / 空值过滤 / 标准化',
    tooltip: '去除重复记录、过滤无效字段，并统一数据格式。',
  },
  {
    icon: '🗄️',
    title: 'ES 存储',
    subtitle: 'Elasticsearch 写入索引',
    tooltip: '将清洗后的记录写入电影或影评索引，准备检索。',
  },
  {
    icon: '🔎',
    title: '前端检索',
    subtitle: '入库完成，可检索展示',
    tooltip: '数据可供检索、详情展示和可视化分析使用。',
  },
]

const movies = [
  '流浪地球', '流浪地球2', '战狼2', '长津湖', '哪吒之魔童降世',
  '红海行动', '我不是药神', '中国机长', '满江红', '消失的她',
]

function now() {
  return new Date().toLocaleTimeString('zh-CN', { hour12: false })
}

function clearTimers() {
  timers.forEach(clearTimeout)
  timers = []
}

function later(fn, delay) {
  const timer = setTimeout(fn, delay)
  timers.push(timer)
}

async function appendLog(level, message) {
  logs.value.push({ time: now(), level, message })
  await nextTick()
  if (logPanel.value) logPanel.value.scrollTop = logPanel.value.scrollHeight
}

function addMetric(key, amount) {
  metrics.value[key] += amount
}

function startDemo() {
  if (running.value) return
  running.value = true
  appendLog('INFO', '演示流水线已启动，等待首批数据源响应')

  let cursor = 0
  let collected = 0

  const runBatch = () => {
    if (!running.value || cursor >= movies.length) {
      if (running.value) {
        activeNode.value = 4
        appendLog('DONE', `采集演示完成：已采集 ${metrics.value.collected} 条，入库 ${metrics.value.stored} 条`)
        later(() => {
          running.value = false
        }, 900)
      }
      return
    }

    const movie = movies[cursor]
    cursor += 1
    collected += 1
    activeNode.value = 0
    addMetric('collected', 1)
    appendLog('SOURCE', `读取数据源：《${movie}》记录已进入采集队列`)

    later(() => {
      if (!running.value) return
      activeNode.value = 1
      appendLog('PARSE', `解析成功：《${movie}》字段映射完成`)
      addMetric('parsed', 1)
    }, 700)

    later(() => {
      if (!running.value) return
      activeNode.value = 2
      if (cursor % 4 === 0) {
        addMetric('discarded', 1)
        appendLog('WARN', `脏数据丢弃：《${movie}》评分字段为空或格式异常`)
      } else {
        appendLog('CLEAN', `清洗通过：《${movie}》去重与字段标准化完成`)
      }
      if (!completedNodes.value.includes(2)) completedNodes.value.push(2)
    }, 1400)

    later(() => {
      if (!running.value) return
      activeNode.value = 3
      if (cursor % 4 !== 0) {
        addMetric('stored', 1)
        appendLog('ES', `Elasticsearch 写入成功：《${movie}》分片索引已更新`)
      }
      if (!completedNodes.value.includes(3)) completedNodes.value.push(3)
    }, 2100)

    later(() => {
      if (!running.value) return
      activeNode.value = 4
      if (cursor % 4 !== 0) {
        appendLog('SEARCH', `前端检索就绪：《${movie}》可通过关键词检索展示`)
      }
      if (!completedNodes.value.includes(4)) completedNodes.value.push(4)
      later(runBatch, 600)
    }, 2800)
  }

  if (!completedNodes.value.includes(0)) completedNodes.value.push(0)
  runBatch()
}

function resetDemo() {
  clearTimers()
  running.value = false
  activeNode.value = -1
  completedNodes.value = []
  logs.value = []
  metrics.value = { collected: 0, parsed: 0, discarded: 0, stored: 0 }
  appendLog('RESET', '演示状态已重置')
  later(() => {
    if (!running.value) logs.value = []
  }, 250)
}

onUnmounted(clearTimers)
</script>

<template>
  <div class="crawl-demo">
    <header class="crawl-demo__header">
      <div>
        <p class="crawl-demo__eyebrow">MOVIE BOX · DATA PIPELINE</p>
        <h1>📡 爬虫采集流水线演示中心</h1>
      </div>
      <div class="crawl-demo__actions">
        <button class="crawl-demo__button crawl-demo__button--primary" :disabled="running" @click="startDemo">
          <span>{{ running ? '采集演示进行中' : '开始采集演示' }}</span>
        </button>
        <button class="crawl-demo__button" :disabled="!running && !logs.length && !metrics.collected" @click="resetDemo">
          重置演示
        </button>
      </div>
    </header>

    <section class="crawl-metrics" aria-label="采集指标">
      <article>
        <span>已采集总数</span>
        <strong>{{ metrics.collected }}</strong>
        <small>records collected</small>
      </article>
      <article>
        <span>解析成功</span>
        <strong>{{ metrics.parsed }}</strong>
        <small>fields parsed</small>
      </article>
      <article>
        <span>清洗丢弃</span>
        <strong>{{ metrics.discarded }}</strong>
        <small>invalid dropped</small>
      </article>
      <article>
        <span>入库成功</span>
        <strong>{{ metrics.stored }}</strong>
        <small>indexed records</small>
      </article>
    </section>

    <section class="pipeline-panel" aria-label="动态采集链路">
      <div class="pipeline-track">
        <template v-for="(node, index) in nodes" :key="node.title">
          <article
            class="pipeline-node"
            :class="{ 'is-active': activeNode === index, 'is-complete': completedNodes.includes(index) }"
            :aria-label="node.tooltip"
          >
            <span class="pipeline-node__icon">{{ node.icon }}</span>
            <strong>{{ node.title }}</strong>
            <small>{{ node.subtitle }}</small>
            <span class="pipeline-node__tooltip">{{ node.tooltip }}</span>
          </article>
          <div v-if="index < nodes.length - 1" class="pipeline-link" :class="{ 'is-active': activeNode === index + 1 }">
            <span v-for="particle in 3" :key="particle" class="pipeline-particle" :style="{ '--particle-delay': `${particle * 0.28}s` }"></span>
            <span class="pipeline-link__arrow">›</span>
          </div>
        </template>
      </div>
    </section>

    <section class="terminal-panel" aria-label="采集终端日志">
      <header>
        <div class="terminal-dots"><i></i><i></i><i></i></div>
        <span>crawler-pipeline.log</span>
        <b>{{ running ? 'LIVE' : 'STANDBY' }}</b>
      </header>
      <div ref="logPanel" class="terminal-body">
        <div v-if="!logs.length" class="terminal-empty">
          等待启动采集演示…
        </div>
        <div v-for="(log, index) in logs" :key="`${log.time}-${index}`" class="terminal-line">
          <time>{{ log.time }}</time>
          <b :class="`level-${log.level.toLowerCase()}`">[{{ log.level }}]</b>
          <span>{{ log.message }}</span>
        </div>
      </div>
    </section>
  </div>
</template>

<style scoped>
.crawl-demo {
  min-height: calc(100vh - 72px);
  padding: 28px 34px 36px;
  color: #4a3527;
  background:
    radial-gradient(circle at 12% 12%, rgba(205, 176, 124, 0.12), transparent 25%),
    linear-gradient(135deg, #f6f0e6 0%, #eee4d4 100%);
}
.crawl-demo__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 20px;
  margin-bottom: 20px;
}
.crawl-demo__eyebrow {
  margin: 0 0 5px;
  color: #9a7c55;
  font-size: 11px;
  letter-spacing: 0.16em;
  font-weight: 800;
}
.crawl-demo h1 { margin: 0; font-size: clamp(24px, 3vw, 38px); }
.crawl-demo__actions { display: flex; gap: 10px; }
.crawl-demo__button {
  min-height: 44px;
  padding: 0 18px;
  border: 1px solid #bda889;
  border-radius: 12px;
  background: rgba(255, 252, 246, 0.82);
  color: #5b4634;
  font-weight: 800;
  cursor: pointer;
}
.crawl-demo__button--primary {
  border-color: #b88a45;
  background: linear-gradient(135deg, #d8b56f, #b78a4a);
  color: #fffaf0;
  box-shadow: 0 8px 24px rgba(150, 111, 59, 0.18);
}
.crawl-demo__button:disabled { cursor: not-allowed; opacity: 0.58; }

.crawl-metrics {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}
.crawl-metrics article {
  position: relative;
  min-height: 102px;
  padding: 16px 18px;
  border: 1px solid rgba(157, 126, 82, 0.24);
  border-radius: 14px;
  background: rgba(255, 252, 246, 0.78);
  box-shadow: 0 10px 30px rgba(96, 72, 48, 0.07);
}
.crawl-metrics span { display: block; color: #80684e; font-size: 13px; font-weight: 700; }
.crawl-metrics strong {
  display: block;
  margin-top: 4px;
  color: #9a6b32;
  font-family: Georgia, serif;
  font-size: 32px;
  line-height: 1;
  font-variant-numeric: tabular-nums;
}
.crawl-metrics small { position: absolute; right: 14px; bottom: 12px; color: #b4a693; }

.pipeline-panel {
  height: 220px;
  display: flex;
  align-items: center;
  overflow-x: auto;
  margin-bottom: 16px;
  border: 1px solid rgba(157, 126, 82, 0.22);
  border-radius: 16px;
  background: rgba(255, 252, 246, 0.62);
}
.pipeline-track {
  width: 100%;
  min-width: 900px;
  display: grid;
  grid-template-columns: 150px minmax(48px, 1fr) 150px minmax(48px, 1fr) 150px minmax(48px, 1fr) 150px minmax(48px, 1fr) 150px;
  align-items: center;
  padding: 22px 28px;
}
.pipeline-node {
  position: relative;
  height: 154px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  border: 1px solid #d3c8b7;
  border-radius: 16px;
  background: #ede7dc;
  color: #978b7d;
  transition: 0.35s ease;
}
.pipeline-node.is-complete { border-color: #c3a875; background: #f5eddf; color: #71583e; }
.pipeline-node.is-active {
  border-color: #cf9f50;
  background: linear-gradient(160deg, #fff9e9, #ead9b6);
  color: #60452b;
  box-shadow: 0 0 0 4px rgba(211, 168, 92, 0.12), 0 14px 30px rgba(154, 111, 57, 0.16);
  transform: translateY(-3px);
}
.pipeline-node__icon { font-size: 30px; margin-bottom: 8px; filter: grayscale(0.7); }
.pipeline-node.is-active .pipeline-node__icon { filter: none; }
.pipeline-node strong { font-size: 15px; }
.pipeline-node small { max-width: 128px; margin-top: 7px; line-height: 1.35; font-size: 11px; }
.pipeline-node__tooltip {
  position: absolute;
  z-index: 10;
  left: 50%;
  bottom: calc(100% + 10px);
  width: 210px;
  padding: 9px 11px;
  border-radius: 8px;
  background: #4b392a;
  color: #fff8e8;
  font-size: 12px;
  line-height: 1.45;
  opacity: 0;
  pointer-events: none;
  transform: translate(-50%, 5px);
  transition: 0.18s ease;
}
.pipeline-node:hover .pipeline-node__tooltip { opacity: 1; transform: translate(-50%, 0); }
.pipeline-link {
  position: relative;
  height: 2px;
  margin: 0 4px;
  background: #d1c5b4;
  overflow: visible;
}
.pipeline-link.is-active { background: linear-gradient(90deg, #d1c5b4 10%, #d3a54f 90%); }
.pipeline-link__arrow { position: absolute; right: -2px; top: -10px; color: #baa889; font-size: 18px; }
.pipeline-particle {
  position: absolute;
  top: -3px;
  left: 0;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #d0a04d;
  box-shadow: 0 0 10px #d0a04d;
  opacity: 0;
}
.pipeline-link.is-active .pipeline-particle {
  animation: crawl-particle 1.8s linear var(--particle-delay) infinite;
}
@keyframes crawl-particle {
  0% { left: 0; opacity: 0; }
  12% { opacity: 1; }
  88% { opacity: 1; }
  100% { left: calc(100% - 8px); opacity: 0; }
}

.terminal-panel {
  height: 330px;
  overflow: hidden;
  border: 1px solid #332d25;
  border-radius: 14px;
  background: #171715;
  box-shadow: 0 16px 40px rgba(55, 44, 33, 0.16);
}
.terminal-panel header {
  height: 42px;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 0 14px;
  border-bottom: 1px solid #35342f;
  color: #aaa99f;
  font-family: Consolas, "Courier New", monospace;
  font-size: 12px;
}
.terminal-panel header b { margin-left: auto; color: #79c89a; font-size: 10px; letter-spacing: 0.12em; }
.terminal-dots { display: flex; gap: 5px; }
.terminal-dots i { width: 8px; height: 8px; border-radius: 50%; background: #b56555; }
.terminal-dots i:nth-child(2) { background: #c39b55; }
.terminal-dots i:nth-child(3) { background: #6c9f76; }
.terminal-body {
  height: 288px;
  overflow-y: auto;
  padding: 14px 16px 18px;
  color: #cfe7d3;
  font: 13px/1.8 Consolas, "Courier New", monospace;
  scrollbar-color: #5d675f #23231f;
}
.terminal-empty { color: #777c74; }
.terminal-line { display: grid; grid-template-columns: 82px 74px 1fr; gap: 8px; }
.terminal-line time { color: #777d74; }
.terminal-line b { color: #82a58b; }
.level-warn { color: #e0b66a !important; }
.level-es, .level-done, .level-search { color: #73cca2 !important; }
.level-reset { color: #d78f75 !important; }

@media (max-width: 900px) {
  .crawl-demo { padding: 20px 16px 28px; }
  .crawl-demo__header { align-items: flex-start; }
  .crawl-metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .terminal-line { grid-template-columns: 74px 68px 1fr; }
}
@media (max-width: 600px) {
  .crawl-demo__header { flex-direction: column; }
  .crawl-demo__actions { width: 100%; }
  .crawl-demo__button { flex: 1; padding: 0 10px; }
  .crawl-metrics { grid-template-columns: 1fr 1fr; }
  .crawl-metrics article { min-height: 94px; padding: 14px; }
  .crawl-metrics strong { font-size: 28px; }
  .crawl-metrics small { display: none; }
  .terminal-line { grid-template-columns: 72px 64px 1fr; font-size: 12px; }
}
</style>
