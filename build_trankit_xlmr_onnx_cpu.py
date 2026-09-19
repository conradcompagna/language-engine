"""
Build precomputed ONNX Runtime dynamic-INT8 XLM-R adapter models for the
standalone Trankit benchmark app.

This script does not start Flask and does not serve requests. It only:

1. Loads the app's Trankit pipeline on CPU.
2. Exports each active XLM-R + adapter task path to ONNX FP32.
3. Runs ONNX Runtime transformer graph optimization.
4. Dynamic-INT8 quantizes the optimized graph.
5. Writes .trankit_onnx_cache/manifest_dynamic_int8.json.

Run when the machine is free:

  python build_trankit_xlmr_onnx_cpu.py
"""

from __future__ import annotations

import argparse
import gc
import json
import os
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Dict, Optional


ROOT = Path(__file__).resolve().parent
CPU_OPT_DEPS_DIR = ROOT / ".trankit_cpu_opt_deps"
ONNX_DEPS_DIRS = [
    Path(r"C:\tmp\trankit_onnx_deps_v2"),
    Path(r"C:\tmp\trankit_onnx_deps"),
    ROOT / ".trankit_onnx_deps",
    CPU_OPT_DEPS_DIR,
]
ONNX_CACHE_DIR = ROOT / ".trankit_onnx_cache"
ONNX_MANIFEST_PATH = ONNX_CACHE_DIR / "manifest_dynamic_int8.json"
ONNX_PROFILE_NAME = "onnxruntime_xlmr_dynamic_int8"
ONNX_EXPORT_OPSET = 17


def append_onnx_deps() -> Dict[str, Any]:
    report = {"active": False, "path": "", "candidates": [str(p) for p in ONNX_DEPS_DIRS]}
    skipped = []
    for path in ONNX_DEPS_DIRS:
        if path.exists():
            probe = path / "onnxruntime" / "__init__.py"
            try:
                with probe.open("rb") as f:
                    f.read(1)
            except Exception as exc:
                skipped.append(f"{path}: {exc}")
                continue
            path_text = str(path)
            if path_text not in sys.path:
                sys.path.append(path_text)
            report["active"] = True
            report["path"] = path_text
            report["skipped"] = skipped
            return report
    report["skipped"] = skipped
    return report


def safe_name(value: Any) -> str:
    out = []
    for ch in str(value):
        if ch.isalnum() or ch in {"-", "_"}:
            out.append(ch)
        else:
            out.append("_")
    return "".join(out).strip("_") or "unknown"


def paths_for_task(lang: str, task: str) -> Dict[str, Path]:
    base = f"{safe_name(lang)}__{safe_name(task)}__xlmr"
    return {
        "raw": ONNX_CACHE_DIR / f"{base}__raw.onnx",
        "optimized": ONNX_CACHE_DIR / f"{base}__ort_optimized.onnx",
        "int8": ONNX_CACHE_DIR / f"{base}__ort_dynamic_int8.onnx",
        "meta": ONNX_CACHE_DIR / f"{base}__meta.json",
    }


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, sort_keys=True)


def install_forced_cpu_pipeline() -> None:
    import trankit  # type: ignore

    original_init = trankit.Pipeline.__init__

    def patched_init(self: Any, *args: Any, **kwargs: Any):
        kwargs["gpu"] = False
        return original_init(self, *args, **kwargs)

    trankit.Pipeline.__init__ = patched_init


def disable_hidden_state_outputs(module: Any) -> Dict[str, Any]:
    changed = 0
    for obj in [module, getattr(module, "config", None)]:
        if obj is None:
            continue
        for attr in ("output_hidden_states", "output_attentions"):
            if hasattr(obj, attr) and getattr(obj, attr) is not False:
                try:
                    setattr(obj, attr, False)
                    changed += 1
                except Exception:
                    pass
    return {"changed_attrs": changed}


def install_xlmr_no_hidden_state_patch() -> Dict[str, Any]:
    try:
        import trankit.models.base_models as base_models  # type: ignore

        cls = base_models.XLMRobertaModel
        current = getattr(cls, "from_pretrained")
        if getattr(current, "_onnx_no_hidden_states", False):
            return {"installed": True, "already_installed": True}
        original_from_pretrained = current

        @classmethod
        def patched_from_pretrained(model_cls: Any, *args: Any, **kwargs: Any):
            kwargs["output_hidden_states"] = False
            model = original_from_pretrained(*args, **kwargs)
            disable_hidden_state_outputs(model)
            return model

        setattr(patched_from_pretrained, "_onnx_no_hidden_states", True)
        cls.from_pretrained = patched_from_pretrained
        return {"installed": True}
    except Exception as exc:
        return {"installed": False, "error": str(exc)}


