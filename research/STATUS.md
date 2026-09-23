# Training runs and application artifacts

The development record contains 29 Trankit parser-training configurations, including
ten runs reported as contributing application models. The tables connect those runs
to their selected artifacts and preserve the alternatives explored during development.

The mapping below is a historical build record.
[`tools/check_provenance.py`](tools/check_provenance.py) screens artifact sizes against
a supplied model store; common sizes are excluded to reduce ambiguous matches, and
`--hash` verifies candidate matches with SHA-256. Training configurations and logs
supply the associated build context.

To verify local artifact matches:

```sh
python research/tools/check_provenance.py \
    --runs <training dir> --deployed <model store>/xlm-roberta-base --hash
```

## Reported shipped

| Run | Shipped as | What it contributed |
|---|---|---|
| `trankit_save_commercial_v1` | arabic, greek, hebrew, hindi, latin, turkish | six deployed languages from one batch |
| `trankit_save_rarelangs_v1` | bengali-custom, punjabi-custom | UD treebanks for low-resource languages |
| `trankit_save_ben_v1` | bengali-custom | lemmatizer |
| `trankit_save_hbo_ptnk_v1` | ancient-hebrew-mwt | tagger, lemmatizer, MWT expander |
| `trankit_save_sa_dcs_v1` | sanskrit-vedic | MWT expander (sandhi splitting), lemmatizer |
| `trankit_save_swh_v1` | swahili-custom | tagger, lemmatizer |
| `trankit_save_tgl_v1` | tagalog-custom | tagger, lemmatizer |
| `trankit_save_tgl_v2` | tagalog-custom | MWT expander only |
| `trankit_save_th_customized_ner` | thai-ner | tagger, NER |
| `trankit_save_oldeng_oedt_tokenize_v3` | customized | Old English tagger |

The mapping captures component-level model selection: `sanskrit-vedic` uses the
**DCS** build, and Tagalog combines v1's tagger and lemmatizer with v2's MWT
expander. Keeping those choices explicit makes the application assets traceable
across separately named training runs.

## Superseded model variants

| Run | Superseded by | Evidence |
|---|---|---|
| `trankit_save_sa_vedic_v1` | `trankit_save_sa_dcs_v1` | produced weights; none deployed |
| `trankit_save_oldeng_oedt_tokenize_v2` | `..._v3` | produced no weights |

Logs: [`experiments/sanskrit-vedic-v1/`](experiments/sanskrit-vedic-v1/).

## Additional development runs

### Arabic morphology and tokenizer experiments

| Run | Evidence |
|---|---|
| `trankit_save_ar_camelmorph_v1` | no weights produced |
| `trankit_save_ar_cameltok_20260405a` | no weights produced |
| `trankit_save_ar_cameltok_20260405b` | no weights produced |
| `trankit_save_ar_cameltok_20260405d` | no weights produced |
| `trankit_save_ar_cameltok_20260405f` | no weights produced |
| `trankit_save_ar_cameltok_20260405h` | no weights produced |
| `trankit_save_ar_cameltok_validate_tmp` | no weights produced |
| `trankit_save_ar_camelmorph_exp_20260405b` | weights produced, none deployed |
| `trankit_save_ar_ziplemma_20260405a` | weights produced, none deployed |
| `trankit_save_ar_zip_surface_lemma_20260405a` | weights produced, none deployed |

The selected Arabic model came from `commercial_v1`; the runtime keeps CAMeL Tools
as an external comparison dependency. The experiment record documents the alternatives.
See [`experiments/arabic-cameltools/OUTCOME.md`](experiments/arabic-cameltools/OUTCOME.md).

### Comparing pooled and per-language training

`trankit_save_rarelangs_v1as`, `v1bn`, `v1mr`, `v1ojp`, `v1pa`, `v1pkt` (Assamese,
Bengali, Marathi, Old Japanese, Punjabi, Prakrit). The retained records contain no weights for these six configurations; the pooled
`trankit_save_rarelangs_v1` run supplied the application models.
See [`experiments/rarelangs-per-language/OUTCOME.md`](experiments/rarelangs-per-language/OUTCOME.md).

### Other

| Run | Evidence |
|---|---|
| `trankit_save_newsanskrit_posdep_v1` | no weights produced |

## NER training runs

Twenty-nine finished NER runs are recorded in [`models/`](models/) with their training
configuration and label vocabulary. They cover Old English, Ancient Greek, Armenian,
Classical Chinese, Filipino, Hebrew, Hindi, Indonesian, Italian, Latin, Persian,
Portuguese, Sanskrit, Swahili, Thai, Turkish and Vietnamese. Several languages have
multiple runs against different label schemes; the Vietnamese and Sanskrit families are
scheme comparisons, not retries.

The parser mapping above is complemented by the NER configurations and vocabularies
in [models/](models/), and by the source/split records in [datasets/](datasets/).
