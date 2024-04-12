import requests
import pandas as pd
import threading
from main import *
lock = threading.Lock()

if __name__ == '__main__':
    file_name = 'douban_movie 科幻.csv'
    df = pd.read_csv(file_name)

    name_and_time_list = list(zip(df['电影名'], df['地址']))

    # 遍历元组内的每一个元素并对name和time分开进行操作
    for name, address in name_and_time_list:
        title = name
        # 在这里对name进行操作
        url = address


        with lock:
            run(title, url)