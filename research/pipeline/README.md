# Build chains

These build chains document corpus, model and dictionary construction. The
[verified selection map](../STATUS.md) identifies current components and separates
retained alternatives; the [construction story](../../docs/BUILD_PROCESS.md) connects
the chains to the product. Use the [evidence index](../EVIDENCE.md) and
[reproduction guide](../REPRODUCIBILITY.md) for measurements and runnable checks.

---

## 1. Neural models (Trankit)

The service loads per-language Trankit models: tokenizer, multi-word-token expander,
tagger, lemmatizer, and named-entity recogniser. Some are upstream Trankit releases.
The ones below were trained here.

### 1a. Sanskrit — sandhi splitting by multi-word-token expansion

Sanskrit is written with *sandhi*: adjacent words fuse and mutate at their boundaries,
so the orthographic string does not segment into dictionary words by any surface rule.
Trankit's multi-word-token expander is a sequence-to-sequence model that maps one
surface token to several underlying tokens. Training it on Sanskrit turns it into a
sandhi splitter.

```
Digital Corpus of Sanskrit (15,900 CoNLL-U chapters + chapter-info.xml)
  │
  ├─ datasets/build_dcs_trankit_full_dataset.py
  │     Walks chapters in corpus order from chapter-info.xml.
  │     Emits the MWT-aware SURFACE form: for a range row (n-m) it writes the
  │     fused token and suppresses its children. That surface/underlying pair is
  │     exactly the supervision the expander needs.
  │     Repairs blank HEAD/DEPREL rows so the CoNLL-U validates.
  │     Chapter-level dev split, every 10th chapter.
  │
  ├─ datasets/build_dcs_trankit_mwt_subset.py
  │     Keeps only chapters that contain MWT range rows: 14,554 of 15,900.
  │     Random 10% sample, seed 1337 → 1,455 chapters.
  │     Result (stats.json): 70,355 train sentences, 532,329 token rows,
  │     100,349 MWT rows; 9,349 dev sentences, 67,004 token rows.
  │     The full corpus is ~5.3M tokens; the expander was trained on the
  │     MWT-bearing subset to concentrate the signal.
  │
  ├─ datasets/convert_vedic_iast_to_slp1.py
  │     Separate Vedic UD track. Transliteration between IAST and SLP1, plus
  │     flat / grouped / chunked sentence variants for segmentation experiments.
  │
  ├─ datasets/build_trankit_mwt_eval_input.py
  │     Builds the evaluation input for the expander.
  │
  └─ run: trankit_save_sa_dcs_v1
        → sanskrit-vedic.tokenizer.mdl     SHIPPED
        → sanskrit-vedic_mwt_expander.pt   (35.7 MB)  SHIPPED
        → sanskrit-vedic_lemmatizer.pt     (28.2 MB)  SHIPPED
        Training logs for tokenize / mwt / lemmatize are in that run directory.

trankit_save_sa_vedic_v1 trained on the Vedic UD track instead. It did not ship.
See experiments/sanskrit-vedic-v1/.
```

### 1b. Sanskrit — named entities from a synthetic corpus

I built a task-specific Sanskrit NER corpus with the Gemini API, then trained
models against its domain-specific label inventory.

```
DCS MWT subset → train_10k_parent_tokens.conllu
  │
  ├─ unannotated BIO chunks, 10 sentences per job
  │
  ├─ datasets/sanskrit/gemini_sanskrit_ner_10_sentence_test.py
  │     Defines the label set, prompt construction, BIO conversion, and the
  │     validator. The validator is the important part: it checks the model's
  │     returned tokens against the input tokens and records any divergence
  │     rather than trusting the response.
  │
  ├─ datasets/sanskrit/gemini_sanskrit_ner_batch_runner.py
  │     Parallel batch runner over every chunk. Per job it writes the input,
  │     both prompts, the raw response, the parsed response, a usage record,
  │     a divergence report, the validated atomic output, the validated BIO
  │     output, and a summary. API keys are redacted from error text.
  │     Resumable: already-validated chunks are skipped.
  │
  ├─ datasets/sanskrit/build_final_sanskrit_gemini_ner_dataset.py
  │     Concatenates validated chunks, drops empties, applies recorded fixes.
  │     Result (final/dataset_summary.json): 1,765 usable chunks of 1,800,
  │     35 skipped empty, 131,507 token rows, 43,622 entity rows, 237 fixes.
  │
  ├─ datasets/sanskrit/build_sanskrit_gemini_ner_dictionary_review.py
  │     Cross-checks annotated surface forms against the Monier-Williams
  │     dictionary build, grouped for manual review.
  │
  └─ models/train_ner.py → san_gemini_ner_chunks_0001_1800_corrected_supervised_even95_5 (selected; other variants retained)
        → sanskrit-vedic.ner.mdl   SHIPPED
```

