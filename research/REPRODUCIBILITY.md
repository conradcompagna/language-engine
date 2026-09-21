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
See [NER commands and environment limits](pipeline/models/TRAINING_RUN.md).

The ONNX exporter and [benchmark](evaluation/benchmarks/trankit_benchmark/README.md)
share `TRANKIT_ONNX_CACHE_DIR`, `TRANKIT_ONNX_DEPS_DIRS` (platform path separator)
and `TRANKIT_CPU_OPT_DEPS_DIR`. Set them before starting either process; defaults
resolve relative to the benchmark directory. Exporting requires the full model
store and optional ONNX/PyTorch dependencies. `--help` and public tests do not
download models or start GPU workers.

Other historical one-off scripts are archival method records unless explicitly
covered above or by their directory guide. For example, `prep_trankit.py`,
`apply_patch.py`, and the Greek monitoring helpers retain old workstation inputs
or unavailable patch bundles; do not run them unedited against a different machine.
Historical configuration/log bytes are preserved rather than rewritten as if they
were portable recipes. Consult [EVIDENCE.md](EVIDENCE.md) before quoting results.
