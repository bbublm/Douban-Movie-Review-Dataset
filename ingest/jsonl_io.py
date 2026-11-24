"""
JSONL 读写小工具 —— 数据湖 interim 层的通用格式。

为什么单独抽一个文件？
    interim 层所有采集模块的产物都是「一行一条记录」的 JSONL：
        seed_movies.jsonl / tmdb_movies.jsonl / imdb_movies.jsonl /
        wiki_movies.jsonl / reviews.jsonl
    读写逻辑就两件事，但有个硬约束必须所有模块一致 —— **流式**：
    来一条写一条、读一行解析一行，永不把整个文件读进内存。
    12 万条记录攒成 list 再写，光 Python dict 开销就 200 MB 起。

    说明：imdb_datasets.py / tmdb.py / wiki.py 里各自有一份同构实现（历史原因）。
    新模块统一用这里，旧模块保持不动以免动摇已验收的链路，
    后续做重构时再把它们收敛过来。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable, Iterator


def iter_jsonl(path: Path) -> Iterator[dict]:
    """逐行读 JSONL，跳过空行与坏行（不因为一行 JSON 残缺就整个任务崩掉）。

    坏行静默跳过是有意为之：采集动辄跑到一半被 Ctrl+C，
    文件末尾留半行是常态，读的时候不该因此报错。
    """
    if not path.exists():
        return
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def write_jsonl(records: Iterable[dict], path: Path) -> int:
    """把一个可迭代对象写成 JSONL，返回行数。

    records 可以是 list，也可以是生成器 —— 后者才是省内存的用法。
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with path.open("w", encoding="utf-8") as fh:
        for rec in records:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n += 1
    return n


def count_lines(path: Path) -> int:
    """数行数（流式，不读进内存）。"""
    if not path.exists():
        return 0
    n = 0
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                n += 1
    return n
