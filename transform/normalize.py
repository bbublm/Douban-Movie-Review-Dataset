"""
分面字段归一化 —— 把多源融合后的「脏枚举值」收敛成一套标准中文短名。

为什么需要这个文件（一次真实事故的教训）：
    阶段 5.5 走查时发现检索页的类型分面出现了 40+ 个桶：
    「冒险 111 / 动作 109 / 动作片 107 / 冒险电影 87」——
    同一部电影的类型列表里同时躺着短名（TMDB）、长名（Wikidata 的维基分类名，
    如「动作片」「超级英雄电影」）、英文标签（如 crime thriller film）
    和繁体（如「文明崩潰後世界題材電影」）。根因：LIST_FIELDS 取各源并集时
    没有做值域归一，四个源四种写法直接并排展示。

    国家/语言同样中英双份（美国 222 + United States of America 149），
    语言里甚至混进了空字符串。

设计取舍：
    1. **只收敛展示层枚举，不动原文** —— interim 的原始值保持原样
       （raw 是 raw），归一化发生在 transform 定稿（finalize）时，
       可随时重跑调参。
    2. **类型未知名一律丢弃（返回 None）** —— 维基分类有 151 种值，
       大量是「Greatest Movie Hits」这种噪音；丢掉的只是分面噪音，
       genres_en 仍保留英文原值供检索匹配，信息不丢。
    3. **国家/语言未知名原样保留** —— 这两个域值空间小（57/33 种），
       映射表全覆盖；万一将来来了没见过的值，保留好过静默丢失。
    4. 归一化顺序：繁体转简体 → 命中标准集 → 显式映射 → 去后缀再命中。
       「纪录片」「电视电影」先查标准集再去后缀，否则会被误切成「纪录」。
"""
from __future__ import annotations

# ============================================================
# 标准类型集（TMDB 官方中文类型 + 功能清单点名的两个）
# ============================================================
CANONICAL_GENRES: frozenset[str] = frozenset({
    "动作", "冒险", "动画", "喜剧", "犯罪", "纪录片", "剧情", "家庭",
    "奇幻", "历史", "恐怖", "音乐", "悬疑", "爱情", "科幻", "惊悚",
    "战争", "西部", "武侠", "黑色电影", "电视电影",
})

# 繁体 → 简体（只收分面值里实际出现过的字，够用即可；opencc 是大依赖，不值当）
_T2S: dict[str, str] = {
    "電": "电", "影": "影", "畫": "画", "動": "动", "劇": "剧", "喜": "喜",
    "驚": "惊", "懸": "悬", "歷": "历", "戰": "战", "愛": "爱", "情": "情",
    "犯": "犯", "罪": "罪", "恐": "恐", "怖": "怖", "作": "作",
    "俠": "侠", "盜": "盗", "紀": "纪", "錄": "录", "偽": "伪", "題": "题",
    "材": "材", "後": "后", "世": "世", "界": "界", "崩": "崩", "潰": "溃",
    "黑": "黑", "幫": "帮", "復": "复", "仇": "仇", "心": "心", "理": "理",
    "血": "血", "鬼": "鬼", "吸": "吸", "搶": "抢", "劫": "劫", "運": "运",
    "監": "监", "獄": "狱", "科": "科", "技": "技", "政": "政", "治": "治",
    "時": "时", "代": "代", "浪": "浪", "漫": "漫", "長": "长", "成": "成",
}

