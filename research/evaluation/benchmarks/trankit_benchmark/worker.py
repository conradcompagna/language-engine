"""Trankit benchmark: worker."""

from __future__ import annotations

import multiprocessing as mp
import os
import time
import traceback
from typing import Any, Dict, Optional

from . import (
    analysis,
    comparison,
    cpu_backend,
    cpu_profile,
    cpu_selection_cache,
    cpu_tuning,
    gpu_profile,
    memory,
    model_cache,
    onnx_batching,
    onnx_runtime,
    quantization,
    settings,
)


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
        memory._force_gc()
        rss_process_start = memory.current_rss_bytes()
        load_started = time.perf_counter()
        send_status("loading", {"rss_process_start_bytes": rss_process_start})

        deps_path_active = False
        thread_report: Dict[str, Any] = {}
        if optimized_cpu:
            deps_path_active = False
            if cpu_opt_thread_count is not None:
                cpu_backend._set_cpu_thread_environment(cpu_opt_thread_count)

        import torch  # type: ignore

        if optimized_cpu and cpu_opt_thread_count is not None:
            thread_report = cpu_backend._set_torch_cpu_threads(
                torch, cpu_opt_thread_count
            )
            thread_report["backend"] = cpu_backend._configure_cpu_torch_backend(torch)

        analysis._install_forced_trankit_pipeline(use_gpu)
        onnx_tokenizer_padding_report: Dict[str, Any] = {}
        onnx_tagger_ner_bucketing_report: Dict[str, Any] = {}
        onnx_dynamic_batching_report: Dict[str, Any] = {}
        if onnx_cpu:
            onnx_tokenizer_padding_report = (
                onnx_batching._install_onnx_tokenizer_dynamic_padding_patch()
            )
            if not onnx_tokenizer_padding_report.get("installed"):
                raise RuntimeError(
                    "ONNX tokenizer dynamic padding patch failed: "
                    f"{onnx_tokenizer_padding_report.get('error') or 'unknown error'}"
                )
            onnx_tagger_ner_bucketing_report = (
                onnx_batching._install_onnx_tagger_ner_length_bucketing_patch()
            )
            if not onnx_tagger_ner_bucketing_report.get("installed"):
                raise RuntimeError(
                    "ONNX POS/NER length bucketing patch failed: "
                    f"{onnx_tagger_ner_bucketing_report.get('error') or 'unknown error'}"
                )
            onnx_dynamic_batching_report = (
                onnx_batching._install_onnx_dynamic_batching_patch()
            )
            if not onnx_dynamic_batching_report.get("installed"):
                raise RuntimeError(
                    "ONNX dynamic batching patch failed: "
                    f"{onnx_dynamic_batching_report.get('error') or 'unknown error'}"
                )
        xlmr_load_patch_report: Dict[str, Any] = {}
        if optimized_cpu or optimized_gpu or onnx_cpu:
            xlmr_load_patch_report = quantization._install_cpu_opt_xlmr_load_patch()

        import language_registry as lr
        from universal_normalization import run_with_universal_normalization

        torch_module = torch
        gpu_before_load = memory._gpu_snapshot(torch_module)
        rss_after_imports = memory.current_rss_bytes()

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
                startup_validation_report["baseline"] = (
                    cpu_tuning._measure_cpu_opt_tuning_case(
                        lr,
                        run_with_universal_normalization,
                        torch_module,
                        cpu_tuning._cpu_opt_tuning_command(),
                        "runtime_patches",
                        repetitions=1,
                    )
                )
            except Exception as exc:
                startup_validation_report["baseline"] = {"ok": False, "error": str(exc)}
            optimization_report = cpu_profile._apply_cpu_optimization_profile(
                getattr(lr, "_trankit_pipeline", None),
                torch_module,
                cpu_opt_profile,
            )
            if optimization_report.get("errors"):
                raise RuntimeError(
                    "; ".join(
                        str(error) for error in optimization_report.get("errors") or []
                    )
                )
            startup_cache_save_report = model_cache._save_cpu_opt_module_caches(
                getattr(lr, "_trankit_pipeline", None),
                torch_module,
                cpu_opt_profile,
                optimization_report,
            )
            if (
                cpu_opt_skip_startup_tuning
                and cpu_opt_tok_batch_size is not None
                and cpu_opt_tag_batch_size is not None
            ):
                startup_tuning_report = {
                    "ok": True,
                    "from_cache": True,
                    "selected_thread_count": int(cpu_opt_thread_count or 1),
                    "selected_tok_batch_size": int(cpu_opt_tok_batch_size),
                    "selected_tag_batch_size": int(cpu_opt_tag_batch_size),
                    "selected_batch_report": cpu_tuning._apply_cpu_opt_batch_sizes(
                        getattr(lr, "_trankit_pipeline", None),
                        int(cpu_opt_tok_batch_size),
                        int(cpu_opt_tag_batch_size),
                    ),
                    "elapsed_seconds": 0.0,
                }
            else:
                startup_tuning_report = cpu_tuning._startup_tune_cpu_opt_runtime(
                    lr,
                    run_with_universal_normalization,
                    torch_module,
                    getattr(lr, "_trankit_pipeline", None),
                    cpu_opt_profile,
                    int(cpu_opt_thread_count or 1),
                )
                startup_selection_payload = {
                    "selected_profile": cpu_opt_profile,
                    "selected_thread_count": int(
                        startup_tuning_report.get("selected_thread_count")
                        or cpu_opt_thread_count
                        or 1
                    ),
                    "selected_tok_batch_size": int(
                        startup_tuning_report.get("selected_tok_batch_size")
                        or settings.CPU_OPT_DEFAULT_TOK_BATCH_SIZE
                    ),
                    "selected_tag_batch_size": int(
                        startup_tuning_report.get("selected_tag_batch_size")
                        or settings.CPU_OPT_DEFAULT_TAG_BATCH_SIZE
                    ),
                    "selected_thread_seconds": startup_tuning_report.get(
                        "selected_thread_seconds"
                    ),
                    "selected_thread_p95_seconds": startup_tuning_report.get(
                        "selected_thread_p95_seconds"
                    ),
                    "selected_batch_seconds": startup_tuning_report.get(
                        "selected_batch_seconds"
                    ),
                    "selected_p95_seconds": startup_tuning_report.get(
                        "selected_thread_p95_seconds"
                    ),
                    "setup_seconds": startup_tuning_report.get("elapsed_seconds"),
                }
            try:
                startup_validation_report["optimized"] = (
                    cpu_tuning._measure_cpu_opt_tuning_case(
                        lr,
                        run_with_universal_normalization,
                        torch_module,
                        cpu_tuning._cpu_opt_tuning_command(),
                        cpu_opt_profile,
                        repetitions=1,
                    )
                )
            except Exception as exc:
                startup_validation_report["optimized"] = {
                    "ok": False,
                    "error": str(exc),
                }
            baseline_fingerprint = ""
            optimized_fingerprint = ""
            try:
                baseline_fingerprint = str(
                    (startup_validation_report.get("baseline") or {}).get("fingerprint")
                    or ""
                )
                optimized_fingerprint = str(
                    (startup_validation_report.get("optimized") or {}).get(
                        "fingerprint"
                    )
                    or ""
                )
            except Exception:
                pass
            startup_validation_report["baseline_fingerprint"] = baseline_fingerprint
            startup_validation_report["optimized_fingerprint"] = optimized_fingerprint
            startup_validation_report["output_match"] = bool(
                baseline_fingerprint
                and optimized_fingerprint
                and baseline_fingerprint == optimized_fingerprint
            )
            if (
                baseline_fingerprint
                and optimized_fingerprint
                and baseline_fingerprint != optimized_fingerprint
            ):
                startup_validation_report["warning"] = (
                    "Optimized CPU startup validation found an annotation fingerprint difference from baseline CPU. "
                    "The worker remains active so the discrepancy pane can show real output differences."
                )
            if startup_selection_payload is not None:
                startup_selection_payload["baseline_fingerprint"] = baseline_fingerprint
                startup_selection_payload["selected_fingerprint"] = (
                    optimized_fingerprint
                )
                startup_selection_payload["output_match"] = bool(
                    baseline_fingerprint
                    and optimized_fingerprint
                    and baseline_fingerprint == optimized_fingerprint
                )
                try:
                    cpu_selection_cache._write_cpu_opt_selection_cache(
                        startup_selection_payload
                    )
                    startup_tuning_report["selection_cache_written"] = True
                    startup_tuning_report["selection_cache_path"] = (
                        settings.CPU_OPT_SELECTION_CACHE_PATH
                    )
                except Exception as exc:
                    startup_tuning_report["selection_cache_write_error"] = str(exc)
            cpu_opt_thread_count = int(
                startup_tuning_report.get("selected_thread_count")
                or cpu_opt_thread_count
                or 1
            )
            cpu_opt_tok_batch_size = int(
                startup_tuning_report.get("selected_tok_batch_size")
                or settings.CPU_OPT_DEFAULT_TOK_BATCH_SIZE
            )
            cpu_opt_tag_batch_size = int(
                startup_tuning_report.get("selected_tag_batch_size")
                or settings.CPU_OPT_DEFAULT_TAG_BATCH_SIZE
            )
        if optimized_gpu:
            gpu_optimization_report = gpu_profile._apply_gpu_optimization_profile(
                getattr(lr, "_trankit_pipeline", None),
                torch_module,
            )
            if gpu_optimization_report.get("errors"):
                raise RuntimeError(
                    "; ".join(
                        str(error)
                        for error in gpu_optimization_report.get("errors") or []
                    )
                )
            gpu_startup_warmup_report = gpu_profile._gpu_opt_startup_warmup(
                lr,
                run_with_universal_normalization,
                torch_module,
            )
        if onnx_cpu:
            onnx_report = onnx_runtime._install_onnx_xlmr_runtime(
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
            onnx_batch_size_report = cpu_tuning._apply_cpu_opt_batch_sizes(
                getattr(lr, "_trankit_pipeline", None),
                settings.ONNX_CPU_TOK_BATCH_SIZE,
                settings.ONNX_CPU_TAG_BATCH_SIZE,
            )
        optimization_seconds = time.perf_counter() - optimization_started

        actual_device = ""
        actual_use_gpu = None
        try:
            actual_device = str(lr._trankit_pipeline._config.device)
            actual_use_gpu = bool(lr._trankit_pipeline._use_gpu)
        except Exception:
            pass

        memory._force_gc()
        if use_gpu and torch_module.cuda.is_available():
            torch_module.cuda.synchronize()
        rss_after_load = memory.current_rss_bytes()
        gpu_after_load = memory._gpu_snapshot(torch_module)
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
            "rss_import_delta_bytes": memory._bytes_delta(
                rss_after_imports, rss_process_start
            ),
            "rss_loaded_pipeline_delta_bytes": memory._bytes_delta(
                rss_after_load, rss_after_imports
            ),
            "rss_total_load_delta_bytes": memory._bytes_delta(
                rss_after_load, rss_process_start
            ),
            "gpu_before_load": gpu_before_load,
            "gpu_after_load": gpu_after_load,
            "gpu_load_delta": memory._gpu_delta(gpu_after_load, gpu_before_load),
        }
        if optimized_cpu:
            load_metrics["optimized_cpu"] = True
            load_metrics["cpu_opt_profile"] = cpu_opt_profile
            load_metrics["cpu_opt_thread_count"] = cpu_opt_thread_count
            load_metrics["cpu_opt_thread_report"] = thread_report
            load_metrics["cpu_opt_deps_path"] = settings.CPU_OPT_DEPS_DIR
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
            load_metrics["gpu_opt_profile"] = settings.GPU_OPT_PROFILE_NAME
            load_metrics["xlmr_load_patch_report"] = xlmr_load_patch_report
            load_metrics["optimization_seconds"] = optimization_seconds
            load_metrics["optimization_report"] = gpu_optimization_report
            load_metrics["startup_warmup_report"] = gpu_startup_warmup_report
        if onnx_cpu:
            load_metrics["onnx_cpu"] = True
            load_metrics["onnx_profile"] = settings.ONNX_PROFILE_NAME
            load_metrics["onnx_tok_batch_size"] = settings.ONNX_CPU_TOK_BATCH_SIZE
            load_metrics["onnx_tag_batch_size"] = settings.ONNX_CPU_TAG_BATCH_SIZE
            load_metrics["onnx_batch_size_report"] = onnx_batch_size_report
            load_metrics["onnx_tokenizer_padding_report"] = (
                onnx_tokenizer_padding_report
            )
            load_metrics["onnx_tagger_ner_bucketing_report"] = (
                onnx_tagger_ner_bucketing_report
            )
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
                    memory._force_gc()
                if (
                    torch_module is not None
                    and use_gpu
                    and torch_module.cuda.is_available()
                ):
                    if not optimized_request:
                        torch_module.cuda.empty_cache()
                    torch_module.cuda.reset_peak_memory_stats()
                    torch_module.cuda.synchronize()

                rss_before = memory.current_rss_bytes()
                gpu_before = memory._gpu_snapshot(torch_module)
                sampler = memory.MemorySampler(torch_module)
                onnx_runtime_manager = None
                onnx_run_count_before: Optional[int] = None
                onnx_runtime_metrics_before: Optional[Dict[str, Any]] = None
                if onnx_cpu:
                    onnx_runtime_manager = getattr(
                        getattr(lr, "_trankit_pipeline", None),
                        "_compressed_xlmr_runtime",
                        None,
                    )
                    if onnx_runtime_manager is not None:
                        try:
                            onnx_runtime_metrics_before = (
                                onnx_runtime_manager.metrics() or {}
                            )
                            onnx_run_count_before = int(
                                onnx_runtime_metrics_before.get("run_count") or 0
                            )
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
                (
                    doc,
                    lang_code,
                    gc_collect_calls,
                    cuda_empty_cache_calls,
                    sync_point_report,
                    task_breakdown_report,
                ) = analysis._run_analysis_command(
                    lr,
                    run_with_universal_normalization,
                    torch_module,
                    command,
                    use_gpu=use_gpu,
                    optimized_cpu=optimized_request,
                    optimized_gpu=optimized_gpu,
                    bf16_autocast=cpu_profile._cpu_profile_uses_bf16(cpu_opt_profile),
                )
                if (
                    torch_module is not None
                    and use_gpu
                    and torch_module.cuda.is_available()
                ):
                    torch_module.cuda.synchronize()
                elapsed = time.perf_counter() - started
                sampler.stop()

                if not optimized_request:
                    memory._force_gc()
                rss_after = memory.current_rss_bytes()
                gpu_after = memory._gpu_snapshot(torch_module)
                fingerprint = comparison._annotation_fingerprint(doc)
                annotation_counts = comparison._annotation_counts(doc)
                sequence_bucket = cpu_tuning._sequence_bucket_for_token_count(
                    annotation_counts.get("token_count")
                )
                inference_metrics = {
                    "request_id": request_id,
                    "device": device_label,
                    "pid": pid,
                    "lang": lang_code,
                    "text_chars": len(text),
                    "elapsed_seconds": elapsed,
                    "rss_before_bytes": rss_before,
                    "rss_after_bytes": rss_after,
                    "rss_delta_bytes": memory._bytes_delta(rss_after, rss_before),
                    "rss_peak_sampled_bytes": sampler.rss_peak_bytes,
                    "rss_peak_sampled_delta_bytes": memory._bytes_delta(
                        sampler.rss_peak_bytes, rss_before
                    ),
                    "sample_count": sampler.samples,
                    "gpu_before": gpu_before,
                    "gpu_after": gpu_after,
                    "gpu_delta": memory._gpu_delta(gpu_after, gpu_before),
                    "gpu_allocated_peak_sampled_bytes": sampler.gpu_allocated_peak_bytes,
                    "gpu_reserved_peak_sampled_bytes": sampler.gpu_reserved_peak_bytes,
                    "gpu_allocator_max_allocated_bytes": gpu_after.get(
                        "max_allocated_bytes"
                    ),
                    "gpu_allocator_max_reserved_bytes": gpu_after.get(
                        "max_reserved_bytes"
                    ),
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
                    inference_metrics["cpu_opt_tok_batch_size"] = getattr(
                        getattr(lr, "_trankit_pipeline", None), "_tokbatchsize", None
                    )
                    inference_metrics["cpu_opt_tag_batch_size"] = getattr(
                        getattr(lr, "_trankit_pipeline", None), "_tagbatchsize", None
                    )
                    inference_metrics["gc_collect_calls_suppressed"] = gc_collect_calls
                    inference_metrics["cuda_empty_cache_calls_suppressed"] = (
                        cuda_empty_cache_calls
                    )
                    inference_metrics["used_inference_mode"] = True
                    inference_metrics["used_bf16_autocast"] = (
                        cpu_profile._cpu_profile_uses_bf16(cpu_opt_profile)
                    )
                if optimized_gpu:
                    inference_metrics["optimized_gpu"] = True
                    inference_metrics["gpu_opt_profile"] = settings.GPU_OPT_PROFILE_NAME
                    inference_metrics["gc_collect_calls_suppressed"] = gc_collect_calls
                    inference_metrics["cuda_empty_cache_calls_suppressed"] = (
                        cuda_empty_cache_calls
                    )
                    inference_metrics["used_inference_mode"] = True
                if onnx_cpu:
                    manager = onnx_runtime_manager or getattr(
                        getattr(lr, "_trankit_pipeline", None),
                        "_compressed_xlmr_runtime",
                        None,
                    )
                    runtime_metrics = manager.metrics() if manager is not None else None
                    if (
                        isinstance(runtime_metrics, dict)
                        and onnx_run_count_before is not None
                    ):
                        try:
                            onnx_run_count_after = int(
                                runtime_metrics.get("run_count") or 0
                            )
                            runtime_metrics["request_run_count"] = max(
                                0, onnx_run_count_after - onnx_run_count_before
                            )
                            runtime_metrics["lifetime_run_count"] = onnx_run_count_after
                            if isinstance(onnx_runtime_metrics_before, dict):
                                request_by_key: Dict[str, Dict[str, Any]] = {}
                                before_by_key = (
                                    onnx_runtime_metrics_before.get("by_key") or {}
                                )
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
                                        before_row = (
                                            before_by_key.get(key)
                                            if isinstance(before_by_key, dict)
                                            else None
                                        )
                                        before_row = (
                                            before_row
                                            if isinstance(before_row, dict)
                                            else {}
                                        )
                                        delta_row: Dict[str, Any] = {}
                                        for field in timing_fields:
                                            after_value = after_row.get(field) or 0
                                            before_value = before_row.get(field) or 0
                                            try:
                                                value = float(after_value) - float(
                                                    before_value
                                                )
                                            except Exception:
                                                value = 0.0
                                            if field == "count":
                                                delta_row[field] = max(
                                                    0, int(round(value))
                                                )
                                            else:
                                                delta_row[field] = max(0.0, value)
                                        if int(delta_row.get("count") or 0) > 0:
                                            request_by_key[str(key)] = delta_row
                                runtime_metrics["request_by_key"] = request_by_key
                                for field in [
                                    "total_seconds",
                                    "preprocess_seconds",
                                    "session_seconds",
                                    "postprocess_seconds",
                                ]:
                                    try:
                                        runtime_metrics[f"request_{field}"] = max(
                                            0.0,
                                            float(runtime_metrics.get(field) or 0.0)
                                            - float(
                                                onnx_runtime_metrics_before.get(field)
                                                or 0.0
                                            ),
                                        )
                                    except Exception:
                                        pass
                        except Exception:
                            pass
                    inference_metrics["onnx_cpu"] = True
                    inference_metrics["onnx_profile"] = settings.ONNX_PROFILE_NAME
                    inference_metrics["onnx_runtime"] = runtime_metrics
                    inference_metrics["onnx_tok_batch_size"] = getattr(
                        getattr(lr, "_trankit_pipeline", None), "_tokbatchsize", None
                    )
                    inference_metrics["onnx_tag_batch_size"] = getattr(
                        getattr(lr, "_trankit_pipeline", None), "_tagbatchsize", None
                    )
                    inference_metrics["onnx_tokenizer_dynamic_padding"] = True
                    inference_metrics["onnx_tagger_ner_length_bucketing"] = True
                    inference_metrics["onnx_dynamic_batching"] = True
                    inference_metrics["onnx_seq2seq_dynamic_batching"] = False
                    try:
                        import trankit.pipeline as trankit_pipeline  # type: ignore

                        events = getattr(
                            trankit_pipeline, "_benchmark_dynamic_batch_events", []
                        )
                        inference_metrics["onnx_dynamic_batch_events"] = (
                            events if isinstance(events, list) else []
                        )
                    except Exception as exc:
                        inference_metrics["onnx_dynamic_batch_events_error"] = str(exc)
                    inference_metrics["gc_collect_calls_suppressed"] = gc_collect_calls
                    inference_metrics["cuda_empty_cache_calls_suppressed"] = (
                        cuda_empty_cache_calls
                    )
                    inference_metrics["used_inference_mode"] = True
                result_queue.put(
                    {
                        "type": "result",
                        "device": device_label,
                        "request_id": request_id,
                        "ok": True,
                        "annotations": doc,
                        "metrics": inference_metrics,
                    }
                )
            except Exception as exc:
                result_queue.put(
                    {
                        "type": "result",
                        "device": device_label,
                        "request_id": request_id,
                        "ok": False,
                        "error": str(exc),
                        "traceback": traceback.format_exc(),
                    }
                )
    except Exception as exc:
        extra = {"error": str(exc), "traceback": traceback.format_exc()}
        if onnx_report_for_error:
            extra["onnx_report"] = onnx_report_for_error
        send_status("error", extra)
