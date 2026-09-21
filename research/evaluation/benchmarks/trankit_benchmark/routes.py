"""Trankit benchmark: routes."""

from __future__ import annotations

import time
import uuid
from typing import Any

from flask import Flask, jsonify, render_template, request

from . import cold_start, comparison, cpu_selection_cache, state

app = Flask(__name__)


def _load_language_options() -> list[dict[str, str]]:
    try:
        import language_registry as lr

        out = []
        for code, info in sorted(lr.LANGUAGE_REGISTRY.items()):
            label = str(info.get("aliases", [code])[0] if info.get("aliases") else code)
            out.append({"code": code, "label": f"{code} - {label}"})
        return out
    except Exception:
        return [
            {"code": "zh", "label": "zh"},
            {"code": "ja", "label": "ja"},
            {"code": "ko", "label": "ko"},
            {"code": "ar", "label": "ar"},
            {"code": "sa", "label": "sa"},
        ]


@app.route("/")
def index() -> str:
    language_options = _load_language_options()
    options_html = "\n".join(
        f'<option value="{item["code"]}">{item["label"]}</option>'
        for item in language_options
    )
    return render_template("index.html", language_options_html=options_html)


@app.route("/api/status")
def api_status() -> Any:
    if not state.workers:
        return jsonify(
            {
                "gpu": {"state": "not_started"},
                "gpu_opt": {"state": "not_started"},
                "cpu_opt": {"state": "not_started"},
                "onnx_cpu": {"state": "not_started"},
            }
        )
    for worker in state.workers.values():
        worker.drain()
    status = {
        "gpu": {"state": "not_started"},
        "gpu_opt": {"state": "not_started"},
        "cpu_opt": {"state": "not_started"},
        "onnx_cpu": {"state": "not_started"},
    }
    status.update({name: worker.status for name, worker in state.workers.items()})
    if state.cpu_opt_selection is not None:
        status["cpu_opt_selection"] = state.cpu_opt_selection
    return jsonify(status)


@app.route("/api/analyze", methods=["POST"])
def api_analyze() -> Any:
    if not {"cpu", "gpu"}.issubset(state.workers):
        return jsonify({"ok": False, "error": "workers are not started"}), 503
    data = request.get_json(silent=True) or {}
    text = str(data.get("text") or "")
    if not text.strip():
        return jsonify({"ok": False, "error": "empty text"}), 400

    request_id = uuid.uuid4().hex
    command = {
        "type": "analyze",
        "request_id": request_id,
        "text": text,
        "lang": str(data.get("lang") or "zh"),
        "trankit_override": str(data.get("trankit_override") or ""),
        "manual_sentence_segmentation": bool(data.get("manual_sentence_segmentation")),
        "strip_punctuation": bool(data.get("strip_punctuation")),
    }

    cpu_result = state.workers["cpu"].analyze(command)
    gpu_result = state.workers["gpu"].analyze(command)
    for worker in state.workers.values():
        worker.drain()

    return jsonify(
        {
            "ok": bool(cpu_result.get("ok") and gpu_result.get("ok")),
            "request_id": request_id,
            "text_chars": len(text),
            "load": {
                "cpu": state.workers["cpu"].status.get("load_metrics"),
                "gpu": state.workers["gpu"].status.get("load_metrics"),
            },
            "devices": {
                "cpu": cpu_result,
                "gpu": gpu_result,
            },
        }
    )