# 细粒度类型 / 英文标签 → 标准类型（覆盖 wikidata 源实际出现的 151 种值）
GENRE_MAP: dict[str, str] = {
    # --- 带「电影/片」后缀的维基分类名 ---
    "动作片": "动作", "冒险电影": "冒险", "剧情片": "剧情", "喜剧电影": "喜剧",
    "科幻电影": "科幻", "奇幻电影": "奇幻", "惊悚电影": "惊悚", "犯罪片": "犯罪",
    "恐怖电影": "恐怖", "家庭电影": "家庭", "历史片": "历史", "爱情片": "爱情",
    "战争片": "战争", "动画电影": "动画", "歌舞片": "音乐", "传记电影": "剧情",
    "西部片": "西部", "神秘片": "悬疑", "成长片": "剧情",
    # --- 细粒度中文分类 ---
    "超级英雄电影": "动作", "剧情喜剧片": "喜剧", "史诗片": "剧情",
    "反乌托邦电影": "科幻", "文明崩溃后世界题材电影": "科幻", "黑色幽默电影": "喜剧",
    "黑色幽默": "喜剧", "悲喜剧": "剧情", "黑色科幻片": "科幻",
    "儿童电影": "家庭", "新黑色电影": "黑色电影", "硬科幻电影": "科幻",
    "伙伴片": "喜剧", "倒叙电影": "剧情", "青春片": "剧情", "动作惊悚片": "惊悚",
    "浪漫喜劇": "爱情", "浪漫片": "爱情", "動作喜劇": "喜剧", "同志片": "剧情",
    "嘲讽电影": "喜剧", "怪兽电影": "科幻", "独立电影": "剧情", "科幻动作片": "科幻",
    "超自然恐怖": "恐怖", "黑幫電影": "犯罪", "丧尸片": "恐怖", "丧尸喜剧": "恐怖",
    "圣诞电影": "家庭", "復仇電影": "剧情", "心理剧电影": "剧情", "心理恐怖電影": "恐怖",
    "心理惊悚片": "惊悚", "心理恐怖": "恐怖", "武侠电影": "武侠", "灾难片": "动作",
    "生存片": "惊悚", "神话片": "奇幻", "间谍片": "惊悚", "飞溅电影": "恐怖",
    "俠盜片": "犯罪", "剑与凉鞋": "动作", "太空歌剧": "科幻", "寻宝电影": "冒险",
    "搶劫片": "犯罪", "警察搭檔片": "喜剧", "運動電影": "剧情", "真人动画电影": "动画",
    "肢解电影": "恐怖", "科幻西部": "科幻", "恐怖喜剧": "喜剧", "警匪片": "犯罪",
    "古装剧": "历史", "吸血鬼電影": "恐怖", "浪漫主义戏剧": "爱情", "生物朋克": "科幻",
    "公路电影": "剧情", "赛博朋克": "科幻", "情色電影": "剧情", "军事科幻小说": "科幻",
    "中世纪主题电影": "历史", "黑暗奇幻": "奇幻", "偽紀錄片": "喜剧", "性喜剧": "喜剧",
    "奇幻日本动漫": "动画", "超自然日本动画": "动画", "电脑动画电影": "动画",
    "時代劇": "历史", "推理作品": "悬疑", "严肃奇幻": "奇幻", "神魔小说": "奇幻",
    "跨界作品": "剧情", "修正主义西部片": "西部", "黑人剥削电影": "犯罪",
    "荒诞作品": "喜剧", "奇幻喜剧": "喜剧", "审判电影": "剧情", "政治讽刺": "喜剧",
    "架空历史电影": "科幻", "脱线喜剧": "喜剧", "多段式电影": "剧情",
    "外星生命入侵": "科幻", "政治剧": "剧情", "政治驚悚片": "惊悚", "監獄電影": "剧情",
    "科技驚悚": "惊悚", "功夫片": "动作", "硬科幻": "科幻", "异世界": "动画",
    "stitchpunk": "动画", "Hopecore": "动画",
    # --- 不是类型的噪音值：显式丢弃 ---
    "Greatest Movie Hits": None,  # type: ignore[dict-item]
    # --- 英文维基标签 ---
    "crime thriller film": "惊悚", "crime drama film": "犯罪", "suspense film": "悬疑",
    "romantic comedy film": "爱情", "historical drama film": "历史",
    "science fiction horror film": "恐怖", "ghost film": "恐怖",
    "psychological thriller film": "惊悚", "detective film": "悬疑",
    "magic realist film": "奇幻", "pirate film": "冒险", "satirical film": "喜剧",
    "time-travel film": "科幻", "action-adventure film": "动作", "ninja film": "动作",
    "romantic drama film": "爱情", "sword and sorcery film": "奇幻",
    "white savior film": "剧情", "Gothic film": "恐怖", "body horror film": "恐怖",
    "desire horror fiction": "恐怖", "fantasy epic film": "奇幻",
    "technofantasy": "科幻", "war drama": "战争", "crime comedy film": "喜剧",
    "chase film": "动作", "tech-noir film": "科幻", "police procedural film": "犯罪",
    "werewolf film": "恐怖", "anti-war film": "战争", "contemporary Western film": "西部",
    "high school film": "剧情", "classical antiquity film": "历史",
    "adventure science fiction": "科幻", "漫画科幻作品": "科幻",
    "arthouse science fiction film": "剧情",
}