Run cost and volume: 1,852 jobs against `gemini-2.5-flash-lite`, 3,107,852 prompt
tokens, 728,721 output tokens, 3,836,573 total, USD 0.60. Recorded in
[`datasets/sanskrit/gemini_ner/RUN_AGGREGATE.json`](datasets/sanskrit/gemini_ner/RUN_AGGREGATE.json);
selected per-job records are in
[`sample_summaries/`](datasets/sanskrit/gemini_ner/sample_summaries/).

The label set was derived from the corpus rather than imported: 19 tags including
DEITY, RITUAL, SUBSTANCE, PLANT, DISEASE, BODY, MEASURE, ASTRO and PROCEDURE, which is
what Sanskrit śāstra literature actually contains. The [dataset summary](datasets/sanskrit/gemini_ner/final/dataset_summary.json)
records chunk coverage, token rows, and annotation corrections.

### 1c. Other trained languages

| Language | Dataset build | Run | Selected components / development status |
|---|---|---|---|
| Ancient Hebrew | `datasets/build_ancient_hebrew_dataset.py`, `train_ancient_hebrew.py` | `hbo_ptnk_v1` | Retained `ancient-hebrew-mwt` resources; outside the current language registry |
| Old English | `datasets/old_english/build_oldeng_trankit_dataset.py` → `train_oldeng_trankit.py` | `oldeng_oedt_tokenize_v3` | `customized` tokenizer and tagger; separate lemmatizer and OEDT NER |
| Tagalog | `datasets/tagalog/parquet_to_conllu.py` → `train_tokenizer.py`, `train_mwt.py` | `tgl_v1`, `tgl_v2` | `tagalog-custom`: v1 tagger/lemmatizer, v2 tokenizer/MWT |
| Swahili | augmented UD set, see `datasets/swahili/DATASET_README.txt` | `swh_v1` | `swahili-custom` tokenizer, tagger and lemmatizer |
| Bengali, Punjabi | `datasets/process_rarelangs.py` over UD treebanks | `ben_v1`, `rarelangs_v1` | Retained development resources; outside the current language registry |
| Ancient Greek | `datasets/ancient_greek/convert_perseus_greek_to_conllu.py`, `build_sampled_subset.py`, `_build_naturalpara_10k.py`, `_verify_naturalpara.py` | `t_grc_naturalpara_tok`, `t_grc10k_tok1` | Natural-paragraph tokenizer; 10k tagger/lemmatizer; separate Pausanias NER |
| Thai | `datasets/` Thai UD + NNER conversion | `th_customized_ner` | `thai-ner` tokenizer/tagger; NER from the separately finished NNER run |
| Korean | `datasets/korean/convert_to_bio.py` → `train_ner.py` | KLUE-NER | `korean-ner` |
| Arabic | Arabic training and tokenizer comparisons | `t_ar10k2`, `commercial_v1/ar` | 10k tokenizer/MWT; commercial-v1 tagger/lemmatizer |
| Greek, Hebrew, Hindi, Latin, Turkish | Component matches in [STATUS.md](../STATUS.md) | `commercial_v1` | Selected syntax/lemma components; NER selected separately |

`datasets/convert_train_jsonl_to_trankit.py` is the shared converter from annotated
JSONL into Trankit's expected CoNLL-U and plain-text pair.
`models/upstream_patches/trankit/tpipeline.py` is a patched copy of Trankit's own
training pipeline; several of the runs above require it.

### 1d. NER label taxonomy

The FiNERweb taxonomy work derives coarse label sets from its fine-grained tags.
Other selected NER models retain their source/task-specific inventories, recorded
in the model and dataset cards. `taxonomy/` holds the derivation: fastText embeddings
of label strings, Louvain community detection over label co-occurrence, and centroid
clustering under purity and internal-coherence gates.
`taxonomy/dataset_builders/` builds a training set for each candidate scheme.
The ~80 parameter variants behind the chosen thresholds are in
[`../experiments/finerweb-taxonomy-sweeps/`](../experiments/finerweb-taxonomy-sweeps/).

---

## 2. Runtime model artefacts

