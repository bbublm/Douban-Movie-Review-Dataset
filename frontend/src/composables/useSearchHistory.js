// ============================================================
// 搜索历史 —— 关键词 / 时间 / 结果数量，存 localStorage。
//
// 为什么不用后端：这是纯本机使用痕迹，和个人中心的"我的收藏"不同，
// 不需要跨设备同步，存后端反而多一个隐私口径要解释。
// 清单要求：个人中心可查看、可一键清空 —— 所以做成响应式 ref，
// 任何页面改了它，个人中心立刻跟着变。
// ============================================================
import { ref } from 'vue'

const KEY = 'yj_search_history'
const MAX = 30

function read() {
  try {
    const raw = JSON.parse(localStorage.getItem(KEY) || '[]')
    return Array.isArray(raw) ? raw.filter((x) => x && x.keyword) : []
  } catch {
    return []
  }
}

function write(list) {
  try {
    localStorage.setItem(KEY, JSON.stringify(list))
  } catch {
    /* 隐私模式下 localStorage 不可写：历史丢了不影响主流程 */
  }
}

const items = ref(read())

export const searchHistory = {
  items,
  /** 记一次搜索。同关键词只保留最新一条（更新时间与结果数）。 */
  add(keyword, count = 0) {
    const kw = String(keyword || '').trim()
    if (!kw) return
    const rest = items.value.filter((x) => x.keyword !== kw)
    items.value = [{ keyword: kw, time: Date.now(), count }, ...rest].slice(0, MAX)
    write(items.value)
  },
  remove(keyword) {
    items.value = items.value.filter((x) => x.keyword !== keyword)
    write(items.value)
  },
  /**
   * 回填结果数量。搜索发起时还不知道命中多少条，是结果页拿到
   * total 之后补的 —— 只改 count，不换顺序也不更新时间，
   * 否则同一次搜索会被反复顶到最前面。
   */
  updateCount(keyword, count) {
    const kw = String(keyword || '').trim()
    if (!kw) return
    const hit = items.value.find((x) => x.keyword === kw)
    if (!hit || hit.count === count) return
    hit.count = count
    write(items.value)
  },
  clear() {
    items.value = []
    write(items.value)
  },
}
