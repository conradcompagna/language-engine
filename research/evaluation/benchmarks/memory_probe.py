"""
Standalone memory probe for this project.

What it measures:
1) Trankit transformer/backend memory.
2) Per-language Trankit model memory by pipeline component.
3) Per-language dictionary load memory for the four configured languages.

Usage:
  python memory_probe.py
  python memory_probe.py --output memory_probe_report.json
  python memory_probe.py --skip-warmup
"""

from __future__ import annotations

import argparse
import ctypes
import gc
import importlib
import json
import os
import platform
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Tuple

import language_registry as lr

try:
    import torch
    import torch.nn as nn
except Exception:  # pragma: no cover - optional at import time
    torch = None
    nn = None


@dataclass
class Snapshot:
    label: str
    rss_bytes: int
    ts: float


def _format_bytes(num_bytes: int) -> str:
    if num_bytes < 0:
        return "n/a"
    units = ["B", "KB", "MB", "GB", "TB"]
    n = float(num_bytes)
    for unit in units:
        if n < 1024.0 or unit == units[-1]:
            return f"{n:.2f} {unit}"
        n /= 1024.0
    return f"{num_bytes} B"


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
    kernel32 = ctypes.windll.kernel32
    psapi = ctypes.windll.psapi
    process = kernel32.GetCurrentProcess()
    ok = psapi.GetProcessMemoryInfo(process, ctypes.byref(counters), counters.cb)
    if not ok:
        raise OSError("GetProcessMemoryInfo failed")
    return int(counters.WorkingSetSize)


def current_rss_bytes() -> int:
    try:
        import psutil

        return int(psutil.Process(os.getpid()).memory_info().rss)
    except Exception:
        pass

    if os.name == "nt":
        try:
            return _get_rss_windows()
        except Exception:
            return -1

    return -1


def _snapshot(label: str, snapshots: list[Snapshot]) -> int:
    _force_gc()
    time.sleep(0.05)
    rss = current_rss_bytes()
    snapshots.append(Snapshot(label=label, rss_bytes=rss, ts=time.time()))
    return rss


def _safe_len(value: Any) -> Optional[int]:
    try:
        return len(value)
    except Exception:
        return None


def _import_class(path: str):
    module_path, class_name = path.rsplit(":", 1)
    module = importlib.import_module(module_path)
    return getattr(module, class_name)


def _register_custom_trankit_names() -> None:
    from trankit.utils.tbinfo import (
        lang2treebank,
        langwithner,
        supported_langs,
        tbname2training_id,
    )

    for info in lr.LANGUAGE_REGISTRY.values():
        name = info.get("trankit_name", "")
        treebank = info.get("trankit_treebank")
        if treebank and name and name not in supported_langs:
            if isinstance(supported_langs, set):
                supported_langs.add(name)
            else:
                supported_langs.append(name)
            if isinstance(langwithner, set):
                langwithner.add(name)
            else:
                langwithner.append(name)
            lang2treebank[name] = treebank
            if treebank not in tbname2training_id:
                tbname2training_id[treebank] = 0

    for info in lr.LANGUAGE_REGISTRY.values():
        name = info.get("trankit_name")
        treebank = info.get("trankit_treebank")
        if name and treebank:
            lang2treebank[name] = treebank


def _iter_tensors(obj: Any, visited: set[int]) -> Iterable[Any]:
    if obj is None or torch is None:
        return

    obj_id = id(obj)
    if obj_id in visited:
        return
    visited.add(obj_id)

    if isinstance(obj, torch.Tensor):
        yield obj
        return

    if nn is not None and isinstance(obj, nn.Module):
        for tensor in obj.parameters(recurse=True):
            yield tensor
        for tensor in obj.buffers(recurse=True):
            yield tensor
        return

    if isinstance(obj, dict):
        for value in obj.values():
            yield from _iter_tensors(value, visited)
        return

    if isinstance(obj, (list, tuple, set, frozenset)):
        for value in obj:
            yield from _iter_tensors(value, visited)


def _tensor_storage_key_and_size(tensor: Any) -> Tuple[Tuple[str, int, int], int]:
    # Return (storage_key, storage_nbytes). Key dedupes shared tensors.
    device = str(getattr(tensor, "device", "cpu"))
    try:
        storage = tensor.untyped_storage()
        key = (device, int(storage.data_ptr()), int(storage.nbytes()))
        size = int(storage.nbytes())
        return key, size
    except Exception:
        try:
            key = (
                device,
                int(tensor.data_ptr()),
                int(tensor.nelement() * tensor.element_size()),
            )
            size = int(tensor.nelement() * tensor.element_size())
            return key, size
        except Exception:
            key = (device, id(tensor), int(sys.getsizeof(tensor)))
            return key, int(sys.getsizeof(tensor))


