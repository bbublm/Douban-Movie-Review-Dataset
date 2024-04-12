# 代码首先导入了需要使用的模块：requests、lxml和csv。
import requests
from lxml import etree
import csv
from main import *
from fake_useragent import UserAgent  # 如果没有安装fake_useragent模块，请先安装：pip install fake_useragent
import threading

lock = threading.Lock()
#
doubanUrl = 'https://movie.douban.com/top250?start={}&filter='
# 使用fake_useragent生成随机的User-Agent
ua = UserAgent()


# 然后定义了豆瓣电影TOP250页面的URL地址，并实现了一个函数getSource(url)来获取网页的源码。该函数发送HTTP请求，添加了请求头信息以防止被网站识别为爬虫，并通过requests.get()方法获取网页源码。
def getSource(url):
    # 反爬 填写headers请求头
    # headers = {
    #     'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.88 Safari/537.36'
    # }
    headers = {'Content-Type': 'text/html; charset=utf-8',
              'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.88 Safari/537.36'}
    # headers = {
    #     'User-Agent': ua.random,  # 使用随机生成的User-Agent
    #     'Referer': 'https://movie.douban.com/top250'  # 添加Referer字段
    # }

    response = requests.get(url, headers=headers)
    # 防止出现乱码
    response.encoding = 'utf-8'
    # print(response.text)
    return response.text


# 定义了一个函数getEveryItem(source)来解析每个电影的信息。首先，使用lxml库的etree模块将源码转换为HTML元素对象。然后，使用XPath表达式定位到包含电影信息的每个HTML元素。通过对每个元素进行XPath查询，提取出电影的标题、副标题、URL、评分和引言等信息。最后，将这些信息存储在一个字典中，并将所有电影的字典存储在一个列表中。
def getEveryItem(source):
    html_element = etree.HTML(source)

    movieItemList = html_element.xpath('//div[@class="info"]')

    # 定义一个空的列表
    movieList = []

    for eachMoive in movieItemList:
        # 创建一个字典 像列表中存储数据[{电影一},{电影二}......]
        movieDict = {}

        title = eachMoive.xpath('div[@class="hd"]/a/span[@class="title"]/text()')  # 标题
        otherTitle = eachMoive.xpath('div[@class="hd"]/a/span[@class="other"]/text()')  # 副标题
        link = eachMoive.xpath('div[@class="hd"]/a/@href')[0]  # url
        star = eachMoive.xpath('div[@class="bd"]/div[@class="star"]/span[@class="rating_num"]/text()')[0]  # 评分
        quote = eachMoive.xpath('div[@class="bd"]/p[@class="quote"]/span/text()')  # 引言（名句）

        if quote:
            quote = quote[0]
        else:
            quote = ''
        # 保存数据
        movieDict['title'] = ''.join(title + otherTitle)
        movieDict['url'] = link
        movieDict['star'] = star
        movieDict['quote'] = quote

        movieList.append(movieDict)

        # print(movieList)
    return movieList


# 保存数据
def writeData(movieList):
    with open('douban.csv', 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['title', 'star', 'quote', 'url'])

        writer.writeheader()  # 写入表头

        for each in movieList:
            writer.writerow(each)


if __name__ == '__main__':
    movieList = []

    # 一共有10页

    for i in range(1,3):
        pageLink = doubanUrl.format(i * 25)

        source = getSource(pageLink)

        movieList += getEveryItem(source)

        # time.sleep(2)

    writeData(movieList)

    count = 0
    for item in movieList:
        title = str(item['title'].split("/")[0])
        url = str(item['url'])
        with lock:
            run(title[:-1], url)
            # print(title)
            # print(url)
            count += 1

    print(count)

    # run("活着", "https://movie.douban.com/subject/1292365/")

