# Reproducing checks and preparing new runs

Python 3.12 and the root `requirements-dev.txt` run the public fixtures:

```sh
python -m pytest tests/test_training_evidence.py tests/test_research_artifacts.py
python research/artifacts.py research/pipeline/dictionaries/japanese/data/rules/manifest.json
python research/pipeline/models/train_ner.py --help
python research/pipeline/models/build_trankit_xlmr_onnx_cpu.py --help
```

The synthetic Sanskrit lattice test converts distinct records into deterministic
train/dev CoNLL-U, checks token/lemma/POS alignment and repeatability, and creates
missing output directories. Dependency heads emitted by that converter are
structural placeholders for tokenizer training, not human dependency annotations.
The BIO preflight rejects empty/malformed corpora and exact cross-split duplicates.
See [NER commands and environment setup](pipeline/models/TRAINING_RUN.md).

The ONNX exporter and [benchmark](evaluation/benchmarks/trankit_benchmark/README.md)
share `TRANKIT_ONNX_CACHE_DIR`, `TRANKIT_ONNX_DEPS_DIRS` (platform path separator)
and `TRANKIT_CPU_OPT_DEPS_DIR`. Set them before starting either process; defaults
resolve relative to the benchmark directory. Exporting requires the full model
store and optional ONNX/PyTorch dependencies. `--help` and public tests do not
download models or start GPU workers.

Historical one-off scripts record earlier implementation methods. To reuse
`prep_trankit.py`, `apply_patch.py`, or the Greek monitoring helpers, adapt their
workstation paths and provide the referenced patch bundles first. The original
configuration and log files preserve the context of those runs. The
[evidence index](EVIDENCE.md) connects this record to datasets and measurements.
