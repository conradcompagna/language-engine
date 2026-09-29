"""Trankit benchmark: cpu tuning."""

from __future__ import annotations

import time
from typing import Any, Dict, Optional

from . import analysis, comparison, cpu_backend, cpu_profile, settings


def _sequence_bucket_for_token_count(token_count: Any) -> int:
    try:
        count = max(0, int(token_count))
    except Exception:
        count = 0
    for bucket in settings.CPU_OPT_SEQUENCE_BUCKETS:
        if count <= bucket:
            return bucket
    return settings.CPU_OPT_SEQUENCE_BUCKETS[-1]


def _apply_cpu_opt_batch_sizes(
    pipeline_obj: Any, tok_batch_size: int, tag_batch_size: int
) -> Dict[str, Any]:
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
        "text": settings.CPU_OPT_TUNE_TEXT,
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
    cleaned = sorted(
        float(value)
        for value in values
        if isinstance(value, (int, float)) and value >= 0
    )
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
    repetitions: int = settings.CPU_OPT_TUNE_REPETITIONS,
) -> Dict[str, Any]:
    samples: list[float] = []
    doc: Dict[str, Any] = {}
    lang_code = ""
    gc_calls = 0
    cuda_empty_cache_calls = 0
    total_started = time.perf_counter()
    for _ in range(max(1, int(repetitions))):
        started = time.perf_counter()
        doc, lang_code, gc_run_calls, cuda_run_calls, _sync_report = (
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
        samples.append(time.perf_counter() - started)
        gc_calls += int(gc_run_calls or 0)
        cuda_empty_cache_calls += int(cuda_run_calls or 0)
    counts = comparison._annotation_counts(doc)
    return {
        "ok": True,
        "elapsed_seconds": samples[-1] if samples else None,
        "elapsed_samples_seconds": samples,
        "p50_seconds": _percentile(samples, 50),
        "p95_seconds": _percentile(samples, 95),
        "total_measure_seconds": time.perf_counter() - total_started,
        "lang": lang_code,
        "fingerprint": comparison._annotation_fingerprint(doc),
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
        "repetitions_per_case": settings.CPU_OPT_TUNE_REPETITIONS,
        "thread_results": [],
        "bucket_results": [],
        "batch_results": [
            {"skipped": True, "reason": "This pass does not tune Trankit batch sizes."}
        ],
        "warmup": None,
        "selected_thread_count": initial_thread_count,
        "selected_tok_batch_size": settings.CPU_OPT_DEFAULT_TOK_BATCH_SIZE,
        "selected_tag_batch_size": settings.CPU_OPT_DEFAULT_TAG_BATCH_SIZE,
    }

    _apply_cpu_opt_batch_sizes(
        pipeline_obj,
        settings.CPU_OPT_DEFAULT_TOK_BATCH_SIZE,
        settings.CPU_OPT_DEFAULT_TAG_BATCH_SIZE,
    )
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
    for thread_count in cpu_backend._cpu_thread_candidates():
        row: Dict[str, Any] = {"thread_count": thread_count}
        row["thread_report"] = cpu_backend._set_torch_cpu_threads(
            torch_module, thread_count
        )
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
            if (
                isinstance(elapsed, (int, float))
                and elapsed > 0
                and (best_thread_p95 is None or elapsed < best_thread_p95)
            ):
                best_thread_p95 = float(elapsed)
                best_thread = thread_count
        except Exception as exc:
            row.update({"ok": False, "error": str(exc)})
        report["thread_results"].append(row)

    report["selected_thread_count"] = best_thread
    report["selected_thread_p95_seconds"] = best_thread_p95
    report["selected_thread_seconds"] = best_thread_p95
    report["selected_thread_report"] = cpu_backend._set_torch_cpu_threads(
        torch_module, best_thread
    )

    for bucket in settings.CPU_OPT_SEQUENCE_BUCKETS:
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

    report["selected_tok_batch_size"] = settings.CPU_OPT_DEFAULT_TOK_BATCH_SIZE
    report["selected_tag_batch_size"] = settings.CPU_OPT_DEFAULT_TAG_BATCH_SIZE
    report["selected_batch_seconds"] = None
    report["selected_batch_report"] = _apply_cpu_opt_batch_sizes(
        pipeline_obj,
        settings.CPU_OPT_DEFAULT_TOK_BATCH_SIZE,
        settings.CPU_OPT_DEFAULT_TAG_BATCH_SIZE,
    )
    report["elapsed_seconds"] = time.perf_counter() - started
    return report
