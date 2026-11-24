"""
归一化主键 —— 判断「两条记录到底是不是同一部电影」。

★ 为什么融合前必须先做归一化？
    同一部电影在四个源里的「名字」长得完全不一样：
        legacy  : 搏击俱乐部
        TMDB    : 搏击俱乐部（title）/ Fight Club（original_title）
        IMDb    : Fight Club
        Wikidata: Fight Club（zh 标签缺失时会静默回退成英文）
    如果只靠 tmdb_id / imdb_id 硬碰，那 120 部老片库里大半个 id 都是空的，
    它们会全部变成孤儿记录，融合率低到没法看。

三级主键（可信度从高到低）：
    imdb:tt0137523            IMDb tconst，跨源最稳
    tmdb:550                  TMDB 数字 id
    title:搏击俱乐部|1999       片名归一化 + 年份，兜底

★ 标题键为什么一定要带年份？
    不带年份的纯标题键会乱合并：《英雄》2002 和《英雄》2018 是两部毫无关系的电影；
    英文片名重名更夸张（"Crash" 1996 与 2004 同名不同片）。
    带上年份后误合并率降一个数量级，代价只是「同名同年」的极少数会被并到一起 ——
    这个代价远小于乱合并。真不想要，可以用 --no-title-key 关掉。
"""
from __future__ import annotations

import re
import unicodedata

# 消歧义后缀：「搏击俱乐部 (电影)」「Crash (2004 film)」→ 先去掉括号部分再比
#   `(?:\d{4}\s*)?` 是为了吃掉维基风格里的年份前缀 —— 少了它，
#   "Crash (2004 film)" 会归一成 "crash2004film"，和 "Crash" 对不上。
_DISAMBIG_RE = re.compile(
    r"[（(]\s*(?:\d{4}\s*)?(?:电影|影片|电视剧|電視劇|剧集|動畫|动画|纪录片|紀錄片"
    r"|film|movie|tv\s*series|tv\s*film|tv\s*program|series)\s*[)）]\s*$",
    re.IGNORECASE,
)
# 归一化时只保留「字母 / 数字 / 下划线 / 汉字」，其余（空格、标点、&、·、-）全部丢弃
_NON_WORD_RE = re.compile(r"[^\w\u4e00-\u9fff]+", re.UNICODE)


def normalize_title(text: str | None) -> str:
    """片名归一化：NFKC 全角转半角 → 去消歧义后缀 → 转小写 → 去标点与空白。

    例：
        "搏击俱乐部 (电影)"   → "搏击俱乐部"
        "Fight Club"          → "fightclub"
        "Ｆｉｇｈｔ　Ｃｌｕｂ"   → "fightclub"      （全角 → 半角）
        "Schindler's List"    → "schindlerslist"
    """
    if not text:
        return ""
    s = unicodedata.normalize("NFKC", str(text)).strip()
    s = _DISAMBIG_RE.sub("", s)
    s = s.lower()
    s = _NON_WORD_RE.sub("", s)
    return s


def film_keys(record: dict, *, use_title_key: bool = True) -> list[str]:
    """算出这条记录所有可用的对齐主键，按可信度排序。

    返回的是「键的字符串」，不是主键本身 —— 归一化后统一的字符串才好比较，
    也方便直接打印出来给人看（调试时一眼知道它对到了哪个 key）。
    """
    keys: list[str] = []

    # 1) IMDb tconst：必须是 tt + 纯数字，脏值（"N/A" / "tt-1"）直接丢掉
    imdb = str(record.get("imdb_id") or "").strip().lower()
    if imdb.startswith("tt") and imdb[2:].isdigit():
        keys.append(f"imdb:{imdb}")

    # 2) TMDB 数字 id（记录里可能是字符串 "550"，统一转 int）
    tmdb = record.get("tmdb_id")
    try:
        if tmdb:
            keys.append(f"tmdb:{int(tmdb)}")
    except (TypeError, ValueError):
        pass

    # 3) 片名 + 年份兜底
    if use_title_key:
        title = normalize_title(
            record.get("title_zh")
            or record.get("title")
            or record.get("title_en")
            or record.get("original_title")
        )
        year = record.get("release_year")
        try:
            year = int(year) if year else None
        except (TypeError, ValueError):
            year = None
        if title and year:
            keys.append(f"title:{title}|{year}")

    return keys


def best_key(keys: list[str]) -> str:
    """从一组主键里挑一个「代表键」，用于展示与稳定排序。"""
    for prefix in ("imdb:", "tmdb:", "title:"):
        for k in keys:
            if k.startswith(prefix):
                return k
    return keys[0] if keys else ""
