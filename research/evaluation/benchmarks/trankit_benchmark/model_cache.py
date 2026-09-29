"""Trankit benchmark: model cache."""

from __future__ import annotations

import os
import time
from typing import Any, Dict, Optional

from . import quantization, settings


def _load_xlmr_int8_cache(
    pipeline_obj: Any, torch_module: Any
) -> Optional[Dict[str, Any]]:
    if not os.path.exists(settings.CPU_OPT_XLMR_CACHE_PATH):
        return None
    try:
        payload = quantization._torch_load_sandbox(
            torch_module, settings.CPU_OPT_XLMR_CACHE_PATH
        )
        if (
            isinstance(payload, dict)
            and payload.get("cache_version") != settings.CPU_OPT_XLMR_CACHE_VERSION
        ):
            raise ValueError("cached XLM-R module cache version mismatch")
        if (
            isinstance(payload, dict)
            and tuple(payload.get("excluded_path_tokens") or ())
            != settings.CPU_OPT_QUANTIZE_EXCLUDE_TOKENS
        ):
            raise ValueError("cached XLM-R module exclusion rules mismatch")
        module = payload.get("module") if isinstance(payload, dict) else payload
        if module is None:
            raise ValueError("missing XLM-R module")
        pipeline_obj._embedding_layers.xlmr = module
        hidden_state_report = quantization._disable_xlmr_hidden_state_outputs(module)
        pipeline_obj._embedding_layers.eval()
        pipeline_obj._embedding_weights = pipeline_obj._embedding_layers.state_dict()
        quantized_count = quantization._count_dynamic_int8_modules(module)
        if quantized_count <= 0:
            raise ValueError("cached XLM-R module has no dynamic INT8 modules")
        return {
            "loaded": True,
            "path": settings.CPU_OPT_XLMR_CACHE_PATH,
            "quantized_count": quantized_count,
            "hidden_state_report": hidden_state_report,
            "cache_version": settings.CPU_OPT_XLMR_CACHE_VERSION,
            "excluded_path_tokens": list(settings.CPU_OPT_QUANTIZE_EXCLUDE_TOKENS),
            "target_type_names": ["Linear"],
        }
    except Exception as exc:
        return {
            "loaded": False,
            "path": settings.CPU_OPT_XLMR_CACHE_PATH,
            "error": str(exc),
        }


def _save_xlmr_int8_cache(pipeline_obj: Any, torch_module: Any) -> Dict[str, Any]:
    try:
        quantized_count = quantization._count_dynamic_int8_modules(
            pipeline_obj._embedding_layers.xlmr
        )
        os.makedirs(settings.CPU_OPT_CACHE_DIR, exist_ok=True)
        torch_module.save(
            {
                "cache_version": settings.CPU_OPT_XLMR_CACHE_VERSION,
                "created_at": time.time(),
                "quantized_count": quantized_count,
                "torch_version": str(getattr(torch_module, "__version__", "")),
                "profile": settings.CPU_OPT_PROFILE_NAME,
                "hidden_states_disabled": True,
                "excluded_path_tokens": list(settings.CPU_OPT_QUANTIZE_EXCLUDE_TOKENS),
                "target_type_names": ["Linear"],
                "module": pipeline_obj._embedding_layers.xlmr,
            },
            settings.CPU_OPT_XLMR_CACHE_PATH,
        )
        return {
            "saved": True,
            "path": settings.CPU_OPT_XLMR_CACHE_PATH,
            "cache_version": settings.CPU_OPT_XLMR_CACHE_VERSION,
            "quantized_count": quantized_count,
            "excluded_path_tokens": list(settings.CPU_OPT_QUANTIZE_EXCLUDE_TOKENS),
            "target_type_names": ["Linear"],
        }
    except Exception as exc:
        return {
            "saved": False,
            "path": settings.CPU_OPT_XLMR_CACHE_PATH,
            "error": str(exc),
        }


