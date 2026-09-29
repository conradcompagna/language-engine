"""Trankit benchmark: onnx batching."""

from __future__ import annotations

from typing import Any, Dict, Optional

from . import settings


def _install_onnx_tokenizer_dynamic_padding_patch() -> Dict[str, Any]:
    report: Dict[str, Any] = {
        "installed": False,
        "target": "trankit.iterators.tokenizer_iterators.TokenizeDatasetLive",
    }
    try:
        from trankit.iterators import (
            tokenizer_iterators as tokenizer_iterators,  # type: ignore
        )

        dataset_cls = tokenizer_iterators.TokenizeDatasetLive
        if getattr(dataset_cls, "_benchmark_dynamic_padding_installed", False):
            report["installed"] = True
            report["already_installed"] = True
            return report

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
            batch_paragraph_index = []
            batch_wordpieces = []
            batch_wordpiece_labels = []
            batch_wordpiece_ends = []
            batch_piece_idxs = []
            batch_attention_masks = []
            batch_token_type_idxs = []
            batch_wordpiece_num = []

            max_piece_num = max(len(inst.piece_idxs) for inst in batch)
            max_token_type_num = max(0, max_piece_num - 2)
            for inst in batch:
                piece_pad = max_piece_num - len(inst.piece_idxs)
                token_type_pad = max_token_type_num - len(inst.token_type_idxs)
                batch_paragraph_index.append(inst.paragraph_index)
                batch_wordpieces.append(inst.wordpieces)
                batch_wordpiece_labels.append(inst.wordpiece_labels)
                batch_wordpiece_ends.append(inst.wordpiece_ends)
                batch_piece_idxs.append(inst.piece_idxs + [0] * piece_pad)
                batch_attention_masks.append(inst.attention_masks + [0] * piece_pad)
                batch_token_type_idxs.append(
                    inst.token_type_idxs + [-100] * max(0, token_type_pad)
                )
                batch_wordpiece_num.append(inst.wordpiece_num)

            torch_module = tokenizer_iterators.torch
            batch_piece_idxs_tensor = torch_module.tensor(
                batch_piece_idxs, dtype=torch_module.long, device=self.config.device
            )
            batch_attention_masks_tensor = torch_module.tensor(
                batch_attention_masks,
                dtype=torch_module.long,
                device=self.config.device,
            )
            batch_token_type_idxs_tensor = torch_module.tensor(
                batch_token_type_idxs,
                dtype=torch_module.long,
                device=self.config.device,
            )
            batch_wordpiece_num_tensor = torch_module.tensor(
                batch_wordpiece_num, dtype=torch_module.long, device=self.config.device
            )

            return tokenizer_iterators.Batch(
                paragraph_index=batch_paragraph_index,
                wordpieces=batch_wordpieces,
                wordpiece_labels=batch_wordpiece_labels,
                wordpiece_ends=batch_wordpiece_ends,
                piece_idxs=batch_piece_idxs_tensor,
                attention_masks=batch_attention_masks_tensor,
                token_type_idxs=batch_token_type_idxs_tensor,
                wordpiece_num=batch_wordpiece_num_tensor,
            )

        dataset_cls._benchmark_original_numberize = original_numberize
        dataset_cls._benchmark_original_collate_fn = original_collate_fn
        dataset_cls.numberize = numberize_dynamic
        dataset_cls.collate_fn = collate_fn_dynamic
        dataset_cls._benchmark_dynamic_padding_installed = True
        report["installed"] = True
        report["padding"] = "dynamic_per_batch"
    except Exception as exc:
        report["error"] = str(exc)
    return report