The service initializes selected Trankit checkpoints, installs the shared
INT8 ONNX encoder/adapter runtime, and dynamically quantizes supported PyTorch
task modules. The [CPU build record](../../docs/BUILD_PROCESS.md#3-package-inference-for-cpu-deployment)
connects those stages to the verified deployed bundle.

```
models/prep_trankit.py                        fetch and lay out base models
models/apply_patch.py                         apply the tpipeline patch
models/build_trankit_xlmr_onnx_cpu.py         export the XLM-R encoder to ONNX,
                                              dynamic INT8, CPU execution provider
models/tune_trankit_onnx_ort_session.py       search ORT session options
                                              (threads, arena, graph optimisation)
models/build_trankit_compressed_runtime_artifacts.py
                                              assemble the compressed runtime bundle
                                              the service actually loads
```

Memory and device profiling tools are in [evaluation/](../evaluation/). The
[adapter-bank prototypes](../experiments/arabic-onnx-adapter-bank/OUTCOME.md) document
the exploration of shared encoder and dynamic adapter inputs; the application
implementation is in the root compressed-runtime and live-switch modules.

---

## 3. Dictionaries

The selected Sanskrit SQLite resource is the **DCS-derived build**: its
[builder](datasets/sanskrit/build_sa_sqlite.py) joins lemma IDs to attested corpus
forms, yielding 180,000 entries and 479,041 forms in the verified local build.
See the [DCS and runtime-pruning explanation](../../docs/BUILD_PROCESS.md#4-engineer-the-dictionaries).
The Monier-Williams converter below records a separate development path.

The deployment uses 42 SQLite dictionary files. This build chain turns their
heterogeneous sources into a common lexical index and entry store; database files
are provisioned separately.

```
source (Wiktionary JSONL, JMdict, KRDict XML, CC-CEDICT, LSJ, Monier-Williams, …)
  │
  ├─ per-source converter → normalised TSV
  │     dictionaries/wiktionary/convert_jsonl_to_tsv.py
  │     dictionaries/japanese/convert_jmdict_to_upload_tsv.py
  │     dictionaries/korean/convert_krdict_xml.py
  │     dictionaries/chinese/convert_cc_cedict_to_wiktionary_tsv.py
  │     dictionaries/classical/convert_cnotes_to_wiktionary_tsv.py
  │     dictionaries/sanskrit/convert_mw_to_tsv.py
  │     dictionaries/convert_lsj_to_sqlite.py, convert_lsj_zip_to_sqlite.py
  │
  ├─ dictionaries/convert_tsv_to_sqlite.py
  │     the importer builds the SQLite entry/form store; runtime pruning and
  │     index construction derive the compact records the browser downloads
  │
  ├─ repair and enrichment passes
  │     fix_ja_redirects.py, fix_ko_redirects.py, fill_ja_form_romanization.py,
  │     cleanup_krdict_glosses.py, regenerate_grc_lsj_sqlite.py,
  │     export_grc_lsj_greek_inflexion.py, build_bt_sqlite.py
  │
  └─ audits before a build is promoted
        audit_sqlite_pos_candidates.py, audit_sqlite_prune_candidates.py,
        audit_sqlite_form_tags_flat.py, audit_nonshared_form_chars.py,
        audit_gloss_of_word_tags.py, audit_yomitan_extra_prune.py,
        diagnose_ccedict_index.py
        Reports these produced: ../evaluation/reports/
```

Per-language packages under `dictionaries/<lang>/` hold the language-specific display
and morphology logic: `dictionary.py` builds entries, `pipeline.py` wires the language
into the registry, `lang_config.json` declares its runtime behaviour.

`dictionaries/japanese/data/` is a hand-built Japanese morphology ruleset:
base generation rules, godan row map, allomorph map, contraction rules, orthography
rules, attachment states and edges, ambiguity resolution, lexical exceptions, and
validation examples. `jp_inflection_table_analyzer.py` and `inflection_adapter.py`
apply it. This is the largest piece of hand-authored linguistic data in the project.

`dictionaries/gemini_generated_glosses/` holds LLM-generated gloss tables for languages
with thin dictionary coverage (Arabic, Bengali, Hebrew, Armenian, Indonesian, Korean,
Punjabi, Sanskrit), used to seed entries where no free dictionary exists.

---

## Engineering examples

Three examples show the construction methods in detail:

1. `datasets/build_dcs_trankit_mwt_subset.py` — deterministic dataset construction with
   a recorded seed and a stats file.
2. `datasets/sanskrit/gemini_sanskrit_ner_batch_runner.py` — a validated, resumable,
   cost-tracked LLM annotation run.
3. `dictionaries/convert_tsv_to_sqlite.py` — the importer that builds the SQLite
   entry/form store from which runtime policies derive the browser index.
