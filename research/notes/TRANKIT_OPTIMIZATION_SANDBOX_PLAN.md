# Trankit CPU/GPU Optimization Sandbox Plan

## Goal

Build a controlled benchmark layer inside `trankit_dual_device_benchmark_app.py` that can test aggressive Trankit CPU and GPU inference optimizations without touching the production Flask app, without changing `language_registry.py`, and without running Trankit unless the standalone benchmark app is explicitly launched by a human.

The target is not a small 5 percent cleanup. The target is to identify whether stacked runtime, PyTorch, quantization, and export optimizations can cut real end-to-end Trankit latency by 2x to 10x, and to prove which optimizations are real on this exact pipeline.

## Current Test App Baseline

The standalone benchmark app already has the right foundation:

- It is a separate Flask app: `trankit_dual_device_benchmark_app.py`.
- It does not import or load Trankit in the parent Flask process.
- It uses subprocesses for CPU and GPU workers.
- It can run CPU then GPU sequentially to avoid direct timing contention.
- It has cold-start probes for:
  - shared XLM-R load only
  - selected language module load only
  - full all-language pipeline load
- It reports process wall time, Trankit load time, first inference time, RSS, and CUDA memory snapshots.

The main limitation is that the app currently measures mostly vanilla Trankit behavior. It does not yet provide controlled optimization profiles or stage-level timings for the real inference path.

## Non-Negotiable Constraints

The sandbox must follow these rules:

- No changes to the main app runtime.
- No changes to production routes in `router.py`.
- No changes to active lookup behavior in `dictionary_client_hybrid.js`, `reader.js`, or `pipeline_common.py`.
- No Trankit import in the benchmark parent process.
- No Trankit load on page visit.
- No Trankit run unless the user clicks a benchmark button.
- Optimization experiments must run in fresh subprocesses first.
- Failed experiments must not corrupt the long-lived baseline CPU/GPU workers.
- Every benchmark result must say exactly which optimizations were active.

## What "Speedup" Means

The report and UI should use latency terms precisely:

- "Inference latency" means wall-clock time for a request.
- "Cold-start latency" means process start plus import plus model load plus optional first inference.
- "Warm inference latency" means model already loaded, request starts at the analysis call.
- "Optimization overhead" means time spent compiling, quantizing, patching, warming up, or converting models before useful inference.

The app should report:

- p50 latency for repeated warm runs
- p95 latency for repeated warm runs
- p99 latency if enough repetitions are requested
- first inference after load
- first warmup-excluded measured inference
- mean latency
- best latency
- worst latency
- speedup ratio against baseline

Do not use only one request as proof. Single-request numbers are useful for debugging, not decision-making.

## Benchmark Design

Add a new optimization benchmark path that is separate from the existing `/api/analyze` path.

Recommended route:

```text
POST /api/optimization_probe
```

Recommended UI button:

```text
Optimization Probe
```

The route should spawn fresh subprocesses. Each subprocess should:

1. Start clean.
2. Import Torch.
3. Apply environment/thread settings before model load where possible.
4. Force CPU or GPU Trankit mode.
5. Import `language_registry`.
6. Load the full current app Trankit pipeline.
7. Apply the selected optimization profile.
8. Run one or more warmup inferences.
9. Run repeated measured inferences.
10. Return timings, memory metrics, output checks, optimization errors, and active settings.

The first version should not mutate the persistent CPU/GPU workers. Keep optimization experiments disposable.

## Result Shape

Each optimization probe should return one object per device and profile:

```json
{
  "profile": "baseline",
  "device": "cpu",
  "ok": true,
  "actual_device": "cpu",
  "load_seconds": 0.0,
  "optimization_seconds": 0.0,
  "warmup_seconds": [0.0],
  "measured_seconds": [0.0, 0.0, 0.0],
  "p50_seconds": 0.0,
  "p95_seconds": 0.0,
  "best_seconds": 0.0,
  "worst_seconds": 0.0,
  "rss_after_load_bytes": 0,
  "rss_peak_bytes": 0,
  "gpu_after_load": {},
  "gpu_peak": {},
  "active_optimizations": {},
  "stage_timings": [],
  "output_fingerprint": "",
  "errors": []
}
```

