"""Trankit benchmark: memory."""

from __future__ import annotations

import ctypes
import gc
import os
import threading
import time
from typing import Any, Dict, Optional


def _force_gc() -> None:
    gc.collect()
    gc.collect()


def _get_rss_windows() -> int:
    class PROCESS_MEMORY_COUNTERS_EX(ctypes.Structure):
        _fields_ = [
            ("cb", ctypes.c_ulong),
            ("PageFaultCount", ctypes.c_ulong),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
            ("PrivateUsage", ctypes.c_size_t),
        ]

    counters = PROCESS_MEMORY_COUNTERS_EX()
    counters.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS_EX)
    process = ctypes.windll.kernel32.GetCurrentProcess()
    ok = ctypes.windll.psapi.GetProcessMemoryInfo(
        process, ctypes.byref(counters), counters.cb
    )
    if not ok:
        raise OSError("GetProcessMemoryInfo failed")
    return int(counters.WorkingSetSize)


def current_rss_bytes() -> int:
    onnx_report_for_error: Dict[str, Any] = {}
    try:
        import psutil  # type: ignore

        return int(psutil.Process(os.getpid()).memory_info().rss)
    except Exception:
        pass

    if os.name == "nt":
        try:
            return _get_rss_windows()
        except Exception:
            return -1

    return -1


def _gpu_snapshot(torch_module: Any) -> Dict[str, Any]:
    if torch_module is None:
        return {"available": False}
    try:
        available = bool(torch_module.cuda.is_available())
    except Exception:
        return {"available": False}
    if not available:
        return {"available": False}

    snap: Dict[str, Any] = {"available": True}
    try:
        snap["device_count"] = int(torch_module.cuda.device_count())
    except Exception:
        snap["device_count"] = None
    try:
        idx = int(torch_module.cuda.current_device())
        snap["current_device"] = idx
        snap["device_name"] = str(torch_module.cuda.get_device_name(idx))
    except Exception:
        snap["current_device"] = None
        snap["device_name"] = ""
    try:
        free_b, total_b = torch_module.cuda.mem_get_info()
        snap["mem_free_bytes"] = int(free_b)
        snap["mem_total_bytes"] = int(total_b)
    except Exception:
        snap["mem_free_bytes"] = None
        snap["mem_total_bytes"] = None
    for name, fn_name in [
        ("allocated_bytes", "memory_allocated"),
        ("reserved_bytes", "memory_reserved"),
        ("max_allocated_bytes", "max_memory_allocated"),
        ("max_reserved_bytes", "max_memory_reserved"),
    ]:
        try:
            snap[name] = int(getattr(torch_module.cuda, fn_name)())
        except Exception:
            snap[name] = None
    return snap


def _bytes_delta(after_value: Any, before_value: Any) -> Optional[int]:
    if isinstance(after_value, int) and isinstance(before_value, int):
        return after_value - before_value
    return None


def _gpu_delta(after: Dict[str, Any], before: Dict[str, Any]) -> Dict[str, Any]:
    keys = [
        "allocated_bytes",
        "reserved_bytes",
        "max_allocated_bytes",
        "max_reserved_bytes",
        "mem_free_bytes",
    ]
    out: Dict[str, Any] = {}
    for key in keys:
        out[f"{key}_delta"] = _bytes_delta(after.get(key), before.get(key))
    return out


def _sync_cuda(torch_module: Any, enabled: bool) -> None:
    if not enabled or torch_module is None:
        return
    try:
        if torch_module.cuda.is_available():
            torch_module.cuda.synchronize()
    except Exception:
        pass


class MemorySampler:
    def __init__(self, torch_module: Any, interval_seconds: float = 0.02):
        self.torch = torch_module
        self.interval_seconds = interval_seconds
        self.stop_event = threading.Event()
        self.thread: Optional[threading.Thread] = None
        self.rss_peak_bytes = -1
        self.gpu_allocated_peak_bytes: Optional[int] = None
        self.gpu_reserved_peak_bytes: Optional[int] = None
        self.samples = 0

    def start(self) -> None:
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread is not None:
            self.thread.join(timeout=1.0)

    def _run(self) -> None:
        while not self.stop_event.is_set():
            self.samples += 1
            rss = current_rss_bytes()
            if rss > self.rss_peak_bytes:
                self.rss_peak_bytes = rss
            gpu = _gpu_snapshot(self.torch)
            allocated = gpu.get("allocated_bytes")
            reserved = gpu.get("reserved_bytes")
            if isinstance(allocated, int):
                if (
                    self.gpu_allocated_peak_bytes is None
                    or allocated > self.gpu_allocated_peak_bytes
                ):
                    self.gpu_allocated_peak_bytes = allocated
            if isinstance(reserved, int):
                if (
                    self.gpu_reserved_peak_bytes is None
                    or reserved > self.gpu_reserved_peak_bytes
                ):
                    self.gpu_reserved_peak_bytes = reserved
            time.sleep(self.interval_seconds)
