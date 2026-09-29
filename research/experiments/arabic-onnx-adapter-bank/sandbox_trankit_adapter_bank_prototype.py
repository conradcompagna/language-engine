"""
Sandbox prototype for a Trankit adapter-bank runtime.

This does not modify production files or Trankit site-packages. It loads one
Trankit CPU pipeline in this standalone process, extracts the currently active
adapter weights, builds a compact vectorized adapter bank, validates adapter
math against Trankit's native Adapter modules, and optionally exports/checks a
small ONNX graph for that adapter bank.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / ".trankit_adapter_bank_proto"
PROTO_DEPS_DIRS = [
    ROOT / "sandbox_adapter_bank_deps",
]


def _set_cpu_only_env() -> None:
    os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")


def _json_default(value: Any) -> Any:
    try:
        import torch

        if isinstance(value, torch.Size):
            return list(value)
        if isinstance(value, torch.Tensor):
            return value.detach().cpu().tolist()
    except Exception:
        pass
    if isinstance(value, Path):
        return str(value)
    return str(value)


def _prepend_proto_deps() -> List[str]:
    active: List[str] = []
    for path in PROTO_DEPS_DIRS:
        if not path.exists():
            continue
        text = str(path)
        if text not in sys.path:
            sys.path.insert(0, text)
        active.append(text)
    return active


def _safe_artifact_name(value: Any) -> str:
    text = str(value or "artifact")
    chars = []
    for char in text:
        if char.isalnum() or char in {"-", "_"}:
            chars.append(char)
        else:
            chars.append("_")
    return "".join(chars).strip("_") or "artifact"


def _first_module(module: Any, class_name: str) -> Optional[Any]:
    for child in module.modules():
        if child.__class__.__name__ == class_name:
            return child
    return None


def _activation_name(adapter: Any, fallback: str = "relu") -> str:
    fn = getattr(getattr(adapter, "non_linearity", None), "f", None)
    name = str(getattr(fn, "__name__", "") or "").lower()
    if name in {"relu", "tanh", "leaky_relu", "swish", "gelu_new"}:
        return name
    return fallback.lower()


def _adapter_signature(adapter: Any, fallback_activation: str) -> Dict[str, Any]:
    down_linear = _first_module(adapter.adapter_down, "Linear")
    up_linear = adapter.adapter_up
    norm_before = getattr(adapter, "adapter_norm_before", None)
    norm_after = getattr(adapter, "adapter_norm_after", None)
    return {
        "input_size": int(adapter.input_size),
        "down_sample": int(adapter.down_sample),
        "activation": _activation_name(adapter, fallback_activation),
        "add_layer_norm_before": bool(getattr(adapter, "add_layer_norm_before", False)),
        "add_layer_norm_after": bool(getattr(adapter, "add_layer_norm_after", False)),
        "residual_before_ln": bool(getattr(adapter, "residual_before_ln", True)),
        "down_weight_shape": list(down_linear.weight.shape),
        "up_weight_shape": list(up_linear.weight.shape),
        "norm_before": norm_before is not None,
        "norm_after": norm_after is not None,
    }


def _same_signature(left: Dict[str, Any], right: Dict[str, Any]) -> bool:
    keys = [
        "input_size",
        "down_sample",
        "activation",
        "add_layer_norm_before",
        "add_layer_norm_after",
        "residual_before_ln",
        "down_weight_shape",
        "up_weight_shape",
        "norm_before",
        "norm_after",
    ]
    return all(left.get(key) == right.get(key) for key in keys)


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


class AdapterBankModule:  # real base class is filled in by build_adapter_bank()
    pass


def build_adapter_bank(torch: Any, adapters: List[Tuple[str, Any]], signature: Dict[str, Any]) -> Any:
    nn = torch.nn
    functional = torch.nn.functional

    class _AdapterBank(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.input_size = int(signature["input_size"])
            self.down_sample = int(signature["down_sample"])
            self.activation = str(signature["activation"])
            self.add_layer_norm_before = bool(signature["add_layer_norm_before"])
            self.add_layer_norm_after = bool(signature["add_layer_norm_after"])
            self.residual_before_ln = bool(signature["residual_before_ln"])
            self.register_buffer(
                "down_weight",
                torch.stack([
                    _first_module(adapter.adapter_down, "Linear").weight.detach().cpu().float()
                    for _, adapter in adapters
                ]),
            )
            self.register_buffer(
                "down_bias",
                torch.stack([
                    _first_module(adapter.adapter_down, "Linear").bias.detach().cpu().float()
                    for _, adapter in adapters
                ]),
            )
            self.register_buffer(
                "up_weight",
                torch.stack([
                    adapter.adapter_up.weight.detach().cpu().float()
                    for _, adapter in adapters
                ]),
            )
            self.register_buffer(
                "up_bias",
                torch.stack([
                    adapter.adapter_up.bias.detach().cpu().float()
                    for _, adapter in adapters
                ]),
            )
            if self.add_layer_norm_before:
                self.register_buffer(
                    "norm_before_weight",
                    torch.stack([
                        adapter.adapter_norm_before.weight.detach().cpu().float()
                        for _, adapter in adapters
                    ]),
                )
                self.register_buffer(
                    "norm_before_bias",
                    torch.stack([
                        adapter.adapter_norm_before.bias.detach().cpu().float()
                        for _, adapter in adapters
                    ]),
                )
            else:
                self.register_buffer("norm_before_weight", torch.empty(0))
                self.register_buffer("norm_before_bias", torch.empty(0))
            if self.add_layer_norm_after:
                self.register_buffer(
                    "norm_after_weight",
                    torch.stack([
                        adapter.adapter_norm_after.weight.detach().cpu().float()
                        for _, adapter in adapters
                    ]),
                )
                self.register_buffer(
                    "norm_after_bias",
                    torch.stack([
                        adapter.adapter_norm_after.bias.detach().cpu().float()
                        for _, adapter in adapters
                    ]),
                )
            else:
                self.register_buffer("norm_after_weight", torch.empty(0))
                self.register_buffer("norm_after_bias", torch.empty(0))

        def _activate(self, x: Any) -> Any:
            if self.activation == "relu":
                return functional.relu(x)
            if self.activation == "tanh":
                return torch.tanh(x)
            if self.activation == "swish":
                return x * torch.sigmoid(x)
            if self.activation == "gelu_new":
                return 0.5 * x * (
                    1.0
                    + torch.tanh(
                        torch.sqrt(torch.tensor(2.0 / 3.141592653589793, dtype=x.dtype, device=x.device))
                        * (x + 0.044715 * torch.pow(x, 3))
                    )
                )
            if self.activation == "leaky_relu":
                return functional.leaky_relu(x)
            raise RuntimeError(f"Unsupported adapter activation: {self.activation}")

        def forward(self, x: Any, residual_input: Any, adapter_id: Any) -> Any:
            idx = adapter_id.to(dtype=torch.long).reshape(())
            current = x
            if self.add_layer_norm_before:
                current = functional.layer_norm(
                    current,
                    (self.input_size,),
                    self.norm_before_weight[idx],
                    self.norm_before_bias[idx],
                    1e-5,
                )
            down = torch.matmul(current, self.down_weight[idx].transpose(0, 1)) + self.down_bias[idx]
            down = self._activate(down)
            up = torch.matmul(down, self.up_weight[idx].transpose(0, 1)) + self.up_bias[idx]
            output = up
            if self.residual_before_ln:
                output = output + residual_input
            if self.add_layer_norm_after:
                output = functional.layer_norm(
                    output,
                    (self.input_size,),
                    self.norm_after_weight[idx],
                    self.norm_after_bias[idx],
                    1e-5,
                )
            if not self.residual_before_ln:
                output = output + residual_input
            return output

    return _AdapterBank().eval()


def _validate_bank(torch: Any, bank: Any, adapters: List[Tuple[str, Any]], sample_count: int) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    torch.manual_seed(7)
    batch = 2
    tokens = 5
    hidden = int(bank.input_size)
    x = torch.randn(batch, tokens, hidden)
    residual = torch.randn(batch, tokens, hidden)
    limit = min(max(1, sample_count), len(adapters))
    indexes = sorted(set([0, len(adapters) // 2, len(adapters) - 1]))[:limit]
    if len(indexes) < limit:
        for idx in range(len(adapters)):
            if idx not in indexes:
                indexes.append(idx)
            if len(indexes) >= limit:
                break
    with torch.inference_mode():
        for idx in indexes:
            path, adapter = adapters[idx]
            adapter = adapter.cpu().float().eval()
            native = adapter(x, residual_input=residual)[0]
            cloned = bank(x, residual, torch.tensor(idx, dtype=torch.long))
            diff = (native - cloned).abs()
            results.append({
                "index": idx,
                "path": path,
                "max_abs_error": float(diff.max().item()),
                "mean_abs_error": float(diff.mean().item()),
                "passed": bool(float(diff.max().item()) <= 1e-5),
            })
    return results


def _try_export_onnx(
    torch: Any,
    bank: Any,
    adapters: List[Tuple[str, Any]],
    artifact_stem: str,
) -> Dict[str, Any]:
    report: Dict[str, Any] = {"attempted": True}
    report["deps_dirs"] = _prepend_proto_deps()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    safe_stem = _safe_artifact_name(artifact_stem)
    fp32_path = OUT_DIR / f"{safe_stem}_fp32.onnx"
    int8_path = OUT_DIR / f"{safe_stem}_dynamic_int8.onnx"
    x = torch.randn(2, 5, int(bank.input_size))
    residual = torch.randn(2, 5, int(bank.input_size))
    adapter_id = torch.tensor(0, dtype=torch.long)
    try:
        import onnx  # type: ignore  # noqa: F401

        torch.onnx.export(
            bank,
            (x, residual, adapter_id),
            str(fp32_path),
            input_names=["x", "residual_input", "adapter_id"],
            output_names=["output"],
            dynamic_axes={
                "x": {0: "batch", 1: "tokens"},
                "residual_input": {0: "batch", 1: "tokens"},
                "output": {0: "batch", 1: "tokens"},
            },
            opset_version=17,
            dynamo=False,
        )
        report["fp32_path"] = str(fp32_path)
        report["fp32_bytes"] = fp32_path.stat().st_size
    except Exception as exc:
        report["ok"] = False
        report["error"] = f"ONNX FP32 export failed: {exc}"
        return report

    try:
        from onnxruntime.quantization import QuantType, quantize_dynamic  # type: ignore

        quantize_dynamic(
            model_input=str(fp32_path),
            model_output=str(int8_path),
            weight_type=QuantType.QInt8,
            per_channel=True,
        )
        report["int8_path"] = str(int8_path)
        report["int8_bytes"] = int8_path.stat().st_size
    except Exception as exc:
        report["int8_error"] = f"ONNX dynamic INT8 quantization failed: {exc}"

    try:
        import numpy as np
        import onnxruntime as ort  # type: ignore

        expected = bank(x, residual, adapter_id).detach().cpu().numpy()
        ort_inputs = {
            "x": x.detach().cpu().numpy().astype(np.float32),
            "residual_input": residual.detach().cpu().numpy().astype(np.float32),
            "adapter_id": adapter_id.detach().cpu().numpy(),
        }

        def validate_ort(path: Path, prefix: str, tolerance: float) -> None:
            session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
            actual = session.run(None, ort_inputs)[0]
            diff = abs(expected - actual)
            report[f"{prefix}_onnxruntime_path"] = str(path)
            report[f"{prefix}_onnxruntime_max_abs_error"] = float(diff.max())
            report[f"{prefix}_onnxruntime_mean_abs_error"] = float(diff.mean())
            report[f"{prefix}_onnxruntime_runs"] = True
            report[f"{prefix}_onnxruntime_ok"] = bool(float(diff.max()) <= tolerance)
            report[f"{prefix}_onnxruntime_tolerance"] = tolerance

        validate_ort(fp32_path, "fp32", 1e-4)
        if int8_path.exists():
            validate_ort(int8_path, "int8", 5e-2)
    except Exception as exc:
        report["onnxruntime_error"] = f"ONNX Runtime validation failed: {exc}"

    report["ok"] = bool(
        report.get("fp32_onnxruntime_ok", False)
        and (not int8_path.exists() or report.get("int8_onnxruntime_runs", False))
    )
    return report


def _summarize_trankit_doc(doc: Any) -> Dict[str, Any]:
    if not isinstance(doc, dict):
        return {"type": type(doc).__name__}
    sentences = doc.get("sentences")
    tokens = doc.get("tokens")
    if isinstance(sentences, list):
        token_count = 0
        for sentence in sentences:
            if isinstance(sentence, dict) and isinstance(sentence.get("tokens"), list):
                token_count += len(sentence["tokens"])
        return {
            "shape": "document",
            "sentence_count": len(sentences),
            "token_count": token_count,
            "top_level_keys": sorted(str(key) for key in doc.keys()),
        }
    if isinstance(tokens, list):
        return {
            "shape": "sentence",
            "sentence_count": 1,
            "token_count": len(tokens),
            "top_level_keys": sorted(str(key) for key in doc.keys()),
        }
    return {"shape": "unknown", "top_level_keys": sorted(str(key) for key in doc.keys())}


def _run_sample_through_exported_adapter_bank(
    torch: Any,
    pipeline: Any,
    task: str,
    adapters: List[Tuple[str, Any]],
    onnx_report: Dict[str, Any],
    sample_text: str,
    max_captures: int = 12,
) -> Dict[str, Any]:
    report: Dict[str, Any] = {
        "attempted": bool(sample_text.strip()),
        "sample_text": sample_text,
        "task": task,
    }
    if not sample_text.strip():
        report["skipped"] = True
        report["reason"] = "empty sample text"
        return report
    fp32_path = onnx_report.get("fp32_path")
    int8_path = onnx_report.get("int8_path")
    if not fp32_path:
        report["ok"] = False
        report["error"] = "no exported FP32 ONNX path available"
        return report

    _prepend_proto_deps()
    import numpy as np
    import onnxruntime as ort  # type: ignore

    path_to_index = {path: idx for idx, (path, _) in enumerate(adapters)}
    originals: List[Tuple[Any, Any]] = []
    captures: List[Dict[str, Any]] = []
    active_task = {"value": None}
    original_load_adapter = pipeline._load_adapter_weights

    def patched_load_adapter(model_name: str) -> Any:
        result = original_load_adapter(model_name)
        active_task["value"] = model_name
        return result

    def make_forward(path: str, module: Any, original_forward: Any) -> Any:
        adapter_index = path_to_index[path]

        def wrapped_forward(x: Any, residual_input: Any):
            native = original_forward(x, residual_input=residual_input)
            if active_task["value"] == task and len(captures) < max_captures:
                captures.append({
                    "path": path,
                    "adapter_index": adapter_index,
                    "x": x.detach().cpu().float(),
                    "residual": residual_input.detach().cpu().float(),
                    "native_output": native[0].detach().cpu().float(),
                })
            return native

        return wrapped_forward

    try:
        pipeline._load_adapter_weights = patched_load_adapter
        for path, module in adapters:
            originals.append((module, module.forward))
            module.forward = make_forward(path, module, module.forward)
        with torch.inference_mode():
            doc = pipeline(sample_text)
    finally:
        pipeline._load_adapter_weights = original_load_adapter
        for module, original_forward in originals:
            module.forward = original_forward

    report["trankit_output_summary"] = _summarize_trankit_doc(doc)
    report["capture_count"] = len(captures)
    if not captures:
        report["ok"] = False
        report["error"] = f"no adapter calls captured for task {task}"
        return report

    fp32_session = ort.InferenceSession(str(fp32_path), providers=["CPUExecutionProvider"])
    int8_session = ort.InferenceSession(str(int8_path), providers=["CPUExecutionProvider"]) if int8_path else None

    rows: List[Dict[str, Any]] = []
    fp32_ok = True
    int8_runs = True
    int8_ok = True
    for capture in captures:
        ort_inputs = {
            "x": capture["x"].numpy().astype(np.float32),
            "residual_input": capture["residual"].numpy().astype(np.float32),
            "adapter_id": np.array(capture["adapter_index"], dtype=np.int64),
        }
        native = capture["native_output"].numpy()
        fp32_actual = fp32_session.run(None, ort_inputs)[0]
        fp32_diff = abs(native - fp32_actual)
        row = {
            "path": capture["path"],
            "adapter_index": capture["adapter_index"],
            "input_shape": list(capture["x"].shape),
            "fp32_max_abs_error": float(fp32_diff.max()),
            "fp32_mean_abs_error": float(fp32_diff.mean()),
            "fp32_ok": bool(float(fp32_diff.max()) <= 1e-4),
        }
        fp32_ok = fp32_ok and bool(row["fp32_ok"])
        if int8_session is not None:
            int8_actual = int8_session.run(None, ort_inputs)[0]
            int8_diff = abs(native - int8_actual)
            row["int8_max_abs_error"] = float(int8_diff.max())
            row["int8_mean_abs_error"] = float(int8_diff.mean())
            row["int8_ok"] = bool(float(int8_diff.max()) <= 5e-2)
            int8_ok = int8_ok and bool(row["int8_ok"])
        else:
            int8_runs = False
        rows.append(row)

    report["captures"] = rows
    report["fp32_ok"] = bool(fp32_ok)
    report["int8_runs"] = bool(int8_runs)
    report["int8_ok"] = bool(int8_ok) if int8_runs else None
    report["ok"] = bool(fp32_ok and (not int8_runs or int8_ok))
    return report


def _load_pipeline(
    lang_code: str,
    *,
    trankit_name_override: str = "",
    cache_dir_override: str = "",
) -> Tuple[Any, str, Dict[str, Any]]:
    if trankit_name_override:
        from trankit import Pipeline  # type: ignore

        info = {
            "trankit_name": trankit_name_override,
            "trankit_cache_dir": cache_dir_override,
            "direct_trankit_load": True,
        }
        if cache_dir_override:
            pipeline = Pipeline(lang=trankit_name_override, cache_dir=cache_dir_override, gpu=False)
        else:
            pipeline = Pipeline(lang=trankit_name_override, gpu=False)
        return pipeline, lang_code, info

    from trankit_dual_device_benchmark_app import _register_single_language_for_probe

    import language_registry as lr
    from trankit import Pipeline  # type: ignore

    resolved = lr.resolve_lang_code(lang_code) or lang_code
    if resolved not in lr.LANGUAGE_REGISTRY:
        raise ValueError(f"Unsupported language code: {lang_code}")
    info = _register_single_language_for_probe(lr, resolved)
    trankit_name = str(info["trankit_name"])
    cache_dir = info.get("trankit_cache_dir")
    if cache_dir:
        pipeline = Pipeline(lang=trankit_name, cache_dir=cache_dir, gpu=False)
    else:
        pipeline = Pipeline(lang=trankit_name, gpu=False)
    return pipeline, resolved, info


def run_probe(
    lang_code: str,
    task: str,
    samples: int,
    export_onnx: bool,
    sample_text: str,
    trankit_name_override: str = "",
    cache_dir_override: str = "",
) -> Dict[str, Any]:
    _set_cpu_only_env()
    started = time.perf_counter()
    import torch

    torch.set_grad_enabled(False)
    pipeline, resolved_lang, info = _load_pipeline(
        lang_code,
        trankit_name_override=trankit_name_override,
        cache_dir_override=cache_dir_override,
    )
    pipeline.set_active(str(info["trankit_name"]))
    if task == "ner" and resolved_lang not in getattr(pipeline, "_ner_model", {}):
        raise ValueError(f"NER model is not loaded for {resolved_lang}")
    pipeline._load_adapter_weights(task)
    embedding = pipeline._embedding_layers
    xlmr = embedding.xlmr
    xlmr.eval()
    adapter_config = xlmr.config.adapters.get("embedding")
    fallback_activation = str(adapter_config["non_linearity"] if adapter_config else "relu")
    adapters = _find_adapter_modules(xlmr, "embedding")
    if not adapters:
        raise RuntimeError("No active embedding adapter modules found in XLM-R.")

    signatures = [_adapter_signature(adapter, fallback_activation) for _, adapter in adapters]
    base_signature = signatures[0]
    incompatible = [
        {"path": path, "signature": sig}
        for (path, _), sig in zip(adapters, signatures)
        if not _same_signature(base_signature, sig)
    ]
    if incompatible:
        raise RuntimeError(f"Adapter modules do not share one bankable signature: {incompatible[:3]}")

    bank = build_adapter_bank(torch, adapters, base_signature)
    validation = _validate_bank(torch, bank, adapters, samples)
    adapter_bytes = sum(
        int(param.detach().numel() * param.detach().element_size())
        for _, adapter in adapters
        for param in adapter.parameters()
    )
    bank_bytes = sum(
        int(buffer.detach().numel() * buffer.detach().element_size())
        for buffer in bank.buffers()
    )
    artifact_stem = f"{resolved_lang}_{task}_adapter_bank"
    onnx_report = _try_export_onnx(torch, bank, adapters, artifact_stem) if export_onnx else {"attempted": False}
    sample_report = (
        _run_sample_through_exported_adapter_bank(
            torch,
            pipeline,
            task,
            adapters,
            onnx_report,
            sample_text,
        )
        if export_onnx
        else {"attempted": False, "skipped": True, "reason": "ONNX export disabled"}
    )
    ok = bool(
        validation
        and all(row["passed"] for row in validation)
        and (not export_onnx or onnx_report.get("ok"))
        and (not sample_report.get("attempted") or sample_report.get("ok"))
    )
    return {
        "ok": ok,
        "elapsed_seconds": time.perf_counter() - started,
        "lang_code": resolved_lang,
        "trankit_name": info["trankit_name"],
        "task": task,
        "active_adapters": getattr(xlmr, "active_adapters", None),
        "adapter_count": len(adapters),
        "adapter_paths": [path for path, _ in adapters],
        "signature": base_signature,
        "adapter_bytes": adapter_bytes,
        "adapter_bank_buffer_bytes": bank_bytes,
        "parity": validation,
        "onnx": onnx_report,
        "sample_inference": sample_report,
        "output_dir": str(OUT_DIR),
    }


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass
    parser = argparse.ArgumentParser(description="Sandbox Trankit adapter-bank prototype.")
    parser.add_argument("--lang", default="sa", help="Language registry code, default: sa")
    parser.add_argument("--trankit-name", default="", help="Direct Trankit language/model name override.")
    parser.add_argument("--cache-dir", default="", help="Direct Trankit cache_dir override.")
    parser.add_argument("--task", default="tagger", choices=["tokenizer", "tagger", "ner"])
    parser.add_argument("--samples", type=int, default=4)
    parser.add_argument(
        "--sample-text",
        default="هذا اختبار قصير. هذه جملة ثانية.",
        help="Real language sample used to validate the exported adapter-bank ONNX model.",
    )
    parser.add_argument("--no-onnx", action="store_true")
    args = parser.parse_args()

    try:
        report = run_probe(
            args.lang,
            args.task,
            args.samples,
            not args.no_onnx,
            args.sample_text,
            trankit_name_override=args.trankit_name,
            cache_dir_override=args.cache_dir,
        )
    except Exception as exc:
        report = {
            "ok": False,
            "error": str(exc),
        }
        print(json.dumps(report, indent=2, ensure_ascii=False, default=_json_default))
        return 1

    print(json.dumps(report, indent=2, ensure_ascii=False, default=_json_default))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
