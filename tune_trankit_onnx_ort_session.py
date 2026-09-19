"""
Standalone ONNX Runtime session tuning for the sandbox compressed Trankit runtime.

This script:
  - loads the existing .trankit_compressed_runtime artifacts
  - loads the app Trankit pipeline on CPU
  - installs the compressed ONNX XLM-R runtime
  - benchmarks ORT session/thread profiles on one page-length sample
  - writes .trankit_compressed_runtime/ort_session_tuning.json

It does not edit production runtime files or installed Trankit files.
"""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
import platform
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from sandbox_trankit_compressed_runtime import (
    MANIFEST_PATH,
    PROFILE_NAME,
    force_utf8,
    install_compressed_runtime,
    prepend_deps,
    set_sandbox_env,
)


OUTPUT_PATH = MANIFEST_PATH.parent / "ort_session_tuning.json"

DEFAULT_SAMPLE = """生体内での酵素の役割は、生命を構成する有機化合物や無機化合物を取り込み、必要な化学反応を引き起こすことにある。生命現象は多くの代謝経路を含み、それぞれの代謝経路は多段階の化学反応からなっている。

細胞内では、その中で起こるさまざまな化学反応を担当する形で多種多様な酵素が働いている。それぞれの酵素は自分の形に合った特定の原料化合物（基質）を外から取り込み、担当する化学反応を触媒し、生成物を外へと放出する。そして再び次の反応のために基質を取り込み、目的の物質を生成し続ける。

ここで放出された生成物は、別の化学反応を担当する酵素の作用を受けて、さらに別の生体物質へと代謝されていく。このような酵素の触媒反応の繰り返しで必要な物質の生成や不必要な物質の分解が進行し、生命活動が維持されていく。

生体内では化学工業のプラントのように基質と生成物の容器が隔てられているわけではなく、さまざまな物質が渾然一体となって存在している。しかし、生命現象を作る代謝経路でいろいろな化合物が無秩序に反応してしまっては生命活動は維持できない。

したがって酵素は、生体内の物質の中から作用するべきものを選び出さなければならない。また、反応で余分なものを作り出してしまうと周囲に悪影響を及ぼしかねないので、ある基質に対して起こす反応は決まっていなければならない。酵素は生体内の化学反応を秩序立てて進めるために、このように高度な基質選択性と反応選択性を持つ。"""


def _force_trankit_pipeline_cpu() -> None:
    import trankit  # type: ignore

    real_init = trankit.Pipeline.__init__
    if getattr(real_init, "_ort_tune_forced_cpu", False):
        return

    def patched_init(self: Any, *args: Any, **kwargs: Any) -> None:
        kwargs["gpu"] = False
        return real_init(self, *args, **kwargs)

    setattr(patched_init, "_ort_tune_forced_cpu", True)
    trankit.Pipeline.__init__ = patched_init


def _artifact_signature(path: Path) -> Dict[str, Any]:
    stat = path.stat()
    return {
        "path": str(path),
        "bytes": int(stat.st_size),
        "mtime": float(stat.st_mtime),
    }


def _annotation_summary(node: Any) -> Any:
    if isinstance(node, dict):
        keep = {}
        for key in ["id", "text", "upos", "xpos", "feats", "head", "deprel", "lemma", "ner", "dspan", "span"]:
            if key in node:
                keep[key] = node.get(key)
        if "tokens" in node:
            keep["tokens"] = _annotation_summary(node.get("tokens"))
        if "expanded" in node:
            keep["expanded"] = _annotation_summary(node.get("expanded"))
        if "mwt_expanded_words" in node:
            keep["mwt_expanded_words"] = _annotation_summary(node.get("mwt_expanded_words"))
        if "sentences" in node:
            keep["sentences"] = _annotation_summary(node.get("sentences"))
        return keep
    if isinstance(node, list):
        return [_annotation_summary(item) for item in node]
    return node


