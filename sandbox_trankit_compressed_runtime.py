"""
Sandbox compressed Trankit runtime helpers.

This module is intentionally standalone. It does not edit production files or
installed Trankit files.

Runtime shape:
  - one shared XLM-R ONNX Runtime dynamic-INT8 graph
  - adapter weights are runtime INT8 inputs to that graph
  - per-language/task adapter packs are loaded from sandbox artifacts
  - Trankit heads / MWT / lemmatizer are dynamically INT8-quantized in PyTorch
"""

from __future__ import annotations

import gc
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


ROOT = Path(__file__).resolve().parent
DEPS_DIR = ROOT / "sandbox_adapter_bank_deps"
ARTIFACT_DIR = ROOT / ".trankit_compressed_runtime"
PACK_DIR = ARTIFACT_DIR / "adapter_packs"
MANIFEST_PATH = ARTIFACT_DIR / "manifest.json"
FP32_ONNX_PATH = ARTIFACT_DIR / "xlmr_dynamic_adapters_fp32.onnx"
OPTIMIZED_ONNX_PATH = ARTIFACT_DIR / "xlmr_dynamic_adapters_optimized.onnx"
INT8_ONNX_PATH = ARTIFACT_DIR / "xlmr_dynamic_adapters_dynamic_int8.onnx"
ORT_SESSION_TUNING_PATH = ARTIFACT_DIR / "ort_session_tuning.json"
PROFILE_NAME = "one_xlmr_dynamic_adapter_int8"
EXPORT_OPSET = 17


def force_utf8() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def set_sandbox_env() -> None:
    os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")


def prepend_deps() -> List[str]:
    active: List[str] = []
    if DEPS_DIR.exists():
        text = str(DEPS_DIR)
        if text not in sys.path:
            sys.path.insert(0, text)
        active.append(text)
    return active


def safe_name(value: Any) -> str:
    text = str(value or "artifact")
    out = []
    for char in text:
        if char.isalnum() or char in {"-", "_"}:
            out.append(char)
        else:
            out.append("_")
    return "".join(out).strip("_") or "artifact"


def first_module(module: Any, class_name: str) -> Any:
    for child in module.modules():
        if child.__class__.__name__ == class_name:
            return child
    raise RuntimeError(f"Could not find child module class {class_name}")


def find_adapter_modules(xlmr: Any, adapter_name: str = "embedding") -> List[Tuple[str, Any]]:
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


def adapter_tasks_for_pipeline(pipeline: Any, lang: str) -> List[str]:
    tasks = []
    if lang in (getattr(pipeline, "_tokenizer", {}) or {}):
        tasks.append("tokenizer")
    if lang in (getattr(pipeline, "_tagger", {}) or {}):
        tasks.append("tagger")
    if lang in (getattr(pipeline, "_ner_model", {}) or {}):
        tasks.append("ner")
    return tasks


def iter_pipeline_tasks(pipeline: Any) -> List[Tuple[str, str]]:
    langs = [str(lang) for lang in (getattr(pipeline, "added_langs", []) or [])]
    tasks: List[Tuple[str, str]] = []
    for lang in langs:
        for task in adapter_tasks_for_pipeline(pipeline, lang):
            tasks.append((lang, task))
    return tasks


def compress_symmetric_int8(array: Any) -> Dict[str, Any]:
    import numpy as np

    values = np.asarray(array, dtype=np.float32)
    max_abs = float(np.max(np.abs(values))) if values.size else 0.0
    scale = np.array(max(max_abs / 127.0, 1.0e-8), dtype=np.float32)
    quantized = np.clip(np.round(values / scale), -127, 127).astype(np.int8)
    return {"values": quantized, "scale": scale}


