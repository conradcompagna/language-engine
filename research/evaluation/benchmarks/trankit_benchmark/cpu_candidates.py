"""Trankit benchmark: cpu candidates."""

from __future__ import annotations

import multiprocessing as mp
import queue
import time
import traceback
from typing import Any, Dict

from . import (
    analysis,
    comparison,
    cpu_backend,
    cpu_profile,
    cpu_tuning,
    dependencies,
    memory,
    model_cache,
    quantization,
    settings,
)


def _cpu_opt_candidate_worker_main(
    profile: str,
    thread_count: int,
    command: Dict[str, Any],
    result_queue: mp.Queue,
) -> None:
    started = time.perf_counter()
    torch_module = None
    try:
        deps_path_active = (
            profile in {"ipex_xlmr", "onnx_xlmr", "onnx_int8_xlmr"}
            and dependencies._prepend_cpu_opt_deps()
        )
        cpu_backend._set_cpu_thread_environment(thread_count)

        import torch  # type: ignore

        torch_module = torch
        thread_report = cpu_backend._set_torch_cpu_threads(torch_module, thread_count)
        thread_report["backend"] = cpu_backend._configure_cpu_torch_backend(
            torch_module
        )

        if profile == "bf16_autocast":
            bf16_probe = cpu_backend._detect_cpu_bf16_support(torch_module)
            if not bool(bf16_probe.get("supported")):
                result_queue.put(
                    {
                        "ok": False,
                        "skipped": True,
                        "profile": profile,
                        "thread_count": thread_count,
                        "error": str(
                            bf16_probe.get("reason")
                            or "CPU BF16 support was not detected"
                        ),
                        "bf16_probe": bf16_probe,
                        "elapsed_seconds": time.perf_counter() - started,
                        "deps_path_active": deps_path_active,
                        "thread_report": thread_report,
                    }
                )
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
            result_queue.put(
                {
                    "ok": False,
                    "skipped": True,
                    "profile": profile,
                    "thread_count": thread_count,
                    "error": skip_error,
                    "elapsed_seconds": time.perf_counter() - started,
                    "deps_path_active": deps_path_active,
                }
            )
            return

        analysis._install_forced_trankit_pipeline(False)
        quantization._install_cpu_opt_xlmr_load_patch()

        import language_registry as lr
        from universal_normalization import run_with_universal_normalization

        lr.init_trankit()
        apply_started = time.perf_counter()
        optimization_report = cpu_profile._apply_cpu_optimization_profile(
            getattr(lr, "_trankit_pipeline", None),
            torch_module,
            profile,
        )
        batch_report = cpu_tuning._apply_cpu_opt_batch_sizes(
            getattr(lr, "_trankit_pipeline", None),
            settings.CPU_OPT_DEFAULT_TOK_BATCH_SIZE,
            settings.CPU_OPT_DEFAULT_TAG_BATCH_SIZE,
        )
        apply_seconds = time.perf_counter() - apply_started
        if optimization_report.get("errors"):
            result_queue.put(
                {
                    "ok": False,
                    "profile": profile,
                    "thread_count": thread_count,
                    "error": "; ".join(
                        str(e) for e in optimization_report.get("errors") or []
                    ),
                    "optimization_report": optimization_report,
                    "apply_seconds": apply_seconds,
                    "elapsed_seconds": time.perf_counter() - started,
                    "deps_path_active": deps_path_active,
                    "thread_report": thread_report,
                }
            )
            return

        rss_before = memory.current_rss_bytes()
        measure_started = time.perf_counter()
        doc, lang_code, gc_collect_calls, cuda_empty_cache_calls, _sync_report = (
            analysis._run_analysis_command(
                lr,
                run_with_universal_normalization,
                torch_module,
                command,
                use_gpu=False,
                optimized_cpu=True,
                bf16_autocast=cpu_profile._cpu_profile_uses_bf16(profile),
            )
        )
        measure_seconds = time.perf_counter() - measure_started
        rss_after = memory.current_rss_bytes()
        result_queue.put(
            {
                "ok": True,
                "profile": profile,
                "thread_count": thread_count,
                "lang": lang_code,
                "elapsed_seconds": measure_seconds,
                "total_process_seconds": time.perf_counter() - started,
                "apply_seconds": apply_seconds,
                "rss_before_bytes": rss_before,
                "rss_after_bytes": rss_after,
                "rss_delta_bytes": memory._bytes_delta(rss_after, rss_before),
                "output_fingerprint": comparison._annotation_fingerprint(doc),
                "annotation_counts": comparison._annotation_counts(doc),
                "optimization_report": optimization_report,
                "batch_report": batch_report,
                "cache_save_report": model_cache._save_cpu_opt_module_caches(
                    getattr(lr, "_trankit_pipeline", None),
                    torch_module,
                    profile,
                    optimization_report,
                ),
                "deps_path_active": deps_path_active,
                "thread_report": thread_report,
                "gc_collect_calls_suppressed": gc_collect_calls,
                "cuda_empty_cache_calls_suppressed": cuda_empty_cache_calls,
            }
        )
    except Exception as exc:
        result_queue.put(
            {
                "ok": False,
                "profile": profile,
                "thread_count": thread_count,
                "elapsed_seconds": time.perf_counter() - started,
                "rss_after_bytes": memory.current_rss_bytes(),
                "gpu_after": memory._gpu_snapshot(torch_module),
                "error": str(exc),
                "traceback": traceback.format_exc(),
            }
        )


def _run_cpu_opt_candidate_process(
    profile: str, thread_count: int, command: Dict[str, Any]
) -> Dict[str, Any]:
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
        result = result_queue.get(timeout=settings.CPU_OPT_PROFILE_TIMEOUT_SECONDS)
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
    for thread_count in cpu_backend._cpu_thread_candidates():
        thread_results.append(
            _run_cpu_opt_candidate_process("runtime_patches", thread_count, command)
        )

    valid_threads = [row for row in thread_results if row.get("ok")]
    if valid_threads:
        baseline = min(
            valid_threads,
            key=lambda row: float(row.get("elapsed_seconds") or float("inf")),
        )
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
        settings.CPU_OPT_PROFILE_NAME,
        "bf16_autocast",
        "torch_compile_xlmr",
    ]
    profile_results = [
        _run_cpu_opt_candidate_process(profile, selected_thread, command)
        for profile in profile_names
    ]
    candidates = [baseline] + profile_results
    valid_candidates = [
        row
        for row in candidates
        if row.get("ok") and row.get("output_fingerprint") == baseline_fingerprint
    ]
    if valid_candidates:
        selected = min(
            valid_candidates,
            key=lambda row: float(row.get("elapsed_seconds") or float("inf")),
        )
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
        "output_match": bool(
            selected.get("output_fingerprint") == baseline_fingerprint
            and baseline_fingerprint
        ),
        "thread_sweep": thread_results,
        "profile_candidates": profile_results,
        "selected_candidate": selected,
        "setup_seconds": time.perf_counter() - started,
        "deps_path": settings.CPU_OPT_DEPS_DIR,
    }
