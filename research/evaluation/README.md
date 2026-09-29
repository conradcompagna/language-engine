# Evaluation

Tests, benchmarks and recorded measurements for the Language Engine models and runtime.
The model development scores are summarised in [`../models/README.md`](../models/README.md).

| Path | Contents |
|---|---|
| `results/` | JSON score records for the selected tokenizer, MWT, parser, lemmatizer and NER components, and the ONNX session-tuning measurements |
| [`selected_components/`](selected_components/) | Scripts that re-evaluate saved checkpoints where the training logs did not keep the final score |
| `test_mwt_realign_dp.py` | Regression test for the dynamic-programming alignment between surface tokens and expanded MWT words |
| `benchmarks/` | Profiling and comparison scripts (below) |
| [`benchmarks/trankit_benchmark/`](benchmarks/trankit_benchmark/) | Browser-based CPU/GPU inference comparison tool |
| `browser_probes/` | Devtools scripts used to inspect reader behaviour in a live page (entry provenance, dictionary download, save and cancel, headword rendering) |
| `reports/grc_lsj_regeneration_summary.json` | Counts from regenerating the Ancient Greek LSJ dictionary database |

## Benchmarks

| Script | Measures |
|---|---|
| `memory_probe.py` | Resident memory per loaded language |
| `trankit_dual_device_benchmark_app.py` | Entry point for the CPU/GPU comparison tool |
| `profile_sqlite_segmenter.py` | Segmentation time against dictionary size |
| `compare_arabic_tokenization.py` | The selected Arabic tokenizer against CAMeL Tools |
| `run_crusades_comparison.py`, `analyze_comparison.py`, `realign_comparison.py` | End-to-end pipeline comparison on a fixed historical text |
| `tag_overlap_analysis.py` | Agreement between tag sets across models |

## ONNX session tuning

[`tune_trankit_onnx_ort_session.py`](../pipeline/models/tune_trankit_onnx_ort_session.py)
compared ONNX Runtime thread counts, execution mode and memory settings for the shared
INT8 encoder on one Japanese request (620 characters, 351 tokens) on a 16-thread Windows
machine, with one warm-up and two timed requests per setting.

| Configuration | Timed requests (s) | Mean (s) |
|---|---|---:|
| ONNX Runtime defaults | 1.914, 1.896 | 1.905 |
| Sequential execution, 8 intra-op threads, 1 inter-op thread, memory patterns off | 0.906, 0.906 | 0.906 |

Both settings produced identical annotations. The full record is
[`results/ort_session_tuning_excerpt.json`](results/ort_session_tuning_excerpt.json).
