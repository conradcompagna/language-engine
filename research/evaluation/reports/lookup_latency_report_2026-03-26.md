# Lookup Latency Report

Date: 2026-03-26

## Test Case

- Input: the Arabic paragraph starting with `الزُّكام أو الرَّشح...`
- Route: `/lookup`
- Flags: `lang=ar`, `merge_greedy=1`, `split_fill=1`, `pos_override=1`, `stanza_ner=1`, `collapse_ner_spans=1`, `dp_resegment=1`, `debug_capture=0`, `strip_punctuation=0`
- Method: one live request through the Flask test client, plus a heavily instrumented follow-up profile for hotspot attribution

## Bottom Line

- The debug path is not the bottleneck when capture is off.
- The real latency cost is still in segmenter-side candidate generation and normalization, especially `_build_span_key_matrix()` and `_normalize_key()`.
- First-lookup warmup exists, but it is small compared with the segmenter work on this paragraph.

## End-to-End Result

- Cold request status: `200`
- Cold request elapsed time: about `14.1 s`
- Segments: `16`
- `results_by_seg`: `16`
- `results`: `1`
- Response size: about `2.0 MB`

## Stage Breakdown From the Cold Request

- `router._build_merged_lookup_payload` + `router._build_results_by_seg` + `router._build_segment_result`: about `13.3 s`
- `segmenter.build_surface_lemma_aware_lookup` + `segmenter.fill_token` + `segmenter._greedy_fill_simple`: about `13.25 s`
- `segmenter._build_span_key_matrix`: about `9.0 s`
- `segmenter._prefetch_candidate_keys`: about `4.0 s` across `37` calls
- `segmenter.lookup_candidate_rows_for_normalized_keys`: about `3.4 s` across `10` calls
- `router.run_with_universal_normalization` + `router.run_trankit`: about `0.76 s`
- `router.process_lookup_nlp_only` on the debug-off path: about `0.2 ms`

## What Is Not the Issue

- `debug_capture=0` does short-circuit the debug snapshot branch.
- The `/debug/*` blueprint is registered globally, but normal lookup does not hit it when debug capture is off.
- `lookup_all()` itself is not the major cost in this paragraph.
- Lazy loading and first-hit initialization exist, but they are not the dominant source of latency here.

## Main Hotspots

### 1. Span-key generation

`_build_span_key_matrix()` is the largest single cost. It normalizes every candidate substring span, which means the request spends a lot of time generating lookup keys before DP can even score candidates.

### 2. Repeated normalization

`_normalize_key()` is heavily exercised. In the instrumented profile it was called about `418,964` times, which makes normalization and its language checks a bigger CPU cost than SQLite I/O.

### 3. Candidate prefetch work

`_prefetch_candidate_keys()` is still doing substantial work, and `lookup_candidate_rows_for_normalized_keys()` is not free. The architecture is improved compared with the earlier state, but the request is still not a truly single-pass “collect all spans once, score entirely in memory” flow.

### 4. Per-language predicate checks

The language-specific helpers inside normalization, such as `_is_urdu()`, `_is_chinese()`, `_is_persian()`, `_is_indic()`, `_is_sanskrit()`, `_is_arabic_script()`, `_is_japanese()`, `_is_hebrew()`, `_is_turkish()`, `_is_thai()`, and `_is_arabic()`, show up in the profile because they are evaluated many times across the span-normalization loop.

## Interpretation

The current lookup path is still spending most of its time on span enumeration and key normalization, not on debug capture, not on NLP, and not primarily on SQLite query latency. The request shape here is large enough that the cost of generating and normalizing candidate spans dominates everything else.

## Notes

- The second, heavily instrumented profile is useful for identifying hotspots, but its absolute wall-clock time is inflated by instrumentation overhead.
- The cold request is the best number to use as the real end-to-end latency baseline for this paragraph.
