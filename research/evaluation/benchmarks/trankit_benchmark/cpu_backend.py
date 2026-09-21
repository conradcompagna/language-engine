"""Trankit benchmark: cpu backend."""

from __future__ import annotations

import os
from typing import Any, Dict


def _cpu_thread_candidates() -> list[int]:
    candidates = [1, 2, 4, 8]
    try:
        import psutil  # type: ignore

        physical = psutil.cpu_count(logical=False)
        logical = psutil.cpu_count(logical=True)
        if isinstance(physical, int) and physical > 0:
            candidates.append(physical)
        if isinstance(logical, int) and logical > 0:
            candidates.append(logical)
    except Exception:
        logical = os.cpu_count()
        if isinstance(logical, int) and logical > 0:
            candidates.append(logical)
    max_count = os.cpu_count() or max(candidates)
    return sorted({n for n in candidates if isinstance(n, int) and 1 <= n <= max_count})


def _set_cpu_thread_environment(thread_count: int) -> None:
    value = str(max(1, int(thread_count)))
    for key in [
        "OMP_NUM_THREADS",
        "MKL_NUM_THREADS",
        "OPENBLAS_NUM_THREADS",
        "NUMEXPR_NUM_THREADS",
    ]:
        os.environ[key] = value


def _set_torch_cpu_threads(torch_module: Any, thread_count: int) -> Dict[str, Any]:
    report: Dict[str, Any] = {"requested_threads": thread_count}
    try:
        torch_module.set_num_threads(max(1, int(thread_count)))
        report["num_threads"] = int(torch_module.get_num_threads())
    except Exception as exc:
        report["num_threads_error"] = str(exc)
    try:
        torch_module.set_num_interop_threads(1)
        report["num_interop_threads"] = int(torch_module.get_num_interop_threads())
    except Exception as exc:
        report["num_interop_threads_error"] = str(exc)
    return report


def _configure_cpu_torch_backend(torch_module: Any) -> Dict[str, Any]:
    report: Dict[str, Any] = {}
    try:
        engines = list(
            getattr(torch_module.backends.quantized, "supported_engines", [])
        )
        report["supported_quantized_engines"] = engines
        if "fbgemm" in engines:
            torch_module.backends.quantized.engine = "fbgemm"
        elif engines:
            torch_module.backends.quantized.engine = str(engines[0])
        report["quantized_engine"] = str(torch_module.backends.quantized.engine)
    except Exception as exc:
        report["quantized_engine_error"] = str(exc)
    try:
        torch_module.set_flush_denormal(True)
        report["flush_denormal"] = True
    except Exception as exc:
        report["flush_denormal_error"] = str(exc)
    return report


def _detect_cpu_bf16_support(torch_module: Any) -> Dict[str, Any]:
    report: Dict[str, Any] = {"supported": False, "reason": ""}
    try:
        checker = getattr(getattr(torch_module, "cpu", None), "is_bf16_supported", None)
        if callable(checker):
            supported = bool(checker())
            report["supported"] = supported
            report["reason"] = "torch.cpu.is_bf16_supported"
            return report
    except Exception as exc:
        report["torch_check_error"] = str(exc)

    try:
        if os.name == "nt":
            report["reason"] = (
                "No reliable Windows CPU BF16 feature probe was available in this Torch build."
            )
            return report
        flags = ""
        with open("/proc/cpuinfo", encoding="utf-8", errors="ignore") as f:
            flags = f.read().lower()
        supported = "avx512_bf16" in flags or "amx_bf16" in flags
        report["supported"] = supported
        report["reason"] = (
            "CPU flags include BF16 support"
            if supported
            else "CPU flags do not include avx512_bf16 or amx_bf16"
        )
        return report
    except Exception as exc:
        report["reason"] = "BF16 support probe failed"
        report["error"] = str(exc)
        return report
