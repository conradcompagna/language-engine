# Arabic segmentation: comparing morphology-derived supervision

## Problem and approach

Arabic clitics attach prepositions, conjunctions, articles, and pronominal suffixes
to surface words. I explored using CAMeL Tools analyses as supervision for Trankit's
multi-word-token expander, aiming to integrate those splits with the reader's
existing model pipeline.

The ten recorded configurations test morphology-driven expansion, several tokenizer
alignments, validation, and lemma supervision derived from a ZIP lexicon:

- `ar_camelmorph_v1`, `ar_camelmorph_exp_20260405b`
- `ar_cameltok_20260405a`, `b`, `d`, `f`, `h`, and `ar_cameltok_validate_tmp`
- `ar_ziplemma_20260405a` and `ar_zip_surface_lemma_20260405a`

## Result and selection

Three runs produced saved weights. Seven ended during training or evaluation without
saved weights; the retained logs document the token-alignment constraints involved
in reconciling CAMeL output with Trankit's CoNLL-U evaluation.

The application selected the Arabic UD/PADT model from
`trankit_save_commercial_v1`. The comparison harness remained useful for checking
that tokenizer against CAMeL output as an external reference, while keeping the
application's runtime dependencies focused on the selected pipeline.

## Inspect the work

- `camel_tools_arabic_tokenizer.py`: integration layer.
- `build_zip_lemmatizer_dataset.py` and `build_zip_lemmatizer_dataset_surface_only.py`:
  alternative lemma-supervision builders.
- `compare_arabic_tokenization.py` and `arabic_segmented_text.py`: comparison harness.
- `run_logs/`: original training and evaluation records.
