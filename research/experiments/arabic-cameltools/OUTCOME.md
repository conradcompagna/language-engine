# Arabic with CAMeL Tools — abandoned

## What was tried

Arabic clitic segmentation is the hard part of making the reader work on Arabic text:
prepositions, conjunctions, the definite article and pronominal suffixes attach
orthographically to the host word, so a dictionary lookup on the surface string fails.
Trankit's multi-word-token expander handles this in principle, but its Arabic training
data segments differently from how a reader needs it segmented.

CAMeL Tools is the standard morphological analyser for Modern Standard Arabic. The idea
was to use its analyses as the supervision signal: run CAMeL over a corpus, convert its
segmentation into Trankit's MWT format, and train an expander that reproduces
CAMeL-quality splits inside the existing pipeline rather than adding a second runtime
dependency.

Ten runs over two days:

- `ar_camelmorph_v1`, `ar_camelmorph_exp_20260405b` — the morphology-driven variant
- `ar_cameltok_20260405a` / `b` / `d` / `f` / `h` — tokenizer variants, each a different
  alignment between CAMeL output and the CoNLL-U range-row convention
- `ar_cameltok_validate_tmp` — validation scratch
- `ar_ziplemma_20260405a`, `ar_zip_surface_lemma_20260405a` — a different approach
  again, deriving lemma supervision from the ZIP lexicon rather than from CAMeL

## What happened

Seven of the ten produced no model weights at all; the runs failed during training or
during Trankit's own CoNLL-U evaluation, which requires the concatenation of tokens in
the gold and system files to be identical. Reconciling CAMeL's segmentation with that
constraint was the thing that never worked. Three runs completed and produced weights
that were never deployed.

## Why it stopped

The deployed Arabic model came from `trankit_save_commercial_v1`, trained on Arabic UD
(PADT) with no CAMeL involvement. It was good enough for the reader's purpose, and the
CAMeL path was adding a heavy dependency for a gain that never materialised.

`camel_tools` is in neither `requirements.txt` nor any runtime module. Nothing in this
directory is used.

## What is here

- `camel_tools_arabic_tokenizer.py` — the integration layer
- `build_zip_lemmatizer_dataset.py`, `build_zip_lemmatizer_dataset_surface_only.py` —
  the ZIP-lexicon alternative
- `compare_arabic_tokenization.py`, `arabic_segmented_text.py` — comparison harness
- `run_logs/` — the training logs from each run, including the failures

The comparison harness is the reusable part: it was later used to check the shipped
Arabic tokenizer against CAMeL output as an external reference.
