"""Trankit benchmark: instrumentation."""

from __future__ import annotations

import gc
import time
from contextlib import ExitStack, contextmanager
from typing import Any, Dict, Optional

from . import memory


@contextmanager
def _temporary_no_gc_collect():
    real_collect = gc.collect
    calls = {"count": 0}

    def fake_collect(*args: Any, **kwargs: Any) -> int:
        calls["count"] += 1
        return 0

    gc.collect = fake_collect
    try:
        yield calls
    finally:
        gc.collect = real_collect


@contextmanager
def _temporary_no_cuda_empty_cache(torch_module: Any):
    calls = {"count": 0}
    cuda_obj = getattr(torch_module, "cuda", None) if torch_module is not None else None
    real_empty_cache = (
        getattr(cuda_obj, "empty_cache", None) if cuda_obj is not None else None
    )
    if real_empty_cache is None:
        yield calls
        return

    def fake_empty_cache(*args: Any, **kwargs: Any) -> None:
        calls["count"] += 1
        return None

    cuda_obj.empty_cache = fake_empty_cache
    try:
        yield calls
    finally:
        cuda_obj.empty_cache = real_empty_cache


@contextmanager
def _temporary_tensor_sync_point_counter(torch_module: Any):
    tensor_cls = (
        getattr(torch_module, "Tensor", None) if torch_module is not None else None
    )
    if tensor_cls is None:
        yield {"available": False, "calls": {}}
        return

    method_names = ["cpu", "numpy", "tolist", "item"]
    originals: Dict[str, Any] = {}
    calls: Dict[str, Dict[str, Any]] = {
        name: {"count": 0, "elapsed_seconds": 0.0} for name in method_names
    }

    def make_wrapper(method_name: str, original: Any):
        def wrapped(self: Any, *args: Any, **kwargs: Any):
            started = time.perf_counter()
            try:
                return original(self, *args, **kwargs)
            finally:
                row = calls[method_name]
                row["count"] = int(row.get("count") or 0) + 1
                row["elapsed_seconds"] = float(row.get("elapsed_seconds") or 0.0) + (
                    time.perf_counter() - started
                )

        return wrapped

    patch_errors: Dict[str, str] = {}
    try:
        for name in method_names:
            original = getattr(tensor_cls, name, None)
            if original is None:
                continue
            originals[name] = original
            try:
                setattr(tensor_cls, name, make_wrapper(name, original))
            except Exception as exc:
                patch_errors[name] = str(exc)
        yield {"available": True, "calls": calls, "patch_errors": patch_errors}
    finally:
        for name, original in originals.items():
            try:
                setattr(tensor_cls, name, original)
            except Exception:
                pass


@contextmanager
def _torch_cpu_inference_context(torch_module: Any, use_bf16_autocast: bool):
    with ExitStack() as stack:
        if hasattr(torch_module, "inference_mode"):
            stack.enter_context(torch_module.inference_mode())
        if use_bf16_autocast and hasattr(torch_module, "autocast"):
            stack.enter_context(
                torch_module.autocast("cpu", dtype=torch_module.bfloat16)
            )
        yield


