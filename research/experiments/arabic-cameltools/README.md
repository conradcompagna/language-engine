# Arabic segmentation: comparing morphology-derived supervision

## Problem and approach

Arabic clitics attach prepositions, conjunctions, articles, and pronominal suffixes
to surface words. These runs tested CAMeL Tools analyses as supervision for Trankit's
multi-word-token expander.

The ten recorded configurations test morphology-driven expansion, several tokenizer
alignments, validation, and lemma supervision derived from a ZIP lexicon:

- `ar_camelmorph_v1`, `ar_camelmorph_exp_20260405b`
- `ar_cameltok_20260405a`, `b`, `d`, `f`, `h`, and `ar_cameltok_validate_tmp`
- `ar_ziplemma_20260405a` and `ar_zip_surface_lemma_20260405a`

## Outcome

Three runs produced saved weights. Seven ended without saved weights; their logs
record token-alignment problems between CAMeL output and Trankit's CoNLL-U evaluation.

The application instead uses the tokenizer and expander from run `t_ar10k2`, trained on
CAMeL output after a correction pass ([`pipeline/datasets/arabic/`](../../pipeline/datasets/arabic/)),
with the tagger and lemmatizer from `trankit_save_commercial_v1/ar`. Scores are in
[`models/README.md`](../../models/README.md).

## Files

- `camel_tools_arabic_tokenizer.py`: integration layer.
- `build_zip_lemmatizer_dataset.py` and `build_zip_lemmatizer_dataset_surface_only.py`:
  alternative lemma-supervision builders.
- `compare_arabic_tokenization.py` and `arabic_segmented_text.py`: comparison harness.
- `run_logs/`: original training and evaluation records.
