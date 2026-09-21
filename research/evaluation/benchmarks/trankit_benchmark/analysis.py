"""Trankit benchmark: analysis."""

from __future__ import annotations

from typing import Any, Dict

from . import instrumentation


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
        manual_sentence_segmentation
        and strip_punctuation
        and lang_code in {"sa", "lzh"}
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
    with instrumentation._temporary_trankit_task_breakdown(
        pipeline_obj, torch_module, use_gpu, lr
    ) as task_counter:
        if optimized_cpu or optimized_gpu:
            with instrumentation._temporary_no_gc_collect() as gc_counter:
                with instrumentation._temporary_no_cuda_empty_cache(
                    torch_module
                ) as cuda_counter:
                    with instrumentation._temporary_tensor_sync_point_counter(
                        torch_module
                    ) as sync_counter:
                        with instrumentation._torch_cpu_inference_context(
                            torch_module, bf16_autocast if optimized_cpu else False
                        ):
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
    return (
        doc,
        lang_code,
        gc_calls,
        cuda_empty_cache_calls,
        sync_point_report,
        task_breakdown,
    )
