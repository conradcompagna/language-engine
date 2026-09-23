# Trankit NER training

Run these commands from the repository root with your own authorized BIO corpus.
Public dataset directories contain cards and counts, not full training files.

```sh
python research/pipeline/models/train_ner.py --dataset-dir /path/to/corpus --validate-only
python research/pipeline/models/train_ner.py --dataset-dir /path/to/corpus --run-id experiment --work-cache /short/cache --finished-models /path/to/results --seed-cache /path/to/seed-cache --max-epoch 1
```

Preflight needs only Python 3.12: it checks UTF-8 two-column BIO/BIOES rows, nonempty
splits and exact token-sequence overlap, and prints file hashes/counts without model
imports or filesystem changes. It does not prove annotation quality or detect
near-duplicate leakage. Full training expects a CUDA-capable PyTorch/Trankit
environment; the application's CPU requirements are not a CUDA training recipe.
Historical package versions are not fully recorded, so the old results cannot be
reproduced from this clone alone. Future runs record installed package versions and
the actual TPipeline source hash in `run_evidence.json`.

Defaults are repository-relative `.cache/training/{active,finished,seed}`. On Windows,
use `--work-cache` with a short path to avoid legacy transformer-cache path limits.
All corpus/cache/output paths are CLI parameters. The shared active category is
overwritten by subsequent training: run only one trainer per work cache. Finished
run IDs are reserved separately to avoid overwriting an existing run.

`--snapshot-only --run-id recovered` copies the active cache without training; a
snapshot is not proof of the data or seed that produced it. Normal training copies
new artifacts and hashes them when it finishes or is interrupted. The installed
Trankit controls random seeds: the published [patch](upstream_patches/trankit/tpipeline.py)
sets 1234, but the wrapper does not silently assume that your installation uses it.
Evaluation logs contain entity-level micro scores and per-label precision/recall/F1.
Keep train, dev and a genuinely unseen evaluation corpus separate.
