"""
Sandbox prototype: one compressed XLM-R ONNX graph with dynamic Trankit adapters.

This script does not edit production app files or installed Trankit files.

Architecture:
  - one ONNX XLM-R graph, exported once
  - base XLM-R weights are static in the graph and dynamically INT8-quantized
  - Trankit adapter weights are runtime inputs to that one graph
  - Arabic tokenizer/tagger/NER adapter packs are selected dynamically at inference
  - Trankit tokenizer/tagger/NER/lemma/MWT Python modules are dynamically INT8-quantized
    where PyTorch supports it
  - Trankit's normal output reconstruction still runs unchanged

This is intentionally production-shaped: a future multi-language runtime would
keep one compressed XLM-R engine loaded, keep compressed adapter/task packs in a
registry, and switch the active packs per language/task.
"""

from __future__ import annotations

import argparse
import difflib
import gc
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Tuple


ROOT = Path(__file__).resolve().parent
DEPS_DIR = ROOT / "sandbox_adapter_bank_deps"
OUT_DIR = ROOT / ".trankit_arabic_one_xlmr_dynamic_adapters_onnx"
DEFAULT_ARABIC_SAMPLE = (
    "اللغة العربية لغة سامية يتحدث بها ملايين الناس في الشرق الأوسط وشمال أفريقيا. "
    "وتستعمل في الصحافة والتعليم والأدب والبحث العلمي، كما تحتفظ بمكانة ثقافية "
    "ودينية واسعة في أنحاء كثيرة من العالم. وتتميز العربية بنظام صرفي غني "
    "وبقدرة كبيرة على الاشتقاق والتعبير الدقيق عن المعاني."
)


def _force_utf8() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def _set_sandbox_env() -> None:
    os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")


def _prepend_deps() -> None:
    if DEPS_DIR.exists():
        text = str(DEPS_DIR)
        if text not in sys.path:
            sys.path.insert(0, text)


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    try:
        import torch

        if isinstance(value, torch.Tensor):
            return value.detach().cpu().tolist()
        if isinstance(value, torch.Size):
            return list(value)
    except Exception:
        pass
    return str(value)


def _load_arabic_pipeline() -> Any:
    from trankit import Pipeline  # type: ignore

    return Pipeline(lang="arabic", gpu=False)


def _adapter_tasks_for_pipeline(pipeline: Any) -> List[str]:
    tasks = ["tokenizer", "tagger"]
    if "arabic" in getattr(pipeline, "_ner_model", {}):
        tasks.append("ner")
    return tasks


def _first_module(module: Any, class_name: str) -> Any:
    for child in module.modules():
        if child.__class__.__name__ == class_name:
            return child
    raise RuntimeError(f"Could not find child module class {class_name}")


def _find_adapter_modules(xlmr: Any, adapter_name: str = "embedding") -> List[Tuple[str, Any]]:
    rows: List[Tuple[str, Any]] = []
    for name, module in xlmr.named_modules():
        if module.__class__.__name__ != "Adapter":
            continue
        if f".{adapter_name}" not in name and not name.endswith(f".{adapter_name}"):
            continue
        if not hasattr(module, "adapter_down") or not hasattr(module, "adapter_up"):
            continue
        rows.append((name, module))
    return rows


def _extract_adapter_pack(torch: Any, pipeline: Any, original_load_adapter: Any, task: str) -> Dict[str, Any]:
    original_load_adapter(task)
    adapters = _find_adapter_modules(pipeline._embedding_layers.xlmr, "embedding")
    if not adapters:
        raise RuntimeError(f"No embedding adapters found for task {task}")

    down_weight = []
    down_bias = []
    up_weight = []
    up_bias = []
    layer_norm_paths = []
    residual_before_ln = []
    for path, adapter in adapters:
        if getattr(adapter, "add_layer_norm_before", False) or getattr(adapter, "add_layer_norm_after", False):
            layer_norm_paths.append(path)
        residual_before_ln.append(bool(getattr(adapter, "residual_before_ln", True)))
        down = _first_module(adapter.adapter_down, "Linear")
        up = adapter.adapter_up
        down_weight.append(down.weight.detach().cpu().float())
        down_bias.append(down.bias.detach().cpu().float())
        up_weight.append(up.weight.detach().cpu().float())
        up_bias.append(up.bias.detach().cpu().float())

    if layer_norm_paths:
        raise RuntimeError(f"Adapter layer norm is not implemented in this prototype: {layer_norm_paths[:3]}")
    if len(set(residual_before_ln)) != 1:
        raise RuntimeError(f"Mixed adapter residual modes are not implemented: {residual_before_ln}")

    fp32 = {
        "down_weight": torch.stack(down_weight).numpy(),
        "down_bias": torch.stack(down_bias).numpy(),
        "up_weight": torch.stack(up_weight).numpy(),
        "up_bias": torch.stack(up_bias).numpy(),
    }
    compressed = {name: _compress_symmetric_int8(array) for name, array in fp32.items()}
    return {
        "task": task,
        "adapter_count": len(adapters),
        "adapter_paths": [path for path, _ in adapters],
        "residual_before_ln": residual_before_ln[0],
        "fp32": fp32,
        "compressed": compressed,
        "compressed_bytes": int(sum(item["values"].nbytes + item["scale"].nbytes for item in compressed.values())),
        "fp32_bytes": int(sum(array.nbytes for array in fp32.values())),
    }


