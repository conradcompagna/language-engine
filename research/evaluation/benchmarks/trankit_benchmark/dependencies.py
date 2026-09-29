"""Trankit benchmark: dependencies."""

from __future__ import annotations

import os
import sys
from typing import Any, Dict

from . import settings


def _prepend_cpu_opt_deps() -> bool:
    if not os.path.isdir(settings.CPU_OPT_DEPS_DIR):
        return False
    if settings.CPU_OPT_DEPS_DIR not in sys.path:
        sys.path.insert(0, settings.CPU_OPT_DEPS_DIR)
    return True


def _append_onnx_deps() -> Dict[str, Any]:
    report = {"active": False, "path": "", "candidates": list(settings.ONNX_DEPS_DIRS)}
    errors = []
    for path in settings.ONNX_DEPS_DIRS:
        if not os.path.isdir(path):
            continue
        probe = os.path.join(path, "onnxruntime", "__init__.py")
        try:
            with open(probe, "rb") as f:
                f.read(1)
        except Exception as exc:
            errors.append(f"{path}: {exc}")
            continue
        if path not in sys.path:
            sys.path.append(path)
        report["active"] = True
        report["path"] = path
        report["skipped"] = errors
        return report
    report["error"] = "No ONNX dependency directory exists."
    report["skipped"] = errors
    return report


def _safe_onnx_name(value: Any) -> str:
    text = str(value or "unknown")
    out = []
    for char in text:
        if char.isalnum() or char in {"-", "_"}:
            out.append(char)
        else:
            out.append("_")
    return "".join(out).strip("_") or "unknown"
