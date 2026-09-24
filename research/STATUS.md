# Selected models and development record

The application selects components per language and task. This map connects the
27 active language IDs to retained runs and to the
[deployed artifact inventory](models/deployed_artifacts.json), checked by SHA-256
on 23 September 2026. Traditional Chinese is additionally loaded as an override.
The [construction guide](../docs/BUILD_PROCESS.md) explains the preparation,
training, dictionary and CPU-export stages that produced these resources.

## Active model map

| Language | Runtime alias | Matched syntax / lexical components | NER record |
|---|---|---|---|
| Chinese (`zh`) | `chinese` | Matches retained Chinese cache components | Retained Chinese cache |
| Japanese (`ja`) | `customized-ner` | Syntax matches retained Japanese cache components | Retained NER work cache |
| Korean (`ko`) | `korean-ner` | Korean-Kaist treebank mapping; KLUE NER work area | KLUE conversion/training record |
| Vietnamese (`vi`) | `vietnamese` | Provisioned components fingerprinted | [wikiann_vi](models/wikiann_vi/) |
| Classical Chinese (`lzh`) | `classical-chinese` | Syntax matches retained Classical Chinese cache components | [lzh_cmag_200k](models/lzh_cmag_200k/) |
| Turkish (`tr`) | `turkish` | commercial_v1/tr: tokenizer, tagger, lemma, MWT | [tur_turkish_wiki_ner](models/tur_turkish_wiki_ner/) |
| Persian (`fa`) | `persian` | Separate persianlemmatizer selection | [fa_multiconer_v2_coarse6](models/fa_multiconer_v2_coarse6/) |
| Indonesian (`id`) | `indonesian` | Provisioned components fingerprinted | [ind_indonlu_nerp](models/ind_indonlu_nerp/) |
| Hindi (`hi`) | `hindi` | commercial_v1/hi: tokenizer, tagger, lemma | [hi_multiconer_v2_coarse6](models/hi_multiconer_v2_coarse6/) |
| Arabic (`ar`) | `arabic` | t_ar10k2: tokenizer/MWT; commercial_v1/ar: tagger/lemma | Retained Arabic cache |
| Thai (`th`) | `thai-ner` | th_customized_ner: tokenizer/tagger; identity lemma | [tha_thai_nner_full_coarse_bio](models/tha_thai_nner_full_coarse_bio/) |
| Sanskrit (`sa`) | `sanskrit-vedic` | sa_dcs_v1: tokenizer/lemma/MWT | [san_gemini_ner_chunks_0001_1800_corrected_supervised_even95_5](models/san_gemini_ner_chunks_0001_1800_corrected_supervised_even95_5/) |
| Old English (`ang`) | `customized` | OEDT tokenize v3: tokenizer/tagger; oldeng_lemmatizer | [ang_oedt](models/ang_oedt/) |
| French (`fr`) | `french` | Provisioned components fingerprinted | Fingerprint recorded |
| Italian (`it`) | `italian-twittiro` | Provisioned components fingerprinted | [it_multiconer_v2_coarse6](models/it_multiconer_v2_coarse6/) |
| Russian (`ru`) | `russian-gsd` | Provisioned components fingerprinted | Fingerprint recorded |
| Spanish (`es`) | `spanish-gsd` | Provisioned components fingerprinted | Fingerprint recorded |
| German (`de`) | `german` | Provisioned components fingerprinted | Fingerprint recorded |
| Dutch (`nl`) | `dutch` | Provisioned components fingerprinted | Fingerprint recorded |
| Portuguese (`pt`) | `portuguese` | Provisioned components fingerprinted | [pt_multiconer_v2_coarse6](models/pt_multiconer_v2_coarse6/) |
| Latin (`la`) | `latin` | commercial_v1/la: tokenizer/tagger/lemma | [lat_herodotos_latin_ner](models/lat_herodotos_latin_ner/) |
| Greek (`el`) | `greek` | commercial_v1/el: tokenizer/tagger/lemma | [ell_greek_ner_nel](models/ell_greek_ner_nel/) |
| Armenian (`hy`) | `armenian` | Provisioned components fingerprinted | [hye_wikiann](models/hye_wikiann/) |
| Ancient Greek (`grc`) | `ancient-greek` | t_grc_naturalpara_tok: tokenizer; t_grc10k_tok1: tagger/lemma | [grc_pausanias_ethnic_civic_misc](models/grc_pausanias_ethnic_civic_misc/) |
| Hebrew (`he`) | `hebrew` | commercial_v1/he: tokenizer/tagger/lemma/MWT | [heb_nemo_token_single](models/heb_nemo_token_single/) |
| Tagalog (`tl`) | `tagalog-custom` | tgl_v2: tokenizer/MWT; tgl_v1: tagger/lemma | [fil_tlunified_ner](models/fil_tlunified_ner/) |
| Swahili (`sw`) | `swahili-custom` | swh_v1: tokenizer/tagger/lemma | [swh_finerweb_top100_lpo_20260507_201707](models/swh_finerweb_top100_lpo_20260507_201707/) |

The inventory contains 159 provisioned checkpoints, 96 adapter packs, the INT8
encoder and its manifest. Stored resources include historical and shared assets;
the registry, rather than the directory count, determines enabled languages.
All 257 listed artifact/manifest fingerprints match the retained local deployment
store. In the earlier 119-file registry-folder comparison, 71 files also matched
retained training outputs or cache copies. Eighteen NER files match named finished
runs linked above. These counts describe file identity, not numbers of custom models.

"Fingerprint recorded" identifies the deployed artifact without assigning an
unverified historical training run. Cached-file identity establishes a retained
copy; dataset and authorship claims come from the associated training record.
Korean shares resources through its treebank mapping, and Traditional Chinese
uses the extra `traditional-chinese` alias; neither should be inferred solely
from the presence of alias-named component files.

## Component selection decisions

- **Arabic:** the selected tokenizer and MWT match `t_ar10k2`; the tagger and
  lemmatizer match `trankit_save_commercial_v1/ar`.
- **Ancient Greek:** natural-paragraph tokenizer training is combined with the
  `t_grc10k_tok1` tagger/lemmatizer and the Pausanias NER run.
- **Sanskrit:** DCS v1 supplies tokenizer, lemma and sandhi/MWT expansion; NER
  matches the corrected supervised 95/5 run. The tagger has a deployment fingerprint
  without a matched historical training output in this comparison.
- **Tagalog:** v2 supplies tokenizer/MWT and v1 supplies tagger/lemma.
- **Old English:** OEDT tokenize v3 supplies tokenizer/tagger, alongside the
  separate lemmatizer and `ang_oedt` NER.
- **Classical Chinese:** the selected NER matches `lzh_cmag_200k`.
- **Thai:** syntax matches `trankit_save_th_customized_ner`; NER matches the
  separately finished `tha_thai_nner_full_coarse_bio` run.

The [model guide](models/README.md#selected-training-results) gives saved development
scores and source-log identities for four selected examples. The
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