def _compress_symmetric_int8(array: Any) -> Dict[str, Any]:
    import numpy as np

    values = np.asarray(array, dtype=np.float32)
    max_abs = float(np.max(np.abs(values))) if values.size else 0.0
    scale = np.array(max(max_abs / 127.0, 1.0e-8), dtype=np.float32)
    quantized = np.clip(np.round(values / scale), -127, 127).astype(np.int8)
    return {"values": quantized, "scale": scale}


def _decompress_symmetric_int8(item: Dict[str, Any]) -> Any:
    import numpy as np

    return np.asarray(item["values"], dtype=np.float32) * np.asarray(item["scale"], dtype=np.float32)


class _AdapterContext:
    down_weight: Any = None
    down_bias: Any = None
    up_weight: Any = None
    up_bias: Any = None
    residual_before_ln: bool = False


def _patch_adapters_for_dynamic_inputs(torch: Any, xlmr: Any, residual_before_ln: bool) -> Dict[str, Any]:
    functional = torch.nn.functional
    adapters = _find_adapter_modules(xlmr, "embedding")
    if not adapters:
        raise RuntimeError("No embedding adapters found while patching XLM-R")
    ctx = _AdapterContext()
    ctx.residual_before_ln = residual_before_ln

    def make_forward(layer_index: int) -> Any:
        def forward(x: Any, residual_input: Any):
            down = functional.linear(x, ctx.down_weight[layer_index], ctx.down_bias[layer_index])
            down = functional.relu(down)
            up = functional.linear(down, ctx.up_weight[layer_index], ctx.up_bias[layer_index])
            output = up
            if ctx.residual_before_ln:
                output = output + residual_input
            if not ctx.residual_before_ln:
                output = output + residual_input
            return output, down, up

        return forward

    for index, (_, adapter) in enumerate(adapters):
        adapter.forward = make_forward(index)
    return {
        "context": ctx,
        "adapter_count": len(adapters),
        "adapter_paths": [path for path, _ in adapters],
    }


