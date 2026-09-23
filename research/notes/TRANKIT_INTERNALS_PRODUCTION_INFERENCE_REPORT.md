# Trankit Internals And Remaining Production Inference Optimizations

## Scope

This development report records the shared ONNX graph, runtime adapter packs, and
remaining optimization opportunities at the time of inspection. It documents the
reasoning behind the inference work; see the maintained [architecture guide](../../docs/ARCHITECTURE.md)
for the published application.

Files inspected:

```text
trankit_dual_device_benchmark_app.py
sandbox_trankit_compressed_runtime.py
build_trankit_compressed_runtime_artifacts.py
language_registry.py
C:\Users\conra\AppData\Local\Programs\Python\Python312\Lib\site-packages\trankit\pipeline.py
C:\Users\conra\AppData\Local\Programs\Python\Python312\Lib\site-packages\trankit\models\base_models.py
C:\Users\conra\AppData\Local\Programs\Python\Python312\Lib\site-packages\trankit\iterators\*.py
C:\Users\conra\AppData\Local\Programs\Python\Python312\Lib\site-packages\trankit\models\lemma_model.py
C:\Users\conra\AppData\Local\Programs\Python\Python312\Lib\site-packages\trankit\models\mwt_model.py
C:\Users\conra\AppData\Local\Programs\Python\Python312\Lib\site-packages\trankit\models\classifiers.py
C:\Users\conra\AppData\Local\Programs\Python\Python312\Lib\site-packages\trankit\layers\seq2seq.py
```

No Trankit model load or inference run is required for this report. This is a static code-path report.

## Current Benchmark App Reality

The test app currently starts only these workers at server startup:

```text
onnx_cpu
gpu
```

The page should not serve until both required workers report ready. The old `cpu_opt` and `gpu_opt` paths still exist in the file, but they are not the active startup path.

The active comparison is:

```text
ONNX dynamic INT8 CPU Trankit-ish runtime
then
regular current GPU Trankit runtime
```

Important: the regular GPU comparator is not a pristine upstream Trankit install. It loads `language_registry.py`, so the runtime monkey patches in `language_registry.py` apply there too. It is "regular GPU" relative to the app's current Trankit runtime, not a totally unmodified upstream Trankit package.

## What Is Already Implemented

### Done: one shared ONNX XLM-R graph with runtime adapter packs

Implemented in:

```text
sandbox_trankit_compressed_runtime.py
build_trankit_compressed_runtime_artifacts.py
```

Current architecture:

```text
one shared XLM-R ONNX graph
adapter weights passed as runtime inputs
one compressed adapter pack per language/task
PyTorch task heads remain outside ONNX
```

This avoids hundreds of full XLM-R ONNX graphs. It preserves Trankit's adapter-swapping design by selecting a compressed adapter pack when Trankit asks to load:

```text
tokenizer
tagger
ner
```

### Done: ONNX graph optimization and dynamic INT8 for XLM-R

The artifact builder creates:

```text
.trankit_compressed_runtime/xlmr_dynamic_adapters_fp32.onnx
.trankit_compressed_runtime/xlmr_dynamic_adapters_optimized.onnx
.trankit_compressed_runtime/xlmr_dynamic_adapters_dynamic_int8.onnx
```

The build path is:

```text
export FP32 ONNX
run ONNX Runtime graph optimization
run ONNX Runtime dynamic INT8 quantization
```

So the report should not list "make ONNX dynamic INT8" as remaining. It is already the current ONNX CPU path.

### Done: compressed adapter packs

Each language/task adapter pack stores the Trankit adapter tensors in compressed form:

```text
down_weight_q
down_weight_scale
down_bias_q
down_bias_scale
up_weight_q
up_weight_scale
up_bias_q
up_bias_scale
```

The runtime feeds those adapter tensors into the shared ONNX graph.

### Done: PyTorch dynamic INT8 for remaining task modules

The ONNX CPU runtime dynamically quantizes supported PyTorch modules left outside ONNX:

```text
tokenizer head
tagger / dependency head
NER head
lemma model
MWT model
```

Target module types:

```text
Linear
LSTM
GRU
LSTMCell when available
```

So the report should not say "quantize seq2seq" as a remaining top item. The current ONNX CPU runtime already tries to quantize those supported PyTorch modules.

### Done: seq2seq dictionary early-exit for lemma and MWT

Implemented in:

```text
language_registry.py
```

The lemmatizer patch checks Trankit's own lemma dictionaries first:

```text
composite_dict
word_dict
```

It sends only dictionary misses to seq2seq, then reassembles the output in original order.

The MWT patch checks:

```text
expansion_dict
```

It sends only expansion misses to seq2seq, then reassembles the output in original order.

