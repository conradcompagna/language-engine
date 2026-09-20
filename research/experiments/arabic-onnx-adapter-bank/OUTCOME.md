# Shared encoder with an adapter bank — prototyped, not shipped

## What was tried

The service holds a separate XLM-R encoder per active language. The encoder is by far
the largest part of each model, and it is the same architecture every time. If one
INT8-quantised encoder could be held in memory and switched between languages by
feeding a small per-language adapter tensor, the memory floor would drop by roughly the
number of active languages.

Three prototypes:

- `sandbox_trankit_adapter_bank_prototype.py` — the adapter bank itself
- `sandbox_arabic_one_xlmr_dynamic_adapters_onnx.py` — dynamic adapter inputs threaded
  through an ONNX graph
- `sandbox_arabic_quantized_trankit_pipeline.py` — the quantised end-to-end pipeline

## What happened

The prototype ran. Exporting adapter selection as a dynamic ONNX input, rather than
baking one adapter into the graph, made the export fragile across ONNX Runtime
versions, and the per-request switching cost ate into the latency budget the reader
needs for interactive lookup.

## What shipped instead

A single dynamic-INT8 ONNX encoder with a compressed runtime bundle and live switching
at the model level rather than the adapter level. See
`research/pipeline/models/build_trankit_compressed_runtime_artifacts.py` and the
runtime module `trankit_onnx_live_switch.py`. Memory measurements that informed the
decision are in `research/evaluation/benchmarks/memory_probe.py`.

The idea is still sound and would be worth revisiting against a newer ONNX Runtime.
