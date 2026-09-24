# Selected custom-model training results

I trained and selected components separately for tokenization, multiword
expansion, POS/dependency parsing, lemmatization and NER. This record connects
the components used by Language Engine to their training runs and scores.
The record covers **all 61 custom component selections** across 28 configured
language pipelines: 54 selected-checkpoint scores from retained training logs,
plus seven new development evaluations of the saved checkpoints. The other
selections comprise 62 stock components verified against official release files,
two identity lemmatizers and 15 unused MWT slots.

The [component map](../STATUS.md) places them alongside upstream models; the
[stock-model identities](stock-models.json) link unchanged components to the
official Trankit release archives by SHA-256.

## Selected checkpoint results

All values below are percentages on the individual run’s development split.
The corpus, annotation scheme and input stage differ by run, so the columns
describe component evaluations rather than a multilingual leaderboard.
A dash denotes a stock or identity component; the component map gives its origin.
An asterisk marks a fresh development evaluation performed on 24 September 2026;
the other values come from the selected checkpoint's historical training record.

| Language | Token F1 | POS F1 | UAS | LAS | Lemma F1 | NER F1 |
|---|---:|---:|---:|---:|---:|---:|
| Ancient Greek | 91.99 | 91.48 | 71.85 | 64.43 | 95.11 | 78.81 |
| Arabic | 99.86 | 95.87 | 90.71 | 87.85 | 75.04 | — |
| Armenian | — | — | — | — | — | 94.12 |
| Classical Chinese | — | — | — | — | — | 80.88 |
| Greek | 99.80 | 98.31 | 92.58 | 90.05 | 88.03 | 84.84 |
| Hebrew | 99.63 | 97.01 | 94.04 | 92.10 | 94.21 | 78.22 |
| Hindi | 99.36 | 96.05 | 89.06 | 84.38 | 94.59 | 81.31 |
| Indonesian | — | — | — | — | — | 81.60 |
| Italian | — | — | — | — | — | 82.90 |
| Japanese | — | — | — | — | — | 81.79* |
| Korean | — | — | — | — | — | 88.79 |
| Latin | 99.99 | 99.72 | 95.95 | 94.89 | 97.76 | 81.30 |
| Old English | 98.32 | 91.20 | 76.81 | 72.33 | 86.40 | 88.20 |
| Persian | — | — | — | — | 99.53 | 72.67 |
| Portuguese | — | — | — | — | — | 78.85 |
| Sanskrit | 97.09 | 90.10* | 72.74* | 62.26* | 95.68 | 54.28 |
| Swahili | 99.63 | 93.66 | 82.68 | 79.77 | 86.85 | 77.60 |
| Tagalog | 98.68 | 95.68 | 71.22 | 64.71 | 7.60 | 89.74 |
| Thai | 85.73 | 78.01 | 61.93 | 55.08 | — | 72.39 |
| Turkish | 99.34 | 92.52 | 81.83 | 75.25 | 79.17 | 78.14 |
| Vietnamese | — | — | — | — | — | 91.72 |

## Multiword expansion

These measurements evaluate the five selected custom MWT checkpoints with the
dictionary ensemble used by the reader. They use the retained development material
and the original UD expanded-word scorer. Expanded-word F1 includes the full text,
including words that need no expansion.

| Language | Expanded-word F1 | Input to the expander |
|---|---:|---|
| Arabic | 98.09% | Retained tokenizer predictions |
| Sanskrit | 93.91% | Reference surface boundaries and MWT flags |
| Turkish | 99.67% | Reference surface boundaries and MWT flags |
| Hebrew | 98.30% | Reference surface boundaries and MWT flags |
| Tagalog | 97.38% | Retained tokenizer predictions |

These are new development evaluations of the selected native checkpoints.
Sanskrit, Turkish and Hebrew measure expansion with reference boundaries;
Arabic and Tagalog include their retained tokenizer predictions. The
[MWT record](../evaluation/results/mwt-development.json) gives checkpoint,
input, reference and prediction hashes, plus sequence-model-only results.

The Sanskrit input spans 1,590 DCS chapters. Its expansion reference was rebuilt
from the retained source chapters with the original exporter and matched against
the input's surface text. Japanese NER uses 507 retained development sentences;
the Sanskrit parser uses all 1,525 retained development sentences with reference
word and sentence boundaries.

## Read the primary score records

- [Tokenizer results](../evaluation/results/tokenizer-training.json): selected and last logged token/sentence F1, checkpoint epochs and log identities.
- [POS/parser results](../evaluation/results/tagger_parser-training.json): POS, features and attachment metrics, including aligned accuracy where recorded.
- [Lemmatizer results](../evaluation/results/lemmatizer-training.json): retained best-development summaries for the selected native checkpoints.
- [NER results](../evaluation/results/ner-training.json): selected checkpoint hashes, exact best-score lines and final log summaries for 19 custom NER selections.
- [Japanese NER development evaluation](../evaluation/results/japanese-ner-development.json): exact-checkpoint entity scores and the retained training command connecting the model to its split.
- [Sanskrit parser development evaluation](../evaluation/results/sanskrit-parser-development.json): POS, features and attachment scores, with the [training vocabulary match](../evaluation/results/sanskrit-parser-dataset.json).
- [Syntax log excerpts](../evaluation/results/syntax-log-excerpts.json): the original selected-epoch score tables and line numbers.

The [selected-component evaluators](../evaluation/selected_components/README.md)
preserve the scoring procedures for the seven fresh measurements. Their
[verification record](../evaluation/selected_components/verification.json)
connects the portable scripts to the original evaluation outputs.

## Checkpoint selection

Tokenizer and parser checkpoints store their training epoch. I report the
evaluation table for that stored epoch, including runs whose final log table
belongs to a later checkpoint. The retained trainer prints a “Best dev”
heading above current-epoch metrics, so the heading alone is not the selection
record. Epoch numbers follow the original zero-based trainer convention.

The JSON records retain last logged results separately. NER uses the saved
best-development summary together with a matching checkpoint epoch; native
lemmatizer records preserve their best-development summaries.

The source records distinguish dictionary baselines from the saved
neural/ensemble results for each lemmatizer.
