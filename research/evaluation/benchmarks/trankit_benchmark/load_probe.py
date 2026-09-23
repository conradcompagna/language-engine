"""Trankit benchmark: load probe."""

from __future__ import annotations

import multiprocessing as mp
import os
import queue
import time
import traceback
from contextlib import contextmanager
from typing import Any, Dict, Optional

from . import memory, settings


class StageRecorder:
    def __init__(self, torch_module: Any, use_gpu: bool):
        self.torch = torch_module
        self.use_gpu = use_gpu
        self.stages: list[Dict[str, Any]] = []

    @contextmanager
    def timed(self, name: str, **metadata: Any):
        memory._sync_cuda(self.torch, self.use_gpu)
        rss_before = memory.current_rss_bytes()
        gpu_before = memory._gpu_snapshot(self.torch)
        started = time.perf_counter()
        ok = True
        error = ""
        try:
            yield
        except Exception as exc:
            ok = False
            error = str(exc)
            raise
        finally:
            memory._sync_cuda(self.torch, self.use_gpu)
            finished = time.perf_counter()
            rss_after = memory.current_rss_bytes()
            gpu_after = memory._gpu_snapshot(self.torch)
            row: Dict[str, Any] = {
                "name": name,
                "ok": ok,
                "elapsed_seconds": finished - started,
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
            self.stages.append(row)


def _install_load_probe_instrumentation(use_gpu: bool, recorder: StageRecorder) -> None:
    import trankit  # type: ignore
    import trankit.pipeline as trankit_pipeline  # type: ignore

    real_pipeline = trankit.Pipeline
    real_download = trankit_pipeline.download

    def timed_download(*args: Any, **kwargs: Any):
        language = str(kwargs.get("language") or (args[1] if len(args) > 1 else ""))
        with recorder.timed("download_or_check_saved_model", language=language):
            return real_download(*args, **kwargs)

    trankit_pipeline.download = timed_download

    def timed_module_class(stage_prefix: str, original_class: Any):
        class TimedModule(original_class):  # type: ignore[misc, valid-type]
            def __init__(self, *args: Any, **kwargs: Any):
                with recorder.timed(f"{stage_prefix}.__init__"):
                    super().__init__(*args, **kwargs)

            def to(self, *args: Any, **kwargs: Any):
                with recorder.timed(f"{stage_prefix}.to_device"):
                    return super().to(*args, **kwargs)

            def half(self, *args: Any, **kwargs: Any):
                with recorder.timed(f"{stage_prefix}.half"):
                    return super().half(*args, **kwargs)

        return TimedModule

    def timed_wrapper_class(stage_prefix: str, original_class: Any):
        class TimedWrapper(original_class):  # type: ignore[misc, valid-type]
            def __init__(self, *args: Any, **kwargs: Any):
                with recorder.timed(f"{stage_prefix}.__init__"):
                    super().__init__(*args, **kwargs)

        return TimedWrapper

    trankit_pipeline.Multilingual_Embedding = timed_module_class(
        "shared_xlm_roberta_embedding",
        trankit_pipeline.Multilingual_Embedding,
    )
    trankit_pipeline.TokenizerClassifier = timed_module_class(
        "language_tokenizer_classifier",
        trankit_pipeline.TokenizerClassifier,
    )
    trankit_pipeline.PosDepClassifier = timed_module_class(
        "language_posdep_classifier",
        trankit_pipeline.PosDepClassifier,
    )
    trankit_pipeline.NERClassifier = timed_module_class(
        "language_ner_classifier",
        trankit_pipeline.NERClassifier,
    )
    trankit_pipeline.MWTWrapper = timed_wrapper_class(
        "language_mwt_wrapper",
        trankit_pipeline.MWTWrapper,
    )
    trankit_pipeline.LemmaWrapper = timed_wrapper_class(
        "language_lemma_wrapper",
        trankit_pipeline.LemmaWrapper,
    )

    original_pipeline_init = real_pipeline.__init__
    original_setup_config = real_pipeline._setup_config
    original_load_vocabs = real_pipeline._load_vocabs
    original_add = real_pipeline.add

    def forced_timed_pipeline_init(self, *args: Any, **kwargs: Any):
        kwargs["gpu"] = use_gpu
        with recorder.timed("pipeline_constructor_total"):
            return original_pipeline_init(self, *args, **kwargs)

    def timed_setup_config(self, lang: str):
        with recorder.timed("pipeline_setup_config", lang=lang):
            return original_setup_config(self, lang)

    def timed_load_vocabs(self):
        with recorder.timed("pipeline_load_vocabs"):
            return original_load_vocabs(self)

    def timed_add(self, lang: str):
        with recorder.timed("pipeline_add_language_total", lang=lang):
            return original_add(self, lang)

    real_pipeline.__init__ = forced_timed_pipeline_init
    real_pipeline._setup_config = timed_setup_config
    real_pipeline._load_vocabs = timed_load_vocabs
    real_pipeline.add = timed_add
    trankit.Pipeline = real_pipeline
    trankit_pipeline.Pipeline = real_pipeline


def _register_single_language_for_probe(lr: Any, lang_code: str) -> Dict[str, Any]:
    from pathlib import Path

    from trankit.models.lemma_model import LemmaWrapper
    from trankit.utils.tbinfo import (
        lang2treebank,
        langwithner,
        supported_langs,
        tbname2max_input_length,
        tbname2training_id,
        treebank2lang,
    )

    info = lr.LANGUAGE_REGISTRY[lang_code]
    name = info["trankit_name"]
    treebank = info.get("trankit_treebank")

    if treebank and name and name not in supported_langs:
        supported_langs.add(name) if isinstance(
            supported_langs, set
        ) else supported_langs.append(name)
    if treebank and name:
        lang2treebank[name] = treebank
        if info.get("has_ner", False) and name not in langwithner:
            langwithner.add(name) if isinstance(
                langwithner, set
            ) else langwithner.append(name)
        if treebank not in treebank2lang:
            treebank2lang[treebank] = name
        if treebank not in tbname2training_id:
            tbname2training_id[treebank] = 1 if info.get("has_mwt", False) else 0
        tbname2max_input_length[treebank] = 512

    if lang_code == "ar" and treebank:
        tbname2training_id[treebank] = 1

    if info.get("identity_lemma") and treebank:
        original_init = LemmaWrapper.__init__
        original_predict = LemmaWrapper.predict

        def patched_lemma_init(
            self, config: Any, treebank_name: str, use_gpu: bool, evaluate: bool = True
        ):
            self._identity_lemma_runtime = False
            if evaluate and treebank_name == treebank:
                language = treebank2lang[treebank_name]
                model_path = (
                    Path(config._cache_dir)
                    / config.embedding_name
                    / language
                    / f"{language}_lemmatizer.pt"
                )
                if model_path.exists():
                    return original_init(self, config, treebank_name, use_gpu, evaluate)
                from trankit.models.lemma_model import get_identity_lemma_model

                self.config = config
                self.treebank_name = treebank_name
                self.args = get_identity_lemma_model()
                self._identity_lemma_runtime = True
                print("Loading lemmatizer for {}".format(treebank2lang[treebank_name]))
                return
            return original_init(self, config, treebank_name, use_gpu, evaluate)

        def patched_lemma_predict(self, tagged_doc: Any, obmit_tag: Any):
            if getattr(self, "_identity_lemma_runtime", False):
                from trankit.models.lemma_model import set_lemma
                from trankit.utils.conll import ID, TEXT, TOKENS

                preds = [
                    t[TEXT]
                    for sentence in tagged_doc
                    for t in sentence[TOKENS]
                    if type(t[ID]) == int or len(t[ID]) == 1
                ]
                return set_lemma(tagged_doc, preds, obmit_tag)
            return original_predict(self, tagged_doc, obmit_tag)

        LemmaWrapper.__init__ = patched_lemma_init
        LemmaWrapper.predict = patched_lemma_predict

    return info


def _load_probe_worker_main(
    mode: str,
    device_label: str,
    use_gpu: bool,
    raw_lang: str,
    result_queue: mp.Queue,
) -> None:
    torch_module = None
    pid = os.getpid()
    total_started = time.perf_counter()
    rss_process_start = memory.current_rss_bytes()
    recorder: Optional[StageRecorder] = None
    try:
        memory._force_gc()

        import torch  # type: ignore

        torch_module = torch
        if use_gpu and torch_module.cuda.is_available():
            torch_module.cuda.empty_cache()
            torch_module.cuda.reset_peak_memory_stats()
            torch_module.cuda.synchronize()

        recorder = StageRecorder(torch_module, use_gpu)
        with recorder.timed("install_trankit_load_instrumentation"):
            _install_load_probe_instrumentation(use_gpu, recorder)

        with recorder.timed("import_language_registry"):
            import language_registry as lr

        resolved_lang = (
            lr.resolve_lang_code(raw_lang) or str(raw_lang or "").strip().lower()
        )
        if not resolved_lang or resolved_lang not in lr.LANGUAGE_REGISTRY:
            raise ValueError(f"Unsupported language: {raw_lang}")

        pipeline_obj = None
        if mode == "full":
            with recorder.timed("full_language_registry_init_trankit_total"):
                lr.init_trankit()
            pipeline_obj = getattr(lr, "_trankit_pipeline", None)
        elif mode == "single_lang":
            with recorder.timed("single_language_metadata_patch", lang=resolved_lang):
                info = _register_single_language_for_probe(lr, resolved_lang)
            from trankit import Pipeline  # type: ignore

            trankit_name = info["trankit_name"]
            cache_dir = info.get("trankit_cache_dir")
            with recorder.timed(
                "single_language_pipeline_load_total",
                lang=resolved_lang,
                trankit_name=trankit_name,
                has_custom_cache=bool(cache_dir),
            ):
                if cache_dir:
                    pipeline_obj = Pipeline(lang=trankit_name, cache_dir=cache_dir)
                else:
                    pipeline_obj = Pipeline(trankit_name)
        else:
            raise ValueError(f"Unsupported load probe mode: {mode}")

        memory._sync_cuda(torch_module, use_gpu)
        memory._force_gc()
        rss_after = memory.current_rss_bytes()
        gpu_after = memory._gpu_snapshot(torch_module)
        actual_device = ""
        actual_use_gpu = None
        added_langs = []
        if pipeline_obj is not None:
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
                "actual_device": actual_device,
                "actual_use_gpu": actual_use_gpu,
                "added_langs": added_langs,
                "total_elapsed_seconds": time.perf_counter() - total_started,
                "rss_process_start_bytes": rss_process_start,
                "rss_after_load_bytes": rss_after,
                "rss_total_delta_bytes": memory._bytes_delta(
                    rss_after, rss_process_start
                ),
                "gpu_after_load": gpu_after,
                "stages": recorder.stages,
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
                "total_elapsed_seconds": time.perf_counter() - total_started,
                "rss_process_start_bytes": rss_process_start,
                "rss_after_load_bytes": memory.current_rss_bytes(),
                "gpu_after_load": memory._gpu_snapshot(torch_module),
                "stages": recorder.stages if recorder is not None else [],
                "error": str(exc),
                "traceback": traceback.format_exc(),
            }
        )


def run_load_probe_process(
    mode: str, device_label: str, use_gpu: bool, raw_lang: str
) -> Dict[str, Any]:
    ctx = mp.get_context("spawn")
    result_queue = ctx.Queue()
    started = time.perf_counter()
    process = ctx.Process(
        target=_load_probe_worker_main,
        args=(mode, device_label, use_gpu, raw_lang, result_queue),
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
            "error": "load probe timed out",
        }
    finally:
        process.join(timeout=5)
        if process.is_alive():
            process.terminate()
    if isinstance(result, dict):
        result["probe_process_wall_seconds"] = time.perf_counter() - started
        result["exitcode"] = process.exitcode
    return result
