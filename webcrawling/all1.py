# 导包
import requests
from lxml import etree  # 用lxml解析器生成的对象中的xpath方法
from time import sleep
import csv
import numpy as np
from main import *

# 指定URL
# url = 'https://movie.douban.com/top250'
# 进行UA伪装
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/117.0.0.0 Safari/537.36 Edg/117.0.2045.41'}

# 定义空列表存放电影数据
tiltes_cn = []  # 中文标题
titles_en = []  # 英文标题
links = []  # 详情页链接
director = []  # 导演
actors = []  # 演员
years = []  # 上映年份
nations = []  # 国籍
types = []  # 类型
scores = []  # 评分
rating_nums = []  # 评分人数

fp = open('./douban_top250.csv', 'w', encoding='utf-8')
writer = csv.writer(fp)
writer.writerow(
    ['电影中文名', '电影英文名', '电影详情页链接', '导演', '演员', '上映年份', '国籍', '类型', '评分', '评分人数'])

for i in range(0, 226, 25):
    url = f'https://movie.douban.com/top250?start={i}&filter='
    # 将URL中的参数封装到字典中
    # data = {
    #     'start':i,            # 设置start参数
    #     'filter':'',
    # }
    # 发起请求，获取网页响应
    response = requests.get(url, headers=headers
                            # ,data=data
                            )
    sleep(1)
    # print(response.status_code)
    # print(response.encoding)
    # print(response.text)

    # 获取响应内容
    html = response.text
    # 实例化一个etree对象
    data = etree.HTML(html)

    # 所有电影信息都在li标签下，所以我们可以先定位到li标签，在通过循环获取每一个li标签中的信息
    li_list = data.xpath('//*[@id="content"]/div/div[1]/ol/li')
    # 通过循环遍历每一页中的所有li标签，获取该页面所有电影的数据
    for each in li_list:
        # 中文标题
        title1 = each.xpath('./div/div[2]/div[1]/a/span[1]/text()')[0]
        tiltes_cn.append(title1)

        # 英文标题
        # 每次获取到的数据存在一个列表中，通过下标索引取列表的值
        # 通过字符串的strip()方法去除字符串首尾的指定字符串
        title2 = each.xpath('./div/div[2]/div[1]/a/span[2]/text()')[0].strip('\xa0/\xa0')
        titles_en.append(title2)

        # 链接
        link = each.xpath('./div/div[2]/div[1]/a/@href')[0]
        links.append(link)

        # 导演、主演
        info1 = each.xpath('./div/div[2]/div[2]/p[1]/text()[1]')[0].strip()  # 通过strip方法去除字符串的前后空格
        split_info1 = info1.split('\xa0\xa0\xa0')  # 通过指定字符串分割字符串
        dirt = split_info1[0].strip('导演: ')
        director.append(dirt)
        # 有些电影的主演为空，所以需要进行条件判断
        # 如果导演和主演信息都有，则获取主演信息
        if len(split_info1) == 2:
            ac = split_info1[1].strip('主演: ')
            actors.append(ac)
        # 如果没有主演信息，则将其信息设置为空
        else:
            actors.append(np.nan)

        # 年份、国籍、类型
        info2 = each.xpath('./div/div[2]/div[2]/p[1]/text()[2]')[0].strip()  # 去除字符串首尾的空格
        split_info2 = info2.split('\xa0/\xa0')  # 通过字符串分割获取字符串中的年份、国籍和类型
        # print(split_info)
        year = split_info2[0]
        nation = split_info2[1]
        ftype = split_info2[2]
        years.append(year)
        nations.append(nation)
        types.append(ftype)

        # 电影评分
        score = each.xpath('./div/div[2]/div[2]/div/span[2]/text()')[0]
        scores.append(score)

        # 获取电影打分人数
        num = each.xpath('./div/div[2]/div[2]/div/span[4]/text()')[0].strip('人评价')
        rating_nums.append(num)

        writer.writerow([title1, title2, link, dirt, ac, year, nation, ftype, score, num])

        run(title1, link)

    print(f'————————————第{int((i / 25) + 1)}页爬取完毕！——————————————')

fp.close()  # 写入完成后，关闭文件
print('——————————————————————————————————爬虫结束！！！！！————————————————————————————————————————————————')


