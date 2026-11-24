"""
阶段 2b：ES 索引层 —— 把 processed/ 里的成品导入 Elasticsearch。

这一层只做三件事：
    1. 设计索引结构（本文件）
    2. 建索引、批量导入、别名切换（builder.py）
    3. 命令行封装（run_index.py）

为什么 mapping 要单独一个文件，而不是塞进 builder？
    因为 mapping 是**纯数据**：它不连 ES、不读文件、不产生副作用。
    这样离线自检可以把它当成普通 dict 校验（比如"processed 里出现的每个字段
    是否都在 mapping 里"），不需要真的起一个 ES 容器。
    放到 builder 里就只能在联网环境下测了。
"""