def _annotation_fingerprint(doc: Any) -> str:
    payload = json.dumps(_annotation_summary(doc), ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _count_tokens(doc: Any) -> int:
    if not isinstance(doc, dict):
        return 0
    sentences = doc.get("sentences") or []
    total = 0
    if isinstance(sentences, list):
        for sentence in sentences:
            if isinstance(sentence, dict) and isinstance(sentence.get("tokens"), list):
                total += len(sentence["tokens"])
    return total


def _percentile(values: List[float], pct: float) -> Optional[float]:
    cleaned = sorted(float(value) for value in values if isinstance(value, (int, float)))
    if not cleaned:
        return None
    if len(cleaned) == 1:
        return cleaned[0]
    rank = (len(cleaned) - 1) * pct / 100.0
    lower = int(rank)
    upper = min(lower + 1, len(cleaned) - 1)
    frac = rank - lower
    return cleaned[lower] + (cleaned[upper] - cleaned[lower]) * frac


def _make_session(ort: Any, session_path: str, profile: Dict[str, Any]) -> Any:
    options = ort.SessionOptions()
    options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL
    if profile.get("intra_op_num_threads") is not None:
        options.intra_op_num_threads = int(profile["intra_op_num_threads"])
    if profile.get("inter_op_num_threads") is not None:
        options.inter_op_num_threads = int(profile["inter_op_num_threads"])
    execution_mode = str(profile.get("execution_mode") or "sequential")
    if execution_mode == "parallel":
        options.execution_mode = ort.ExecutionMode.ORT_PARALLEL
    else:
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
    if profile.get("enable_cpu_mem_arena") is not None:
        options.enable_cpu_mem_arena = bool(profile["enable_cpu_mem_arena"])
    if profile.get("enable_mem_pattern") is not None:
        options.enable_mem_pattern = bool(profile["enable_mem_pattern"])
    return ort.InferenceSession(session_path, sess_options=options, providers=["CPUExecutionProvider"])


def _profile_candidates(cpu_count: int) -> List[Dict[str, Any]]:
    thread_values = []
    for value in [1, 2, 4, 8, 12, 16, cpu_count]:
        if isinstance(value, int) and value > 0 and value not in thread_values:
            thread_values.append(value)
    base = [{
        "name": f"seq_intra_{threads}",
        "intra_op_num_threads": threads,
        "inter_op_num_threads": 1,
        "execution_mode": "sequential",
        "enable_cpu_mem_arena": True,
        "enable_mem_pattern": True,
    } for threads in thread_values]
    base.insert(0, {
        "name": "ort_default",
        "intra_op_num_threads": None,
        "inter_op_num_threads": None,
        "execution_mode": "default",
        "enable_cpu_mem_arena": None,
        "enable_mem_pattern": None,
    })
    if cpu_count and cpu_count > 1:
        best_guess = min(cpu_count, 8)
        base.extend([
            {
                "name": f"seq_intra_{best_guess}_no_mem_pattern",
                "intra_op_num_threads": best_guess,
                "inter_op_num_threads": 1,
                "execution_mode": "sequential",
                "enable_cpu_mem_arena": True,
                "enable_mem_pattern": False,
            },
            {
                "name": f"seq_intra_{best_guess}_no_arena",
                "intra_op_num_threads": best_guess,
                "inter_op_num_threads": 1,
                "execution_mode": "sequential",
                "enable_cpu_mem_arena": False,
                "enable_mem_pattern": True,
            },
        ])
    return base


def _run_request(lr: Any, run_with_universal_normalization: Any, text: str, lang: str) -> Any:
    def run_one(model_text: str, trankit_lang: str) -> Dict[str, Any]:
        return lr.run_trankit(model_text, trankit_lang)

    return run_with_universal_normalization(
        text,
        run_one,
        lang,
        language=lang,
        strip_punctuation=False,
    )


def _delta_metrics(before: Dict[str, Any], after: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for key in ["run_count", "total_seconds", "preprocess_seconds", "session_seconds", "postprocess_seconds"]:
        try:
            out[key] = max(0.0, float(after.get(key) or 0.0) - float(before.get(key) or 0.0))
        except Exception:
            out[key] = None
    try:
        out["run_count"] = int(round(float(out.get("run_count") or 0)))
    except Exception:
        out["run_count"] = None
    return out


def _benchmark_profile(
    shim: Any,
    ort: Any,
    lr: Any,
    run_with_universal_normalization: Any,
    session_path: str,
    profile: Dict[str, Any],
    text: str,
    lang: str,
    warmup: int,
    repetitions: int,
) -> Dict[str, Any]:
    session_started = time.perf_counter()
    shim.session = _make_session(ort, session_path, profile)
    session_create_seconds = time.perf_counter() - session_started

    for _ in range(max(0, warmup)):
        _run_request(lr, run_with_universal_normalization, text, lang)

    timings = []
    fingerprints = []
    tokens = []
    ort_session_seconds = []
    for _ in range(max(1, repetitions)):
        gc.collect()
        before = shim.metrics()
        started = time.perf_counter()
        doc = _run_request(lr, run_with_universal_normalization, text, lang)
        elapsed = time.perf_counter() - started
        after = shim.metrics()
        delta = _delta_metrics(before, after)
        timings.append(elapsed)
        fingerprints.append(_annotation_fingerprint(doc))
        tokens.append(_count_tokens(doc))
        if isinstance(delta.get("session_seconds"), (int, float)):
            ort_session_seconds.append(float(delta["session_seconds"]))

    return {
        "profile": profile,
        "session_create_seconds": session_create_seconds,
        "warmup_count": int(max(0, warmup)),
        "repetitions": int(max(1, repetitions)),
        "elapsed_samples_seconds": timings,
        "p50_seconds": _percentile(timings, 50),
        "p95_seconds": _percentile(timings, 95),
        "mean_seconds": statistics.fmean(timings) if timings else None,
        "best_seconds": min(timings) if timings else None,
        "ort_session_samples_seconds": ort_session_seconds,
        "ort_session_mean_seconds": statistics.fmean(ort_session_seconds) if ort_session_seconds else None,
        "fingerprint": fingerprints[-1] if fingerprints else "",
        "fingerprints_match_within_profile": len(set(fingerprints)) <= 1,
        "token_count": tokens[-1] if tokens else 0,
    }


def main() -> int:
    force_utf8()
    parser = argparse.ArgumentParser()
    parser.add_argument("--lang", default="ja")
    parser.add_argument("--text-file", default="")
    parser.add_argument("--warmup", type=int, default=1)
    parser.add_argument("--repetitions", type=int, default=2)
    args = parser.parse_args()

    set_sandbox_env()
    prepend_deps()
    text = DEFAULT_SAMPLE
    if args.text_file:
        text = Path(args.text_file).read_text(encoding="utf-8")
    lang = str(args.lang or "ja").strip().lower()

    if not MANIFEST_PATH.exists():
        raise RuntimeError(f"Missing ONNX manifest: {MANIFEST_PATH}")

    import onnxruntime as ort  # type: ignore
    import torch  # type: ignore

    _force_trankit_pipeline_cpu()
    import language_registry as lr
    from universal_normalization import run_with_universal_normalization

    started = time.perf_counter()
    print("loading Trankit pipeline on CPU", flush=True)
    lr.init_trankit()
    pipeline = getattr(lr, "_trankit_pipeline", None)
    if pipeline is None:
        raise RuntimeError("language_registry did not create _trankit_pipeline")

    print("installing compressed ONNX runtime", flush=True)
    install_report = install_compressed_runtime(pipeline, torch, manifest_path=MANIFEST_PATH)
    shim = getattr(pipeline, "_compressed_xlmr_runtime", None)
    if shim is None:
        raise RuntimeError("compressed runtime did not install _compressed_xlmr_runtime")
    session_path = str((shim.metrics() or {}).get("onnx_session") or install_report.get("onnx_session") or "")
    if not session_path:
        raise RuntimeError("could not determine ONNX session path")

    cpu_count = os.cpu_count() or 1
    candidates = _profile_candidates(cpu_count)
    results = []
    print(f"benchmarking {len(candidates)} ORT profiles on {lang} sample", flush=True)
    for index, profile in enumerate(candidates, start=1):
        name = str(profile.get("name") or f"profile_{index}")
        print(f"[{index}/{len(candidates)}] {name}", flush=True)
        try:
            row = _benchmark_profile(
                shim,
                ort,
                lr,
                run_with_universal_normalization,
                session_path,
                profile,
                text,
                lang,
                int(args.warmup),
                int(args.repetitions),
            )
            row["ok"] = True
        except Exception as exc:
            row = {
                "ok": False,
                "profile": profile,
                "error": str(exc),
            }
        results.append(row)

    valid = [row for row in results if row.get("ok") and isinstance(row.get("p95_seconds"), (int, float))]
    if not valid:
        raise RuntimeError(f"No ORT profile benchmark succeeded: {results}")

    baseline = next((row for row in valid if (row.get("profile") or {}).get("name") == "ort_default"), valid[0])
    best = min(valid, key=lambda row: float(row.get("p95_seconds") or row.get("mean_seconds") or 999999.0))
    baseline_seconds = float(baseline.get("p95_seconds") or baseline.get("mean_seconds") or 0.0)
    best_seconds = float(best.get("p95_seconds") or best.get("mean_seconds") or 0.0)
    savings_pct = ((baseline_seconds - best_seconds) / baseline_seconds * 100.0) if baseline_seconds else 0.0

    artifact_path = Path(session_path)
    output = {
        "ok": True,
        "profile_name": PROFILE_NAME,
        "created_at": time.time(),
        "elapsed_seconds": time.perf_counter() - started,
        "lang": lang,
        "sample_chars": len(text),
        "cpu": {
            "os_cpu_count": cpu_count,
            "platform": platform.platform(),
            "processor": platform.processor(),
        },
        "runtime": {
            "python_version": sys.version,
            "torch_version": str(getattr(torch, "__version__", "")),
            "onnxruntime_version": str(getattr(ort, "__version__", "")),
        },
        "artifact": _artifact_signature(artifact_path),
        "manifest": _artifact_signature(MANIFEST_PATH),
        "install_report": install_report,
        "baseline": {
            "profile": baseline.get("profile"),
            "p95_seconds": baseline.get("p95_seconds"),
            "mean_seconds": baseline.get("mean_seconds"),
            "best_seconds": baseline.get("best_seconds"),
        },
        "best": {
            "profile": best.get("profile"),
            "p95_seconds": best.get("p95_seconds"),
            "mean_seconds": best.get("mean_seconds"),
            "best_seconds": best.get("best_seconds"),
            "token_count": best.get("token_count"),
        },
        "savings_vs_default": {
            "p95_seconds_saved": baseline_seconds - best_seconds,
            "p95_percent_saved": savings_pct,
            "speedup_ratio": (baseline_seconds / best_seconds) if best_seconds else None,
        },
        "results": results,
    }
    OUTPUT_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2, default=str), encoding="utf-8")

    print(json.dumps({
        "ok": True,
        "output_path": str(OUTPUT_PATH),
        "baseline_p95_seconds": baseline.get("p95_seconds"),
        "best_p95_seconds": best.get("p95_seconds"),
        "p95_percent_saved": savings_pct,
        "best_profile": best.get("profile"),
        "token_count": best.get("token_count"),
    }, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
