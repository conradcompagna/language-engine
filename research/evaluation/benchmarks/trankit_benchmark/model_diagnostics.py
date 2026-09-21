"""Trankit benchmark: model diagnostics."""

from __future__ import annotations

from typing import Any, Dict

from . import quantization


def _pipeline_eval_status(pipeline_obj: Any) -> Dict[str, Any]:
    embedding = getattr(pipeline_obj, "_embedding_layers", None)
    xlmr = getattr(embedding, "xlmr", None)
    return {
        "embedding_eval": bool(
            embedding is not None and not bool(getattr(embedding, "training", True))
        ),
        "xlmr_eval": bool(
            xlmr is not None and not bool(getattr(xlmr, "training", True))
        ),
    }


def _module_dtype_summary(name: str, module: Any) -> Dict[str, Any]:
    summary: Dict[str, Any] = {
        "name": name,
        "present": module is not None,
        "parameter_count": 0,
        "dtype_counts": {},
    }
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
    summary["all_float_params_fp16"] = bool(
        float_param_count > 0 and fp16_param_count == float_param_count
    )
    return summary


def _named_parameter_dtype_summary(
    name: str, module: Any, path_token: str
) -> Dict[str, Any]:
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
    summary["all_float_params_fp16"] = bool(
        float_param_count > 0 and fp16_param_count == float_param_count
    )
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
    for name, model in quantization._iter_seq2seq_models(pipeline_obj):
        modules.append(_module_dtype_summary(name, model))
    checked = [row for row in modules if row.get("present")]
    return {
        "module_count": len(checked),
        "all_checked_float_params_fp16": bool(
            checked
            and all(
                row.get("all_float_params_fp16")
                for row in checked
                if row.get("float_parameter_count")
            )
        ),
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