def _build_dynamic_xlmr_wrapper(torch: Any, xlmr: Any, ctx: _AdapterContext) -> Any:
    nn = torch.nn

    class DynamicAdapterXLMR(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.xlmr = xlmr

        def forward(
            self,
            input_ids: Any,
            attention_mask: Any,
            adapter_down_weight: Any,
            adapter_down_bias: Any,
            adapter_up_weight: Any,
            adapter_up_bias: Any,
        ) -> Any:
            ctx.down_weight = adapter_down_weight
            ctx.down_bias = adapter_down_bias
            ctx.up_weight = adapter_up_weight
            ctx.up_bias = adapter_up_bias
            outputs = self.xlmr(input_ids=input_ids, attention_mask=attention_mask)
            return outputs[0]

    wrapper = DynamicAdapterXLMR()
    wrapper.eval()
    return wrapper


def _torch_onnx_export(torch: Any, wrapper: Any, args: Tuple[Any, ...], path: Path) -> None:
    kwargs = {
        "input_names": [
            "input_ids",
            "attention_mask",
            "adapter_down_weight",
            "adapter_down_bias",
            "adapter_up_weight",
            "adapter_up_bias",
        ],
        "output_names": ["last_hidden_state"],
        "dynamic_axes": {
            "input_ids": {0: "batch_size", 1: "sequence_length"},
            "attention_mask": {0: "batch_size", 1: "sequence_length"},
            "last_hidden_state": {0: "batch_size", 1: "sequence_length"},
        },
        "opset_version": 17,
        "do_constant_folding": True,
    }
    try:
        torch.onnx.export(wrapper, args, str(path), dynamo=False, **kwargs)
    except TypeError:
        torch.onnx.export(wrapper, args, str(path), **kwargs)


def _save_optimized_onnx(onnxruntime: Any, source: Path, target: Path) -> None:
    options = onnxruntime.SessionOptions()
    options.graph_optimization_level = onnxruntime.GraphOptimizationLevel.ORT_ENABLE_EXTENDED
    options.optimized_model_filepath = str(target)
    onnxruntime.InferenceSession(str(source), sess_options=options, providers=["CPUExecutionProvider"])
    if not target.exists() or target.stat().st_size <= 0:
        raise RuntimeError(f"ONNX Runtime did not write optimized graph: {target}")


def _quantize_dynamic_onnx(source: Path, target: Path) -> None:
    import onnx  # type: ignore
    from onnxruntime.quantization import QuantType, quantize_dynamic  # type: ignore

    quantize_dynamic(
        str(source),
        str(target),
        weight_type=QuantType.QInt8,
        per_channel=True,
        extra_options={"DefaultTensorType": onnx.TensorProto.FLOAT},
    )
    if not target.exists() or target.stat().st_size <= 0:
        raise RuntimeError(f"ONNX dynamic quantization did not write graph: {target}")


def _make_export_inputs(torch: Any, pack: Dict[str, Any], sequence_length: int) -> Tuple[Any, ...]:
    import numpy as np

    vocab_size = 250002
    torch.manual_seed(7)
    input_ids = torch.randint(4, vocab_size - 1, (1, sequence_length), dtype=torch.long)
    input_ids[0, 0] = 0
    input_ids[0, -1] = 2
    attention_mask = torch.ones_like(input_ids)
    return (
        input_ids,
        attention_mask,
        torch.from_numpy(np.asarray(pack["fp32"]["down_weight"], dtype=np.float32)),
        torch.from_numpy(np.asarray(pack["fp32"]["down_bias"], dtype=np.float32)),
        torch.from_numpy(np.asarray(pack["fp32"]["up_weight"], dtype=np.float32)),
        torch.from_numpy(np.asarray(pack["fp32"]["up_bias"], dtype=np.float32)),
    )


def _run_ort(session: Any, inputs: Tuple[Any, ...], compressed_pack: Dict[str, Any] | None = None) -> Any:
    import numpy as np

    if compressed_pack is None:
        down_weight = inputs[2].detach().cpu().numpy().astype(np.float32)
        down_bias = inputs[3].detach().cpu().numpy().astype(np.float32)
        up_weight = inputs[4].detach().cpu().numpy().astype(np.float32)
        up_bias = inputs[5].detach().cpu().numpy().astype(np.float32)
    else:
        down_weight = _decompress_symmetric_int8(compressed_pack["down_weight"])
        down_bias = _decompress_symmetric_int8(compressed_pack["down_bias"])
        up_weight = _decompress_symmetric_int8(compressed_pack["up_weight"])
        up_bias = _decompress_symmetric_int8(compressed_pack["up_bias"])
    feed = {
        "input_ids": inputs[0].detach().cpu().numpy().astype(np.int64),
        "attention_mask": inputs[1].detach().cpu().numpy().astype(np.int64),
        "adapter_down_weight": down_weight,
        "adapter_down_bias": down_bias,
        "adapter_up_weight": up_weight,
        "adapter_up_bias": up_bias,
    }
    return session.run(None, feed)[0]


def _compare_arrays(torch: Any, expected: Any, actual: Any) -> Dict[str, Any]:
    import numpy as np

    left = expected.detach().cpu().numpy().astype(np.float32)
    right = np.asarray(actual, dtype=np.float32)
    diff = np.abs(left - right)
    return {
        "max_abs_error": float(diff.max()) if diff.size else 0.0,
        "mean_abs_error": float(diff.mean()) if diff.size else 0.0,
        "shape": list(right.shape),
    }


def _quantize_supported_pytorch_modules(torch: Any, pipeline: Any) -> Dict[str, Any]:
    nn = torch.nn
    try:
        quantize_dynamic = torch.ao.quantization.quantize_dynamic
    except Exception:
        quantize_dynamic = torch.quantization.quantize_dynamic

    target_types = {nn.Linear, nn.LSTM, nn.GRU}
    try:
        target_types.add(nn.LSTMCell)
    except Exception:
        pass

    containers: List[Tuple[str, Any]] = []
    for attr in ["_tokenizer", "_tagger", "_ner_model", "_lemma_model", "_mwt_model"]:
        value = getattr(pipeline, attr, None)
        if isinstance(value, dict):
            for key, module in value.items():
                found_name, found_module = _unwrap_torch_module(f"{attr}.{key}", module)
                if found_module is not None:
                    containers.append((found_name, found_module))
        elif hasattr(value, "modules"):
            containers.append((attr, value))
        else:
            found_name, found_module = _unwrap_torch_module(attr, value)
            if found_module is not None:
                containers.append((found_name, found_module))

    before = {_name: _count_float_modules(torch, module) for _name, module in containers}
    quantized = []
    errors = []
    for name, module in containers:
        try:
            quantize_dynamic(module, target_types, dtype=torch.qint8, inplace=True)
            quantized.append(name)
        except Exception as exc:
            errors.append({"module": name, "error": repr(exc)})
    after = {_name: _count_float_modules(torch, module) for _name, module in containers}
    return {
        "attempted": [name for name, _ in containers],
        "quantized": quantized,
        "errors": errors,
        "float_modules_before": before,
        "float_modules_after": after,
    }


def _unwrap_torch_module(name: str, value: Any) -> Tuple[str, Any]:
    current = value
    current_name = name
    for _ in range(4):
        if hasattr(current, "modules"):
            return current_name, current
        if not hasattr(current, "model"):
            break
        current = current.model
        current_name = f"{current_name}.model"
    return name, None


def _count_float_modules(torch: Any, module: Any) -> Dict[str, int]:
    nn = torch.nn
    counts = {"Linear": 0, "LSTM": 0, "GRU": 0, "LSTMCell": 0}
    for child in module.modules():
        if isinstance(child, nn.Linear):
            counts["Linear"] += 1
        elif isinstance(child, nn.LSTM):
            counts["LSTM"] += 1
        elif isinstance(child, nn.GRU):
            counts["GRU"] += 1
        elif isinstance(child, nn.LSTMCell):
            counts["LSTMCell"] += 1
    return counts


class _ORTXLMRShim:
    pass


def _install_ort_xlmr_runtime(torch: Any, pipeline: Any, int8_path: Path, packs: Dict[str, Any]) -> Dict[str, Any]:
    import numpy as np
    import onnxruntime as ort  # type: ignore

    nn = torch.nn

    class ORTXLMRShim(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.session = ort.InferenceSession(str(int8_path), providers=["CPUExecutionProvider"])
            self.active_task = None
            self.config = getattr(pipeline._embedding_layers.xlmr, "config", None)

        def forward(self, input_ids: Any = None, attention_mask: Any = None, **_: Any) -> Tuple[Any]:
            if self.active_task not in packs:
                raise RuntimeError(f"No active compressed adapter pack selected: {self.active_task}")
            pack = packs[self.active_task]["compressed"]
            feed = {
                "input_ids": input_ids.detach().cpu().numpy().astype(np.int64),
                "attention_mask": attention_mask.detach().cpu().numpy().astype(np.int64),
                "adapter_down_weight": _decompress_symmetric_int8(pack["down_weight"]),
                "adapter_down_bias": _decompress_symmetric_int8(pack["down_bias"]),
                "adapter_up_weight": _decompress_symmetric_int8(pack["up_weight"]),
                "adapter_up_bias": _decompress_symmetric_int8(pack["up_bias"]),
            }
            output = self.session.run(None, feed)[0]
            tensor = torch.from_numpy(output).to(device=input_ids.device, dtype=torch.float32)
            return (tensor,)

    shim = ORTXLMRShim()

    def select_task(model_name: str) -> None:
        if model_name not in packs:
            raise RuntimeError(f"No compressed adapter pack for task {model_name}")
        shim.active_task = model_name

    pipeline._embedding_layers.xlmr = shim
    pipeline._load_adapter_weights = select_task
    return {
        "onnx_session": str(int8_path),
        "tasks": sorted(packs.keys()),
        "runtime": "one dynamic-adapter XLM-R ONNX Runtime INT8 graph",
    }


def _extract_tokens(doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    sentences = doc.get("sentences") if isinstance(doc, dict) else None
    if isinstance(sentences, list):
        for sentence in sentences:
            for token in sentence.get("tokens", []):
                if "expanded" in token and isinstance(token["expanded"], list):
                    for word in token["expanded"]:
                        rows.append(_token_row(word))
                else:
                    rows.append(_token_row(token))
    elif isinstance(doc.get("tokens"), list):
        rows = [_token_row(token) for token in doc["tokens"]]
    return rows


def _token_row(token: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "text": token.get("text"),
        "upos": token.get("upos"),
        "xpos": token.get("xpos"),
        "feats": token.get("feats"),
        "lemma": token.get("lemma"),
        "head": token.get("head"),
        "deprel": token.get("deprel"),
        "ner": token.get("ner"),
    }


def _compare_docs(baseline: Dict[str, Any], optimized: Dict[str, Any]) -> Dict[str, Any]:
    base = _extract_tokens(baseline)
    opt = _extract_tokens(optimized)
    base_texts = [str(row.get("text")) for row in base]
    opt_texts = [str(row.get("text")) for row in opt]
    ratio = difflib.SequenceMatcher(a=base_texts, b=opt_texts).ratio()
    aligned = len(base) == len(opt) and base_texts == opt_texts
    field_rates: Dict[str, Any] = {}
    if aligned:
        for field in ["upos", "xpos", "feats", "lemma", "head", "deprel", "ner"]:
            comparable = [(left.get(field), right.get(field)) for left, right in zip(base, opt)]
            comparable = [(left, right) for left, right in comparable if left is not None or right is not None]
            if comparable:
                field_rates[field] = sum(1 for left, right in comparable if left == right) / len(comparable)
    return {
        "baseline_token_count": len(base),
        "optimized_token_count": len(opt),
        "same_token_count": len(base) == len(opt),
        "token_text_exact": aligned,
        "token_sequence_ratio": ratio,
        "field_match_rates_when_aligned": field_rates,
        "not_obviously_busted": len(opt) >= 20 and ratio >= 0.85,
        "preview": [
            {"i": index + 1, "baseline": left, "optimized": right}
            for index, (left, right) in enumerate(zip(base, opt))
            if left != right
        ][:20],
    }


def run(sample_text: str, sequence_length: int) -> Dict[str, Any]:
    _set_sandbox_env()
    _prepend_deps()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    import numpy as np
    import onnxruntime as ort  # type: ignore
    import torch

    torch.set_num_interop_threads(1)

    total_start = time.perf_counter()
    baseline_load_start = time.perf_counter()
    baseline_pipeline = _load_arabic_pipeline()
    baseline_pipeline._embedding_layers.eval()
    baseline_pipeline._embedding_layers.xlmr.eval()
    baseline_load_seconds = time.perf_counter() - baseline_load_start

    baseline_start = time.perf_counter()
    with torch.inference_mode():
        baseline_doc = baseline_pipeline(sample_text)
    baseline_inference_seconds = time.perf_counter() - baseline_start
    del baseline_pipeline
    gc.collect()

    opt_load_start = time.perf_counter()
    pipeline = _load_arabic_pipeline()
    pipeline._embedding_layers.eval()
    pipeline._embedding_layers.xlmr.eval()
    if hasattr(pipeline._embedding_layers.xlmr, "config"):
        pipeline._embedding_layers.xlmr.config.output_hidden_states = False
    original_load_adapter = pipeline._load_adapter_weights
    tasks = _adapter_tasks_for_pipeline(pipeline)
    packs = {
        task: _extract_adapter_pack(torch, pipeline, original_load_adapter, task)
        for task in tasks
    }
    residual_modes = {pack["residual_before_ln"] for pack in packs.values()}
    if len(residual_modes) != 1:
        raise RuntimeError(f"Mixed residual modes across tasks are not implemented: {residual_modes}")
    patch_report = _patch_adapters_for_dynamic_inputs(
        torch,
        pipeline._embedding_layers.xlmr,
        residual_before_ln=next(iter(residual_modes)),
    )
    wrapper = _build_dynamic_xlmr_wrapper(torch, pipeline._embedding_layers.xlmr, patch_report["context"])
    export_inputs = _make_export_inputs(torch, packs["tokenizer"], sequence_length)
    opt_load_seconds = time.perf_counter() - opt_load_start

    export_start = time.perf_counter()
    fp32_path = OUT_DIR / "arabic_one_xlmr_dynamic_adapters_fp32.onnx"
    optimized_path = OUT_DIR / "arabic_one_xlmr_dynamic_adapters_optimized.onnx"
    int8_path = OUT_DIR / "arabic_one_xlmr_dynamic_adapters_dynamic_int8.onnx"
    _torch_onnx_export(torch, wrapper, export_inputs, fp32_path)
    export_seconds = time.perf_counter() - export_start

    optimize_start = time.perf_counter()
    _save_optimized_onnx(ort, fp32_path, optimized_path)
    optimize_seconds = time.perf_counter() - optimize_start

    quantize_start = time.perf_counter()
    _quantize_dynamic_onnx(optimized_path, int8_path)
    quantize_seconds = time.perf_counter() - quantize_start

    validate_start = time.perf_counter()
    with torch.inference_mode():
        torch_expected = wrapper(*export_inputs)
    fp32_session = ort.InferenceSession(str(optimized_path), providers=["CPUExecutionProvider"])
    int8_session = ort.InferenceSession(str(int8_path), providers=["CPUExecutionProvider"])
    fp32_output = _run_ort(fp32_session, export_inputs)
    int8_output = _run_ort(int8_session, export_inputs, compressed_pack=packs["tokenizer"]["compressed"])
    fp32_compare = _compare_arrays(torch, torch_expected, fp32_output)
    int8_compare = _compare_arrays(torch, torch_expected, int8_output)
    validate_seconds = time.perf_counter() - validate_start

    pytorch_quant_report = _quantize_supported_pytorch_modules(torch, pipeline)
    runtime_report = _install_ort_xlmr_runtime(torch, pipeline, int8_path, packs)

    optimized_start = time.perf_counter()
    with torch.inference_mode():
        optimized_doc = pipeline(sample_text)
    optimized_inference_seconds = time.perf_counter() - optimized_start

    comparison = _compare_docs(baseline_doc, optimized_doc)
    artifact_sizes = {
        "fp32_bytes": fp32_path.stat().st_size,
        "optimized_bytes": optimized_path.stat().st_size,
        "dynamic_int8_bytes": int8_path.stat().st_size,
    }
    adapter_sizes = {
        task: {
            "fp32_bytes": pack["fp32_bytes"],
            "compressed_bytes": pack["compressed_bytes"],
            "adapter_count": pack["adapter_count"],
        }
        for task, pack in packs.items()
    }

    return {
        "ok": bool(comparison["not_obviously_busted"]),
        "architecture": {
            "shared_xlmr_graph": "one ONNX Runtime graph",
            "xlmr_base": "static ONNX initializers with ONNX Runtime dynamic INT8 quantization",
            "adapters": "runtime inputs selected from compressed Arabic tokenizer/tagger/NER adapter packs",
            "task_heads_and_seq2seq": "PyTorch dynamic INT8 where supported",
            "production_shape": "one compressed XLM-R engine + dynamically selected compressed language/task packs",
        },
        "sample_chars": len(sample_text),
        "sequence_length_used_for_export": sequence_length,
        "elapsed_seconds": time.perf_counter() - total_start,
        "baseline_load_seconds": baseline_load_seconds,
        "baseline_inference_seconds": baseline_inference_seconds,
        "optimized_load_seconds": opt_load_seconds,
        "onnx_export_seconds": export_seconds,
        "onnx_graph_optimization_seconds": optimize_seconds,
        "onnx_dynamic_int8_seconds": quantize_seconds,
        "onnx_validation_seconds": validate_seconds,
        "optimized_inference_seconds": optimized_inference_seconds,
        "artifact_sizes": artifact_sizes,
        "adapter_pack_sizes": adapter_sizes,
        "adapter_patch": {
            "adapter_count": patch_report["adapter_count"],
            "adapter_paths": patch_report["adapter_paths"],
        },
        "onnx_validation": {
            "optimized_fp32_vs_torch": fp32_compare,
            "dynamic_int8_vs_torch": int8_compare,
        },
        "pytorch_quantization": pytorch_quant_report,
        "runtime": runtime_report,
        "comparison": comparison,
        "artifact_dir": str(OUT_DIR),
    }


def main() -> int:
    _force_utf8()
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", default=DEFAULT_ARABIC_SAMPLE)
    parser.add_argument("--sequence-length", type=int, default=128)
    args = parser.parse_args()
    report = run(args.text, args.sequence_length)
    print(json.dumps(report, ensure_ascii=False, indent=2, default=_json_default))
    return 0 if report.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
