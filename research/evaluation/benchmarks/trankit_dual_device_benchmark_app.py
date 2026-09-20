"""
Standalone Trankit CPU/GPU benchmark app.

This file is intentionally separate from router.py and the main Flask app.
It does not import or load Trankit in the parent process. When you run this
file, it starts worker processes immediately at server startup:

  - one worker forces the current language_registry pipeline onto GPU
  - one worker forces GPU and applies sandboxed PyTorch hot-path optimizations

The workers load pipelines into memory at app start, then the web UI lets
you paste text and run the same Trankit request through each worker.

Run only when the machine is free:

  python trankit_dual_device_benchmark_app.py

Then open:

  http://127.0.0.1:5055
"""

from __future__ import annotations

import ctypes
import gc
import hashlib
import json
import multiprocessing as mp
import os
import queue
import sys
import threading
import time
import traceback
import types
import uuid
from contextlib import ExitStack, contextmanager
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from flask import Flask, jsonify, request


HOST = "127.0.0.1"
PORT = 5055
WORKER_RESPONSE_TIMEOUT_SECONDS = 60 * 60
LOAD_PROBE_TIMEOUT_SECONDS = 60 * 60
STARTUP_WORKER_TIMEOUT_SECONDS = 60 * 60
CPU_OPT_DEPS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".trankit_cpu_opt_deps")
CPU_OPT_CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".trankit_cpu_opt_cache")
CPU_OPT_PROFILE_NAME = "xlmr_base_int8_pytorch"
CPU_OPT_SELECTION_CACHE_VERSION = 4
CPU_OPT_SELECTION_CACHE_PATH = os.path.join(CPU_OPT_CACHE_DIR, "selection_v4_xlmr_base_int8_pytorch.json")
CPU_OPT_XLMR_CACHE_VERSION = 3
CPU_OPT_XLMR_CACHE_PATH = os.path.join(CPU_OPT_CACHE_DIR, "xlmr_base_int8_no_adapters_v3.pt")
CPU_OPT_SEQ2SEQ_CACHE_PATH = os.path.join(CPU_OPT_CACHE_DIR, "seq2seq_int8_modules_v2.pt")
CPU_OPT_PROFILE_TIMEOUT_SECONDS = 60 * 60
CPU_OPT_TUNE_REPETITIONS = 3
CPU_OPT_SEQUENCE_BUCKETS = [64, 128, 256, 400]
CPU_OPT_QUANTIZE_EXCLUDE_TOKENS = ("adapter", "layernorm", "layer_norm", "embedding")
CPU_OPT_TUNE_TEXT = (
    "Ceci est une phrase courte pour regler le chemin CPU. "
    "Cette deuxieme phrase garde la tokenisation et l'analyse actives."
)
CPU_OPT_DEFAULT_TOK_BATCH_SIZE = 8
CPU_OPT_DEFAULT_TAG_BATCH_SIZE = 32
GPU_OPT_PROFILE_NAME = "gpu_pytorch_hotpath"
GPU_OPT_ENABLE_TORCH_COMPILE = False
GPU_OPT_SEQUENCE_BUCKETS = [64, 128, 256, 400]
ONNX_DEPS_DIRS = [
    r"C:\tmp\trankit_onnx_deps_v2",
    r"C:\tmp\trankit_onnx_deps",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), ".trankit_onnx_deps"),
    CPU_OPT_DEPS_DIR,
]
ONNX_CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".trankit_compressed_runtime")
ONNX_MANIFEST_PATH = os.path.join(ONNX_CACHE_DIR, "manifest.json")
ONNX_PROFILE_NAME = "one_xlmr_dynamic_adapter_int8"
ONNX_EXPORT_OPSET = 17
ONNX_CPU_TOK_BATCH_SIZE = 12
ONNX_CPU_TAG_BATCH_SIZE = 32
ONNX_DYNAMIC_TOK_BATCH_CANDIDATES = [1, 2, 3, 4, 6, 8, 12, 16]
ONNX_DYNAMIC_TAG_BATCH_CANDIDATES = [1, 2, 4, 8, 12, 16, 24, 32]
ONNX_DYNAMIC_TOK_CALL_OVERHEAD_UNITS = 768
ONNX_DYNAMIC_TAG_CALL_OVERHEAD_UNITS = 768


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
    ok = ctypes.windll.psapi.GetProcessMemoryInfo(process, ctypes.byref(counters), counters.cb)
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


