"""
生成 frontend/public/data/movies.json —— 电影宇宙 3D 星系的【真实数据】源。

数据全部来自 Elasticsearch（项目真实数据），没有任何 mock：
  · 节点 = 真实电影（movies 索引，488 部）
  · 位置 x/y/z = 真实文本语义降维：对 标题+类型+简介+关键词 做
        TF-IDF(中文 jieba 分词) + TruncatedSVD(3)，语义相近的电影真聚在一起
        （这是真实的降维，不是随机坐标；电影侧无 embedding 向量，故用 SVD 近似 UMAP）
  · 情感 sentiment = 真实影评情感：用项目自带 analysis/sentiment.py 引擎
        对「挂了 movie_id 的真实 TMDB 影评」逐条按真实语言打分再取均值；
        仅 ≥5 条影评的电影才输出实测情感（避免单条/极少数影评的代表性偏差），
        其余用 vote_average 做【评分代理】并明确标注 sentiment_source / review_count / review_lang；
        review_lang 记录该电影影评的语言构成（en 英文为主 / zh 中文 / mix 混合）
  · 分歧/引力透镜 divergence = 真实影评分歧度（该电影多条影评情感的标准差），
        取分歧最大的 Top12 作为引力源（数据不支持「中外分歧」，如实改为「影评争议焦点」）
  · 六维方面 aspects = 真实影评的方面情感：剧情/演技/特效/节奏/结局/音乐 关键词
        命中影评后汇总其情感分，仅对有影评的电影输出（其余为 null，前端隐藏雷达）
  · 相似度 similarity_ids = 真实 3D 坐标的 k 近邻（语义邻近）
  · 大小 = 真实 vote_count；颜色 = 情感极性

运行：python scripts/build_cosmos_data.py
依赖：numpy / sklearn（已装）；elasticsearch 走 HTTP（http://localhost:9200）
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
PUBLIC_DATA = ROOT / "frontend" / "public" / "data" / "movies.json"
LEXICON_PATH = ROOT / "data_lake" / "analysis" / "lexicon.json"
ES = "http://localhost:9200"
GALAXY_RADIUS = 6.0          # SVD 坐标缩放到此半径，匹配相机距离
K_NEIGHBORS = 5
MAX_LENS = 12                # CosmosStage 着色器上限
REVIEW_MIN_FOR_SENTIMENT = 5   # 至少多少条影评才输出真实情感（避免单条/极少数影评的代表性偏差）
REVIEW_MIN_FOR_ASPECTS = 5     # 至少多少条影评才输出六维（同情感门槛，确保可靠）
ASPECT_MIN_COVERED = 3         # 至少覆盖几个维度才输出（避免单轴雷达图名不副实）

# 方面情感关键词（中 + 英），命中影评时取该影评情感分汇总
ASPECT_KEYWORDS = {
    "剧情": ["剧情", "故事", "剧本", "叙事", "情节", "逻辑", "人物", "plot", "story",
            "script", "narrative", "character", "characters"],
    "演技": ["演技", "表演", "演员", "主角", "配角", "acting", "performance", "cast",
            "actor", "actress"],
    "特效": ["特效", "画面", "视觉", "镜头", "摄影", "场景", "effects", "visual",
            "cinematography", "cgi", "shot"],
    "节奏": ["节奏", "剪辑", "紧凑", "拖沓", "冗长", "pacing", "editing", "rhythm", "tight"],
    "结局": ["结局", "结尾", "收尾", "尾声", "ending", "finale"],
    "音乐": ["音乐", "配乐", "原声", "插曲", "music", "soundtrack", "score", "song"],
}


def _post(url, body):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def es_scroll(index, body, page_size=1000):
    """显式索引 + scroll 翻页，确保取全量（movies 488 部 / reviews 全部）。"""
    url = f"{ES}/{index}/_search?scroll=1m"
    body = {**body, "size": page_size}
    resp = _post(url, body)
    scroll_id = resp.get("_scroll_id")
    hits = resp["hits"]["hits"]
    while hits:
        for h in hits:
            yield h
        resp = _post(f"{ES}/_search/scroll", {"scroll": "1m", "scroll_id": scroll_id})
        hits = resp["hits"]["hits"]


def fetch_all_movies():
    out = []
    body = {"query": {"match_all": {}},
            "_source": ["title_zh", "title_en", "title", "original_title", "release_year",
                        "genres_zh", "genres_en", "vote_average", "vote_count", "director",
                        "cast", "poster_url", "overview", "keywords", "imdb_rating",
                        "tmdb_id", "movie_id"]}
    for h in es_scroll("movies", body):
        out.append((h["_id"], h["_source"]))
    return out


def fetch_reviews_with_movie():
    """返回 {movie_id: [(text, lang), ...]}（仅挂了 movie_id 的真实影评）。

    lang 取自影评自身的语言检测（CJK>0.2 → zh，否则 en），用于后续按真实语言
    路由情感引擎，避免用英文文本套中文分词器。
    """
    body = {"query": {"exists": {"field": "movie_id"}},
            "_source": ["movie_id", "text", "lang"]}
    groups = {}
    for h in es_scroll("reviews", body):
        s = h["_source"]
        mid = s.get("movie_id")
        txt = s.get("text")
        lang = s.get("lang") or "en"
        if mid and txt:
            groups.setdefault(mid, []).append((txt, lang))
    return groups


def _lang_label(lang_dist: dict) -> str | None:
    """把影评语言分布压缩成 en / zh / mix 标签。"""
    if not lang_dist:
        return None
    en = lang_dist.get("en", 0)
    zh = lang_dist.get("zh", 0)
    tot = en + zh
    if tot == 0:
        return "en"
    if zh == 0:
        return "en"
    if en == 0:
        return "zh"
    return "mix"


# ---------- 真实情感引擎（直接复用项目 analysis 模块） ----------
def load_lexicon():
    from analysis.lexicon import load_lexicon
    return load_lexicon(LEXICON_PATH)


def score_one(text, lex, score_text, lang):
    res = score_text(text, lex, lang=lang)
    return res.score  # tanh 压到 [-1,1]


def review_sentiment_and_aspects(texts_langs, lex, score_text, tokenize_zh):
    scores = [score_one(t, lex, score_text, l) for t, l in texts_langs]
    mean_s = float(np.mean(scores)) if scores else 0.0
    std_s = float(np.std(scores)) if len(scores) > 1 else 0.0
    # 方面：对每条影评分词，命中方面关键词则收集该影评情感分
    aspect_acc = {k: [] for k in ASPECT_KEYWORDS}
    for (t, _l), sc in zip(texts_langs, scores):
        toks = set(tokenize_zh(t))
        for asp, kws in ASPECT_KEYWORDS.items():
            if any(k in toks for k in kws):
                aspect_acc[asp].append(sc)
    aspects = {}
    for asp, vals in aspect_acc.items():
        if vals:
            # [-1,1] -> [0,10]
            aspects[asp] = round((float(np.mean(vals)) + 1) / 2 * 10, 2)
    from collections import Counter
    lang_dist = dict(Counter(l for _, l in texts_langs))
    return mean_s, std_s, aspects, lang_dist


def main():
    sys.path.insert(0, str(ROOT))
    from analysis.lexicon import tokenize_zh
    from analysis.sentiment import score_text

    print("[1/5] 加载真实情感词典 …")
    lex = load_lexicon()

    print("[2/5] 拉取真实电影 (movies 索引) …")
    movies = fetch_all_movies()
    print(f"      电影数 = {len(movies)}")

    print("[3/5] 拉取真实影评 (带 movie_id) …")
    reviews_by_movie = fetch_reviews_with_movie()
    print(f"      有影评的电影数 = {len(reviews_by_movie)}，影评总数 = "
          f"{sum(len(v) for v in reviews_by_movie.values())}")

    # 预计算每部有影评电影的真实情感 / 分歧 / 方面
    review_stats = {}
    for mid, texts_langs in reviews_by_movie.items():
        mean_s, std_s, aspects, lang_dist = review_sentiment_and_aspects(
            texts_langs, lex, score_text, tokenize_zh)
        review_stats[mid] = {"mean": mean_s, "std": std_s, "aspects": aspects,
                             "n_reviews": len(texts_langs), "lang_dist": lang_dist}

    # ---------- 真实 3D 坐标：TF-IDF + TruncatedSVD ----------
    print("[4/5] 真实文本语义降维 (TF-IDF + TruncatedSVD → 3D) …")
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.decomposition import TruncatedSVD
    import jieba

    def build_text(src):
        parts = []
        for key in ("title_zh", "title", "title_en"):
            v = src.get(key)
            if v:
                parts.append(str(v))
        parts.extend(src.get("genres_zh") or [])
        ov = src.get("overview") or ""
        if ov:
            parts.append(ov)
        kw = src.get("keywords")
        if isinstance(kw, list):
            parts.extend(kw)
        elif isinstance(kw, str) and kw:
            parts.append(kw)
        # 中文 jieba 分词 + 英文保留，空格连接
        raw = " ".join(parts)
        seg = " ".join(jieba.lcut(raw))
        return seg

    texts = [build_text(src) for _, src in movies]
    vec = TfidfVectorizer(max_features=20000, min_df=2, sublinear_tf=True)
    X = vec.fit_transform(texts)              # 稀疏矩阵 (488, n)
    svd = TruncatedSVD(n_components=3, random_state=42)
    coords = svd.fit_transform(X)             # (488, 3) 真实语义坐标
    coords = coords - coords.mean(axis=0)
    maxabs = np.max(np.abs(coords), axis=0)
    maxabs[maxabs == 0] = 1.0
    coords = coords / maxabs * GALAXY_RADIUS
    print(f"      SVD 解释方差比 = {svd.explained_variance_ratio_.round(3).tolist()}")

    # ---------- 争议焦点（引力透镜源）：真实情感标准差 TopN ----------
    controversy = [(mid, st["std"], st["n_reviews"]) for mid, st in review_stats.items()]
    controversy.sort(key=lambda x: x[1], reverse=True)
    lens_ids = {mid for mid, std, n in controversy[:MAX_LENS] if std > 0}
    print(f"      引力透镜源(影评争议 Top{MAX_LENS}) = {len(lens_ids)} 部")

    # ---------- 装配输出 ----------
    print("[5/5] 装配 movies.json …")
    out = []
    for i, (mid, src) in enumerate(movies):
        rating = float(src.get("vote_average") or 0.0)
        vcount = int(src.get("vote_count") or 0)
        year = int(src.get("release_year") or 0)
        # 情感：有足够真实影评(≥阈值) → 实测；否则评分代理
        n_rev = review_stats[mid]["n_reviews"] if mid in review_stats else 0
        if mid in review_stats and n_rev >= REVIEW_MIN_FOR_SENTIMENT:
            s_raw = review_stats[mid]["mean"]          # [-1,1]
            sentiment = round((s_raw + 1) / 2, 4)      # [0,1]
            source = "review"
            st = review_stats[mid]
            aspects = st["aspects"] if (
                st["n_reviews"] >= REVIEW_MIN_FOR_ASPECTS
                and len(st["aspects"]) >= ASPECT_MIN_COVERED) else None
            review_count = n_rev
            review_lang = _lang_label(st["lang_dist"])
        else:
            # 评分代理：vote_average 4~10 映射到 0~1（标注来源，不冒充实测）
            sentiment = round(min(1.0, max(0.0, (rating - 4.0) / 6.0)), 4)
            source = "rating"
            aspects = None
            review_count = n_rev
            review_lang = None
        # 类型主色 hue（给无海报时的渐变兜底）
        hue = _genre_hue((src.get("genres_zh") or ["其他"])[0])
        rec = {
            "id": mid,
            "title_zh": src.get("title_zh") or src.get("title") or src.get("title_en") or "",
            "title": src.get("title") or src.get("title_en") or src.get("title_zh") or "",
            "year": year,
            "genres_zh": src.get("genres_zh") or [],
            "rating": rating,
            "vote_count": vcount,
            "sentiment": sentiment,
            "sentiment_source": source,
            "review_count": review_count,
            "review_lang": review_lang,
            "divergence": mid in lens_ids,
            "director": src.get("director") or "",
            "cast": src.get("cast") or [],
            "poster_url": src.get("poster_url") or "",
            "summary": (src.get("overview") or "").strip(),
            "x": round(float(coords[i, 0]), 4),
            "y": round(float(coords[i, 1]), 4),
            "z": round(float(coords[i, 2]), 4),
            "aspects": aspects,
            "poster_hue": hue,
            # similarity_ids 在算完坐标后统一补
        }
        out.append(rec)

    # k 近邻相似度（真实 3D 距离）
    pos = np.array([[r["x"], r["y"], r["z"]] for r in out])
    for i, r in enumerate(out):
        d = np.linalg.norm(pos - pos[i], axis=1)
        order = np.argsort(d)
        neigh = [out[j]["id"] for j in order[1:K_NEIGHBORS + 1]
                 if out[j]["id"] != r["id"]]
        r["similarity_ids"] = neigh

    PUBLIC_DATA.parent.mkdir(parents=True, exist_ok=True)
    PUBLIC_DATA.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")

    # ---------- 统计 ----------
    n_review = sum(1 for r in out if r["sentiment_source"] == "review")
    n_lens = sum(1 for r in out if r["divergence"])
    n_aspects = sum(1 for r in out if r["aspects"])
    total_votes = sum(r["vote_count"] for r in out)
    # 真实情感分布（实测 vs 代理）
    rev_sent = [r["sentiment"] for r in out if r["sentiment_source"] == "review"]
    import statistics as _st
    print("\n=== 生成完成 ===")
    print(f"  总电影数      : {len(out)}")
    print(f"  真实影评情感  : {n_review} 部 (≥{REVIEW_MIN_FOR_SENTIMENT}条影评才实测；其余 {len(out)-n_review} 部用评分代理)")
    if rev_sent:
        print(f"    实测情感分布: min={min(rev_sent):.2f} max={max(rev_sent):.2f} "
              f"均值={_st.mean(rev_sent):.2f} (有区分度)")
    print(f"  引力透镜源    : {n_lens} 部 (真实影评争议 Top{MAX_LENS})")
    print(f"  六维方面雷达  : {n_aspects} 部 (≥{REVIEW_MIN_FOR_ASPECTS}条影评且≥{ASPECT_MIN_COVERED}维度才输出)")
    print(f"  输出文件      : {PUBLIC_DATA}  ({PUBLIC_DATA.stat().st_size/1024:.1f} KB)")
    print(f"  样例(有影评)  : ", end="")
    shown = 0
    for r in out:
        if r["sentiment_source"] == "review" and shown < 3:
            print(f"\n    {r['title_zh']} 情感={r['sentiment']} 分歧={r['divergence']} 方面={list((r['aspects'] or {}).keys())}")
            shown += 1


def _genre_hue(genre: str) -> int:
    table = {
        "动作": 8, "科幻": 210, "喜剧": 45, "爱情": 330, "悬疑": 265, "惊悚": 275,
        "恐怖": 290, "动画": 160, "剧情": 35, "战争": 18, "犯罪": 0, "家庭": 120,
        "传记": 30, "历史": 25, "音乐": 280, "歌舞": 300, "西部": 25, "纪录": 200,
        "灾难": 15, "武侠": 40, "儿童": 110, "奇幻": 280, "冒险": 150, "其他": 30,
    }
    return table.get(genre, 30)


if __name__ == "__main__":
    main()