@app.route("/api/analyze_cpu_opt_vs_gpu", methods=["POST"])
def api_analyze_cpu_opt_vs_gpu() -> Any:

    if (
        not {"cpu_opt", "gpu"}.issubset(state.workers)
        or state.cpu_opt_selection is None
    ):
        return jsonify(
            {"ok": False, "error": "optimized CPU and GPU workers are not started"}
        ), 503
    for worker in state.workers.values():
        worker.drain()
    cpu_status = state.workers["cpu_opt"].status
    gpu_status = state.workers["gpu"].status
    if cpu_status.get("state") != "ready" or gpu_status.get("state") != "ready":
        status_error = ""
        if cpu_status.get("state") == "error":
            status_error = str(
                cpu_status.get("error") or "optimized CPU worker is in error state"
            )
        elif gpu_status.get("state") == "error":
            status_error = str(
                gpu_status.get("error") or "GPU worker is in error state"
            )
        else:
            status_error = "workers are still loading"
        return jsonify(
            {
                "ok": False,
                "error": status_error,
                "load": {
                    "cpu_opt": cpu_status.get("load_metrics"),
                    "gpu": gpu_status.get("load_metrics"),
                },
                "worker_status": {
                    "cpu_opt": cpu_status,
                    "gpu": gpu_status,
                },
                "cpu_opt_selection": state.cpu_opt_selection,
                "comparison": {
                    "cpu_opt_seconds": None,
                    "gpu_seconds": None,
                    "cpu_opt_vs_gpu_ratio": None,
                    "output_match": False,
                    "cpu_opt_fingerprint": None,
                    "gpu_fingerprint": None,
                },
                "discrepancies": {
                    "match": False,
                    "diff_count": None,
                    "truncated": False,
                    "text": status_error,
                },
                "devices": {
                    "cpu_opt": {
                        "type": "result",
                        "device": "cpu_opt",
                        "ok": False,
                        "error": status_error,
                        "status": cpu_status,
                    },
                    "gpu": {
                        "type": "result",
                        "device": "gpu",
                        "ok": False,
                        "error": status_error,
                        "status": gpu_status,
                    },
                },
            }
        ), 503
    data = request.get_json(silent=True) or {}
    text = str(data.get("text") or "")
    if not text.strip():
        return jsonify({"ok": False, "error": "empty text"}), 400

    request_id = uuid.uuid4().hex
    command = {
        "type": "analyze",
        "request_id": request_id,
        "text": text,
        "lang": str(data.get("lang") or "zh"),
        "trankit_override": str(data.get("trankit_override") or ""),
        "manual_sentence_segmentation": bool(data.get("manual_sentence_segmentation")),
        "strip_punctuation": bool(data.get("strip_punctuation")),
    }

    cpu_opt_result = state.workers["cpu_opt"].analyze(command)
    gpu_result = state.workers["gpu"].analyze(command)
    for worker in state.workers.values():
        worker.drain()
    cached_selection = cpu_selection_cache._read_cpu_opt_selection_cache()
    if cached_selection is not None:
        state.cpu_opt_selection = cached_selection
    selection = state.cpu_opt_selection

    cpu_metrics = (
        cpu_opt_result.get("metrics") if isinstance(cpu_opt_result, dict) else None
    )
    gpu_metrics = gpu_result.get("metrics") if isinstance(gpu_result, dict) else None
    cpu_seconds = (
        cpu_metrics.get("elapsed_seconds") if isinstance(cpu_metrics, dict) else None
    )
    gpu_seconds = (
        gpu_metrics.get("elapsed_seconds") if isinstance(gpu_metrics, dict) else None
    )
    ratio = None
    if (
        isinstance(cpu_seconds, (int, float))
        and isinstance(gpu_seconds, (int, float))
        and gpu_seconds
    ):
        ratio = cpu_seconds / gpu_seconds
    cpu_fingerprint = (
        cpu_metrics.get("output_fingerprint") if isinstance(cpu_metrics, dict) else None
    )
    gpu_fingerprint = (
        gpu_metrics.get("output_fingerprint") if isinstance(gpu_metrics, dict) else None
    )
    if cpu_opt_result.get("ok") and gpu_result.get("ok"):
        discrepancies = comparison._annotation_discrepancy_report(
            cpu_opt_result.get("annotations"),
            gpu_result.get("annotations"),
        )
    else:
        discrepancies = {
            "match": False,
            "diff_count": None,
            "truncated": False,
            "text": "Comparison unavailable because one output failed.",
        }

    return jsonify(
        {
            "ok": bool(cpu_opt_result.get("ok") and gpu_result.get("ok")),
            "request_id": request_id,
            "text_chars": len(text),
            "load": {
                "cpu_opt": state.workers["cpu_opt"].status.get("load_metrics"),
                "gpu": state.workers["gpu"].status.get("load_metrics"),
            },
            "cpu_opt_selection": selection,
            "worker_status": {
                "cpu_opt": state.workers["cpu_opt"].status,
                "gpu": state.workers["gpu"].status,
            },
            "comparison": {
                "cpu_opt_seconds": cpu_seconds,
                "gpu_seconds": gpu_seconds,
                "cpu_opt_vs_gpu_ratio": ratio,
                "output_match": bool(
                    cpu_fingerprint and cpu_fingerprint == gpu_fingerprint
                ),
                "cpu_opt_fingerprint": cpu_fingerprint,
                "gpu_fingerprint": gpu_fingerprint,
            },
            "discrepancies": discrepancies,
            "devices": {
                "cpu_opt": cpu_opt_result,
                "gpu": gpu_result,
            },
        }
    )


