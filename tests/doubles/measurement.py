"""Process-local observations for acceptance tools, never a production dependency."""

# SPDX-License-Identifier: Apache-2.0
import asyncio
import os
from pathlib import Path
import sys
import tracemalloc


def memory():
    rss = None
    source = "unavailable"
    if sys.platform == "win32":
        import ctypes
        from ctypes import wintypes
        class Counters(ctypes.Structure):
            _fields_ = [("cb", wintypes.DWORD), ("faults", wintypes.DWORD)] + [
                (name, ctypes.c_size_t) for name in
                ("peak", "working", "peak_paged", "paged", "peak_nonpaged", "nonpaged", "pagefile", "peak_pagefile")]
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        kernel.GetCurrentProcess.restype = wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        counters = Counters()
        counters.cb = ctypes.sizeof(counters)
        if not psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            raise ctypes.WinError(ctypes.get_last_error())
        rss, source = counters.working, "Windows working set"
    elif sys.platform.startswith("linux"):
        rss = int(Path("/proc/self/statm").read_text().split()[1]) * os.sysconf("SC_PAGE_SIZE")
        source = "Linux resident pages"
    traced, peak = tracemalloc.get_traced_memory() if tracemalloc.is_tracing() else (None, None)
    return {"pid": os.getpid(), "rss_bytes": rss, "rss_source": source,
            "python_bytes": traced, "python_peak_bytes": peak,
            "live_tasks": len(asyncio.all_tasks())}