def iter_xlmr_tasks(pipeline_obj: Any) -> list[tuple[str, str]]:
    langs = list(getattr(pipeline_obj, "added_langs", []) or [])
    tokenizer_map = getattr(pipeline_obj, "_tokenizer", {}) or {}
    tagger_map = getattr(pipeline_obj, "_tagger", {}) or {}
    ner_map = getattr(pipeline_obj, "_ner_model", {}) or {}
    tasks: list[tuple[str, str]] = []
    for lang in langs:
        lang_name = str(lang)
        if lang_name in tokenizer_map:
            tasks.append((lang_name, "tokenizer"))
        if lang_name in tagger_map:
            tasks.append((lang_name, "tagger"))
        if lang_name in ner_map:
            tasks.append((lang_name, "ner"))
    return tasks


def make_dummy_inputs(pipeline_obj: Any, torch_module: Any, seq_len: int = 16) -> tuple[Any, Any]:
    splitter = getattr(getattr(pipeline_obj, "_config", None), "wordpiece_splitter", None)
    vocab_size = int(getattr(splitter, "vocab_size", 250002) or 250002)
    cls_id = int(getattr(splitter, "cls_token_id", 0) or 0)
    sep_id = int(getattr(splitter, "sep_token_id", 2) or 2)
    pad_id = int(getattr(splitter, "pad_token_id", 1) or 1)
    seq_len = max(4, int(seq_len))
    ids = torch_module.full((1, seq_len), pad_id, dtype=torch_module.long)
    ids[0, 0] = cls_id
    ids[0, seq_len - 1] = sep_id
    for idx in range(1, seq_len - 1):
        ids[0, idx] = 5 + (idx % max(10, min(vocab_size - 6, 5000)))
    attention = torch_module.ones((1, seq_len), dtype=torch_module.long)
    return ids, attention


def export_onnx_fp32(
    pipeline_obj: Any,
    torch_module: Any,
    lang: str,
    task: str,
    raw_path: Path,
    original_load_adapter: Any,
) -> Dict[str, Any]:
    pipeline_obj.set_active(lang)
    original_load_adapter(task)
    embedding_layers = pipeline_obj._embedding_layers
    embedding_layers.eval()
    disable_hidden_state_outputs(embedding_layers.xlmr)

    class TrankitXLMRWrapper(torch_module.nn.Module):
        def __init__(self, layers: Any):
            super().__init__()
            self.embedding_layers = layers
            self.embedding_layers.eval()

        def forward(self, input_ids: Any, attention_mask: Any) -> Any:
            outputs = self.embedding_layers.xlmr(
                input_ids=input_ids,
                attention_mask=attention_mask,
            )
            if isinstance(outputs, (tuple, list)):
                return outputs[0]
            return outputs.last_hidden_state

    dummy_ids, dummy_attention = make_dummy_inputs(pipeline_obj, torch_module)
    started = time.perf_counter()
    kwargs = {
        "input_names": ["input_ids", "attention_mask"],
        "output_names": ["last_hidden_state"],
        "dynamic_axes": {
            "input_ids": {0: "batch_size", 1: "sequence_length"},
            "attention_mask": {0: "batch_size", 1: "sequence_length"},
            "last_hidden_state": {0: "batch_size", 1: "sequence_length"},
        },
        "opset_version": ONNX_EXPORT_OPSET,
        "do_constant_folding": True,
    }
    with torch_module.inference_mode():
        try:
            torch_module.onnx.export(
                TrankitXLMRWrapper(embedding_layers),
                (dummy_ids, dummy_attention),
                str(raw_path),
                dynamo=False,
                **kwargs,
            )
        except TypeError as exc:
            if "dynamo" not in str(exc):
                raise
            torch_module.onnx.export(
                TrankitXLMRWrapper(embedding_layers),
                (dummy_ids, dummy_attention),
                str(raw_path),
                **kwargs,
            )
    return {
        "ok": True,
        "path": str(raw_path),
        "elapsed_seconds": time.perf_counter() - started,
        "opset": ONNX_EXPORT_OPSET,
        "dynamic_axes": True,
        "unit": "active_xlmr_adapter_path",
    }


