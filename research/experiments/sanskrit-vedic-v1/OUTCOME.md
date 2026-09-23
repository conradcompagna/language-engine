# Sanskrit from the Vedic UD treebank — superseded

## What was tried

The first Sanskrit models were trained on the Vedic UD treebank, with a transliteration
layer between IAST and SLP1 and several sentence-grouping variants (flat, grouped,
10-sentence chunks) to find a segmentation the tokenizer could learn. The build scripts
are in `research/pipeline/datasets/convert_vedic_iast_to_slp1.py` and the
`sa_vedic-ud-*` dataset variants.

## What happened

The run completed and produced weights, establishing an initial Vedic UD training
path before the application selected DCS supervision.

## Selecting DCS supervision

The Vedic treebank is small and its sandhi resolution is inconsistent for the purpose —
what the reader needs is a model that splits fused orthographic words into their
underlying dictionary forms, and the Digital Corpus of Sanskrit provides an order of
magnitude more multi-word-token supervision for exactly that. The DCS run
(`trankit_save_sa_dcs_v1`) shipped instead.

The application retains the `sanskrit-vedic` model name for the selected DCS build.
The [artifact mapping](../../STATUS.md) records that lineage explicitly.

`run_logs/` holds the training logs.
