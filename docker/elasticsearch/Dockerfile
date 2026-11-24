## 电影盒子 · Elasticsearch 镜像（基础镜像 + IK 中文分词插件）
##
## 为什么需要这个 Dockerfile？
##     官方镜像不带任何中文分词插件，默认 standard 分析器对中文是「一字一 token」，
##     搜「科幻电影」会把所有含「电」含「影」的片子全捞回来。
##     IK 是中文检索的事实标准插件（ik_max_word 细切 / ik_smart 粗切）。
##
## 为什么不用 `docker exec ... elasticsearch-plugin install` 手工装？
##     那样插件只存在于**当前容器**里。一旦 `docker-compose down` 后重建容器，
##     或者换台机器部署，插件就没了 —— 而索引创建会直接失败
##     （failed to find global tokenizer under [ik_max_word]）。
##     写进 Dockerfile，插件就跟着镜像走，`docker-compose up -d` 一次到位。
##
## index/mappings.py 里还有一层降级：探测不到 IK 会自动退回内置 cjk 分析器，
## 所以即使这里构建失败，索引照样能建、能搜，只是中文分词质量下降。
##
## 构建：  docker-compose build elasticsearch
##         docker-compose up -d

ARG ES_VERSION=8.15.3
FROM docker.elastic.co/elasticsearch/elasticsearch:${ES_VERSION}

# IK 插件版本号必须与 ES 主版本完全一致，否则 ES 启动时会拒绝加载
ARG IK_VERSION=8.15.3

# --batch：跳过「插件需要额外权限」的交互确认
RUN bin/elasticsearch-plugin install --batch \
    https://get.infini.cloud/elasticsearch/analysis-ik/${IK_VERSION}