def optimize_onnx_graph(
    raw_path: Path,
    optimized_path: Path,
    optimize_model_fn: Any,
    *,
    hidden_size: int,
    num_heads: int,
) -> Dict[str, Any]:
    started = time.perf_counter()
    optimized_model = optimize_model_fn(
        str(raw_path),
        model_type="bert",
        num_heads=num_heads,
        hidden_size=hidden_size,
    )
    optimized_model.save_model_to_file(str(optimized_path))
    return {
        "ok": True,
        "path": str(optimized_path),
        "elapsed_seconds": time.perf_counter() - started,
        "method": "onnxruntime.transformers.optimizer",
        "model_type": "bert",
        "num_heads": num_heads,
        "hidden_size": hidden_size,
    }


def dynamic_int8_quantize(
    optimized_path: Path,
    int8_path: Path,
    quantize_dynamic_fn: Any,
    quant_type_cls: Any,
) -> Dict[str, Any]:
    started = time.perf_counter()
    try:
        quantize_dynamic_fn(
            model_input=str(optimized_path),
            model_output=str(int8_path),
            weight_type=quant_type_cls.QInt8,
            per_channel=True,
            extra_options={
                "WeightSymmetric": True,
                "MatMulConstBOnly": True,
                "DefaultTensorType": 1,
            },
        )
    except TypeError:
        quantize_dynamic_fn(
            str(optimized_path),
            str(int8_path),
            weight_type=quant_type_cls.QInt8,
            per_channel=True,
        )
    return {
        "ok": True,
        "path": str(int8_path),
        "elapsed_seconds": time.perf_counter() - started,
        "quantization": "dynamic",
        "weight_type": "QInt8",
        "per_channel": True,
    }


def load_onnx_session(ort_module: Any, path: Path) -> Any:
    session_options = ort_module.SessionOptions()
    session_options.graph_optimization_level = ort_module.GraphOptimizationLevel.ORT_ENABLE_ALL
    return ort_module.InferenceSession(
        str(path),
        sess_options=session_options,
        providers=["CPUExecutionProvider"],
    )


def verify_int8_session(
    ort_module: Any,
    torch_module: Any,
    pipeline_obj: Any,
    int8_path: Path,
) -> Dict[str, Any]:
    started = time.perf_counter()
    session = load_onnx_session(ort_module, int8_path)
    dummy_ids, dummy_attention = make_dummy_inputs(pipeline_obj, torch_module)
    outputs = session.run(
        None,
        {
            "input_ids": dummy_ids.detach().cpu().numpy().astype("int64", copy=False),
            "attention_mask": dummy_attention.detach().cpu().numpy().astype("int64", copy=False),
        },
    )
    first_shape = list(getattr(outputs[0], "shape", [])) if outputs else []
    return {
        "ok": bool(outputs),
        "elapsed_seconds": time.perf_counter() - started,
        "output_shape": first_shape,
        "providers": session.get_providers(),
    }


def remove_intermediates(paths: Dict[str, Path]) -> Dict[str, Any]:
    report: Dict[str, Any] = {"removed": []}
    for key in ("raw", "optimized"):
        path = paths[key]
        if path.exists():
            try:
                path.unlink()
                report["removed"].append(str(path))
            except Exception as exc:
                report.setdefault("errors", []).append(f"{path}: {exc}")
    return report


def build_task(
    pipeline_obj: Any,
    torch_module: Any,
    ort_module: Any,
    optimize_model_fn: Any,
    quantize_dynamic_fn: Any,
    quant_type_cls: Any,
    original_load_adapter: Any,
    lang: str,
    task: str,
    *,
    force: bool,
) -> Dict[str, Any]:
    paths = paths_for_task(lang, task)
    report: Dict[str, Any] = {
        "lang": lang,
        "task": task,
        "profile": ONNX_PROFILE_NAME,
        "paths": {key: str(path) for key, path in paths.items()},
        "session_path": None,
        "ok": False,
    }
    try:
        if force:
            for path in paths.values():
                if path.exists():
                    path.unlink()

        config = getattr(pipeline_obj._embedding_layers.xlmr, "config", None)
        hidden_size = int(getattr(config, "hidden_size", getattr(pipeline_obj._embedding_layers, "xlmr_dim", 768)) or 768)
        num_heads = int(getattr(config, "num_attention_heads", 12) or 12)

        if paths["int8"].exists():
            report["export"] = {"ok": True, "from_cache": True, "skipped": True}
            report["optimization"] = {"ok": True, "from_cache": True, "skipped": True}
            report["quantization"] = {"ok": True, "from_cache": True, "path": str(paths["int8"])}
        else:
            if not paths["raw"].exists() and not paths["optimized"].exists():
                report["export"] = export_onnx_fp32(
                    pipeline_obj,
                    torch_module,
                    lang,
                    task,
                    paths["raw"],
                    original_load_adapter,
                )
            else:
                report["export"] = {
                    "ok": True,
                    "from_cache": True,
                    "path": str(paths["raw"] if paths["raw"].exists() else paths["optimized"]),
                }

            if not paths["optimized"].exists():
                report["optimization"] = optimize_onnx_graph(
                    paths["raw"],
                    paths["optimized"],
                    optimize_model_fn,
                    hidden_size=hidden_size,
                    num_heads=num_heads,
                )
            else:
                report["optimization"] = {"ok": True, "from_cache": True, "path": str(paths["optimized"])}

            report["quantization"] = dynamic_int8_quantize(
                paths["optimized"],
                paths["int8"],
                quantize_dynamic_fn,
                quant_type_cls,
            )

        report["verification"] = verify_int8_session(
            ort_module,
            torch_module,
            pipeline_obj,
            paths["int8"],
        )
        report["session_path"] = paths["int8"].name
        report["int8_path"] = paths["int8"].name
        report["ok"] = bool(report["verification"].get("ok"))
        report["cleanup"] = remove_intermediates(paths)
    except Exception as exc:
        report["ok"] = False
        report["error"] = str(exc)
        report["traceback"] = traceback.format_exc()

    write_json(paths["meta"], report)
    return report