def _raw_tensor_nbytes(tensor: Any) -> int:
    try:
        return int(tensor.nelement() * tensor.element_size())
    except Exception:
        return int(sys.getsizeof(tensor))


def _tensor_memory_stats(obj: Any, global_seen: Optional[set[Tuple[str, int, int]]] = None) -> Dict[str, Any]:
    if torch is None:
        return {
            "tensor_count": 0,
            "raw_bytes": 0,
            "unique_local_bytes": 0,
            "unique_global_increment_bytes": 0,
            "torch_available": False,
        }

    if global_seen is None:
        global_seen = set()

    local_seen: set[Tuple[str, int, int]] = set()
    raw_bytes = 0
    unique_local_bytes = 0
    unique_global_increment_bytes = 0
    tensor_count = 0

    for tensor in _iter_tensors(obj, visited=set()):
        tensor_count += 1
        raw_bytes += _raw_tensor_nbytes(tensor)

        storage_key, storage_nbytes = _tensor_storage_key_and_size(tensor)
        if storage_key not in local_seen:
            local_seen.add(storage_key)
            unique_local_bytes += storage_nbytes
        if storage_key not in global_seen:
            global_seen.add(storage_key)
            unique_global_increment_bytes += storage_nbytes

    return {
        "tensor_count": tensor_count,
        "raw_bytes": raw_bytes,
        "unique_local_bytes": unique_local_bytes,
        "unique_global_increment_bytes": unique_global_increment_bytes,
        "torch_available": True,
    }


