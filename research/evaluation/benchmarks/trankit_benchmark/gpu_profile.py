"""Trankit benchmark: gpu profile."""

from __future__ import annotations

import time
from typing import Any, Dict

from . import (
    analysis,
    comparison,
    cpu_tuning,
    model_diagnostics,
    quantization,
    settings,
)


def _configure_gpu_torch_backend(torch_module: Any) -> Dict[str, Any]:
    report: Dict[str, Any] = {"profile": settings.GPU_OPT_PROFILE_NAME}
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


def _apply_gpu_optimization_profile(
    pipeline_obj: Any, torch_module: Any
) -> Dict[str, Any]:
    report: Dict[str, Any] = {
        "profile": settings.GPU_OPT_PROFILE_NAME,
        "eval_module_count": quantization._force_pipeline_eval(pipeline_obj),
        "eval_status": model_diagnostics._pipeline_eval_status(pipeline_obj),
        "backend": _configure_gpu_torch_backend(torch_module),
        "xlmr_hidden_state_outputs": None,
        "xlmr_hidden_state_status": None,
        "fp16_coverage": None,
        "torch_compile": None,
        "errors": [],
    }
    try:
        xlmr = getattr(getattr(pipeline_obj, "_embedding_layers", None), "xlmr", None)
        report["xlmr_hidden_state_outputs"] = (
            quantization._disable_xlmr_hidden_state_outputs(xlmr)
        )
        report["xlmr_hidden_state_status"] = (
            model_diagnostics._hidden_states_disabled_status(xlmr)
        )
    except Exception as exc:
        report["errors"].append(f"hidden-state patch failed: {exc}")

    try:
        report["fp16_coverage"] = model_diagnostics._gpu_fp16_coverage_report(
            pipeline_obj
        )
    except Exception as exc:
        report["fp16_coverage"] = {"error": str(exc)}

    if settings.GPU_OPT_ENABLE_TORCH_COMPILE:
        try:
            if not hasattr(torch_module, "compile"):
                raise RuntimeError("torch.compile is unavailable")
            pipeline_obj._embedding_layers.xlmr = torch_module.compile(
                pipeline_obj._embedding_layers.xlmr,
                mode="reduce-overhead",
            )
            pipeline_obj._embedding_weights = (
                pipeline_obj._embedding_layers.state_dict()
            )
            report["torch_compile"] = {
                "status": "kept",
                "target": "_embedding_layers.xlmr",
            }
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
    command = cpu_tuning._cpu_opt_tuning_command()
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
    for bucket in settings.GPU_OPT_SEQUENCE_BUCKETS:
        row: Dict[str, Any] = {"bucket": bucket}
        try:
            measured_started = time.perf_counter()
            doc, lang_code, gc_calls, cuda_empty_cache_calls, sync_report = (
                analysis._run_analysis_command(
                    lr,
                    run_with_universal_normalization,
                    torch_module,
                    _gpu_opt_bucket_command(bucket),
                    use_gpu=True,
                    optimized_gpu=True,
                )
            )
            row.update(
                {
                    "ok": True,
                    "elapsed_seconds": time.perf_counter() - measured_started,
                    "lang": lang_code,
                    "fingerprint": comparison._annotation_fingerprint(doc),
                    "counts": comparison._annotation_counts(doc),
                    "gc_collect_calls_suppressed": gc_calls,
                    "cuda_empty_cache_calls_suppressed": cuda_empty_cache_calls,
                    "sync_points": sync_report,
                }
            )
        except Exception as exc:
            row.update({"ok": False, "error": str(exc)})
        report["bucket_results"].append(row)
    report["elapsed_seconds"] = time.perf_counter() - started
    return report
