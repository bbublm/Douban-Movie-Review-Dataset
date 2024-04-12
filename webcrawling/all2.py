# import requests
# import requests
#
#
# if __name__ == "__main__":
#     # 处理ucl携带的参数:封装到字典中
#     # UA伪装为一个用户浏览器进行访问数据
#     headers = {'Content-Type': 'text/html; charset=utf-8',
#               'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.88 Safari/537.36'}
#     url = 'https://movie.douban.com/j/chart/top_list'
#     param = {
#         "type": "24",
#         "interval_id": "100:90",
#         "action": "",
#         "start": "0",  # 从第几部电影开始
#         "limit": "100"  # 到第几部电影结束
#     }
#
#     try:
#
#         # 对指定的url发起的请求对应的url是携带参数的..并且请求过程虫处理了参数
#         response = requests.get(url=url, params=param, headers=headers)
#         response.raise_for_status()  # 检查是否成功获取响应
#
#         try:
#             diany_json = response.json()
#             print(diany_json)
#         except ValueError:
#             print("返回内容不是 JSON 格式:", response.text)
#
#         # 转换json文件为csv文件存储
#         keys = list(diany_json[0].keys())
#         # 这里输出类型转换前的类型和样子 供参考
#         # 为了方便保存的时候方便进行索引，于是先获取json内map的key值
#         list_json_data = []
#         for i in range(100):
#             list_json_data.append([diany_json[i][x] for x in keys])
#         # 上面一行的代码等于 ：
#         # 1、
#         # list_json_data.append([json_list[i][keys[0]], json_list[i][keys[1]], json_list[i][keys[2]]])
#         # 2、
#         # tmpList = []
#         # for x in keys:
#         #     tmpList.append(json_list[i][x])
#         # list_json_data.append(tmpList)
#     except requests.exceptions.RequestException as e:
#         print("请求出错:", e)
#
# with open('data.csv', 'w', encoding='utf-8-sig', newline='') as f:
#     # 初始化 csv writer 对象
#     import csv
#
#     f = csv.writer(f)
#     # 遍历json数据列表并保存每个列表
#     for list_data in list_json_data:
#         f.writerow(list_data)

#  在下拉的过程中 页面ajax动态刷新页面 利用抓包工具查看返回内容类型 get请求 返回特定的参数即可
# import requests
# import json
# import pandas as pd
#
# if __name__ =="__main__":
#     # 爬取豆瓣喜剧电影排行榜前200步电影的相关信息
#     df = pd.DataFrame(columns=['电影名','评分','地区','地址','发布日期','评论人数'])
#     url = 'https://movie.douban.com/j/chart/top_list'  # 豆瓣电影地址
#     headers =  {
#         "User-Agent" :"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.90 Safari/537.36"
#     }  # 利用 headers进行伪装
#
#     for num in range(0,181,20):   # 页面是ajax动态刷新的 每下拉到二十部 就刷新一次页面  所以181的下标 包含了前200部
#         param = {
#             'type': '24',
#             'interval_id': '100:90',
#             'action': '',
#             'start': num,
#             'limit': '20'
#         }
#         response = requests.get(url=url,params=param,headers=headers)   # 页面为get请求 可以在网站的headers中看到
#         content=response.json()  # Content-Type 为 json格式的数据
#         length=len(content)
#         for i in range(0,length):
#             s = pd.Series({'电影名':content[i].get('title'),
#                             '评分':eval(content[i].get('score')),
#                            '地区':content[i].get('regions')[0] ,
#                            '地址':content[i].get('url'),
#                            '发布日期':content[i].get('release_date'),
#                            '评论人数':content[i].get('vote_count')
#                           })
#             # 在执行拼接操作之前排除空值或全为NA的列
#             df = df.dropna(axis=1, how='all')  # 删除全为NA的列
#             df = df.dropna()  # 删除包含NA值的行
#
#             # 然后执行拼接操作
#             df = df._append(s, ignore_index=True)
#             # df = df._append(s, ignore_index=True)
#             # 这里必须选择ignore_index=True 或者给 Series 一个index值
#     df.to_csv('./douban_movie xijv.csv',encoding='utf-8',index=False,index_label=None)

import requests
import json
import pandas as pd

if __name__ == "__main__":
    # 爬取豆瓣喜剧电影排行榜前200步电影的相关信息
    df = pd.DataFrame(columns=['电影名', '评分', '地区', '地址', '发布日期', '评论人数'])
    url = 'https://movie.douban.com/j/chart/top_list'  # 豆瓣电影地址
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.90 Safari/537.36"
    }  # 利用 headers进行伪装

    for num in range(0, 181, 20):  # 页面是ajax动态刷新的，每下拉到二十部就刷新一次页面，所以181的下标包含了前200部
        param = {
            'type': '11',
            'interval_id': '100:90',
            'action': '',
            'start': num,
            'limit': '20'
        }
        try:
            response = requests.get(url=url, params=param, headers=headers)  # 页面为get请求 可以在网站的headers中看到
            content = response.json()  # Content-Type 为 json格式的数据
            for i in range(len(content)):
                s = pd.Series({'电影名': content[i].get('title'),
                               '评分': content[i].get('score'),
                               '地区': content[i].get('regions')[0],
                               '地址': content[i].get('url'),
                               '发布日期': content[i].get('release_date'),
                               '评论人数': content[i].get('vote_count')
                               })
                df = df._append(s, ignore_index=True)
        except requests.exceptions.RequestException as e:
            print(f"请求异常：{e}")

    # 删除全为NA的列
    df = df.dropna(axis=1, how='all')
    # 删除包含NA值的行
    df = df.dropna()

    # 保存数据到CSV文件
    df.to_csv('./douban_movie_a.csv', encoding='utf-8', index=False)