def _load_seq2seq_int8_cache(
    pipeline_obj: Any, torch_module: Any
) -> Optional[Dict[str, Any]]:
    if not os.path.exists(settings.CPU_OPT_SEQ2SEQ_CACHE_PATH):
        return None
    try:
        payload = quantization._torch_load_sandbox(
            torch_module, settings.CPU_OPT_SEQ2SEQ_CACHE_PATH
        )
        modules = payload.get("modules") if isinstance(payload, dict) else None
        if not isinstance(modules, dict):
            raise ValueError("missing seq2seq module map")
        loaded = []
        missing = []
        quantized_count = 0
        for name, module in modules.items():
            if quantization._set_seq2seq_model_by_name(pipeline_obj, str(name), module):
                loaded.append(str(name))
                quantized_count += quantization._count_dynamic_int8_modules(module)
            else:
                missing.append(str(name))
        if loaded and quantized_count <= 0:
            raise ValueError("cached seq2seq modules have no dynamic INT8 modules")
        return {
            "loaded": True,
            "path": settings.CPU_OPT_SEQ2SEQ_CACHE_PATH,
            "loaded_count": len(loaded),
            "missing_count": len(missing),
            "missing": missing[:25],
            "quantized_count": quantized_count,
        }
    except Exception as exc:
        return {
            "loaded": False,
            "path": settings.CPU_OPT_SEQ2SEQ_CACHE_PATH,
            "error": str(exc),
        }


def _save_seq2seq_int8_cache(pipeline_obj: Any, torch_module: Any) -> Dict[str, Any]:
    try:
        modules = {
            name: model
            for name, model in quantization._iter_seq2seq_models(pipeline_obj)
        }
        if not modules:
            return {
                "saved": False,
                "path": settings.CPU_OPT_SEQ2SEQ_CACHE_PATH,
                "error": "no seq2seq modules found",
            }
        quantized_count = sum(
            quantization._count_dynamic_int8_modules(model)
            for model in modules.values()
        )
        os.makedirs(settings.CPU_OPT_CACHE_DIR, exist_ok=True)
        torch_module.save(
            {
                "cache_version": 1,
                "created_at": time.time(),
                "quantized_count": quantized_count,
                "modules": modules,
            },
            settings.CPU_OPT_SEQ2SEQ_CACHE_PATH,
        )
        return {
            "saved": True,
            "path": settings.CPU_OPT_SEQ2SEQ_CACHE_PATH,
            "module_count": len(modules),
            "quantized_count": quantized_count,
        }
    except Exception as exc:
        return {
            "saved": False,
            "path": settings.CPU_OPT_SEQ2SEQ_CACHE_PATH,
            "error": str(exc),
        }


def _cpu_opt_report_needs_xlmr_cache(optimization_report: Dict[str, Any]) -> bool:
    q = (
        optimization_report.get("xlmr_quantization")
        if isinstance(optimization_report, dict)
        else None
    )
    if not isinstance(q, dict):
        return False
    if q.get("from_cache"):
        return False
    try:
        return int(q.get("quantized_count") or 0) > 0
    except Exception:
        return False


def _cpu_opt_report_needs_seq2seq_cache(optimization_report: Dict[str, Any]) -> bool:
    rows = (
        optimization_report.get("seq2seq_quantization")
        if isinstance(optimization_report, dict)
        else None
    )
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
    if profile in {settings.CPU_OPT_PROFILE_NAME, "xlmr_int8", "xlmr_seq2seq_int8"}:
        if optimization_report is not None and not _cpu_opt_report_needs_xlmr_cache(
            optimization_report
        ):
            report["xlmr_int8_cache"] = {
                "saved": False,
                "skipped": True,
                "reason": "loaded from cache or no new XLM-R quantization",
            }
        else:
            report["xlmr_int8_cache"] = _save_xlmr_int8_cache(
                pipeline_obj, torch_module
            )
    if profile in {"seq2seq_int8", "xlmr_seq2seq_int8"}:
        if optimization_report is not None and not _cpu_opt_report_needs_seq2seq_cache(
            optimization_report
        ):
            report["seq2seq_int8_cache"] = {
                "saved": False,
                "skipped": True,
                "reason": "loaded from cache or no new seq2seq quantization",
            }
        else:
            report["seq2seq_int8_cache"] = _save_seq2seq_int8_cache(
                pipeline_obj, torch_module
            )
    return report
