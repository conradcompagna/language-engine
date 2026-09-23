# Trankit device benchmark

This opt-in harness compares annotations, timing and memory for CPU/GPU/ONNX
execution; it is separate from the reader server and is not a CI performance claim.
The preserved default startup loads the ONNX CPU worker and the GPU worker.
Historical UI options for other worker combinations require provisioning those
workers; an unavailable pair returns 503.

Run from an environment with the root application's Trankit/PyTorch dependencies,
authorized model caches, the ONNX runtime and a supported CUDA installation:

```sh
python research/evaluation/benchmarks/trankit_dual_device_benchmark_app.py
```

The compatibility entrypoint works from any current directory. Importing it starts
no worker. Startup explicitly starts and waits for spawned processes; shutdown
joins/terminates them. Open the local URL printed by Flask after workers are ready.
This development harness should remain bound to localhost.

## Ownership

- `worker.py`, `worker_handle.py`, `lifecycle.py`, `state.py`: isolated device
  processes, request queues, parent lifecycle and parent-owned mutable status.
- `cpu_backend.py`, `cpu_profile.py`, `cpu_tuning.py`, `cpu_candidates.py`: CPU
  execution profiles and measured candidate selection.
- `gpu_profile.py`, `onnx_runtime.py`, `onnx_batching.py`: device-specific adapters.
- `quantization.py`, `model_cache.py`, `cpu_selection_cache.py`: module transforms
  and cached optimization decisions.
- `memory.py`, `instrumentation.py`, `load_probe.py`, `cold_start.py`: measurements.
- `comparison.py`: annotation alignment and discrepancy metrics.
- `routes.py`, `templates/`, `static/`: the local benchmark interface.

## Configuration

Set environment variables **before** starting the parent so spawned workers see
the same paths. Cache defaults remain adjacent to the compatibility entrypoint.

| Variable | Default |
|---|---|
| `TRANKIT_BENCHMARK_HOST` | `127.0.0.1` |
| `TRANKIT_BENCHMARK_PORT` | `5055` |
| `TRANKIT_CPU_OPT_DEPS_DIR` | `.trankit_cpu_opt_deps` |
| `TRANKIT_CPU_OPT_CACHE_DIR` | `.trankit_cpu_opt_cache` |
| `TRANKIT_ONNX_CACHE_DIR` | `.trankit_compressed_runtime` |
| `TRANKIT_ONNX_DEPS_DIRS` | Optional directories separated by the OS path separator |

No private `C:\\tmp` dependency paths are assumed. This repository does not ship
model weights or claim a fresh clone reproduces a hardware benchmark result.
Record model hashes, dependencies, hardware, input, repetitions and warmup state
alongside any measurements you publish.

`python -m pytest tests/test_benchmark.py` checks pre-extraction comparison fixtures,
the asset-serving interface, spawn imports and picklable worker targets without
loading models. Hardware timing, CUDA and ONNX inference require a separate run
with the authorized assets and are not covered by these fixture checks.