For comparing outputs, do not dump huge annotation blobs into every optimization result. Store a compact fingerprint:

```text
hash(canonical_json(annotation))
```

Also return small counts:

```text
sentence_count
token_count
ner_count
dependency_edge_count
```

If an optimization changes the fingerprint, the UI should mark it as an accuracy/output-change risk.

## UI Plan

Keep the UI simple. Add one new panel, not a large configuration system.

Controls:

- Optimization profile dropdown:
  - baseline
  - tier0_runtime
  - cpu_dynamic_int8
  - cpu_thread_sweep
  - torch_compile
  - gpu_runtime
  - gpu_autocast
  - all_safe_runtime
- Repetitions input, default 5.
- Warmup runs input, default 1.
- CPU thread values input, only used by thread sweep.
- Run optimization probe button.

Output:

- CPU baseline latency
- CPU optimized latency
- CPU speedup
- GPU baseline latency
- GPU optimized latency
- GPU speedup
- load time
- optimization setup time
- warmup time
- p50/p95
- memory deltas
- output fingerprint match/mismatch
- errors by attempted optimization

The app should not imply success because a patch was applied. It should only report speedup when measured output is valid and the request completes.

## Profile 1: Baseline

Purpose:

Measure current unmodified Trankit behavior in a fresh subprocess.

Actions:

- Force CPU or GPU with the existing Trankit pipeline patch.
- Load `language_registry.init_trankit()`.
- Run warmup.
- Run repeated measured inference.
- Use the current app path through `run_with_universal_normalization()` and `lr.run_trankit()`.

This is the denominator for every speedup claim.

## Profile 2: Tier 0 Runtime Patches

Purpose:

Test low-risk runtime changes that should not affect model output.

Actions:

- Wrap inference in `torch.inference_mode()`.
- Ensure all neural modules are in `.eval()`.
- Patch `torch.cuda.empty_cache()` to a no-op during request-time inference.
- Patch `gc.collect()` to a no-op during request-time inference.
- Keep CUDA synchronization only around measurement boundaries.
- Record whether Trankit or the wrapper attempted to call `empty_cache()` or `gc.collect()`.

Important:

The benchmark app itself currently calls `_force_gc()` and `torch.cuda.empty_cache()` in the worker inference path. The optimization probe must be able to disable those app-level calls too, otherwise it will not honestly measure the effect of removing Trankit's hot-path cleanup.

Expected value:

- CPU: small to moderate.
- GPU: potentially large if `empty_cache()` is causing CUDA synchronization and allocator churn.
- Tail latency may improve more than mean latency.

Validation:

- Output fingerprint should match baseline.
- Memory should be watched carefully because disabled cleanup can increase reserved CUDA memory.

## Profile 3: CPU Thread Sweep

Purpose:

Find the best CPU threading configuration for latency, not theoretical throughput.

Actions:

- In a fresh subprocess, before model load:
  - set `OMP_NUM_THREADS`
  - set `MKL_NUM_THREADS`
  - call `torch.set_num_threads(N)`
  - call `torch.set_num_interop_threads(1)`
- Test values:
  - 1
  - 2
  - 4
  - 8
  - physical core count

Do not assume physical core count is optimal. For a web server, multiple lower-thread workers can beat one high-thread worker.

Expected value:

- CPU: potentially meaningful.
- GPU: mostly irrelevant except CPU preprocessing/tokenization.

Validation:

- Output fingerprint should match baseline.
- Record CPU model, logical cores, process count, and chosen thread counts if available.

## Profile 4: CPU Dynamic INT8 Quantization

Purpose:

Test the easiest serious CPU model-speed optimization.

Actions:

- CPU only.
- After pipeline load, apply dynamic quantization to selected modules:
  - `torch.nn.Linear`
  - possibly `torch.nn.LSTM`
  - possibly `torch.nn.GRU`