def _install_onnx_tagger_ner_length_bucketing_patch() -> Dict[str, Any]:
    report: Dict[str, Any] = {
        "installed": False,
        "targets": [
            "trankit.iterators.tagger_iterators.TaggerDatasetLive",
            "trankit.iterators.ner_iterators.NERDatasetLive",
        ],
    }

    def sort_key(inst: Any) -> tuple[int, int, int, int]:
        try:
            piece_len = int(len(getattr(inst, "piece_idxs", []) or []))
        except Exception:
            piece_len = 0
        try:
            word_num = int(getattr(inst, "word_num", 0) or 0)
        except Exception:
            word_num = 0
        try:
            sent_index = int(getattr(inst, "sent_index", 0) or 0)
        except Exception:
            sent_index = 0
        word_ids = getattr(inst, "word_ids", []) or []
        try:
            first_word_id = int(word_ids[0]) if word_ids else 0
        except Exception:
            first_word_id = 0
        return piece_len, word_num, sent_index, first_word_id

    def patch_dataset(dataset_cls: Any, label: str) -> Dict[str, Any]:
        row: Dict[str, Any] = {"target": label, "installed": False}
        if getattr(dataset_cls, "_benchmark_length_bucketing_installed", False):
            row["installed"] = True
            row["already_installed"] = True
            return row

        original_numberize = dataset_cls.numberize

        def numberize_bucketed(self: Any, *args: Any, **kwargs: Any) -> Any:
            result = original_numberize(self, *args, **kwargs)
            try:
                self.data = sorted(self.data, key=sort_key)
            except Exception:
                pass
            return result

        dataset_cls._benchmark_original_numberize_for_bucketing = original_numberize
        dataset_cls.numberize = numberize_bucketed
        dataset_cls._benchmark_length_bucketing_installed = True
        row["installed"] = True
        return row

    try:
        from trankit.iterators import ner_iterators, tagger_iterators  # type: ignore

        rows = [
            patch_dataset(tagger_iterators.TaggerDatasetLive, "TaggerDatasetLive"),
            patch_dataset(ner_iterators.NERDatasetLive, "NERDatasetLive"),
        ]
        report["patches"] = rows
        report["installed"] = all(bool(row.get("installed")) for row in rows)
        report["strategy"] = "sort_numberized_examples_by_piece_length"
    except Exception as exc:
        report["error"] = str(exc)
    return report


