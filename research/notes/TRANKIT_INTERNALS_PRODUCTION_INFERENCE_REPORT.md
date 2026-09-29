# Multilingual inference on CPU

I adapted Trankit's shared encoder and language/task adapters into a CPU runtime
that retains the application's tokenization, grammatical analysis and named-entity
interfaces. The work combines encoder export, quantization, adapter selection,
dictionary-first sequence processing and measurement of individual pipeline stages.

## Shared encoder and compressed adapters

The [artifact builder](../pipeline/models/build_trankit_compressed_runtime_artifacts.py)
exports XLM-R to ONNX, applies graph optimization and dynamic INT8 quantization,
and assembles compressed language/task adapter packs. The
[runtime](../../trankit_compressed_runtime.py) supplies the selected adapter tensors
as inputs to one shared encoder graph, preserving Trankit's adapter-switching model.

Each pack stores quantized down/up weights and biases with their scales. Tokenizer,
tagger and NER adapters can change without loading another full XLM-R graph.
Trankit's task heads, lemmatizer and multi-word-token expander remain in PyTorch;
supported linear and recurrent modules are dynamically quantized there.

The [selected artifact manifest](../models/deployed_artifacts.json) records the
encoder and adapter identities. The INT8 encoder is 278,515,512 bytes, compared
with 1,110,086,874 bytes for its FP32 export: roughly a 75% reduction in file size.
The [construction guide](../../docs/BUILD_PROCESS.md#3-package-inference-for-cpu-deployment)
connects the export stages to the deployed bundle.

## Avoiding unnecessary sequence-model work

The [language registry](../../language_registry.py) integrates dictionary-first
handling for lemmatization and multi-word-token expansion. Trankit's
`composite_dict` and `word_dict` resolve known lemmas; `expansion_dict` resolves
known expansions. Only misses go to the sequence decoder, and the results are
reassembled in their original order.

Manual sentence boundaries are packed into a common tokenizer document with
internal newline handling, retaining the boundary policy without creating a
separate tokenizer request for every sentence.

## Batching and instrumentation

I built a separate [device-comparison tool](../evaluation/benchmarks/trankit_benchmark/README.md)
to examine the costs of the encoder, task heads, sequence decoders and Python
processing. Its ONNX worker includes tokenizer padding to the actual batch length,
length sorting for tokenizer/POS/NER examples, and dynamic batch partitions based
on padded-token cost and estimated call overhead. Lemmatization and MWT expansion
retain their own sequence-processing path.

The instrumentation records task time, batch sizes, real and padded units, model
call counts, ONNX session time and tensor-handoff time. Annotation fingerprints
and aligned discrepancy reports accompany device comparisons. These tools expose
both execution cost and the linguistic outputs affected by a runtime change.

## Session tuning and recorded result

The [session tuner](../pipeline/models/tune_trankit_onnx_ort_session.py) compares
thread counts, execution modes and memory settings on the same request. The
recorded selection uses sequential execution, eight intra-op threads, one inter-op
thread and disabled memory patterns.

| Session profile | Timed requests | Mean |
|---|---|---:|
| ORT defaults | 1.914 s, 1.896 s | 1.905 s |
| Selected settings | 0.906 s, 0.906 s | 0.906 s |

The [measurement record](../evaluation/results/ort_session_tuning_excerpt.json)
preserves the profile settings, matching annotation fingerprints, CPU/runtime
versions and original report hash. The request contained 620 Japanese characters
and produced 351 tokens; each profile had one warmup and two timed requests on
a 16-logical-CPU Windows machine. These figures describe that session-tuning run.

## Code map

| Concern | Implementation |
|---|---|
| Export and artifact assembly | [Compressed-runtime builder](../pipeline/models/build_trankit_compressed_runtime_artifacts.py) |
| Adapter tensors, quantization and ONNX execution | [trankit_compressed_runtime.py](../../trankit_compressed_runtime.py) |
| Language policy and dictionary-first decoding | [language_registry.py](../../language_registry.py) |
| Runtime session profiles | [Session tuner](../pipeline/models/tune_trankit_onnx_ort_session.py) |
| Process isolation, device comparison and profiling | [Benchmark modules](../evaluation/benchmarks/trankit_benchmark/README.md) |
| Corpus and model selection | [Build chains](../pipeline/README.md), [selected resources](../STATUS.md) |
