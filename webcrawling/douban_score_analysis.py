import pandas as pd
from collections import Counter

#读取csv文件
def score_analysis(output_file_name, result_file_name, movie_name):
    try:
        df = pd.read_csv(output_file_name)

        result_filename = './result/' + movie_name + '.csv'


        # 假设你有一个包含NBSP的字符串

        # 使用字符串处理函数将NBSP替换为空格
        # text_without_nbsp = movie_name.replace("&nbsp;", " ")
        #
        # # 打开txt文件并写入处理后的文本
        # with open("output.txt", "w", encoding="utf-8") as file:
        #     file.write(text_without_nbsp)


        #统计打分数量
        star_list = list(df['star'].values)
        num_count = Counter(star_list)

        #显示热评种不同分值的评论数量
        with open(result_file_name, 'a', encoding='utf-8') as file:
            file.write("\n" + movie_name)
            file.write("\n" + "=================================分数统计==========================================")
            file.write("\n")
            file.write(str(num_count))
        # print("=================================分数统计==========================================")
        # print(num_count)

        #分组求平均
        grouped = df.groupby('star').describe().reset_index()
        star = grouped['star'].values.tolist()
        with open(result_file_name, 'a', encoding='utf-8') as file:
            star_str = ','.join(map(str, star))
            file.write("\n" + star_str)
        # print(star)

        #根据用户打分的分组，对每组的情感值求平均
        sentiment_average = df.groupby('star')['sentiment_score'].mean()
        sentiment_scores = sentiment_average.values


        with open(result_file_name, 'a', encoding='utf-8') as file:
            sentiment_scores_str = str(sentiment_scores)
            file.write("\n" + sentiment_scores_str)
            file.write("\n" + "===================================================================================")
            file.write("\n" + "\n" )
        # print(sentiment_scores)
        # print("===================================================================================")

        data1 = [(num_count,
                  sentiment_scores)]
        data2 = pd.DataFrame(data1)
        data2.to_csv(result_filename, header=False, index=False, mode='a+')
        df_1 = pd.read_csv(result_filename, header=None,
                           names=['count', 'score'])

    except FileNotFoundError:
        print(f"Error: file '{output_file_name}' not found.")
        # exit program
        # exit()