- Start conservatively with task heads first:
  - tokenizer classifier
  - POS/dependency classifier
  - NER classifier
- Then separately test quantizing the shared embedding module.

Do not combine every quantization target in the first pass. Use separate subprofiles:

```text
cpu_int8_heads_only
cpu_int8_embedding_only
cpu_int8_embedding_plus_heads
```

Expected value:

- Could be 1.2x to 2x in PyTorch dynamic quantization.
- Bigger gains likely require ONNX Runtime INT8 or OpenVINO INT8.

Risks:

- Some Trankit adapter-transformer modules may not quantize cleanly.
- Output may change.
- Unsupported modules may silently remain FP32.

Validation:

- Compare output fingerprint.
- Compare token count, lemma count, UPOS counts, NER counts, dependency edge count.
- Report which modules actually changed type after quantization.

## Profile 5: CPU BF16 Autocast

Purpose:

Test BF16 on CPUs that support it without bluntly converting the whole model.

Actions:

- CPU only.
- Wrap inference:

```python
with torch.inference_mode(), torch.autocast("cpu", dtype=torch.bfloat16):
    ...
```

- Report whether CPU BF16 appears available.
- Do not assume availability on all CPUs.

Expected value:

- Potentially meaningful on modern Intel CPUs with BF16/AMX support.
- Less predictable on AMD depending on CPU generation and PyTorch backend.

Validation:

- Output fingerprint may change slightly.
- If output changes, inspect whether changes affect only confidence/order or actual labels/lemmas.

## Profile 6: Torch Compile

Purpose:

Test whether PyTorch 2 compilation helps Trankit's neural modules.

Actions:

- Do not compile the full Trankit `Pipeline`.
- Compile submodules only:
  - shared embedding module
  - tokenizer classifier
  - POS/dependency classifier
  - NER classifier
- Use:

```python
torch.compile(module, mode="reduce-overhead")
```

- Optionally test `max-autotune` separately for GPU only.
- Record compile/setup time separately from inference time.

Expected value:

- CPU: possible but uncertain.
- GPU: possible 1.2x to 1.6x if dynamic Python and shape variation do not dominate.

Risks:

- Windows support and backend availability may be a blocker.
- Dynamic shapes may erase gains.
- First compiled calls may include compilation overhead.
- Some Trankit modules may break graph capture.

Validation:

- Output fingerprint should match baseline.
- Benchmark must exclude compile time from warm inference latency, but still report compile time because it matters for cold start.

## Profile 7: GPU Runtime Patches

Purpose:

Test cheap GPU-side runtime settings that should not require model export.

Actions:

- Wrap inference in `torch.inference_mode()`.
- Keep Trankit's existing `.half()` behavior as the default GPU baseline.
- Patch request-time `torch.cuda.empty_cache()` to no-op.
- Patch request-time `gc.collect()` to no-op.
- Enable TF32 only for remaining FP32 matmul paths:

```python
torch.backends.cuda.matmul.allow_tf32 = True
torch.backends.cudnn.allow_tf32 = True
```

- Treat `torch.backends.cudnn.benchmark = True` as low-priority metadata, not a major transformer optimization.

Expected value:

- Removing cleanup calls may be the largest Tier 0 GPU win.
- TF32 likely helps little if Trankit is already using FP16 for major modules.

Validation:

- Output fingerprint should match baseline unless precision behavior changes.
- Record GPU name, CUDA availability, allocated/reserved/peak memory, and whether actual device is CUDA.

## Profile 8: GPU Autocast vs Existing Half

Purpose:

Check whether autocast beats or stabilizes Trankit's existing `.half()` conversion.

Actions:

- Compare:
  - current Trankit `.half()`
  - autocast FP16 wrapper
  - no forced `.half()` plus autocast FP16, if feasible in the sandbox
  - BF16 autocast only on GPUs that truly support BF16

Expected value:

- FP16 is likely already the main path.
- Autocast may improve numerical safety more than speed.
- BF16 is only worth testing on GPUs with real BF16 tensor core support.

Risks:

- Disabling Trankit's `.half()` may require deeper monkey patching and may not be worth first-pass implementation.

Validation:

- Output fingerprint and per-field diffs.
- GPU memory usage, because FP32 fallback can increase memory.

## Profile 9: Trankit Adapter-Switch Instrumentation

Purpose:

Find out whether Trankit spends meaningful time switching adapter weights between language/task modules.

Actions:

- Monkey-patch and time:
  - `Pipeline._load_adapter_weights`
  - any calls that mutate shared embedding weights
  - task transitions tokenizer -> tagger -> lemmatizer -> NER
- Count adapter switches per request.
- Record adapter switch wall time and memory deltas.

Expected value:

- This could be one of the most important Trankit-specific findings.
- If adapter switching is expensive, model backend optimization alone will not deliver the expected speedup.

Potential follow-up experiments:

- Group requests by language/task.
- Keep separate warmed embedding modules for hot language/task pairs.
- Keep adapter state device-resident on GPU.

Validation:

- This is an instrumentation profile first. It should not alter output.

## Profile 10: Stage-Level Inference Timing

Purpose:

Measure exactly where time is going.

The app should time at least:

- universal normalization
- Trankit language resolution
- `set_active()` or active language switching
- tokenizer dataset construction
- tokenizer neural forward
- tokenizer post-processing
- MWT expansion
- POS/dependency dataset construction
- shared XLM forward
- POS/dependency classifier forward
- dependency MST decoding
- lemmatizer
- NER forward
- NER post-processing
- GPU to CPU transfer points
- `.cpu().numpy().tolist()` points
- final annotation construction

Implementation approach:

- Use monkey patches around Trankit functions/classes in subprocess only.
- Do not rewrite Trankit internals in the first pass.
- Record stage names, elapsed time, RSS delta, CUDA allocated/reserved delta, and call count.

Expected value:

This decides the whole strategy. If 70 percent of time is Python post-processing, ONNX will disappoint. If 70 percent is XLM-R forward, ONNX/TensorRT is worth the work.

## Profile 11: Fast Tokenizer Compatibility

Purpose:

Test whether replacing `XLMRobertaTokenizer` with `XLMRobertaTokenizerFast` is safe and faster.

Actions:

- In a fresh subprocess, monkey-patch tokenizer construction to use the fast tokenizer.
- Run baseline and fast-tokenizer outputs on the same text.
- Compare:
  - token surfaces
  - offsets
  - sentence boundaries
  - wordpiece counts
  - final annotation fingerprint

Expected value:

- Potentially large if tokenization/span reconstruction is CPU-bound.

Risks:

- Offset behavior may differ.
- Trankit may assume slow-tokenizer internals.
- A small offset mismatch can break reader highlighting.

Validation:

- This requires strict output comparison before considering it safe.

## Profile 12: Length Bucketing and Fixed Shapes

Purpose:

Prepare for compile, CUDA Graphs, ONNX Runtime, and TensorRT.

Actions:

- Add benchmark mode that runs the same input chopped into length buckets:
  - 64 tokens
  - 128 tokens
  - 256 tokens
  - 384 tokens
  - 512 tokens
- Pad within bucket where the underlying model path allows it.
- Measure padding overhead versus compiler/runtime gains.

Expected value:

- Small by itself.
- Important enabler for `torch.compile`, CUDA Graphs, ONNX profiles, and TensorRT profiles.

Risks:

- Harder to implement inside Trankit without deeper integration.

Validation:

- Output must preserve original token boundaries and sentence order.

## Profile 13: GPU Microbatching Prototype

Purpose:

Test whether the GPU is underfed by single requests.

Actions:

- In the sandbox only, create a synthetic microbatch benchmark:
  - same language
  - same task path
  - similar text lengths
  - 2, 4, 8, 16 queued requests
