# Model runs

One directory per finished NER training run, holding the training configuration and the
label vocabulary. The configuration records the base encoder, the
dataset, and the hyperparameters; the vocabulary records the label set the run was
trained against.

Twenty-nine runs across Old English, Ancient Greek, Armenian, Classical Chinese,
Filipino, Hebrew, Hindi, Indonesian, Italian, Latin, Persian, Portuguese, Sanskrit,
Swahili, Thai, Turkish and Vietnamese.

Several languages have complementary runs comparing label schemes, corpus sizes,
and supervision settings:

- `vie_plo75`, `vie_manual12_direct_raw`, `vie_collapse13_all_tags_raw`, `wikiann_vi` —
  four different coarse label sets for Vietnamese
- `san_gemini_ner_chunks_0001_1800_corrected` and its `_supervised_even95_5` and
  `_tag_scores` variants — the Sanskrit set under different supervision and scoring
  regimes, plus two per-label probes
- `lzh_cmag_200k` and `lzh_cmag_1m` — Classical Chinese at two corpus sizes
- `swh_finerweb_top100_lpo` — two runs, the second a rerun with a timestamped output

The trainer is [`../pipeline/models/train_ner.py`](../pipeline/models/train_ner.py).
Dataset cards for the corpora are in [`../datasets/`](../datasets/).
