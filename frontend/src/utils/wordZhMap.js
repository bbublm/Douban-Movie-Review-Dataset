// ============================================================
// 英文影评情感词 → 中文释义映射（前端展示用）。
//
// 背景：影评数据集是英文的（Kaggle 50k IMDB 影评），语料本身没有
// 中文标注（中文影评涉及合规限制，不采集）。所以"热词"只能是英文词。
// 为了在中文界面呈现，这里归纳一份"英文影评情感词 → 中文释义"的
// 对照表，仅用于**展示层翻译**，点击检索时仍使用英文原词（ES 里影评
// 是英文文档，中文检索召回不到）。
//
// 原则：
//   · 评价/情感词 → 翻译成地道中文影评用语（烂片/精湛/唯美…）
//   · 专名（导演、演员、梗词）→ 不翻，保留原文（如 uwe=Uwe Boll、
//     mst=MST3K、manos=《Manos》烂片梗），否则会翻出无意义的中文
//   · 未收录的词 → 返回 null，调用方回退显示英文原词
// ============================================================

const MAP = {
  // ---- 负面情感/评价词 ----
  waste: '浪费',
  awful: '糟糕透顶',
  poorly: '差劲',
  terrible: '糟透了',
  laughable: '可笑',
  lame: '蹩脚',
  redeeming: '可取之处',
  pointless: '毫无意义',
  unfunny: '一点不好笑',
  stinker: '烂片',
  horrible: '糟糕',
  wasted: '白白浪费',
  crap: '烂货',
  stupid: '愚蠢',
  pathetic: '可悲',
  atrocious: '恶劣',
  amateurish: '业余',
  unwatchable: '没法看',
  incoherent: '混乱',
  garbage: '垃圾',
  wasting: '浪费',
  sucks: '烂透了',
  boring: '无聊',
  mess: '一团糟',
  lousy: '极差',
  avoid: '避坑',
  uninteresting: '乏味',
  badly: '糟糕地',
  ridiculous: '荒唐',
  dull: '沉闷',
  remotely: '丝毫',
  worst: '最差',
  insult: '侮辱',
  stunk: '烂臭',
  uninspired: '缺乏新意',
  drivel: '胡言乱语',
  idiotic: '愚蠢透顶',
  pile: '一堆烂货',
  yawn: '昏昏欲睡',
  unconvincing: '难以信服',
  insulting: '充满冒犯',
  dreck: '垃圾片',
  turd: '烂作',

  // ---- 正面情感/评价词 ----
  superb: '精湛',
  beautifully: '唯美',
  wonderfully: '精彩绝伦',
  excellent: '精彩',
  wonderful: '美妙',
  flawless: '完美无瑕',
  refreshing: '耳目一新',
  excellently: '出色',
  influential: '有影响力',
  superbly: '极佳',
  delightful: '愉悦',
  understated: '含蓄克制',
  magnificent: '宏大',
  brilliantly: '精彩',
  pleasantly: '令人愉悦',
  perfection: '完美',
  unforgettable: '难忘',
  gem: '佳作',
  captures: '精准捕捉',
  underrated: '被低估',
  loneliness: '孤独感',
  poignant: '动人',
  extraordinary: '非凡',
  marvellous: '了不起',
  breathtaking: '震撼',
  friendship: '友谊',
  outstanding: '出众',
  touching: '暖心',
  finest: '上乘',
  splendid: '壮丽',
  simplicity: '简洁动人',
  accessible: '平易近人',
  sadness: '忧伤',
  viewings: '反复重看',
}

/** 返回词的中文释义；未收录或专名返回 null（调用方回退英文原词）。 */
export function toZh(word) {
  if (!word) return null
  const key = String(word).toLowerCase()
  return MAP[key] ?? null
}
