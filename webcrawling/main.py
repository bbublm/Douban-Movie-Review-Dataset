import pandas as pd
from douban_wordcloud import *
from douban_sentiment_analysis import *
from douban_score_analysis import *
from douban_movie_comment import *
def play(output_filename,header,Cookie,url_1,url_2,sleep_time,wordcloud_name,stop_word,star,result_file_name,movie_name):
    crawl(output_filename,header,Cookie,url_1,url_2,sleep_time)
    time.sleep(2)
    sentiment_analysis(output_filename,movie_name)
    # time.sleep(2)
    score_analysis(output_filename,result_file_name, movie_name)
    # time.sleep(2)
    # WORDCLOAD(output_filename,wordcloud_name,stop_word,star)

# if __name__=='__main__':
def run(output_filename0, url_10):
    # output_filename0.replace('\xa0', ' ')
    #输出文件名
    output_filename = "douban_movie_xsk_1-5" + output_filename0 + ".csv"


    # url请求文件头,User-Agent要改为自己登录后的
    # header = {'Content-Type': 'text/html; charset=utf-8',
    #           'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/87.0.4280.88 Safari/537.36'}

    header = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/69.0.3497.100 Safari/537.36'
    }
    # 登录cookies,自己填写登录豆瓣后的cookie
    Cookie={
    }
    # 构造请求网址
    # url_1 = "https://movie.douban.com/subject/1292063/" + "comments?start="
    url_1 = url_10 + "comments?start="
    url_2 = "&limit=20&sort=new_score&status=P"
    #睡眠时间
    sleep_time =2
    #词云文件名
    wordcloud_name = 'ciyun.png'
    #停用词存放地址
    stop_word='hit_stopwords.txt'
    #生成词云要使用的评分,一共是1-5
    star=[5]

    result_file_name = 'reselt.txt'
    movie_name = output_filename0
    #词云,对应8个参数为输出文件名，Cookie,url第一部分，url第二部分,睡眠时间，输出词云文件名，要看是哪些评星的词云
    play(output_filename,header,Cookie,url_1,url_2,sleep_time,wordcloud_name,stop_word,star,result_file_name, movie_name)
