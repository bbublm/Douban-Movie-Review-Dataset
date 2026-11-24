"""
进程内存读数 —— 用来把「这个采集脚本到底吃了多少内存」量化出来。

为什么需要这个文件：
    采集 IMDb 全量数据集时最容易踩的坑，就是用 pandas 一次性读完
    title.basics.tsv.gz（解压后约 900 MB、1200 万行），
    峰值内存直接冲到 4~5 GB，机器被拖死。
    本项目全流程是**流式解析**（内存恒定，与总行数无关），
    但「我们说它省内存」需要证据 —— 所以跑完采集打印一次峰值工作集，
    答辩时这就是实测数据，而不是口头承诺。

跨平台实现（Windows 上没有 resource 模块）：
    Linux   -> resource.getrusage().ru_maxrss，单位 KB
    macOS   -> 同上，但单位是字节（苹果的历史坑）
    Windows -> ctypes 调 psapi!GetProcessMemoryInfo
"""
from __future__ import annotations

import sys


def _windows_counters() -> tuple[int, int] | None:
    """返回 (当前工作集字节, 峰值工作集字节)；调用失败返回 None。"""
    try:
        import ctypes
        from ctypes import wintypes

        class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        # 64 位下必须显式声明 argtypes/restype，否则句柄会被截断成 32 位
        get_info = ctypes.WinDLL("psapi.dll").GetProcessMemoryInfo
        get_info.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(PROCESS_MEMORY_COUNTERS),
            wintypes.DWORD,
        ]
        get_info.restype = wintypes.BOOL

        get_current = ctypes.WinDLL("kernel32.dll").GetCurrentProcess
        get_current.argtypes = []
        get_current.restype = wintypes.HANDLE

        counters = PROCESS_MEMORY_COUNTERS()
        counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
        if not get_info(get_current(), ctypes.byref(counters), counters.cb):
            return None
        return int(counters.WorkingSetSize), int(counters.PeakWorkingSetSize)
    except Exception:  # noqa: BLE001 —— 读内存失败不该影响采集主流程
        return None


def _posix_maxrss_bytes() -> int | None:
    try:
        import resource

        raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    except Exception:  # noqa: BLE001
        return None
    # macOS 的单位是字节，其余平台是 KB
    return raw if sys.platform == "darwin" else raw * 1024


def peak_rss_mb() -> float:
    """进程峰值内存（MB）。取不到时返回 -1.0，调用方自行跳过展示。"""
    if sys.platform == "win32":
        pair = _windows_counters()
        return round(pair[1] / 1024 / 1024, 1) if pair else -1.0
    n = _posix_maxrss_bytes()
    return round(n / 1024 / 1024, 1) if n else -1.0


def current_rss_mb() -> float:
    """进程当前内存（MB）。"""
    if sys.platform == "win32":
        pair = _windows_counters()
        return round(pair[0] / 1024 / 1024, 1) if pair else -1.0
    # POSIX 上只有峰值可读，用峰值近似当前值
    return peak_rss_mb()


def format_mem() -> str:
    """给日志用的一行字符串，例如 `峰值内存 96.4 MB`。"""
    peak = peak_rss_mb()
    if peak < 0:
        return "峰值内存 读取失败"
    return f"峰值内存 {peak:.1f} MB"