def extract_adapter_pack(torch: Any, pipeline: Any, original_load_adapter: Any, lang: str, task: str) -> Dict[str, Any]:
    previous_lang = str(getattr(pipeline._config, "active_lang", ""))
    pipeline.set_active(lang)
    original_load_adapter(task)
    adapters = find_adapter_modules(pipeline._embedding_layers.xlmr, "embedding")
    if not adapters:
        raise RuntimeError(f"No embedding adapters found for {lang}:{task}")

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
        down = first_module(adapter.adapter_down, "Linear")
        up = adapter.adapter_up
        down_weight.append(down.weight.detach().cpu().float().numpy())
        down_bias.append(down.bias.detach().cpu().float().numpy())
        up_weight.append(up.weight.detach().cpu().float().numpy())
        up_bias.append(up.bias.detach().cpu().float().numpy())

    if previous_lang:
        try:
            pipeline.set_active(previous_lang)
        except Exception:
            pass
    if layer_norm_paths:
        raise RuntimeError(f"Adapter layer norm is not implemented: {layer_norm_paths[:3]}")
    if len(set(residual_before_ln)) != 1:
        raise RuntimeError(f"Mixed adapter residual modes are not implemented: {residual_before_ln}")

    import numpy as np

    fp32 = {
        "down_weight": np.stack(down_weight).astype(np.float32),
        "down_bias": np.stack(down_bias).astype(np.float32),
        "up_weight": np.stack(up_weight).astype(np.float32),
        "up_bias": np.stack(up_bias).astype(np.float32),
    }
    compressed = {name: compress_symmetric_int8(array) for name, array in fp32.items()}
    return {
        "lang": lang,
        "task": task,
        "adapter_count": len(adapters),
        "adapter_paths": [path for path, _ in adapters],
        "residual_before_ln": residual_before_ln[0],
        "signature": {
            "adapter_count": len(adapters),
            "down_weight_shape": list(fp32["down_weight"].shape),
            "down_bias_shape": list(fp32["down_bias"].shape),
            "up_weight_shape": list(fp32["up_weight"].shape),
            "up_bias_shape": list(fp32["up_bias"].shape),
            "residual_before_ln": residual_before_ln[0],
        },
        "compressed": compressed,
        "fp32_bytes": int(sum(array.nbytes for array in fp32.values())),
        "compressed_bytes": int(sum(item["values"].nbytes + item["scale"].nbytes for item in compressed.values())),
    }


def save_adapter_pack(pack: Dict[str, Any], path: Path) -> Dict[str, Any]:
    import numpy as np

    compressed = pack["compressed"]
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        path,
        lang=np.array(str(pack["lang"])),
        task=np.array(str(pack["task"])),
        residual_before_ln=np.array(bool(pack["residual_before_ln"])),
        adapter_paths=np.array(pack["adapter_paths"]),
        down_weight_q=compressed["down_weight"]["values"],
        down_weight_scale=compressed["down_weight"]["scale"],
        down_bias_q=compressed["down_bias"]["values"],
        down_bias_scale=compressed["down_bias"]["scale"],
        up_weight_q=compressed["up_weight"]["values"],
        up_weight_scale=compressed["up_weight"]["scale"],
        up_bias_q=compressed["up_bias"]["values"],
        up_bias_scale=compressed["up_bias"]["scale"],
    )
    return {
        "lang": pack["lang"],
        "task": pack["task"],
        "path": str(path.relative_to(ARTIFACT_DIR)),
        "adapter_count": pack["adapter_count"],
        "adapter_paths": pack["adapter_paths"],
        "signature": pack["signature"],
        "fp32_bytes": pack["fp32_bytes"],
        "compressed_bytes": pack["compressed_bytes"],
        "file_bytes": path.stat().st_size,
    }


