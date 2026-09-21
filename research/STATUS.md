# Historical training-run mapping

The tables below preserve the author's development records for 29 Trankit runs,
including ten reported contributors to the deployed model store. These are historical
claims, not a fresh inspection of a server. The public repository omits the weights
and their original run/deployment SHA-256 manifests, so this audit cannot verify
that mapping. File-size matches alone do not establish identity or deployment.

The current [provenance checker](tools/check_provenance.py) labels equal-size files
as candidates and compares their contents only with `--hash`; unmatched runs are
unmatched, not automatically abandoned. The status labels below retain the author's
reported outcomes. See the [evidence index](EVIDENCE.md) for supported conclusions.

Recheck against authorized local run and model stores:


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

Two results here contradict their own directory names, which is why the check exists.
The deployed `sanskrit-vedic` model came from the **DCS** run, not from
`trankit_save_sa_vedic_v1`. The deployed Tagalog model is **not** `tgl_v2` superseding
`tgl_v1`: it is v1's tagger and lemmatizer combined with v2's MWT expander.

## Reported superseded

| Run | Superseded by | Evidence |
|---|---|---|
| `trankit_save_sa_vedic_v1` | `trankit_save_sa_dcs_v1` | produced weights; none deployed |
| `trankit_save_oldeng_oedt_tokenize_v2` | `..._v3` | produced no weights |

Logs: [`experiments/sanskrit-vedic-v1/`](experiments/sanskrit-vedic-v1/).

## Reported abandoned

### Arabic with CAMeL Tools — ten runs, nothing shipped

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

Confirmed independently: `camel_tools` appears in neither `requirements.txt` nor any
runtime module. The deployed Arabic model came from `commercial_v1`.
See [`experiments/arabic-cameltools/OUTCOME.md`](experiments/arabic-cameltools/OUTCOME.md).

### Per-language rare-language splits — six runs, nothing shipped

`trankit_save_rarelangs_v1as`, `v1bn`, `v1mr`, `v1ojp`, `v1pa`, `v1pkt` (Assamese,
Bengali, Marathi, Old Japanese, Punjabi, Prakrit). None produced weights; the pooled
`trankit_save_rarelangs_v1` run is what shipped.
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

The NER models load from the same store as the parsers, so the same comparison applies
to them. Weights are not published, so the table above covers the parser runs only.