# 国家：英文/别称 → 标准中文名（覆盖 interim 全部 57 种）
COUNTRY_MAP: dict[str, str] = {
    "United States of America": "美国", "USA": "美国", "US": "美国",
    "United Kingdom": "英国", "UK": "英国", "中华人民共和国": "中国", "China": "中国",
    "Hong Kong": "中国香港", "香港": "中国香港", "大韩民国": "韩国", "South Korea": "韩国",
    "France": "法国", "Germany": "德国", "Canada": "加拿大", "Australia": "澳大利亚",
    "Japan": "日本", "Italy": "意大利", "New Zealand": "新西兰", "Spain": "西班牙",
    "Mexico": "墨西哥", "Ireland": "爱尔兰", "爱尔兰岛": "爱尔兰",
    "Denmark": "丹麦", "Sweden": "瑞典", "Brazil": "巴西", "India": "印度",
    "Russia": "俄罗斯", "Greece": "希腊", "Turkey": "土耳其", "Norway": "挪威",
    "Argentina": "阿根廷", "Israel": "以色列", "Switzerland": "瑞士",
    "Morocco": "摩洛哥", "Belgium": "比利时", "Netherlands": "荷兰",
    "Thailand": "泰国", "Indonesia": "印尼", "Poland": "波兰",
    "Czech Republic": "捷克", "Austria": "奥地利", "Finland": "芬兰",
    "Ukraine": "乌克兰", "Philippines": "菲律宾", "Romania": "罗马尼亚",
    "Venezuela": "委内瑞拉", "Chile": "智利", "Colombia": "哥伦比亚",
    "Hungary": "匈牙利",
}

# 语言：英文/外文 → 标准中文名（覆盖 interim 全部 33 种；空串直接丢）
LANGUAGE_MAP: dict[str, str] = {
    "English": "英语", "Español": "西班牙语", "Français": "法语",
    "Pусский": "俄语", "Русский": "俄语", "日本語": "日语", "Italiano": "意大利语",
    "한국어/조선말": "韩语", "Deutsch": "德语", "Português": "葡萄牙语",
    "广州话 / 廣州話": "粤语", "粤语": "粤语", "العربية": "阿拉伯语",
    "עִבְרִית": "希伯来语", "svenska": "瑞典语", "普通话": "汉语", "汉语": "汉语",
    "ภาษาไทย": "泰语", "Bahasa indonesia": "印尼语", "Latin": "拉丁语",
    "Magyar": "匈牙利语", "ελληνικά": "希腊语",
}


def _t2s(text: str) -> str:
    """繁体转简体（只处理映射表里收的字）。"""
    return "".join(_T2S.get(ch, ch) for ch in text)


def _strip_suffix(text: str) -> str:
    """去掉「电影/电视/影片/片」后缀（只在后缀前还有内容时）。"""
    for suf in ("电影", "电视", "影片", "片"):
        if text.endswith(suf) and len(text) > len(suf):
            return text[: -len(suf)]
    return text