So "seq2seq dictionary early-exit" is already implemented and should not appear as a remaining item. What remains is only further tuning around the remaining miss set.

### Done: XLM-R hidden-state output disabled in optimized paths

Upstream Trankit creates XLM-R with:

```text
output_hidden_states=True
```

but Trankit only uses the final hidden state.

The benchmark app patches XLM-R loading so optimized paths request:

```text
output_hidden_states=False
```

The ONNX artifact builder also disables XLM-R hidden states before export.

So "disable hidden states" is already done for the benchmark app's optimized ONNX CPU path.

### Done: tokenizer dynamic padding for ONNX CPU

Upstream Trankit tokenizer pads every tokenizer example to the configured maximum input length before batching.

The benchmark app patches:

```text
TokenizeDatasetLive.numberize()
TokenizeDatasetLive.collate_fn()
```

so tokenizer examples are padded only to the longest example in the actual batch.

This is already implemented for the ONNX CPU worker.

### Done: POS/NER length sorting and dynamic batch planning

Upstream POS/dep and NER already pad to the longest item in the batch, but examples can be badly grouped.

The benchmark app now:

```text
sorts tokenizer/POS/NER examples by wordpiece length
patches trankit.pipeline.DataLoader in the ONNX worker only
computes dynamic batch partitions per request
chooses batches using padded-token cost + estimated ONNX-call overhead
records dynamic batch decisions in the UI
```

This does not touch:

```text
MWTDataLoader
LemmaDataLoader
```

MWT and lemma remain on the separate seq2seq path. They are optimized by dictionary early-exit and PyTorch dynamic INT8, not by the ONNX XLM dynamic batch planner.

So "tokenizer bucketing" and "per-request dynamic batching" are no longer remaining design items. They are implemented in the test app. Runtime validation with real inputs is still needed, but the code exists.

### Done: per-task timing, batch, padding, ONNX/PyTorch split metrics

The app reports, per task:

```text
total task time
batch count
items per batch
padded units
real units
fake padding units
per-batch padding details
XLM/head/seq2seq call counts
ONNX Runtime time
ORT session time
handoff time
PyTorch/other time
```

This is enough to identify whether remaining latency is in:

```text
ONNX XLM-R
PyTorch seq2seq/head work
Python postprocessing
padding/batching
handoff/conversion
```

### Done: manual sentence segmentation no longer forces one document per sentence

The runtime manual sentence tokenizer now combines manual sentence spans into one tokenizer document and replaces internal newlines with spaces before tokenization. This avoids the previous behavior where line/paragraph boundaries caused many tiny tokenizer documents and much higher latency.

## What Is Actually Left To Optimize

This section lists only items not already solved by the current test app/runtime path.

## 1. ONNX Runtime session and thread tuning

Status:

```text
not done
high priority
accuracy-preserving
```

Current runtime creates the ORT session roughly as:

```python
ort.InferenceSession(str(session_path), providers=["CPUExecutionProvider"])
```

That means the benchmark is not yet tuning:

```text
intra_op_num_threads
inter_op_num_threads
execution_mode
enable_cpu_mem_arena
enable_mem_pattern
provider options
ORT graph optimization level at runtime
```

Why this matters:

```text
XLM-R CPU inference is mostly matrix multiplication and memory bandwidth.
Bad ORT thread settings can waste cores, oversubscribe threads, or increase latency jitter.
```

What to implement next:

```text
At ONNX worker startup, create several ORT sessions with different SessionOptions.
Run a small representative benchmark through each session.
Keep the fastest p95 session.
Report the selected ORT profile in the UI.
```

Candidate profiles:

```text
intra_op: 1, 2, 4, 8, physical_core_count
inter_op: 1
execution_mode: ORT_SEQUENTIAL first
graph_optimization_level: ORT_ENABLE_ALL
enable_cpu_mem_arena: true/false
enable_mem_pattern: true/false
```

Expected value:

```text
moderate to large, depending on CPU
```

## 2. Empirical calibration for the dynamic batch planner

Status:

```text
partially done
medium/high priority
accuracy-preserving
```

The app now has dynamic batch planning, but the cost model still uses fixed constants:

```text
ONNX_DYNAMIC_TOK_CALL_OVERHEAD_UNITS = 768
ONNX_DYNAMIC_TAG_CALL_OVERHEAD_UNITS = 768
```

That is better than one global batch size, but it is still a heuristic.

What remains:

```text
Measure real ONNX call overhead and real per-token cost per task.
Use those measured coefficients in the planner.
Store separate coefficients for tokenizer, tagger, and NER.
Possibly store separate coefficients per language family if data shows it matters.
```

Why this matters:

