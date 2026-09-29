"""Trankit benchmark: cpu selection cache."""

from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, Optional

from . import cpu_backend, settings


def _read_cpu_opt_selection_cache() -> Optional[Dict[str, Any]]:
    try:
        with open(settings.CPU_OPT_SELECTION_CACHE_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    if data.get("cache_version") != settings.CPU_OPT_SELECTION_CACHE_VERSION:
        return None
    profile = str(data.get("selected_profile") or "")
    thread_count = data.get("selected_thread_count")
    tok_batch_size = data.get("selected_tok_batch_size")
    tag_batch_size = data.get("selected_tag_batch_size")
    if not profile or not isinstance(thread_count, int):
        return None
    if not isinstance(tok_batch_size, int) or not isinstance(tag_batch_size, int):
        return None
    if profile != settings.CPU_OPT_PROFILE_NAME:
        return None
    if data.get("output_match") is False:
        return None
    data["from_cache"] = True
    data["cache_path"] = settings.CPU_OPT_SELECTION_CACHE_PATH
    return data


def _write_cpu_opt_selection_cache(selection: Dict[str, Any]) -> None:
    os.makedirs(settings.CPU_OPT_CACHE_DIR, exist_ok=True)
    payload = {
        "cache_version": settings.CPU_OPT_SELECTION_CACHE_VERSION,
        "created_at": time.time(),
        "selected_profile": str(
            selection.get("selected_profile") or settings.CPU_OPT_PROFILE_NAME
        ),
        "selected_thread_count": int(selection.get("selected_thread_count") or 1),
        "selected_tok_batch_size": int(
            selection.get("selected_tok_batch_size")
            or settings.CPU_OPT_DEFAULT_TOK_BATCH_SIZE
        ),
        "selected_tag_batch_size": int(
            selection.get("selected_tag_batch_size")
            or settings.CPU_OPT_DEFAULT_TAG_BATCH_SIZE
        ),
        "selected_elapsed_seconds": selection.get("selected_elapsed_seconds"),
        "selected_p50_seconds": selection.get("selected_p50_seconds"),
        "selected_p95_seconds": selection.get("selected_p95_seconds"),
        "selected_thread_seconds": selection.get("selected_thread_seconds"),
        "selected_thread_p95_seconds": selection.get("selected_thread_p95_seconds"),
        "selected_batch_seconds": selection.get("selected_batch_seconds"),
        "baseline_fingerprint": selection.get("baseline_fingerprint"),
        "selected_fingerprint": selection.get("selected_fingerprint"),
        "output_match": bool(selection.get("output_match")),
        "setup_seconds": selection.get("setup_seconds"),
        "deps_path": settings.CPU_OPT_DEPS_DIR,
        "module_cache_dir": settings.CPU_OPT_CACHE_DIR,
    }
    with open(settings.CPU_OPT_SELECTION_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)


def _default_cpu_opt_selection() -> Dict[str, Any]:
    candidates = cpu_backend._cpu_thread_candidates()
    thread_count = max(candidates) if candidates else 1
    return {
        "ok": True,
        "selected_profile": settings.CPU_OPT_PROFILE_NAME,
        "selected_thread_count": thread_count,
        "selected_tok_batch_size": settings.CPU_OPT_DEFAULT_TOK_BATCH_SIZE,
        "selected_tag_batch_size": settings.CPU_OPT_DEFAULT_TAG_BATCH_SIZE,
        "selected_elapsed_seconds": None,
        "baseline_fingerprint": "",
        "selected_fingerprint": "",
        "output_match": None,
        "setup_seconds": 0.0,
        "deps_path": settings.CPU_OPT_DEPS_DIR,
        "module_cache_dir": settings.CPU_OPT_CACHE_DIR,
        "from_default": True,
        "reason": "No cached CPU optimization selection was found; using PyTorch XLM-R base dynamic INT8 as the default CPU profile.",
    }
