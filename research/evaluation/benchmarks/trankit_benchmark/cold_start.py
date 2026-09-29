"""Trankit benchmark: cold start."""

from __future__ import annotations

import json
import multiprocessing as mp
import os
import queue
import time
import traceback
from contextlib import contextmanager
from typing import Any, Dict

from . import load_probe, memory, settings


def _patch_trankit_pipeline_device(use_gpu: bool) -> None:
    import trankit  # type: ignore

    original_init = trankit.Pipeline.__init__

    def patched_init(self, *args: Any, **kwargs: Any):
        kwargs["gpu"] = use_gpu
        return original_init(self, *args, **kwargs)

    trankit.Pipeline.__init__ = patched_init


def _cold_start_worker_main(
    mode: str,
    device_label: str,
    use_gpu: bool,
    raw_lang: str,
    warmup_text: str,
    result_queue: mp.Queue,
) -> None:
    pid = os.getpid()
    torch_module = None
    stages: list[Dict[str, Any]] = []
    started = time.perf_counter()

    @contextmanager
    def timed_stage(name: str, **metadata: Any):
        memory._sync_cuda(torch_module, use_gpu)
        rss_before = memory.current_rss_bytes()
        gpu_before = memory._gpu_snapshot(torch_module)
        stage_started = time.perf_counter()
        ok = True
        error = ""
        try:
            yield
        except Exception as exc:
            ok = False
            error = str(exc)
            raise
        finally:
            memory._sync_cuda(torch_module, use_gpu)
            rss_after = memory.current_rss_bytes()
            gpu_after = memory._gpu_snapshot(torch_module)
            row: Dict[str, Any] = {
                "name": name,
                "ok": ok,
                "elapsed_seconds": time.perf_counter() - stage_started,
                "rss_before_bytes": rss_before,
                "rss_after_bytes": rss_after,
                "rss_delta_bytes": memory._bytes_delta(rss_after, rss_before),
                "gpu_before": gpu_before,
                "gpu_after": gpu_after,
                "gpu_delta": memory._gpu_delta(gpu_after, gpu_before),
            }
            if metadata:
                row["metadata"] = metadata
            if error:
                row["error"] = error
            stages.append(row)

    try:
        rss_process_start = memory.current_rss_bytes()
        gpu_process_start = memory._gpu_snapshot(None)

        with timed_stage("import_torch"):
            import torch  # type: ignore

            torch_module = torch
            if use_gpu and torch_module.cuda.is_available():
                torch_module.cuda.empty_cache()
                torch_module.cuda.reset_peak_memory_stats()
                torch_module.cuda.synchronize()
            gpu_process_start = memory._gpu_snapshot(torch_module)

        with timed_stage("import_trankit_and_force_device"):
            _patch_trankit_pipeline_device(use_gpu)

        with timed_stage("import_language_registry"):
            import language_registry as lr

        resolved_lang = (
            lr.resolve_lang_code(raw_lang) or str(raw_lang or "").strip().lower()
        )
        if not resolved_lang or resolved_lang not in lr.LANGUAGE_REGISTRY:
            raise ValueError(f"Unsupported language: {raw_lang}")

        pipeline_obj = None
        loaded_description = ""
        if mode == "xlm_only":
            with timed_stage("select_cache_dir_for_xlm_only", lang=resolved_lang):
                info = lr.LANGUAGE_REGISTRY[resolved_lang]
                cache_dir = info.get("trankit_cache_dir") or os.path.join(
                    "cache", "trankit"
                )

            with timed_stage(
                "load_shared_xlm_only",
                lang=resolved_lang,
                has_custom_cache=bool(info.get("trankit_cache_dir")),
            ):
                from trankit.adapter_transformers import (
                    XLMRobertaTokenizer,  # type: ignore
                )
                from trankit.config import config as master_config  # type: ignore
                from trankit.models.base_models import (
                    Multilingual_Embedding,  # type: ignore
                )

                master_config.embedding_name = "xlm-roberta-base"
                master_config._cache_dir = cache_dir
                master_config.device = torch_module.device(
                    "cuda" if use_gpu and torch_module.cuda.is_available() else "cpu"
                )
                master_config.wordpiece_splitter = XLMRobertaTokenizer.from_pretrained(
                    master_config.embedding_name,
                    cache_dir=os.path.join(
                        master_config._cache_dir, master_config.embedding_name
                    ),
                )
                pipeline_obj = Multilingual_Embedding(master_config)
                pipeline_obj.to(master_config.device)
                if use_gpu and torch_module.cuda.is_available():
                    pipeline_obj.half()
                pipeline_obj.eval()
            loaded_description = "Shared XLM-R tokenizer/model only. No Trankit language modules are loaded."
        elif mode == "full":
            loaded_description = "Full all-language app Trankit pipeline via language_registry.init_trankit()."
            with timed_stage("load_full_app_trankit_pipeline"):
                lr.init_trankit()
            pipeline_obj = getattr(lr, "_trankit_pipeline", None)
        elif mode == "lang_modules":
            loaded_description = "Selected language-specific Trankit modules only. Shared XLM-R is not loaded."
            with timed_stage("register_selected_language_metadata", lang=resolved_lang):
                info = load_probe._register_single_language_for_probe(lr, resolved_lang)

            with timed_stage("load_selected_language_modules", lang=resolved_lang):
                from collections import defaultdict

                from trankit.config import config as master_config  # type: ignore
                from trankit.models.classifiers import (  # type: ignore
                    NERClassifier,
                    PosDepClassifier,
                    TokenizerClassifier,
                )
                from trankit.models.lemma_model import LemmaWrapper  # type: ignore
                from trankit.models.mwt_model import MWTWrapper  # type: ignore
                from trankit.utils.conll import (  # type: ignore
                    DEPREL,
                    FEATS,
                    UPOS,
                    XPOS,
                )
                from trankit.utils.tbinfo import (  # type: ignore
                    lang2treebank,
                    langwithner,
                    tbname2training_id,
                    treebank2lang,
                )

                trankit_name = info["trankit_name"]
                treebank_name = lang2treebank[trankit_name]
                cache_dir = info.get("trankit_cache_dir") or os.path.join(
                    "cache", "trankit"
                )
                model_lang = trankit_name
                vocab_lang = treebank2lang.get(treebank_name) or trankit_name
                use_gpu_actual = bool(use_gpu and torch_module.cuda.is_available())

                master_config.embedding_name = "xlm-roberta-base"
                master_config._cache_dir = cache_dir
                master_config.device = torch_module.device(
                    "cuda" if use_gpu_actual else "cpu"
                )
                master_config.training = False
                master_config.vocabs = {}
                master_config.ner_vocabs = {}
                master_config.itos = defaultdict(dict)

                vocab_path = os.path.join(
                    master_config._cache_dir,
                    master_config.embedding_name,
                    model_lang,
                    f"{model_lang}.vocabs.json",
                )
                if not os.path.exists(vocab_path):
                    vocab_path = os.path.join(
                        master_config._cache_dir,
                        master_config.embedding_name,
                        vocab_lang,
                        f"{vocab_lang}.vocabs.json",
                    )
                with open(vocab_path, encoding="utf-8") as f:
                    vocabs = json.load(f)
                master_config.vocabs[treebank_name] = vocabs
                master_config.itos[trankit_name][UPOS] = {
                    v: k for k, v in vocabs[UPOS].items()
                }
                master_config.itos[trankit_name][XPOS] = {
                    v: k for k, v in vocabs[XPOS].items()
                }
                master_config.itos[trankit_name][FEATS] = {
                    v: k for k, v in vocabs[FEATS].items()
                }
                master_config.itos[trankit_name][DEPREL] = {
                    v: k for k, v in vocabs[DEPREL].items()
                }

                if trankit_name in langwithner:
                    ner_vocab_path = os.path.join(
                        master_config._cache_dir,
                        master_config.embedding_name,
                        trankit_name,
                        f"{trankit_name}.ner-vocab.json",
                    )
                    with open(ner_vocab_path, encoding="utf-8") as f:
                        master_config.ner_vocabs[trankit_name] = json.load(f)

                tokenizer = TokenizerClassifier(
                    master_config, treebank_name=treebank_name
                )
                tokenizer.to(master_config.device)
                if use_gpu_actual:
                    tokenizer.half()
                tokenizer.eval()

                tagger = PosDepClassifier(master_config, treebank_name=treebank_name)
                tagger.to(master_config.device)
                if use_gpu_actual:
                    tagger.half()
                tagger.eval()

                mwt_model = None
                if tbname2training_id[treebank_name] % 2 == 1:
                    mwt_model = MWTWrapper(
                        master_config,
                        treebank_name=treebank_name,
                        use_gpu=use_gpu_actual,
                    )

                lemma_model = LemmaWrapper(
                    master_config, treebank_name=treebank_name, use_gpu=use_gpu_actual
                )

                ner_model = None
                if trankit_name in langwithner:
                    ner_model = NERClassifier(master_config, trankit_name)
                    ner_model.to(master_config.device)
                    if use_gpu_actual:
                        ner_model.half()
                    ner_model.eval()

                pipeline_obj = {
                    "tokenizer": tokenizer,
                    "tagger": tagger,
                    "mwt": mwt_model,
                    "lemma": lemma_model,
                    "ner": ner_model,
                    "trankit_name": trankit_name,
                    "device": str(master_config.device),
                    "use_gpu": use_gpu_actual,
                }
        else:
            raise ValueError(f"Unsupported cold-start probe mode: {mode}")

        first_inference_doc = None
        if warmup_text.strip() and mode != "xlm_only" and mode != "lang_modules":
            if mode == "full":
                with timed_stage(
                    "first_inference_after_cold_load",
                    lang=resolved_lang,
                    chars=len(warmup_text),
                ):
                    first_inference_doc = lr.run_trankit(warmup_text, resolved_lang)

        memory._sync_cuda(torch_module, use_gpu)
        memory._force_gc()
        rss_after = memory.current_rss_bytes()
        gpu_after = memory._gpu_snapshot(torch_module)
        actual_device = ""
        actual_use_gpu = None
        added_langs = []
        if mode == "xlm_only" and pipeline_obj is not None:
            actual_device = str(
                getattr(getattr(pipeline_obj, "config", None), "device", "")
            )
            actual_use_gpu = "cuda" in actual_device
        elif mode == "lang_modules" and isinstance(pipeline_obj, dict):
            actual_device = str(pipeline_obj.get("device") or "")
            actual_use_gpu = bool(pipeline_obj.get("use_gpu"))
            added_langs = [str(pipeline_obj.get("trankit_name") or "")]
        elif pipeline_obj is not None:
            try:
                actual_device = str(pipeline_obj._config.device)
                actual_use_gpu = bool(pipeline_obj._use_gpu)
                added_langs = list(getattr(pipeline_obj, "added_langs", []) or [])
            except Exception:
                pass

        result_queue.put(
            {
                "ok": True,
                "mode": mode,
                "device": device_label,
                "requested_gpu": use_gpu,
                "pid": pid,
                "lang": resolved_lang,
                "loaded_description": loaded_description,
                "actual_device": actual_device,
                "actual_use_gpu": actual_use_gpu,
                "added_lang_count": len(added_langs),
                "added_langs": added_langs,
                "total_elapsed_seconds": time.perf_counter() - started,
                "rss_process_start_bytes": rss_process_start,
                "rss_after_load_bytes": rss_after,
                "rss_total_delta_bytes": memory._bytes_delta(
                    rss_after, rss_process_start
                ),
                "gpu_process_start": gpu_process_start,
                "gpu_after_load": gpu_after,
                "gpu_total_delta": memory._gpu_delta(gpu_after, gpu_process_start),
                "stages": stages,
                "warmup_inference_ran": bool(warmup_text.strip()),
                "warmup_annotation": first_inference_doc,
            }
        )
    except Exception as exc:
        memory._sync_cuda(torch_module, use_gpu)
        memory._force_gc()
        result_queue.put(
            {
                "ok": False,
                "mode": mode,
                "device": device_label,
                "requested_gpu": use_gpu,
                "pid": pid,
                "total_elapsed_seconds": time.perf_counter() - started,
                "rss_after_load_bytes": memory.current_rss_bytes(),
                "gpu_after_load": memory._gpu_snapshot(torch_module),
                "stages": stages,
                "error": str(exc),
                "traceback": traceback.format_exc(),
            }
        )


def run_cold_start_probe_process(
    mode: str,
    device_label: str,
    use_gpu: bool,
    raw_lang: str,
    warmup_text: str,
) -> Dict[str, Any]:
    ctx = mp.get_context("spawn")
    result_queue = ctx.Queue()
    started = time.perf_counter()
    process = ctx.Process(
        target=_cold_start_worker_main,
        args=(mode, device_label, use_gpu, raw_lang, warmup_text, result_queue),
        daemon=False,
    )
    process.start()
    try:
        result = result_queue.get(timeout=settings.LOAD_PROBE_TIMEOUT_SECONDS)
    except queue.Empty:
        result = {
            "ok": False,
            "mode": mode,
            "device": device_label,
            "requested_gpu": use_gpu,
            "pid": process.pid,
            "error": "cold-start probe timed out",
        }
    finally:
        process.join(timeout=5)
        if process.is_alive():
            process.terminate()
    if isinstance(result, dict):
        result["probe_process_wall_seconds"] = time.perf_counter() - started
        result["exitcode"] = process.exitcode
    return result