def build_all(force: bool) -> Dict[str, Any]:
    started = time.perf_counter()
    ONNX_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    os.environ["TOKENIZERS_PARALLELISM"] = "false"
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
    import torch  # type: ignore

    deps_report = append_onnx_deps()
    import onnxruntime as ort  # type: ignore
    from onnxruntime.quantization import QuantType, quantize_dynamic  # type: ignore
    from onnxruntime.transformers.optimizer import optimize_model  # type: ignore

    install_forced_cpu_pipeline()
    hidden_state_patch = install_xlmr_no_hidden_state_patch()

    import language_registry as lr

    print("[ONNX] Loading Trankit pipeline on CPU...")
    lr.init_trankit()
    pipeline_obj = getattr(lr, "_trankit_pipeline", None)
    if pipeline_obj is None:
        raise RuntimeError("language_registry did not create _trankit_pipeline")

    original_load_adapter = getattr(pipeline_obj, "_load_adapter_weights")
    tasks = iter_xlmr_tasks(pipeline_obj)
    print(f"[ONNX] Building {len(tasks)} XLM-R adapter task models.")

    reports = []
    failed = 0
    for idx, (lang, task) in enumerate(tasks, start=1):
        label = f"{idx}/{len(tasks)} {lang}:{task}"
        print(f"[ONNX] {label} export -> optimize -> dynamic INT8")
        task_report = build_task(
            pipeline_obj,
            torch,
            ort,
            optimize_model,
            quantize_dynamic,
            QuantType,
            original_load_adapter,
            lang,
            task,
            force=force,
        )
        reports.append(task_report)
        if task_report.get("ok"):
            print(f"[ONNX] {label} ok")
        else:
            failed += 1
            print(f"[ONNX] {label} failed: {task_report.get('error')}")
            break
        gc.collect()

    manifest = {
        "cache_version": 1,
        "profile": ONNX_PROFILE_NAME,
        "built_at": time.time(),
        "elapsed_seconds": time.perf_counter() - started,
        "root": str(ROOT),
        "cache_dir": str(ONNX_CACHE_DIR),
        "deps": deps_report,
        "torch_version": getattr(torch, "__version__", ""),
        "onnxruntime_version": getattr(ort, "__version__", ""),
        "opset": ONNX_EXPORT_OPSET,
        "hidden_state_patch": hidden_state_patch,
        "task_count": len(tasks),
        "built_task_count": len([r for r in reports if r.get("ok")]),
        "failed_task_count": failed + max(0, len(tasks) - len(reports)),
        "ok": failed == 0 and len(reports) == len(tasks),
        "tasks": reports,
    }
    write_json(ONNX_MANIFEST_PATH, manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build ONNX Runtime optimized dynamic-INT8 XLM-R adapter models for the Trankit benchmark app."
    )
    parser.add_argument("--force", action="store_true", help="delete existing ONNX task files before rebuilding")
    args = parser.parse_args()

    try:
        manifest = build_all(force=bool(args.force))
    except Exception as exc:
        print(f"[ONNX] build failed: {exc}", file=sys.stderr)
        traceback.print_exc()
        return 2

    print(
        "[ONNX] manifest:",
        ONNX_MANIFEST_PATH,
        f"ok={manifest.get('ok')}",
        f"built={manifest.get('built_task_count')}/{manifest.get('task_count')}",
        f"failed={manifest.get('failed_task_count')}",
    )
    return 0 if manifest.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