```text
Sometimes one larger batch is faster despite more padding.
Sometimes two smaller batches win because padding explodes.
The correct break-even point is hardware- and task-dependent.
```

Expected value:

```text
small to moderate normally
large for pathological mixed-length inputs
```

## 3. Fixed-shape ONNX bucket exports

Status:

```text
not done
medium priority
accuracy-preserving before quantization, drift-sensitive after quantization
```

Current ONNX graph uses dynamic axes:

```text
batch_size
sequence_length
```

This keeps one model flexible, but dynamic shapes can block some runtime optimizations.

Remaining experiment:

```text
Export bucketed ONNX graphs:
  64
  128
  256
  400 or 512

Route each batch to the smallest graph that fits.
Keep the same runtime adapter input architecture.
```

Why this may help:

```text
Fixed shapes can improve kernel selection, memory planning, and graph optimization.
They also make dynamic batch planning more predictable.
```

Why this may not help:

```text
More sessions in memory.
More artifact complexity.
Dynamic adapter inputs may still block some fusions.
```

Expected value:

```text
unknown until measured; plausible moderate win
```

## 4. Runtime adapter inputs limit graph optimization

Status:

```text
known architectural tradeoff
not solved
only worth optimizing for hot languages/tasks
```

The current architecture passes adapter tensors as runtime ONNX inputs. That is what avoids one graph per language/task.

Cost:

```text
ORT cannot treat adapter weights as static constants.
Adapter matmul weights cannot be prepacked the same way static initializers can.
Adapter dequantization/cast/multiply happens inside the graph each call.
```

Likely impact:

```text
small to moderate, because adapters are small compared with XLM-R
```

Remaining options:

```text
Option A: keep current dynamic-adapter graph for all languages.
Option B: build static baked-adapter ONNX graphs only for hot language/task pairs.
Option C: keep dynamic adapter graph, but benchmark FP32 adapter inputs vs INT8 adapter inputs if adapter dequantization overhead is visible.
```

Production recommendation:

```text
Do not build static graphs for every language/task unless measurements prove it is needed.
Use static baked graphs only for high-traffic languages where latency justifies memory/artifact cost.
```

## 5. Seq2seq miss-set batching and length bucketing

Status:

```text
not done
medium priority for decoder-heavy languages
accuracy-preserving if output order is restored exactly
```

What is already done:

```text
dictionary early-exit
dynamic INT8 quantization for LSTM/Linear seq2seq modules
```

What remains:

```text
For the remaining dictionary misses, batch by character length.
Avoid putting a very long word in the same seq2seq batch as many short words.
Keep a global index map so outputs return to original token order.
```

Why this matters:

```text
LemmaDataLoader and MWTDataLoader chunk data before sorting inside each batch.
They sort inside a batch, but they do not globally bucket the miss set before chunking.
```

Expected value:

```text
small if dictionary hits are high
moderate if many misses remain
large only for pathological length mixtures
```

## 6. Seq2seq early-exit metrics are not surfaced enough

Status:

```text
instrumentation gap, not model optimization
```

The patches record:

```text
_lemma_early_exit_last
_mwt_early_exit_last
```

but the test app UI does not yet clearly show:

```text
lemma total
lemma dict hits
lemma seq2seq misses
MWT total
MWT dict hits
MWT seq2seq misses
```

Why this matters:

```text
If seq2seq is still slow, the first question is whether the miss rate is high.
Without hit/miss metrics, it is easy to optimize the wrong thing.
```

Expected value:

```text
no direct speedup, but high diagnostic value
```

## 7. ONNX input/output binding and conversion cleanup

Status:

```text
not done
lower priority unless handoff metrics rise
```

Current ONNX shim does:

```python
input_ids.detach().cpu().numpy()
attention_mask.detach().cpu().numpy()
self.session.run(...)
torch.from_numpy(output).to(...)
```

For the ONNX CPU worker, this is usually cheap because tensors are already CPU-side, and your recent metrics showed handoff near zero. But it is still a possible cleanup target.

Potential improvements:

```text
use ONNX Runtime I/O binding
avoid redundant device/dtype conversions
reuse input/output buffers where shapes repeat
```

Expected value:

```text
low unless metrics show handoff/postprocess time is meaningful
```

## 8. Python postprocessing after model calls

Status:

```text
not solved
profile-dependent
accuracy-preserving only if exact outputs are maintained
```

Remaining Python-heavy pieces:

```text
dependency MST decoding
NER Viterbi decoding
deep copies
dict/list reconstruction
offset remapping
manual sentence regrouping
```

Known Trankit internals:

```text
POS/dependency converts dependency scores to CPU NumPy and calls Chu-Liu/Edmonds per sentence.
NER CRF prediction converts logits/transitions to CPU NumPy and runs Viterbi per sentence.
```