@app.route("/api/analyze_gpu_opt_vs_gpu", methods=["POST"])
def api_analyze_gpu_opt_vs_gpu() -> Any:
    if not {"gpu_opt", "gpu"}.issubset(state.workers):
        return jsonify(
            {
                "ok": False,
                "error": "optimized GPU and regular GPU workers are not started",
            }
        ), 503
    for worker in state.workers.values():
        worker.drain()
    gpu_opt_status = state.workers["gpu_opt"].status
    gpu_status = state.workers["gpu"].status
    if gpu_opt_status.get("state") != "ready" or gpu_status.get("state") != "ready":
        if gpu_opt_status.get("state") == "error":
            status_error = str(
                gpu_opt_status.get("error") or "optimized GPU worker is in error state"
            )
        elif gpu_status.get("state") == "error":
            status_error = str(
                gpu_status.get("error") or "regular GPU worker is in error state"
            )
        else:
            status_error = "workers are still loading"
        return jsonify(
            {
                "ok": False,
                "error": status_error,
                "load": {
                    "gpu_opt": gpu_opt_status.get("load_metrics"),
                    "gpu": gpu_status.get("load_metrics"),
                },
                "worker_status": {
                    "gpu_opt": gpu_opt_status,
                    "gpu": gpu_status,
                },
                "comparison": {
                    "gpu_opt_seconds": None,
                    "gpu_seconds": None,
                    "gpu_opt_speedup_ratio": None,
                    "output_match": False,
                    "gpu_opt_fingerprint": None,
                    "gpu_fingerprint": None,
                },
                "discrepancies": {
                    "match": False,
                    "diff_count": None,
                    "truncated": False,
                    "text": status_error,
                },
                "devices": {
                    "gpu_opt": {
                        "type": "result",
                        "device": "gpu_opt",
                        "ok": False,
                        "error": status_error,
                        "status": gpu_opt_status,
                    },
                    "gpu": {
                        "type": "result",
                        "device": "gpu",
                        "ok": False,
                        "error": status_error,
                        "status": gpu_status,
                    },
                },
            }
        ), 503

    data = request.get_json(silent=True) or {}
    text = str(data.get("text") or "")
    if not text.strip():
        return jsonify({"ok": False, "error": "empty text"}), 400

    request_id = uuid.uuid4().hex
    command = {
        "type": "analyze",
        "request_id": request_id,
        "text": text,
        "lang": str(data.get("lang") or "zh"),
        "trankit_override": str(data.get("trankit_override") or ""),
        "manual_sentence_segmentation": bool(data.get("manual_sentence_segmentation")),
        "strip_punctuation": bool(data.get("strip_punctuation")),
    }

    gpu_opt_result = state.workers["gpu_opt"].analyze(command)
    gpu_result = state.workers["gpu"].analyze(command)
    for worker in state.workers.values():
        worker.drain()

    gpu_opt_metrics = (
        gpu_opt_result.get("metrics") if isinstance(gpu_opt_result, dict) else None
    )
    gpu_metrics = gpu_result.get("metrics") if isinstance(gpu_result, dict) else None
    gpu_opt_seconds = (
        gpu_opt_metrics.get("elapsed_seconds")
        if isinstance(gpu_opt_metrics, dict)
        else None
    )
    gpu_seconds = (
        gpu_metrics.get("elapsed_seconds") if isinstance(gpu_metrics, dict) else None
    )
    speedup = None
    if (
        isinstance(gpu_opt_seconds, (int, float))
        and isinstance(gpu_seconds, (int, float))
        and gpu_opt_seconds
    ):
        speedup = gpu_seconds / gpu_opt_seconds
    gpu_opt_fingerprint = (
        gpu_opt_metrics.get("output_fingerprint")
        if isinstance(gpu_opt_metrics, dict)
        else None
    )
    gpu_fingerprint = (
        gpu_metrics.get("output_fingerprint") if isinstance(gpu_metrics, dict) else None
    )
    if gpu_opt_result.get("ok") and gpu_result.get("ok"):
        discrepancies = comparison._annotation_discrepancy_report(
            gpu_opt_result.get("annotations"),
            gpu_result.get("annotations"),
        )
    else:
        discrepancies = {
            "match": False,
            "diff_count": None,
            "truncated": False,
            "text": "Comparison unavailable because one output failed.",
        }

    return jsonify(
        {
            "ok": bool(gpu_opt_result.get("ok") and gpu_result.get("ok")),
            "request_id": request_id,
            "text_chars": len(text),
            "load": {
                "gpu_opt": state.workers["gpu_opt"].status.get("load_metrics"),
                "gpu": state.workers["gpu"].status.get("load_metrics"),
            },
            "worker_status": {
                "gpu_opt": state.workers["gpu_opt"].status,
                "gpu": state.workers["gpu"].status,
            },
            "comparison": {
                "gpu_opt_seconds": gpu_opt_seconds,
                "gpu_seconds": gpu_seconds,
                "gpu_opt_speedup_ratio": speedup,
                "output_match": bool(
                    gpu_opt_fingerprint and gpu_opt_fingerprint == gpu_fingerprint
                ),
                "gpu_opt_fingerprint": gpu_opt_fingerprint,
                "gpu_fingerprint": gpu_fingerprint,
            },
            "discrepancies": discrepancies,
            "devices": {
                "gpu_opt": gpu_opt_result,
                "gpu": gpu_result,
            },
        }
    )


