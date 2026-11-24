"""
阶段 4 · 分析层：情感分析 + 主题/关键词抽取。

这一层在数据湖里的位置：

    data_lake/processed/movies.jsonl   ┐
    data_lake/processed/reviews.jsonl  ├─> analysis/ ─> data_lake/analysis/
                                        │   · lexicon.json          归纳出的情感词典
                                        │   · topics.json           全局/分情感关键词统计
                                        │   · movie_keywords.json   单片关键词画像
                                        │   · report.json           准确率等评估结果
                                        └

★ 为什么单独一层，不塞进 transform？
    transform 做的是「把不同数据源拼成一张表」，产出要供索引层直接入库；
    分析层的产出**不进 ES 索引的主体结构**（影评已有 Kaggle 标签字段），
    而是给洞察接口（/insights）和前端大屏用的派生数据。
    两件事的重跑代价差得远：改融合规则要重跑 transform + 重建索引，
    改情感规则只需要重跑 analysis。所以分开，改哪层跑哪层。

★ 为什么情感不用现成库（SnowNLP）一把梭？
    两个原因：
    1. 不可解释 —— 答辩时被问「为什么这句话是负面」答不上来；
    2. SnowNLP 的训练语料是电商评论，对影评（"the plot was predictable"）
       口径不一定对。
    我们的做法是**用 Kaggle 那 5 万条自带情感标签的影评，自己归纳一部词典**
    （词 -> log-odds 得分），打分规则就三行、每个命中词都能报出来。
    同时把 SnowNLP 当基线一起评估，用数字说话谁更适配影评这个领域。
"""
from __future__ import annotations
