# Pooled and per-language training configurations

The pooled `trankit_save_rarelangs_v1` run combines UD treebanks for low-resource
languages and supplied the application's `bengali-custom` and `punjabi-custom`
models. [process_rarelangs.py](../../pipeline/datasets/process_rarelangs.py)
records the dataset construction.

Six individual-language configurations were also prepared: `v1as` (Assamese),
`v1bn` (Bengali), `v1mr` (Marathi), `v1ojp` (Old Japanese), `v1pa` (Punjabi), and
`v1pkt` (Prakrit). Their retained directories contain no training logs or weights,
so they are recorded here as configurations rather than completed model runs.

The [training-to-application record](../../STATUS.md) identifies the pooled artifacts
selected for the reader.
