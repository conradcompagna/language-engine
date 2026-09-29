# Trankit CPU/GPU benchmark

A local web tool for comparing the CPU (INT8 ONNX) and GPU (PyTorch) inference paths
on the same input. It runs each path in a separate worker process, times each
pipeline stage, measures memory, and reports any differences in the resulting
tokens, tags and entities. Start it with
[`../trankit_dual_device_benchmark_app.py`](../trankit_dual_device_benchmark_app.py).

| Modules | Role |
|---|---|
| `routes.py`, `settings.py`, `templates/`, `static/` | Web interface |
| `worker.py`, `worker_handle.py`, `lifecycle.py`, `state.py` | Worker processes and their lifecycle |
| `cpu_backend.py`, `cpu_profile.py`, `cpu_tuning.py`, `cpu_candidates.py`, `cpu_selection_cache.py` | CPU configurations and selection |
| `gpu_profile.py`, `onnx_runtime.py`, `onnx_batching.py` | Device execution and batching |
| `quantization.py`, `model_cache.py`, `model_diagnostics.py`, `dependencies.py` | Model loading and quantization |
| `instrumentation.py`, `memory.py`, `load_probe.py`, `cold_start.py` | Timing, memory and start-up measurement |
| `comparison.py`, `analysis.py` | Alignment and comparison of the two outputs |
