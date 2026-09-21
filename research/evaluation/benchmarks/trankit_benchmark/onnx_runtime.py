"""Trankit benchmark: onnx runtime."""

from __future__ import annotations

import os
import time
from typing import Any, Dict

from . import dependencies, settings


class _OnnxXlmrRuntime:
    def __init__(
        self, ort_module: Any, torch_module: Any, sessions: Dict[tuple[str, str], Any]
    ):
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
        attention_mask = (
            attention_masks.detach().cpu().numpy().astype("int64", copy=False)
        )
        outputs = session.run(
            None, {"input_ids": input_ids, "attention_mask": attention_mask}
        )
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
    base = f"{dependencies._safe_onnx_name(lang)}__{dependencies._safe_onnx_name(task)}__xlmr"
    return {
        "raw": os.path.join(settings.ONNX_CACHE_DIR, f"{base}__raw.onnx"),
        "optimized": os.path.join(
            settings.ONNX_CACHE_DIR, f"{base}__ort_optimized.onnx"
        ),
        "int8": os.path.join(settings.ONNX_CACHE_DIR, f"{base}__ort_dynamic_int8.onnx"),
        "meta": os.path.join(settings.ONNX_CACHE_DIR, f"{base}__meta.json"),
    }


def _load_onnx_session(ort_module: Any, path: str) -> Any:
    session_options = ort_module.SessionOptions()
    session_options.graph_optimization_level = (
        ort_module.GraphOptimizationLevel.ORT_ENABLE_ALL
    )
    return ort_module.InferenceSession(
        path, sess_options=session_options, providers=["CPUExecutionProvider"]
    )


def _install_onnx_xlmr_runtime(pipeline_obj: Any, torch_module: Any) -> Dict[str, Any]:
    started = time.perf_counter()
    report: Dict[str, Any] = {
        "profile": settings.ONNX_PROFILE_NAME,
        "deps": dependencies._append_onnx_deps(),
        "cache_dir": settings.ONNX_CACHE_DIR,
        "manifest_path": settings.ONNX_MANIFEST_PATH,
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
        from sandbox_trankit_compressed_runtime import (
            install_compressed_runtime,  # type: ignore
        )
    except Exception as exc:
        report["errors"].append(f"compressed runtime import failed: {exc}")
        report["elapsed_seconds"] = time.perf_counter() - started
        return report

    if not os.path.exists(settings.ONNX_MANIFEST_PATH):
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
            manifest_path=Path(os.path.abspath(settings.ONNX_MANIFEST_PATH)),
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