def _probe_trankit(skip_warmup: bool) -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    snapshots: list[Snapshot] = []
    events: list[Dict[str, Any]] = []

    t0 = _snapshot("trankit_probe_start", snapshots)

    from trankit import Pipeline

    t1 = _snapshot("after_trankit_import", snapshots)
    events.append(
        {
            "event": "trankit_import",
            "delta_bytes": max(0, t1 - t0),
        }
    )

    _register_custom_trankit_names()

    codes = sorted(
        lr.LANGUAGE_REGISTRY.keys(),
        key=lambda code: (0 if lr.LANGUAGE_REGISTRY[code].get("trankit_cache_dir") else 1),
    )

    first_code = codes[0]
    first_info = lr.LANGUAGE_REGISTRY[first_code]
    first_name = first_info["trankit_name"]
    first_cache_dir = first_info.get("trankit_cache_dir")

    before_init = _snapshot(f"before_pipeline_init:{first_name}", snapshots)
    if first_cache_dir:
        pipeline = Pipeline(lang=first_name, cache_dir=first_cache_dir)
    else:
        pipeline = Pipeline(first_name)
    after_init = _snapshot(f"after_pipeline_init:{first_name}", snapshots)

    init_delta = max(0, after_init - before_init)
    events.append(
        {
            "event": "pipeline_init_first_language",
            "lang_code": first_code,
            "trankit_name": first_name,
            "delta_bytes": init_delta,
        }
    )

    per_language_rss: Dict[str, Dict[str, Any]] = {
        first_code: {
            "trankit_name": first_name,
            "load_delta_bytes": init_delta,
        }
    }

    for code in codes[1:]:
        info = lr.LANGUAGE_REGISTRY[code]
        trankit_name = info["trankit_name"]
        before_add = _snapshot(f"before_add:{trankit_name}", snapshots)
        pipeline.add(trankit_name)
        after_add = _snapshot(f"after_add:{trankit_name}", snapshots)
        delta = max(0, after_add - before_add)
        events.append(
            {
                "event": "pipeline_add_language",
                "lang_code": code,
                "trankit_name": trankit_name,
                "delta_bytes": delta,
            }
        )
        per_language_rss[code] = {
            "trankit_name": trankit_name,
            "load_delta_bytes": delta,
        }

    sample_text_by_code = {
        "zh": "今天天气很好。",
        "ja": "今日は良い天気です。",
        "ko": "오늘 날씨가 좋다.",
        "vi": "Hom nay troi dep.",
    }

    if not skip_warmup:
        for code in lr.LANGUAGE_REGISTRY.keys():
            info = lr.LANGUAGE_REGISTRY[code]
            trankit_name = info["trankit_name"]
            before_warm = _snapshot(f"before_warmup:{trankit_name}", snapshots)
            warmup_status = "ok"
            warmup_error = ""
            try:
                pipeline.set_active(trankit_name)
                _ = pipeline(sample_text_by_code.get(code, "Hello world."))
            except Exception as exc:  # pragma: no cover - depends on runtime models
                warmup_status = "error"
                warmup_error = f"{type(exc).__name__}: {exc}"
            after_warm = _snapshot(f"after_warmup:{trankit_name}", snapshots)
            warm_delta = max(0, after_warm - before_warm)
            lang_slot = per_language_rss.setdefault(
                code, {"trankit_name": trankit_name, "load_delta_bytes": 0}
            )
            lang_slot["warmup_delta_bytes"] = warm_delta
            lang_slot["warmup_status"] = warmup_status
            if warmup_error:
                lang_slot["warmup_error"] = warmup_error

    # Tensor attribution with global dedupe:
    # backend first, then per-language components.
    tensor_seen: set[Tuple[str, int, int]] = set()
    backend: Dict[str, Any] = {}
    backend_groups = [
        ("embedding_layers", getattr(pipeline, "_embedding_layers", None)),
        ("embedding_weights_cache", getattr(pipeline, "_embedding_weights", None)),
    ]
    for label, obj in backend_groups:
        stats = _tensor_memory_stats(obj, global_seen=tensor_seen)
        backend[label] = stats

    backend_total_unique = sum(
        int(group["unique_global_increment_bytes"]) for group in backend.values()
    )

    language_components: Dict[str, Any] = {}
    for code, info in lr.LANGUAGE_REGISTRY.items():
        trankit_name = info["trankit_name"]
        component_objects = {
            "tokenizer": getattr(pipeline, "_tokenizer", {}).get(trankit_name),
            "tagger": getattr(pipeline, "_tagger", {}).get(trankit_name),
            "lemmatizer": getattr(pipeline, "_lemma_model", {}).get(trankit_name),
            "ner": getattr(pipeline, "_ner_model", {}).get(trankit_name),
            "mwt": getattr(pipeline, "_mwt_model", {}).get(trankit_name),
        }
        components_out: Dict[str, Any] = {}
        unique_total = 0
        raw_total = 0
        for comp_name, comp_obj in component_objects.items():
            stats = _tensor_memory_stats(comp_obj, global_seen=tensor_seen)
            components_out[comp_name] = stats
            unique_total += int(stats["unique_global_increment_bytes"])
            raw_total += int(stats["raw_bytes"])

        language_components[code] = {
            "trankit_name": trankit_name,
            "components": components_out,
            "component_unique_total_bytes": unique_total,
            "component_raw_total_bytes": raw_total,
        }

    t_final = _snapshot("trankit_probe_end", snapshots)

    result["events"] = events
    result["snapshots"] = [
        {"label": s.label, "rss_bytes": s.rss_bytes, "rss_human": _format_bytes(s.rss_bytes), "ts": s.ts}
        for s in snapshots
    ]
    result["total_probe_delta_bytes"] = max(0, t_final - t0)
    result["per_language_rss"] = per_language_rss
    result["backend_tensor_breakdown"] = backend
    result["backend_tensor_unique_total_bytes"] = backend_total_unique
    result["language_component_tensors"] = language_components
    result["torch_available"] = torch is not None

    return result


def _probe_dictionaries() -> Dict[str, Any]:
    result: Dict[str, Any] = {}
    snapshots: list[Snapshot] = []
    per_language: Dict[str, Any] = {}
    loaded_objects: Dict[str, Any] = {}

    start = _snapshot("dictionary_probe_start", snapshots)

    for code, info in lr.LANGUAGE_REGISTRY.items():
        dict_cls = _import_class(info["dict_class"])
        dict_path = lr.APP_ROOT / info["dict_file"]
        before = _snapshot(f"before_dictionary_load:{code}", snapshots)
        dict_obj = dict_cls(dict_path)
        after = _snapshot(f"after_dictionary_load:{code}", snapshots)

        loaded_objects[code] = dict_obj
        attr_summary: Dict[str, Any] = {}
        for attr_name, attr_value in vars(dict_obj).items():
            attr_summary[attr_name] = {
                "type": type(attr_value).__name__,
                "len": _safe_len(attr_value),
                "shallow_bytes": int(sys.getsizeof(attr_value)),
            }

        per_language[code] = {
            "dict_class": info["dict_class"],
            "dict_path": str(dict_path),
            "load_delta_bytes": max(0, after - before),
            "top_level_attrs": attr_summary,
        }

    end = _snapshot("dictionary_probe_end", snapshots)

    # Keep references alive until after the final snapshot.
    _ = loaded_objects

    result["per_language"] = per_language
    result["snapshots"] = [
        {"label": s.label, "rss_bytes": s.rss_bytes, "rss_human": _format_bytes(s.rss_bytes), "ts": s.ts}
        for s in snapshots
    ]
    result["total_probe_delta_bytes"] = max(0, end - start)
    return result


