# Shared ONNX encoder and dynamic adapters

## Engineering problem

A multilingual service needs to switch language-specific components while managing
the memory and startup cost of the shared XLM-R encoder. This prototype series
explored supplying adapter tensors as ONNX inputs and combining that design with
INT8 quantization.

## Prototype record

- `sandbox_trankit_adapter_bank_prototype.py` explores the adapter-bank representation.
- `sandbox_arabic_one_xlmr_dynamic_adapters_onnx.py` threads dynamic adapter inputs
  through an ONNX graph.
- `sandbox_arabic_quantized_trankit_pipeline.py` exercises the quantized pipeline.

## Application architecture

The application uses a shared dynamic-INT8 ONNX encoder with language/task adapter
inputs. Its maintained implementation is in
[trankit_compressed_runtime.py](../../../trankit_compressed_runtime.py) and
[trankit_onnx_live_switch.py](../../../trankit_onnx_live_switch.py), with artifact
assembly in [the runtime bundle builder](../../pipeline/models/build_trankit_compressed_runtime_artifacts.py).

These scripts document the prototype stage; the runtime modules above show how the
architecture is integrated into the reader. The
[memory probe](../../evaluation/benchmarks/memory_probe.py) and
[session tuner](../../pipeline/models/tune_trankit_onnx_ort_session.py) support
measurement of memory and inference settings on a provisioned model store.