def normalize_genre(value: object) -> str | None:
    """把任意源的类型值归一成标准中文类型；无法识别返回 None（丢弃）。

    顺序：繁体转简体 → 命中标准集 → 显式映射 → 去后缀再命中。
    """
    if not isinstance(value, str):
        return None
    text = _t2s(value.strip())
    if not text:
        return None
    if text in CANONICAL_GENRES:
        return text
    mapped = GENRE_MAP.get(text, GENRE_MAP.get(value.strip()))
    if mapped is not None or text in GENRE_MAP:
        return mapped
    stripped = _strip_suffix(text)
    if stripped != text and stripped in CANONICAL_GENRES:
        return stripped
    return None


def normalize_country(value: object) -> str | None:
    """国家归一：英文/别称 → 标准中文名；未知名原样保留（不丢数据）。"""
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    return COUNTRY_MAP.get(text, text)


def normalize_language(value: object) -> str | None:
    """语言归一：外文 → 标准中文名；未知名原样保留，空串丢弃。"""
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    return LANGUAGE_MAP.get(text, text)


def _uniq_keep_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for v in values:
        if v not in seen:
            seen.add(v)
            out.append(v)
    return out


def normalize_genres(values: object) -> list[str]:
    """类型列表归一 + 去重保序。"""
    if not isinstance(values, (list, tuple)):
        return []
    out = [g for g in (normalize_genre(v) for v in values) if g]
    return _uniq_keep_order(out)


def normalize_countries(values: object) -> list[str]:
    if not isinstance(values, (list, tuple)):
        return []
    out = [c for c in (normalize_country(v) for v in values) if c]
    return _uniq_keep_order(out)


def normalize_languages(values: object) -> list[str]:
    if not isinstance(values, (list, tuple)):
        return []
    out = [x for x in (normalize_language(v) for v in values) if x]
    return _uniq_keep_order(out)


# ============================================================
# 主出品国（国家分面口径，2026-10-20 用户定调）
# ============================================================
# 「国家」筛选只按主出品国算，不带合拍国：
# 《毒液》制片国是 [中国, 美国]（腾讯影业联合出品），但用户语义上
# 认为"美国片"。TMDB 的国家列表顺序不可靠（毒液那条恰好把中国排
# 前面），Wikidata 行序也无保证 —— 所以用「影片原始语言」锁定主出品国：
# 语言对应的国家若在制片国列表里，取它；否则退回列表第一项。
# 纯函数、可离线自检。
_LANG_PRIMARY_COUNTRY: dict[str, tuple[str, ...]] = {
    "en": ("美国", "英国"),      # 英语片美/英优先（美在英前）
    "zh": ("中国",), "cn": ("中国",), "yue": ("中国香港", "中国台湾", "中国"),
    "ja": ("日本",), "ko": ("韩国",), "fr": ("法国",), "de": ("德国",),
    "es": ("西班牙", "墨西哥", "阿根廷"), "it": ("意大利",),
    "ru": ("俄罗斯",), "hi": ("印度",), "pt": ("葡萄牙", "巴西"),
    "th": ("泰国",), "sv": ("瑞典",), "da": ("丹麦",), "no": ("挪威",),
    "fi": ("芬兰",), "nl": ("荷兰",), "pl": ("波兰",), "tr": ("土耳其",),
    "id": ("印度尼西亚",), "ms": ("马来西亚",), "vi": ("越南",),
    "tl": ("菲律宾",), "ar": ("埃及", "黎巴嫩"), "fa": ("伊朗",),
    "cs": ("捷克",), "hu": ("匈牙利",), "el": ("希腊",), "is": ("冰岛",),
}


def pick_primary_country(
    countries_zh: list[str], original_language: str | None
) -> str | None:
    """从归一化后的制片国列表里挑出主出品国。

    规则：原始语言对应的首选国命中列表 → 取它；否则取列表第一项
    （各源把主出品国放首位的情况仍占多数）；列表为空 → None。
    """
    if not countries_zh:
        return None
    pref = _LANG_PRIMARY_COUNTRY.get((original_language or "").lower()) or ()
    for cand in pref:
        if cand in countries_zh:
            return cand
    return countries_zh[0]


