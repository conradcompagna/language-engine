# Model training and export

| Script | Role |
|---|---|
| `train_ner.py` | Trains a Trankit NER model from BIO files; validates the input and writes `run_evidence.json` with input hashes, package versions and output hashes |
| `training_evidence.py` | Helper for the run-evidence record |
| `prep_trankit.py` | Splits local UD treebanks for six languages into train/dev CoNLL-U and text files |
| `apply_patch.py` | Extracts a patch archive over the project folder, backing up replaced files |
| `upstream_patches/trankit/tpipeline.py` | Patched copy of Trankit's training pipeline (fixed seed 1234), required by several runs |
| `build_trankit_xlmr_onnx_cpu.py` | Exports the XLM-R encoder to ONNX with dynamic INT8 quantization |
| `tune_trankit_onnx_ort_session.py` | Compares ONNX Runtime session settings |
| `build_trankit_compressed_runtime_artifacts.py` | Builds the shared-encoder and adapter bundle loaded by the application |

`train_ner.py` checks that every row has a token and a tag, that no split is empty and
that no sentence appears in both training and development data. Run identifiers are
reserved before training so earlier outputs are not overwritten.

The trained runs are listed in [`../../models/README.md`](../../models/README.md).
