# Model components and training results

Language Engine runs a Trankit pipeline per language. Each pipeline has up to five
components: tokenizer, multi-word-token (MWT) expander, POS/morphology/parser,
lemmatizer and named-entity recognizer. For each language and component the
application uses either a component I trained (Custom), an unchanged upstream Trankit
release (Stock), or an identity lemmatizer.

Across the 28 configured pipelines, 61 components are custom, 62 are stock, 2 use
identity lemmatization, and 15 have no MWT component.

## Contents of this folder

| Path | Contents |
|---|---|
| `component-origins.json` | Checkpoint hashes for custom components and upstream sources for stock ones |
| `stock-models.json` | SHA-256 matches between stock components and the official Trankit release archives |
| `deployed_artifacts.json` | Model files checked against the production server on 23 September 2026 |
| 27 run folders (`ang_oedt/` … `wikiann_vi/`) | One per finished NER training run: `training_config.json` and/or the label vocabulary `customized-ner.ner-vocab.json` |

The NER runs cover Old English, Ancient Greek, Modern Greek, Armenian, Classical
Chinese, Filipino, Hebrew, Hindi, Indonesian, Italian, Latin, Persian, Portuguese,
Sanskrit, Swahili, Thai, Turkish and Vietnamese. Several languages have more than one
run comparing label schemes or corpus sizes (four Vietnamese label sets; four Sanskrit
supervision and scoring variants; Classical Chinese at 200k and 1M tokens).
Folders with a timestamp suffix are reruns of the folder of the same name. The trainer
is [`../pipeline/models/train_ner.py`](../pipeline/models/train_ner.py) and the corpora
are described in [`../datasets/`](../datasets/).

## Component map

| Language | Tokenizer | MWT expansion | POS/morphology/parser | Lemmatizer | NER |
|---|---|---|---|---|---|
| Chinese (Simplified) | Stock | — | Stock | Stock | Stock |
| Japanese | Stock | — | Stock | Stock | Custom |
| Korean | Stock | — | Stock | Stock | Custom |
| Vietnamese | Stock | — | Stock | Identity | Custom |
| Classical Chinese | Stock | — | Stock | Stock | Custom |
| Turkish | Custom | Custom | Custom | Custom | Custom |
| Persian | Stock | Stock | Stock | Custom | Custom |
| Indonesian | Stock | — | Stock | Stock | Custom |
| Hindi | Custom | — | Custom | Custom | Custom |
| Arabic | Custom | Custom | Custom | Custom | Stock |
| Thai | Custom | — | Custom | Identity | Custom |
| Sanskrit | Custom | Custom | Custom | Custom | Custom |
| Old English | Custom | — | Custom | Custom | Custom |
| French | Stock | Stock | Stock | Stock | Stock |
| Italian | Stock | Stock | Stock | Stock | Custom |
| Russian | Stock | — | Stock | Stock | Stock |
| Spanish | Stock | Stock | Stock | Stock | Stock |
| German | Stock | Stock | Stock | Stock | Stock |
| Dutch | Stock | — | Stock | Stock | Stock |
| Portuguese | Stock | Stock | Stock | Stock | Custom |
| Latin | Custom | — | Custom | Custom | Custom |
| Greek | Custom | Stock | Custom | Custom | Custom |
| Armenian | Stock | Stock | Stock | Stock | Custom |
| Ancient Greek | Custom | — | Custom | Custom | Custom |
| Hebrew | Custom | Custom | Custom | Custom | Custom |
| Tagalog | Custom | Custom | Custom | Custom | Custom |
| Swahili | Custom | — | Custom | Custom | Custom |
| Chinese (Traditional) | Stock | — | Stock | Stock | Stock |

Korean syntax uses the stock Korean-Kaist components; Korean NER is trained on KLUE.

## Development scores

All values are percentages on each run's own development split. Corpora, label schemes
and input stages differ between runs, so the columns are not a cross-language
comparison. A dash marks a stock or identity component. An asterisk marks a
re-evaluation of the saved checkpoint performed on 24 September 2026; other values come
from the selected checkpoint's training log.

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

The Vietnamese NER run (`wikiann_vi`) trained on the WikiANN train and test splits
combined and used the validation split for development, so its score is a development
score only.

### Multi-word-token expansion

Expanded-word F1 from the CoNLL UD scorer, measured on the retained development data
with the dictionary ensemble the application uses.

| Language | Expanded-word F1 | Input to the expander |
|---|---:|---|
| Arabic | 98.09% | Retained tokenizer predictions |
| Sanskrit | 93.91% | Reference surface boundaries and MWT flags |
| Turkish | 99.67% | Reference surface boundaries and MWT flags |
| Hebrew | 98.30% | Reference surface boundaries and MWT flags |
| Tagalog | 97.38% | Retained tokenizer predictions |

## Score records

| File | Contents |
|---|---|
| [tokenizer-training.json](../evaluation/results/tokenizer-training.json) | Token and sentence F1 at the selected and last logged epochs |
| [tagger_parser-training.json](../evaluation/results/tagger_parser-training.json) | POS, features, UAS and LAS |
| [lemmatizer-training.json](../evaluation/results/lemmatizer-training.json) | Lemmatizer development scores, with dictionary baselines |
| [ner-training.json](../evaluation/results/ner-training.json) | NER scores and checkpoint hashes for the 19 custom NER components |
| [mwt-development.json](../evaluation/results/mwt-development.json) | MWT re-evaluation inputs, references and results |
| [japanese-ner-development.json](../evaluation/results/japanese-ner-development.json) | Japanese NER re-evaluation |
| [sanskrit-parser-development.json](../evaluation/results/sanskrit-parser-development.json) | Sanskrit parser re-evaluation |
| [syntax-log-excerpts.json](../evaluation/results/syntax-log-excerpts.json) | Original score tables from the training logs |
| [selected_ner_training.json](../evaluation/results/selected_ner_training.json) | Training-log excerpts for four NER runs (Old English, Ancient Greek, Sanskrit, Vietnamese) |
| [sanskrit-parser-dataset.json](../evaluation/results/sanskrit-parser-dataset.json) | Match between the Sanskrit parser's vocabulary and its training data |

The scripts behind the re-evaluations are in
[`../evaluation/selected_components/`](../evaluation/selected_components/).
Epoch numbers follow the trainer's zero-based convention.