What to do:

```text
Use the current task breakdown first.
If "PyTorch/other" is a large share after ONNX time falls, profile these exact functions.
Only then consider Cython/Rust/Numba/vectorized exact replacements.
```

Expected value:

```text
small for model-dominated requests
moderate for many-short-sentence requests
```

## 9. GPU production path still has unfixed upstream Trankit overhead

Status:

```text
not relevant to current ONNX CPU path
still relevant if production stays GPU
```

The current active comparison keeps regular GPU as the app's current Trankit runtime. The optimized ONNX CPU worker suppresses request-time cleanup calls through its optimized path; the regular GPU comparator does not.

If production stays GPU, remaining safe GPU work includes:

```text
remove request-time torch.cuda.empty_cache()
wrap full request path in torch.inference_mode()
keep hidden states disabled
keep seq2seq dictionary early-exit
check FP16 coverage
reduce CPU sync points where possible
```

Expected value:

```text
small to moderate
not the dramatic compression path
```

## 10. Static quantization or selective precision policy

Status:

```text
not done
accuracy/drift tradeoff
```

Current ONNX path uses dynamic INT8. Remaining experiments:

```text
static INT8 calibration for XLM-R
per-task quantization policy
FP32 tokenizer + INT8 POS/NER
INT8 tokenizer + FP32 selected heads
```

Why this matters:

```text
Tokenizer drift can cascade into sentence/token/POS/NER differences.
If tokenization drift is unacceptable, tokenizer XLM-R may need higher precision than POS/NER.
```

Expected value:

```text
speed could improve with static INT8
accuracy drift must be measured per language/task
```

## Current Biggest Remaining Speed Targets, Ordered

### 1. ORT session/thread tuning

This is the biggest pure speed target not yet implemented. It does not change model output.

### 2. Calibrated dynamic batch planner

The current planner is structurally right, but it needs measured per-task coefficients instead of fixed overhead constants.

### 3. Fixed-shape ONNX bucket exports

This is the biggest remaining ONNX-engine experiment. It adds complexity but may unlock more runtime optimization.

### 4. Seq2seq miss-set length bucketing

Early-exit and INT8 are already done. The next seq2seq target is batching only the remaining misses more intelligently.

### 5. Python postprocessing if metrics prove it is large

Do this only after task breakdown shows `PyTorch/other` is a real bottleneck.

### 6. Static hot-language graphs

Do this only for high-traffic language/task pairs if the dynamic adapter graph is still too slow.

## Things That Should No Longer Be Listed As Remaining

These have already been implemented in the current app/runtime path:

```text
seq2seq dictionary early-exit
dynamic INT8 for seq2seq/task modules in ONNX CPU runtime
ONNX dynamic INT8 XLM-R
compressed adapter packs
one shared adapter-aware ONNX graph
XLM-R hidden states disabled
tokenizer dynamic padding
tokenizer/POS/NER length grouping
per-request dynamic batch partitioning
task timing breakdown
ONNX/PyTorch timing split
per-batch padding metrics
startup preload of ONNX CPU and GPU workers
manual sentence segmentation packed into one tokenizer document
```

## What The Current Test App Can Already Tell You

Use the current UI metrics this way:

```text
If ONNX runtime dominates:
  tune ORT sessions, fixed-shape buckets, static hot graphs.

If fake padding dominates:
  inspect dynamic batch planner events and tune/calibrate planner coefficients.

If PyTorch/other dominates in lemma/MWT:
  inspect seq2seq early-exit hit/miss rate, then bucket seq2seq misses.

If PyTorch/other dominates in POS/NER:
  profile dependency MST, CRF/Viterbi, and Python reconstruction.

If handoff dominates:
  try ONNX I/O binding and buffer reuse.

If output mismatch is mostly tokenizer/sentence drift:
  test FP32 tokenizer path or selective precision.
```

## Production Readiness Assessment

The ONNX CPU sandbox is no longer just a toy XLM-R export. It is now an architecture-compatible prototype:

```text
shared XLM-R graph
runtime Trankit adapter packs
Trankit task heads still used
Trankit MWT/lemma still used
all languages covered by adapter packs
regular GPU comparator still available
```

But it is not production-ready until these are resolved:

```text
accuracy/drift thresholds per language
ORT session tuning
dynamic batch planner calibration
startup artifact/version validation
clear fallback policy, or no fallback policy
production integration plan
```

The remaining work is no longer "make Trankit use ONNX" or "quantize XLM-R." Those are done in the sandbox. The remaining work is tuning the ONNX runtime, tuning batching from real measurements, validating drift, and cleaning up the remaining Python/seq2seq hot spots only where the current metrics prove they matter.