def _print_summary(report: Dict[str, Any]) -> None:
    print("")
    print("=== Memory Probe Summary ===")
    print(f"Python: {report['meta']['python_version']}")
    print(f"Platform: {report['meta']['platform']}")
    print(f"PID: {report['meta']['pid']}")

    trankit = report.get("trankit")
    if trankit:
        print("")
        print("Trankit RSS deltas:")
        for event in trankit.get("events", []):
            name = event["event"]
            code = event.get("lang_code")
            tr_name = event.get("trankit_name")
            delta = _format_bytes(int(event.get("delta_bytes", 0)))
            parts = [name, delta]
            if code:
                parts.append(f"code={code}")
            if tr_name:
                parts.append(f"name={tr_name}")
            print("  - " + " | ".join(parts))

        print("")
        print("Trankit tensor memory (deduped unique increments):")
        backend_total = trankit.get("backend_tensor_unique_total_bytes", 0)
        print(f"  - backend_total: {_format_bytes(int(backend_total))}")
        backend = trankit.get("backend_tensor_breakdown", {})
        for label, stats in backend.items():
            print(
                f"    {label}: {_format_bytes(int(stats.get('unique_global_increment_bytes', 0)))}"
            )

        for code in lr.LANGUAGE_REGISTRY.keys():
            lang = trankit.get("language_component_tensors", {}).get(code, {})
            if not lang:
                continue
            unique_total = int(lang.get("component_unique_total_bytes", 0))
            load_delta = int(trankit.get("per_language_rss", {}).get(code, {}).get("load_delta_bytes", 0))
            warm_delta = int(
                trankit.get("per_language_rss", {}).get(code, {}).get("warmup_delta_bytes", 0)
            )
            tr_name = lang.get("trankit_name", "")
            print(
                f"  - {code} ({tr_name}): "
                f"component_unique={_format_bytes(unique_total)}, "
                f"load_rss_delta={_format_bytes(load_delta)}, "
                f"warmup_rss_delta={_format_bytes(warm_delta)}"
            )

    dictionaries = report.get("dictionaries")
    if dictionaries:
        print("")
        print("Dictionary load RSS deltas:")
        for code in lr.LANGUAGE_REGISTRY.keys():
            row = dictionaries.get("per_language", {}).get(code)
            if not row:
                continue
            print(
                f"  - {code}: {_format_bytes(int(row.get('load_delta_bytes', 0)))} "
                f"({row.get('dict_class', '')})"
            )

    print("")
    print("Notes:")
    print("  - RSS deltas are process-level and can include allocator/caching effects.")
    print("  - Tensor bytes are computed from live torch storages with deduplication.")
    print("  - Dictionary attr sizes are shallow; use RSS deltas as primary numbers.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Probe memory usage for Trankit + dictionaries.")
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Optional path to write full JSON report.",
    )
    parser.add_argument(
        "--skip-trankit",
        action="store_true",
        help="Skip Trankit probing.",
    )
    parser.add_argument(
        "--skip-dictionaries",
        action="store_true",
        help="Skip dictionary probing.",
    )
    parser.add_argument(
        "--skip-warmup",
        action="store_true",
        help="Do not run first inference warm-up per language.",
    )
    args = parser.parse_args()

    report: Dict[str, Any] = {
        "meta": {
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "python_version": sys.version.replace("\n", " "),
            "platform": platform.platform(),
            "pid": os.getpid(),
            "app_root": str(lr.APP_ROOT),
        }
    }

    if not args.skip_trankit:
        report["trankit"] = _probe_trankit(skip_warmup=args.skip_warmup)
    if not args.skip_dictionaries:
        report["dictionaries"] = _probe_dictionaries()

    _print_summary(report)

    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"JSON report written to: {args.output}")


if __name__ == "__main__":
    main()
