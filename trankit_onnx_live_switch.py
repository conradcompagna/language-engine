"""
Live ONNX switch for the Trankit runtime.

This installs the compressed ONNX CPU XLM-R runtime built by the sandbox
artifact scripts, while preserving Trankit's normal document output shape.
It is intentionally backend-only and has no frontend or route behavior.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional


ROOT = Path(__file__).resolve().parent
MANIFEST_PATH = ROOT / ".trankit_compressed_runtime" / "manifest.json"
TOKENIZER_CANDIDATES = [1, 2, 3, 4, 6, 8, 12, 16]
TAGGER_NER_CANDIDATES = [1, 2, 4, 8, 12, 16, 24, 32]
TOKENIZER_CALL_OVERHEAD_UNITS = 768
TAGGER_NER_CALL_OVERHEAD_UNITS = 768
DEFAULT_TOK_BATCH_SIZE = 12
DEFAULT_TAG_BATCH_SIZE = 32


def prepare_newpipeline_environment() -> None:
    """Force the live NEWPIPELINE runtime onto CPU before Trankit imports."""
    os.environ["CUDA_VISIBLE_DEVICES"] = ""
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")


def _disable_hidden_states(module: Any) -> Dict[str, Any]:
    checked = 0
    changed = 0
    try:
        iterator = module.modules()
    except Exception:
        iterator = [module]
    for child in iterator:
        if hasattr(child, "output_hidden_states"):
            checked += 1
            try:
                if getattr(child, "output_hidden_states") is not False:
                    setattr(child, "output_hidden_states", False)
                    changed += 1
            except Exception:
                pass
        config = getattr(child, "config", None)
        if config is not None and hasattr(config, "output_hidden_states"):
            checked += 1
            try:
                if getattr(config, "output_hidden_states") is not False:
                    setattr(config, "output_hidden_states", False)
                    changed += 1
            except Exception:
                pass
    return {"checked": checked, "changed": changed}


def _force_eval_mode(pipeline: Any) -> Dict[str, Any]:
    targets = []
    for attr in [
        "_embedding_layers",
        "_tokenizer",
        "_tagger",
        "_ner_model",
        "_lemma_model",
        "_mwt_model",
    ]:
        value = getattr(pipeline, attr, None)
        if isinstance(value, dict):
            for key, module in value.items():
                targets.append((f"{attr}.{key}", module))
        elif value is not None:
            targets.append((attr, value))
    if getattr(getattr(pipeline, "_embedding_layers", None), "xlmr", None) is not None:
        targets.append(("_embedding_layers.xlmr", pipeline._embedding_layers.xlmr))

    evaled = []
    errors = []
    for name, module in targets:
        try:
            if hasattr(module, "eval"):
                module.eval()
                evaled.append(name)
            model = getattr(module, "model", None)
            if model is not None and hasattr(model, "eval"):
                model.eval()
                evaled.append(f"{name}.model")
        except Exception as exc:
            errors.append({"module": name, "error": str(exc)})
    return {"evaled": evaled, "errors": errors}


def _suppress_cuda_empty_cache(torch_module: Any) -> Dict[str, Any]:
    cuda_obj = getattr(torch_module, "cuda", None)
    if cuda_obj is None or getattr(cuda_obj, "empty_cache", None) is None:
        return {"installed": False, "reason": "torch.cuda.empty_cache unavailable"}
    if getattr(cuda_obj.empty_cache, "_live_onnx_suppressed", False):
        return {"installed": True, "already_installed": True}

    def no_empty_cache(*_args: Any, **_kwargs: Any) -> None:
        return None

    setattr(no_empty_cache, "_live_onnx_suppressed", True)
    cuda_obj.empty_cache = no_empty_cache
    return {"installed": True}


def _apply_batch_sizes(pipeline: Any, tok_batch_size: int, tag_batch_size: int) -> Dict[str, Any]:
    tok_value = max(1, int(tok_batch_size))
    tag_value = max(1, int(tag_batch_size))
    report: Dict[str, Any] = {
        "tok_batch_size": tok_value,
        "tag_batch_size": tag_value,
        "previous_tok_batch_size": getattr(pipeline, "_tokbatchsize", None),
        "previous_tag_batch_size": getattr(pipeline, "_tagbatchsize", None),
        "tb_tok_overrides_changed": 0,
        "tb_tag_overrides_changed": 0,
    }
    pipeline._tokbatchsize = tok_value
    pipeline._tagbatchsize = tag_value

    import trankit.utils.tbinfo as tbinfo  # type: ignore

    tok_map = getattr(tbinfo, "tbname2tokbatchsize", None)
    if isinstance(tok_map, dict):
        for key in list(tok_map.keys()):
            tok_map[key] = tok_value
        report["tb_tok_overrides_changed"] = len(tok_map)
    tag_map = getattr(tbinfo, "tbname2tagbatchsize", None)
    if isinstance(tag_map, dict):
        for key in list(tag_map.keys()):
            tag_map[key] = tag_value
        report["tb_tag_overrides_changed"] = len(tag_map)
    return report


def _install_tokenizer_dynamic_padding_patch() -> Dict[str, Any]:
    from trankit.iterators import tokenizer_iterators  # type: ignore

    dataset_cls = tokenizer_iterators.TokenizeDatasetLive
    if getattr(dataset_cls, "_live_onnx_dynamic_padding_installed", False):
        return {"installed": True, "already_installed": True}

    original_numberize = dataset_cls.numberize
    original_collate_fn = dataset_cls.collate_fn

    def numberize_dynamic(self: Any, wordpiece_splitter: Any) -> None:
        data = []
        for inst in self.data:
            wordpieces = inst["wordpieces"]
            wordpiece_labels = inst["wordpiece_labels"]
            wordpiece_ends = inst["wordpiece_ends"]
            paragraph_index = inst["paragraph_index"]
            piece_idxs = wordpiece_splitter.encode(
                wordpieces,
                add_special_tokens=True,
                max_length=self.max_input_length,
                truncation=True,
            )
            assert len(piece_idxs) <= self.max_input_length
            attention_masks = [1] * len(piece_idxs)
            token_type_idxs = [
                -100 if piece_id >= len(wordpieces) else wordpiece_labels[piece_id]
                for piece_id in range(max(0, len(piece_idxs) - 2))
            ]
            data.append(
                tokenizer_iterators.Instance(
                    paragraph_index=paragraph_index,
                    wordpieces=wordpieces,
                    wordpiece_labels=wordpiece_labels,
                    wordpiece_ends=wordpiece_ends,
                    piece_idxs=piece_idxs,
                    attention_masks=attention_masks,
                    token_type_idxs=token_type_idxs,
                    wordpiece_num=len(wordpieces),
                )
            )
        self.data = data

    def collate_fn_dynamic(self: Any, batch: Any) -> Any:
        max_piece_num = max(len(inst.piece_idxs) for inst in batch)
        max_token_type_num = max(0, max_piece_num - 2)
        batch_paragraph_index = []
        batch_wordpieces = []
        batch_wordpiece_labels = []
        batch_wordpiece_ends = []
        batch_piece_idxs = []
        batch_attention_masks = []
        batch_token_type_idxs = []
        batch_wordpiece_num = []

        for inst in batch:
            piece_pad = max_piece_num - len(inst.piece_idxs)
            token_type_pad = max_token_type_num - len(inst.token_type_idxs)
            batch_paragraph_index.append(inst.paragraph_index)
            batch_wordpieces.append(inst.wordpieces)
            batch_wordpiece_labels.append(inst.wordpiece_labels)
            batch_wordpiece_ends.append(inst.wordpiece_ends)
            batch_piece_idxs.append(inst.piece_idxs + [0] * piece_pad)
            batch_attention_masks.append(inst.attention_masks + [0] * piece_pad)
            batch_token_type_idxs.append(inst.token_type_idxs + [-100] * max(0, token_type_pad))
            batch_wordpiece_num.append(inst.wordpiece_num)

        torch_module = tokenizer_iterators.torch
        return tokenizer_iterators.Batch(
            paragraph_index=batch_paragraph_index,
            wordpieces=batch_wordpieces,
            wordpiece_labels=batch_wordpiece_labels,
            wordpiece_ends=batch_wordpiece_ends,
            piece_idxs=torch_module.tensor(
                batch_piece_idxs, dtype=torch_module.long, device=self.config.device
            ),
            attention_masks=torch_module.tensor(
                batch_attention_masks, dtype=torch_module.long, device=self.config.device
            ),
            token_type_idxs=torch_module.tensor(
                batch_token_type_idxs, dtype=torch_module.long, device=self.config.device
            ),
            wordpiece_num=torch_module.tensor(
                batch_wordpiece_num, dtype=torch_module.long, device=self.config.device
            ),
        )

    dataset_cls._live_onnx_original_numberize = original_numberize
    dataset_cls._live_onnx_original_collate_fn = original_collate_fn
    dataset_cls.numberize = numberize_dynamic
    dataset_cls.collate_fn = collate_fn_dynamic
    dataset_cls._live_onnx_dynamic_padding_installed = True
    return {"installed": True, "padding": "dynamic_per_batch"}


def _install_tagger_ner_length_bucketing_patch() -> Dict[str, Any]:
    from trankit.iterators import ner_iterators, tagger_iterators  # type: ignore

    def sort_key(inst: Any) -> tuple[int, int, int, int]:
        piece_len = int(len(getattr(inst, "piece_idxs", []) or []))
        word_num = int(getattr(inst, "word_num", 0) or 0)
        sent_index = int(getattr(inst, "sent_index", 0) or 0)
        word_ids = getattr(inst, "word_ids", []) or []
        first_word_id = int(word_ids[0]) if word_ids else 0
        return piece_len, word_num, sent_index, first_word_id

    def patch_dataset(dataset_cls: Any, label: str) -> Dict[str, Any]:
        if getattr(dataset_cls, "_live_onnx_length_bucketing_installed", False):
            return {"target": label, "installed": True, "already_installed": True}
        original_numberize = dataset_cls.numberize

        def numberize_bucketed(self: Any, *args: Any, **kwargs: Any) -> Any:
            result = original_numberize(self, *args, **kwargs)
            self.data = sorted(self.data, key=sort_key)
            return result

        dataset_cls._live_onnx_original_numberize_for_bucketing = original_numberize
        dataset_cls.numberize = numberize_bucketed
        dataset_cls._live_onnx_length_bucketing_installed = True
        return {"target": label, "installed": True}

    rows = [
        patch_dataset(tagger_iterators.TaggerDatasetLive, "TaggerDatasetLive"),
        patch_dataset(ner_iterators.NERDatasetLive, "NERDatasetLive"),
    ]
    return {
        "installed": all(bool(row.get("installed")) for row in rows),
        "patches": rows,
        "strategy": "sort_numberized_examples_by_piece_length",
    }


def _get_piece_length(inst: Any) -> int:
    return int(len(getattr(inst, "piece_idxs", []) or []))


def _stable_sort_key(inst: Any) -> tuple[int, int, int, int, int]:
    piece_len = _get_piece_length(inst)
    word_num = int(getattr(inst, "word_num", getattr(inst, "wordpiece_num", 0)) or 0)
    paragraph_index = int(getattr(inst, "paragraph_index", 0) or 0)
    sent_index = int(getattr(inst, "sent_index", 0) or 0)
    word_ids = getattr(inst, "word_ids", []) or []
    first_word_id = int(word_ids[0]) if word_ids else 0
    return piece_len, word_num, paragraph_index, sent_index, first_word_id


def _partition_plan(lengths: list[int], max_batch_size: int, overhead_units: int) -> Dict[str, Any]:
    clean_lengths = [int(length) for length in lengths if int(length) > 0]
    item_count = len(clean_lengths)
    if not clean_lengths:
        return {"batch_indices": [], "batch_count": 0}
    max_size = max(1, min(item_count, int(max_batch_size or 1)))
    prefix = [0]
    for length in clean_lengths:
        prefix.append(prefix[-1] + length)

    dp = [0] + [10**18] * item_count
    prev = [0] * (item_count + 1)
    for end in range(1, item_count + 1):
        best_cost = 10**18
        best_start = end - 1
        start_floor = max(0, end - max_size)
        for start in range(end - 1, start_floor - 1, -1):
            group_len = end - start
            max_len = clean_lengths[end - 1]
            padded_units = group_len * max_len
            cost = dp[start] + padded_units + overhead_units
            if cost < best_cost:
                best_cost = cost
                best_start = start
        dp[end] = best_cost
        prev[end] = best_start

    ranges = []
    cursor = item_count
    while cursor > 0:
        start = prev[cursor]
        ranges.append((start, cursor))
        cursor = start
    ranges.reverse()

    batch_indices = [list(range(start, end)) for start, end in ranges if end > start]
    return {
        "batch_indices": batch_indices,
        "batch_count": len(batch_indices),
        "batch_sizes": [len(indexes) for indexes in batch_indices],
        "max_batch_size": max_size,
        "real_units": prefix[-1],
    }


def _install_dynamic_batching_patch() -> Dict[str, Any]:
    import trankit.pipeline as trankit_pipeline  # type: ignore
    from trankit.iterators import ner_iterators, tagger_iterators, tokenizer_iterators  # type: ignore

    if getattr(trankit_pipeline, "_live_onnx_dynamic_batching_installed", False):
        return {"installed": True, "already_installed": True}

    original_loader = getattr(trankit_pipeline, "DataLoader", None)
    if original_loader is None:
        raise RuntimeError("trankit.pipeline.DataLoader is unavailable")

    tokenizer_cls = tokenizer_iterators.TokenizeDatasetLive
    tagger_cls = tagger_iterators.TaggerDatasetLive
    ner_cls = ner_iterators.NERDatasetLive

    def dataset_kind(dataset: Any) -> Optional[str]:
        class_name = dataset.__class__.__name__
        if class_name in {"LemmaDataLoader", "MWTDataLoader"}:
            return None
        if isinstance(dataset, tokenizer_cls):
            return "tokenizer"
        if isinstance(dataset, tagger_cls):
            return "tagger"
        if isinstance(dataset, ner_cls):
            return "ner"
        return None

    def get_requested_batch_size(args: tuple[Any, ...], kwargs: Dict[str, Any]) -> Optional[int]:
        if "batch_size" in kwargs and kwargs.get("batch_size") is not None:
            return int(kwargs["batch_size"])
        if args:
            return int(args[0])
        return None

    class StaticBatchSampler:
        def __init__(self, batches: list[list[int]]) -> None:
            self.batches = [list(batch) for batch in batches if batch]

        def __iter__(self):
            return iter(self.batches)

        def __len__(self) -> int:
            return len(self.batches)

    def dynamic_loader(dataset: Any, *args: Any, **kwargs: Any) -> Any:
        kind = dataset_kind(dataset)
        if not kind or bool(kwargs.get("shuffle")):
            return original_loader(dataset, *args, **kwargs)
        data = getattr(dataset, "data", None)
        if not isinstance(data, list) or not data:
            return original_loader(dataset, *args, **kwargs)

        dataset.data = sorted(data, key=_stable_sort_key)
        lengths = [_get_piece_length(inst) for inst in dataset.data]
        requested = get_requested_batch_size(args, kwargs)
        if kind == "tokenizer":
            candidate_max = max(TOKENIZER_CANDIDATES + ([requested] if requested else []))
            overhead_units = TOKENIZER_CALL_OVERHEAD_UNITS
        else:
            candidate_max = max(TAGGER_NER_CANDIDATES + ([requested] if requested else []))
            overhead_units = TAGGER_NER_CALL_OVERHEAD_UNITS
        plan = _partition_plan(lengths, candidate_max, overhead_units)
        batch_indices = plan.get("batch_indices")
        if not isinstance(batch_indices, list) or not batch_indices:
            return original_loader(dataset, *args, **kwargs)

        clean_kwargs = dict(kwargs)
        clean_kwargs.pop("batch_size", None)
        clean_kwargs.pop("shuffle", None)
        clean_kwargs.pop("sampler", None)
        clean_kwargs.pop("drop_last", None)
        clean_kwargs["batch_sampler"] = StaticBatchSampler(batch_indices)
        clean_args = list(args[1:]) if args else []
        return original_loader(dataset, *clean_args, **clean_kwargs)

    trankit_pipeline._live_onnx_original_dataloader = original_loader
    trankit_pipeline.DataLoader = dynamic_loader
    trankit_pipeline._live_onnx_dynamic_batching_installed = True
    return {
        "installed": True,
        "strategy": "sort_by_piece_length_and_dynamic_partition",
        "seq2seq_dynamic_batching": False,
    }


def install_live_onnx_pipeline(pipeline: Any) -> Dict[str, Any]:
    """Install the live ONNX CPU runtime into an already-loaded Trankit pipeline."""
    prepare_newpipeline_environment()
    if not MANIFEST_PATH.exists():
        raise RuntimeError(
            f"NEWPIPELINE=1 but compressed runtime manifest is missing: {MANIFEST_PATH}"
        )

    import torch  # type: ignore
    from trankit_compressed_runtime import install_compressed_runtime

    eval_report = _force_eval_mode(pipeline)
    hidden_report = _disable_hidden_states(getattr(pipeline, "_embedding_layers", pipeline))
    batch_report = _apply_batch_sizes(pipeline, DEFAULT_TOK_BATCH_SIZE, DEFAULT_TAG_BATCH_SIZE)
    tokenizer_padding_report = _install_tokenizer_dynamic_padding_patch()
    tagger_ner_bucketing_report = _install_tagger_ner_length_bucketing_patch()
    dynamic_batching_report = _install_dynamic_batching_patch()
    cuda_cache_report = _suppress_cuda_empty_cache(torch)
    compressed_report = install_compressed_runtime(pipeline, torch, manifest_path=MANIFEST_PATH)

    ort_tuning = compressed_report.get("ort_tuning") if isinstance(compressed_report, dict) else {}
    if not isinstance(ort_tuning, dict) or not ort_tuning.get("applied"):
        raise RuntimeError(f"NEWPIPELINE=1 but ORT session tuning was not applied: {ort_tuning}")

    quant_report = (
        compressed_report.get("pytorch_quantization") if isinstance(compressed_report, dict) else {}
    )
    if not isinstance(quant_report, dict) or not quant_report.get("quantized"):
        raise RuntimeError(
            "NEWPIPELINE=1 but PyTorch task-module quantization did not quantize any modules"
        )

    required_reports = {
        "tokenizer_dynamic_padding": tokenizer_padding_report,
        "tagger_ner_length_bucketing": tagger_ner_bucketing_report,
        "dynamic_batching": dynamic_batching_report,
    }
    failed = {
        name: report
        for name, report in required_reports.items()
        if not isinstance(report, dict) or not report.get("installed")
    }
    if failed:
        raise RuntimeError(f"NEWPIPELINE=1 but live ONNX runtime patches failed: {failed}")

    return {
        "installed": True,
        "profile": compressed_report.get("profile"),
        "manifest_path": str(MANIFEST_PATH),
        "onnx_session": compressed_report.get("onnx_session"),
        "adapter_pack_count": compressed_report.get("adapter_pack_count"),
        "task_count": compressed_report.get("task_count"),
        "language_count": compressed_report.get("language_count"),
        "ort_tuning": ort_tuning,
        "pytorch_quantization": quant_report,
        "eval": eval_report,
        "hidden_states": hidden_report,
        "batch_sizes": batch_report,
        "tokenizer_dynamic_padding": tokenizer_padding_report,
        "tagger_ner_length_bucketing": tagger_ner_bucketing_report,
        "dynamic_batching": dynamic_batching_report,
        "cuda_empty_cache": cuda_cache_report,
    }