def load_adapter_pack(path: Path) -> Dict[str, Any]:
    import numpy as np

    data = np.load(path, allow_pickle=False)
    return {
        "lang": str(data["lang"].item()),
        "task": str(data["task"].item()),
        "residual_before_ln": bool(data["residual_before_ln"].item()),
        "adapter_paths": [str(item) for item in data["adapter_paths"].tolist()],
        "down_weight_q": data["down_weight_q"],
        "down_weight_scale": data["down_weight_scale"],
        "down_bias_q": data["down_bias_q"],
        "down_bias_scale": data["down_bias_scale"],
        "up_weight_q": data["up_weight_q"],
        "up_weight_scale": data["up_weight_scale"],
        "up_bias_q": data["up_bias_q"],
        "up_bias_scale": data["up_bias_scale"],
    }


class AdapterContext:
    down_weight_q: Any = None
    down_weight_scale: Any = None
    down_bias_q: Any = None
    down_bias_scale: Any = None
    up_weight_q: Any = None
    up_weight_scale: Any = None
    up_bias_q: Any = None
    up_bias_scale: Any = None
    residual_before_ln: bool = False


def patch_adapters_for_dynamic_int8_inputs(torch: Any, xlmr: Any, residual_before_ln: bool) -> Dict[str, Any]:
    functional = torch.nn.functional
    adapters = find_adapter_modules(xlmr, "embedding")
    if not adapters:
        raise RuntimeError("No embedding adapters found while patching XLM-R")
    ctx = AdapterContext()
    ctx.residual_before_ln = residual_before_ln

    def make_forward(layer_index: int) -> Any:
        def forward(x: Any, residual_input: Any):
            down_weight = ctx.down_weight_q[layer_index].to(torch.float32) * ctx.down_weight_scale
            down_bias = ctx.down_bias_q[layer_index].to(torch.float32) * ctx.down_bias_scale
            up_weight = ctx.up_weight_q[layer_index].to(torch.float32) * ctx.up_weight_scale
            up_bias = ctx.up_bias_q[layer_index].to(torch.float32) * ctx.up_bias_scale
            down = functional.linear(x, down_weight, down_bias)
            down = functional.relu(down)
            up = functional.linear(down, up_weight, up_bias)
            output = up + residual_input
            return output, down, up

        return forward

    for index, (_, adapter) in enumerate(adapters):
        adapter.forward = make_forward(index)
    return {
        "context": ctx,
        "adapter_count": len(adapters),
        "adapter_paths": [path for path, _ in adapters],
    }