# ============================================================
# 地点名归一化（足迹地图用）
# ============================================================
# 繁体→简体：地点名 583 个用字逐一核对后的全集（jieba 简体词典反查
# 只能捞出 32 个 —— 词典里恰好收录了「國際」「時裝」这类繁体词，
# 会长+國+時 漏网；所以这张表按全量用字人工核对，不依赖词典）。
# 只收地点名里实际出现的繁体字；英文/虚构地名（Alabama Hills /
# Caladan）不走这张表，原样保留。
_T2S_PLACE: dict[str, str] = {
    # -- 检测集首轮捞出的 32 个 --
    "倫": "伦", "區": "区", "喬": "乔", "壩": "坝", "奧": "奥", "橋": "桥",
    "機": "机", "濟": "济", "濱": "滨", "獄": "狱", "約": "约", "聖": "圣",
    "艦": "舰", "莊": "庄", "華": "华", "萊": "莱", "號": "号", "衛": "卫",
    "製": "制", "貝": "贝", "買": "买", "邊": "边", "鐸": "铎", "隊": "队",
    "際": "际", "韋": "韦", "頓": "顿", "館": "馆", "馬": "马", "魯": "鲁",
    "龍": "龙",
    # -- 词典反查漏网、全量核对补收 --
    "亞": "亚", "島": "岛", "場": "场", "園": "园", "國": "国", "壘": "垒",
    "夢": "梦", "爾": "尔", "寶": "宝", "學": "学", "宮": "宫", "時": "时",
    "會": "会", "樓": "楼", "環": "环", "畫": "画", "瘋": "疯", "監": "监",
    "磯": "矶", "戰": "战", "納": "纳", "維": "维", "羅": "罗", "藝": "艺",
    "蘭": "兰", "覺": "觉", "軍": "军", "辦": "办", "達": "达", "醫": "医",
    "鎮": "镇", "長": "长", "門": "门", "開": "开", "顛": "颠", "髮": "发",
    "麥": "麦", "嶼": "屿", "縣": "县", "灣": "湾", "鋼": "钢", "鐵": "铁",
    "圖": "图", "攝": "摄", "劇": "剧", "獲": "获", "澤": "泽", "鳳": "凤",
    "飛": "飞", "鳥": "鸟", "龜": "龟", "齒": "齿", "齡": "龄", "廠": "厂",
}

# 地点全称 → 通用短名。只收与 production_countries 口径冲突的
# （同一部片「制作国家=中国」而「故事发生地=中华人民共和国」时，
#  地图上会并排出现两个点，用户以为数据错了）。
PLACE_MAP: dict[str, str] = {
    "中华人民共和国": "中国",
}


def normalize_place(value: object) -> str | None:
    """地点名归一：繁体→简体 + 全称→短名。无法识别原样保留（不丢点位）。

    英文地名（如 Alabama Hills）与虚构地名（如 Caladan、Gargantua）
    一律原样保留 —— 前者没有可靠的机器翻译，后者翻译了反而错。
    """
    if not isinstance(value, str):
        return None
    text = "".join(_T2S_PLACE.get(ch, ch) for ch in value.strip())
    if not text:
        return None
    return PLACE_MAP.get(text, text)


def normalize_places(values: object) -> list[dict]:
    """filming_locations 列表归一：地名归一 + 按 (地名, lat, lon) 去重。

    去重必须放在归一之后：繁体简体两条（「長島」「长岛」）在合并期
    按原值去重是两条，归一后撞车，定稿期再收一次口子。
    """
    if not isinstance(values, (list, tuple)):
        return []
    seen: set[tuple] = set()
    out: list[dict] = []
    for p in values:
        if not isinstance(p, dict):
            continue
        q = dict(p)
        name = normalize_place(q.get("name"))
        if not name:
            continue
        q["name"] = name
        sig = (name, q.get("lat"), q.get("lon"))
        if sig in seen:
            continue
        seen.add(sig)
        out.append(q)
    return out
