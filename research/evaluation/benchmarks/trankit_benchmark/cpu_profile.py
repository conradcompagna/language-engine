"""Trankit benchmark: cpu profile."""

from __future__ import annotations

from typing import Any, Dict

from . import cpu_backend, model_cache, model_diagnostics, quantization, settings


def _apply_cpu_optimization_profile(
    pipeline_obj: Any, torch_module: Any, profile: str
) -> Dict[str, Any]:
    report: Dict[str, Any] = {
        "profile": profile,
        "eval_module_count": quantization._force_pipeline_eval(pipeline_obj),
        "eval_status": model_diagnostics._pipeline_eval_status(pipeline_obj),
        "xlmr_quantization": None,
        "xlmr_hidden_state_outputs": None,
        "seq2seq_quantization": None,
        "bf16_autocast": profile == "bf16_autocast",
        "bf16_probe": cpu_backend._detect_cpu_bf16_support(torch_module),
        "torch_compile": None,
        "ipex": None,
        "onnxruntime": None,
        "errors": [],
    }
    if profile in {settings.CPU_OPT_PROFILE_NAME, "xlmr_int8", "xlmr_seq2seq_int8"}:
        try:
            cached = model_cache._load_xlmr_int8_cache(pipeline_obj, torch_module)
            if cached and cached.get("loaded"):
                report["xlmr_quantization"] = {
                    "cache": cached,
                    "quantized_count": int(cached.get("quantized_count") or 0),
                    "from_cache": True,
                }
                report["xlmr_hidden_state_outputs"] = cached.get("hidden_state_report")
            else:
                xlmr = pipeline_obj._embedding_layers.xlmr
                report["xlmr_hidden_state_outputs"] = (
                    quantization._disable_xlmr_hidden_state_outputs(xlmr)
                )
                quant_report = quantization._quantize_selected_children(
                    xlmr,
                    torch_module,
                    skip_adapter_paths=True,
                    excluded_path_tokens=settings.CPU_OPT_QUANTIZE_EXCLUDE_TOKENS,
                    target_type_names=("Linear",),
                )
                if cached:
                    quant_report["cache"] = cached
                report["xlmr_quantization"] = quant_report
                pipeline_obj._embedding_weights = (
                    pipeline_obj._embedding_layers.state_dict()
                )
            report["xlmr_hidden_state_status"] = (
                model_diagnostics._hidden_states_disabled_status(
                    getattr(
                        getattr(pipeline_obj, "_embedding_layers", None), "xlmr", None
                    )
                )
            )
            xlmr_after = getattr(
                getattr(pipeline_obj, "_embedding_layers", None), "xlmr", None
            )
            report["xlmr_adapter_dynamic_int8_count"] = (
                quantization._count_dynamic_int8_modules_matching_path(
                    xlmr_after, "adapter"
                )
            )
        except Exception as exc:
            report["errors"].append(f"xlmr_int8 failed: {exc}")
    if profile == settings.CPU_OPT_PROFILE_NAME:
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
        cached = model_cache._load_seq2seq_int8_cache(pipeline_obj, torch_module)
        if cached and cached.get("loaded"):
            report["seq2seq_quantization"] = [
                {
                    "cache": cached,
                    "quantized_count": int(cached.get("quantized_count") or 0),
                    "from_cache": True,
                }
            ]
        else:
            seq_reports = []
            for name, model in quantization._iter_seq2seq_models(pipeline_obj):
                seq_report = quantization._quantize_selected_children(
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
            pipeline_obj._embedding_weights = (
                pipeline_obj._embedding_layers.state_dict()
            )
            report["torch_compile"] = {"ok": True, "target": "_embedding_layers.xlmr"}
        except Exception as exc:
            report["torch_compile"] = {"ok": False, "error": str(exc)}
            report["errors"].append(f"torch_compile_xlmr failed: {exc}")
    if profile == "ipex_xlmr":
        try:
            import intel_extension_for_pytorch as ipex  # type: ignore

            pipeline_obj._embedding_layers.xlmr = ipex.optimize(
                pipeline_obj._embedding_layers.xlmr.eval()
            )
            pipeline_obj._embedding_weights = (
                pipeline_obj._embedding_layers.state_dict()
            )
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
