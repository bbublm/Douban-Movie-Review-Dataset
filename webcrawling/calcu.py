import numpy as np
import matplotlib.pyplot as plt
from scipy.optimize import curve_fit
import pandas as pd
from datetime import datetime
import os

def linear_func(x, a, b):
    return a * x + b

def cal(file_path, out_name):
    # 读取CSV文件中的数据
    data = pd.read_csv(file_path)

    # 分离自变量和因变量
    date_string = data.iloc[:, 0]  # 使用 iloc 方法，获取所有行的第0列数据  # 时间
    y = data.iloc[:, 3]  # 因变量（0到1间的取值）

    # 修改日期时间字符串的格

    date_object = date_string.apply(lambda x: datetime.strptime(x, "%Y-%m-%d %H:%M:%S"))

    x = date_object.values.astype(float) / 10 ** 9  # 转换为秒级时间戳

    # 使用最小二乘法拟合直线
    popt, pcov = curve_fit(linear_func, x, y)

    # 拟合出的直线参数
    # a_fit为斜率
    a_fit, b_fit = popt

    # 绘制散点图和拟合的直线
    plt.clf()
    plt.scatter(date_object, y, label='Data')
    plt.plot(date_object, linear_func(x, a_fit, b_fit), color='red', label='Fit: y = {:.2f}x + {:.2f}'.format(a_fit, b_fit))
    plt.xlabel('Time')
    plt.ylabel('Value')
    plt.legend()
    plt.title(out_name)
    plt.grid(True)
    plt.rcParams['font.sans-serif'] = ['SimHei']
    plt.savefig(out_name+'.png')
    # plt.show()
    return a_fit

def main():
    # 读取CSV文件中的数据
    upward=0
    downward=0
    data_path = './sorted'
    file_names = [f for f in os.listdir( data_path ) if
                  os.path.isfile(os.path.join(data_path, f)) and f.endswith('.csv')]
    for file_name in file_names:
        csv_file_path = data_path + "/" + file_name
        output_png_name = './image/' + file_name

        fit = cal(csv_file_path, output_png_name)
        if fit >0:
            upward+=1
        else:
            downward+=1

    print(upward, downward)


if __name__ == "__main__":
    main()