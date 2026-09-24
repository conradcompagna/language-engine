# Inference comparison and profiling

I built this benchmark interface while adapting multilingual Trankit inference
for CPU deployment. It brings annotation comparison, stage timing and memory
measurements together so runtime changes can be examined at the component level.

## Comparison design

CPU and GPU workers run in separate processes, with request queues and a
parent-owned lifecycle. The retained startup selects the ONNX CPU worker and the
application's GPU Trankit path. Both use the application's language registry and
integration policies.

The comparison layer fingerprints complete annotations and aligns sentence and
token sequences before reporting differences. This connects performance work to
its effect on tokenization, expanded words, grammatical tags and named entities.

Instrumentation separates task time, ONNX session time, tensor handoff and other
PyTorch work. Batch records distinguish real sequence lengths from padded work;
load and memory probes separate initialization from request processing.

## Engineering components

| Responsibility | Source |
|---|---|
| Process ownership and lifecycle | [worker.py](worker.py), [worker_handle.py](worker_handle.py), [lifecycle.py](lifecycle.py), [state.py](state.py) |
| CPU profiles and candidate selection | [cpu_backend.py](cpu_backend.py), [cpu_profile.py](cpu_profile.py), [cpu_tuning.py](cpu_tuning.py), [cpu_candidates.py](cpu_candidates.py) |
| Device execution and batching | [gpu_profile.py](gpu_profile.py), [onnx_runtime.py](onnx_runtime.py), [onnx_batching.py](onnx_batching.py) |
| Model transforms and cached decisions | [quantization.py](quantization.py), [model_cache.py](model_cache.py), [cpu_selection_cache.py](cpu_selection_cache.py) |
| Timing, memory and initialization | [instrumentation.py](instrumentation.py), [memory.py](memory.py), [load_probe.py](load_probe.py), [cold_start.py](cold_start.py) |
| Annotation alignment and discrepancy metrics | [comparison.py](comparison.py) |

## Recorded optimization result

The separate [ONNX session-tuning record](../../README.md#onnx-session-tuning)
compares session settings on one fixed Japanese request: mean time fell from
1.905 seconds to 0.906 seconds across two timed requests per profile, following
one warmup, with matching annotation fingerprints. The record includes the input
size, hardware context and runtime versions.

The [CPU construction record](../../../../docs/BUILD_PROCESS.md#3-package-inference-for-cpu-deployment)
connects these optimization tools to the selected shared encoder and adapter packs.
