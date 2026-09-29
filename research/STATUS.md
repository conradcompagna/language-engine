# Selected models and development record

The application selects components per language and task. This map connects the
27 active language IDs to retained runs and to the
[deployed artifact inventory](models/deployed_artifacts.json), checked by SHA-256
on 23 September 2026. Traditional Chinese is additionally loaded as an override.
The [construction guide](../docs/BUILD_PROCESS.md) explains the preparation,
training, dictionary and CPU-export stages that produced these resources.

## Active model map

I combine my own trained components with upstream Trankit models. This table records the selection for each task rather than treating an entire language pipeline as either custom or stock.

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

Across these 28 pipelines, 61 task slots use custom checkpoints, 62 use stock checkpoints, 2 use identity lemmatization, and 15 do not use an MWT component.

Korean syntax uses the Korean-Kaist components; Korean NER is separately trained on KLUE. Persian combines stock tokenization, syntax and MWT expansion with my lemmatizer and NER; Greek combines my tokenizer, syntax and lemmatizer with the stock MWT expander.

The [component identities](models/component-origins.json) record checkpoint hashes and immutable upstream sources. The training results distinguish original selected-checkpoint development scores from fresh evaluations of the retained MWT, Japanese NER and Sanskrit parser checkpoints.

## Component selection decisions

- **Arabic:** the selected tokenizer and MWT match `t_ar10k2`; the tagger and
  lemmatizer match `trankit_save_commercial_v1/ar`.
- **Ancient Greek:** natural-paragraph tokenizer training is combined with the
  `t_grc10k_tok1` tagger/lemmatizer and the Pausanias NER run.
- **Sanskrit:** DCS v1 supplies tokenizer, lemma and sandhi/MWT expansion; NER
  matches the corrected supervised 95/5 run. The tagger uses the separate
  10,000-sentence DCS dependency-data track: all seven training vocabulary maps
  match the selected model, and its retained development evaluation is recorded.
- **Tagalog:** v2 supplies tokenizer/MWT and v1 supplies tagger/lemma.
- **Old English:** OEDT tokenize v3 supplies tokenizer/tagger, alongside the
  separate lemmatizer and `ang_oedt` NER.
- **Classical Chinese:** the selected NER matches `lzh_cmag_200k`.
- **Thai:** syntax matches `trankit_save_th_customized_ner`; NER matches the
  separately finished `tha_thai_nner_full_coarse_bio` run.

The [complete training results](models/TRAINING_RESULTS.md) give selected-checkpoint
development scores, last logged results and source-log identities across tasks. The
[dataset cards](datasets/README.md) and [build chains](pipeline/README.md) document
their input preparation and label schemes.

## CPU artifact selection

`NEWPIPELINE=1` selects the shared dynamic-INT8 XLM-R encoder and adapter runtime.
The model store is named `training/trankit_save_ja_ner_v2/xlm-roberta-base` because
the initial pipeline constructor establishes a shared cache; it serves the full
language registry. See [CPU construction](../docs/BUILD_PROCESS.md#3-package-inference-for-cpu-deployment).

The manifest's 34 stored aliases include Ancient Hebrew, Bengali, Irish, Punjabi,
Tamil and Urdu outside the active registry/Traditional Chinese selection. Their
packs preserve development history without adding languages to the current UI.

## Retained alternatives

The [experiment guide](experiments/README.md) preserves consequential alternatives:
Vedic Sanskrit versus the selected DCS build, Arabic CAMeL Tools morphology/tokenizer
work, pooled versus per-language low-resource runs, and shared-encoder prototypes.
The [NER collection](models/README.md) also records label-scheme and corpus-size
comparisons. Those records explain selection decisions alongside the active map.

## Artifact identities

The JSON inventory records relative paths, byte sizes and SHA-256 hashes.
The [provenance tool](tools/check_provenance.py) compares retained training
directories with a model store, connecting run outputs to selected components.
The [training record](REPRODUCIBILITY.md) describes the corpus, configuration and
artifact records behind those matches.
