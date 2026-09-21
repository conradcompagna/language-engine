"""Trankit benchmark: settings."""

from __future__ import annotations

import os
from pathlib import Path

BENCHMARK_ROOT = str(Path(__file__).resolve().parent.parent)

HOST = os.environ.get("TRANKIT_BENCHMARK_HOST", "127.0.0.1")


PORT = int(os.environ.get("TRANKIT_BENCHMARK_PORT", "5055"))


WORKER_RESPONSE_TIMEOUT_SECONDS = 60 * 60


LOAD_PROBE_TIMEOUT_SECONDS = 60 * 60


STARTUP_WORKER_TIMEOUT_SECONDS = 60 * 60


CPU_OPT_DEPS_DIR = os.environ.get(
    "TRANKIT_CPU_OPT_DEPS_DIR", os.path.join(BENCHMARK_ROOT, ".trankit_cpu_opt_deps")
)


CPU_OPT_CACHE_DIR = os.environ.get(
    "TRANKIT_CPU_OPT_CACHE_DIR", os.path.join(BENCHMARK_ROOT, ".trankit_cpu_opt_cache")
)


CPU_OPT_PROFILE_NAME = "xlmr_base_int8_pytorch"


CPU_OPT_SELECTION_CACHE_VERSION = 4


CPU_OPT_SELECTION_CACHE_PATH = os.path.join(
    CPU_OPT_CACHE_DIR, "selection_v4_xlmr_base_int8_pytorch.json"
)


CPU_OPT_XLMR_CACHE_VERSION = 3


CPU_OPT_XLMR_CACHE_PATH = os.path.join(
    CPU_OPT_CACHE_DIR, "xlmr_base_int8_no_adapters_v3.pt"
)


CPU_OPT_SEQ2SEQ_CACHE_PATH = os.path.join(
    CPU_OPT_CACHE_DIR, "seq2seq_int8_modules_v2.pt"
)


CPU_OPT_PROFILE_TIMEOUT_SECONDS = 60 * 60


CPU_OPT_TUNE_REPETITIONS = 3


CPU_OPT_SEQUENCE_BUCKETS = [64, 128, 256, 400]


CPU_OPT_QUANTIZE_EXCLUDE_TOKENS = ("adapter", "layernorm", "layer_norm", "embedding")


CPU_OPT_TUNE_TEXT = (
    "Ceci est une phrase courte pour regler le chemin CPU. "
    "Cette deuxieme phrase garde la tokenisation et l'analyse actives."
)


CPU_OPT_DEFAULT_TOK_BATCH_SIZE = 8


CPU_OPT_DEFAULT_TAG_BATCH_SIZE = 32


GPU_OPT_PROFILE_NAME = "gpu_pytorch_hotpath"


GPU_OPT_ENABLE_TORCH_COMPILE = False


GPU_OPT_SEQUENCE_BUCKETS = [64, 128, 256, 400]


ONNX_DEPS_DIRS = [
    p for p in os.environ.get("TRANKIT_ONNX_DEPS_DIRS", "").split(os.pathsep) if p
] + [os.path.join(BENCHMARK_ROOT, ".trankit_onnx_deps"), CPU_OPT_DEPS_DIR]


ONNX_CACHE_DIR = os.environ.get(
    "TRANKIT_ONNX_CACHE_DIR",
    os.path.join(BENCHMARK_ROOT, ".trankit_compressed_runtime"),
)


ONNX_MANIFEST_PATH = os.path.join(ONNX_CACHE_DIR, "manifest.json")


ONNX_PROFILE_NAME = "one_xlmr_dynamic_adapter_int8"


ONNX_EXPORT_OPSET = 17


ONNX_CPU_TOK_BATCH_SIZE = 12


ONNX_CPU_TAG_BATCH_SIZE = 32


ONNX_DYNAMIC_TOK_BATCH_CANDIDATES = [1, 2, 3, 4, 6, 8, 12, 16]


ONNX_DYNAMIC_TAG_BATCH_CANDIDATES = [1, 2, 4, 8, 12, 16, 24, 32]


ONNX_DYNAMIC_TOK_CALL_OVERHEAD_UNITS = 768


ONNX_DYNAMIC_TAG_CALL_OVERHEAD_UNITS = 768
