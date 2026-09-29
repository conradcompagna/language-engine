# Shared ONNX encoder and dynamic adapters

Prototypes for serving many languages from one XLM-R encoder: the language-specific
adapter weights are passed to a single ONNX graph as inputs, and the encoder is
quantized to INT8.

## Files

- `sandbox_trankit_adapter_bank_prototype.py` explores the adapter-bank representation.
- `sandbox_arabic_one_xlmr_dynamic_adapters_onnx.py` threads dynamic adapter inputs
  through an ONNX graph.
- `sandbox_arabic_quantized_trankit_pipeline.py` exercises the quantized pipeline.

## Outcome

The application uses this design. The maintained implementation is in
[trankit_compressed_runtime.py](../../../trankit_compressed_runtime.py) and
[trankit_onnx_live_switch.py](../../../trankit_onnx_live_switch.py), with artifact
assembly in [the runtime bundle builder](../../pipeline/models/build_trankit_compressed_runtime_artifacts.py).
