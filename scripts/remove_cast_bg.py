#!/usr/bin/env python3
"""把 cast-group.jpg 的棋盘格透明背景替换为页面底色，保留角色主体。"""
from PIL import Image, ImageFilter
import numpy as np
import cv2

SRC = r'C:\Users\16280\Desktop\movie-recommendation-system-main\frontend\public\images\cast-group.jpg'
DST = SRC
PAGE_BG = (246, 242, 234)  # var(--page-bg) #f6f2ea

im = Image.open(SRC).convert('RGB')
w, h = im.size

# 1. 用高斯模糊+亮度阈值得到候选背景（棋盘格经模糊后亮度约 242）
gray = np.array(im.convert('L').filter(ImageFilter.GaussianBlur(radius=4)))
candidate = (gray > 235).astype(np.uint8) * 255

# 2. 连通域分析：与图像边缘相连的组件即为真实背景
num_labels, labels, stats, _ = cv2.connectedComponentsWithStats(candidate, connectivity=4)
bg_mask = np.zeros_like(candidate, dtype=bool)
for i in range(1, num_labels):
    x, y, cw, ch, area = stats[i]
    # 只要组件接触到任意边缘，就视为背景
    if x == 0 or y == 0 or x + cw >= w or y + ch >= h:
        bg_mask[labels == i] = True

# 3. 对背景蒙版做形态学闭运算，填补角色之间较小的封闭空洞
kernel = np.ones((25, 25), np.uint8)
bg_mask = cv2.morphologyEx(bg_mask.astype(np.uint8) * 255, cv2.MORPH_CLOSE, kernel).astype(bool)

# 4. 替换背景像素为页面底色
out_arr = np.array(im)
out_arr[bg_mask] = PAGE_BG

# 5. 二道清理：把仍孤立的“类棋盘格”亮斑（周围多数已是背景）也替换掉
# 这些通常是角色之间没被闭运算吞掉的微小封闭空洞
bg_frac = cv2.blur(bg_mask.astype(np.float32), (11, 11))
light_spot = (
    (out_arr[:, :, 0] >= 220) &
    (out_arr[:, :, 1] >= 220) &
    (out_arr[:, :, 2] >= 220) &
    ~bg_mask
)
out_arr[light_spot & (bg_frac > 0.6)] = PAGE_BG

Image.fromarray(out_arr).save(DST, quality=95, optimize=True)
print(f'[ok] 背景已替换为 {PAGE_BG}，保存到 {DST}')