@contextmanager
def _temporary_trankit_task_breakdown(
    pipeline_obj: Any, torch_module: Any, use_gpu: bool, registry_module: Any = None
):
    method_to_stage = {
        "_tokenize_doc": "tokenization",
        "_mwt_expand": "mwt_expansion",
        "_posdep_doc": "posdep_tagging",
        "_lemmatize_doc": "lemmatization",
        "_ner_doc": "ner",
    }
    stage_order = [
        "tokenization",
        "mwt_expansion",
        "posdep_tagging",
        "lemmatization",
        "ner",
    ]
    rows: Dict[str, Dict[str, Any]] = {
        name: {
            "count": 0,
            "elapsed_seconds": 0.0,
            "exclusive_seconds": 0.0,
            "nested_seconds": 0.0,
            "errors": 0,
            "batch_count": 0,
            "batch_items": 0,
            "batch_min_items": None,
            "batch_max_items": None,
            "batch_padded_units": 0,
            "batch_real_units": 0,
            "batch_padding_units": 0,
            "batch_padding_details": [],
            "batch_max_padded_length": None,
            "xlm_call_count": 0,
            "xlm_call_seconds": 0.0,
            "head_call_count": 0,
            "head_call_seconds": 0.0,
            "seq2seq_call_count": 0,
            "seq2seq_call_seconds": 0.0,
            "model_call_seconds": 0.0,
        }
        for name in stage_order
    }
    report: Dict[str, Any] = {
        "available": pipeline_obj is not None,
        "uses_cuda_sync": bool(use_gpu),
        "stages": rows,
    }
    if pipeline_obj is None:
        yield report
        return

    originals: Dict[str, Any] = {}
    module_originals: Dict[str, Any] = {}
    method_originals: list[tuple[Any, str, Any]] = []
    patched_method_keys: set[tuple[int, str]] = set()
    stack: list[Dict[str, Any]] = []

    def current_stage() -> Optional[str]:
        if not stack:
            return None
        stage = stack[-1].get("stage")
        return str(stage) if stage in rows else None

    def safe_len(value: Any) -> Optional[int]:
        try:
            return int(len(value))
        except Exception:
            return None

    def safe_dim(value: Any, index: int) -> Optional[int]:
        try:
            if hasattr(value, "size"):
                return int(value.size(index))
        except Exception:
            pass
        try:
            shape = getattr(value, "shape", None)
            if shape is not None and len(shape) > index:
                return int(shape[index])
        except Exception:
            pass
        return None

    def infer_batch_shape(
        args: tuple[Any, ...],
    ) -> tuple[Optional[int], Optional[int], Optional[int]]:
        if not args:
            return None, None, None
        batch = args[0]
        item_count: Optional[int] = None
        padded_length: Optional[int] = None
        real_units: Optional[int] = None

        for attr in ("word_num", "wordpiece_num", "paragraph_index", "sent_index"):
            value = getattr(batch, attr, None)
            item_count = safe_len(value)
            if item_count is not None:
                break

        wordpieces = getattr(batch, "wordpieces", None)
        if isinstance(wordpieces, list):
            try:
                real_units = sum(
                    len(item) + 2 for item in wordpieces if isinstance(item, list)
                )
            except Exception:
                real_units = None

        word_lens = getattr(batch, "word_lens", None)
        if real_units is None and isinstance(word_lens, list):
            try:
                real_units = sum(
                    sum(int(length) for length in item) + 2
                    for item in word_lens
                    if isinstance(item, list)
                )
            except Exception:
                real_units = None

        piece_idxs = getattr(batch, "piece_idxs", None)
        if piece_idxs is not None:
            if item_count is None:
                item_count = safe_dim(piece_idxs, 0)
            padded_length = safe_dim(piece_idxs, 1)

        if isinstance(batch, (tuple, list)) and batch:
            first = batch[0]
            if item_count is None:
                item_count = safe_dim(first, 0)
            padded_length = (
                padded_length if padded_length is not None else safe_dim(first, 1)
            )

        return item_count, padded_length, real_units

    def add_batch_stats(
        stage_name: str,
        kind: str,
        args: tuple[Any, ...],
        elapsed_seconds: float,
        count_as_batch: bool,
    ) -> None:
        row = rows.get(stage_name)
        if row is None:
            return
        call_count_key = f"{kind}_call_count"
        call_seconds_key = f"{kind}_call_seconds"
        row[call_count_key] = int(row.get(call_count_key) or 0) + 1
        row[call_seconds_key] = (
            float(row.get(call_seconds_key) or 0.0) + elapsed_seconds
        )
        row["model_call_seconds"] = (
            float(row.get("model_call_seconds") or 0.0) + elapsed_seconds
        )
        if not count_as_batch:
            return
        item_count, padded_length, real_units = infer_batch_shape(args)
        row["batch_count"] = int(row.get("batch_count") or 0) + 1
        batch_index = int(row.get("batch_count") or 0)
        if isinstance(item_count, int) and item_count >= 0:
            row["batch_items"] = int(row.get("batch_items") or 0) + item_count
            previous_min = row.get("batch_min_items")
            row["batch_min_items"] = (
                item_count
                if previous_min is None
                else min(int(previous_min), item_count)
            )
            previous_max = row.get("batch_max_items")
            row["batch_max_items"] = (
                item_count
                if previous_max is None
                else max(int(previous_max), item_count)
            )
        if isinstance(padded_length, int) and padded_length >= 0:
            previous_len = row.get("batch_max_padded_length")
            row["batch_max_padded_length"] = (
                padded_length
                if previous_len is None
                else max(int(previous_len), padded_length)
            )
            if isinstance(item_count, int) and item_count >= 0:
                padded_units = item_count * padded_length
                row["batch_padded_units"] = (
                    int(row.get("batch_padded_units") or 0) + padded_units
                )
                detail: Dict[str, Any] = {
                    "index": batch_index,
                    "items": item_count,
                    "max_len": padded_length,
                    "padded_units": padded_units,
                }
                if isinstance(real_units, int) and real_units >= 0:
                    padding_units = max(0, padded_units - real_units)
                    row["batch_real_units"] = (
                        int(row.get("batch_real_units") or 0) + real_units
                    )
                    row["batch_padding_units"] = (
                        int(row.get("batch_padding_units") or 0) + padding_units
                    )
                    detail["real_units"] = real_units
                    detail["padding_units"] = padding_units
                details = row.get("batch_padding_details")
                if isinstance(details, list) and len(details) < 80:
                    details.append(detail)

    def patch_bound_method(
        obj: Any, method_name: str, kind: str, count_as_batch: bool
    ) -> None:
        if obj is None:
            return
        key = (id(obj), method_name)
        if key in patched_method_keys:
            return
        original = getattr(obj, method_name, None)
        if original is None:
            return

        def wrapped(*args: Any, **kwargs: Any):
            stage_name = current_stage()
            started = time.perf_counter()
            try:
                return original(*args, **kwargs)
            finally:
                if stage_name:
                    add_batch_stats(
                        stage_name,
                        kind,
                        args,
                        time.perf_counter() - started,
                        count_as_batch,
                    )

        try:
            setattr(obj, method_name, wrapped)
        except Exception:
            return
        patched_method_keys.add(key)
        method_originals.append((obj, method_name, original))

    def patch_model_call_counters() -> None:
        embedding_layers = getattr(pipeline_obj, "_embedding_layers", None)
        patch_bound_method(embedding_layers, "get_tokenizer_inputs", "xlm", True)
        patch_bound_method(embedding_layers, "get_tagger_inputs", "xlm", True)

        for model in (getattr(pipeline_obj, "_tokenizer", {}) or {}).values():
            patch_bound_method(model, "predict", "head", False)
        for model in (getattr(pipeline_obj, "_tagger", {}) or {}).values():
            patch_bound_method(model, "predict", "head", False)
        for model in (getattr(pipeline_obj, "_ner_model", {}) or {}).values():
            patch_bound_method(model, "predict", "head", False)

        for wrapper in (getattr(pipeline_obj, "_lemma_model", {}) or {}).values():
            patch_bound_method(
                getattr(wrapper, "model", None), "predict", "seq2seq", True
            )
        for wrapper in (getattr(pipeline_obj, "_mwt_model", {}) or {}).values():
            patch_bound_method(
                getattr(wrapper, "model", None), "predict", "seq2seq", True
            )

    @contextmanager
    def timed(stage_name: str):
        memory._sync_cuda(torch_module, use_gpu)
        frame = {"stage": stage_name, "nested_seconds": 0.0}
        stack.append(frame)
        started = time.perf_counter()
        ok = True
        try:
            yield
        except Exception:
            ok = False
            raise
        finally:
            memory._sync_cuda(torch_module, use_gpu)
            elapsed = time.perf_counter() - started
            current = stack.pop() if stack else frame
            nested = float(current.get("nested_seconds") or 0.0)
            exclusive = max(0.0, elapsed - nested)
            row = rows[stage_name]
            row["count"] = int(row.get("count") or 0) + 1
            row["elapsed_seconds"] = float(row.get("elapsed_seconds") or 0.0) + elapsed
            row["exclusive_seconds"] = (
                float(row.get("exclusive_seconds") or 0.0) + exclusive
            )
            row["nested_seconds"] = float(row.get("nested_seconds") or 0.0) + nested
            if not ok:
                row["errors"] = int(row.get("errors") or 0) + 1
            if stack:
                stack[-1]["nested_seconds"] = (
                    float(stack[-1].get("nested_seconds") or 0.0) + elapsed
                )

    def make_wrapper(stage_name: str, original: Any):
        def wrapped(*args: Any, **kwargs: Any):
            with timed(stage_name):
                return original(*args, **kwargs)

        return wrapped

    try:
        for method_name, stage_name in method_to_stage.items():
            original = getattr(pipeline_obj, method_name, None)
            if original is None:
                continue
            originals[method_name] = original
            setattr(pipeline_obj, method_name, make_wrapper(stage_name, original))
        patch_model_call_counters()
        if registry_module is not None:
            helper_name = "_tokenize_manual_sentence_spans_batched"
            original = getattr(registry_module, helper_name, None)
            if original is not None:
                module_originals[helper_name] = original
                setattr(
                    registry_module, helper_name, make_wrapper("tokenization", original)
                )
        report["patched_methods"] = sorted(originals)
        yield report
    finally:
        for method_name, original in originals.items():
            try:
                setattr(pipeline_obj, method_name, original)
            except Exception:
                pass
        for method_name, original in module_originals.items():
            try:
                setattr(registry_module, method_name, original)
            except Exception:
                pass
        for obj, method_name, original in reversed(method_originals):
            try:
                setattr(obj, method_name, original)
            except Exception:
                pass