def _install_onnx_dynamic_batching_patch() -> Dict[str, Any]:
    report: Dict[str, Any] = {
        "installed": False,
        "target": "trankit.pipeline.DataLoader",
        "included_targets": [
            "TokenizeDatasetLive",
            "TaggerDatasetLive",
            "NERDatasetLive",
        ],
        "excluded_targets": [
            "LemmaDataLoader",
            "MWTDataLoader",
        ],
        "seq2seq_dynamic_batching": False,
        "tokenizer_candidates": list(settings.ONNX_DYNAMIC_TOK_BATCH_CANDIDATES),
        "tagger_ner_candidates": list(settings.ONNX_DYNAMIC_TAG_BATCH_CANDIDATES),
        "tokenizer_call_overhead_units": settings.ONNX_DYNAMIC_TOK_CALL_OVERHEAD_UNITS,
        "tagger_ner_call_overhead_units": settings.ONNX_DYNAMIC_TAG_CALL_OVERHEAD_UNITS,
    }

    def get_piece_length(inst: Any) -> int:
        try:
            return int(len(getattr(inst, "piece_idxs", []) or []))
        except Exception:
            return 0

    def stable_sort_key(inst: Any) -> tuple[int, int, int, int, int]:
        piece_len = get_piece_length(inst)
        try:
            word_num = int(
                getattr(inst, "word_num", getattr(inst, "wordpiece_num", 0)) or 0
            )
        except Exception:
            word_num = 0
        try:
            paragraph_index = int(getattr(inst, "paragraph_index", 0) or 0)
        except Exception:
            paragraph_index = 0
        try:
            sent_index = int(getattr(inst, "sent_index", 0) or 0)
        except Exception:
            sent_index = 0
        word_ids = getattr(inst, "word_ids", []) or []
        try:
            first_word_id = int(word_ids[0]) if word_ids else 0
        except Exception:
            first_word_id = 0
        return piece_len, word_num, paragraph_index, sent_index, first_word_id

    def candidate_plan(
        lengths: list[int], batch_size: int, overhead_units: int
    ) -> Dict[str, Any]:
        batches: list[Dict[str, Any]] = []
        padded_units = 0
        real_units = sum(lengths)
        for start in range(0, len(lengths), max(1, batch_size)):
            chunk = lengths[start : start + max(1, batch_size)]
            if not chunk:
                continue
            max_len = max(chunk)
            batch_padded_units = len(chunk) * max_len
            padded_units += batch_padded_units
            batches.append(
                {
                    "items": len(chunk),
                    "max_len": max_len,
                    "padded_units": batch_padded_units,
                    "real_units": sum(chunk),
                    "padding_units": max(0, batch_padded_units - sum(chunk)),
                }
            )
        call_count = len(batches)
        return {
            "batch_size": batch_size,
            "batch_count": call_count,
            "padded_units": padded_units,
            "real_units": real_units,
            "padding_units": max(0, padded_units - real_units),
            "estimated_cost_units": padded_units + call_count * overhead_units,
            "batches": batches[:80],
        }

    def partition_plan(
        lengths: list[int], max_batch_size: int, overhead_units: int
    ) -> Dict[str, Any]:
        clean_lengths = [
            int(length) for length in lengths if isinstance(length, int) and length > 0
        ]
        item_count = len(clean_lengths)
        if not clean_lengths:
            return {
                "algorithm": "dynamic_partition",
                "batch_indices": [],
                "batches": [],
                "batch_count": 0,
                "max_batch_size": int(max_batch_size or 1),
                "padded_units": 0,
                "real_units": 0,
                "padding_units": 0,
                "estimated_cost_units": 0,
            }
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

        ranges: list[tuple[int, int]] = []
        cursor = item_count
        while cursor > 0:
            start = prev[cursor]
            ranges.append((start, cursor))
            cursor = start
        ranges.reverse()

        batches: list[Dict[str, Any]] = []
        batch_indices: list[list[int]] = []
        padded_total = 0
        real_total = prefix[-1]
        for start, end in ranges:
            chunk = clean_lengths[start:end]
            if not chunk:
                continue
            max_len = max(chunk)
            real_units = prefix[end] - prefix[start]
            padded_units = len(chunk) * max_len
            padded_total += padded_units
            batch_indices.append(list(range(start, end)))
            batches.append(
                {
                    "items": len(chunk),
                    "max_len": max_len,
                    "padded_units": padded_units,
                    "real_units": real_units,
                    "padding_units": max(0, padded_units - real_units),
                }
            )

        return {
            "algorithm": "dynamic_partition",
            "batch_indices": batch_indices,
            "batches": batches[:80],
            "batch_count": len(batch_indices),
            "batch_sizes": [len(indexes) for indexes in batch_indices],
            "max_batch_size": max_size,
            "padded_units": padded_total,
            "real_units": real_total,
            "padding_units": max(0, padded_total - real_total),
            "estimated_cost_units": padded_total + len(batch_indices) * overhead_units,
        }

    def choose_batch_size(
        lengths: list[int],
        candidates: list[int],
        requested: Optional[int],
        overhead_units: int,
    ) -> Dict[str, Any]:
        clean_lengths = [
            int(length) for length in lengths if isinstance(length, int) and length > 0
        ]
        if not clean_lengths:
            return {
                "selected_batch_size": int(requested or 1),
                "selected": None,
                "candidates": [],
                "reason": "no lengths",
            }
        max_items = len(clean_lengths)
        candidate_set = {
            int(value) for value in candidates if isinstance(value, int) and value > 0
        }
        if requested:
            candidate_set.add(int(requested))
        candidate_set.add(max_items)
        plans = [
            candidate_plan(clean_lengths, min(max_items, size), overhead_units)
            for size in sorted(candidate_set)
            if size > 0
        ]
        if not plans:
            return {
                "selected_batch_size": int(requested or max_items),
                "selected": None,
                "candidates": [],
                "reason": "no candidates",
            }
        max_batch_size = max(int(row.get("batch_size") or 1) for row in plans)
        selected = partition_plan(clean_lengths, max_batch_size, overhead_units)
        slim_plans = [
            {
                "batch_size": row["batch_size"],
                "batch_count": row["batch_count"],
                "padded_units": row["padded_units"],
                "real_units": row["real_units"],
                "padding_units": row["padding_units"],
                "estimated_cost_units": row["estimated_cost_units"],
            }
            for row in plans
        ]
        return {
            "selected_batch_size": int(
                max(selected.get("batch_sizes") or [max_batch_size])
            ),
            "selected": selected,
            "candidates": slim_plans,
            "reason": "dynamic_partition_min_estimated_cost",
        }

    def dataset_kind(
        dataset: Any, tokenizer_cls: Any, tagger_cls: Any, ner_cls: Any
    ) -> Optional[str]:
        class_name = dataset.__class__.__name__
        if class_name in {"LemmaDataLoader", "MWTDataLoader"}:
            return None
        try:
            if isinstance(dataset, tokenizer_cls):
                return "tokenizer"
            if isinstance(dataset, tagger_cls):
                return "tagger"
            if isinstance(dataset, ner_cls):
                return "ner"
        except Exception:
            return None
        return None

    def get_requested_batch_size(
        args: tuple[Any, ...], kwargs: Dict[str, Any]
    ) -> Optional[int]:
        try:
            if "batch_size" in kwargs and kwargs.get("batch_size") is not None:
                return int(kwargs.get("batch_size"))
            if args:
                return int(args[0])
        except Exception:
            return None
        return None

    def set_batch_size(
        args: tuple[Any, ...], kwargs: Dict[str, Any], batch_size: int
    ) -> tuple[tuple[Any, ...], Dict[str, Any]]:
        clean_kwargs = dict(kwargs)
        if args:
            clean_args = list(args)
            clean_args[0] = batch_size
            return tuple(clean_args), clean_kwargs
        clean_kwargs["batch_size"] = batch_size
        return args, clean_kwargs

    class StaticBatchSampler:
        def __init__(self, batches: list[list[int]]):
            self.batches = [list(batch) for batch in batches if batch]

        def __iter__(self):
            return iter(self.batches)

        def __len__(self) -> int:
            return len(self.batches)

    def set_batch_sampler(
        args: tuple[Any, ...], kwargs: Dict[str, Any], batches: list[list[int]]
    ) -> tuple[tuple[Any, ...], Dict[str, Any]]:
        clean_kwargs = dict(kwargs)
        if args:
            clean_args = list(args)
            clean_args = clean_args[1:]
        else:
            clean_args = []
        clean_kwargs.pop("batch_size", None)
        clean_kwargs.pop("shuffle", None)
        clean_kwargs.pop("sampler", None)
        clean_kwargs.pop("drop_last", None)
        clean_kwargs["batch_sampler"] = StaticBatchSampler(batches)
        return tuple(clean_args), clean_kwargs

    try:
        import trankit.pipeline as trankit_pipeline  # type: ignore
        from trankit.iterators import (  # type: ignore
            ner_iterators,
            tagger_iterators,
            tokenizer_iterators,
        )

        if getattr(trankit_pipeline, "_benchmark_dynamic_batching_installed", False):
            report["installed"] = True
            report["already_installed"] = True
            return report

        original_loader = getattr(trankit_pipeline, "DataLoader", None)
        if original_loader is None:
            raise RuntimeError("trankit.pipeline.DataLoader is unavailable")

        tokenizer_cls = tokenizer_iterators.TokenizeDatasetLive
        tagger_cls = tagger_iterators.TaggerDatasetLive
        ner_cls = ner_iterators.NERDatasetLive
        trankit_pipeline._benchmark_dynamic_batch_events = []

        def dynamic_loader(dataset: Any, *args: Any, **kwargs: Any) -> Any:
            kind = dataset_kind(dataset, tokenizer_cls, tagger_cls, ner_cls)
            if not kind:
                return original_loader(dataset, *args, **kwargs)
            if bool(kwargs.get("shuffle")):
                return original_loader(dataset, *args, **kwargs)
            data = getattr(dataset, "data", None)
            if not isinstance(data, list) or not data:
                return original_loader(dataset, *args, **kwargs)

            try:
                sorted_data = sorted(data, key=stable_sort_key)
                dataset.data = sorted_data
            except Exception:
                sorted_data = data
            lengths = [get_piece_length(inst) for inst in sorted_data]
            requested = get_requested_batch_size(args, kwargs)
            if kind == "tokenizer":
                candidates = list(settings.ONNX_DYNAMIC_TOK_BATCH_CANDIDATES)
                overhead_units = settings.ONNX_DYNAMIC_TOK_CALL_OVERHEAD_UNITS
            else:
                candidates = list(settings.ONNX_DYNAMIC_TAG_BATCH_CANDIDATES)
                overhead_units = settings.ONNX_DYNAMIC_TAG_CALL_OVERHEAD_UNITS
            plan = choose_batch_size(lengths, candidates, requested, overhead_units)
            selected_batch_size = int(plan.get("selected_batch_size") or requested or 1)
            selected_plan = plan.get("selected") if isinstance(plan, dict) else None
            batch_indices = (
                selected_plan.get("batch_indices")
                if isinstance(selected_plan, dict)
                else None
            )
            if isinstance(batch_indices, list) and batch_indices:
                new_args, new_kwargs = set_batch_sampler(args, kwargs, batch_indices)
            else:
                new_args, new_kwargs = set_batch_size(args, kwargs, selected_batch_size)
            event = {
                "kind": kind,
                "item_count": len(lengths),
                "requested_batch_size": requested,
                "selected_batch_size": selected_batch_size,
                "overhead_units": overhead_units,
                "length_min": min(lengths) if lengths else None,
                "length_max": max(lengths) if lengths else None,
                "length_total": sum(lengths),
                "plan": plan,
            }
            try:
                events = getattr(
                    trankit_pipeline, "_benchmark_dynamic_batch_events", None
                )
                if isinstance(events, list):
                    events.append(event)
            except Exception:
                pass
            return original_loader(dataset, *new_args, **new_kwargs)

        trankit_pipeline._benchmark_original_dataloader = original_loader
        trankit_pipeline.DataLoader = dynamic_loader
        trankit_pipeline._benchmark_dynamic_batching_installed = True
        report["installed"] = True
        report["strategy"] = (
            "sort_by_piece_length_and_choose_min_estimated_padding_cost"
        )
    except Exception as exc:
        report["error"] = str(exc)
    return report