@app.route("/api/analyze_onnx_cpu_vs_gpu", methods=["POST"])
def api_analyze_onnx_cpu_vs_gpu() -> Any:
    if not {"onnx_cpu", "gpu"}.issubset(state.workers):
        return jsonify(
            {"ok": False, "error": "ONNX CPU and GPU workers are not started"}
        ), 503
    for worker in state.workers.values():
        worker.drain()
    onnx_status = state.workers["onnx_cpu"].status
    gpu_status = state.workers["gpu"].status
    if onnx_status.get("state") != "ready" or gpu_status.get("state") != "ready":
        if onnx_status.get("state") == "error":
            status_error = str(
                onnx_status.get("error") or "ONNX CPU worker is in error state"
            )
        elif gpu_status.get("state") == "error":
            status_error = str(
                gpu_status.get("error") or "regular GPU worker is in error state"
            )
        else:
            status_error = "workers are still loading"
        return jsonify(
            {
                "ok": False,
                "error": status_error,
                "load": {
                    "onnx_cpu": onnx_status.get("load_metrics"),
                    "gpu": gpu_status.get("load_metrics"),
                },
                "worker_status": {
                    "onnx_cpu": onnx_status,
                    "gpu": gpu_status,
                },
                "comparison": {
                    "onnx_cpu_seconds": None,
                    "gpu_seconds": None,
                    "onnx_cpu_vs_gpu_ratio": None,
                    "output_match": False,
                    "onnx_cpu_fingerprint": None,
                    "gpu_fingerprint": None,
                },
                "discrepancies": {
                    "match": False,
                    "diff_count": None,
                    "truncated": False,
                    "text": status_error,
                },
                "devices": {
                    "onnx_cpu": {
                        "type": "result",
                        "device": "onnx_cpu",
                        "ok": False,
                        "error": status_error,
                        "status": onnx_status,
                    },
                    "gpu": {
                        "type": "result",
                        "device": "gpu",
                        "ok": False,
                        "error": status_error,
                        "status": gpu_status,
                    },
                },
            }
        ), 503
    data = request.get_json(silent=True) or {}
    text = str(data.get("text") or "")
    if not text.strip():
        return jsonify({"ok": False, "error": "empty text"}), 400

    request_id = uuid.uuid4().hex
    command = {
        "type": "analyze",
        "request_id": request_id,
        "text": text,
        "lang": str(data.get("lang") or "zh"),
        "trankit_override": str(data.get("trankit_override") or ""),
        "manual_sentence_segmentation": bool(data.get("manual_sentence_segmentation")),
        "strip_punctuation": bool(data.get("strip_punctuation")),
    }

    onnx_result = state.workers["onnx_cpu"].analyze(command)
    gpu_result = state.workers["gpu"].analyze(command)
    for worker in state.workers.values():
        worker.drain()

    onnx_metrics = onnx_result.get("metrics") if isinstance(onnx_result, dict) else None
    gpu_metrics = gpu_result.get("metrics") if isinstance(gpu_result, dict) else None
    onnx_seconds = (
        onnx_metrics.get("elapsed_seconds") if isinstance(onnx_metrics, dict) else None
    )
    gpu_seconds = (
        gpu_metrics.get("elapsed_seconds") if isinstance(gpu_metrics, dict) else None
    )
    ratio = None
    if (
        isinstance(onnx_seconds, (int, float))
        and isinstance(gpu_seconds, (int, float))
        and gpu_seconds
    ):
        ratio = onnx_seconds / gpu_seconds
    onnx_fingerprint = (
        onnx_metrics.get("output_fingerprint")
        if isinstance(onnx_metrics, dict)
        else None
    )
    gpu_fingerprint = (
        gpu_metrics.get("output_fingerprint") if isinstance(gpu_metrics, dict) else None
    )
    if onnx_result.get("ok") and gpu_result.get("ok"):
        discrepancies = comparison._annotation_discrepancy_report(
            onnx_result.get("annotations"),
            gpu_result.get("annotations"),
        )
    else:
        discrepancies = {
            "match": False,
            "diff_count": None,
            "truncated": False,
            "text": "Comparison unavailable because one output failed.",
        }

    return jsonify(
        {
            "ok": bool(onnx_result.get("ok") and gpu_result.get("ok")),
            "request_id": request_id,
            "text_chars": len(text),
            "load": {
                "onnx_cpu": state.workers["onnx_cpu"].status.get("load_metrics"),
                "gpu": state.workers["gpu"].status.get("load_metrics"),
            },
            "worker_status": {
                "onnx_cpu": state.workers["onnx_cpu"].status,
                "gpu": state.workers["gpu"].status,
            },
            "comparison": {
                "onnx_cpu_seconds": onnx_seconds,
                "gpu_seconds": gpu_seconds,
                "onnx_cpu_vs_gpu_ratio": ratio,
                "output_match": bool(
                    onnx_fingerprint and onnx_fingerprint == gpu_fingerprint
                ),
                "onnx_cpu_fingerprint": onnx_fingerprint,
                "gpu_fingerprint": gpu_fingerprint,
            },
            "discrepancies": discrepancies,
            "devices": {
                "onnx_cpu": onnx_result,
                "gpu": gpu_result,
            },
        }
    )


