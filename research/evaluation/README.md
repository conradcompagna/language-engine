# Evaluation

## Regression

`test_mwt_realign_dp.py` — the multi-word-token realignment regression. This covers the
dynamic-programming alignment between a tokenizer's surface tokens and an expander's
underlying tokens, which is the step most likely to break silently when a model is
swapped. It passes against the current runtime.

## Benchmarks

| Script | Measures |
|---|---|
| `benchmarks/memory_probe.py` | resident memory per loaded language, used to decide how many models can be held at once |
| `benchmarks/trankit_dual_device_benchmark_app.py` | CPU vs GPU inference across the pipeline stages |
| `benchmarks/profile_sqlite_segmenter.py` | segmentation cost against dictionary size |
| `benchmarks/compare_arabic_tokenization.py` | shipped Arabic tokenizer against CAMeL Tools as an external reference |
| `benchmarks/run_crusades_comparison.py`, `analyze_comparison.py`, `realign_comparison.py` | end-to-end pipeline comparison on a fixed historical text |
| `benchmarks/tag_overlap_analysis.py` | agreement between tagsets across models |

## Reports

`reports/` holds the audits that gated dictionary and pipeline changes. The substantial
ones:

- `dictionary_sqlite_port_function_audit_2026-03-27.md` — function-by-function audit of
  the port from the TSV-era lookup to the SQLite lookup, with the gap report alongside it
- `wiktionary_form_tags_audit_2026-04-11.md`, `wiktionary_forms_surface_audit_2026-04-11.md`
  — what Wiktionary's form tags actually contain, across languages
- `headword_non_script_marks_master.md` — headwords carrying marks outside their own
  script, the cause of a long tail of lookup misses
- `grc_lsj_vs_wiktionary_samples.md` — Liddell–Scott–Jones against Wiktionary for
  Ancient Greek
- `lookup_latency_report_2026-03-26.md`, `lookup_latency_report_2026-03-27_arabic_sqlite.md`
  — the measurements behind the hybrid lookup design
- `transparency_attribution_inventory.md` — source and licence inventory for every
  dictionary
- `mwt_child_authority_audit_report.md` — which of a multi-word token's children may
  override the parent's analysis

## Browser probes

`browser_probes/` holds the devtools scripts used to inspect reader behaviour in a live
page: entry provenance, dictionary download, save and cancel paths, headword rendering.
