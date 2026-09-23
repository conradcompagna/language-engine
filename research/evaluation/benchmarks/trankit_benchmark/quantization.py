"""Trankit benchmark: quantization."""

from __future__ import annotations

from typing import Any, Dict


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
            (
                getattr(torch_module.nn, "Linear", None),
                getattr(dynamic_nn, "Linear", None),
            ),
            (getattr(torch_module.nn, "LSTM", None), getattr(dynamic_nn, "LSTM", None)),
            (getattr(torch_module.nn, "GRU", None), getattr(dynamic_nn, "GRU", None)),
            (
                getattr(torch_module.nn, "LSTMCell", None),
                getattr(dynamic_nn, "LSTMCell", None),
            ),
        ]
        for float_cls, quantized_cls in mappings:
            if (
                float_cls is None
                or quantized_cls is None
                or not isinstance(child, float_cls)
            ):
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
        quantized = quantize_dynamic(
            child, qconfig_spec=qconfig_spec, dtype=torch_module.qint8, inplace=False
        )
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
        matched_excluded_token = next(
            (token for token in excluded_tokens if token in child_path_lower), ""
        )
        if matched_excluded_token:
            report["skipped_excluded_count"] += 1
            if matched_excluded_token == "embedding":
                report["skipped_embedding_count"] += 1
            elif matched_excluded_token in {"layernorm", "layer_norm"}:
                report["skipped_layernorm_count"] += 1
            elif matched_excluded_token == "adapter":
                report["skipped_adapter_count"] += 1
            continue
        quantized, changed, error = _dynamic_quantize_leaf(
            torch_module, child, target_types
        )
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
        report["skipped_embedding_count"] += int(
            nested.get("skipped_embedding_count") or 0
        )
        report["skipped_layernorm_count"] += int(
            nested.get("skipped_layernorm_count") or 0
        )
        report["skipped_excluded_count"] += int(
            nested.get("skipped_excluded_count") or 0
        )
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
            "torch.ao.nn.quantized" in module_name
            and type_name in {"linear", "lstm", "gru", "lstmcell"}
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