def _annotation_fingerprint(annotation: Any) -> str:
    payload = json.dumps(annotation, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _annotation_counts(annotation: Any) -> Dict[str, int]:
    sentences = annotation.get("sentences") if isinstance(annotation, dict) else []
    if not isinstance(sentences, list):
        sentences = []
    token_count = 0
    ner_count = 0
    dependency_edge_count = 0
    for sentence in sentences:
        if not isinstance(sentence, dict):
            continue
        tokens = sentence.get("tokens")
        if not isinstance(tokens, list):
            tokens = sentence.get("TOKENS") if isinstance(sentence.get("TOKENS"), list) else []
        for token in tokens:
            if not isinstance(token, dict):
                continue
            token_count += 1
            if token.get("ner") or token.get("NER"):
                ner_count += 1
            if token.get("head") is not None or token.get("HEAD") is not None:
                dependency_edge_count += 1
    return {
        "sentence_count": len(sentences),
        "token_count": token_count,
        "ner_count": ner_count,
        "dependency_edge_count": dependency_edge_count,
    }


def _annotation_sentences(annotation: Any) -> list[Any]:
    if not isinstance(annotation, dict):
        return []
    sentences = annotation.get("sentences")
    if isinstance(sentences, list):
        return sentences
    sentences = annotation.get("SENTENCES")
    return sentences if isinstance(sentences, list) else []


def _sentence_tokens(sentence: Any) -> list[Any]:
    if not isinstance(sentence, dict):
        return []
    tokens = sentence.get("tokens")
    if isinstance(tokens, list):
        return tokens
    tokens = sentence.get("TOKENS")
    return tokens if isinstance(tokens, list) else []


def _first_value(data: Any, keys: list[str]) -> Any:
    if not isinstance(data, dict):
        return None
    for key in keys:
        if key in data:
            return data.get(key)
    return None


def _compact_value(value: Any) -> str:
    if value is None:
        return "missing"
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def _token_text(token: Any) -> str:
    return _compact_value(_first_value(token, ["text", "TEXT"]))


def _expanded_texts(token: Any) -> tuple[str, ...]:
    expanded = _first_value(token, ["expanded", "EXPANDED"])
    if not isinstance(expanded, list):
        return ()
    return tuple(_token_text(item) for item in expanded if isinstance(item, dict))


def _analysis_units(sentence: Any) -> list[Any]:
    out: list[Any] = []
    for token in _sentence_tokens(sentence):
        expanded = _first_value(token, ["expanded", "EXPANDED"])
        if isinstance(expanded, list) and expanded:
            out.extend(item for item in expanded if isinstance(item, dict))
        elif isinstance(token, dict):
            out.append(token)
    return out


def _sentence_signature(sentence: Any) -> str:
    return "\u241f".join(_token_text(token) for token in _sentence_tokens(sentence))


def _sentence_boundary_signature(sentence: Any) -> str:
    if not isinstance(sentence, dict):
        return "missing"
    span = _first_value(sentence, ["dspan", "DSPAN", "span", "SPAN"])
    if isinstance(span, (list, tuple)) and len(span) >= 2:
        try:
            return f"span:{int(span[0])}:{int(span[1])}"
        except (TypeError, ValueError):
            pass
    text = _first_value(sentence, ["text", "TEXT"])
    if text is not None:
        return f"text:{_compact_value(text)}"
    tokens = _sentence_tokens(sentence)
    if not tokens:
        return "empty"
    first_span = _first_value(tokens[0], ["dspan", "DSPAN", "span", "SPAN"])
    last_span = _first_value(tokens[-1], ["dspan", "DSPAN", "span", "SPAN"])
    if (
        isinstance(first_span, (list, tuple)) and len(first_span) >= 1
        and isinstance(last_span, (list, tuple)) and len(last_span) >= 2
    ):
        try:
            return f"token-span:{int(first_span[0])}:{int(last_span[1])}"
        except (TypeError, ValueError):
            pass
    return f"tokens:{_sentence_signature(sentence)}"


def _matching_index_pairs(left: list[str], right: list[str]) -> list[tuple[int, int]]:
    pairs: list[tuple[int, int]] = []
    matcher = __import__("difflib").SequenceMatcher(a=left, b=right)
    for block in matcher.get_matching_blocks():
        for offset in range(block.size):
            pairs.append((block.a + offset, block.b + offset))
    return pairs


def _sequence_same_count(left: list[str], right: list[str]) -> int:
    matcher = __import__("difflib").SequenceMatcher(a=left, b=right)
    return sum(block.size for block in matcher.get_matching_blocks())


def _metric_payload(label: str, same: int, total: int) -> Dict[str, Any]:
    same = int(max(0, same))
    total = int(max(0, total))
    diff = max(0, total - same)
    same_percent = (same / total * 100.0) if total else None
    diff_percent = (diff / total * 100.0) if total else None
    return {
        "label": label,
        "same": same,
        "diff": diff,
        "total": total,
        "same_percent": same_percent,
        "diff_percent": diff_percent,
    }


def _metric_line(metric: Dict[str, Any]) -> str:
    same_percent = metric.get("same_percent")
    diff_percent = metric.get("diff_percent")
    if same_percent is None or diff_percent is None:
        return f"{metric['label']}: n/a"
    return (
        f"{metric['label']}: "
        f"{same_percent:.1f}% same / {diff_percent:.1f}% diff "
        f"({metric['same']}/{metric['total']})"
    )


def _annotation_discrepancy_report(cpu_annotation: Any, gpu_annotation: Any) -> Dict[str, Any]:
    cpu_fingerprint = _annotation_fingerprint(cpu_annotation)
    gpu_fingerprint = _annotation_fingerprint(gpu_annotation)

    cpu_sentences = _annotation_sentences(cpu_annotation)
    gpu_sentences = _annotation_sentences(gpu_annotation)
    metrics: list[Dict[str, Any]] = []
    cpu_sentence_boundaries = [_sentence_boundary_signature(sentence) for sentence in cpu_sentences]
    gpu_sentence_boundaries = [_sentence_boundary_signature(sentence) for sentence in gpu_sentences]
    cpu_sentence_sigs = [_sentence_signature(sentence) for sentence in cpu_sentences]
    gpu_sentence_sigs = [_sentence_signature(sentence) for sentence in gpu_sentences]
    sentence_total = max(len(cpu_sentence_boundaries), len(gpu_sentence_boundaries))
    sentence_same = _sequence_same_count(cpu_sentence_boundaries, gpu_sentence_boundaries) if sentence_total else 0
    metrics.append(_metric_payload("Sentences", sentence_same, sentence_total))
    sentence_token_total = max(len(cpu_sentence_sigs), len(gpu_sentence_sigs))
    sentence_token_same = _sequence_same_count(cpu_sentence_sigs, gpu_sentence_sigs) if sentence_token_total else 0
    metrics.append(_metric_payload("Sentence token sequences", sentence_token_same, sentence_token_total))

    cpu_token_texts: list[str] = []
    gpu_token_texts: list[str] = []
    cpu_word_texts: list[str] = []
    gpu_word_texts: list[str] = []
    mwt_same = 0
    mwt_total = 0
    field_counts: Dict[str, Dict[str, int]] = {
        "Morph feats": {"same": 0, "total": 0},
        "UPOS": {"same": 0, "total": 0},
        "XPOS": {"same": 0, "total": 0},
        "Dependency relations": {"same": 0, "total": 0},
        "Heads": {"same": 0, "total": 0},
        "NER tags": {"same": 0, "total": 0},
        "Lemmas": {"same": 0, "total": 0},
    }
    field_keys = [
        ("Morph feats", ["feats", "FEATS"]),
        ("UPOS", ["upos", "UPOS"]),
        ("XPOS", ["xpos", "XPOS"]),
        ("Dependency relations", ["deprel", "DEPREL"]),
        ("Heads", ["head", "HEAD"]),
        ("NER tags", ["ner", "NER"]),
        ("Lemmas", ["lemma", "LEMMA"]),
    ]

    for sentence in cpu_sentences:
        cpu_token_texts.extend(_token_text(token) for token in _sentence_tokens(sentence))
        cpu_word_texts.extend(_token_text(unit) for unit in _analysis_units(sentence))
    for sentence in gpu_sentences:
        gpu_token_texts.extend(_token_text(token) for token in _sentence_tokens(sentence))
        gpu_word_texts.extend(_token_text(unit) for unit in _analysis_units(sentence))

    for cpu_sent_index, gpu_sent_index in _matching_index_pairs(cpu_sentence_boundaries, gpu_sentence_boundaries):
        cpu_sentence = cpu_sentences[cpu_sent_index]
        gpu_sentence = gpu_sentences[gpu_sent_index]
        cpu_tokens = _sentence_tokens(cpu_sentence)
        gpu_tokens = _sentence_tokens(gpu_sentence)

        for token_index in range(min(len(cpu_tokens), len(gpu_tokens))):
            cpu_token = cpu_tokens[token_index]
            gpu_token = gpu_tokens[token_index]
            if _token_text(cpu_token) != _token_text(gpu_token):
                continue
            cpu_expanded = _expanded_texts(cpu_token)
            gpu_expanded = _expanded_texts(gpu_token)
            if cpu_expanded or gpu_expanded:
                mwt_total += 1
                if cpu_expanded == gpu_expanded:
                    mwt_same += 1

        cpu_units = _analysis_units(cpu_sentence)
        gpu_units = _analysis_units(gpu_sentence)
        for unit_index in range(min(len(cpu_units), len(gpu_units))):
            cpu_unit = cpu_units[unit_index]
            gpu_unit = gpu_units[unit_index]
            if _token_text(cpu_unit) != _token_text(gpu_unit):
                continue
            for label, keys in field_keys:
                cpu_value = _first_value(cpu_unit, keys)
                gpu_value = _first_value(gpu_unit, keys)
                if cpu_value is None and gpu_value is None:
                    continue
                field_counts[label]["total"] += 1
                if cpu_value == gpu_value:
                    field_counts[label]["same"] += 1

    token_total = max(len(cpu_token_texts), len(gpu_token_texts))
    token_same = _sequence_same_count(cpu_token_texts, gpu_token_texts) if token_total else 0
    word_total = max(len(cpu_word_texts), len(gpu_word_texts))
    word_same = _sequence_same_count(cpu_word_texts, gpu_word_texts) if word_total else 0
    metrics.append(_metric_payload("Tokens", token_same, token_total))
    metrics.append(_metric_payload("Analysis units", word_same, word_total))
    metrics.append(_metric_payload("MWT expansions", mwt_same, mwt_total))
    for label in [
        "UPOS",
        "XPOS",
        "Morph feats",
        "Dependency relations",
        "Heads",
        "NER tags",
        "Lemmas",
    ]:
        row = field_counts[label]
        metrics.append(_metric_payload(label, row["same"], row["total"]))

    text = "\n".join(_metric_line(metric) for metric in metrics)
    return {
        "match": bool(cpu_fingerprint == gpu_fingerprint),
        "diff_count": sum(int(metric["diff"]) for metric in metrics),
        "truncated": False,
        "metrics": metrics,
        "text": text,
    }


def _prepend_cpu_opt_deps() -> bool:
    if not os.path.isdir(CPU_OPT_DEPS_DIR):
        return False
    if CPU_OPT_DEPS_DIR not in sys.path:
        sys.path.insert(0, CPU_OPT_DEPS_DIR)
    return True


def _append_onnx_deps() -> Dict[str, Any]:
    report = {"active": False, "path": "", "candidates": list(ONNX_DEPS_DIRS)}
    errors = []
    for path in ONNX_DEPS_DIRS:
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


def _read_cpu_opt_selection_cache() -> Optional[Dict[str, Any]]:
    try:
        with open(CPU_OPT_SELECTION_CACHE_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return None
    if not isinstance(data, dict):
        return None
    if data.get("cache_version") != CPU_OPT_SELECTION_CACHE_VERSION:
        return None
    profile = str(data.get("selected_profile") or "")
    thread_count = data.get("selected_thread_count")
    tok_batch_size = data.get("selected_tok_batch_size")
    tag_batch_size = data.get("selected_tag_batch_size")
    if not profile or not isinstance(thread_count, int):
        return None
    if not isinstance(tok_batch_size, int) or not isinstance(tag_batch_size, int):
        return None
    if profile != CPU_OPT_PROFILE_NAME:
        return None
    if data.get("output_match") is False:
        return None
    data["from_cache"] = True
    data["cache_path"] = CPU_OPT_SELECTION_CACHE_PATH
    return data


def _write_cpu_opt_selection_cache(selection: Dict[str, Any]) -> None:
    os.makedirs(CPU_OPT_CACHE_DIR, exist_ok=True)
    payload = {
        "cache_version": CPU_OPT_SELECTION_CACHE_VERSION,
        "created_at": time.time(),
        "selected_profile": str(selection.get("selected_profile") or CPU_OPT_PROFILE_NAME),
        "selected_thread_count": int(selection.get("selected_thread_count") or 1),
        "selected_tok_batch_size": int(selection.get("selected_tok_batch_size") or CPU_OPT_DEFAULT_TOK_BATCH_SIZE),
        "selected_tag_batch_size": int(selection.get("selected_tag_batch_size") or CPU_OPT_DEFAULT_TAG_BATCH_SIZE),
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
        "deps_path": CPU_OPT_DEPS_DIR,
        "module_cache_dir": CPU_OPT_CACHE_DIR,
    }
    with open(CPU_OPT_SELECTION_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)


def _default_cpu_opt_selection() -> Dict[str, Any]:
    candidates = _cpu_thread_candidates()
    thread_count = max(candidates) if candidates else 1
    return {
        "ok": True,
        "selected_profile": CPU_OPT_PROFILE_NAME,
        "selected_thread_count": thread_count,
        "selected_tok_batch_size": CPU_OPT_DEFAULT_TOK_BATCH_SIZE,
        "selected_tag_batch_size": CPU_OPT_DEFAULT_TAG_BATCH_SIZE,
        "selected_elapsed_seconds": None,
        "baseline_fingerprint": "",
        "selected_fingerprint": "",
        "output_match": None,
        "setup_seconds": 0.0,
        "deps_path": CPU_OPT_DEPS_DIR,
        "module_cache_dir": CPU_OPT_CACHE_DIR,
        "from_default": True,
        "reason": "No cached CPU optimization selection was found; using PyTorch XLM-R base dynamic INT8 as the default CPU profile.",
    }


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
    for key in ["OMP_NUM_THREADS", "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS", "NUMEXPR_NUM_THREADS"]:
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
        engines = list(getattr(torch_module.backends.quantized, "supported_engines", []))
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


def _configure_gpu_torch_backend(torch_module: Any) -> Dict[str, Any]:
    report: Dict[str, Any] = {"profile": GPU_OPT_PROFILE_NAME}
    try:
        cuda_backends = getattr(getattr(torch_module, "backends", None), "cuda", None)
        matmul_backend = getattr(cuda_backends, "matmul", None)
        if matmul_backend is not None and hasattr(matmul_backend, "allow_tf32"):
            matmul_backend.allow_tf32 = True
            report["cuda_matmul_allow_tf32"] = bool(matmul_backend.allow_tf32)
    except Exception as exc:
        report["cuda_matmul_allow_tf32_error"] = str(exc)
    try:
        cudnn_backend = getattr(getattr(torch_module, "backends", None), "cudnn", None)
        if cudnn_backend is not None and hasattr(cudnn_backend, "allow_tf32"):
            cudnn_backend.allow_tf32 = True
            report["cudnn_allow_tf32"] = bool(cudnn_backend.allow_tf32)
    except Exception as exc:
        report["cudnn_allow_tf32_error"] = str(exc)
    try:
        report["cuda_available"] = bool(torch_module.cuda.is_available())
        if report["cuda_available"]:
            report["device_name"] = str(torch_module.cuda.get_device_name(0))
    except Exception as exc:
        report["cuda_probe_error"] = str(exc)
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
            report["reason"] = "No reliable Windows CPU BF16 feature probe was available in this Torch build."
            return report
        flags = ""
        with open("/proc/cpuinfo", encoding="utf-8", errors="ignore") as f:
            flags = f.read().lower()
        supported = "avx512_bf16" in flags or "amx_bf16" in flags
        report["supported"] = supported
        report["reason"] = "CPU flags include BF16 support" if supported else "CPU flags do not include avx512_bf16 or amx_bf16"
        return report
    except Exception as exc:
        report["reason"] = "BF16 support probe failed"
        report["error"] = str(exc)
        return report


def _sequence_bucket_for_token_count(token_count: Any) -> int:
    try:
        count = max(0, int(token_count))
    except Exception:
        count = 0
    for bucket in CPU_OPT_SEQUENCE_BUCKETS:
        if count <= bucket:
            return bucket
    return CPU_OPT_SEQUENCE_BUCKETS[-1]


def _pipeline_eval_status(pipeline_obj: Any) -> Dict[str, Any]:
    embedding = getattr(pipeline_obj, "_embedding_layers", None)
    xlmr = getattr(embedding, "xlmr", None)
    return {
        "embedding_eval": bool(embedding is not None and not bool(getattr(embedding, "training", True))),
        "xlmr_eval": bool(xlmr is not None and not bool(getattr(xlmr, "training", True))),
    }


def _module_dtype_summary(name: str, module: Any) -> Dict[str, Any]:
    summary: Dict[str, Any] = {"name": name, "present": module is not None, "parameter_count": 0, "dtype_counts": {}}
    if module is None or not hasattr(module, "parameters"):
        summary["all_float_params_fp16"] = False
        return summary
    dtype_counts: Dict[str, int] = {}
    float_param_count = 0
    fp16_param_count = 0
    try:
        for param in module.parameters():
            count = int(param.numel())
            dtype_name = str(param.dtype)
            dtype_counts[dtype_name] = dtype_counts.get(dtype_name, 0) + count
            summary["parameter_count"] += count
            if dtype_name.startswith("torch.float"):
                float_param_count += count
                if dtype_name == "torch.float16":
                    fp16_param_count += count
    except Exception as exc:
        summary["error"] = str(exc)
    summary["dtype_counts"] = dtype_counts
    summary["float_parameter_count"] = float_param_count
    summary["fp16_parameter_count"] = fp16_param_count
    summary["all_float_params_fp16"] = bool(float_param_count > 0 and fp16_param_count == float_param_count)
    return summary


def _named_parameter_dtype_summary(name: str, module: Any, path_token: str) -> Dict[str, Any]:
    summary: Dict[str, Any] = {
        "name": name,
        "path_token": path_token,
        "parameter_count": 0,
        "dtype_counts": {},
        "all_float_params_fp16": False,
    }
    if module is None or not hasattr(module, "named_parameters"):
        return summary
    token = str(path_token).lower()
    dtype_counts: Dict[str, int] = {}
    float_param_count = 0
    fp16_param_count = 0
    try:
        for param_name, param in module.named_parameters():
            if token not in str(param_name).lower():
                continue
            count = int(param.numel())
            dtype_name = str(param.dtype)
            dtype_counts[dtype_name] = dtype_counts.get(dtype_name, 0) + count
            summary["parameter_count"] += count
            if dtype_name.startswith("torch.float"):
                float_param_count += count
                if dtype_name == "torch.float16":
                    fp16_param_count += count
    except Exception as exc:
        summary["error"] = str(exc)
    summary["dtype_counts"] = dtype_counts
    summary["float_parameter_count"] = float_param_count
    summary["fp16_parameter_count"] = fp16_param_count
    summary["all_float_params_fp16"] = bool(float_param_count > 0 and fp16_param_count == float_param_count)
    return summary


def _gpu_fp16_coverage_report(pipeline_obj: Any) -> Dict[str, Any]:
    embedding = getattr(pipeline_obj, "_embedding_layers", None)
    xlmr = getattr(embedding, "xlmr", None)
    modules: list[Dict[str, Any]] = [
        _module_dtype_summary("embedding_layers", embedding),
        _module_dtype_summary("xlmr", xlmr),
        _named_parameter_dtype_summary("xlmr_adapters", xlmr, "adapter"),
    ]
    for attr_name, label in [
        ("_tokenizer", "tokenizer"),
        ("_tagger", "tagger"),
        ("_ner_model", "ner"),
    ]:
        module_map = getattr(pipeline_obj, attr_name, {}) or {}
        if isinstance(module_map, dict):
            for key, module in module_map.items():
                modules.append(_module_dtype_summary(f"{label}.{key}", module))
    for name, model in _iter_seq2seq_models(pipeline_obj):
        modules.append(_module_dtype_summary(name, model))
    checked = [row for row in modules if row.get("present")]
    return {
        "module_count": len(checked),
        "all_checked_float_params_fp16": bool(checked and all(row.get("all_float_params_fp16") for row in checked if row.get("float_parameter_count"))),
        "modules": modules,
    }


def _hidden_states_disabled_status(module: Any) -> Dict[str, Any]:
    checked = 0
    enabled = 0
    try:
        iterator = module.modules()
    except Exception:
        iterator = [module]
    for child in iterator:
        if hasattr(child, "output_hidden_states"):
            checked += 1
            try:
                if bool(getattr(child, "output_hidden_states")):
                    enabled += 1
            except Exception:
                pass
        config = getattr(child, "config", None)
        if config is not None and hasattr(config, "output_hidden_states"):
            checked += 1
            try:
                if bool(getattr(config, "output_hidden_states")):
                    enabled += 1
            except Exception:
                pass
    return {
        "checked_attrs": checked,
        "enabled_attrs": enabled,
        "disabled": enabled == 0,
    }


@contextmanager
def _temporary_no_gc_collect():
    real_collect = gc.collect
    calls = {"count": 0}

    def fake_collect(*args: Any, **kwargs: Any) -> int:
        calls["count"] += 1
        return 0

    gc.collect = fake_collect
    try:
        yield calls
    finally:
        gc.collect = real_collect


@contextmanager
def _temporary_no_cuda_empty_cache(torch_module: Any):
    calls = {"count": 0}
    cuda_obj = getattr(torch_module, "cuda", None) if torch_module is not None else None
    real_empty_cache = getattr(cuda_obj, "empty_cache", None) if cuda_obj is not None else None
    if real_empty_cache is None:
        yield calls
        return

    def fake_empty_cache(*args: Any, **kwargs: Any) -> None:
        calls["count"] += 1
        return None

    cuda_obj.empty_cache = fake_empty_cache
    try:
        yield calls
    finally:
        cuda_obj.empty_cache = real_empty_cache


@contextmanager
def _temporary_tensor_sync_point_counter(torch_module: Any):
    tensor_cls = getattr(torch_module, "Tensor", None) if torch_module is not None else None
    if tensor_cls is None:
        yield {"available": False, "calls": {}}
        return

    method_names = ["cpu", "numpy", "tolist", "item"]
    originals: Dict[str, Any] = {}
    calls: Dict[str, Dict[str, Any]] = {
        name: {"count": 0, "elapsed_seconds": 0.0}
        for name in method_names
    }

    def make_wrapper(method_name: str, original: Any):
        def wrapped(self: Any, *args: Any, **kwargs: Any):
            started = time.perf_counter()
            try:
                return original(self, *args, **kwargs)
            finally:
                row = calls[method_name]
                row["count"] = int(row.get("count") or 0) + 1
                row["elapsed_seconds"] = float(row.get("elapsed_seconds") or 0.0) + (time.perf_counter() - started)

        return wrapped

    patch_errors: Dict[str, str] = {}
    try:
        for name in method_names:
            original = getattr(tensor_cls, name, None)
            if original is None:
                continue
            originals[name] = original
            try:
                setattr(tensor_cls, name, make_wrapper(name, original))
            except Exception as exc:
                patch_errors[name] = str(exc)
        yield {"available": True, "calls": calls, "patch_errors": patch_errors}
    finally:
        for name, original in originals.items():
            try:
                setattr(tensor_cls, name, original)
            except Exception:
                pass


@contextmanager
def _torch_cpu_inference_context(torch_module: Any, use_bf16_autocast: bool):
    with ExitStack() as stack:
        if hasattr(torch_module, "inference_mode"):
            stack.enter_context(torch_module.inference_mode())
        if use_bf16_autocast and hasattr(torch_module, "autocast"):
            stack.enter_context(torch_module.autocast("cpu", dtype=torch_module.bfloat16))
        yield


@contextmanager
def _temporary_trankit_task_breakdown(pipeline_obj: Any, torch_module: Any, use_gpu: bool, registry_module: Any = None):
    method_to_stage = {
        "_tokenize_doc": "tokenization",
        "_mwt_expand": "mwt_expansion",
        "_posdep_doc": "posdep_tagging",
        "_lemmatize_doc": "lemmatization",
        "_ner_doc": "ner",
    }
    stage_order = [
        "tokenization",
        "mwt_expansion",
        "posdep_tagging",
        "lemmatization",
        "ner",
    ]
    rows: Dict[str, Dict[str, Any]] = {
        name: {
            "count": 0,
            "elapsed_seconds": 0.0,
            "exclusive_seconds": 0.0,
            "nested_seconds": 0.0,
            "errors": 0,
            "batch_count": 0,
            "batch_items": 0,
            "batch_min_items": None,
            "batch_max_items": None,
            "batch_padded_units": 0,
            "batch_real_units": 0,
            "batch_padding_units": 0,
            "batch_padding_details": [],
            "batch_max_padded_length": None,
            "xlm_call_count": 0,
            "xlm_call_seconds": 0.0,
            "head_call_count": 0,
            "head_call_seconds": 0.0,
            "seq2seq_call_count": 0,
            "seq2seq_call_seconds": 0.0,
            "model_call_seconds": 0.0,
        }
        for name in stage_order
    }
    report: Dict[str, Any] = {
        "available": pipeline_obj is not None,
        "uses_cuda_sync": bool(use_gpu),
        "stages": rows,
    }
    if pipeline_obj is None:
        yield report
        return

    originals: Dict[str, Any] = {}
    module_originals: Dict[str, Any] = {}
    method_originals: list[tuple[Any, str, Any]] = []
    patched_method_keys: set[tuple[int, str]] = set()
    stack: list[Dict[str, Any]] = []

    def current_stage() -> Optional[str]:
        if not stack:
            return None
        stage = stack[-1].get("stage")
        return str(stage) if stage in rows else None

    def safe_len(value: Any) -> Optional[int]:
        try:
            return int(len(value))
        except Exception:
            return None

    def safe_dim(value: Any, index: int) -> Optional[int]:
        try:
            if hasattr(value, "size"):
                return int(value.size(index))
        except Exception:
            pass
        try:
            shape = getattr(value, "shape", None)
            if shape is not None and len(shape) > index:
                return int(shape[index])
        except Exception:
            pass
        return None

    def infer_batch_shape(args: tuple[Any, ...]) -> tuple[Optional[int], Optional[int], Optional[int]]:
        if not args:
            return None, None, None
        batch = args[0]
        item_count: Optional[int] = None
        padded_length: Optional[int] = None
        real_units: Optional[int] = None

        for attr in ("word_num", "wordpiece_num", "paragraph_index", "sent_index"):
            value = getattr(batch, attr, None)
            item_count = safe_len(value)
            if item_count is not None:
                break

        wordpieces = getattr(batch, "wordpieces", None)
        if isinstance(wordpieces, list):
            try:
                real_units = sum(len(item) + 2 for item in wordpieces if isinstance(item, list))
            except Exception:
                real_units = None

        word_lens = getattr(batch, "word_lens", None)
        if real_units is None and isinstance(word_lens, list):
            try:
                real_units = sum(sum(int(length) for length in item) + 2 for item in word_lens if isinstance(item, list))
            except Exception:
                real_units = None

        piece_idxs = getattr(batch, "piece_idxs", None)
        if piece_idxs is not None:
            if item_count is None:
                item_count = safe_dim(piece_idxs, 0)
            padded_length = safe_dim(piece_idxs, 1)

        if isinstance(batch, (tuple, list)) and batch:
            first = batch[0]
            if item_count is None:
                item_count = safe_dim(first, 0)
            padded_length = padded_length if padded_length is not None else safe_dim(first, 1)

        return item_count, padded_length, real_units

    def add_batch_stats(stage_name: str, kind: str, args: tuple[Any, ...], elapsed_seconds: float, count_as_batch: bool) -> None:
        row = rows.get(stage_name)
        if row is None:
            return
        call_count_key = f"{kind}_call_count"
        call_seconds_key = f"{kind}_call_seconds"
        row[call_count_key] = int(row.get(call_count_key) or 0) + 1
        row[call_seconds_key] = float(row.get(call_seconds_key) or 0.0) + elapsed_seconds
        row["model_call_seconds"] = float(row.get("model_call_seconds") or 0.0) + elapsed_seconds
        if not count_as_batch:
            return
        item_count, padded_length, real_units = infer_batch_shape(args)
        row["batch_count"] = int(row.get("batch_count") or 0) + 1
        batch_index = int(row.get("batch_count") or 0)
        if isinstance(item_count, int) and item_count >= 0:
            row["batch_items"] = int(row.get("batch_items") or 0) + item_count
            previous_min = row.get("batch_min_items")
            row["batch_min_items"] = item_count if previous_min is None else min(int(previous_min), item_count)
            previous_max = row.get("batch_max_items")
            row["batch_max_items"] = item_count if previous_max is None else max(int(previous_max), item_count)
        if isinstance(padded_length, int) and padded_length >= 0:
            previous_len = row.get("batch_max_padded_length")
            row["batch_max_padded_length"] = padded_length if previous_len is None else max(int(previous_len), padded_length)
            if isinstance(item_count, int) and item_count >= 0:
                padded_units = item_count * padded_length
                row["batch_padded_units"] = int(row.get("batch_padded_units") or 0) + padded_units
                detail: Dict[str, Any] = {
                    "index": batch_index,
                    "items": item_count,
                    "max_len": padded_length,
                    "padded_units": padded_units,
                }
                if isinstance(real_units, int) and real_units >= 0:
                    padding_units = max(0, padded_units - real_units)
                    row["batch_real_units"] = int(row.get("batch_real_units") or 0) + real_units
                    row["batch_padding_units"] = int(row.get("batch_padding_units") or 0) + padding_units
                    detail["real_units"] = real_units
                    detail["padding_units"] = padding_units
                details = row.get("batch_padding_details")
                if isinstance(details, list) and len(details) < 80:
                    details.append(detail)

    def patch_bound_method(obj: Any, method_name: str, kind: str, count_as_batch: bool) -> None:
        if obj is None:
            return
        key = (id(obj), method_name)
        if key in patched_method_keys:
            return
        original = getattr(obj, method_name, None)
        if original is None:
            return

        def wrapped(*args: Any, **kwargs: Any):
            stage_name = current_stage()
            started = time.perf_counter()
            try:
                return original(*args, **kwargs)
            finally:
                if stage_name:
                    add_batch_stats(stage_name, kind, args, time.perf_counter() - started, count_as_batch)

        try:
            setattr(obj, method_name, wrapped)
        except Exception:
            return
        patched_method_keys.add(key)
        method_originals.append((obj, method_name, original))

    def patch_model_call_counters() -> None:
        embedding_layers = getattr(pipeline_obj, "_embedding_layers", None)
        patch_bound_method(embedding_layers, "get_tokenizer_inputs", "xlm", True)
        patch_bound_method(embedding_layers, "get_tagger_inputs", "xlm", True)

        for model in (getattr(pipeline_obj, "_tokenizer", {}) or {}).values():
            patch_bound_method(model, "predict", "head", False)
        for model in (getattr(pipeline_obj, "_tagger", {}) or {}).values():
            patch_bound_method(model, "predict", "head", False)
        for model in (getattr(pipeline_obj, "_ner_model", {}) or {}).values():
            patch_bound_method(model, "predict", "head", False)

        for wrapper in (getattr(pipeline_obj, "_lemma_model", {}) or {}).values():
            patch_bound_method(getattr(wrapper, "model", None), "predict", "seq2seq", True)
        for wrapper in (getattr(pipeline_obj, "_mwt_model", {}) or {}).values():
            patch_bound_method(getattr(wrapper, "model", None), "predict", "seq2seq", True)

    @contextmanager
    def timed(stage_name: str):
        _sync_cuda(torch_module, use_gpu)
        frame = {"stage": stage_name, "nested_seconds": 0.0}
        stack.append(frame)
        started = time.perf_counter()
        ok = True
        try:
            yield
        except Exception:
            ok = False
            raise
        finally:
            _sync_cuda(torch_module, use_gpu)
            elapsed = time.perf_counter() - started
            current = stack.pop() if stack else frame
            nested = float(current.get("nested_seconds") or 0.0)
            exclusive = max(0.0, elapsed - nested)
            row = rows[stage_name]
            row["count"] = int(row.get("count") or 0) + 1
            row["elapsed_seconds"] = float(row.get("elapsed_seconds") or 0.0) + elapsed
            row["exclusive_seconds"] = float(row.get("exclusive_seconds") or 0.0) + exclusive
            row["nested_seconds"] = float(row.get("nested_seconds") or 0.0) + nested
            if not ok:
                row["errors"] = int(row.get("errors") or 0) + 1
            if stack:
                stack[-1]["nested_seconds"] = float(stack[-1].get("nested_seconds") or 0.0) + elapsed

    def make_wrapper(stage_name: str, original: Any):
        def wrapped(*args: Any, **kwargs: Any):
            with timed(stage_name):
                return original(*args, **kwargs)

        return wrapped

    try:
        for method_name, stage_name in method_to_stage.items():
            original = getattr(pipeline_obj, method_name, None)
            if original is None:
                continue
            originals[method_name] = original
            setattr(pipeline_obj, method_name, make_wrapper(stage_name, original))
        patch_model_call_counters()
        if registry_module is not None:
            helper_name = "_tokenize_manual_sentence_spans_batched"
            original = getattr(registry_module, helper_name, None)
            if original is not None:
                module_originals[helper_name] = original
                setattr(registry_module, helper_name, make_wrapper("tokenization", original))
        report["patched_methods"] = sorted(originals)
        yield report
    finally:
        for method_name, original in originals.items():
            try:
                setattr(pipeline_obj, method_name, original)
            except Exception:
                pass
        for method_name, original in module_originals.items():
            try:
                setattr(registry_module, method_name, original)
            except Exception:
                pass
        for obj, method_name, original in reversed(method_originals):
            try:
                setattr(obj, method_name, original)
            except Exception:
                pass


class StageRecorder:
    def __init__(self, torch_module: Any, use_gpu: bool):
        self.torch = torch_module
        self.use_gpu = use_gpu
        self.stages: list[Dict[str, Any]] = []

    @contextmanager
    def timed(self, name: str, **metadata: Any):
        _sync_cuda(self.torch, self.use_gpu)
        rss_before = current_rss_bytes()
        gpu_before = _gpu_snapshot(self.torch)
        started = time.perf_counter()
        ok = True
        error = ""
        try:
            yield
        except Exception as exc:
            ok = False
            error = str(exc)
            raise
        finally:
            _sync_cuda(self.torch, self.use_gpu)
            finished = time.perf_counter()
            rss_after = current_rss_bytes()
            gpu_after = _gpu_snapshot(self.torch)
            row: Dict[str, Any] = {
                "name": name,
                "ok": ok,
                "elapsed_seconds": finished - started,
                "rss_before_bytes": rss_before,
                "rss_after_bytes": rss_after,
                "rss_delta_bytes": _bytes_delta(rss_after, rss_before),
                "gpu_before": gpu_before,
                "gpu_after": gpu_after,
                "gpu_delta": _gpu_delta(gpu_after, gpu_before),
            }
            if metadata:
                row["metadata"] = metadata
            if error:
                row["error"] = error
            self.stages.append(row)


def _install_load_probe_instrumentation(use_gpu: bool, recorder: StageRecorder) -> None:
    import trankit  # type: ignore
    import trankit.pipeline as trankit_pipeline  # type: ignore

    real_pipeline = trankit.Pipeline
    real_download = trankit_pipeline.download

    def timed_download(*args: Any, **kwargs: Any):
        language = str(kwargs.get("language") or (args[1] if len(args) > 1 else ""))
        with recorder.timed("download_or_check_saved_model", language=language):
            return real_download(*args, **kwargs)

    trankit_pipeline.download = timed_download

    def timed_module_class(stage_prefix: str, original_class: Any):
        class TimedModule(original_class):  # type: ignore[misc, valid-type]
            def __init__(self, *args: Any, **kwargs: Any):
                with recorder.timed(f"{stage_prefix}.__init__"):
                    super().__init__(*args, **kwargs)

            def to(self, *args: Any, **kwargs: Any):
                with recorder.timed(f"{stage_prefix}.to_device"):
                    return super().to(*args, **kwargs)

            def half(self, *args: Any, **kwargs: Any):
                with recorder.timed(f"{stage_prefix}.half"):
                    return super().half(*args, **kwargs)

        return TimedModule

    def timed_wrapper_class(stage_prefix: str, original_class: Any):
        class TimedWrapper(original_class):  # type: ignore[misc, valid-type]
            def __init__(self, *args: Any, **kwargs: Any):
                with recorder.timed(f"{stage_prefix}.__init__"):
                    super().__init__(*args, **kwargs)

        return TimedWrapper

    trankit_pipeline.Multilingual_Embedding = timed_module_class(
        "shared_xlm_roberta_embedding",
        trankit_pipeline.Multilingual_Embedding,
    )
    trankit_pipeline.TokenizerClassifier = timed_module_class(
        "language_tokenizer_classifier",
        trankit_pipeline.TokenizerClassifier,
    )
    trankit_pipeline.PosDepClassifier = timed_module_class(
        "language_posdep_classifier",
        trankit_pipeline.PosDepClassifier,
    )
    trankit_pipeline.NERClassifier = timed_module_class(
        "language_ner_classifier",
        trankit_pipeline.NERClassifier,
    )
    trankit_pipeline.MWTWrapper = timed_wrapper_class(
        "language_mwt_wrapper",
        trankit_pipeline.MWTWrapper,
    )
    trankit_pipeline.LemmaWrapper = timed_wrapper_class(
        "language_lemma_wrapper",
        trankit_pipeline.LemmaWrapper,
    )

    original_pipeline_init = real_pipeline.__init__
    original_setup_config = real_pipeline._setup_config
    original_load_vocabs = real_pipeline._load_vocabs
    original_add = real_pipeline.add

    def forced_timed_pipeline_init(self, *args: Any, **kwargs: Any):
        kwargs["gpu"] = use_gpu
        with recorder.timed("pipeline_constructor_total"):
            return original_pipeline_init(self, *args, **kwargs)

    def timed_setup_config(self, lang: str):
        with recorder.timed("pipeline_setup_config", lang=lang):
            return original_setup_config(self, lang)

    def timed_load_vocabs(self):
        with recorder.timed("pipeline_load_vocabs"):
            return original_load_vocabs(self)

    def timed_add(self, lang: str):
        with recorder.timed("pipeline_add_language_total", lang=lang):
            return original_add(self, lang)

    real_pipeline.__init__ = forced_timed_pipeline_init
    real_pipeline._setup_config = timed_setup_config
    real_pipeline._load_vocabs = timed_load_vocabs
    real_pipeline.add = timed_add
    trankit.Pipeline = real_pipeline
    trankit_pipeline.Pipeline = real_pipeline


def _register_single_language_for_probe(lr: Any, lang_code: str) -> Dict[str, Any]:
    from pathlib import Path

    from trankit.models.lemma_model import LemmaWrapper
    from trankit.utils.tbinfo import (
        lang2treebank,
        langwithner,
        supported_langs,
        tbname2max_input_length,
        tbname2training_id,
        treebank2lang,
    )

    info = lr.LANGUAGE_REGISTRY[lang_code]
    name = info["trankit_name"]
    treebank = info.get("trankit_treebank")

    if treebank and name and name not in supported_langs:
        supported_langs.add(name) if isinstance(supported_langs, set) else supported_langs.append(name)
    if treebank and name:
        lang2treebank[name] = treebank
        if info.get("has_ner", False) and name not in langwithner:
            langwithner.add(name) if isinstance(langwithner, set) else langwithner.append(name)
        if treebank not in treebank2lang:
            treebank2lang[treebank] = name
        if treebank not in tbname2training_id:
            tbname2training_id[treebank] = 1 if info.get("has_mwt", False) else 0
        tbname2max_input_length[treebank] = 512

    if lang_code == "ar" and treebank:
        tbname2training_id[treebank] = 1

    if info.get("identity_lemma") and treebank:
        original_init = LemmaWrapper.__init__
        original_predict = LemmaWrapper.predict

        def patched_lemma_init(self, config: Any, treebank_name: str, use_gpu: bool, evaluate: bool = True):
            self._identity_lemma_runtime = False
            if evaluate and treebank_name == treebank:
                language = treebank2lang[treebank_name]
                model_path = Path(config._cache_dir) / config.embedding_name / language / f"{language}_lemmatizer.pt"
                if model_path.exists():
                    return original_init(self, config, treebank_name, use_gpu, evaluate)
                from trankit.models.lemma_model import get_identity_lemma_model

                self.config = config
                self.treebank_name = treebank_name
                self.args = get_identity_lemma_model()
                self._identity_lemma_runtime = True
                print("Loading lemmatizer for {}".format(treebank2lang[treebank_name]))
                return
            return original_init(self, config, treebank_name, use_gpu, evaluate)

        def patched_lemma_predict(self, tagged_doc: Any, obmit_tag: Any):
            if getattr(self, "_identity_lemma_runtime", False):
                from trankit.models.lemma_model import set_lemma
                from trankit.utils.conll import ID, TEXT, TOKENS

                preds = [
                    t[TEXT]
                    for sentence in tagged_doc
                    for t in sentence[TOKENS]
                    if type(t[ID]) == int or len(t[ID]) == 1
                ]
                return set_lemma(tagged_doc, preds, obmit_tag)
            return original_predict(self, tagged_doc, obmit_tag)

        LemmaWrapper.__init__ = patched_lemma_init
        LemmaWrapper.predict = patched_lemma_predict

    return info


def _load_probe_worker_main(
    mode: str,
    device_label: str,
    use_gpu: bool,
    raw_lang: str,
    result_queue: mp.Queue,
) -> None:
    torch_module = None
    pid = os.getpid()
    total_started = time.perf_counter()
    rss_process_start = current_rss_bytes()
    recorder: Optional[StageRecorder] = None
    try:
        _force_gc()

        import torch  # type: ignore

        torch_module = torch
        if use_gpu and torch_module.cuda.is_available():
            torch_module.cuda.empty_cache()
            torch_module.cuda.reset_peak_memory_stats()
            torch_module.cuda.synchronize()

        recorder = StageRecorder(torch_module, use_gpu)
        with recorder.timed("install_trankit_load_instrumentation"):
            _install_load_probe_instrumentation(use_gpu, recorder)

        with recorder.timed("import_language_registry"):
            import language_registry as lr

        resolved_lang = lr.resolve_lang_code(raw_lang) or str(raw_lang or "").strip().lower()
        if not resolved_lang or resolved_lang not in lr.LANGUAGE_REGISTRY:
            raise ValueError(f"Unsupported language: {raw_lang}")

        pipeline_obj = None
        if mode == "full":
            with recorder.timed("full_language_registry_init_trankit_total"):
                lr.init_trankit()
            pipeline_obj = getattr(lr, "_trankit_pipeline", None)
        elif mode == "single_lang":
            with recorder.timed("single_language_metadata_patch", lang=resolved_lang):
                info = _register_single_language_for_probe(lr, resolved_lang)
            from trankit import Pipeline  # type: ignore

            trankit_name = info["trankit_name"]
            cache_dir = info.get("trankit_cache_dir")
            with recorder.timed(
                "single_language_pipeline_load_total",
                lang=resolved_lang,
                trankit_name=trankit_name,
                has_custom_cache=bool(cache_dir),
            ):
                if cache_dir:
                    pipeline_obj = Pipeline(lang=trankit_name, cache_dir=cache_dir)
                else:
                    pipeline_obj = Pipeline(trankit_name)
        else:
            raise ValueError(f"Unsupported load probe mode: {mode}")

        _sync_cuda(torch_module, use_gpu)
        _force_gc()
        rss_after = current_rss_bytes()
        gpu_after = _gpu_snapshot(torch_module)
        actual_device = ""
        actual_use_gpu = None
        added_langs = []
        if pipeline_obj is not None:
            try:
                actual_device = str(pipeline_obj._config.device)
                actual_use_gpu = bool(pipeline_obj._use_gpu)
                added_langs = list(getattr(pipeline_obj, "added_langs", []) or [])
            except Exception:
                pass

        result_queue.put({
            "ok": True,
            "mode": mode,
            "device": device_label,
            "requested_gpu": use_gpu,
            "pid": pid,
            "lang": resolved_lang,
            "actual_device": actual_device,
            "actual_use_gpu": actual_use_gpu,
            "added_langs": added_langs,
            "total_elapsed_seconds": time.perf_counter() - total_started,
            "rss_process_start_bytes": rss_process_start,
            "rss_after_load_bytes": rss_after,
            "rss_total_delta_bytes": _bytes_delta(rss_after, rss_process_start),
            "gpu_after_load": gpu_after,
            "stages": recorder.stages,
        })
    except Exception as exc:
        _sync_cuda(torch_module, use_gpu)
        _force_gc()
        result_queue.put({
            "ok": False,
            "mode": mode,
            "device": device_label,
            "requested_gpu": use_gpu,
            "pid": pid,
            "total_elapsed_seconds": time.perf_counter() - total_started,
            "rss_process_start_bytes": rss_process_start,
            "rss_after_load_bytes": current_rss_bytes(),
            "gpu_after_load": _gpu_snapshot(torch_module),
            "stages": recorder.stages if recorder is not None else [],
            "error": str(exc),
            "traceback": traceback.format_exc(),
        })


def run_load_probe_process(mode: str, device_label: str, use_gpu: bool, raw_lang: str) -> Dict[str, Any]:
    ctx = mp.get_context("spawn")
    result_queue = ctx.Queue()
    started = time.perf_counter()
    process = ctx.Process(
        target=_load_probe_worker_main,
        args=(mode, device_label, use_gpu, raw_lang, result_queue),
        daemon=False,
    )
    process.start()
    try:
        result = result_queue.get(timeout=LOAD_PROBE_TIMEOUT_SECONDS)
    except queue.Empty:
        result = {
            "ok": False,
            "mode": mode,
            "device": device_label,
            "requested_gpu": use_gpu,
            "pid": process.pid,
            "error": "load probe timed out",
        }
    finally:
        process.join(timeout=5)
        if process.is_alive():
            process.terminate()
    if isinstance(result, dict):
        result["probe_process_wall_seconds"] = time.perf_counter() - started
        result["exitcode"] = process.exitcode
    return result


def _patch_trankit_pipeline_device(use_gpu: bool) -> None:
    import trankit  # type: ignore

    original_init = trankit.Pipeline.__init__

    def patched_init(self, *args: Any, **kwargs: Any):
        kwargs["gpu"] = use_gpu
        return original_init(self, *args, **kwargs)

    trankit.Pipeline.__init__ = patched_init


def _cold_start_worker_main(
    mode: str,
    device_label: str,
    use_gpu: bool,
    raw_lang: str,
    warmup_text: str,
    result_queue: mp.Queue,
) -> None:
    pid = os.getpid()
    torch_module = None
    stages: list[Dict[str, Any]] = []
    started = time.perf_counter()

    @contextmanager
    def timed_stage(name: str, **metadata: Any):
        _sync_cuda(torch_module, use_gpu)
        rss_before = current_rss_bytes()
        gpu_before = _gpu_snapshot(torch_module)
        stage_started = time.perf_counter()
        ok = True
        error = ""
        try:
            yield
        except Exception as exc:
            ok = False
            error = str(exc)
            raise
        finally:
            _sync_cuda(torch_module, use_gpu)
            rss_after = current_rss_bytes()
            gpu_after = _gpu_snapshot(torch_module)
            row: Dict[str, Any] = {
                "name": name,
                "ok": ok,
                "elapsed_seconds": time.perf_counter() - stage_started,
                "rss_before_bytes": rss_before,
                "rss_after_bytes": rss_after,
                "rss_delta_bytes": _bytes_delta(rss_after, rss_before),
                "gpu_before": gpu_before,
                "gpu_after": gpu_after,
                "gpu_delta": _gpu_delta(gpu_after, gpu_before),
            }
            if metadata:
                row["metadata"] = metadata
            if error:
                row["error"] = error
            stages.append(row)

    try:
        rss_process_start = current_rss_bytes()
        gpu_process_start = _gpu_snapshot(None)

        with timed_stage("import_torch"):
            import torch  # type: ignore

            torch_module = torch
            if use_gpu and torch_module.cuda.is_available():
                torch_module.cuda.empty_cache()
                torch_module.cuda.reset_peak_memory_stats()
                torch_module.cuda.synchronize()
            gpu_process_start = _gpu_snapshot(torch_module)

        with timed_stage("import_trankit_and_force_device"):
            _patch_trankit_pipeline_device(use_gpu)

        with timed_stage("import_language_registry"):
            import language_registry as lr

        resolved_lang = lr.resolve_lang_code(raw_lang) or str(raw_lang or "").strip().lower()
        if not resolved_lang or resolved_lang not in lr.LANGUAGE_REGISTRY:
            raise ValueError(f"Unsupported language: {raw_lang}")

        pipeline_obj = None
        loaded_description = ""
        if mode == "xlm_only":
            with timed_stage("select_cache_dir_for_xlm_only", lang=resolved_lang):
                info = lr.LANGUAGE_REGISTRY[resolved_lang]
                cache_dir = info.get("trankit_cache_dir") or os.path.join("cache", "trankit")

            with timed_stage("load_shared_xlm_only", lang=resolved_lang, has_custom_cache=bool(info.get("trankit_cache_dir"))):
                from trankit.adapter_transformers import XLMRobertaTokenizer  # type: ignore
                from trankit.config import config as master_config  # type: ignore
                from trankit.models.base_models import Multilingual_Embedding  # type: ignore

                master_config.embedding_name = "xlm-roberta-base"
                master_config._cache_dir = cache_dir
                master_config.device = torch_module.device(
                    "cuda" if use_gpu and torch_module.cuda.is_available() else "cpu"
                )
                master_config.wordpiece_splitter = XLMRobertaTokenizer.from_pretrained(
                    master_config.embedding_name,
                    cache_dir=os.path.join(master_config._cache_dir, master_config.embedding_name),
                )
                pipeline_obj = Multilingual_Embedding(master_config)
                pipeline_obj.to(master_config.device)
                if use_gpu and torch_module.cuda.is_available():
                    pipeline_obj.half()
                pipeline_obj.eval()
            loaded_description = "Shared XLM-R tokenizer/model only. No Trankit language modules are loaded."
        elif mode == "full":
            loaded_description = "Full all-language app Trankit pipeline via language_registry.init_trankit()."
            with timed_stage("load_full_app_trankit_pipeline"):
                lr.init_trankit()
            pipeline_obj = getattr(lr, "_trankit_pipeline", None)
        elif mode == "lang_modules":
            loaded_description = "Selected language-specific Trankit modules only. Shared XLM-R is not loaded."
            with timed_stage("register_selected_language_metadata", lang=resolved_lang):
                info = _register_single_language_for_probe(lr, resolved_lang)

            with timed_stage("load_selected_language_modules", lang=resolved_lang):
                from collections import defaultdict

                from trankit.config import config as master_config  # type: ignore
                from trankit.models.classifiers import NERClassifier, PosDepClassifier, TokenizerClassifier  # type: ignore
                from trankit.models.lemma_model import LemmaWrapper  # type: ignore
                from trankit.models.mwt_model import MWTWrapper  # type: ignore
                from trankit.utils.conll import DEPREL, FEATS, UPOS, XPOS  # type: ignore
                from trankit.utils.tbinfo import lang2treebank, langwithner, tbname2training_id, treebank2lang  # type: ignore

                trankit_name = info["trankit_name"]
                treebank_name = lang2treebank[trankit_name]
                cache_dir = info.get("trankit_cache_dir") or os.path.join("cache", "trankit")
                model_lang = trankit_name
                vocab_lang = treebank2lang.get(treebank_name) or trankit_name
                use_gpu_actual = bool(use_gpu and torch_module.cuda.is_available())

                master_config.embedding_name = "xlm-roberta-base"
                master_config._cache_dir = cache_dir
                master_config.device = torch_module.device("cuda" if use_gpu_actual else "cpu")
                master_config.training = False
                master_config.vocabs = {}
                master_config.ner_vocabs = {}
                master_config.itos = defaultdict(dict)

                vocab_path = os.path.join(
                    master_config._cache_dir,
                    master_config.embedding_name,
                    model_lang,
                    f"{model_lang}.vocabs.json",
                )
                if not os.path.exists(vocab_path):
                    vocab_path = os.path.join(
                        master_config._cache_dir,
                        master_config.embedding_name,
                        vocab_lang,
                        f"{vocab_lang}.vocabs.json",
                    )
                with open(vocab_path, encoding="utf-8") as f:
                    vocabs = json.load(f)
                master_config.vocabs[treebank_name] = vocabs
                master_config.itos[trankit_name][UPOS] = {v: k for k, v in vocabs[UPOS].items()}
                master_config.itos[trankit_name][XPOS] = {v: k for k, v in vocabs[XPOS].items()}
                master_config.itos[trankit_name][FEATS] = {v: k for k, v in vocabs[FEATS].items()}
                master_config.itos[trankit_name][DEPREL] = {v: k for k, v in vocabs[DEPREL].items()}

                if trankit_name in langwithner:
                    ner_vocab_path = os.path.join(
                        master_config._cache_dir,
                        master_config.embedding_name,
                        trankit_name,
                        f"{trankit_name}.ner-vocab.json",
                    )
                    with open(ner_vocab_path, encoding="utf-8") as f:
                        master_config.ner_vocabs[trankit_name] = json.load(f)

                tokenizer = TokenizerClassifier(master_config, treebank_name=treebank_name)
                tokenizer.to(master_config.device)
                if use_gpu_actual:
                    tokenizer.half()
                tokenizer.eval()

                tagger = PosDepClassifier(master_config, treebank_name=treebank_name)
                tagger.to(master_config.device)
                if use_gpu_actual:
                    tagger.half()
                tagger.eval()

                mwt_model = None
                if tbname2training_id[treebank_name] % 2 == 1:
                    mwt_model = MWTWrapper(master_config, treebank_name=treebank_name, use_gpu=use_gpu_actual)

                lemma_model = LemmaWrapper(master_config, treebank_name=treebank_name, use_gpu=use_gpu_actual)

                ner_model = None
                if trankit_name in langwithner:
                    ner_model = NERClassifier(master_config, trankit_name)
                    ner_model.to(master_config.device)
                    if use_gpu_actual:
                        ner_model.half()
                    ner_model.eval()

                pipeline_obj = {
                    "tokenizer": tokenizer,
                    "tagger": tagger,
                    "mwt": mwt_model,
                    "lemma": lemma_model,
                    "ner": ner_model,
                    "trankit_name": trankit_name,
                    "device": str(master_config.device),
                    "use_gpu": use_gpu_actual,
                }
        else:
            raise ValueError(f"Unsupported cold-start probe mode: {mode}")

        first_inference_doc = None
        if warmup_text.strip() and mode != "xlm_only" and mode != "lang_modules":
            if mode == "full":
                with timed_stage("first_inference_after_cold_load", lang=resolved_lang, chars=len(warmup_text)):
                    first_inference_doc = lr.run_trankit(warmup_text, resolved_lang)

        _sync_cuda(torch_module, use_gpu)
        _force_gc()
        rss_after = current_rss_bytes()
        gpu_after = _gpu_snapshot(torch_module)
        actual_device = ""
        actual_use_gpu = None
        added_langs = []
        if mode == "xlm_only" and pipeline_obj is not None:
            actual_device = str(getattr(getattr(pipeline_obj, "config", None), "device", ""))
            actual_use_gpu = "cuda" in actual_device
        elif mode == "lang_modules" and isinstance(pipeline_obj, dict):
            actual_device = str(pipeline_obj.get("device") or "")
            actual_use_gpu = bool(pipeline_obj.get("use_gpu"))
            added_langs = [str(pipeline_obj.get("trankit_name") or "")]
        elif pipeline_obj is not None:
            try:
                actual_device = str(pipeline_obj._config.device)
                actual_use_gpu = bool(pipeline_obj._use_gpu)
                added_langs = list(getattr(pipeline_obj, "added_langs", []) or [])
            except Exception:
                pass

        result_queue.put({
            "ok": True,
            "mode": mode,
            "device": device_label,
            "requested_gpu": use_gpu,
            "pid": pid,
            "lang": resolved_lang,
            "loaded_description": loaded_description,
            "actual_device": actual_device,
            "actual_use_gpu": actual_use_gpu,
            "added_lang_count": len(added_langs),
            "added_langs": added_langs,
            "total_elapsed_seconds": time.perf_counter() - started,
            "rss_process_start_bytes": rss_process_start,
            "rss_after_load_bytes": rss_after,
            "rss_total_delta_bytes": _bytes_delta(rss_after, rss_process_start),
            "gpu_process_start": gpu_process_start,
            "gpu_after_load": gpu_after,
            "gpu_total_delta": _gpu_delta(gpu_after, gpu_process_start),
            "stages": stages,
            "warmup_inference_ran": bool(warmup_text.strip()),
            "warmup_annotation": first_inference_doc,
        })
    except Exception as exc:
        _sync_cuda(torch_module, use_gpu)
        _force_gc()
        result_queue.put({
            "ok": False,
            "mode": mode,
            "device": device_label,
            "requested_gpu": use_gpu,
            "pid": pid,
            "total_elapsed_seconds": time.perf_counter() - started,
            "rss_after_load_bytes": current_rss_bytes(),
            "gpu_after_load": _gpu_snapshot(torch_module),
            "stages": stages,
            "error": str(exc),
            "traceback": traceback.format_exc(),
        })


def run_cold_start_probe_process(
    mode: str,
    device_label: str,
    use_gpu: bool,
    raw_lang: str,
    warmup_text: str,
) -> Dict[str, Any]:
    ctx = mp.get_context("spawn")
    result_queue = ctx.Queue()
    started = time.perf_counter()
    process = ctx.Process(
        target=_cold_start_worker_main,
        args=(mode, device_label, use_gpu, raw_lang, warmup_text, result_queue),
        daemon=False,
    )
    process.start()
    try:
        result = result_queue.get(timeout=LOAD_PROBE_TIMEOUT_SECONDS)
    except queue.Empty:
        result = {
            "ok": False,
            "mode": mode,
            "device": device_label,
            "requested_gpu": use_gpu,
            "pid": process.pid,
            "error": "cold-start probe timed out",
        }
    finally:
        process.join(timeout=5)
        if process.is_alive():
            process.terminate()
    if isinstance(result, dict):
        result["probe_process_wall_seconds"] = time.perf_counter() - started
        result["exitcode"] = process.exitcode
    return result


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
                if self.gpu_allocated_peak_bytes is None or allocated > self.gpu_allocated_peak_bytes:
                    self.gpu_allocated_peak_bytes = allocated
            if isinstance(reserved, int):
                if self.gpu_reserved_peak_bytes is None or reserved > self.gpu_reserved_peak_bytes:
                    self.gpu_reserved_peak_bytes = reserved
            time.sleep(self.interval_seconds)


def _install_forced_trankit_pipeline(use_gpu: bool) -> None:
    import trankit  # type: ignore

    real_pipeline = trankit.Pipeline

    class ForcedDevicePipeline(real_pipeline):  # type: ignore[misc, valid-type]
        def __init__(self, *args: Any, **kwargs: Any):
            kwargs["gpu"] = use_gpu
            super().__init__(*args, **kwargs)

    trankit.Pipeline = ForcedDevicePipeline


def _run_analysis_command(
    lr: Any,
    run_with_universal_normalization: Any,
    torch_module: Any,
    command: Dict[str, Any],
    *,
    use_gpu: bool,
    optimized_cpu: bool = False,
    optimized_gpu: bool = False,
    bf16_autocast: bool = False,
) -> tuple[Dict[str, Any], str, int, int, Dict[str, Any], Dict[str, Any]]:
    text = str(command.get("text") or "")
    raw_lang = str(command.get("lang") or "zh").strip().lower()
    trankit_override = str(command.get("trankit_override") or "").strip()
    manual_sentence_segmentation = bool(command.get("manual_sentence_segmentation"))
    strip_punctuation = bool(command.get("strip_punctuation"))

    lang_code = lr.resolve_lang_code(raw_lang)
    if not lang_code:
        raise ValueError(f"Unsupported language: {raw_lang}")

    manual_post_strip = bool(
        manual_sentence_segmentation and strip_punctuation and lang_code in {"sa", "lzh"}
    )
    effective_strip_punctuation = bool(strip_punctuation and not manual_post_strip)

    def run_one(model_text: str, trankit_lang: str) -> Dict[str, Any]:
        return lr.run_trankit(
            model_text,
            trankit_lang,
            trankit_name_override=trankit_override,
            manual_sentence_segmentation=manual_sentence_segmentation,
            strip_punctuation_after_manual_sentence_segmentation=manual_post_strip,
        )

    gc_calls = 0
    cuda_empty_cache_calls = 0
    sync_point_report: Dict[str, Any] = {"available": False, "calls": {}}
    task_breakdown: Dict[str, Any] = {"available": False, "stages": {}}
    pipeline_obj = getattr(lr, "_trankit_pipeline", None)
    with _temporary_trankit_task_breakdown(pipeline_obj, torch_module, use_gpu, lr) as task_counter:
        if optimized_cpu or optimized_gpu:
            with _temporary_no_gc_collect() as gc_counter:
                with _temporary_no_cuda_empty_cache(torch_module) as cuda_counter:
                    with _temporary_tensor_sync_point_counter(torch_module) as sync_counter:
                        with _torch_cpu_inference_context(torch_module, bf16_autocast if optimized_cpu else False):
                            doc = run_with_universal_normalization(
                                text,
                                run_one,
                                lang_code,
                                language=lang_code,
                                strip_punctuation=effective_strip_punctuation,
                            )
                        sync_point_report = dict(sync_counter)
                gc_calls = int(gc_counter.get("count") or 0)
                cuda_empty_cache_calls = int(cuda_counter.get("count") or 0)
        else:
            doc = run_with_universal_normalization(
                text,
                run_one,
                lang_code,
                language=lang_code,
                strip_punctuation=effective_strip_punctuation,
            )
        task_breakdown = dict(task_counter)
    if torch_module is not None and use_gpu and torch_module.cuda.is_available():
        torch_module.cuda.synchronize()
    return doc, lang_code, gc_calls, cuda_empty_cache_calls, sync_point_report, task_breakdown


def _force_pipeline_eval(pipeline_obj: Any) -> int:
    count = 0
    for value in [
        getattr(pipeline_obj, "_embedding_layers", None),
        *list((getattr(pipeline_obj, "_tokenizer", {}) or {}).values()),
        *list((getattr(pipeline_obj, "_tagger", {}) or {}).values()),
        *list((getattr(pipeline_obj, "_ner_model", {}) or {}).values()),
    ]:
        if hasattr(value, "eval"):
            value.eval()
            count += 1
    for wrapper_map_name in ["_lemma_model", "_mwt_model"]:
        wrapper_map = getattr(pipeline_obj, wrapper_map_name, {}) or {}
        for wrapper in wrapper_map.values():
            trainer = getattr(wrapper, "model", None)
            model = getattr(trainer, "model", None)
            if hasattr(model, "eval"):
                model.eval()
                count += 1
    return count


def _dynamic_quantize_leaf(
    torch_module: Any,
    child: Any,
    target_types: tuple[Any, ...],
) -> tuple[Any, bool, str]:
    if not isinstance(child, target_types):
        return child, False, ""
    try:
        dynamic_nn = torch_module.ao.nn.quantized.dynamic
        quantization = torch_module.ao.quantization
        mappings = [
            (getattr(torch_module.nn, "Linear", None), getattr(dynamic_nn, "Linear", None)),
            (getattr(torch_module.nn, "LSTM", None), getattr(dynamic_nn, "LSTM", None)),
            (getattr(torch_module.nn, "GRU", None), getattr(dynamic_nn, "GRU", None)),
            (getattr(torch_module.nn, "LSTMCell", None), getattr(dynamic_nn, "LSTMCell", None)),
        ]
        for float_cls, quantized_cls in mappings:
            if float_cls is None or quantized_cls is None or not isinstance(child, float_cls):
                continue
            child.qconfig = quantization.default_dynamic_qconfig
            quantized = quantized_cls.from_float(child)
            changed = type(quantized) is not type(child)
            return quantized, changed, "" if changed else "module type unchanged"
    except Exception as exc:
        return child, False, str(exc)

    quantize_dynamic = None
    try:
        quantize_dynamic = torch_module.ao.quantization.quantize_dynamic
    except Exception:
        try:
            quantize_dynamic = torch_module.quantization.quantize_dynamic
        except Exception:
            quantize_dynamic = None
    if quantize_dynamic is None:
        return child, False, "torch dynamic quantization API unavailable"
    if not isinstance(child, target_types):
        return child, False, ""
    try:
        qconfig_spec = {type(child)}
        quantized = quantize_dynamic(child, qconfig_spec=qconfig_spec, dtype=torch_module.qint8, inplace=False)
        changed = type(quantized) is not type(child)
        return quantized, changed, "" if changed else "module type unchanged"
    except Exception as exc:
        return child, False, str(exc)


def _quantize_selected_children(
    module: Any,
    torch_module: Any,
    *,
    skip_adapter_paths: bool,
    excluded_path_tokens: tuple[str, ...] = (),
    target_type_names: tuple[str, ...] = ("Linear", "LSTM", "GRU", "LSTMCell"),
    path: str = "",
) -> Dict[str, Any]:
    nn = torch_module.nn
    target_types = tuple(
        getattr(nn, type_name, None)
        for type_name in target_type_names
        if getattr(nn, type_name, None) is not None
    )
    excluded_tokens = tuple(token.lower() for token in excluded_path_tokens if token)
    report: Dict[str, Any] = {
        "quantized_count": 0,
        "skipped_adapter_count": 0,
        "skipped_embedding_count": 0,
        "skipped_layernorm_count": 0,
        "skipped_excluded_count": 0,
        "unchanged_count": 0,
        "errors": [],
        "quantized_modules": [],
        "excluded_path_tokens": list(excluded_tokens),
        "target_type_names": list(target_type_names),
    }
    for name, child in list(module.named_children()):
        child_path = f"{path}.{name}" if path else name
        child_path_lower = child_path.lower()
        if skip_adapter_paths and "adapter" in child_path_lower:
            report["skipped_adapter_count"] += 1
            continue
        matched_excluded_token = next((token for token in excluded_tokens if token in child_path_lower), "")
        if matched_excluded_token:
            report["skipped_excluded_count"] += 1
            if matched_excluded_token == "embedding":
                report["skipped_embedding_count"] += 1
            elif matched_excluded_token in {"layernorm", "layer_norm"}:
                report["skipped_layernorm_count"] += 1
            elif matched_excluded_token == "adapter":
                report["skipped_adapter_count"] += 1
            continue
        quantized, changed, error = _dynamic_quantize_leaf(torch_module, child, target_types)
        if changed:
            setattr(module, name, quantized)
            report["quantized_count"] += 1
            report["quantized_modules"].append(child_path)
            continue
        if error:
            if error != "module type unchanged":
                report["errors"].append({"module": child_path, "error": error})
            else:
                report["unchanged_count"] += 1
        nested = _quantize_selected_children(
            child,
            torch_module,
            skip_adapter_paths=skip_adapter_paths,
            excluded_path_tokens=excluded_path_tokens,
            target_type_names=target_type_names,
            path=child_path,
        )
        report["quantized_count"] += int(nested.get("quantized_count") or 0)
        report["skipped_adapter_count"] += int(nested.get("skipped_adapter_count") or 0)
        report["skipped_embedding_count"] += int(nested.get("skipped_embedding_count") or 0)
        report["skipped_layernorm_count"] += int(nested.get("skipped_layernorm_count") or 0)
        report["skipped_excluded_count"] += int(nested.get("skipped_excluded_count") or 0)
        report["unchanged_count"] += int(nested.get("unchanged_count") or 0)
        report["errors"].extend(nested.get("errors") or [])
        report["quantized_modules"].extend(nested.get("quantized_modules") or [])
    return report


def _iter_seq2seq_models(pipeline_obj: Any) -> list[tuple[str, Any]]:
    out: list[tuple[str, Any]] = []
    for attr_name in ["_lemma_model", "_mwt_model"]:
        wrapper_map = getattr(pipeline_obj, attr_name, {}) or {}
        if not isinstance(wrapper_map, dict):
            continue
        for lang, wrapper in wrapper_map.items():
            trainer = getattr(wrapper, "model", None)
            model = getattr(trainer, "model", None)
            if model is not None:
                out.append((f"{attr_name}.{lang}", model))
    return out


def _set_seq2seq_model_by_name(pipeline_obj: Any, name: str, model: Any) -> bool:
    parts = name.split(".", 1)
    if len(parts) != 2:
        return False
    attr_name, lang = parts
    wrapper_map = getattr(pipeline_obj, attr_name, {}) or {}
    wrapper = wrapper_map.get(lang) if isinstance(wrapper_map, dict) else None
    trainer = getattr(wrapper, "model", None)
    if trainer is None:
        return False
    trainer.model = model
    if hasattr(trainer.model, "eval"):
        trainer.model.eval()
    return True


def _torch_load_sandbox(torch_module: Any, path: str) -> Any:
    try:
        return torch_module.load(path, map_location="cpu", weights_only=False)
    except TypeError:
        return torch_module.load(path, map_location="cpu")


def _count_dynamic_int8_modules(module: Any) -> int:
    count = 0
    try:
        iterator = module.modules()
    except Exception:
        return 0
    for child in iterator:
        module_name = str(type(child).__module__).lower()
        type_name = str(type(child).__name__).lower()
        if "quantized.dynamic" in module_name or (
            "torch.ao.nn.quantized" in module_name and type_name in {"linear", "lstm", "gru", "lstmcell"}
        ):
            count += 1
    return count


def _count_dynamic_int8_modules_matching_path(module: Any, token: str) -> int:
    token_lower = str(token).lower()
    count = 0
    try:
        iterator = module.named_modules()
    except Exception:
        return 0
    for name, child in iterator:
        if token_lower not in str(name).lower():
            continue
        probe = _count_dynamic_int8_modules(child)
        if probe:
            count += probe
    return count


def _disable_xlmr_hidden_state_outputs(module: Any) -> Dict[str, Any]:
    report = {"changed_attrs": 0}
    try:
        iterator = module.modules()
    except Exception:
        iterator = [module]
    for child in iterator:
        for attr in ["output_hidden_states"]:
            if hasattr(child, attr):
                try:
                    if bool(getattr(child, attr)):
                        setattr(child, attr, False)
                        report["changed_attrs"] += 1
                except Exception:
                    pass
        config = getattr(child, "config", None)
        if config is not None and hasattr(config, "output_hidden_states"):
            try:
                if bool(getattr(config, "output_hidden_states")):
                    setattr(config, "output_hidden_states", False)
                    report["changed_attrs"] += 1
            except Exception:
                pass
    return report


def _install_cpu_opt_xlmr_load_patch() -> Dict[str, Any]:
    report: Dict[str, Any] = {"installed": False}
    try:
        import trankit.models.base_models as base_models  # type: ignore

        cls = base_models.XLMRobertaModel
        current = getattr(cls, "from_pretrained")
        if getattr(current, "_cpu_opt_no_hidden_states", False):
            return {"installed": True, "already_installed": True}
        original_from_pretrained = current

        @classmethod
        def patched_from_pretrained(model_cls: Any, *args: Any, **kwargs: Any):
            kwargs["output_hidden_states"] = False
            model = original_from_pretrained(*args, **kwargs)
            _disable_xlmr_hidden_state_outputs(model)
            return model

        setattr(patched_from_pretrained, "_cpu_opt_no_hidden_states", True)
        cls.from_pretrained = patched_from_pretrained
        report["installed"] = True
    except Exception as exc:
        report["installed"] = False
        report["error"] = str(exc)
    return report


class _OnnxXlmrRuntime:
    def __init__(self, ort_module: Any, torch_module: Any, sessions: Dict[tuple[str, str], Any]):
        self.ort = ort_module
        self.torch = torch_module
        self.sessions = sessions
        self.run_count = 0
        self.missing_session_count = 0
        self.missing_sessions: Dict[str, int] = {}
        self.last_session_key = ""

    def has_session(self, lang: str, task: str) -> bool:
        return (str(lang), str(task)) in self.sessions

    def run(self, lang: str, task: str, piece_idxs: Any, attention_masks: Any) -> Any:
        key = (str(lang), str(task))
        session = self.sessions.get(key)
        if session is None:
            self.missing_session_count += 1
            label = f"{key[0]}:{key[1]}"
            self.missing_sessions[label] = int(self.missing_sessions.get(label, 0)) + 1
            raise RuntimeError(f"Missing required ONNX XLM-R session for {label}")
        self.run_count += 1
        self.last_session_key = f"{key[0]}:{key[1]}"
        input_ids = piece_idxs.detach().cpu().numpy().astype("int64", copy=False)
        attention_mask = attention_masks.detach().cpu().numpy().astype("int64", copy=False)
        outputs = session.run(None, {"input_ids": input_ids, "attention_mask": attention_mask})
        return self.torch.from_numpy(outputs[0]).to(device=piece_idxs.device)

    def metrics(self) -> Dict[str, Any]:
        return {
            "run_count": self.run_count,
            "missing_session_count": self.missing_session_count,
            "missing_sessions": dict(self.missing_sessions),
            "last_session_key": self.last_session_key,
            "loaded_session_count": len(self.sessions),
        }


def _iter_onnx_xlmr_tasks(pipeline_obj: Any) -> list[tuple[str, str]]:
    langs = list(getattr(pipeline_obj, "added_langs", []) or [])
    tokenizer_map = getattr(pipeline_obj, "_tokenizer", {}) or {}
    tagger_map = getattr(pipeline_obj, "_tagger", {}) or {}
    ner_map = getattr(pipeline_obj, "_ner_model", {}) or {}
    tasks: list[tuple[str, str]] = []
    for lang in langs:
        lang_name = str(lang)
        if lang_name in tokenizer_map:
            tasks.append((lang_name, "tokenizer"))
        if lang_name in tagger_map:
            tasks.append((lang_name, "tagger"))
        if lang_name in ner_map:
            tasks.append((lang_name, "ner"))
    return tasks


def _onnx_paths_for_task(lang: str, task: str) -> Dict[str, str]:
    base = f"{_safe_onnx_name(lang)}__{_safe_onnx_name(task)}__xlmr"
    return {
        "raw": os.path.join(ONNX_CACHE_DIR, f"{base}__raw.onnx"),
        "optimized": os.path.join(ONNX_CACHE_DIR, f"{base}__ort_optimized.onnx"),
        "int8": os.path.join(ONNX_CACHE_DIR, f"{base}__ort_dynamic_int8.onnx"),
        "meta": os.path.join(ONNX_CACHE_DIR, f"{base}__meta.json"),
    }


def _load_onnx_session(ort_module: Any, path: str) -> Any:
    session_options = ort_module.SessionOptions()
    session_options.graph_optimization_level = ort_module.GraphOptimizationLevel.ORT_ENABLE_ALL
    return ort_module.InferenceSession(path, sess_options=session_options, providers=["CPUExecutionProvider"])


def _install_onnx_xlmr_runtime(pipeline_obj: Any, torch_module: Any) -> Dict[str, Any]:
    started = time.perf_counter()
    report: Dict[str, Any] = {
        "profile": ONNX_PROFILE_NAME,
        "deps": _append_onnx_deps(),
        "cache_dir": ONNX_CACHE_DIR,
        "manifest_path": ONNX_MANIFEST_PATH,
        "tasks": [],
        "task_count": 0,
        "session_count": 0,
        "int8_session_count": 0,
        "failed_task_count": 0,
        "installed": False,
        "errors": [],
    }
    if pipeline_obj is None:
        report["errors"].append("missing Trankit pipeline")
        report["elapsed_seconds"] = time.perf_counter() - started
        return report
    try:
        from sandbox_trankit_compressed_runtime import install_compressed_runtime  # type: ignore
    except Exception as exc:
        report["errors"].append(f"compressed runtime import failed: {exc}")
        report["elapsed_seconds"] = time.perf_counter() - started
        return report

    if not os.path.exists(ONNX_MANIFEST_PATH):
        report["errors"].append(
            "prebuilt compressed runtime manifest is missing; run python build_trankit_compressed_runtime_artifacts.py first"
        )
        report["elapsed_seconds"] = time.perf_counter() - started
        return report

    try:
        from pathlib import Path

        installed = install_compressed_runtime(
            pipeline_obj,
            torch_module,
            manifest_path=Path(os.path.abspath(ONNX_MANIFEST_PATH)),
        )
    except Exception as exc:
        report["errors"].append(str(exc))
        report["elapsed_seconds"] = time.perf_counter() - started
        return report

    report.update(installed)
    report["task_count"] = int(installed.get("task_count") or 0)
    report["session_count"] = 1
    report["int8_session_count"] = 1
    report["failed_task_count"] = 0
    report["tasks"] = []
    report["installed"] = True
    report["elapsed_seconds"] = time.perf_counter() - started
    return report


def _load_xlmr_int8_cache(pipeline_obj: Any, torch_module: Any) -> Optional[Dict[str, Any]]:
    if not os.path.exists(CPU_OPT_XLMR_CACHE_PATH):
        return None
    try:
        payload = _torch_load_sandbox(torch_module, CPU_OPT_XLMR_CACHE_PATH)
        if isinstance(payload, dict) and payload.get("cache_version") != CPU_OPT_XLMR_CACHE_VERSION:
            raise ValueError("cached XLM-R module cache version mismatch")
        if isinstance(payload, dict) and tuple(payload.get("excluded_path_tokens") or ()) != CPU_OPT_QUANTIZE_EXCLUDE_TOKENS:
            raise ValueError("cached XLM-R module exclusion rules mismatch")
        module = payload.get("module") if isinstance(payload, dict) else payload
        if module is None:
            raise ValueError("missing XLM-R module")
        pipeline_obj._embedding_layers.xlmr = module
        hidden_state_report = _disable_xlmr_hidden_state_outputs(module)
        pipeline_obj._embedding_layers.eval()
        pipeline_obj._embedding_weights = pipeline_obj._embedding_layers.state_dict()
        quantized_count = _count_dynamic_int8_modules(module)
        if quantized_count <= 0:
            raise ValueError("cached XLM-R module has no dynamic INT8 modules")
        return {
            "loaded": True,
            "path": CPU_OPT_XLMR_CACHE_PATH,
            "quantized_count": quantized_count,
            "hidden_state_report": hidden_state_report,
            "cache_version": CPU_OPT_XLMR_CACHE_VERSION,
            "excluded_path_tokens": list(CPU_OPT_QUANTIZE_EXCLUDE_TOKENS),
            "target_type_names": ["Linear"],
        }
    except Exception as exc:
        return {"loaded": False, "path": CPU_OPT_XLMR_CACHE_PATH, "error": str(exc)}


def _save_xlmr_int8_cache(pipeline_obj: Any, torch_module: Any) -> Dict[str, Any]:
    try:
        quantized_count = _count_dynamic_int8_modules(pipeline_obj._embedding_layers.xlmr)
        os.makedirs(CPU_OPT_CACHE_DIR, exist_ok=True)
        torch_module.save(
            {
                "cache_version": CPU_OPT_XLMR_CACHE_VERSION,
                "created_at": time.time(),
                "quantized_count": quantized_count,
                "torch_version": str(getattr(torch_module, "__version__", "")),
                "profile": CPU_OPT_PROFILE_NAME,
                "hidden_states_disabled": True,
                "excluded_path_tokens": list(CPU_OPT_QUANTIZE_EXCLUDE_TOKENS),
                "target_type_names": ["Linear"],
                "module": pipeline_obj._embedding_layers.xlmr,
            },
            CPU_OPT_XLMR_CACHE_PATH,
        )
        return {
            "saved": True,
            "path": CPU_OPT_XLMR_CACHE_PATH,
            "cache_version": CPU_OPT_XLMR_CACHE_VERSION,
            "quantized_count": quantized_count,
            "excluded_path_tokens": list(CPU_OPT_QUANTIZE_EXCLUDE_TOKENS),
            "target_type_names": ["Linear"],
        }
    except Exception as exc:
        return {"saved": False, "path": CPU_OPT_XLMR_CACHE_PATH, "error": str(exc)}


def _load_seq2seq_int8_cache(pipeline_obj: Any, torch_module: Any) -> Optional[Dict[str, Any]]:
    if not os.path.exists(CPU_OPT_SEQ2SEQ_CACHE_PATH):
        return None
    try:
        payload = _torch_load_sandbox(torch_module, CPU_OPT_SEQ2SEQ_CACHE_PATH)
        modules = payload.get("modules") if isinstance(payload, dict) else None
        if not isinstance(modules, dict):
            raise ValueError("missing seq2seq module map")
        loaded = []
        missing = []
        quantized_count = 0
        for name, module in modules.items():
            if _set_seq2seq_model_by_name(pipeline_obj, str(name), module):
                loaded.append(str(name))
                quantized_count += _count_dynamic_int8_modules(module)
            else:
                missing.append(str(name))
        if loaded and quantized_count <= 0:
            raise ValueError("cached seq2seq modules have no dynamic INT8 modules")
        return {
            "loaded": True,
            "path": CPU_OPT_SEQ2SEQ_CACHE_PATH,
            "loaded_count": len(loaded),
            "missing_count": len(missing),
            "missing": missing[:25],
            "quantized_count": quantized_count,
        }
    except Exception as exc:
        return {"loaded": False, "path": CPU_OPT_SEQ2SEQ_CACHE_PATH, "error": str(exc)}


def _save_seq2seq_int8_cache(pipeline_obj: Any, torch_module: Any) -> Dict[str, Any]:
    try:
        modules = {name: model for name, model in _iter_seq2seq_models(pipeline_obj)}
        if not modules:
            return {"saved": False, "path": CPU_OPT_SEQ2SEQ_CACHE_PATH, "error": "no seq2seq modules found"}
        quantized_count = sum(_count_dynamic_int8_modules(model) for model in modules.values())
        os.makedirs(CPU_OPT_CACHE_DIR, exist_ok=True)
        torch_module.save(
            {
                "cache_version": 1,
                "created_at": time.time(),
                "quantized_count": quantized_count,
                "modules": modules,
            },
            CPU_OPT_SEQ2SEQ_CACHE_PATH,
        )
        return {"saved": True, "path": CPU_OPT_SEQ2SEQ_CACHE_PATH, "module_count": len(modules), "quantized_count": quantized_count}
    except Exception as exc:
        return {"saved": False, "path": CPU_OPT_SEQ2SEQ_CACHE_PATH, "error": str(exc)}


def _cpu_opt_report_needs_xlmr_cache(optimization_report: Dict[str, Any]) -> bool:
    q = optimization_report.get("xlmr_quantization") if isinstance(optimization_report, dict) else None
    if not isinstance(q, dict):
        return False
    if q.get("from_cache"):
        return False
    try:
        return int(q.get("quantized_count") or 0) > 0
    except Exception:
        return False


def _cpu_opt_report_needs_seq2seq_cache(optimization_report: Dict[str, Any]) -> bool:
    rows = optimization_report.get("seq2seq_quantization") if isinstance(optimization_report, dict) else None
    if not isinstance(rows, list):
        return False
    for row in rows:
        if not isinstance(row, dict) or row.get("from_cache"):
            continue
        try:
            if int(row.get("quantized_count") or 0) > 0:
                return True
        except Exception:
            continue
    return False


def _save_cpu_opt_module_caches(
    pipeline_obj: Any,
    torch_module: Any,
    profile: str,
    optimization_report: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    report: Dict[str, Any] = {}
    if profile in {CPU_OPT_PROFILE_NAME, "xlmr_int8", "xlmr_seq2seq_int8"}:
        if optimization_report is not None and not _cpu_opt_report_needs_xlmr_cache(optimization_report):
            report["xlmr_int8_cache"] = {"saved": False, "skipped": True, "reason": "loaded from cache or no new XLM-R quantization"}
        else:
            report["xlmr_int8_cache"] = _save_xlmr_int8_cache(pipeline_obj, torch_module)
    if profile in {"seq2seq_int8", "xlmr_seq2seq_int8"}:
        if optimization_report is not None and not _cpu_opt_report_needs_seq2seq_cache(optimization_report):
            report["seq2seq_int8_cache"] = {"saved": False, "skipped": True, "reason": "loaded from cache or no new seq2seq quantization"}
        else:
            report["seq2seq_int8_cache"] = _save_seq2seq_int8_cache(pipeline_obj, torch_module)
    return report


def _apply_cpu_optimization_profile(pipeline_obj: Any, torch_module: Any, profile: str) -> Dict[str, Any]:
    report: Dict[str, Any] = {
        "profile": profile,
        "eval_module_count": _force_pipeline_eval(pipeline_obj),
        "eval_status": _pipeline_eval_status(pipeline_obj),
        "xlmr_quantization": None,
        "xlmr_hidden_state_outputs": None,
        "seq2seq_quantization": None,
        "bf16_autocast": profile == "bf16_autocast",
        "bf16_probe": _detect_cpu_bf16_support(torch_module),
        "torch_compile": None,
        "ipex": None,
        "onnxruntime": None,
        "errors": [],
    }
    if profile in {CPU_OPT_PROFILE_NAME, "xlmr_int8", "xlmr_seq2seq_int8"}:
        try:
            cached = _load_xlmr_int8_cache(pipeline_obj, torch_module)
            if cached and cached.get("loaded"):
                report["xlmr_quantization"] = {
                    "cache": cached,
                    "quantized_count": int(cached.get("quantized_count") or 0),
                    "from_cache": True,
                }
                report["xlmr_hidden_state_outputs"] = cached.get("hidden_state_report")
            else:
                xlmr = pipeline_obj._embedding_layers.xlmr
                report["xlmr_hidden_state_outputs"] = _disable_xlmr_hidden_state_outputs(xlmr)
                quant_report = _quantize_selected_children(
                    xlmr,
                    torch_module,
                    skip_adapter_paths=True,
                    excluded_path_tokens=CPU_OPT_QUANTIZE_EXCLUDE_TOKENS,
                    target_type_names=("Linear",),
                )
                if cached:
                    quant_report["cache"] = cached
                report["xlmr_quantization"] = quant_report
                pipeline_obj._embedding_weights = pipeline_obj._embedding_layers.state_dict()
            report["xlmr_hidden_state_status"] = _hidden_states_disabled_status(
                getattr(getattr(pipeline_obj, "_embedding_layers", None), "xlmr", None)
            )
            xlmr_after = getattr(getattr(pipeline_obj, "_embedding_layers", None), "xlmr", None)
            report["xlmr_adapter_dynamic_int8_count"] = _count_dynamic_int8_modules_matching_path(xlmr_after, "adapter")
        except Exception as exc:
            report["errors"].append(f"xlmr_int8 failed: {exc}")
    if profile == CPU_OPT_PROFILE_NAME:
        report["seq2seq_quantization"] = {
            "skipped": True,
            "reason": "This CPU profile intentionally quantizes only base XLM-R Linear layers.",
        }
        report["torch_compile"] = {
            "status": "skipped",
            "reason": "Compile is benchmarked separately before it is allowed to replace the stable INT8 profile.",
        }
        if not bool(report["bf16_probe"].get("supported")):
            report["bf16_autocast"] = False
            report["bf16_status"] = "skipped"
        else:
            report["bf16_status"] = "available_for_experiment"
    if profile in {"seq2seq_int8", "xlmr_seq2seq_int8"}:
        cached = _load_seq2seq_int8_cache(pipeline_obj, torch_module)
        if cached and cached.get("loaded"):
            report["seq2seq_quantization"] = [{
                "cache": cached,
                "quantized_count": int(cached.get("quantized_count") or 0),
                "from_cache": True,
            }]
        else:
            seq_reports = []
            for name, model in _iter_seq2seq_models(pipeline_obj):
                seq_report = _quantize_selected_children(
                    model,
                    torch_module,
                    skip_adapter_paths=False,
                )
                seq_report["module"] = name
                seq_reports.append(seq_report)
            if cached:
                seq_reports.insert(0, {"cache": cached, "quantized_count": 0})
            report["seq2seq_quantization"] = seq_reports
    if profile == "torch_compile_xlmr":
        try:
            if not hasattr(torch_module, "compile"):
                raise RuntimeError("torch.compile is unavailable")
            pipeline_obj._embedding_layers.xlmr = torch_module.compile(
                pipeline_obj._embedding_layers.xlmr,
                mode="reduce-overhead",
            )
            pipeline_obj._embedding_weights = pipeline_obj._embedding_layers.state_dict()
            report["torch_compile"] = {"ok": True, "target": "_embedding_layers.xlmr"}
        except Exception as exc:
            report["torch_compile"] = {"ok": False, "error": str(exc)}
            report["errors"].append(f"torch_compile_xlmr failed: {exc}")
    if profile == "ipex_xlmr":
        try:
            import intel_extension_for_pytorch as ipex  # type: ignore

            pipeline_obj._embedding_layers.xlmr = ipex.optimize(pipeline_obj._embedding_layers.xlmr.eval())
            pipeline_obj._embedding_weights = pipeline_obj._embedding_layers.state_dict()
            report["ipex"] = {"ok": True, "target": "_embedding_layers.xlmr"}
        except Exception as exc:
            report["ipex"] = {"ok": False, "error": str(exc)}
            report["errors"].append(f"ipex_xlmr failed: {exc}")
    if profile in {"onnx_xlmr", "onnx_int8_xlmr"}:
        try:
            import onnxruntime  # type: ignore  # noqa: F401

            report["onnxruntime"] = {
                "ok": False,
                "skipped": True,
                "reason": "XLM-R ONNX replacement is not safely selectable while Trankit mutates adapter state with load_state_dict.",
            }
        except Exception as exc:
            report["onnxruntime"] = {"ok": False, "skipped": True, "error": str(exc)}
        report["errors"].append(f"{profile} skipped")
    return report


def _cpu_profile_uses_bf16(profile: str) -> bool:
    return profile == "bf16_autocast"


def _apply_gpu_optimization_profile(pipeline_obj: Any, torch_module: Any) -> Dict[str, Any]:
    report: Dict[str, Any] = {
        "profile": GPU_OPT_PROFILE_NAME,
        "eval_module_count": _force_pipeline_eval(pipeline_obj),
        "eval_status": _pipeline_eval_status(pipeline_obj),
        "backend": _configure_gpu_torch_backend(torch_module),
        "xlmr_hidden_state_outputs": None,
        "xlmr_hidden_state_status": None,
        "fp16_coverage": None,
        "torch_compile": None,
        "errors": [],
    }
    try:
        xlmr = getattr(getattr(pipeline_obj, "_embedding_layers", None), "xlmr", None)
        report["xlmr_hidden_state_outputs"] = _disable_xlmr_hidden_state_outputs(xlmr)
        report["xlmr_hidden_state_status"] = _hidden_states_disabled_status(xlmr)
    except Exception as exc:
        report["errors"].append(f"hidden-state patch failed: {exc}")

    try:
        report["fp16_coverage"] = _gpu_fp16_coverage_report(pipeline_obj)
    except Exception as exc:
        report["fp16_coverage"] = {"error": str(exc)}

    if GPU_OPT_ENABLE_TORCH_COMPILE:
        try:
            if not hasattr(torch_module, "compile"):
                raise RuntimeError("torch.compile is unavailable")
            pipeline_obj._embedding_layers.xlmr = torch_module.compile(
                pipeline_obj._embedding_layers.xlmr,
                mode="reduce-overhead",
            )
            pipeline_obj._embedding_weights = pipeline_obj._embedding_layers.state_dict()
            report["torch_compile"] = {"status": "kept", "target": "_embedding_layers.xlmr"}
        except Exception as exc:
            report["torch_compile"] = {"status": "rejected", "error": str(exc)}
    else:
        report["torch_compile"] = {
            "status": "skipped",
            "reason": "Disabled in v1 to avoid startup stalls/recompilation while measuring safe GPU hot-path patches.",
        }
    return report


def _gpu_opt_bucket_text(bucket: int) -> str:
    unit = "Ceci est une phrase francaise de calibrage pour rechauffer le chemin GPU optimise Trankit. "
    try:
        repeat_count = max(1, int(bucket) // 16)
    except Exception:
        repeat_count = 1
    return (unit * repeat_count).strip()


def _gpu_opt_bucket_command(bucket: int) -> Dict[str, Any]:
    command = _cpu_opt_tuning_command()
    command["request_id"] = f"gpu-opt-bucket-{bucket}"
    command["text"] = _gpu_opt_bucket_text(bucket)
    command["bucket"] = bucket
    return command


def _gpu_opt_startup_warmup(
    lr: Any,
    run_with_universal_normalization: Any,
    torch_module: Any,
) -> Dict[str, Any]:
    started = time.perf_counter()
    report: Dict[str, Any] = {
        "ok": True,
        "bucket_results": [],
    }
    for bucket in GPU_OPT_SEQUENCE_BUCKETS:
        row: Dict[str, Any] = {"bucket": bucket}
        try:
            measured_started = time.perf_counter()
            doc, lang_code, gc_calls, cuda_empty_cache_calls, sync_report = _run_analysis_command(
                lr,
                run_with_universal_normalization,
                torch_module,
                _gpu_opt_bucket_command(bucket),
                use_gpu=True,
                optimized_gpu=True,
            )
            row.update({
                "ok": True,
                "elapsed_seconds": time.perf_counter() - measured_started,
                "lang": lang_code,
                "fingerprint": _annotation_fingerprint(doc),
                "counts": _annotation_counts(doc),
                "gc_collect_calls_suppressed": gc_calls,
                "cuda_empty_cache_calls_suppressed": cuda_empty_cache_calls,
                "sync_points": sync_report,
            })
        except Exception as exc:
            row.update({"ok": False, "error": str(exc)})
        report["bucket_results"].append(row)
    report["elapsed_seconds"] = time.perf_counter() - started
    return report


def _apply_cpu_opt_batch_sizes(pipeline_obj: Any, tok_batch_size: int, tag_batch_size: int) -> Dict[str, Any]:
    tok_value = max(1, int(tok_batch_size))
    tag_value = max(1, int(tag_batch_size))
    report: Dict[str, Any] = {
        "tok_batch_size": tok_value,
        "tag_batch_size": tag_value,
        "previous_tok_batch_size": getattr(pipeline_obj, "_tokbatchsize", None),
        "previous_tag_batch_size": getattr(pipeline_obj, "_tagbatchsize", None),
        "tb_tok_overrides_changed": 0,
        "tb_tag_overrides_changed": 0,
    }
    try:
        pipeline_obj._tokbatchsize = tok_value
        pipeline_obj._tagbatchsize = tag_value
    except Exception as exc:
        report["pipeline_batch_error"] = str(exc)
    try:
        import trankit.utils.tbinfo as tbinfo  # type: ignore

        tok_map = getattr(tbinfo, "tbname2tokbatchsize", None)
        if isinstance(tok_map, dict):
            for key in list(tok_map.keys()):
                tok_map[key] = tok_value
            report["tb_tok_overrides_changed"] = len(tok_map)
        tag_map = getattr(tbinfo, "tbname2tagbatchsize", None)
        if isinstance(tag_map, dict):
            for key in list(tag_map.keys()):
                tag_map[key] = tag_value
            report["tb_tag_overrides_changed"] = len(tag_map)
    except Exception as exc:
        report["tbinfo_batch_error"] = str(exc)
    return report


def _install_onnx_tokenizer_dynamic_padding_patch() -> Dict[str, Any]:
    report: Dict[str, Any] = {
        "installed": False,
        "target": "trankit.iterators.tokenizer_iterators.TokenizeDatasetLive",
    }
    try:
        from trankit.iterators import tokenizer_iterators as tokenizer_iterators  # type: ignore

        dataset_cls = tokenizer_iterators.TokenizeDatasetLive
        if getattr(dataset_cls, "_benchmark_dynamic_padding_installed", False):
            report["installed"] = True
            report["already_installed"] = True
            return report

        original_numberize = dataset_cls.numberize
        original_collate_fn = dataset_cls.collate_fn

        def numberize_dynamic(self: Any, wordpiece_splitter: Any) -> None:
            data = []
            for inst in self.data:
                wordpieces = inst["wordpieces"]
                wordpiece_labels = inst["wordpiece_labels"]
                wordpiece_ends = inst["wordpiece_ends"]
                paragraph_index = inst["paragraph_index"]
                piece_idxs = wordpiece_splitter.encode(
                    wordpieces,
                    add_special_tokens=True,
                    max_length=self.max_input_length,
                    truncation=True,
                )
                assert len(piece_idxs) <= self.max_input_length

                attention_masks = [1] * len(piece_idxs)
                token_type_idxs = [
                    -100 if piece_id >= len(wordpieces) else wordpiece_labels[piece_id]
                    for piece_id in range(max(0, len(piece_idxs) - 2))
                ]

                data.append(tokenizer_iterators.Instance(
                    paragraph_index=paragraph_index,
                    wordpieces=wordpieces,
                    wordpiece_labels=wordpiece_labels,
                    wordpiece_ends=wordpiece_ends,
                    piece_idxs=piece_idxs,
                    attention_masks=attention_masks,
                    token_type_idxs=token_type_idxs,
                    wordpiece_num=len(wordpieces),
                ))
            self.data = data

        def collate_fn_dynamic(self: Any, batch: Any) -> Any:
            batch_paragraph_index = []
            batch_wordpieces = []
            batch_wordpiece_labels = []
            batch_wordpiece_ends = []
            batch_piece_idxs = []
            batch_attention_masks = []
            batch_token_type_idxs = []
            batch_wordpiece_num = []

            max_piece_num = max(len(inst.piece_idxs) for inst in batch)
            max_token_type_num = max(0, max_piece_num - 2)
            for inst in batch:
                piece_pad = max_piece_num - len(inst.piece_idxs)
                token_type_pad = max_token_type_num - len(inst.token_type_idxs)
                batch_paragraph_index.append(inst.paragraph_index)
                batch_wordpieces.append(inst.wordpieces)
                batch_wordpiece_labels.append(inst.wordpiece_labels)
                batch_wordpiece_ends.append(inst.wordpiece_ends)
                batch_piece_idxs.append(inst.piece_idxs + [0] * piece_pad)
                batch_attention_masks.append(inst.attention_masks + [0] * piece_pad)
                batch_token_type_idxs.append(inst.token_type_idxs + [-100] * max(0, token_type_pad))
                batch_wordpiece_num.append(inst.wordpiece_num)

            torch_module = tokenizer_iterators.torch
            batch_piece_idxs_tensor = torch_module.tensor(batch_piece_idxs, dtype=torch_module.long, device=self.config.device)
            batch_attention_masks_tensor = torch_module.tensor(batch_attention_masks, dtype=torch_module.long, device=self.config.device)
            batch_token_type_idxs_tensor = torch_module.tensor(batch_token_type_idxs, dtype=torch_module.long, device=self.config.device)
            batch_wordpiece_num_tensor = torch_module.tensor(batch_wordpiece_num, dtype=torch_module.long, device=self.config.device)

            return tokenizer_iterators.Batch(
                paragraph_index=batch_paragraph_index,
                wordpieces=batch_wordpieces,
                wordpiece_labels=batch_wordpiece_labels,
                wordpiece_ends=batch_wordpiece_ends,
                piece_idxs=batch_piece_idxs_tensor,
                attention_masks=batch_attention_masks_tensor,
                token_type_idxs=batch_token_type_idxs_tensor,
                wordpiece_num=batch_wordpiece_num_tensor,
            )

        dataset_cls._benchmark_original_numberize = original_numberize
        dataset_cls._benchmark_original_collate_fn = original_collate_fn
        dataset_cls.numberize = numberize_dynamic
        dataset_cls.collate_fn = collate_fn_dynamic
        dataset_cls._benchmark_dynamic_padding_installed = True
        report["installed"] = True
        report["padding"] = "dynamic_per_batch"
    except Exception as exc:
        report["error"] = str(exc)
    return report


def _install_onnx_tagger_ner_length_bucketing_patch() -> Dict[str, Any]:
    report: Dict[str, Any] = {
        "installed": False,
        "targets": [
            "trankit.iterators.tagger_iterators.TaggerDatasetLive",
            "trankit.iterators.ner_iterators.NERDatasetLive",
        ],
    }

    def sort_key(inst: Any) -> tuple[int, int, int, int]:
        try:
            piece_len = int(len(getattr(inst, "piece_idxs", []) or []))
        except Exception:
            piece_len = 0
        try:
            word_num = int(getattr(inst, "word_num", 0) or 0)
        except Exception:
            word_num = 0
        try:
            sent_index = int(getattr(inst, "sent_index", 0) or 0)
        except Exception:
            sent_index = 0
        word_ids = getattr(inst, "word_ids", []) or []
        try:
            first_word_id = int(word_ids[0]) if word_ids else 0
        except Exception:
            first_word_id = 0
        return piece_len, word_num, sent_index, first_word_id

    def patch_dataset(dataset_cls: Any, label: str) -> Dict[str, Any]:
        row: Dict[str, Any] = {"target": label, "installed": False}
        if getattr(dataset_cls, "_benchmark_length_bucketing_installed", False):
            row["installed"] = True
            row["already_installed"] = True
            return row

        original_numberize = dataset_cls.numberize

        def numberize_bucketed(self: Any, *args: Any, **kwargs: Any) -> Any:
            result = original_numberize(self, *args, **kwargs)
            try:
                self.data = sorted(self.data, key=sort_key)
            except Exception:
                pass
            return result

        dataset_cls._benchmark_original_numberize_for_bucketing = original_numberize
        dataset_cls.numberize = numberize_bucketed
        dataset_cls._benchmark_length_bucketing_installed = True
        row["installed"] = True
        return row

    try:
        from trankit.iterators import ner_iterators, tagger_iterators  # type: ignore

        rows = [
            patch_dataset(tagger_iterators.TaggerDatasetLive, "TaggerDatasetLive"),
            patch_dataset(ner_iterators.NERDatasetLive, "NERDatasetLive"),
        ]
        report["patches"] = rows
        report["installed"] = all(bool(row.get("installed")) for row in rows)
        report["strategy"] = "sort_numberized_examples_by_piece_length"
    except Exception as exc:
        report["error"] = str(exc)
    return report


def _install_onnx_dynamic_batching_patch() -> Dict[str, Any]:
    report: Dict[str, Any] = {
        "installed": False,
        "target": "trankit.pipeline.DataLoader",
        "included_targets": [
            "TokenizeDatasetLive",
            "TaggerDatasetLive",
            "NERDatasetLive",
        ],
        "excluded_targets": [
            "LemmaDataLoader",
            "MWTDataLoader",
        ],
        "seq2seq_dynamic_batching": False,
        "tokenizer_candidates": list(ONNX_DYNAMIC_TOK_BATCH_CANDIDATES),
        "tagger_ner_candidates": list(ONNX_DYNAMIC_TAG_BATCH_CANDIDATES),
        "tokenizer_call_overhead_units": ONNX_DYNAMIC_TOK_CALL_OVERHEAD_UNITS,
        "tagger_ner_call_overhead_units": ONNX_DYNAMIC_TAG_CALL_OVERHEAD_UNITS,
    }

    def get_piece_length(inst: Any) -> int:
        try:
            return int(len(getattr(inst, "piece_idxs", []) or []))
        except Exception:
            return 0

    def stable_sort_key(inst: Any) -> tuple[int, int, int, int, int]:
        piece_len = get_piece_length(inst)
        try:
            word_num = int(getattr(inst, "word_num", getattr(inst, "wordpiece_num", 0)) or 0)
        except Exception:
            word_num = 0
        try:
            paragraph_index = int(getattr(inst, "paragraph_index", 0) or 0)
        except Exception:
            paragraph_index = 0
        try:
            sent_index = int(getattr(inst, "sent_index", 0) or 0)
        except Exception:
            sent_index = 0
        word_ids = getattr(inst, "word_ids", []) or []
        try:
            first_word_id = int(word_ids[0]) if word_ids else 0
        except Exception:
            first_word_id = 0
        return piece_len, word_num, paragraph_index, sent_index, first_word_id

    def candidate_plan(lengths: list[int], batch_size: int, overhead_units: int) -> Dict[str, Any]:
        batches: list[Dict[str, Any]] = []
        padded_units = 0
        real_units = sum(lengths)
        for start in range(0, len(lengths), max(1, batch_size)):
            chunk = lengths[start:start + max(1, batch_size)]
            if not chunk:
                continue
            max_len = max(chunk)
            batch_padded_units = len(chunk) * max_len
            padded_units += batch_padded_units
            batches.append({
                "items": len(chunk),
                "max_len": max_len,
                "padded_units": batch_padded_units,
                "real_units": sum(chunk),
                "padding_units": max(0, batch_padded_units - sum(chunk)),
            })
        call_count = len(batches)
        return {
            "batch_size": batch_size,
            "batch_count": call_count,
            "padded_units": padded_units,
            "real_units": real_units,
            "padding_units": max(0, padded_units - real_units),
            "estimated_cost_units": padded_units + call_count * overhead_units,
            "batches": batches[:80],
        }

    def partition_plan(lengths: list[int], max_batch_size: int, overhead_units: int) -> Dict[str, Any]:
        clean_lengths = [int(length) for length in lengths if isinstance(length, int) and length > 0]
        item_count = len(clean_lengths)
        if not clean_lengths:
            return {
                "algorithm": "dynamic_partition",
                "batch_indices": [],
                "batches": [],
                "batch_count": 0,
                "max_batch_size": int(max_batch_size or 1),
                "padded_units": 0,
                "real_units": 0,
                "padding_units": 0,
                "estimated_cost_units": 0,
            }
        max_size = max(1, min(item_count, int(max_batch_size or 1)))
        prefix = [0]
        for length in clean_lengths:
            prefix.append(prefix[-1] + length)

        dp = [0] + [10**18] * item_count
        prev = [0] * (item_count + 1)
        for end in range(1, item_count + 1):
            best_cost = 10**18
            best_start = end - 1
            start_floor = max(0, end - max_size)
            for start in range(end - 1, start_floor - 1, -1):
                group_len = end - start
                max_len = clean_lengths[end - 1]
                padded_units = group_len * max_len
                cost = dp[start] + padded_units + overhead_units
                if cost < best_cost:
                    best_cost = cost
                    best_start = start
            dp[end] = best_cost
            prev[end] = best_start

        ranges: list[tuple[int, int]] = []
        cursor = item_count
        while cursor > 0:
            start = prev[cursor]
            ranges.append((start, cursor))
            cursor = start
        ranges.reverse()

        batches: list[Dict[str, Any]] = []
        batch_indices: list[list[int]] = []
        padded_total = 0
        real_total = prefix[-1]
        for start, end in ranges:
            chunk = clean_lengths[start:end]
            if not chunk:
                continue
            max_len = max(chunk)
            real_units = prefix[end] - prefix[start]
            padded_units = len(chunk) * max_len
            padded_total += padded_units
            batch_indices.append(list(range(start, end)))
            batches.append({
                "items": len(chunk),
                "max_len": max_len,
                "padded_units": padded_units,
                "real_units": real_units,
                "padding_units": max(0, padded_units - real_units),
            })

        return {
            "algorithm": "dynamic_partition",
            "batch_indices": batch_indices,
            "batches": batches[:80],
            "batch_count": len(batch_indices),
            "batch_sizes": [len(indexes) for indexes in batch_indices],
            "max_batch_size": max_size,
            "padded_units": padded_total,
            "real_units": real_total,
            "padding_units": max(0, padded_total - real_total),
            "estimated_cost_units": padded_total + len(batch_indices) * overhead_units,
        }

    def choose_batch_size(lengths: list[int], candidates: list[int], requested: Optional[int], overhead_units: int) -> Dict[str, Any]:
        clean_lengths = [int(length) for length in lengths if isinstance(length, int) and length > 0]
        if not clean_lengths:
            return {
                "selected_batch_size": int(requested or 1),
                "selected": None,
                "candidates": [],
                "reason": "no lengths",
            }
        max_items = len(clean_lengths)
        candidate_set = {int(value) for value in candidates if isinstance(value, int) and value > 0}
        if requested:
            candidate_set.add(int(requested))
        candidate_set.add(max_items)
        plans = [
            candidate_plan(clean_lengths, min(max_items, size), overhead_units)
            for size in sorted(candidate_set)
            if size > 0
        ]
        if not plans:
            return {
                "selected_batch_size": int(requested or max_items),
                "selected": None,
                "candidates": [],
                "reason": "no candidates",
            }
        max_batch_size = max(int(row.get("batch_size") or 1) for row in plans)
        selected = partition_plan(clean_lengths, max_batch_size, overhead_units)
        slim_plans = [
            {
                "batch_size": row["batch_size"],
                "batch_count": row["batch_count"],
                "padded_units": row["padded_units"],
                "real_units": row["real_units"],
                "padding_units": row["padding_units"],
                "estimated_cost_units": row["estimated_cost_units"],
            }
            for row in plans
        ]
        return {
            "selected_batch_size": int(max(selected.get("batch_sizes") or [max_batch_size])),
            "selected": selected,
            "candidates": slim_plans,
            "reason": "dynamic_partition_min_estimated_cost",
        }

    def dataset_kind(dataset: Any, tokenizer_cls: Any, tagger_cls: Any, ner_cls: Any) -> Optional[str]:
        class_name = dataset.__class__.__name__
        if class_name in {"LemmaDataLoader", "MWTDataLoader"}:
            return None
        try:
            if isinstance(dataset, tokenizer_cls):
                return "tokenizer"
            if isinstance(dataset, tagger_cls):
                return "tagger"
            if isinstance(dataset, ner_cls):
                return "ner"
        except Exception:
            return None
        return None

    def get_requested_batch_size(args: tuple[Any, ...], kwargs: Dict[str, Any]) -> Optional[int]:
        try:
            if "batch_size" in kwargs and kwargs.get("batch_size") is not None:
                return int(kwargs.get("batch_size"))
            if args:
                return int(args[0])
        except Exception:
            return None
        return None

    def set_batch_size(args: tuple[Any, ...], kwargs: Dict[str, Any], batch_size: int) -> tuple[tuple[Any, ...], Dict[str, Any]]:
        clean_kwargs = dict(kwargs)
        if args:
            clean_args = list(args)
            clean_args[0] = batch_size
            return tuple(clean_args), clean_kwargs
        clean_kwargs["batch_size"] = batch_size
        return args, clean_kwargs

    class StaticBatchSampler:
        def __init__(self, batches: list[list[int]]):
            self.batches = [list(batch) for batch in batches if batch]

        def __iter__(self):
            return iter(self.batches)

        def __len__(self) -> int:
            return len(self.batches)

    def set_batch_sampler(args: tuple[Any, ...], kwargs: Dict[str, Any], batches: list[list[int]]) -> tuple[tuple[Any, ...], Dict[str, Any]]:
        clean_kwargs = dict(kwargs)
        if args:
            clean_args = list(args)
            clean_args = clean_args[1:]
        else:
            clean_args = []
        clean_kwargs.pop("batch_size", None)
        clean_kwargs.pop("shuffle", None)
        clean_kwargs.pop("sampler", None)
        clean_kwargs.pop("drop_last", None)
        clean_kwargs["batch_sampler"] = StaticBatchSampler(batches)
        return tuple(clean_args), clean_kwargs

    try:
        import trankit.pipeline as trankit_pipeline  # type: ignore
        from trankit.iterators import ner_iterators, tagger_iterators, tokenizer_iterators  # type: ignore

        if getattr(trankit_pipeline, "_benchmark_dynamic_batching_installed", False):
            report["installed"] = True
            report["already_installed"] = True
            return report

        original_loader = getattr(trankit_pipeline, "DataLoader", None)
        if original_loader is None:
            raise RuntimeError("trankit.pipeline.DataLoader is unavailable")

        tokenizer_cls = tokenizer_iterators.TokenizeDatasetLive
        tagger_cls = tagger_iterators.TaggerDatasetLive
        ner_cls = ner_iterators.NERDatasetLive
        trankit_pipeline._benchmark_dynamic_batch_events = []

        def dynamic_loader(dataset: Any, *args: Any, **kwargs: Any) -> Any:
            kind = dataset_kind(dataset, tokenizer_cls, tagger_cls, ner_cls)
            if not kind:
                return original_loader(dataset, *args, **kwargs)
            if bool(kwargs.get("shuffle")):
                return original_loader(dataset, *args, **kwargs)
            data = getattr(dataset, "data", None)
            if not isinstance(data, list) or not data:
                return original_loader(dataset, *args, **kwargs)

            try:
                sorted_data = sorted(data, key=stable_sort_key)
                dataset.data = sorted_data
            except Exception:
                sorted_data = data
            lengths = [get_piece_length(inst) for inst in sorted_data]
            requested = get_requested_batch_size(args, kwargs)
            if kind == "tokenizer":
                candidates = list(ONNX_DYNAMIC_TOK_BATCH_CANDIDATES)
                overhead_units = ONNX_DYNAMIC_TOK_CALL_OVERHEAD_UNITS
            else:
                candidates = list(ONNX_DYNAMIC_TAG_BATCH_CANDIDATES)
                overhead_units = ONNX_DYNAMIC_TAG_CALL_OVERHEAD_UNITS
            plan = choose_batch_size(lengths, candidates, requested, overhead_units)
            selected_batch_size = int(plan.get("selected_batch_size") or requested or 1)
            selected_plan = plan.get("selected") if isinstance(plan, dict) else None
            batch_indices = selected_plan.get("batch_indices") if isinstance(selected_plan, dict) else None
            if isinstance(batch_indices, list) and batch_indices:
                new_args, new_kwargs = set_batch_sampler(args, kwargs, batch_indices)
            else:
                new_args, new_kwargs = set_batch_size(args, kwargs, selected_batch_size)
            event = {
                "kind": kind,
                "item_count": len(lengths),
                "requested_batch_size": requested,
                "selected_batch_size": selected_batch_size,
                "overhead_units": overhead_units,
                "length_min": min(lengths) if lengths else None,
                "length_max": max(lengths) if lengths else None,
                "length_total": sum(lengths),
                "plan": plan,
            }
            try:
                events = getattr(trankit_pipeline, "_benchmark_dynamic_batch_events", None)
                if isinstance(events, list):
                    events.append(event)
            except Exception:
                pass
            return original_loader(dataset, *new_args, **new_kwargs)

        trankit_pipeline._benchmark_original_dataloader = original_loader
        trankit_pipeline.DataLoader = dynamic_loader
        trankit_pipeline._benchmark_dynamic_batching_installed = True
        report["installed"] = True
        report["strategy"] = "sort_by_piece_length_and_choose_min_estimated_padding_cost"
    except Exception as exc:
        report["error"] = str(exc)
    return report


def _cpu_opt_batch_candidates() -> list[tuple[int, int]]:
    return [
        (2, 12),
        (4, 16),
        (6, 24),
        (8, 32),
        (12, 48),
        (16, 64),
    ]


def _cpu_opt_tuning_command() -> Dict[str, Any]:
    return {
        "type": "analyze",
        "request_id": "cpu-opt-startup-tune",
        "lang": "fr",
        "trankit_override": "",
        "manual_sentence_segmentation": False,
        "strip_punctuation": False,
        "text": CPU_OPT_TUNE_TEXT,
    }


def _cpu_opt_bucket_text(bucket: int) -> str:
    unit = "Ceci est une phrase francaise de calibrage pour mesurer le chemin XLM-R CPU optimise. "
    try:
        repeat_count = max(1, int(bucket) // 16)
    except Exception:
        repeat_count = 1
    return (unit * repeat_count).strip()


def _cpu_opt_bucket_command(bucket: int) -> Dict[str, Any]:
    command = _cpu_opt_tuning_command()
    command["request_id"] = f"cpu-opt-bucket-{bucket}"
    command["text"] = _cpu_opt_bucket_text(bucket)
    command["bucket"] = bucket
    return command


def _percentile(values: list[float], percentile: float) -> Optional[float]:
    cleaned = sorted(float(value) for value in values if isinstance(value, (int, float)) and value >= 0)
    if not cleaned:
        return None
    if len(cleaned) == 1:
        return cleaned[0]
    rank = (len(cleaned) - 1) * max(0.0, min(100.0, percentile)) / 100.0
    lower = int(rank)
    upper = min(lower + 1, len(cleaned) - 1)
    fraction = rank - lower
    return cleaned[lower] + (cleaned[upper] - cleaned[lower]) * fraction


def _measure_cpu_opt_tuning_case(
    lr: Any,
    run_with_universal_normalization: Any,
    torch_module: Any,
    command: Dict[str, Any],
    profile: str,
    repetitions: int = CPU_OPT_TUNE_REPETITIONS,
) -> Dict[str, Any]:
    samples: list[float] = []
    doc: Dict[str, Any] = {}
    lang_code = ""
    gc_calls = 0
    cuda_empty_cache_calls = 0
    total_started = time.perf_counter()
    for _ in range(max(1, int(repetitions))):
        started = time.perf_counter()
        doc, lang_code, gc_run_calls, cuda_run_calls, _sync_report = _run_analysis_command(
            lr,
            run_with_universal_normalization,
            torch_module,
            command,
            use_gpu=False,
            optimized_cpu=True,
            bf16_autocast=_cpu_profile_uses_bf16(profile),
        )
        samples.append(time.perf_counter() - started)
        gc_calls += int(gc_run_calls or 0)
        cuda_empty_cache_calls += int(cuda_run_calls or 0)
    counts = _annotation_counts(doc)
    return {
        "ok": True,
        "elapsed_seconds": samples[-1] if samples else None,
        "elapsed_samples_seconds": samples,
        "p50_seconds": _percentile(samples, 50),
        "p95_seconds": _percentile(samples, 95),
        "total_measure_seconds": time.perf_counter() - total_started,
        "lang": lang_code,
        "fingerprint": _annotation_fingerprint(doc),
        "counts": counts,
        "sequence_bucket": _sequence_bucket_for_token_count(counts.get("token_count")),
        "gc_collect_calls_suppressed": gc_calls,
        "cuda_empty_cache_calls_suppressed": cuda_empty_cache_calls,
    }


def _startup_tune_cpu_opt_runtime(
    lr: Any,
    run_with_universal_normalization: Any,
    torch_module: Any,
    pipeline_obj: Any,
    profile: str,
    initial_thread_count: int,
) -> Dict[str, Any]:
    started = time.perf_counter()
    command = _cpu_opt_tuning_command()
    report: Dict[str, Any] = {
        "ok": True,
        "text_chars": len(str(command.get("text") or "")),
        "repetitions_per_case": CPU_OPT_TUNE_REPETITIONS,
        "thread_results": [],
        "bucket_results": [],
        "batch_results": [{"skipped": True, "reason": "This pass does not tune Trankit batch sizes."}],
        "warmup": None,
        "selected_thread_count": initial_thread_count,
        "selected_tok_batch_size": CPU_OPT_DEFAULT_TOK_BATCH_SIZE,
        "selected_tag_batch_size": CPU_OPT_DEFAULT_TAG_BATCH_SIZE,
    }

    _apply_cpu_opt_batch_sizes(pipeline_obj, CPU_OPT_DEFAULT_TOK_BATCH_SIZE, CPU_OPT_DEFAULT_TAG_BATCH_SIZE)
    try:
        report["warmup"] = _measure_cpu_opt_tuning_case(
            lr,
            run_with_universal_normalization,
            torch_module,
            command,
            profile,
        )
    except Exception as exc:
        report["warmup"] = {"ok": False, "error": str(exc)}

    best_thread = max(1, int(initial_thread_count or 1))
    best_thread_p95 = None
    for thread_count in _cpu_thread_candidates():
        row: Dict[str, Any] = {"thread_count": thread_count}
        row["thread_report"] = _set_torch_cpu_threads(torch_module, thread_count)
        try:
            measured = _measure_cpu_opt_tuning_case(
                lr,
                run_with_universal_normalization,
                torch_module,
                command,
                profile,
            )
            row.update(measured)
            elapsed = measured.get("p95_seconds")
            if isinstance(elapsed, (int, float)) and elapsed > 0 and (best_thread_p95 is None or elapsed < best_thread_p95):
                best_thread_p95 = float(elapsed)
                best_thread = thread_count
        except Exception as exc:
            row.update({"ok": False, "error": str(exc)})
        report["thread_results"].append(row)

    report["selected_thread_count"] = best_thread
    report["selected_thread_p95_seconds"] = best_thread_p95
    report["selected_thread_seconds"] = best_thread_p95
    report["selected_thread_report"] = _set_torch_cpu_threads(torch_module, best_thread)

    for bucket in CPU_OPT_SEQUENCE_BUCKETS:
        row = {"bucket": bucket}
        try:
            measured = _measure_cpu_opt_tuning_case(
                lr,
                run_with_universal_normalization,
                torch_module,
                _cpu_opt_bucket_command(bucket),
                profile,
            )
            row.update(measured)
        except Exception as exc:
            row.update({"ok": False, "error": str(exc)})
        report["bucket_results"].append(row)

    report["selected_tok_batch_size"] = CPU_OPT_DEFAULT_TOK_BATCH_SIZE
    report["selected_tag_batch_size"] = CPU_OPT_DEFAULT_TAG_BATCH_SIZE
    report["selected_batch_seconds"] = None
    report["selected_batch_report"] = _apply_cpu_opt_batch_sizes(
        pipeline_obj,
        CPU_OPT_DEFAULT_TOK_BATCH_SIZE,
        CPU_OPT_DEFAULT_TAG_BATCH_SIZE,
    )
    report["elapsed_seconds"] = time.perf_counter() - started
    return report


def _worker_main(
    device_label: str,
    use_gpu: bool,
    command_queue: mp.Queue,
    result_queue: mp.Queue,
    optimized_cpu: bool = False,
    optimized_gpu: bool = False,
    onnx_cpu: bool = False,
    cpu_opt_profile: str = "runtime_patches",
    cpu_opt_thread_count: Optional[int] = None,
    cpu_opt_tok_batch_size: Optional[int] = None,
    cpu_opt_tag_batch_size: Optional[int] = None,
    cpu_opt_skip_startup_tuning: bool = False,
) -> None:
    pid = os.getpid()
    torch_module = None
    onnx_report_for_error: Dict[str, Any] = {}

    def send_status(state: str, extra: Optional[Dict[str, Any]] = None) -> None:
        payload = {
            "type": "status",
            "device": device_label,
            "state": state,
            "pid": pid,
            "time": time.time(),
        }
        if extra:
            payload.update(extra)
        result_queue.put(payload)

    try:
        _force_gc()
        rss_process_start = current_rss_bytes()
        load_started = time.perf_counter()
        send_status("loading", {"rss_process_start_bytes": rss_process_start})

        deps_path_active = False
        thread_report: Dict[str, Any] = {}
        if optimized_cpu:
            deps_path_active = False
            if cpu_opt_thread_count is not None:
                _set_cpu_thread_environment(cpu_opt_thread_count)

        import torch  # type: ignore

        if optimized_cpu and cpu_opt_thread_count is not None:
            thread_report = _set_torch_cpu_threads(torch, cpu_opt_thread_count)
            thread_report["backend"] = _configure_cpu_torch_backend(torch)

        _install_forced_trankit_pipeline(use_gpu)
        onnx_tokenizer_padding_report: Dict[str, Any] = {}
        onnx_tagger_ner_bucketing_report: Dict[str, Any] = {}
        onnx_dynamic_batching_report: Dict[str, Any] = {}
        if onnx_cpu:
            onnx_tokenizer_padding_report = _install_onnx_tokenizer_dynamic_padding_patch()
            if not onnx_tokenizer_padding_report.get("installed"):
                raise RuntimeError(
                    "ONNX tokenizer dynamic padding patch failed: "
                    f"{onnx_tokenizer_padding_report.get('error') or 'unknown error'}"
                )
            onnx_tagger_ner_bucketing_report = _install_onnx_tagger_ner_length_bucketing_patch()
            if not onnx_tagger_ner_bucketing_report.get("installed"):
                raise RuntimeError(
                    "ONNX POS/NER length bucketing patch failed: "
                    f"{onnx_tagger_ner_bucketing_report.get('error') or 'unknown error'}"
                )
            onnx_dynamic_batching_report = _install_onnx_dynamic_batching_patch()
            if not onnx_dynamic_batching_report.get("installed"):
                raise RuntimeError(
                    "ONNX dynamic batching patch failed: "
                    f"{onnx_dynamic_batching_report.get('error') or 'unknown error'}"
                )
        xlmr_load_patch_report: Dict[str, Any] = {}
        if optimized_cpu or optimized_gpu or onnx_cpu:
            xlmr_load_patch_report = _install_cpu_opt_xlmr_load_patch()

        import language_registry as lr
        from universal_normalization import run_with_universal_normalization

        torch_module = torch
        gpu_before_load = _gpu_snapshot(torch_module)
        rss_after_imports = current_rss_bytes()

        lr.init_trankit()
        optimization_report: Dict[str, Any] = {}
        onnx_report: Dict[str, Any] = {}
        onnx_batch_size_report: Dict[str, Any] = {}
        startup_cache_save_report: Dict[str, Any] = {}
        startup_tuning_report: Dict[str, Any] = {}
        startup_validation_report: Dict[str, Any] = {}
        gpu_optimization_report: Dict[str, Any] = {}
        gpu_startup_warmup_report: Dict[str, Any] = {}
        startup_selection_payload: Optional[Dict[str, Any]] = None
        optimization_started = time.perf_counter()
        if optimized_cpu:
            try:
                startup_validation_report["baseline"] = _measure_cpu_opt_tuning_case(
                    lr,
                    run_with_universal_normalization,
                    torch_module,
                    _cpu_opt_tuning_command(),
                    "runtime_patches",
                    repetitions=1,
                )
            except Exception as exc:
                startup_validation_report["baseline"] = {"ok": False, "error": str(exc)}
            optimization_report = _apply_cpu_optimization_profile(
                getattr(lr, "_trankit_pipeline", None),
                torch_module,
                cpu_opt_profile,
            )
            if optimization_report.get("errors"):
                raise RuntimeError("; ".join(str(error) for error in optimization_report.get("errors") or []))
            startup_cache_save_report = _save_cpu_opt_module_caches(
                getattr(lr, "_trankit_pipeline", None),
                torch_module,
                cpu_opt_profile,
                optimization_report,
            )
            if cpu_opt_skip_startup_tuning and cpu_opt_tok_batch_size is not None and cpu_opt_tag_batch_size is not None:
                startup_tuning_report = {
                    "ok": True,
                    "from_cache": True,
                    "selected_thread_count": int(cpu_opt_thread_count or 1),
                    "selected_tok_batch_size": int(cpu_opt_tok_batch_size),
                    "selected_tag_batch_size": int(cpu_opt_tag_batch_size),
                    "selected_batch_report": _apply_cpu_opt_batch_sizes(
                        getattr(lr, "_trankit_pipeline", None),
                        int(cpu_opt_tok_batch_size),
                        int(cpu_opt_tag_batch_size),
                    ),
                    "elapsed_seconds": 0.0,
                }
            else:
                startup_tuning_report = _startup_tune_cpu_opt_runtime(
                    lr,
                    run_with_universal_normalization,
                    torch_module,
                    getattr(lr, "_trankit_pipeline", None),
                    cpu_opt_profile,
                    int(cpu_opt_thread_count or 1),
                )
                startup_selection_payload = {
                    "selected_profile": cpu_opt_profile,
                    "selected_thread_count": int(startup_tuning_report.get("selected_thread_count") or cpu_opt_thread_count or 1),
                    "selected_tok_batch_size": int(startup_tuning_report.get("selected_tok_batch_size") or CPU_OPT_DEFAULT_TOK_BATCH_SIZE),
                    "selected_tag_batch_size": int(startup_tuning_report.get("selected_tag_batch_size") or CPU_OPT_DEFAULT_TAG_BATCH_SIZE),
                    "selected_thread_seconds": startup_tuning_report.get("selected_thread_seconds"),
                    "selected_thread_p95_seconds": startup_tuning_report.get("selected_thread_p95_seconds"),
                    "selected_batch_seconds": startup_tuning_report.get("selected_batch_seconds"),
                    "selected_p95_seconds": startup_tuning_report.get("selected_thread_p95_seconds"),
                    "setup_seconds": startup_tuning_report.get("elapsed_seconds"),
                }
            try:
                startup_validation_report["optimized"] = _measure_cpu_opt_tuning_case(
                    lr,
                    run_with_universal_normalization,
                    torch_module,
                    _cpu_opt_tuning_command(),
                    cpu_opt_profile,
                    repetitions=1,
                )
            except Exception as exc:
                startup_validation_report["optimized"] = {"ok": False, "error": str(exc)}
            baseline_fingerprint = ""
            optimized_fingerprint = ""
            try:
                baseline_fingerprint = str((startup_validation_report.get("baseline") or {}).get("fingerprint") or "")
                optimized_fingerprint = str((startup_validation_report.get("optimized") or {}).get("fingerprint") or "")
            except Exception:
                pass
            startup_validation_report["baseline_fingerprint"] = baseline_fingerprint
            startup_validation_report["optimized_fingerprint"] = optimized_fingerprint
            startup_validation_report["output_match"] = bool(
                baseline_fingerprint and optimized_fingerprint and baseline_fingerprint == optimized_fingerprint
            )
            if baseline_fingerprint and optimized_fingerprint and baseline_fingerprint != optimized_fingerprint:
                startup_validation_report["warning"] = (
                    "Optimized CPU startup validation found an annotation fingerprint difference from baseline CPU. "
                    "The worker remains active so the discrepancy pane can show real output differences."
                )
            if startup_selection_payload is not None:
                startup_selection_payload["baseline_fingerprint"] = baseline_fingerprint
                startup_selection_payload["selected_fingerprint"] = optimized_fingerprint
                startup_selection_payload["output_match"] = bool(
                    baseline_fingerprint and optimized_fingerprint and baseline_fingerprint == optimized_fingerprint
                )
                try:
                    _write_cpu_opt_selection_cache(startup_selection_payload)
                    startup_tuning_report["selection_cache_written"] = True
                    startup_tuning_report["selection_cache_path"] = CPU_OPT_SELECTION_CACHE_PATH
                except Exception as exc:
                    startup_tuning_report["selection_cache_write_error"] = str(exc)
            cpu_opt_thread_count = int(startup_tuning_report.get("selected_thread_count") or cpu_opt_thread_count or 1)
            cpu_opt_tok_batch_size = int(startup_tuning_report.get("selected_tok_batch_size") or CPU_OPT_DEFAULT_TOK_BATCH_SIZE)
            cpu_opt_tag_batch_size = int(startup_tuning_report.get("selected_tag_batch_size") or CPU_OPT_DEFAULT_TAG_BATCH_SIZE)
        if optimized_gpu:
            gpu_optimization_report = _apply_gpu_optimization_profile(
                getattr(lr, "_trankit_pipeline", None),
                torch_module,
            )
            if gpu_optimization_report.get("errors"):
                raise RuntimeError("; ".join(str(error) for error in gpu_optimization_report.get("errors") or []))
            gpu_startup_warmup_report = _gpu_opt_startup_warmup(
                lr,
                run_with_universal_normalization,
                torch_module,
            )
        if onnx_cpu:
            onnx_report = _install_onnx_xlmr_runtime(
                getattr(lr, "_trankit_pipeline", None),
                torch_module,
            )
            onnx_report_for_error = onnx_report
            if not onnx_report.get("installed"):
                raise RuntimeError(
                    "ONNX XLM-R runtime did not install completely: "
                    f"{onnx_report.get('session_count')}/{onnx_report.get('task_count')} sessions. "
                    f"Errors: {onnx_report.get('errors')}"
                )
            onnx_batch_size_report = _apply_cpu_opt_batch_sizes(
                getattr(lr, "_trankit_pipeline", None),
                ONNX_CPU_TOK_BATCH_SIZE,
                ONNX_CPU_TAG_BATCH_SIZE,
            )
        optimization_seconds = time.perf_counter() - optimization_started

        actual_device = ""
        actual_use_gpu = None
        try:
            actual_device = str(lr._trankit_pipeline._config.device)
            actual_use_gpu = bool(lr._trankit_pipeline._use_gpu)
        except Exception:
            pass

        _force_gc()
        if use_gpu and torch_module.cuda.is_available():
            torch_module.cuda.synchronize()
        rss_after_load = current_rss_bytes()
        gpu_after_load = _gpu_snapshot(torch_module)
        load_metrics = {
            "requested_device": device_label,
            "requested_gpu": use_gpu,
            "actual_device": actual_device,
            "actual_use_gpu": actual_use_gpu,
            "pid": pid,
            "load_seconds": time.perf_counter() - load_started,
            "rss_process_start_bytes": rss_process_start,
            "rss_after_imports_bytes": rss_after_imports,
            "rss_after_load_bytes": rss_after_load,
            "rss_import_delta_bytes": _bytes_delta(rss_after_imports, rss_process_start),
            "rss_loaded_pipeline_delta_bytes": _bytes_delta(rss_after_load, rss_after_imports),
            "rss_total_load_delta_bytes": _bytes_delta(rss_after_load, rss_process_start),
            "gpu_before_load": gpu_before_load,
            "gpu_after_load": gpu_after_load,
            "gpu_load_delta": _gpu_delta(gpu_after_load, gpu_before_load),
        }
        if optimized_cpu:
            load_metrics["optimized_cpu"] = True
            load_metrics["cpu_opt_profile"] = cpu_opt_profile
            load_metrics["cpu_opt_thread_count"] = cpu_opt_thread_count
            load_metrics["cpu_opt_thread_report"] = thread_report
            load_metrics["cpu_opt_deps_path"] = CPU_OPT_DEPS_DIR
            load_metrics["cpu_opt_deps_path_active"] = deps_path_active
            load_metrics["xlmr_load_patch_report"] = xlmr_load_patch_report
            load_metrics["optimization_seconds"] = optimization_seconds
            load_metrics["optimization_report"] = optimization_report
            load_metrics["startup_cache_save_report"] = startup_cache_save_report
            load_metrics["startup_tuning_report"] = startup_tuning_report
            load_metrics["startup_validation_report"] = startup_validation_report
            load_metrics["cpu_opt_thread_count"] = cpu_opt_thread_count
            load_metrics["cpu_opt_tok_batch_size"] = cpu_opt_tok_batch_size
            load_metrics["cpu_opt_tag_batch_size"] = cpu_opt_tag_batch_size
        if optimized_gpu:
            load_metrics["optimized_gpu"] = True
            load_metrics["gpu_opt_profile"] = GPU_OPT_PROFILE_NAME
            load_metrics["xlmr_load_patch_report"] = xlmr_load_patch_report
            load_metrics["optimization_seconds"] = optimization_seconds
            load_metrics["optimization_report"] = gpu_optimization_report
            load_metrics["startup_warmup_report"] = gpu_startup_warmup_report
        if onnx_cpu:
            load_metrics["onnx_cpu"] = True
            load_metrics["onnx_profile"] = ONNX_PROFILE_NAME
            load_metrics["onnx_tok_batch_size"] = ONNX_CPU_TOK_BATCH_SIZE
            load_metrics["onnx_tag_batch_size"] = ONNX_CPU_TAG_BATCH_SIZE
            load_metrics["onnx_batch_size_report"] = onnx_batch_size_report
            load_metrics["onnx_tokenizer_padding_report"] = onnx_tokenizer_padding_report
            load_metrics["onnx_tagger_ner_bucketing_report"] = onnx_tagger_ner_bucketing_report
            load_metrics["onnx_dynamic_batching_report"] = onnx_dynamic_batching_report
            load_metrics["xlmr_load_patch_report"] = xlmr_load_patch_report
            load_metrics["optimization_seconds"] = optimization_seconds
            load_metrics["onnx_report"] = onnx_report
        send_status("ready", {"load_metrics": load_metrics})

        while True:
            command = command_queue.get()
            if not isinstance(command, dict):
                continue
            command_type = command.get("type")
            if command_type == "shutdown":
                send_status("stopped")
                return
            if command_type != "analyze":
                continue

            request_id = str(command.get("request_id") or "")
            text = str(command.get("text") or "")

            try:
                optimized_request = optimized_cpu or optimized_gpu or onnx_cpu
                if not optimized_request:
                    _force_gc()
                if torch_module is not None and use_gpu and torch_module.cuda.is_available():
                    if not optimized_request:
                        torch_module.cuda.empty_cache()
                    torch_module.cuda.reset_peak_memory_stats()
                    torch_module.cuda.synchronize()

                rss_before = current_rss_bytes()
                gpu_before = _gpu_snapshot(torch_module)
                sampler = MemorySampler(torch_module)
                onnx_runtime_manager = None
                onnx_run_count_before: Optional[int] = None
                onnx_runtime_metrics_before: Optional[Dict[str, Any]] = None
                if onnx_cpu:
                    onnx_runtime_manager = getattr(getattr(lr, "_trankit_pipeline", None), "_compressed_xlmr_runtime", None)
                    if onnx_runtime_manager is not None:
                        try:
                            onnx_runtime_metrics_before = onnx_runtime_manager.metrics() or {}
                            onnx_run_count_before = int(onnx_runtime_metrics_before.get("run_count") or 0)
                        except Exception:
                            onnx_run_count_before = None
                            onnx_runtime_metrics_before = None
                    try:
                        import trankit.pipeline as trankit_pipeline  # type: ignore

                        trankit_pipeline._benchmark_dynamic_batch_events = []
                    except Exception:
                        pass
                started = time.perf_counter()
                sampler.start()
                doc, lang_code, gc_collect_calls, cuda_empty_cache_calls, sync_point_report, task_breakdown_report = _run_analysis_command(
                    lr,
                    run_with_universal_normalization,
                    torch_module,
                    command,
                    use_gpu=use_gpu,
                    optimized_cpu=optimized_request,
                    optimized_gpu=optimized_gpu,
                    bf16_autocast=_cpu_profile_uses_bf16(cpu_opt_profile),
                )
                if torch_module is not None and use_gpu and torch_module.cuda.is_available():
                    torch_module.cuda.synchronize()
                elapsed = time.perf_counter() - started
                sampler.stop()

                if not optimized_request:
                    _force_gc()
                rss_after = current_rss_bytes()
                gpu_after = _gpu_snapshot(torch_module)
                fingerprint = _annotation_fingerprint(doc)
                annotation_counts = _annotation_counts(doc)
                sequence_bucket = _sequence_bucket_for_token_count(annotation_counts.get("token_count"))
                inference_metrics = {
                    "request_id": request_id,
                    "device": device_label,
                    "pid": pid,
                    "lang": lang_code,
                    "text_chars": len(text),
                    "elapsed_seconds": elapsed,
                    "rss_before_bytes": rss_before,
                    "rss_after_bytes": rss_after,
                    "rss_delta_bytes": _bytes_delta(rss_after, rss_before),
                    "rss_peak_sampled_bytes": sampler.rss_peak_bytes,
                    "rss_peak_sampled_delta_bytes": _bytes_delta(sampler.rss_peak_bytes, rss_before),
                    "sample_count": sampler.samples,
                    "gpu_before": gpu_before,
                    "gpu_after": gpu_after,
                    "gpu_delta": _gpu_delta(gpu_after, gpu_before),
                    "gpu_allocated_peak_sampled_bytes": sampler.gpu_allocated_peak_bytes,
                    "gpu_reserved_peak_sampled_bytes": sampler.gpu_reserved_peak_bytes,
                    "gpu_allocator_max_allocated_bytes": gpu_after.get("max_allocated_bytes"),
                    "gpu_allocator_max_reserved_bytes": gpu_after.get("max_reserved_bytes"),
                    "output_fingerprint": fingerprint,
                    "annotation_counts": annotation_counts,
                    "sequence_bucket": sequence_bucket,
                    "sync_points": sync_point_report,
                    "task_breakdown": task_breakdown_report,
                }
                if optimized_cpu:
                    inference_metrics["optimized_cpu"] = True
                    inference_metrics["cpu_opt_profile"] = cpu_opt_profile
                    inference_metrics["cpu_opt_thread_count"] = cpu_opt_thread_count
                    inference_metrics["cpu_opt_tok_batch_size"] = getattr(getattr(lr, "_trankit_pipeline", None), "_tokbatchsize", None)
                    inference_metrics["cpu_opt_tag_batch_size"] = getattr(getattr(lr, "_trankit_pipeline", None), "_tagbatchsize", None)
                    inference_metrics["gc_collect_calls_suppressed"] = gc_collect_calls
                    inference_metrics["cuda_empty_cache_calls_suppressed"] = cuda_empty_cache_calls
                    inference_metrics["used_inference_mode"] = True
                    inference_metrics["used_bf16_autocast"] = _cpu_profile_uses_bf16(cpu_opt_profile)
                if optimized_gpu:
                    inference_metrics["optimized_gpu"] = True
                    inference_metrics["gpu_opt_profile"] = GPU_OPT_PROFILE_NAME
                    inference_metrics["gc_collect_calls_suppressed"] = gc_collect_calls
                    inference_metrics["cuda_empty_cache_calls_suppressed"] = cuda_empty_cache_calls
                    inference_metrics["used_inference_mode"] = True
                if onnx_cpu:
                    manager = onnx_runtime_manager or getattr(getattr(lr, "_trankit_pipeline", None), "_compressed_xlmr_runtime", None)
                    runtime_metrics = manager.metrics() if manager is not None else None
                    if isinstance(runtime_metrics, dict) and onnx_run_count_before is not None:
                        try:
                            onnx_run_count_after = int(runtime_metrics.get("run_count") or 0)
                            runtime_metrics["request_run_count"] = max(0, onnx_run_count_after - onnx_run_count_before)
                            runtime_metrics["lifetime_run_count"] = onnx_run_count_after
                            if isinstance(onnx_runtime_metrics_before, dict):
                                request_by_key: Dict[str, Dict[str, Any]] = {}
                                before_by_key = onnx_runtime_metrics_before.get("by_key") or {}
                                after_by_key = runtime_metrics.get("by_key") or {}
                                if isinstance(after_by_key, dict):
                                    timing_fields = [
                                        "count",
                                        "total_seconds",
                                        "preprocess_seconds",
                                        "session_seconds",
                                        "postprocess_seconds",
                                    ]
                                    for key, after_row in after_by_key.items():
                                        if not isinstance(after_row, dict):
                                            continue
                                        before_row = before_by_key.get(key) if isinstance(before_by_key, dict) else None
                                        before_row = before_row if isinstance(before_row, dict) else {}
                                        delta_row: Dict[str, Any] = {}
                                        for field in timing_fields:
                                            after_value = after_row.get(field) or 0
                                            before_value = before_row.get(field) or 0
                                            try:
                                                value = float(after_value) - float(before_value)
                                            except Exception:
                                                value = 0.0
                                            if field == "count":
                                                delta_row[field] = max(0, int(round(value)))
                                            else:
                                                delta_row[field] = max(0.0, value)
                                        if int(delta_row.get("count") or 0) > 0:
                                            request_by_key[str(key)] = delta_row
                                runtime_metrics["request_by_key"] = request_by_key
                                for field in ["total_seconds", "preprocess_seconds", "session_seconds", "postprocess_seconds"]:
                                    try:
                                        runtime_metrics[f"request_{field}"] = max(
                                            0.0,
                                            float(runtime_metrics.get(field) or 0.0)
                                            - float(onnx_runtime_metrics_before.get(field) or 0.0),
                                        )
                                    except Exception:
                                        pass
                        except Exception:
                            pass
                    inference_metrics["onnx_cpu"] = True
                    inference_metrics["onnx_profile"] = ONNX_PROFILE_NAME
                    inference_metrics["onnx_runtime"] = runtime_metrics
                    inference_metrics["onnx_tok_batch_size"] = getattr(getattr(lr, "_trankit_pipeline", None), "_tokbatchsize", None)
                    inference_metrics["onnx_tag_batch_size"] = getattr(getattr(lr, "_trankit_pipeline", None), "_tagbatchsize", None)
                    inference_metrics["onnx_tokenizer_dynamic_padding"] = True
                    inference_metrics["onnx_tagger_ner_length_bucketing"] = True
                    inference_metrics["onnx_dynamic_batching"] = True
                    inference_metrics["onnx_seq2seq_dynamic_batching"] = False
                    try:
                        import trankit.pipeline as trankit_pipeline  # type: ignore

                        events = getattr(trankit_pipeline, "_benchmark_dynamic_batch_events", [])
                        inference_metrics["onnx_dynamic_batch_events"] = events if isinstance(events, list) else []
                    except Exception as exc:
                        inference_metrics["onnx_dynamic_batch_events_error"] = str(exc)
                    inference_metrics["gc_collect_calls_suppressed"] = gc_collect_calls
                    inference_metrics["cuda_empty_cache_calls_suppressed"] = cuda_empty_cache_calls
                    inference_metrics["used_inference_mode"] = True
                result_queue.put({
                    "type": "result",
                    "device": device_label,
                    "request_id": request_id,
                    "ok": True,
                    "annotations": doc,
                    "metrics": inference_metrics,
                })
            except Exception as exc:
                result_queue.put({
                    "type": "result",
                    "device": device_label,
                    "request_id": request_id,
                    "ok": False,
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                })
    except Exception as exc:
        extra = {"error": str(exc), "traceback": traceback.format_exc()}
        if onnx_report_for_error:
            extra["onnx_report"] = onnx_report_for_error
        send_status("error", extra)


def _cpu_opt_candidate_worker_main(
    profile: str,
    thread_count: int,
    command: Dict[str, Any],
    result_queue: mp.Queue,
) -> None:
    started = time.perf_counter()
    torch_module = None
    try:
        deps_path_active = profile in {"ipex_xlmr", "onnx_xlmr", "onnx_int8_xlmr"} and _prepend_cpu_opt_deps()
        _set_cpu_thread_environment(thread_count)

        import torch  # type: ignore

        torch_module = torch
        thread_report = _set_torch_cpu_threads(torch_module, thread_count)
        thread_report["backend"] = _configure_cpu_torch_backend(torch_module)

        if profile == "bf16_autocast":
            bf16_probe = _detect_cpu_bf16_support(torch_module)
            if not bool(bf16_probe.get("supported")):
                result_queue.put({
                    "ok": False,
                    "skipped": True,
                    "profile": profile,
                    "thread_count": thread_count,
                    "error": str(bf16_probe.get("reason") or "CPU BF16 support was not detected"),
                    "bf16_probe": bf16_probe,
                    "elapsed_seconds": time.perf_counter() - started,
                    "deps_path_active": deps_path_active,
                    "thread_report": thread_report,
                })
                return

        if profile in {"onnx_xlmr", "onnx_int8_xlmr"}:
            try:
                import onnxruntime  # type: ignore  # noqa: F401

                skip_error = (
                    "ONNX Runtime is importable, but XLM-R ONNX replacement is not safely wired in v1 "
                    "because Trankit mutates adapter state through load_state_dict during inference."
                )
            except Exception as exc:
                skip_error = f"ONNX Runtime unavailable in isolated deps: {exc}"
            result_queue.put({
                "ok": False,
                "skipped": True,
                "profile": profile,
                "thread_count": thread_count,
                "error": skip_error,
                "elapsed_seconds": time.perf_counter() - started,
                "deps_path_active": deps_path_active,
            })
            return

        _install_forced_trankit_pipeline(False)
        _install_cpu_opt_xlmr_load_patch()

        import language_registry as lr
        from universal_normalization import run_with_universal_normalization

        lr.init_trankit()
        apply_started = time.perf_counter()
        optimization_report = _apply_cpu_optimization_profile(
            getattr(lr, "_trankit_pipeline", None),
            torch_module,
            profile,
        )
        batch_report = _apply_cpu_opt_batch_sizes(
            getattr(lr, "_trankit_pipeline", None),
            CPU_OPT_DEFAULT_TOK_BATCH_SIZE,
            CPU_OPT_DEFAULT_TAG_BATCH_SIZE,
        )
        apply_seconds = time.perf_counter() - apply_started
        if optimization_report.get("errors"):
            result_queue.put({
                "ok": False,
                "profile": profile,
                "thread_count": thread_count,
                "error": "; ".join(str(e) for e in optimization_report.get("errors") or []),
                "optimization_report": optimization_report,
                "apply_seconds": apply_seconds,
                "elapsed_seconds": time.perf_counter() - started,
                "deps_path_active": deps_path_active,
                "thread_report": thread_report,
            })
            return

        rss_before = current_rss_bytes()
        measure_started = time.perf_counter()
        doc, lang_code, gc_collect_calls, cuda_empty_cache_calls, _sync_report = _run_analysis_command(
            lr,
            run_with_universal_normalization,
            torch_module,
            command,
            use_gpu=False,
            optimized_cpu=True,
            bf16_autocast=_cpu_profile_uses_bf16(profile),
        )
        measure_seconds = time.perf_counter() - measure_started
        rss_after = current_rss_bytes()
        result_queue.put({
            "ok": True,
            "profile": profile,
            "thread_count": thread_count,
            "lang": lang_code,
            "elapsed_seconds": measure_seconds,
            "total_process_seconds": time.perf_counter() - started,
            "apply_seconds": apply_seconds,
            "rss_before_bytes": rss_before,
            "rss_after_bytes": rss_after,
            "rss_delta_bytes": _bytes_delta(rss_after, rss_before),
            "output_fingerprint": _annotation_fingerprint(doc),
            "annotation_counts": _annotation_counts(doc),
            "optimization_report": optimization_report,
            "batch_report": batch_report,
            "cache_save_report": _save_cpu_opt_module_caches(
                getattr(lr, "_trankit_pipeline", None),
                torch_module,
                profile,
                optimization_report,
            ),
            "deps_path_active": deps_path_active,
            "thread_report": thread_report,
            "gc_collect_calls_suppressed": gc_collect_calls,
            "cuda_empty_cache_calls_suppressed": cuda_empty_cache_calls,
        })
    except Exception as exc:
        result_queue.put({
            "ok": False,
            "profile": profile,
            "thread_count": thread_count,
            "elapsed_seconds": time.perf_counter() - started,
            "rss_after_bytes": current_rss_bytes(),
            "gpu_after": _gpu_snapshot(torch_module),
            "error": str(exc),
            "traceback": traceback.format_exc(),
        })


def _run_cpu_opt_candidate_process(profile: str, thread_count: int, command: Dict[str, Any]) -> Dict[str, Any]:
    ctx = mp.get_context("spawn")
    result_queue = ctx.Queue()
    process_started = time.perf_counter()
    process = ctx.Process(
        target=_cpu_opt_candidate_worker_main,
        args=(profile, thread_count, command, result_queue),
        daemon=False,
    )
    process.start()
    try:
        result = result_queue.get(timeout=CPU_OPT_PROFILE_TIMEOUT_SECONDS)
    except queue.Empty:
        result = {
            "ok": False,
            "profile": profile,
            "thread_count": thread_count,
            "pid": process.pid,
            "error": "CPU optimization candidate timed out",
        }
    finally:
        process.join(timeout=5)
        if process.is_alive():
            process.terminate()
    if isinstance(result, dict):
        result["probe_process_wall_seconds"] = time.perf_counter() - process_started
        result["exitcode"] = process.exitcode
    return result


def _select_cpu_optimization_profile(command: Dict[str, Any]) -> Dict[str, Any]:
    started = time.perf_counter()
    thread_results = []
    for thread_count in _cpu_thread_candidates():
        thread_results.append(_run_cpu_opt_candidate_process("runtime_patches", thread_count, command))

    valid_threads = [row for row in thread_results if row.get("ok")]
    if valid_threads:
        baseline = min(valid_threads, key=lambda row: float(row.get("elapsed_seconds") or float("inf")))
    else:
        baseline = {
            "ok": False,
            "profile": "runtime_patches",
            "thread_count": 1,
            "error": "No valid CPU baseline candidate completed",
        }

    selected_thread = int(baseline.get("thread_count") or 1)
    baseline_fingerprint = str(baseline.get("output_fingerprint") or "")
    profile_names = [
        CPU_OPT_PROFILE_NAME,
        "bf16_autocast",
        "torch_compile_xlmr",
    ]
    profile_results = [
        _run_cpu_opt_candidate_process(profile, selected_thread, command)
        for profile in profile_names
    ]
    candidates = [baseline] + profile_results
    valid_candidates = [
        row for row in candidates
        if row.get("ok") and row.get("output_fingerprint") == baseline_fingerprint
    ]
    if valid_candidates:
        selected = min(valid_candidates, key=lambda row: float(row.get("elapsed_seconds") or float("inf")))
    else:
        selected = baseline
    selected_profile = str(selected.get("profile") or "runtime_patches")
    selected_thread = int(selected.get("thread_count") or selected_thread or 1)

    return {
        "ok": bool(selected.get("ok")),
        "selected_profile": selected_profile,
        "selected_thread_count": selected_thread,
        "selected_elapsed_seconds": selected.get("elapsed_seconds"),
        "baseline_fingerprint": baseline_fingerprint,
        "selected_fingerprint": selected.get("output_fingerprint"),
        "output_match": bool(selected.get("output_fingerprint") == baseline_fingerprint and baseline_fingerprint),
        "thread_sweep": thread_results,
        "profile_candidates": profile_results,
        "selected_candidate": selected,
        "setup_seconds": time.perf_counter() - started,
        "deps_path": CPU_OPT_DEPS_DIR,
    }


@dataclass
class WorkerHandle:
    device: str
    use_gpu: bool
    ctx: Any
    optimized_cpu: bool = False
    optimized_gpu: bool = False
    onnx_cpu: bool = False
    cpu_opt_profile: str = "runtime_patches"
    cpu_opt_thread_count: Optional[int] = None
    cpu_opt_tok_batch_size: Optional[int] = None
    cpu_opt_tag_batch_size: Optional[int] = None
    cpu_opt_skip_startup_tuning: bool = False
    command_queue: mp.Queue = field(init=False)
    result_queue: mp.Queue = field(init=False)
    process: mp.Process = field(init=False)
    status: Dict[str, Any] = field(default_factory=lambda: {"state": "not_started"})
    pending: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def start(self) -> None:
        self.command_queue = self.ctx.Queue()
        self.result_queue = self.ctx.Queue()
        self.process = self.ctx.Process(
            target=_worker_main,
            args=(
                self.device,
                self.use_gpu,
                self.command_queue,
                self.result_queue,
                self.optimized_cpu,
                self.optimized_gpu,
                self.onnx_cpu,
                self.cpu_opt_profile,
                self.cpu_opt_thread_count,
                self.cpu_opt_tok_batch_size,
                self.cpu_opt_tag_batch_size,
                self.cpu_opt_skip_startup_tuning,
            ),
            daemon=False,
        )
        self.process.start()
        self.status = {"state": "starting", "pid": self.process.pid, "device": self.device}

    def drain(self) -> None:
        while True:
            try:
                msg = self.result_queue.get_nowait()
            except queue.Empty:
                break
            if not isinstance(msg, dict):
                continue
            if msg.get("type") == "status":
                self.status = msg
            elif msg.get("type") == "result":
                self.pending[str(msg.get("request_id") or "")] = msg
        try:
            state = str(self.status.get("state") or "")
            if state in {"starting", "loading"} and hasattr(self, "process") and not self.process.is_alive():
                self.status = {
                    "type": "status",
                    "device": self.device,
                    "state": "error",
                    "pid": getattr(self.process, "pid", None),
                    "time": time.time(),
                    "error": f"worker process exited before ready; exitcode={self.process.exitcode}",
                }
        except Exception:
            pass

    def analyze(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        with self.lock:
            self.drain()
            request_id = str(payload["request_id"])
            self.command_queue.put(dict(payload))
            deadline = time.time() + WORKER_RESPONSE_TIMEOUT_SECONDS
            while time.time() < deadline:
                self.drain()
                if request_id in self.pending:
                    return self.pending.pop(request_id)
                if not self.process.is_alive():
                    return {
                        "type": "result",
                        "device": self.device,
                        "request_id": request_id,
                        "ok": False,
                        "error": "worker process exited",
                        "status": self.status,
                    }
                time.sleep(0.05)
            return {
                "type": "result",
                "device": self.device,
                "request_id": request_id,
                "ok": False,
                "error": "worker response timed out",
                "status": self.status,
            }

    def shutdown(self) -> None:
        try:
            self.command_queue.put({"type": "shutdown"})
        except Exception:
            pass
        try:
            self.process.join(timeout=5)
        except Exception:
            pass
        if self.process.is_alive():
            self.process.terminate()


app = Flask(__name__)
workers: Dict[str, WorkerHandle] = {}
workers_started = False
workers_start_lock = threading.Lock()
cpu_opt_selection: Optional[Dict[str, Any]] = None
cpu_opt_start_lock = threading.Lock()


def _load_language_options() -> list[dict[str, str]]:
    try:
        import language_registry as lr

        out = []
        for code, info in sorted(lr.LANGUAGE_REGISTRY.items()):
            label = str(info.get("aliases", [code])[0] if info.get("aliases") else code)
            out.append({"code": code, "label": f"{code} - {label}"})
        return out
    except Exception:
        return [
            {"code": "zh", "label": "zh"},
            {"code": "ja", "label": "ja"},
            {"code": "ko", "label": "ko"},
            {"code": "ar", "label": "ar"},
            {"code": "sa", "label": "sa"},
        ]


@app.route("/")
def index() -> str:
    language_options = _load_language_options()
    options_html = "\n".join(
        f'<option value="{item["code"]}">{item["label"]}</option>' for item in language_options
    )
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Trankit CPU/GPU Benchmark</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f7f8fb;
      --panel: #ffffff;
      --border: #ccd3df;
      --text: #1d2430;
      --muted: #5c6675;
      --accent: #0f766e;
      --accent-dark: #115e59;
      --code: #0f172a;
      --warn: #9a3412;
      --err: #b91c1c;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 14px/1.45 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    header {{
      padding: 16px 22px;
      border-bottom: 1px solid var(--border);
      background: #fff;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
    }}
    h1 {{
      margin: 0;
      font-size: 18px;
      font-weight: 650;
      letter-spacing: 0;
    }}
    main {{
      width: min(1480px, calc(100vw - 32px));
      margin: 16px auto 24px;
      display: grid;
      grid-template-columns: 380px minmax(0, 1fr);
      gap: 16px;
    }}
    section {{
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 8px;
      min-width: 0;
    }}
    .controls {{
      padding: 14px;
      align-self: start;
      position: sticky;
      top: 12px;
    }}
    label {{
      display: block;
      margin: 0 0 6px;
      color: var(--muted);
      font-size: 12px;
      font-weight: 650;
    }}
    select, input, textarea, button {{
      width: 100%;
      border: 1px solid var(--border);
      border-radius: 6px;
      font: inherit;
    }}
    select, input {{
      height: 36px;
      padding: 0 10px;
      background: #fff;
    }}
    textarea {{
      min-height: 260px;
      resize: vertical;
      padding: 10px;
      font-family: ui-monospace, SFMono-Regular, Consolas, "Liberation Mono", monospace;
    }}
    button {{
      height: 38px;
      background: var(--accent);
      color: #fff;
      border-color: var(--accent-dark);
      font-weight: 650;
      cursor: pointer;
    }}
    button:disabled {{
      opacity: 0.55;
      cursor: wait;
    }}
    button.secondary {{
      background: #fff;
      color: var(--accent-dark);
      border-color: var(--accent);
    }}
    .button-grid {{
      display: grid;
      grid-template-columns: 1fr;
      gap: 8px;
    }}
    .row {{
      margin-bottom: 12px;
    }}
    .checks {{
      display: grid;
      gap: 8px;
      margin: 8px 0 14px;
    }}
    .check {{
      display: flex;
      align-items: center;
      gap: 8px;
      color: var(--text);
    }}
    .check input {{
      width: 16px;
      height: 16px;
    }}
    .status {{
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 10px;
      margin-top: 12px;
    }}
    .status-item {{
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 8px;
      background: #fafafa;
    }}
    .status-name {{
      font-weight: 700;
      margin-bottom: 2px;
    }}
    .status-state {{
      color: var(--muted);
      overflow-wrap: anywhere;
    }}
    .output {{
      min-width: 0;
    }}
    .tabs {{
      display: flex;
      border-bottom: 1px solid var(--border);
      background: #fff;
      border-radius: 8px 8px 0 0;
      overflow: hidden;
    }}
    .tab {{
      width: auto;
      min-width: 92px;
      border: 0;
      border-right: 1px solid var(--border);
      border-radius: 0;
      background: #fff;
      color: var(--text);
      height: 38px;
    }}
    .tab.active {{
      background: #e6f2f0;
      color: #0f3f3a;
    }}
    .pane {{
      display: none;
      padding: 14px;
    }}
    .pane.active {{
      display: block;
    }}
    .summary {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
      margin-bottom: 12px;
    }}
    .metric {{
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 9px;
      background: #fafafa;
      min-width: 0;
    }}
    .metric-name {{
      color: var(--muted);
      font-size: 12px;
      margin-bottom: 3px;
    }}
    .metric-value {{
      font-weight: 700;
      overflow-wrap: anywhere;
    }}
    .metric-details {{
      grid-column: 1 / -1;
      border: 1px solid var(--border);
      border-radius: 6px;
      background: #fafafa;
      padding: 8px 9px;
    }}
    .metric-details summary {{
      cursor: pointer;
      color: var(--muted);
      font-size: 12px;
      font-weight: 700;
    }}
    .metric-details-grid {{
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 10px;
      margin-top: 9px;
    }}
    .metric-split {{
      grid-column: 1 / -1;
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
    }}
    .metric-panel {{
      border: 1px solid var(--border);
      border-radius: 6px;
      background: #fff;
      padding: 10px;
      min-width: 0;
    }}
    .metric-panel h3 {{
      margin: 0 0 9px;
      font-size: 13px;
    }}
    .metric-panel-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
    }}
    pre {{
      margin: 0;
      padding: 12px;
      border: 1px solid var(--border);
      border-radius: 6px;
      background: #0b1020;
      color: #e5e7eb;
      overflow: auto;
      max-height: 68vh;
      font-size: 12px;
      line-height: 1.4;
      tab-size: 2;
    }}
    .note {{
      color: var(--muted);
      margin: 8px 0 0;
      font-size: 12px;
    }}
    .error {{
      color: var(--err);
      font-weight: 650;
      white-space: pre-wrap;
    }}
    @media (max-width: 980px) {{
      main {{
        grid-template-columns: 1fr;
      }}
      .controls {{
        position: static;
      }}
      .summary {{
        grid-template-columns: 1fr 1fr;
      }}
      .metric-split {{
        grid-template-columns: 1fr;
      }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>Trankit CPU/GPU Benchmark</h1>
    <div id="topStatus">Workers starting</div>
  </header>
  <main>
    <section class="controls">
      <div class="row">
        <label for="lang">Language</label>
        <select id="lang">{options_html}</select>
      </div>
      <div class="row">
        <label for="trankitOverride">Trankit override</label>
        <input id="trankitOverride" placeholder="optional, e.g. traditional-chinese">
      </div>
      <div class="checks">
        <label class="check"><input type="checkbox" id="manualSentence">Manual sentence segmentation</label>
        <label class="check"><input type="checkbox" id="stripPunctuation">Strip punctuation</label>
      </div>
      <div class="row">
        <label for="text">Text</label>
        <textarea id="text" spellcheck="false"></textarea>
      </div>
      <button id="gpuOptRunBtn">Run Compressed ONNX CPU then Regular GPU</button>
      <div class="row button-grid">
        <button id="xlmLoadProbeBtn" class="secondary">Shared XLM Cold-Load Probe</button>
        <button id="langLoadProbeBtn" class="secondary">Selected Language Modules Probe</button>
        <button id="fullLoadProbeBtn" class="secondary">Full All-Language Pipeline Probe</button>
      </div>
      <p class="note">Compressed ONNX CPU and regular GPU pipelines are loaded in separate worker processes at server start. Inference runs sequentially.</p>
      <div class="status">
        <div class="status-item">
          <div class="status-name">ONNX CPU</div>
          <div class="status-state" id="gpuOptStatus">starting</div>
        </div>
        <div class="status-item">
          <div class="status-name">GPU</div>
          <div class="status-state" id="gpuStatus">starting</div>
        </div>
      </div>
    </section>
    <section class="output">
      <div class="tabs">
        <button class="tab active" data-pane="metricsPane">Metrics</button>
        <button class="tab" data-pane="cpuPane">ONNX CPU JSON</button>
        <button class="tab" data-pane="gpuPane">GPU JSON</button>
        <button class="tab" data-pane="diffPane">Diff</button>
        <button class="tab" data-pane="probePane">Load Probe</button>
        <button class="tab" data-pane="rawPane">Raw Response</button>
      </div>
      <div class="pane active" id="metricsPane">
        <div class="summary" id="summary"></div>
        <pre id="metricsOut">No request yet.</pre>
      </div>
      <div class="pane" id="cpuPane"><pre id="cpuOut">No request yet.</pre></div>
      <div class="pane" id="gpuPane"><pre id="gpuOut">No request yet.</pre></div>
      <div class="pane" id="diffPane"><pre id="diffOut">No compressed CPU comparison yet.</pre></div>
      <div class="pane" id="probePane">
        <div class="summary" id="probeSummary"></div>
        <pre id="probeOut">No load probe yet.</pre>
      </div>
      <div class="pane" id="rawPane"><pre id="rawOut">No request yet.</pre></div>
    </section>
  </main>
  <script>
    const gpuOptRunBtn = document.getElementById("gpuOptRunBtn");
    const xlmLoadProbeBtn = document.getElementById("xlmLoadProbeBtn");
    const langLoadProbeBtn = document.getElementById("langLoadProbeBtn");
    const fullLoadProbeBtn = document.getElementById("fullLoadProbeBtn");
    const topStatus = document.getElementById("topStatus");
    const gpuOptStatus = document.getElementById("gpuOptStatus");
    const gpuStatus = document.getElementById("gpuStatus");
    const summary = document.getElementById("summary");
    const metricsOut = document.getElementById("metricsOut");
    const cpuOut = document.getElementById("cpuOut");
    const gpuOut = document.getElementById("gpuOut");
    const diffOut = document.getElementById("diffOut");
    const probeSummary = document.getElementById("probeSummary");
    const probeOut = document.getElementById("probeOut");
    const rawOut = document.getElementById("rawOut");

    function fmtBytes(n) {{
      if (typeof n !== "number" || !isFinite(n) || n < 0) return "n/a";
      const units = ["B", "KB", "MB", "GB", "TB"];
      let v = n;
      let i = 0;
      while (v >= 1024 && i < units.length - 1) {{
        v /= 1024;
        i++;
      }}
      return `${{v.toFixed(2)}} ${{units[i]}}`;
    }}

    function fmtSeconds(n) {{
      if (typeof n !== "number" || !isFinite(n)) return "n/a";
      return `${{n.toFixed(3)}} s`;
    }}

    function pretty(value) {{
      return JSON.stringify(value, null, 2);
    }}

    function metricBox(name, value) {{
      return `<div class="metric"><div class="metric-name">${{name}}</div><div class="metric-value">${{value}}</div></div>`;
    }}

    function metricPanel(title, boxes) {{
      return `<section class="metric-panel"><h3>${{title}}</h3><div class="metric-panel-grid">${{boxes.join("")}}</div></section>`;
    }}

    function metricSplit(leftTitle, leftBoxes, rightTitle, rightBoxes) {{
      return `<div class="metric-split">${{metricPanel(leftTitle, leftBoxes)}}${{metricPanel(rightTitle, rightBoxes)}}</div>`;
    }}

    function metricDetails(title, contentHtml) {{
      return `<details class="metric-details"><summary>${{title}}</summary>${{contentHtml}}</details>`;
    }}

    function cpuOptQuantCount(load, field) {{
      const report = load && load.cpu_opt && load.cpu_opt.optimization_report;
      if (!report) return "n/a";
      if (field === "xlmr") {{
        const q = report.xlmr_quantization || {{}};
        if (typeof q.quantized_count === "number") return String(q.quantized_count);
        if (q.cache && typeof q.cache.quantized_count === "number") return String(q.cache.quantized_count);
        return "n/a";
      }}
      const rows = Array.isArray(report.seq2seq_quantization) ? report.seq2seq_quantization : [];
      if (report.seq2seq_quantization && report.seq2seq_quantization.skipped) return "0 (skipped)";
      let total = 0;
      let seen = false;
      rows.forEach((row) => {{
        if (row && typeof row.quantized_count === "number") {{
          total += row.quantized_count;
          seen = true;
        }} else if (row && row.cache && typeof row.cache.quantized_count === "number") {{
          total += row.cache.quantized_count;
          seen = true;
        }}
      }});
      return seen ? String(total) : "n/a";
    }}

    function cpuOptReport(load) {{
      return load && load.cpu_opt && load.cpu_opt.optimization_report ? load.cpu_opt.optimization_report : {{}};
    }}

    function cpuOptAdapterStatus(load) {{
      const report = cpuOptReport(load);
      const q = report.xlmr_quantization || {{}};
      const skipped = Number(q.skipped_adapter_count || 0);
      const quantized = Number(report.xlmr_adapter_dynamic_int8_count || 0);
      return `${{skipped}} skipped / ${{quantized}} quantized`;
    }}

    function cpuOptEvalStatus(load) {{
      const status = cpuOptReport(load).eval_status || {{}};
      if (status.embedding_eval && status.xlmr_eval) return "yes";
      if (status.embedding_eval || status.xlmr_eval) return "partial";
      return "no";
    }}

    function cpuOptCompileStatus(load) {{
      const value = cpuOptReport(load).torch_compile || {{}};
      return String(value.status || (value.ok ? "kept" : value.error ? "rejected" : "skipped"));
    }}

    function cpuOptBf16Status(load) {{
      const report = cpuOptReport(load);
      if (report.bf16_status) return String(report.bf16_status);
      const probe = report.bf16_probe || {{}};
      if (probe.supported) return "available";
      return "skipped";
    }}

    function cpuOptHiddenStateStatus(load) {{
      const patch = load && load.cpu_opt && load.cpu_opt.xlmr_load_patch_report;
      const report = load && load.cpu_opt && load.cpu_opt.optimization_report && load.cpu_opt.optimization_report.xlmr_hidden_state_outputs;
      if (patch && patch.installed === false) return "patch failed";
      if (report && typeof report.changed_attrs === "number") return `disabled (${{report.changed_attrs}} attrs)`;
      if (patch && patch.installed) return "load patched";
      return "n/a";
    }}

    function renderStatus(status) {{
      const gpu = status.gpu || {{}};
      const gpuOpt = status.onnx_cpu || {{}};
      gpuOptStatus.textContent = `${{gpuOpt.state || "not started"}}${{gpuOpt.pid ? " pid " + gpuOpt.pid : ""}}`;
      gpuStatus.textContent = `${{gpu.state || "unknown"}}${{gpu.pid ? " pid " + gpu.pid : ""}}`;
      if (gpuOpt.state === "error" && gpuOpt.error) {{
        gpuOptStatus.textContent += ` error: ${{gpuOpt.error}}`;
      }}
      const optReady = gpuOpt.state === "ready" && gpu.state === "ready";
      if (gpuOpt.state === "error" || gpu.state === "error") {{
        topStatus.textContent = "Worker error";
      }} else {{
        topStatus.textContent = optReady ? "Workers ready" : "Workers loading";
      }}
    }}

    async function refreshStatus() {{
      try {{
        const res = await fetch("/api/status", {{ cache: "no-store" }});
        renderStatus(await res.json());
      }} catch (err) {{
        topStatus.textContent = "Status unavailable";
      }}
    }}

    function responseTokenCount(response) {{
      const devices = response.devices || {{}};
      const candidates = [devices.onnx_cpu, devices.cpu_opt, devices.gpu_opt, devices.cpu, devices.gpu];
      for (const device of candidates) {{
        const counts = device && device.metrics && device.metrics.annotation_counts;
        const count = counts && counts.token_count;
        if (Number.isFinite(Number(count))) return String(count);
      }}
      return "0";
    }}

    function taskStageTime(metrics, stageName) {{
      const stages = metrics && metrics.task_breakdown && metrics.task_breakdown.stages;
      const row = stages && stages[stageName];
      if (!row || !row.count) return "n/a";
      const seconds = Number(row.exclusive_seconds);
      const suffix = row.count > 1 ? ` (${{row.count}}x)` : "";
      return Number.isFinite(seconds) ? `${{fmtSeconds(seconds)}}${{suffix}}` : "n/a";
    }}

    function taskStageSeconds(metrics, stageName) {{
      const stages = metrics && metrics.task_breakdown && metrics.task_breakdown.stages;
      const row = stages && stages[stageName];
      const seconds = row && row.count ? Number(row.exclusive_seconds) : NaN;
      return Number.isFinite(seconds) ? seconds : 0;
    }}

    function taskStageRow(metrics, stageName) {{
      const stages = metrics && metrics.task_breakdown && metrics.task_breakdown.stages;
      return stages && stages[stageName] ? stages[stageName] : {{}};
    }}

    function taskBatchCount(metrics, stageName) {{
      const row = taskStageRow(metrics, stageName);
      const direct = Number(row.batch_count || 0);
      if (direct > 0) return direct;
      return Math.max(
        Number(row.xlm_call_count || 0),
        Number(row.seq2seq_call_count || 0),
        Number(row.head_call_count || 0)
      );
    }}

    function taskBatchText(metrics, stageName) {{
      const row = taskStageRow(metrics, stageName);
      const count = taskBatchCount(metrics, stageName);
      if (!count) return "n/a";
      const items = Number(row.batch_items || 0);
      const avg = items && count ? (items / count).toFixed(1) : "n/a";
      const min = row.batch_min_items == null ? "n/a" : String(row.batch_min_items);
      const max = row.batch_max_items == null ? "n/a" : String(row.batch_max_items);
      return `${{count}} batches / avg ${{avg}} / min ${{min}} / max ${{max}}`;
    }}

    function taskShapeText(metrics, stageName) {{
      const row = taskStageRow(metrics, stageName);
      const count = taskBatchCount(metrics, stageName);
      if (!count) return "n/a";
      const maxLen = row.batch_max_padded_length == null ? "n/a" : String(row.batch_max_padded_length);
      const padded = Number(row.batch_padded_units || 0);
      const real = Number(row.batch_real_units || 0);
      const fake = Number(row.batch_padding_units || 0);
      const fakeText = real ? ` / fake pad ${{fake}}` : "";
      return `max seq ${{maxLen}} / total padded units ${{padded || "n/a"}}${{fakeText}}`;
    }}

    function taskBatchPaddingText(metrics, stageName) {{
      const row = taskStageRow(metrics, stageName);
      const details = Array.isArray(row.batch_padding_details) ? row.batch_padding_details : [];
      if (!details.length) return "n/a";
      return details.map((item) => {{
        const index = Number(item.index || 0);
        const items = Number(item.items || 0);
        const maxLen = Number(item.max_len || 0);
        const padded = Number(item.padded_units || 0);
        const fake = item.padding_units == null ? null : Number(item.padding_units);
        const fakePart = Number.isFinite(fake) ? `, fake ${{fake}}` : "";
        return `#${{index}}: ${{items}}x${{maxLen}}=${{padded}}${{fakePart}}`;
      }}).join(" | ");
    }}

    function dynamicBatchSummary(metrics) {{
      const events = Array.isArray(metrics && metrics.onnx_dynamic_batch_events) ? metrics.onnx_dynamic_batch_events : [];
      if (!events.length) return metrics && metrics.onnx_dynamic_batching ? "dynamic" : "n/a";
      return events.map((event) => {{
        const kind = String(event.kind || "?");
        const selected = event.selected_batch_size == null ? "?" : String(event.selected_batch_size);
        const requested = event.requested_batch_size == null ? "?" : String(event.requested_batch_size);
        const plan = event.plan && event.plan.selected ? event.plan.selected : {{}};
        const fake = plan.padding_units == null ? "?" : String(plan.padding_units);
        return `${{kind}}:${{selected}}/${{requested}} fake ${{fake}}`;
      }}).join(" | ");
    }}

    function ortTuningSummary(runtime, report) {{
      const tuning = (runtime && runtime.ort_tuning) || (report && report.ort_tuning) || {{}};
      if (tuning.applied && tuning.profile) {{
        const profile = tuning.profile || {{}};
        const name = String(profile.name || "applied");
        const intra = profile.intra_op_num_threads == null ? "default" : String(profile.intra_op_num_threads);
        const inter = profile.inter_op_num_threads == null ? "default" : String(profile.inter_op_num_threads);
        const mem = profile.enable_mem_pattern === false ? "mem-pattern off" : "mem-pattern on";
        return `${{name}} / intra ${{intra}} / inter ${{inter}} / ${{mem}}`;
      }}
      if (tuning.loaded && !tuning.applied) {{
        return `default (${{String(tuning.reason || tuning.error || "not applied")}})`;
      }}
      return "default";
    }}

    function taskModelCallText(metrics, stageName) {{
      const row = taskStageRow(metrics, stageName);
      const parts = [];
      const xlm = Number(row.xlm_call_count || 0);
      const head = Number(row.head_call_count || 0);
      const seq2seq = Number(row.seq2seq_call_count || 0);
      if (xlm) parts.push(`XLM:${{xlm}}`);
      if (head) parts.push(`head:${{head}}`);
      if (seq2seq) parts.push(`seq2seq:${{seq2seq}}`);
      if (!parts.length) return "n/a";
      const seconds = Number(row.model_call_seconds || 0);
      const suffix = Number.isFinite(seconds) && seconds > 0 ? ` / call wall ${{fmtSeconds(seconds)}}` : "";
      return `${{parts.join(" ")}}${{suffix}}`;
    }}

    function onnxTaskRuntime(runtime, taskName) {{
      const rows = runtime && runtime.request_by_key ? runtime.request_by_key : {{}};
      const out = {{
        count: 0,
        total_seconds: 0,
        preprocess_seconds: 0,
        session_seconds: 0,
        postprocess_seconds: 0
      }};
      Object.keys(rows).forEach((key) => {{
        if (!key.endsWith(`:${{taskName}}`)) return;
        const row = rows[key] || {{}};
        out.count += Number(row.count || 0);
        out.total_seconds += Number(row.total_seconds || 0);
        out.preprocess_seconds += Number(row.preprocess_seconds || 0);
        out.session_seconds += Number(row.session_seconds || 0);
        out.postprocess_seconds += Number(row.postprocess_seconds || 0);
      }});
      return out;
    }}

    function taskPanel(label, stageName, onnxTaskName, cpuM, gpuM, runtime) {{
      const cpuTotal = taskStageSeconds(cpuM, stageName);
      const gpuTotal = taskStageTime(gpuM, stageName);
      const cpuBoxes = [
        metricBox("Total", cpuTotal ? taskStageTime(cpuM, stageName) : "n/a"),
        metricBox("Batches", taskBatchText(cpuM, stageName)),
        metricBox("Shapes", taskShapeText(cpuM, stageName)),
        metricBox("Padding / batch", taskBatchPaddingText(cpuM, stageName)),
        metricBox("Model calls", taskModelCallText(cpuM, stageName))
      ];
      if (onnxTaskName) {{
        const rt = onnxTaskRuntime(runtime, onnxTaskName);
        const handoff = rt.preprocess_seconds + rt.postprocess_seconds;
        const nonOnnx = Math.max(0, cpuTotal - rt.total_seconds);
        cpuBoxes.push(metricBox("ONNX runtime", rt.count ? `${{fmtSeconds(rt.total_seconds)}} (${{rt.count}}x)` : "n/a"));
        cpuBoxes.push(metricBox("ORT session", rt.count ? fmtSeconds(rt.session_seconds) : "n/a"));
        cpuBoxes.push(metricBox("ONNX handoff", rt.count ? fmtSeconds(handoff) : "n/a"));
        cpuBoxes.push(metricBox("PyTorch/other", cpuTotal ? fmtSeconds(nonOnnx) : "n/a"));
      }} else {{
        cpuBoxes.push(metricBox("ONNX runtime", "n/a"));
        cpuBoxes.push(metricBox("ORT session", "n/a"));
        cpuBoxes.push(metricBox("ONNX handoff", "n/a"));
        cpuBoxes.push(metricBox("PyTorch/other", cpuTotal ? fmtSeconds(cpuTotal) : "n/a"));
      }}
      const gpuBoxes = [
        metricBox("Total", gpuTotal),
        metricBox("Batches", taskBatchText(gpuM, stageName)),
        metricBox("Shapes", taskShapeText(gpuM, stageName)),
        metricBox("Padding / batch", taskBatchPaddingText(gpuM, stageName)),
        metricBox("Model calls", taskModelCallText(gpuM, stageName))
      ];
      return `<section class="metric-panel"><h3>${{label}}</h3>${{metricSplit("ONNX CPU", cpuBoxes, "Regular GPU", gpuBoxes)}}</section>`;
    }}

    function taskBreakdownByTask(cpuM, gpuM, runtime) {{
      return [
        taskPanel("Tokenization", "tokenization", "tokenizer", cpuM, gpuM, runtime),
        taskPanel("MWT expansion", "mwt_expansion", null, cpuM, gpuM, runtime),
        taskPanel("POS / dependency", "posdep_tagging", "tagger", cpuM, gpuM, runtime),
        taskPanel("Lemmatization", "lemmatization", null, cpuM, gpuM, runtime),
        taskPanel("NER", "ner", "ner", cpuM, gpuM, runtime)
      ].join("");
    }}

    function renderSummary(response) {{
      const cpu = response.devices && response.devices.cpu;
      const gpu = response.devices && response.devices.gpu;
      const cpuM = cpu && cpu.metrics;
      const gpuM = gpu && gpu.metrics;
      summary.innerHTML = [
        metricBox("CPU time", fmtSeconds(cpuM && cpuM.elapsed_seconds)),
        metricBox("GPU time", fmtSeconds(gpuM && gpuM.elapsed_seconds)),
        metricBox("CPU peak RSS delta", fmtBytes(cpuM && cpuM.rss_peak_sampled_delta_bytes)),
        metricBox("GPU peak allocated", fmtBytes(gpuM && gpuM.gpu_allocator_max_allocated_bytes)),
        metricBox("CPU load RSS", fmtBytes(response.load && response.load.cpu && response.load.cpu.rss_total_load_delta_bytes)),
        metricBox("GPU load RSS", fmtBytes(response.load && response.load.gpu && response.load.gpu.rss_total_load_delta_bytes)),
        metricBox("GPU load reserved", fmtBytes(response.load && response.load.gpu && response.load.gpu.gpu_after_load && response.load.gpu.gpu_after_load.reserved_bytes)),
        metricBox("Tokens", responseTokenCount(response))
      ].join("");
    }}

    function renderCpuOptSummary(response) {{
      const cpu = response.devices && response.devices.cpu_opt;
      const gpu = response.devices && response.devices.gpu;
      const cpuM = cpu && cpu.metrics;
      const gpuM = gpu && gpu.metrics;
      const comparison = response.comparison || {{}};
      const load = response.load || {{}};
      const selection = response.cpu_opt_selection || {{}};
      const cpuStatus = response.worker_status && response.worker_status.cpu_opt ? response.worker_status.cpu_opt : {{}};
      const ratio = typeof comparison.cpu_opt_vs_gpu_ratio === "number" ? `${{comparison.cpu_opt_vs_gpu_ratio.toFixed(3)}}x GPU` : "n/a";
      summary.innerHTML = [
        metricBox("Optimized CPU time", fmtSeconds(cpuM && cpuM.elapsed_seconds)),
        metricBox("Regular GPU time", fmtSeconds(gpuM && gpuM.elapsed_seconds)),
        metricBox("CPU/GPU ratio", ratio),
        metricBox("CPU worker", String(cpuStatus.state || (cpu && cpu.ok === false ? "error" : "n/a"))),
        metricBox("Output match", comparison.output_match ? "yes" : "no"),
        metricBox("CPU profile", String((cpuM && cpuM.cpu_opt_profile) || selection.selected_profile || "n/a")),
        metricBox("CPU threads", String((cpuM && cpuM.cpu_opt_thread_count) || selection.selected_thread_count || "n/a")),
        metricBox("Sequence bucket", String((cpuM && cpuM.sequence_bucket) || "n/a")),
        metricBox("XLM-R INT8 modules", cpuOptQuantCount(load, "xlmr")),
        metricBox("Adapter modules", cpuOptAdapterStatus(load)),
        metricBox("Seq2seq INT8 modules", cpuOptQuantCount(load, "seq2seq")),
        metricBox("Hidden states", cpuOptHiddenStateStatus(load)),
        metricBox("Eval mode", cpuOptEvalStatus(load)),
        metricBox("torch.compile", cpuOptCompileStatus(load)),
        metricBox("BF16", cpuOptBf16Status(load)),
        metricBox("CPU opt setup", fmtSeconds(selection.setup_seconds)),
        metricBox("CPU opt load", fmtSeconds(load.cpu_opt && load.cpu_opt.load_seconds)),
        metricBox("CPU opt apply", fmtSeconds(load.cpu_opt && load.cpu_opt.optimization_seconds)),
        metricBox("CPU opt tune", fmtSeconds(load.cpu_opt && load.cpu_opt.startup_tuning_report && load.cpu_opt.startup_tuning_report.elapsed_seconds)),
        metricBox("GPU load", fmtSeconds(load.gpu && load.gpu.load_seconds)),
        metricBox("GC suppressed", String((cpuM && cpuM.gc_collect_calls_suppressed) || 0)),
        metricBox("CUDA cache suppressed", String((cpuM && cpuM.cuda_empty_cache_calls_suppressed) || 0)),
        metricBox("Tokens", responseTokenCount(response))
      ].join("");
    }}

    function gpuOptReport(load) {{
      return load && load.gpu_opt && load.gpu_opt.optimization_report ? load.gpu_opt.optimization_report : {{}};
    }}

    function gpuOptEvalStatus(load) {{
      const status = gpuOptReport(load).eval_status || {{}};
      if (status.embedding_eval && status.xlmr_eval) return "yes";
      if (status.embedding_eval || status.xlmr_eval) return "partial";
      return "no";
    }}

    function gpuOptHiddenStateStatus(load) {{
      const report = gpuOptReport(load);
      const status = report.xlmr_hidden_state_status || {{}};
      if (status.disabled === true) return "yes";
      if (status.disabled === false) return "no";
      return "n/a";
    }}

    function gpuOptFp16Status(load) {{
      const fp16 = gpuOptReport(load).fp16_coverage || {{}};
      if (fp16.error) return `error: ${{fp16.error}}`;
      if (fp16.all_checked_float_params_fp16 === true) return "yes";
      if (fp16.all_checked_float_params_fp16 === false) return "partial/no";
      return "n/a";
    }}

    function gpuOptTf32Status(load) {{
      const backend = gpuOptReport(load).backend || {{}};
      const mm = backend.cuda_matmul_allow_tf32 === true;
      const cudnn = backend.cudnn_allow_tf32 === true;
      return `${{mm ? "matmul yes" : "matmul n/a"}} / ${{cudnn ? "cudnn yes" : "cudnn n/a"}}`;
    }}

    function gpuOptCompileStatus(load) {{
      const compile = gpuOptReport(load).torch_compile || {{}};
      return String(compile.status || (compile.ok ? "kept" : compile.error ? "rejected" : "skipped"));
    }}

    function syncPointSummary(metrics) {{
      const sync = metrics && metrics.sync_points ? metrics.sync_points : {{}};
      const calls = sync.calls || {{}};
      const parts = [];
      ["cpu", "numpy", "tolist", "item"].forEach((name) => {{
        const row = calls[name] || {{}};
        parts.push(`${{name}}:${{row.count || 0}}`);
      }});
      return parts.join(" ");
    }}

    function renderGpuOptSummary(response) {{
      const gpuOpt = response.devices && response.devices.gpu_opt;
      const gpu = response.devices && response.devices.gpu;
      const optM = gpuOpt && gpuOpt.metrics;
      const gpuM = gpu && gpu.metrics;
      const comparison = response.comparison || {{}};
      const load = response.load || {{}};
      const status = response.worker_status && response.worker_status.gpu_opt ? response.worker_status.gpu_opt : {{}};
      const speedup = typeof comparison.gpu_opt_speedup_ratio === "number" ? `${{comparison.gpu_opt_speedup_ratio.toFixed(3)}}x` : "n/a";
      summary.innerHTML = [
        metricBox("Optimized GPU time", fmtSeconds(optM && optM.elapsed_seconds)),
        metricBox("Regular GPU time", fmtSeconds(gpuM && gpuM.elapsed_seconds)),
        metricBox("Speedup ratio", speedup),
        metricBox("GPU opt worker", String(status.state || (gpuOpt && gpuOpt.ok === false ? "error" : "n/a"))),
        metricBox("Output match", comparison.output_match ? "yes" : "no"),
        metricBox("GPU opt profile", String((optM && optM.gpu_opt_profile) || (load.gpu_opt && load.gpu_opt.gpu_opt_profile) || "n/a")),
        metricBox("Hidden states disabled", gpuOptHiddenStateStatus(load)),
        metricBox("Eval mode", gpuOptEvalStatus(load)),
        metricBox("FP16 coverage", gpuOptFp16Status(load)),
        metricBox("TF32 enabled", gpuOptTf32Status(load)),
        metricBox("torch.compile", gpuOptCompileStatus(load)),
        metricBox("Sequence bucket", String((optM && optM.sequence_bucket) || "n/a")),
        metricBox("GC suppressed", String((optM && optM.gc_collect_calls_suppressed) || 0)),
        metricBox("CUDA cache suppressed", String((optM && optM.cuda_empty_cache_calls_suppressed) || 0)),
        metricBox("GPU allocated peak", fmtBytes(optM && optM.gpu_allocator_max_allocated_bytes)),
        metricBox("GPU reserved peak", fmtBytes(optM && optM.gpu_allocator_max_reserved_bytes)),
        metricBox("GPU opt load", fmtSeconds(load.gpu_opt && load.gpu_opt.load_seconds)),
        metricBox("GPU opt setup", fmtSeconds(load.gpu_opt && load.gpu_opt.optimization_seconds)),
        metricBox("Sync points", syncPointSummary(optM)),
        metricBox("Tokens", responseTokenCount(response))
      ].join("");
    }}

    function renderOnnxSummary(response) {{
      const cpu = response.devices && response.devices.onnx_cpu;
      const gpu = response.devices && response.devices.gpu;
      const cpuM = cpu && cpu.metrics;
      const gpuM = gpu && gpu.metrics;
      const comparison = response.comparison || {{}};
      const load = response.load || {{}};
      const report = load.onnx_cpu && load.onnx_cpu.onnx_report ? load.onnx_cpu.onnx_report : {{}};
      const runtime = cpuM && cpuM.onnx_runtime ? cpuM.onnx_runtime : {{}};
      const requestOnnxCalls = runtime.request_run_count != null ? runtime.request_run_count : runtime.run_count;
      const ratio = typeof comparison.onnx_cpu_vs_gpu_ratio === "number" ? `${{comparison.onnx_cpu_vs_gpu_ratio.toFixed(3)}}x GPU` : "n/a";
      const onnxBoxes = [
        metricBox("Time", fmtSeconds(cpuM && cpuM.elapsed_seconds)),
        metricBox("Profile", String((cpuM && cpuM.onnx_profile) || (load.onnx_cpu && load.onnx_cpu.onnx_profile) || "n/a")),
        metricBox("Session", runtime.onnx_session ? "1 shared" : "n/a"),
        metricBox("ORT profile", ortTuningSummary(runtime, report)),
        metricBox("Adapter packs", `${{report.adapter_pack_count || runtime.loaded_pack_count || 0}}/${{report.task_count || 0}}`),
        metricBox("Missing packs", String(report.missing_count || 0)),
        metricBox("Tok batch", String((cpuM && cpuM.onnx_tok_batch_size) || (load.onnx_cpu && load.onnx_cpu.onnx_tok_batch_size) || "n/a")),
        metricBox("POS/NER batch", String((cpuM && cpuM.onnx_tag_batch_size) || (load.onnx_cpu && load.onnx_cpu.onnx_tag_batch_size) || "n/a")),
        metricBox("XLM batch planner", dynamicBatchSummary(cpuM)),
        metricBox("Seq2seq planner", (cpuM && cpuM.onnx_seq2seq_dynamic_batching) ? "dynamic" : "off"),
        metricBox("Tok padding", (cpuM && cpuM.onnx_tokenizer_dynamic_padding) ? "dynamic" : ((load.onnx_cpu && load.onnx_cpu.onnx_tokenizer_padding_report && load.onnx_cpu.onnx_tokenizer_padding_report.installed) ? "dynamic" : "n/a")),
        metricBox("POS/NER bucketing", (cpuM && cpuM.onnx_tagger_ner_length_bucketing) ? "length" : ((load.onnx_cpu && load.onnx_cpu.onnx_tagger_ner_bucketing_report && load.onnx_cpu.onnx_tagger_ner_bucketing_report.installed) ? "length" : "n/a")),
        metricBox("Calls/request", String(requestOnnxCalls || 0)),
        metricBox("Calls/lifetime", String(runtime.run_count || 0)),
        metricBox("Latent RSS", fmtBytes(load.onnx_cpu && load.onnx_cpu.rss_after_load_bytes)),
        metricBox("RSS spike", fmtBytes(cpuM && cpuM.rss_peak_sampled_delta_bytes)),
        metricBox("Setup", fmtSeconds(load.onnx_cpu && load.onnx_cpu.optimization_seconds)),
        metricBox("Load", fmtSeconds(load.onnx_cpu && load.onnx_cpu.load_seconds)),
        metricBox("GC suppressed", String((cpuM && cpuM.gc_collect_calls_suppressed) || 0))
      ];
      const gpuBoxes = [
        metricBox("Time", fmtSeconds(gpuM && gpuM.elapsed_seconds)),
        metricBox("Latent RSS", fmtBytes(load.gpu && load.gpu.rss_after_load_bytes)),
        metricBox("Latent VRAM", fmtBytes(load.gpu && load.gpu.gpu_after_load && load.gpu.gpu_after_load.allocated_bytes)),
        metricBox("RSS spike", fmtBytes(gpuM && gpuM.rss_peak_sampled_delta_bytes)),
        metricBox("VRAM peak", fmtBytes(gpuM && gpuM.gpu_allocator_max_allocated_bytes)),
        metricBox("Load", fmtSeconds(load.gpu && load.gpu.load_seconds))
      ];
      summary.innerHTML = [
        metricBox("CPU/GPU ratio", ratio),
        metricBox("Output match", comparison.output_match ? "yes" : "no"),
        metricBox("Tokens", responseTokenCount(response)),
        metricSplit("ONNX CPU", onnxBoxes, "Regular GPU", gpuBoxes),
        metricDetails("Task timing breakdown", taskBreakdownByTask(cpuM, gpuM, runtime))
      ].join("");
    }}

    function stageSeconds(result, predicate) {{
      if (!result || !Array.isArray(result.stages)) return 0;
      return result.stages.reduce((sum, stage) => {{
        if (!stage || !predicate(stage)) return sum;
        const seconds = Number(stage.elapsed_seconds);
        return sum + (Number.isFinite(seconds) ? seconds : 0);
      }}, 0);
    }}

    function topStageText(result) {{
      if (!result || !Array.isArray(result.stages)) return "No stages.";
      return result.stages
        .filter((stage) => stage && !String(stage.name || "").endsWith("_total"))
        .slice()
        .sort((a, b) => Number(b.elapsed_seconds || 0) - Number(a.elapsed_seconds || 0))
        .slice(0, 12)
        .map((stage) => `${{fmtSeconds(Number(stage.elapsed_seconds || 0)).padStart(10)}}  ${{stage.name}}`)
        .join("\\n");
    }}

    function renderLoadProbe(response) {{
      const cpu = response.devices && response.devices.cpu;
      const gpu = response.devices && response.devices.gpu;
      const cpuImport = stageSeconds(cpu, (s) => String(s.name || "").startsWith("import_"));
      const gpuImport = stageSeconds(gpu, (s) => String(s.name || "").startsWith("import_"));
      const cpuLoad = stageSeconds(cpu, (s) => ["load_shared_xlm_only", "load_selected_language_modules", "load_full_app_trankit_pipeline"].includes(String(s.name || "")));
      const gpuLoad = stageSeconds(gpu, (s) => ["load_shared_xlm_only", "load_selected_language_modules", "load_full_app_trankit_pipeline"].includes(String(s.name || "")));
      const cpuFirstInference = stageSeconds(cpu, (s) => String(s.name || "") === "first_inference_after_cold_load");
      const gpuFirstInference = stageSeconds(gpu, (s) => String(s.name || "") === "first_inference_after_cold_load");
      const cpuError = cpu && cpu.ok === false ? String(cpu.error || "probe failed") : "";
      const gpuError = gpu && gpu.ok === false ? String(gpu.error || "probe failed") : "";
      probeSummary.innerHTML = [
        metricBox("Probe wall time", fmtSeconds(response.elapsed_seconds)),
        metricBox("CPU process wall", fmtSeconds(cpu && cpu.probe_process_wall_seconds)),
        metricBox("GPU process wall", fmtSeconds(gpu && gpu.probe_process_wall_seconds)),
        metricBox("CPU imports", fmtSeconds(cpuImport)),
        metricBox("GPU imports", fmtSeconds(gpuImport)),
        metricBox("CPU Trankit load", fmtSeconds(cpuLoad)),
        metricBox("GPU Trankit load", fmtSeconds(gpuLoad)),
        metricBox("CPU first inference", fmtSeconds(cpuFirstInference)),
        metricBox("GPU first inference", fmtSeconds(gpuFirstInference)),
        metricBox("CPU loaded langs", String((cpu && cpu.added_lang_count) || 0)),
        metricBox("GPU loaded langs", String((gpu && gpu.added_lang_count) || 0)),
        metricBox("CPU status", cpuError || (cpu && cpu.ok ? "ok" : "missing")),
        metricBox("GPU status", gpuError || (gpu && gpu.ok ? "ok" : "missing"))
      ].join("");
      probeOut.textContent = [
        "Probe mode:",
        response.description || response.mode || "",
        "",
        "CPU loaded:",
        cpu && cpu.loaded_description ? cpu.loaded_description : "",
        "",
        "GPU loaded:",
        gpu && gpu.loaded_description ? gpu.loaded_description : "",
        "",
        "CPU slowest stages:",
        topStageText(cpu),
        cpuError ? "\\nCPU error:\\n" + cpuError : "",
        "",
        "GPU slowest stages:",
        topStageText(gpu),
        gpuError ? "\\nGPU error:\\n" + gpuError : "",
        "",
        "Raw JSON:",
        pretty(response)
      ].join("\\n");
    }}

    function showPane(paneId) {{
      document.querySelectorAll(".tab").forEach((t) => {{
        t.classList.toggle("active", t.dataset.pane === paneId);
      }});
      document.querySelectorAll(".pane").forEach((p) => {{
        p.classList.toggle("active", p.id === paneId);
      }});
    }}

    document.querySelectorAll(".tab").forEach((tab) => {{
      tab.addEventListener("click", () => {{
        document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
        document.querySelectorAll(".pane").forEach((p) => p.classList.remove("active"));
        tab.classList.add("active");
        document.getElementById(tab.dataset.pane).classList.add("active");
      }});
    }});

    gpuOptRunBtn.addEventListener("click", async () => {{
      gpuOptRunBtn.disabled = true;
      gpuOptRunBtn.textContent = "Running";
      metricsOut.textContent = "Running preloaded compressed ONNX CPU and then regular GPU...";
      cpuOut.textContent = "Waiting for compressed ONNX CPU...";
      gpuOut.textContent = "Waiting for regular GPU...";
      diffOut.textContent = "Waiting for compressed ONNX CPU and regular GPU outputs...";
      rawOut.textContent = "Waiting...";
      try {{
        const payload = {{
          lang: document.getElementById("lang").value,
          trankit_override: document.getElementById("trankitOverride").value,
          manual_sentence_segmentation: document.getElementById("manualSentence").checked,
          strip_punctuation: document.getElementById("stripPunctuation").checked,
          text: document.getElementById("text").value
        }};
        const res = await fetch("/api/analyze_onnx_cpu_vs_gpu", {{
          method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify(payload)
        }});
        const data = await res.json();
        renderOnnxSummary(data);
        metricsOut.textContent = pretty({{
          comparison: data.comparison,
          load: data.load,
          devices: {{
            onnx_cpu: data.devices && data.devices.onnx_cpu && data.devices.onnx_cpu.metrics,
            gpu: data.devices && data.devices.gpu && data.devices.gpu.metrics
          }}
        }});
        cpuOut.textContent = pretty(data.devices && data.devices.onnx_cpu);
        gpuOut.textContent = pretty(data.devices && data.devices.gpu);
        diffOut.textContent = data.discrepancies && data.discrepancies.text ? data.discrepancies.text : "No discrepancy report.";
        rawOut.textContent = pretty(data);
      }} catch (err) {{
        metricsOut.innerHTML = `<span class="error">${{String(err)}}</span>`;
      }} finally {{
        gpuOptRunBtn.disabled = false;
        gpuOptRunBtn.textContent = "Run Compressed ONNX CPU then Regular GPU";
        refreshStatus();
      }}
    }});

    async function runLoadProbe(mode) {{
      const labels = {{
        xlm_only: "shared XLM cold-load",
        lang_modules: "selected-language module load",
        full: "full all-language pipeline load"
      }};
      const label = labels[mode] || mode;
      const xlmLabel = xlmLoadProbeBtn.textContent;
      const langLabel = langLoadProbeBtn.textContent;
      const fullLabel = fullLoadProbeBtn.textContent;
      showPane("probePane");
      probeSummary.innerHTML = "";
      xlmLoadProbeBtn.disabled = true;
      langLoadProbeBtn.disabled = true;
      fullLoadProbeBtn.disabled = true;
      if (mode === "xlm_only") {{
        xlmLoadProbeBtn.textContent = "Loading shared XLM...";
      }} else if (mode === "lang_modules") {{
        langLoadProbeBtn.textContent = "Loading language modules...";
      }} else {{
        fullLoadProbeBtn.textContent = "Loading full pipeline...";
      }}
      const started = performance.now();
      const updateTimer = () => {{
        const elapsed = (performance.now() - started) / 1000;
        probeOut.textContent = `Running ${{label}} probe: CPU then GPU...\\nElapsed: ${{fmtSeconds(elapsed)}}`;
      }};
      updateTimer();
      const timerId = window.setInterval(updateTimer, 250);
      try {{
        const res = await fetch("/api/load_probe", {{
          method: "POST",
          headers: {{ "Content-Type": "application/json" }},
          body: JSON.stringify({{
            mode,
            lang: document.getElementById("lang").value,
            warmup_text: document.getElementById("text").value
          }})
        }});
        const data = await res.json();
        renderLoadProbe(data);
      }} catch (err) {{
        probeOut.innerHTML = `<span class="error">${{String(err)}}</span>`;
      }} finally {{
        window.clearInterval(timerId);
        xlmLoadProbeBtn.disabled = false;
        langLoadProbeBtn.disabled = false;
        fullLoadProbeBtn.disabled = false;
        xlmLoadProbeBtn.textContent = xlmLabel;
        langLoadProbeBtn.textContent = langLabel;
        fullLoadProbeBtn.textContent = fullLabel;
        refreshStatus();
      }}
    }}

    xlmLoadProbeBtn.addEventListener("click", () => runLoadProbe("xlm_only"));
    langLoadProbeBtn.addEventListener("click", () => runLoadProbe("lang_modules"));
    fullLoadProbeBtn.addEventListener("click", () => runLoadProbe("full"));

    refreshStatus();
    setInterval(refreshStatus, 1500);
  </script>
</body>
</html>"""


@app.route("/api/status")
def api_status() -> Any:
    if not workers:
        return jsonify({
            "gpu": {"state": "not_started"},
            "gpu_opt": {"state": "not_started"},
            "cpu_opt": {"state": "not_started"},
            "onnx_cpu": {"state": "not_started"},
        })
    for worker in workers.values():
        worker.drain()
    status = {
        "gpu": {"state": "not_started"},
        "gpu_opt": {"state": "not_started"},
        "cpu_opt": {"state": "not_started"},
        "onnx_cpu": {"state": "not_started"},
    }
    status.update({name: worker.status for name, worker in workers.items()})
    if cpu_opt_selection is not None:
        status["cpu_opt_selection"] = cpu_opt_selection
    return jsonify(status)


@app.route("/api/analyze", methods=["POST"])
def api_analyze() -> Any:
    if not {"cpu", "gpu"}.issubset(workers):
        return jsonify({"ok": False, "error": "workers are not started"}), 503
    data = request.get_json(silent=True) or {}
    text = str(data.get("text") or "")
    if not text.strip():
        return jsonify({"ok": False, "error": "empty text"}), 400

    request_id = uuid.uuid4().hex
    command = {
        "type": "analyze",
        "request_id": request_id,
        "text": text,
        "lang": str(data.get("lang") or "zh"),
        "trankit_override": str(data.get("trankit_override") or ""),
        "manual_sentence_segmentation": bool(data.get("manual_sentence_segmentation")),
        "strip_punctuation": bool(data.get("strip_punctuation")),
    }

    cpu_result = workers["cpu"].analyze(command)
    gpu_result = workers["gpu"].analyze(command)
    for worker in workers.values():
        worker.drain()

    return jsonify({
        "ok": bool(cpu_result.get("ok") and gpu_result.get("ok")),
        "request_id": request_id,
        "text_chars": len(text),
        "load": {
            "cpu": workers["cpu"].status.get("load_metrics"),
            "gpu": workers["gpu"].status.get("load_metrics"),
        },
        "devices": {
            "cpu": cpu_result,
            "gpu": gpu_result,
        },
    })


@app.route("/api/analyze_cpu_opt_vs_gpu", methods=["POST"])
def api_analyze_cpu_opt_vs_gpu() -> Any:
    global cpu_opt_selection
    if not {"cpu_opt", "gpu"}.issubset(workers) or cpu_opt_selection is None:
        return jsonify({"ok": False, "error": "optimized CPU and GPU workers are not started"}), 503
    for worker in workers.values():
        worker.drain()
    cpu_status = workers["cpu_opt"].status
    gpu_status = workers["gpu"].status
    if cpu_status.get("state") != "ready" or gpu_status.get("state") != "ready":
        status_error = ""
        if cpu_status.get("state") == "error":
            status_error = str(cpu_status.get("error") or "optimized CPU worker is in error state")
        elif gpu_status.get("state") == "error":
            status_error = str(gpu_status.get("error") or "GPU worker is in error state")
        else:
            status_error = "workers are still loading"
        return jsonify({
            "ok": False,
            "error": status_error,
            "load": {
                "cpu_opt": cpu_status.get("load_metrics"),
                "gpu": gpu_status.get("load_metrics"),
            },
            "worker_status": {
                "cpu_opt": cpu_status,
                "gpu": gpu_status,
            },
            "cpu_opt_selection": cpu_opt_selection,
            "comparison": {
                "cpu_opt_seconds": None,
                "gpu_seconds": None,
                "cpu_opt_vs_gpu_ratio": None,
                "output_match": False,
                "cpu_opt_fingerprint": None,
                "gpu_fingerprint": None,
            },
            "discrepancies": {
                "match": False,
                "diff_count": None,
                "truncated": False,
                "text": status_error,
            },
            "devices": {
                "cpu_opt": {
                    "type": "result",
                    "device": "cpu_opt",
                    "ok": False,
                    "error": status_error,
                    "status": cpu_status,
                },
                "gpu": {
                    "type": "result",
                    "device": "gpu",
                    "ok": False,
                    "error": status_error,
                    "status": gpu_status,
                },
            },
        }), 503
    data = request.get_json(silent=True) or {}
    text = str(data.get("text") or "")
    if not text.strip():
        return jsonify({"ok": False, "error": "empty text"}), 400

    request_id = uuid.uuid4().hex
    command = {
        "type": "analyze",
        "request_id": request_id,
        "text": text,
        "lang": str(data.get("lang") or "zh"),
        "trankit_override": str(data.get("trankit_override") or ""),
        "manual_sentence_segmentation": bool(data.get("manual_sentence_segmentation")),
        "strip_punctuation": bool(data.get("strip_punctuation")),
    }

    cpu_opt_result = workers["cpu_opt"].analyze(command)
    gpu_result = workers["gpu"].analyze(command)
    for worker in workers.values():
        worker.drain()
    cached_selection = _read_cpu_opt_selection_cache()
    if cached_selection is not None:
        cpu_opt_selection = cached_selection
    selection = cpu_opt_selection

    cpu_metrics = cpu_opt_result.get("metrics") if isinstance(cpu_opt_result, dict) else None
    gpu_metrics = gpu_result.get("metrics") if isinstance(gpu_result, dict) else None
    cpu_seconds = cpu_metrics.get("elapsed_seconds") if isinstance(cpu_metrics, dict) else None
    gpu_seconds = gpu_metrics.get("elapsed_seconds") if isinstance(gpu_metrics, dict) else None
    ratio = None
    if isinstance(cpu_seconds, (int, float)) and isinstance(gpu_seconds, (int, float)) and gpu_seconds:
        ratio = cpu_seconds / gpu_seconds
    cpu_fingerprint = cpu_metrics.get("output_fingerprint") if isinstance(cpu_metrics, dict) else None
    gpu_fingerprint = gpu_metrics.get("output_fingerprint") if isinstance(gpu_metrics, dict) else None
    if cpu_opt_result.get("ok") and gpu_result.get("ok"):
        discrepancies = _annotation_discrepancy_report(
            cpu_opt_result.get("annotations"),
            gpu_result.get("annotations"),
        )
    else:
        discrepancies = {
            "match": False,
            "diff_count": None,
            "truncated": False,
            "text": "Comparison unavailable because one output failed.",
        }

    return jsonify({
        "ok": bool(cpu_opt_result.get("ok") and gpu_result.get("ok")),
        "request_id": request_id,
        "text_chars": len(text),
        "load": {
            "cpu_opt": workers["cpu_opt"].status.get("load_metrics"),
            "gpu": workers["gpu"].status.get("load_metrics"),
        },
        "cpu_opt_selection": selection,
        "worker_status": {
            "cpu_opt": workers["cpu_opt"].status,
            "gpu": workers["gpu"].status,
        },
        "comparison": {
            "cpu_opt_seconds": cpu_seconds,
            "gpu_seconds": gpu_seconds,
            "cpu_opt_vs_gpu_ratio": ratio,
            "output_match": bool(cpu_fingerprint and cpu_fingerprint == gpu_fingerprint),
            "cpu_opt_fingerprint": cpu_fingerprint,
            "gpu_fingerprint": gpu_fingerprint,
        },
        "discrepancies": discrepancies,
        "devices": {
            "cpu_opt": cpu_opt_result,
            "gpu": gpu_result,
        },
    })


@app.route("/api/analyze_gpu_opt_vs_gpu", methods=["POST"])
def api_analyze_gpu_opt_vs_gpu() -> Any:
    if not {"gpu_opt", "gpu"}.issubset(workers):
        return jsonify({"ok": False, "error": "optimized GPU and regular GPU workers are not started"}), 503
    for worker in workers.values():
        worker.drain()
    gpu_opt_status = workers["gpu_opt"].status
    gpu_status = workers["gpu"].status
    if gpu_opt_status.get("state") != "ready" or gpu_status.get("state") != "ready":
        if gpu_opt_status.get("state") == "error":
            status_error = str(gpu_opt_status.get("error") or "optimized GPU worker is in error state")
        elif gpu_status.get("state") == "error":
            status_error = str(gpu_status.get("error") or "regular GPU worker is in error state")
        else:
            status_error = "workers are still loading"
        return jsonify({
            "ok": False,
            "error": status_error,
            "load": {
                "gpu_opt": gpu_opt_status.get("load_metrics"),
                "gpu": gpu_status.get("load_metrics"),
            },
            "worker_status": {
                "gpu_opt": gpu_opt_status,
                "gpu": gpu_status,
            },
            "comparison": {
                "gpu_opt_seconds": None,
                "gpu_seconds": None,
                "gpu_opt_speedup_ratio": None,
                "output_match": False,
                "gpu_opt_fingerprint": None,
                "gpu_fingerprint": None,
            },
            "discrepancies": {
                "match": False,
                "diff_count": None,
                "truncated": False,
                "text": status_error,
            },
            "devices": {
                "gpu_opt": {
                    "type": "result",
                    "device": "gpu_opt",
                    "ok": False,
                    "error": status_error,
                    "status": gpu_opt_status,
                },
                "gpu": {
                    "type": "result",
                    "device": "gpu",
                    "ok": False,
                    "error": status_error,
                    "status": gpu_status,
                },
            },
        }), 503

    data = request.get_json(silent=True) or {}
    text = str(data.get("text") or "")
    if not text.strip():
        return jsonify({"ok": False, "error": "empty text"}), 400

    request_id = uuid.uuid4().hex
    command = {
        "type": "analyze",
        "request_id": request_id,
        "text": text,
        "lang": str(data.get("lang") or "zh"),
        "trankit_override": str(data.get("trankit_override") or ""),
        "manual_sentence_segmentation": bool(data.get("manual_sentence_segmentation")),
        "strip_punctuation": bool(data.get("strip_punctuation")),
    }

    gpu_opt_result = workers["gpu_opt"].analyze(command)
    gpu_result = workers["gpu"].analyze(command)
    for worker in workers.values():
        worker.drain()

    gpu_opt_metrics = gpu_opt_result.get("metrics") if isinstance(gpu_opt_result, dict) else None
    gpu_metrics = gpu_result.get("metrics") if isinstance(gpu_result, dict) else None
    gpu_opt_seconds = gpu_opt_metrics.get("elapsed_seconds") if isinstance(gpu_opt_metrics, dict) else None
    gpu_seconds = gpu_metrics.get("elapsed_seconds") if isinstance(gpu_metrics, dict) else None
    speedup = None
    if isinstance(gpu_opt_seconds, (int, float)) and isinstance(gpu_seconds, (int, float)) and gpu_opt_seconds:
        speedup = gpu_seconds / gpu_opt_seconds
    gpu_opt_fingerprint = gpu_opt_metrics.get("output_fingerprint") if isinstance(gpu_opt_metrics, dict) else None
    gpu_fingerprint = gpu_metrics.get("output_fingerprint") if isinstance(gpu_metrics, dict) else None
    if gpu_opt_result.get("ok") and gpu_result.get("ok"):
        discrepancies = _annotation_discrepancy_report(
            gpu_opt_result.get("annotations"),
            gpu_result.get("annotations"),
        )
    else:
        discrepancies = {
            "match": False,
            "diff_count": None,
            "truncated": False,
            "text": "Comparison unavailable because one output failed.",
        }

    return jsonify({
        "ok": bool(gpu_opt_result.get("ok") and gpu_result.get("ok")),
        "request_id": request_id,
        "text_chars": len(text),
        "load": {
            "gpu_opt": workers["gpu_opt"].status.get("load_metrics"),
            "gpu": workers["gpu"].status.get("load_metrics"),
        },
        "worker_status": {
            "gpu_opt": workers["gpu_opt"].status,
            "gpu": workers["gpu"].status,
        },
        "comparison": {
            "gpu_opt_seconds": gpu_opt_seconds,
            "gpu_seconds": gpu_seconds,
            "gpu_opt_speedup_ratio": speedup,
            "output_match": bool(gpu_opt_fingerprint and gpu_opt_fingerprint == gpu_fingerprint),
            "gpu_opt_fingerprint": gpu_opt_fingerprint,
            "gpu_fingerprint": gpu_fingerprint,
        },
        "discrepancies": discrepancies,
        "devices": {
            "gpu_opt": gpu_opt_result,
            "gpu": gpu_result,
        },
    })


@app.route("/api/analyze_onnx_cpu_vs_gpu", methods=["POST"])
def api_analyze_onnx_cpu_vs_gpu() -> Any:
    if not {"onnx_cpu", "gpu"}.issubset(workers):
        return jsonify({"ok": False, "error": "ONNX CPU and GPU workers are not started"}), 503
    for worker in workers.values():
        worker.drain()
    onnx_status = workers["onnx_cpu"].status
    gpu_status = workers["gpu"].status
    if onnx_status.get("state") != "ready" or gpu_status.get("state") != "ready":
        if onnx_status.get("state") == "error":
            status_error = str(onnx_status.get("error") or "ONNX CPU worker is in error state")
        elif gpu_status.get("state") == "error":
            status_error = str(gpu_status.get("error") or "regular GPU worker is in error state")
        else:
            status_error = "workers are still loading"
        return jsonify({
            "ok": False,
            "error": status_error,
            "load": {
                "onnx_cpu": onnx_status.get("load_metrics"),
                "gpu": gpu_status.get("load_metrics"),
            },
            "worker_status": {
                "onnx_cpu": onnx_status,
                "gpu": gpu_status,
            },
            "comparison": {
                "onnx_cpu_seconds": None,
                "gpu_seconds": None,
                "onnx_cpu_vs_gpu_ratio": None,
                "output_match": False,
                "onnx_cpu_fingerprint": None,
                "gpu_fingerprint": None,
            },
            "discrepancies": {
                "match": False,
                "diff_count": None,
                "truncated": False,
                "text": status_error,
            },
            "devices": {
                "onnx_cpu": {
                    "type": "result",
                    "device": "onnx_cpu",
                    "ok": False,
                    "error": status_error,
                    "status": onnx_status,
                },
                "gpu": {
                    "type": "result",
                    "device": "gpu",
                    "ok": False,
                    "error": status_error,
                    "status": gpu_status,
                },
            },
        }), 503
    data = request.get_json(silent=True) or {}
    text = str(data.get("text") or "")
    if not text.strip():
        return jsonify({"ok": False, "error": "empty text"}), 400

    request_id = uuid.uuid4().hex
    command = {
        "type": "analyze",
        "request_id": request_id,
        "text": text,
        "lang": str(data.get("lang") or "zh"),
        "trankit_override": str(data.get("trankit_override") or ""),
        "manual_sentence_segmentation": bool(data.get("manual_sentence_segmentation")),
        "strip_punctuation": bool(data.get("strip_punctuation")),
    }

    onnx_result = workers["onnx_cpu"].analyze(command)
    gpu_result = workers["gpu"].analyze(command)
    for worker in workers.values():
        worker.drain()

    onnx_metrics = onnx_result.get("metrics") if isinstance(onnx_result, dict) else None
    gpu_metrics = gpu_result.get("metrics") if isinstance(gpu_result, dict) else None
    onnx_seconds = onnx_metrics.get("elapsed_seconds") if isinstance(onnx_metrics, dict) else None
    gpu_seconds = gpu_metrics.get("elapsed_seconds") if isinstance(gpu_metrics, dict) else None
    ratio = None
    if isinstance(onnx_seconds, (int, float)) and isinstance(gpu_seconds, (int, float)) and gpu_seconds:
        ratio = onnx_seconds / gpu_seconds
    onnx_fingerprint = onnx_metrics.get("output_fingerprint") if isinstance(onnx_metrics, dict) else None
    gpu_fingerprint = gpu_metrics.get("output_fingerprint") if isinstance(gpu_metrics, dict) else None
    if onnx_result.get("ok") and gpu_result.get("ok"):
        discrepancies = _annotation_discrepancy_report(
            onnx_result.get("annotations"),
            gpu_result.get("annotations"),
        )
    else:
        discrepancies = {
            "match": False,
            "diff_count": None,
            "truncated": False,
            "text": "Comparison unavailable because one output failed.",
        }

    return jsonify({
        "ok": bool(onnx_result.get("ok") and gpu_result.get("ok")),
        "request_id": request_id,
        "text_chars": len(text),
        "load": {
            "onnx_cpu": workers["onnx_cpu"].status.get("load_metrics"),
            "gpu": workers["gpu"].status.get("load_metrics"),
        },
        "worker_status": {
            "onnx_cpu": workers["onnx_cpu"].status,
            "gpu": workers["gpu"].status,
        },
        "comparison": {
            "onnx_cpu_seconds": onnx_seconds,
            "gpu_seconds": gpu_seconds,
            "onnx_cpu_vs_gpu_ratio": ratio,
            "output_match": bool(onnx_fingerprint and onnx_fingerprint == gpu_fingerprint),
            "onnx_cpu_fingerprint": onnx_fingerprint,
            "gpu_fingerprint": gpu_fingerprint,
        },
        "discrepancies": discrepancies,
        "devices": {
            "onnx_cpu": onnx_result,
            "gpu": gpu_result,
        },
    })


@app.route("/api/load_probe", methods=["POST"])
def api_load_probe() -> Any:
    data = request.get_json(silent=True) or {}
    mode = str(data.get("mode") or "").strip().lower()
    if mode not in {"xlm_only", "lang_modules", "full"}:
        return jsonify({"ok": False, "error": "mode must be xlm_only, lang_modules, or full"}), 400
    raw_lang = str(data.get("lang") or "zh").strip().lower()
    warmup_text = str(data.get("warmup_text") or "")
    if mode == "xlm_only":
        description = (
            "Cold-start probe for the shared XLM-R part only: start a fresh process, "
            "import torch/trankit/language_registry, force the selected device, then load "
            "the XLM-R tokenizer/model used by Trankit. No Trankit language modules are loaded."
        )
    elif mode == "lang_modules":
        description = (
            "Cold-start probe for selected language-specific Trankit modules only: start a "
            "fresh process, import torch/trankit/language_registry, force the selected device, "
            "then load the selected language tokenizer classifier, POS/dependency classifier, "
            "lemmatizer, MWT wrapper if required, and NER classifier if registered. Shared "
            "XLM-R is not loaded in this probe."
        )
    else:
        description = (
            "Cold-start simulation for a dedicated Trankit worker: start a fresh process, "
            "import torch/trankit/language_registry, force the selected device, then call "
            "language_registry.init_trankit() to load the full all-language app pipeline."
        )

    started = time.perf_counter()
    cpu_result = run_cold_start_probe_process(mode, "cpu", False, raw_lang, warmup_text)
    gpu_result = run_cold_start_probe_process(mode, "gpu", True, raw_lang, warmup_text)

    return jsonify({
        "ok": bool(cpu_result.get("ok") and gpu_result.get("ok")),
        "mode": mode,
        "lang": raw_lang,
        "description": description,
        "warmup_inference_requested": bool(warmup_text.strip()),
        "elapsed_seconds": time.perf_counter() - started,
        "devices": {
            "cpu": cpu_result,
            "gpu": gpu_result,
        },
    })


def _start_worker_if_missing(
    name: str,
    device: str,
    use_gpu: bool,
    ctx: Any,
    *,
    optimized_cpu: bool = False,
    optimized_gpu: bool = False,
    onnx_cpu: bool = False,
    cpu_opt_profile: str = "runtime_patches",
    cpu_opt_thread_count: Optional[int] = None,
    cpu_opt_tok_batch_size: Optional[int] = None,
    cpu_opt_tag_batch_size: Optional[int] = None,
    cpu_opt_skip_startup_tuning: bool = False,
) -> None:
    existing = workers.get(name)
    if existing is not None:
        try:
            existing.drain()
            if existing.process.is_alive():
                return
        except Exception:
            pass
    workers[name] = WorkerHandle(
        device,
        use_gpu,
        ctx,
        optimized_cpu=optimized_cpu,
        optimized_gpu=optimized_gpu,
        onnx_cpu=onnx_cpu,
        cpu_opt_profile=cpu_opt_profile,
        cpu_opt_thread_count=cpu_opt_thread_count,
        cpu_opt_tok_batch_size=cpu_opt_tok_batch_size,
        cpu_opt_tag_batch_size=cpu_opt_tag_batch_size,
        cpu_opt_skip_startup_tuning=cpu_opt_skip_startup_tuning,
    )
    workers[name].start()


def _startup_status_line(name: str, status: Dict[str, Any]) -> str:
    state = str(status.get("state") or "unknown")
    pid = status.get("pid")
    error = status.get("error")
    pieces = [f"{name}={state}"]
    if pid:
        pieces.append(f"pid={pid}")
    if error:
        pieces.append(f"error={error}")
    return " ".join(pieces)


def wait_for_required_workers(required_names: list[str]) -> None:
    deadline = time.time() + STARTUP_WORKER_TIMEOUT_SECONDS
    last_line = ""
    print(
        "Waiting for benchmark workers to fully load before serving: "
        + ", ".join(required_names),
        flush=True,
    )
    while time.time() < deadline:
        for worker in workers.values():
            worker.drain()

        statuses = {name: workers[name].status for name in required_names if name in workers}
        line = " | ".join(_startup_status_line(name, statuses.get(name, {})) for name in required_names)
        if line != last_line:
            print(line, flush=True)
            last_line = line

        for name, status in statuses.items():
            if status.get("state") == "error":
                raise RuntimeError(
                    f"Benchmark worker '{name}' failed during startup before lookup. "
                    f"Status: {json.dumps(status, ensure_ascii=False, default=str)}"
                )

        if all(status.get("state") == "ready" for status in statuses.values()) and len(statuses) == len(required_names):
            print("Benchmark workers are ready; starting Flask server.", flush=True)
            return

        time.sleep(1.0)

    timed_out = {
        name: workers[name].status
        for name in required_names
        if name in workers
    }
    raise RuntimeError(
        "Benchmark workers did not finish startup before timeout. "
        f"Status: {json.dumps(timed_out, ensure_ascii=False, default=str)}"
    )


def start_workers() -> None:
    global workers_started, cpu_opt_selection
    ctx = mp.get_context("spawn")
    _start_worker_if_missing("gpu", "gpu", True, ctx)
    _start_worker_if_missing(
        "onnx_cpu",
        "onnx_cpu",
        False,
        ctx,
        onnx_cpu=True,
    )
    wait_for_required_workers(["onnx_cpu", "gpu"])
    workers_started = True


def ensure_workers_started() -> None:
    if workers_started:
        return
    raise RuntimeError("workers are not started; start_workers() must run before serving requests")


def ensure_cpu_opt_gpu_started(command: Dict[str, Any]) -> Dict[str, Any]:
    if cpu_opt_selection is None:
        raise RuntimeError("optimized CPU worker is not started; start_workers() must run before serving requests")
    return cpu_opt_selection


def stop_workers() -> None:
    for worker in workers.values():
        worker.shutdown()


if __name__ == "__main__":
    try:
        start_workers()
        app.run(host=HOST, port=PORT, debug=False, use_reloader=False, threaded=True)
    finally:
        stop_workers()
