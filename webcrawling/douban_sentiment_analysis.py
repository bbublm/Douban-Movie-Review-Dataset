
import pandas as pd
from snownlp import SnowNLP
import numpy as np

def sentiment_analysis(output_filename,movie_name):

    try:
        # with open(output_filename, "r") as f:
        #     contents = f.read()


        # �ڴ˴�ִ����������
        sorted_filename = './sorted/' + movie_name + 'sorted.csv'

        # ��ȡ CSV �ļ���ָ������
        df_1 = pd.read_csv(output_filename, header=None,
                         names=['time', 'uname', 'comment', 'star', 'title', 'support'])

        # ȱʧ��Ĳ���
        df_1['time'].fillna('2000-01-01', inplace=True)
        df_1['comment'].fillna(" ", inplace=True)
        df_1['star'] = df_1['star'].astype(str)
        df_1['star'] = df_1['star'].str.replace("allstar", "")
        df_1['star'] = df_1['star'].str.replace("0", "")
        df_1['star'] = df_1['star'].apply(lambda x: 3 if len(x) > 1 or eval(x) > 5 else x)

        # df_1['star']=df_1['star'].str.replace("33","3")
        df_1['star'].fillna(3, inplace=True)
        # 读抓取的csv文件，标题在第三列，序号�?2
        df = pd.read_csv(output_filename, header=None, usecols=[2])

        # 将dataframe转换为List
        contents = df.values.tolist()
        # 数据长度

        # 定义空列表存储情感分�?
        score = []
        for content in contents:
            try:
                s = SnowNLP(content[0])
                # print(s.summary())
                score.append(s.sentiments)
            except:
                # TODO �?查错误要把这里加�?个输�?
                # print("")
                # 自动填补�?
                score.append(0.5)
        data2 = pd.DataFrame(score)
        # data2.to_csv('sentiment.csv',header=False,index=False,mode='a+')

        df_1['sentiment_score'] = data2

        df_1.to_csv(output_filename, index=False)

        df_2 = pd.read_csv(output_filename)

        # ��ʱ����ת��Ϊ����ʱ������
        # �ڽ�ʱ����ת��Ϊ����ʱ������ǰ������ϴ���ݲ������쳣ֵ
        df_2['time'] = df_2['time'].apply(lambda x: x.strip() if isinstance(x, str) else x)

        # ��ʱ������ת��Ϊ����ʱ�����ͣ�ʹ�� errors='coerce' ���޷�������ֵ�滻Ϊ NaT
        df_2['time'] = pd.to_datetime(df_2['time'], format='%Y-%m-%d %H:%M:%S', errors='coerce')

        # df_2['time'] = df_2['time'].apply(lambda x: x.strip() if isinstance(x, str) else x)
        # df_2['time'] = pd.to_datetime(df_2['time'], format = '%Y-%m-%d %H:%M:%S')
        # , format = '%Y-%m-%d %H:%M:%S'

        # ����ʱ��˳������
        df_sorted = df_2.sort_values(by=['time'])

        # �������� DataFrame ����� CSV �ļ�
        df_sorted.to_csv(sorted_filename, header=False, index=False)


    except FileNotFoundError:
        print(f"Error: file '{output_filename}' not found.")
        # exit program
        # exit()