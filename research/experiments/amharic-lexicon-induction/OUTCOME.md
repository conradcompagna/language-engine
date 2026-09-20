# Amharic bilingual lexicon induction — research, not product

## What was tried

Unsupervised induction of an Amharic–English dictionary from monolingual corpora, for a
language with almost no machine-readable lexical resources. The approach: train
embeddings on each side, align the two vector spaces with VecMap, extract translation
pairs from nearest neighbours, and refine with statistical alignment over what parallel
text exists.

- `align_bitext.py`, `prep_parallel.py` — parallel corpus preparation
- `statistical_align.py`, `align_and_extract.py` — alignment and pair extraction
- `extract_dictionary.py`, `sort_dictionary.py` — lexicon assembly
- `train_morfessor_from_sqlite.py` — unsupervised morphological segmentation, since
  Amharic morphology makes whole-word alignment sparse
- `nllb_test_app.py`, `test_enc_dec.py`, `Modelfile` — NLLB and local-model comparisons

## Outcome

It produced a usable statistical dictionary, but Amharic was never added to Language
Engine and this is not connected to the product. It is here because it is the same
research question the rest of the project circles — how to get usable lexical coverage
for a language that has none — approached from the opposite direction.
