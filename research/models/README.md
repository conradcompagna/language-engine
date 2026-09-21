# Model runs

One directory per finished NER training run, holding the training configuration and the
label vocabulary. **No weights.** The configuration records the base encoder, the
dataset, and the hyperparameters; the vocabulary records the label set the run was
trained against.

Twenty-nine runs across Old English, Ancient Greek, Armenian, Classical Chinese,
Filipino, Hebrew, Hindi, Indonesian, Italian, Latin, Persian, Portuguese, Sanskrit,
Swahili, Thai, Turkish and Vietnamese.

Several languages appear more than once. Those are comparisons between label schemes,
not retries:

- `vie_plo75`, `vie_manual12_direct_raw`, `vie_collapse13_all_tags_raw`, `wikiann_vi` —
  four different coarse label sets for Vietnamese
- `san_gemini_ner_chunks_0001_1800_corrected` and its `_supervised_even95_5` and
  `_tag_scores` variants — the Sanskrit set under different supervision and scoring
  regimes, plus two per-label probes
- `lzh_cmag_200k` and `lzh_cmag_1m` — Classical Chinese at two corpus sizes
- `swh_finerweb_top100_lpo` — two runs, the second a rerun with a timestamped output

The trainer is [`../pipeline/models/train_ner.py`](../pipeline/models/train_ner.py).
Dataset cards for the corpora are in [`../datasets/`](../datasets/).

## Selected training results

These runs connect the dataset work to measured NER outcomes: converting an existing
Old English corpus, separating an Ancient Greek entity category, preparing synthetic
Sanskrit supervision, and adapting Vietnamese WikiANN to Trankit's BIO format.

| Run | Dataset / build record | Best dev F1 (%) | Selected epoch | Run assets |
|---|---|---:|---:|---|
| Old English OEDT | [BIO conversion](../datasets/ang_oedt/README.md) | 88.20 | 13 | [label vocabulary](ang_oedt/customized-ner.ner-vocab.json) |
| Ancient Greek Pausanias | [ethnic/civic label remap](../datasets/grc_pausanias_ethnic_civic_misc/README.md) | 78.81 | 13 | [configuration](grc_pausanias_ethnic_civic_misc/training_config.json) |
| Sanskrit synthetic NER | [corpus construction](../pipeline/README.md#1b-sanskrit--named-entities-from-a-synthetic-corpus) | 54.28 | 29 | [supervised 95/5 configuration](san_gemini_ner_chunks_0001_1800_corrected_supervised_even95_5/training_config.json) |
| Vietnamese WikiANN | [source and split policy](../datasets/wikiann_vi/README.md) | 91.72 | 18 | [configuration](wikiann_vi/training_config.json) |

The [saved-log excerpts](../evaluation/results/selected_ner_training.json) include
exact score lines, original line numbers, run identifiers, and source-log SHA-256
hashes. These are historical best-development scores used for epoch selection;
the datasets and label sets differ, so the rows are examples of completed training
rather than a cross-language ranking. WikiANN uses upstream train + test for
training and validation for development. Independent test performance and current
deployment identity are not established by these logs; the Old English run's
configuration is not part of the published snapshot.