@app.route("/api/load_probe", methods=["POST"])
def api_load_probe() -> Any:
    data = request.get_json(silent=True) or {}
    mode = str(data.get("mode") or "").strip().lower()
    if mode not in {"xlm_only", "lang_modules", "full"}:
        return jsonify(
            {"ok": False, "error": "mode must be xlm_only, lang_modules, or full"}
        ), 400
    raw_lang = str(data.get("lang") or "zh").strip().lower()
    warmup_text = str(data.get("warmup_text") or "")
    if mode == "xlm_only":
        description = (
            "Cold-start probe for the shared XLM-R part only: start a fresh process, "
            "import torch/trankit/language_registry, force the selected device, then load "
            "the XLM-R tokenizer/model used by Trankit. No Trankit language modules are loaded."
        )
    elif mode == "lang_modules":
        description = (
            "Cold-start probe for selected language-specific Trankit modules only: start a "
            "fresh process, import torch/trankit/language_registry, force the selected device, "
            "then load the selected language tokenizer classifier, POS/dependency classifier, "
            "lemmatizer, MWT wrapper if required, and NER classifier if registered. Shared "
            "XLM-R is not loaded in this probe."
        )
    else:
        description = (
            "Cold-start simulation for a dedicated Trankit worker: start a fresh process, "
            "import torch/trankit/language_registry, force the selected device, then call "
            "language_registry.init_trankit() to load the full all-language app pipeline."
        )

    started = time.perf_counter()
    cpu_result = cold_start.run_cold_start_probe_process(
        mode, "cpu", False, raw_lang, warmup_text
    )
    gpu_result = cold_start.run_cold_start_probe_process(
        mode, "gpu", True, raw_lang, warmup_text
    )

    return jsonify(
        {
            "ok": bool(cpu_result.get("ok") and gpu_result.get("ok")),
            "mode": mode,
            "lang": raw_lang,
            "description": description,
            "warmup_inference_requested": bool(warmup_text.strip()),
            "elapsed_seconds": time.perf_counter() - started,
            "devices": {
                "cpu": cpu_result,
                "gpu": gpu_result,
            },
        }
    )
