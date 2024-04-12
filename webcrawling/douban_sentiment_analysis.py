
import pandas as pd
from snownlp import SnowNLP
import numpy as np

def sentiment_analysis(output_filename,movie_name):

    try:
        # with open(output_filename, "r") as f:
        #     contents = f.read()


        # 在此处执行其它操作
        sorted_filename = './sorted/' + movie_name + 'sorted.csv'

        # 读取 CSV 文件并指定列名
        df_1 = pd.read_csv(output_filename, header=None,
                         names=['time', 'uname', 'comment', 'star', 'title', 'support'])

        # 缺失项的补充
        df_1['time'].fillna('2000-01-01', inplace=True)
        df_1['comment'].fillna(" ", inplace=True)
        df_1['star'] = df_1['star'].astype(str)
        df_1['star'] = df_1['star'].str.replace("allstar", "")
        df_1['star'] = df_1['star'].str.replace("0", "")
        df_1['star'] = df_1['star'].apply(lambda x: 3 if len(x) > 1 or eval(x) > 5 else x)

        # df_1['star']=df_1['star'].str.replace("33","3")
        df_1['star'].fillna(3, inplace=True)
        # 璇绘姄鍙栫殑csv鏂囦欢锛屾爣棰樺湪绗笁鍒楋紝搴忓彿涓?2
        df = pd.read_csv(output_filename, header=None, usecols=[2])

        # 灏哾ataframe杞崲涓篖ist
        contents = df.values.tolist()
        # 鏁版嵁闀垮害

        # 瀹氫箟绌哄垪琛ㄥ瓨鍌ㄦ儏鎰熷垎鍊?
        score = []
        for content in contents:
            try:
                s = SnowNLP(content[0])
                # print(s.summary())
                score.append(s.sentiments)
            except:
                # TODO 妫?鏌ラ敊璇鎶婅繖閲屽姞涓?涓緭鍑?
                # print("")
                # 鑷姩濉ˉ涓?
                score.append(0.5)
        data2 = pd.DataFrame(score)
        # data2.to_csv('sentiment.csv',header=False,index=False,mode='a+')

        df_1['sentiment_score'] = data2

        df_1.to_csv(output_filename, index=False)

        df_2 = pd.read_csv(output_filename)

        # 将时间列转换为日期时间类型
        # 在将时间列转换为日期时间类型前，先清洗数据并处理异常值
        df_2['time'] = df_2['time'].apply(lambda x: x.strip() if isinstance(x, str) else x)

        # 将时间数据转换为日期时间类型，使用 errors='coerce' 将无法解析的值替换为 NaT
        df_2['time'] = pd.to_datetime(df_2['time'], format='%Y-%m-%d %H:%M:%S', errors='coerce')

        # df_2['time'] = df_2['time'].apply(lambda x: x.strip() if isinstance(x, str) else x)
        # df_2['time'] = pd.to_datetime(df_2['time'], format = '%Y-%m-%d %H:%M:%S')
        # , format = '%Y-%m-%d %H:%M:%S'

        # 按照时间顺序排序
        df_sorted = df_2.sort_values(by=['time'])

        # 将排序后的 DataFrame 保存回 CSV 文件
        df_sorted.to_csv(sorted_filename, header=False, index=False)


    except FileNotFoundError:
        print(f"Error: file '{output_filename}' not found.")
        # exit program
        # exit()