def build_dynamic_xlmr_wrapper(torch: Any, xlmr: Any, ctx: AdapterContext) -> Any:
    nn = torch.nn

    class DynamicAdapterXLMR(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.xlmr = xlmr

        def forward(
            self,
            input_ids: Any,
            attention_mask: Any,
            adapter_down_weight_q: Any,
            adapter_down_weight_scale: Any,
            adapter_down_bias_q: Any,
            adapter_down_bias_scale: Any,
            adapter_up_weight_q: Any,
            adapter_up_weight_scale: Any,
            adapter_up_bias_q: Any,
            adapter_up_bias_scale: Any,
        ) -> Any:
            ctx.down_weight_q = adapter_down_weight_q
            ctx.down_weight_scale = adapter_down_weight_scale
            ctx.down_bias_q = adapter_down_bias_q
            ctx.down_bias_scale = adapter_down_bias_scale
            ctx.up_weight_q = adapter_up_weight_q
            ctx.up_weight_scale = adapter_up_weight_scale
            ctx.up_bias_q = adapter_up_bias_q
            ctx.up_bias_scale = adapter_up_bias_scale
            outputs = self.xlmr(input_ids=input_ids, attention_mask=attention_mask)
            return outputs[0]

    wrapper = DynamicAdapterXLMR()
    wrapper.eval()
    return wrapper


def make_export_inputs(torch: Any, pack: Dict[str, Any], sequence_length: int) -> Tuple[Any, ...]:
    import numpy as np

    compressed = pack["compressed"]
    torch.manual_seed(7)
    input_ids = torch.randint(4, 250001, (1, sequence_length), dtype=torch.long)
    input_ids[0, 0] = 0
    input_ids[0, -1] = 2
    attention_mask = torch.ones_like(input_ids)
    return (
        input_ids,
        attention_mask,
        torch.from_numpy(np.asarray(compressed["down_weight"]["values"], dtype=np.int8)),
        torch.from_numpy(np.asarray(compressed["down_weight"]["scale"], dtype=np.float32)),
        torch.from_numpy(np.asarray(compressed["down_bias"]["values"], dtype=np.int8)),
        torch.from_numpy(np.asarray(compressed["down_bias"]["scale"], dtype=np.float32)),
        torch.from_numpy(np.asarray(compressed["up_weight"]["values"], dtype=np.int8)),
        torch.from_numpy(np.asarray(compressed["up_weight"]["scale"], dtype=np.float32)),
        torch.from_numpy(np.asarray(compressed["up_bias"]["values"], dtype=np.int8)),
        torch.from_numpy(np.asarray(compressed["up_bias"]["scale"], dtype=np.float32)),
    )


def torch_onnx_export(torch: Any, wrapper: Any, args: Tuple[Any, ...], path: Path) -> None:
    kwargs = {
        "input_names": [
            "input_ids",
            "attention_mask",
            "adapter_down_weight_q",
            "adapter_down_weight_scale",
            "adapter_down_bias_q",
            "adapter_down_bias_scale",
            "adapter_up_weight_q",
            "adapter_up_weight_scale",
            "adapter_up_bias_q",
            "adapter_up_bias_scale",
        ],
        "output_names": ["last_hidden_state"],
        "dynamic_axes": {
            "input_ids": {0: "batch_size", 1: "sequence_length"},
            "attention_mask": {0: "batch_size", 1: "sequence_length"},
            "last_hidden_state": {0: "batch_size", 1: "sequence_length"},
        },
        "opset_version": EXPORT_OPSET,
        "do_constant_folding": True,
    }
    try:
        torch.onnx.export(wrapper, args, str(path), dynamo=False, **kwargs)
    except TypeError:
        torch.onnx.export(wrapper, args, str(path), **kwargs)


def save_optimized_onnx(ort: Any, source: Path, target: Path) -> None:
    options = ort.SessionOptions()
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_EXTENDED
    options.optimized_model_filepath = str(target)
    ort.InferenceSession(str(source), sess_options=options, providers=["CPUExecutionProvider"])
    if not target.exists() or target.stat().st_size <= 0:
        raise RuntimeError(f"ONNX Runtime did not write optimized graph: {target}")


def quantize_dynamic_onnx(source: Path, target: Path) -> None:
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


def quantize_supported_pytorch_modules(torch: Any, pipeline: Any) -> Dict[str, Any]:
    nn = torch.nn
    try:
        quantize_dynamic = torch.ao.quantization.quantize_dynamic
    except Exception:
        quantize_dynamic = torch.quantization.quantize_dynamic

    target_types = {nn.Linear, nn.LSTM, nn.GRU}
    if hasattr(nn, "LSTMCell"):
        target_types.add(nn.LSTMCell)

    containers: List[Tuple[str, Any]] = []
    for attr in ["_tokenizer", "_tagger", "_ner_model", "_lemma_model", "_mwt_model"]:
        value = getattr(pipeline, attr, None)
        if isinstance(value, dict):
            for key, module in value.items():
                found_name, found_module = unwrap_torch_module(f"{attr}.{key}", module)
                if found_module is not None:
                    containers.append((found_name, found_module))
        else:
            found_name, found_module = unwrap_torch_module(attr, value)
            if found_module is not None:
                containers.append((found_name, found_module))

    before = {name: count_float_modules(torch, module) for name, module in containers}
    quantized = []
    errors = []
    for name, module in containers:
        try:
            quantize_dynamic(module, target_types, dtype=torch.qint8, inplace=True)
            quantized.append(name)
        except Exception as exc:
            errors.append({"module": name, "error": repr(exc)})
    after = {name: count_float_modules(torch, module) for name, module in containers}
    return {
        "attempted": [name for name, _ in containers],
        "quantized": quantized,
        "errors": errors,
        "float_modules_before": before,
        "float_modules_after": after,
    }


def unwrap_torch_module(name: str, value: Any) -> Tuple[str, Optional[Any]]:
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


def count_float_modules(torch: Any, module: Any) -> Dict[str, int]:
    nn = torch.nn
    counts = {"Linear": 0, "LSTM": 0, "GRU": 0, "LSTMCell": 0}
    for child in module.modules():
        if isinstance(child, nn.Linear):
            counts["Linear"] += 1
        elif isinstance(child, nn.LSTM):
            counts["LSTM"] += 1
        elif isinstance(child, nn.GRU):
            counts["GRU"] += 1
        elif hasattr(nn, "LSTMCell") and isinstance(child, nn.LSTMCell):
            counts["LSTMCell"] += 1
    return counts


def build_artifacts(pipeline: Any, torch: Any, sequence_length: int = 128) -> Dict[str, Any]:
    set_sandbox_env()
    prepend_deps()
    import onnxruntime as ort  # type: ignore

    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    PACK_DIR.mkdir(parents=True, exist_ok=True)

    started = time.perf_counter()
    original_load_adapter = pipeline._load_adapter_weights
    tasks = iter_pipeline_tasks(pipeline)
    if not tasks:
        raise RuntimeError("No Trankit language/task adapters found to build")

    packs: Dict[Tuple[str, str], Dict[str, Any]] = {}
    pack_manifest = []
    errors = []
    for lang, task in tasks:
        try:
            pack = extract_adapter_pack(torch, pipeline, original_load_adapter, lang, task)
            key = (lang, task)
            packs[key] = pack
            pack_path = PACK_DIR / f"{safe_name(lang)}__{safe_name(task)}.npz"
            pack_manifest.append(save_adapter_pack(pack, pack_path))
            print(f"built adapter pack {lang}:{task} -> {pack_path}", flush=True)
        except Exception as exc:
            errors.append({"lang": lang, "task": task, "error": str(exc)})

    if errors:
        raise RuntimeError(f"Adapter pack build failed: {errors[:5]}")

    signatures = {json.dumps(pack["signature"], sort_keys=True) for pack in packs.values()}
    if len(signatures) != 1:
        raise RuntimeError(f"Adapter signatures are not uniform; cannot use one XLM-R graph: {len(signatures)} signatures")

    first_pack = next(iter(packs.values()))
    patch = patch_adapters_for_dynamic_int8_inputs(
        torch,
        pipeline._embedding_layers.xlmr,
        residual_before_ln=bool(first_pack["residual_before_ln"]),
    )
    wrapper = build_dynamic_xlmr_wrapper(torch, pipeline._embedding_layers.xlmr, patch["context"])
    export_inputs = make_export_inputs(torch, first_pack, sequence_length)

    export_started = time.perf_counter()
    torch_onnx_export(torch, wrapper, export_inputs, FP32_ONNX_PATH)
    export_seconds = time.perf_counter() - export_started

    optimize_started = time.perf_counter()
    save_optimized_onnx(ort, FP32_ONNX_PATH, OPTIMIZED_ONNX_PATH)
    optimize_seconds = time.perf_counter() - optimize_started

    quantize_started = time.perf_counter()
    quantize_dynamic_onnx(OPTIMIZED_ONNX_PATH, INT8_ONNX_PATH)
    quantize_seconds = time.perf_counter() - quantize_started

    manifest = {
        "ok": True,
        "profile": PROFILE_NAME,
        "built_at": time.time(),
        "sequence_length_used_for_export": sequence_length,
        "task_count": len(pack_manifest),
        "languages": sorted({lang for lang, _ in tasks}),
        "onnx": {
            "fp32_path": str(FP32_ONNX_PATH.relative_to(ARTIFACT_DIR)),
            "optimized_path": str(OPTIMIZED_ONNX_PATH.relative_to(ARTIFACT_DIR)),
            "dynamic_int8_path": str(INT8_ONNX_PATH.relative_to(ARTIFACT_DIR)),
            "fp32_bytes": FP32_ONNX_PATH.stat().st_size,
            "optimized_bytes": OPTIMIZED_ONNX_PATH.stat().st_size,
            "dynamic_int8_bytes": INT8_ONNX_PATH.stat().st_size,
        },
        "adapter_signature": first_pack["signature"],
        "adapter_packs": pack_manifest,
        "timing": {
            "elapsed_seconds": time.perf_counter() - started,
            "onnx_export_seconds": export_seconds,
            "onnx_graph_optimization_seconds": optimize_seconds,
            "onnx_dynamic_int8_seconds": quantize_seconds,
        },
    }
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    return manifest


def load_manifest(path: Path = MANIFEST_PATH) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _resolve_artifact_path(manifest_path: Path, value: str) -> Path:
    base = manifest_path.parent
    normalized = str(value).replace("\\", "/")
    path = Path(normalized)
    if path.is_absolute():
        return path
    return base / path


def load_ort_session_tuning(session_path: Path, tuning_path: Path = ORT_SESSION_TUNING_PATH) -> Tuple[Optional[Dict[str, Any]], Dict[str, Any]]:
    report: Dict[str, Any] = {
        "path": str(tuning_path),
        "loaded": False,
        "applied": False,
    }
    if not tuning_path.exists():
        report["reason"] = "missing"
        return None, report
    try:
        with open(tuning_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        report["loaded"] = True
        report["created_at"] = payload.get("created_at")
        report["profile_name"] = payload.get("profile_name")
        if payload.get("profile_name") != PROFILE_NAME:
            report["reason"] = f"profile mismatch: {payload.get('profile_name')} != {PROFILE_NAME}"
            return None, report

        artifact = payload.get("artifact") if isinstance(payload.get("artifact"), dict) else {}
        expected_bytes = artifact.get("bytes")
        if isinstance(expected_bytes, int) and session_path.exists() and int(session_path.stat().st_size) != expected_bytes:
            report["reason"] = "ONNX artifact size changed"
            report["expected_artifact_bytes"] = expected_bytes
            report["actual_artifact_bytes"] = int(session_path.stat().st_size)
            return None, report

        best = payload.get("best") if isinstance(payload.get("best"), dict) else {}
        profile = best.get("profile") if isinstance(best.get("profile"), dict) else None
        if not isinstance(profile, dict):
            report["reason"] = "missing best.profile"
            return None, report

        report["applied"] = True
        report["profile"] = profile
        report["baseline"] = payload.get("baseline")
        report["best"] = best
        report["savings_vs_default"] = payload.get("savings_vs_default")
        return profile, report
    except Exception as exc:
        report["error"] = str(exc)
        return None, report


def make_ort_session_options(ort: Any, profile: Optional[Dict[str, Any]]) -> Optional[Any]:
    if not isinstance(profile, dict):
        return None
    options = ort.SessionOptions()
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    if profile.get("intra_op_num_threads") is not None:
        options.intra_op_num_threads = int(profile["intra_op_num_threads"])
    if profile.get("inter_op_num_threads") is not None:
        options.inter_op_num_threads = int(profile["inter_op_num_threads"])
    execution_mode = str(profile.get("execution_mode") or "sequential")
    if execution_mode == "parallel":
        options.execution_mode = ort.ExecutionMode.ORT_PARALLEL
    elif execution_mode == "sequential":
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    if profile.get("enable_cpu_mem_arena") is not None:
        options.enable_cpu_mem_arena = bool(profile["enable_cpu_mem_arena"])
    if profile.get("enable_mem_pattern") is not None:
        options.enable_mem_pattern = bool(profile["enable_mem_pattern"])
    return options


def create_tuned_ort_session(ort: Any, session_path: Path) -> Tuple[Any, Dict[str, Any]]:
    profile, tuning_report = load_ort_session_tuning(session_path)
    options = make_ort_session_options(ort, profile)
    if options is None:
        session = ort.InferenceSession(str(session_path), providers=["CPUExecutionProvider"])
    else:
        session = ort.InferenceSession(str(session_path), sess_options=options, providers=["CPUExecutionProvider"])
    return session, tuning_report


def install_compressed_runtime(pipeline: Any, torch: Any, manifest_path: Path = MANIFEST_PATH) -> Dict[str, Any]:
    prepend_deps()
    import numpy as np
    import onnxruntime as ort  # type: ignore

    started = time.perf_counter()
    manifest = load_manifest(manifest_path)
    if manifest.get("ok") is not True:
        raise RuntimeError(f"Compressed runtime manifest is not ok: {manifest_path}")
    if manifest.get("profile") != PROFILE_NAME:
        raise RuntimeError(f"Compressed runtime profile mismatch: {manifest.get('profile')} != {PROFILE_NAME}")

    onnx_rel = str((manifest.get("onnx") or {}).get("dynamic_int8_path") or "")
    if not onnx_rel:
        raise RuntimeError("Compressed runtime manifest has no dynamic INT8 ONNX path")
    session_path = _resolve_artifact_path(manifest_path, onnx_rel)
    if not session_path.exists():
        raise RuntimeError(f"Compressed XLM-R ONNX file is missing: {session_path}")

    packs: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for item in manifest.get("adapter_packs", []):
        lang = str(item.get("lang") or "")
        task = str(item.get("task") or "")
        rel_path = str(item.get("path") or "")
        if not lang or not task or not rel_path:
            continue
        packs[(lang, task)] = load_adapter_pack(_resolve_artifact_path(manifest_path, rel_path))

    expected_tasks = iter_pipeline_tasks(pipeline)
    missing = [f"{lang}:{task}" for lang, task in expected_tasks if (lang, task) not in packs]
    if missing:
        raise RuntimeError(f"Compressed adapter pack coverage incomplete: missing {missing[:10]}")

    class ORTXLMRShim(torch.nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.session, self.ort_tuning_report = create_tuned_ort_session(ort, session_path)
            self.active_key: Optional[Tuple[str, str]] = None
            self.config = getattr(pipeline._embedding_layers.xlmr, "config", None)
            self.run_count = 0
            self.last_key = ""
            self.total_seconds = 0.0
            self.preprocess_seconds = 0.0
            self.session_seconds = 0.0
            self.postprocess_seconds = 0.0
            self.by_key: Dict[str, Dict[str, Any]] = {}

        def _add_timing(
            self,
            key_label: str,
            total_seconds: float,
            preprocess_seconds: float,
            session_seconds: float,
            postprocess_seconds: float,
        ) -> None:
            self.run_count += 1
            self.total_seconds += total_seconds
            self.preprocess_seconds += preprocess_seconds
            self.session_seconds += session_seconds
            self.postprocess_seconds += postprocess_seconds
            row = self.by_key.setdefault(
                key_label,
                {
                    "count": 0,
                    "total_seconds": 0.0,
                    "preprocess_seconds": 0.0,
                    "session_seconds": 0.0,
                    "postprocess_seconds": 0.0,
                },
            )
            row["count"] = int(row.get("count") or 0) + 1
            row["total_seconds"] = float(row.get("total_seconds") or 0.0) + total_seconds
            row["preprocess_seconds"] = float(row.get("preprocess_seconds") or 0.0) + preprocess_seconds
            row["session_seconds"] = float(row.get("session_seconds") or 0.0) + session_seconds
            row["postprocess_seconds"] = float(row.get("postprocess_seconds") or 0.0) + postprocess_seconds

        def forward(self, input_ids: Any = None, attention_mask: Any = None, **_: Any) -> Tuple[Any]:
            if self.active_key not in packs:
                raise RuntimeError(f"No active compressed adapter pack selected: {self.active_key}")
            key_label = f"{self.active_key[0]}:{self.active_key[1]}"
            pack = packs[self.active_key]
            started = time.perf_counter()
            preprocess_started = time.perf_counter()
            feed = {
                "input_ids": input_ids.detach().cpu().numpy().astype(np.int64, copy=False),
                "attention_mask": attention_mask.detach().cpu().numpy().astype(np.int64, copy=False),
                "adapter_down_weight_q": pack["down_weight_q"],
                "adapter_down_weight_scale": pack["down_weight_scale"],
                "adapter_down_bias_q": pack["down_bias_q"],
                "adapter_down_bias_scale": pack["down_bias_scale"],
                "adapter_up_weight_q": pack["up_weight_q"],
                "adapter_up_weight_scale": pack["up_weight_scale"],
                "adapter_up_bias_q": pack["up_bias_q"],
                "adapter_up_bias_scale": pack["up_bias_scale"],
            }
            preprocess_seconds = time.perf_counter() - preprocess_started
            session_started = time.perf_counter()
            output = self.session.run(None, feed)[0]
            session_seconds = time.perf_counter() - session_started
            postprocess_started = time.perf_counter()
            result = torch.from_numpy(output).to(device=input_ids.device, dtype=torch.float32)
            postprocess_seconds = time.perf_counter() - postprocess_started
            total_seconds = time.perf_counter() - started
            self.last_key = key_label
            self._add_timing(
                key_label,
                total_seconds,
                preprocess_seconds,
                session_seconds,
                postprocess_seconds,
            )
            return (result,)

        def metrics(self) -> Dict[str, Any]:
            return {
                "run_count": self.run_count,
                "total_seconds": self.total_seconds,
                "preprocess_seconds": self.preprocess_seconds,
                "session_seconds": self.session_seconds,
                "postprocess_seconds": self.postprocess_seconds,
                "by_key": {key: dict(value) for key, value in self.by_key.items()},
                "last_session_key": self.last_key,
                "loaded_pack_count": len(packs),
                "onnx_session": str(session_path),
                "ort_tuning": dict(self.ort_tuning_report),
            }

    original_xlmr_config = getattr(pipeline._embedding_layers.xlmr, "config", None)
    shim = ORTXLMRShim()
    shim.config = original_xlmr_config
    original_load_adapter = pipeline._load_adapter_weights

    def select_adapter_pack(model_name: str) -> None:
        lang = str(getattr(pipeline._config, "active_lang", ""))
        key = (lang, str(model_name))
        if key not in packs:
            raise RuntimeError(f"No compressed adapter pack for {key[0]}:{key[1]}")
        shim.active_key = key
        return None

    pipeline._embedding_layers.xlmr = shim
    pipeline._load_adapter_weights = select_adapter_pack
    pipeline._compressed_xlmr_runtime = shim
    pipeline._compressed_original_load_adapter = original_load_adapter
    released_original_xlmr = gc.collect()
    quant_report = quantize_supported_pytorch_modules(torch, pipeline)
    return {
        "installed": True,
        "profile": PROFILE_NAME,
        "manifest_path": str(manifest_path),
        "onnx_session": str(session_path),
        "language_count": len(set(lang for lang, _ in packs)),
        "adapter_pack_count": len(packs),
        "task_count": len(expected_tasks),
        "missing_count": 0,
        "artifact_sizes": manifest.get("onnx"),
        "adapter_signature": manifest.get("adapter_signature"),
        "ort_tuning": shim.ort_tuning_report,
        "pytorch_quantization": quant_report,
        "released_original_xlmr_gc_objects": released_original_xlmr,
        "elapsed_seconds": time.perf_counter() - started,
    }