- Measure:
  - total wall time
  - per-request latency
  - throughput
  - GPU memory peak

Important:

This is not a single-user latency optimization unless requests are naturally concurrent. It is a hosting efficiency optimization.

Expected value:

- Could be large for throughput.
- May not improve single request latency.

Validation:

- Output fingerprint per request.
- Compare latency impact of 5 ms, 10 ms, and 20 ms queue windows in a later server prototype.

## Export Engine Phase

ONNX, OpenVINO, and TensorRT should not be the first implementation pass. They are real projects. The sandbox should first prove whether the model forward pass is actually the bottleneck.

If stage timings show XLM-R and classifier forward passes dominate, then add a second standalone export app or export module.

### ONNX Runtime CPU

Plan:

- Export shared XLM-R with adapter state included.
- Export task heads separately if needed.
- Run ONNX Runtime transformer optimizer.
- Benchmark:
  - ORT CPU FP32
  - ORT CPU dynamic INT8
  - ORT CPU static INT8 with calibration
  - ORT CUDA execution provider

Trankit caveat:

Because Trankit mutates adapter weights for language/task states, export is probably not one universal XLM-R engine. It is likely one engine per language/task adapter state, or a deeper refactor where adapters are modeled as explicit ONNX subgraphs.

### OpenVINO CPU

Plan:

- Test only if target hosting CPU is Intel or if OpenVINO benchmarks well on available hardware.
- Export FP32/BF16.
- Test INT8 via NNCF calibration.
- Compare against ONNX Runtime and IPEX.

### TensorRT GPU

Plan:

- Export ONNX first.
- Build TensorRT FP16 engines.
- Build TensorRT INT8 engines with calibration only after FP16 works.
- Use optimization profiles by length bucket:
  - 64
  - 128
  - 256
  - 384
  - 512

Trankit caveat:

Adapter switching means TensorRT engines may need to be per language/task adapter state. This can still be acceptable if the shared XLM-R dominates but languages/tasks are finite and known.

## Accuracy and Output Validation

Every optimization profile must be treated as unsafe until it proves output compatibility.

Minimum validation:

- Full annotation fingerprint.
- Sentence count.
- Token count.
- Token surface list.
- Lemma list.
- UPOS list.
- XPOS list.
- dependency head/deprel pairs.
- NER spans and labels.

For quantization and precision tests, exact output may change. That does not automatically mean failure, but it must be visible. The UI should say:

```text
Output match: yes/no
Changed fields: lemma, UPOS, deprel, NER, offsets
```

The reader app is offset-sensitive, so tokenizer or normalization changes require stricter validation than pure classifier precision changes.

## Memory Metrics

The benchmark should continue reporting:

- process RSS before import
- RSS after imports
- RSS after load
- RSS before inference
- RSS after inference
- sampled RSS peak during inference
- CUDA allocated before/after
- CUDA reserved before/after
- CUDA max allocated
- CUDA max reserved
- CUDA free/total memory

Add:

- optimization setup memory delta
- post-warmup memory state
- post-measured-runs memory state
- cleanup-call counts
- adapter-switch memory delta

For GPU, reserved memory increasing is not automatically bad. It can be PyTorch caching allocator doing useful work. The important metrics are latency, peak allocated memory, and whether the process remains stable over repeated runs.

## Cold Start Metrics

Cold start must be reported separately from warm inference.

Keep existing probes:

- shared XLM-R only
- selected language modules only
- full all-language pipeline

Add optimization cold-start costs:

- quantization setup time
- compile time
- warmup time
- export/load engine time if later implemented

For hosting decisions, the key number is:

```text
process start + imports + model load + optimization setup + required warmup
```

If a GPU worker scales to zero, this total is what users wait for unless the app prewarms the worker before the first analysis request.

## Implementation Order

### Pass 1: Measurement Integrity

Add:

- `/api/optimization_probe`
- baseline profile
- repeated warm runs
- output fingerprint
- p50/p95/best/worst
- clear UI comparison table

