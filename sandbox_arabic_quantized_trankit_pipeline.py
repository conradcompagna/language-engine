"""
Arabic-only production-shaped quantized Trankit prototype.

This is a sandbox script. It does not edit production runtime files or Trankit
site-packages.

Architecture tested here:
  - one Arabic Trankit pipeline
  - one shared XLM-R module
  - XLM-R base nn.Linear modules dynamically INT8-quantized in PyTorch
  - Arabic tokenizer/tagger/NER adapter weights exported as static ONNX adapter
    packs and dynamically INT8-quantized
  - Trankit's normal _load_adapter_weights task switch is replaced by selecting
    the relevant static adapter pack
  - task heads, lemmatizer/MWT, dependency decoding, and output reconstruction
    stay unchanged

This is intentionally the same high-level inference shape that could be used
for all languages later:
  shared quantized XLM-R base + static quantized adapter packs per language/task.
"""

from __future__ import annotations

import argparse
import difflib
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple


ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / ".trankit_arabic_quantized_pipeline"
ADAPTER_BANK_DIR = ROOT / ".trankit_adapter_bank_proto"
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


def _set_cpu_env() -> None:
    os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")


def _json_default(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    return str(value)


def _load_arabic_pipeline() -> Any:
    from trankit import Pipeline  # type: ignore

    return Pipeline(lang="arabic", gpu=False)


def _adapter_tasks_for_pipeline(pipeline: Any) -> List[str]:
    tasks = ["tokenizer", "tagger"]
    if "arabic" in getattr(pipeline, "_ner_model", {}):
        tasks.append("ner")
    return tasks


def _replace_child_module(root: Any, module_name: str, replacement: Any) -> None:
    parent = root
    parts = module_name.split(".")
    for part in parts[:-1]:
        parent = getattr(parent, part)
    setattr(parent, parts[-1], replacement)


def _dynamic_quantize_xlmr_base_linears(torch: Any, xlmr: Any) -> Dict[str, Any]:
    nn = torch.nn
    try:
        from torch.ao.nn.quantized.dynamic import Linear as QuantizedDynamicLinear
        from torch.ao.quantization import default_dynamic_qconfig
    except Exception:
        from torch.nn.quantized.dynamic import Linear as QuantizedDynamicLinear  # type: ignore
        from torch.quantization import default_dynamic_qconfig  # type: ignore

    quantized: List[str] = []
    skipped_adapters: List[str] = []
    for name, module in list(xlmr.named_modules()):
        if not isinstance(module, nn.Linear):
            continue
        lowered = name.lower()
        if "adapter" in lowered:
            skipped_adapters.append(name)
            continue
        module.eval()
        module.qconfig = default_dynamic_qconfig
        qmodule = QuantizedDynamicLinear.from_float(module)
        _replace_child_module(xlmr, name, qmodule)
        quantized.append(name)
    return {
        "quantized_count": len(quantized),
        "quantized_modules": quantized,
        "skipped_adapter_count": len(skipped_adapters),
        "skipped_adapter_modules": skipped_adapters,
    }


def _build_adapter_packs(torch: Any, pipeline: Any, original_load_adapter: Any) -> Dict[str, Any]:
    from sandbox_trankit_adapter_bank_prototype import (
        _adapter_signature,
        _find_adapter_modules,
        _safe_artifact_name,
        _same_signature,
        _try_export_onnx,
        build_adapter_bank,
    )

    packs: Dict[str, Any] = {}
    xlmr = pipeline._embedding_layers.xlmr
    adapter_config = xlmr.config.adapters.get("embedding")
    fallback_activation = str(adapter_config["non_linearity"] if adapter_config else "relu")

    for task in _adapter_tasks_for_pipeline(pipeline):
        original_load_adapter(task)
        adapters = _find_adapter_modules(xlmr, "embedding")
        if not adapters:
            raise RuntimeError(f"No adapter modules found after loading task {task}")
        signatures = [_adapter_signature(adapter, fallback_activation) for _, adapter in adapters]
        base_signature = signatures[0]
        bad = [
            path
            for (path, _), sig in zip(adapters, signatures)
            if not _same_signature(base_signature, sig)
        ]
        if bad:
            raise RuntimeError(f"Task {task} has incompatible adapter signatures: {bad[:3]}")
        bank = build_adapter_bank(torch, adapters, base_signature)
        artifact_stem = _safe_artifact_name(f"arabic_{task}_adapter_bank")
        onnx_report = _try_export_onnx(torch, bank, adapters, artifact_stem)
        if not onnx_report.get("ok"):
            raise RuntimeError(f"Adapter ONNX export failed for {task}: {onnx_report}")
        packs[task] = {
            "task": task,
            "adapter_count": len(adapters),
            "adapter_paths": [path for path, _ in adapters],
            "signature": base_signature,
            "onnx": onnx_report,
        }
    return packs


def _install_quantized_adapter_runtime(torch: Any, pipeline: Any, packs: Dict[str, Any]) -> Dict[str, Any]:
    from sandbox_trankit_adapter_bank_prototype import _find_adapter_modules, _prepend_proto_deps

    _prepend_proto_deps()
    import numpy as np
    import onnxruntime as ort  # type: ignore

    sessions: Dict[str, Any] = {}
    for task, pack in packs.items():
        int8_path = pack["onnx"].get("int8_path")
        fp32_path = pack["onnx"].get("fp32_path")
        session_path = int8_path or fp32_path
        if not session_path:
            raise RuntimeError(f"No ONNX session path for adapter task {task}")
        sessions[task] = ort.InferenceSession(str(session_path), providers=["CPUExecutionProvider"])

    adapters = _find_adapter_modules(pipeline._embedding_layers.xlmr, "embedding")
    path_to_index = {path: idx for idx, (path, _) in enumerate(adapters)}
    active_task = {"value": None}
    original_load_adapter = pipeline._load_adapter_weights

    def select_adapter_pack(model_name: str) -> None:
        if model_name not in sessions:
            raise RuntimeError(f"No quantized adapter pack for task {model_name}")
        active_task["value"] = model_name
        return None

    def make_forward(path: str) -> Any:
        adapter_index = path_to_index[path]

        def forward(x: Any, residual_input: Any):
            task = active_task["value"]
            if task not in sessions:
                raise RuntimeError(f"Adapter task is not selected before forward: {task}")
            ort_inputs = {
                "x": x.detach().cpu().float().numpy().astype(np.float32),
                "residual_input": residual_input.detach().cpu().float().numpy().astype(np.float32),
                "adapter_id": np.array(adapter_index, dtype=np.int64),
            }
            output = sessions[task].run(None, ort_inputs)[0]
            output_tensor = torch.from_numpy(output).to(device=x.device, dtype=x.dtype)
            return output_tensor, None, None

        return forward

    for path, adapter in adapters:
        adapter.forward = make_forward(path)

    pipeline._load_adapter_weights = select_adapter_pack
    return {
        "session_tasks": sorted(sessions.keys()),
        "patched_adapter_count": len(adapters),
        "original_load_adapter_preserved": bool(original_load_adapter),
    }


def _extract_tokens(doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    sentences = doc.get("sentences") if isinstance(doc, dict) else None
    if isinstance(sentences, list):
        for sentence in sentences:
            sent_id = sentence.get("id")
            for token in sentence.get("tokens", []) if isinstance(sentence, dict) else []:
                if isinstance(token, dict):
                    row = dict(token)
                    row["_sentence_id"] = sent_id
                    rows.append(row)
    tokens = doc.get("tokens") if isinstance(doc, dict) else None
    if isinstance(tokens, list):
        for token in tokens:
            if isinstance(token, dict):
                rows.append(dict(token))
    return rows


def _token_text(token: Dict[str, Any]) -> str:
    return str(token.get("text") or token.get("token") or token.get("word") or "")


def _field_match_rate(left: List[Dict[str, Any]], right: List[Dict[str, Any]], field: str) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    total = 0
    matched = 0
    for a, b in zip(left, right):
        av = a.get(field)
        bv = b.get(field)
        if av is None and bv is None:
            continue
        total += 1
        if av == bv:
            matched += 1
    return matched / total if total else 1.0


def _compare_docs(baseline: Dict[str, Any], optimized: Dict[str, Any]) -> Dict[str, Any]:
    base_tokens = _extract_tokens(baseline)
    opt_tokens = _extract_tokens(optimized)
    base_texts = [_token_text(token) for token in base_tokens]
    opt_texts = [_token_text(token) for token in opt_tokens]
    token_ratio = difflib.SequenceMatcher(a=base_texts, b=opt_texts).ratio()
    same_length = len(base_tokens) == len(opt_tokens)
    aligned = same_length and base_texts == opt_texts
    fields = ["upos", "xpos", "feats", "lemma", "head", "deprel", "ner"]
    field_rates = {
        field: _field_match_rate(base_tokens, opt_tokens, field)
        for field in fields
        if any(field in token for token in base_tokens + opt_tokens)
    }
    preview = []
    for idx, (a, b) in enumerate(zip(base_tokens, opt_tokens)):
        if idx >= 20:
            break
        preview.append({
            "i": idx + 1,
            "baseline": {
                "text": _token_text(a),
                "upos": a.get("upos"),
                "lemma": a.get("lemma"),
                "head": a.get("head"),
                "deprel": a.get("deprel"),
                "ner": a.get("ner"),
            },
            "optimized": {
                "text": _token_text(b),
                "upos": b.get("upos"),
                "lemma": b.get("lemma"),
                "head": b.get("head"),
                "deprel": b.get("deprel"),
                "ner": b.get("ner"),
            },
        })
    return {
        "baseline_token_count": len(base_tokens),
        "optimized_token_count": len(opt_tokens),
        "same_token_count": same_length,
        "token_text_exact": aligned,
        "token_sequence_ratio": token_ratio,
        "field_match_rates_when_aligned": field_rates if aligned else {},
        "not_obviously_busted": bool(len(opt_tokens) >= 20 and token_ratio >= 0.85),
        "preview": preview,
    }


def run_quantized_arabic(sample_text: str) -> Dict[str, Any]:
    _set_cpu_env()
    import torch

    torch.set_grad_enabled(False)
    started = time.perf_counter()

    vanilla_started = time.perf_counter()
    vanilla = _load_arabic_pipeline()
    vanilla_load_seconds = time.perf_counter() - vanilla_started
    with torch.inference_mode():
        baseline_started = time.perf_counter()
        baseline_doc = vanilla(sample_text)
        baseline_seconds = time.perf_counter() - baseline_started
    del vanilla

    quant_started = time.perf_counter()
    quantized = _load_arabic_pipeline()
    quantized_load_seconds = time.perf_counter() - quant_started
    original_load_adapter = quantized._load_adapter_weights
    adapter_packs = _build_adapter_packs(torch, quantized, original_load_adapter)
    quant_report = _dynamic_quantize_xlmr_base_linears(torch, quantized._embedding_layers.xlmr)
    adapter_runtime_report = _install_quantized_adapter_runtime(torch, quantized, adapter_packs)
    quantized._embedding_layers.eval()
    quantized._embedding_layers.xlmr.eval()

    with torch.inference_mode():
        optimized_started = time.perf_counter()
        optimized_doc = quantized(sample_text)
        optimized_seconds = time.perf_counter() - optimized_started

    comparison = _compare_docs(baseline_doc, optimized_doc)
    return {
        "ok": bool(comparison["not_obviously_busted"]),
        "architecture": {
            "shared_xlmr_model": True,
            "xlmr_base_runtime": "PyTorch dynamic INT8 Linear modules",
            "adapter_runtime": "static Arabic ONNX Runtime dynamic INT8 adapter packs selected by Trankit task",
            "task_heads": "unchanged FP32 PyTorch",
            "lemma_mwt_dependency_output": "unchanged Trankit code",
            "production_shape": "shared quantized XLM-R base + per-language/task static quantized adapter packs",
        },
        "sample_chars": len(sample_text),
        "sample_text": sample_text,
        "elapsed_seconds": time.perf_counter() - started,
        "vanilla_load_seconds": vanilla_load_seconds,
        "baseline_inference_seconds": baseline_seconds,
        "quantized_load_seconds": quantized_load_seconds,
        "optimized_inference_seconds": optimized_seconds,
        "xlmr_quantization": quant_report,
        "adapter_packs": adapter_packs,
        "adapter_runtime": adapter_runtime_report,
        "comparison": comparison,
        "artifact_dirs": {
            "script_cache": str(OUT_DIR),
            "adapter_bank_onnx": str(ADAPTER_BANK_DIR),
        },
    }


def main() -> int:
    _force_utf8()
    parser = argparse.ArgumentParser(description="Arabic quantized Trankit production-shaped sandbox.")
    parser.add_argument("--text", default=DEFAULT_ARABIC_SAMPLE)
    args = parser.parse_args()
    try:
        report = run_quantized_arabic(args.text)
    except Exception as exc:
        report = {"ok": False, "error": str(exc)}
        print(json.dumps(report, indent=2, ensure_ascii=False, default=_json_default))
        return 1
    print(json.dumps(report, indent=2, ensure_ascii=False, default=_json_default))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