No real optimization yet. This makes the measurement harness trustworthy.

### Pass 2: Tier 0 Runtime Patches

Add:

- `torch.inference_mode()`
- `.eval()` verification
- no-op request-time `torch.cuda.empty_cache()`
- no-op request-time `gc.collect()`
- cleanup-call counters

This is likely the fastest useful test.

### Pass 3: CPU Tuning

Add:

- CPU thread sweep
- interop thread control
- OMP/MKL env settings before Torch work
- CPU dynamic INT8 profiles
- CPU BF16 autocast if supported

This decides whether optimized CPU can get close enough to GPU latency to avoid GPU hosting.

### Pass 4: GPU Runtime Tuning

Add:

- TF32 metadata/toggle for remaining FP32 paths
- autocast-vs-half probe
- GPU memory stability under repeated runs
- optional `torch.compile` on neural submodules

This decides whether vanilla GPU can become much faster without TensorRT.

### Pass 5: Trankit-Specific Instrumentation

Add:

- adapter switch timings
- tokenizer timing
- dataset construction timing
- neural forward timing
- CPU transfer timing
- dependency decoder timing
- NER and lemmatizer timing

This decides whether export engines are worth building.

### Pass 6: Export Feasibility

Only after stage timing proves model forward dominates:

- ONNX Runtime CPU/CUDA prototype
- ONNX INT8 prototype
- OpenVINO prototype if Intel CPU target
- TensorRT FP16 prototype
- TensorRT INT8 prototype

## Expected Decision Points

After Pass 2:

- If GPU latency drops sharply, hot-path cleanup was a major problem.
- If CPU and GPU barely move, continue to stage timing.

After Pass 3:

- If CPU dynamic INT8 plus thread tuning gives 2x or better, optimized CPU hosting becomes credible.
- If CPU remains far slower, look at ONNX/OpenVINO or GPU hosting.

After Pass 5:

- If XLM-R forward dominates, pursue ONNX/TensorRT.
- If tokenizer/post-processing dominates, pursue tokenizer replacement and Python-path cleanup.
- If adapter switching dominates, pursue adapter residency or request grouping.
- If dependency decoding dominates, optimize or move that stage separately.

## What Not To Do First

Do not start with TensorRT. It may be the biggest GPU win, but it is too expensive before stage timing proves model forward dominates.

Do not compile the entire Trankit pipeline. Compile submodules only.

Do not treat a single request as proof. Use repeated warm runs.

Do not treat speedup as valid if output changes silently.

Do not mutate the persistent workers with experimental monkey patches until the subprocess probe proves they work.

Do not benchmark cold-start and warm inference as one blended number.

## Practical Speedup Expectations

Possible realistic bands:

- Tier 0 cleanup: 1.05x to 2x, with GPU tail latency potentially improving more.
- CPU thread tuning: 1.1x to 1.8x depending on current defaults and hardware.
- CPU dynamic INT8: 1.2x to 2x if the right modules quantize.
- CPU ONNX/OpenVINO INT8: 2x to 5x if model forward dominates.
- GPU runtime tuning: 1.1x to 2x depending on cleanup, shapes, and precision path.
- GPU TensorRT FP16/INT8: 2x to 4x if export is feasible and model forward dominates.
- Combined best case: large speedups are plausible, but only if the bottleneck is neural forward or avoidable runtime overhead. If the bottleneck is Python orchestration, tokenizer spans, adapter mutation, or dependency decoding, backend engines alone will not produce 10x.

## Recommended First Implementation

The first code change should be small and direct:

1. Add `/api/optimization_probe`.
2. Add a subprocess worker for optimization probes.
3. Add baseline and `tier0_runtime` profiles only.
4. Add repeated warm-run timing.
5. Add output fingerprint comparison.
6. Add UI cards for baseline versus optimized speedup.

Once those numbers are reliable, add CPU dynamic INT8 and CPU thread sweep. Then add stage-level Trankit instrumentation. Export engines should wait until the sandbox proves they are the right target.

