# Transparency / Attribution Inventory

Generated: 2026-05-10

This is an engineering inventory for the planned transparency page. It is not legal advice. The main purpose is to identify what the app should link to, attribute, and review before public deployment.

Scope rules used here:

- Trankit/UD model names come from `DEFINITIONS DUMP/TRANKIT_MODEL_MAP.md`, not `language_registry.py` and not save-folder names.
- NER provenance starts from `training/nerdump/nerdump_dataset_recap_non_vi_non_ancient.md`, plus local license files where they clarify obvious runtime gaps.
- Excluded because they are being phased out: Ancient Hebrew (`hbo`), Irish (`ga`), Bengali (`bn`), Punjabi (`pa`), Tamil (`ta`), Urdu (`ur`).
- `REVIEW` means the item is present or likely present in runtime artifacts, but the exact source/license should be confirmed before the public page claims it as cleared.

Common model stack note:

- [Trankit](https://github.com/nlp-uoregon/trankit) is the runtime NLP toolkit, Apache-2.0. Include in an OSS notice file if distributing the app/model bundle.
- [XLM-RoBERTa base](https://huggingface.co/FacebookAI/xlm-roberta-base) is the transformer base used by Trankit-style models. This is useful model transparency, but not necessarily a public attribution obligation for a hosted service unless we distribute/copy the model files or choose to list every base model.
- [Universal Dependencies](https://universaldependencies.org/contributing/licensing.html) is the actual tokenizer/tagger/parser training-data source family. UD treebank licenses are the important public attribution items.

## Exact Deployed NER Model Folders

This table is the canonical NER mapping for the app. It was derived by SHA-256 hash-matching each current deployed runtime NER model under `training/trankit_save_ja_ner_v2/xlm-roberta-base/*/*.ner.mdl` against `training/trankit_finerweb_prep/trankit_training_run/finished_models/*/customized-ner.ner.mdl`.

Every included app language has exactly one runtime NER target. `unknown` means the deployed runtime model did not match any finished model folder in `training/trankit_finerweb_prep/trankit_training_run/finished_models`.

| App lang | Runtime NER target | Finished NER model folder |
|---|---|---|
| `zh` | `chinese` | unknown |
| `zh-Hant` | `traditional-chinese` | unknown |
| `ja` | `customized-ner` | unknown |
| `ko` | `korean-ner` | unknown |
| `vi` | `vietnamese` | `wikiann_vi` |
| `lzh` | `classical-chinese` | `lzh_cmag_200k` |
| `tr` | `turkish` | `tur_turkish_wiki_ner` |
| `fa` | `persian` | `fa_multiconer_v2_coarse6` |
| `id` | `indonesian` | `ind_indonlu_nerp` |
| `hi` | `hindi` | `hi_multiconer_v2_coarse6` |
| `ar` | `arabic` | unknown |
| `th` | `thai-ner` | `tha_thai_nner_full_coarse_bio` |
| `sa` | `sanskrit-vedic` | `san_gemini_ner_chunks_0001_1800_corrected_supervised_even95_5` |
| `ang` | `customized` | `ang_oedt` |
| `fr` | `french` | unknown |
| `it` | `italian-twittiro` | `it_multiconer_v2_coarse6` |
| `ru` | `russian-gsd` | unknown |
| `es` | `spanish-gsd` | unknown |
| `de` | `german` | unknown |
| `nl` | `dutch` | unknown |
| `pt` | `portuguese` | `pt_multiconer_v2_coarse6` |
| `la` | `latin` | `lat_herodotos_latin_ner` |
| `el` | `greek` | `ell_greek_ner_nel` |
| `hy` | `armenian` | `hye_wikiann` |
| `grc` | `ancient-greek` | `grc_pausanias_ethnic_civic_misc` |
| `he` | `hebrew` | `heb_nemo_token_single` |
| `tl` | `tagalog-custom` | `fil_tlunified_ner` |
| `sw` | `swahili-custom` | `swh_finerweb_top100_lpo_20260507_201707` |

Not-deployed finished candidates found in the same finished-model directory: `vie_collapse13_all_tags_raw`, `vie_manual12_direct_raw`, `vie_plo75_20260504_223313`, `san_gemini_ner_chunks_0001_1800_corrected_tag_scores`, `san_gemini_ner_chunks_0001_1800_corrected_supervised_even95_5_tag_scores`.

## Per-Language Model And Dataset Inventory

### Chinese, Simplified (`zh`)

- Trankit syntax model: `chinese`.
- UD tokenizer/tagger/parser source: [UD Chinese GSD](https://github.com/UniversalDependencies/UD_Chinese-GSD), CC BY-SA 4.0.
- Runtime NER: `chinese`; finished NER model folder is unknown from finished-folder hash matching. REVIEW.
- Runtime dictionaries: Wiktionary/Kaikki-derived Chinese TSV/SQLite, plus [CC-CEDICT](https://www.mdbg.net/chinese/dictionary?page=cc-cedict). Current MDBG download page lists CC BY-SA 4.0; older CC-CEDICT wiki text references CC BY-SA 3.0, so attribute against the exact downloaded release.

### Chinese, Traditional (`zh-Hant`)

- Trankit syntax model: `traditional-chinese`.
- UD tokenizer/tagger/parser source: UD Chinese GSD traditional split, based on [UD Chinese GSD](https://github.com/UniversalDependencies/UD_Chinese-GSD), CC BY-SA 4.0.
- Runtime NER: `traditional-chinese`; finished NER model folder is unknown from finished-folder hash matching. REVIEW.
- Runtime dictionaries: Wiktionary/Kaikki-derived Chinese TSV/SQLite, plus [CC-CEDICT](https://www.mdbg.net/chinese/dictionary?page=cc-cedict).

### Japanese (`ja`)

- Trankit syntax model: `customized-ner`.
- UD tokenizer/tagger/parser source: [UD Japanese GSD](https://github.com/UniversalDependencies/UD_Japanese-GSD), CC BY-SA 4.0.
- Runtime NER: `customized-ner`; finished NER model folder is unknown from finished-folder hash matching. REVIEW.
- Runtime dictionaries: Wiktionary/Kaikki-derived Japanese TSV/SQLite, plus [JMDict/EDICT via EDRDG](https://www.edrdg.org/edrdg/licence.html), CC BY-SA 4.0.

### Korean (`ko`)

- Trankit syntax model: `korean-ner`.
- UD tokenizer/tagger/parser source: [UD Korean Kaist](https://github.com/UniversalDependencies/UD_Korean-Kaist), CC BY-SA 4.0. Runtime vocab also includes [UD Korean GSD](https://github.com/UniversalDependencies/UD_Korean-GSD), CC BY-SA 4.0.
- Runtime NER: `korean-ner`; finished NER model folder is unknown from finished-folder hash matching. REVIEW.
- Runtime dictionaries: Wiktionary/Kaikki-derived Korean TSV/SQLite, plus [Korean Learners' Dictionary / KRDict](https://krdict.korean.go.kr/eng/kboardPolicy/copyRightTermsInfo), Creative Commons Attribution-ShareAlike terms. Korean policy text identifies CC BY-SA 2.0 Korea for site text materials.

### Vietnamese (`vi`)

- Trankit syntax model: `vietnamese`.
- UD tokenizer/tagger/parser source: [UD Vietnamese VTB](https://github.com/UniversalDependencies/UD_Vietnamese-VTB), CC BY-SA 4.0.
- Runtime NER: `vietnamese`; finished NER model folder `wikiann_vi`, trained from `training/trankit_finerweb_prep/datasets/wikiann_vi`. Source is [WikiANN Vietnamese](https://huggingface.co/datasets/unimelb-nlp/wikiann), license unknown on primary HF card.
- Runtime dictionaries: Wiktionary/Kaikki-derived Vietnamese TSV/SQLite.

### Classical Chinese (`lzh`)

- Trankit syntax model: `classical-chinese`.
- UD tokenizer/tagger/parser source: [UD Classical Chinese Kyoto](https://github.com/UniversalDependencies/UD_Classical_Chinese-Kyoto), public-domain source according to local UD license classification.
- Runtime NER: `classical-chinese`; finished NER model folder `lzh_cmag_200k`, trained from `training/trankit_finerweb_prep/datasets/lzh_cmag_200k`. REVIEW exact upstream CMAG source/license before public attribution.
- Runtime dictionaries: Chinese Notes-derived Classical Chinese SQLite plus Wiktionary/Kaikki-derived Classical Chinese SQLite. REVIEW exact Chinese Notes source/license link before publication.

### Turkish (`tr`)

- Trankit syntax model: `turkish`.
- UD tokenizer/tagger/parser source: [UD Turkish BOUN](https://github.com/UniversalDependencies/UD_Turkish-BOUN), CC BY-SA 4.0.
- Runtime NER: `turkish`; finished NER model folder `tur_turkish_wiki_ner`. Source is [Turkish Wiki NER Dataset](https://github.com/turkish-nlp-suite/Turkish-Wiki-NER-Dataset), CC BY-SA 4.0.
- Runtime dictionaries: Wiktionary/Kaikki-derived Turkish TSV/SQLite.

### Persian / Farsi (`fa`)

- Trankit syntax model: `persian`.
- UD tokenizer/tagger/parser source: [UD Persian Seraji](https://github.com/UniversalDependencies/UD_Persian-Seraji), CC BY-SA 4.0.
- Runtime NER: `persian`; finished NER model folder `fa_multiconer_v2_coarse6`. Source is [MultiCoNER v2 Farsi](https://huggingface.co/datasets/MultiCoNER/multiconer_v2), CC BY 4.0.
- Runtime dictionaries: Wiktionary/Kaikki-derived Persian TSV/SQLite.

### Indonesian (`id`)

- Trankit syntax model: `indonesian`.
- UD tokenizer/tagger/parser source: [UD Indonesian GSD](https://github.com/UniversalDependencies/UD_Indonesian-GSD), CC BY-SA 4.0.
- Runtime NER: `indonesian`; finished NER model folder `ind_indonlu_nerp`. Source is IndoNLU NERP, Apache-2.0 per local notes.
- Runtime dictionaries: Wiktionary/Kaikki-derived Indonesian TSV/SQLite.

### Hindi (`hi`)

- Trankit syntax model: `hindi`.
- UD tokenizer/tagger/parser source: [UD Hindi PUD](https://github.com/UniversalDependencies/UD_Hindi-PUD), CC BY-SA 3.0.
- Runtime NER: `hindi`; finished NER model folder `hi_multiconer_v2_coarse6`. Source is [MultiCoNER v2 Hindi](https://huggingface.co/datasets/MultiCoNER/multiconer_v2), CC BY 4.0.
- Runtime dictionaries: Wiktionary/Kaikki-derived Hindi TSV/SQLite.

### Arabic (`ar`)

- Trankit syntax model: `arabic`.
- UD tokenizer/tagger/parser source: [UD Arabic PUD](https://github.com/UniversalDependencies/UD_Arabic-PUD), CC BY-SA 3.0.
- Runtime NER: `arabic`; finished NER model folder is unknown from finished-folder hash matching. REVIEW.
- Optional Arabic tokenizer data: if the CAMeL/CALIMA path is enabled, local `training/camel_tools_data/data/morphology_db/calima-msa-r13/LICENSE` identifies derived Aramorph/CALIMA data under GPL-2.0. Treat this as a high-priority licensing review item.
- Runtime dictionaries: Wiktionary/Kaikki-derived Arabic TSV/SQLite.

### Thai (`th`)

- Trankit syntax model: `thai-ner`.
- UD tokenizer/tagger/parser source: [UD Thai TUD](https://github.com/UniversalDependencies/UD_Thai-TUD), CC BY-SA 4.0.
- Runtime NER: `thai-ner`; finished NER model folder `tha_thai_nner_full_coarse_bio`. Source is [Thai-NNER](https://github.com/vistec-AI/Thai-NNER), CC BY-SA 3.0 for dataset.
- Runtime dictionaries: Wiktionary/Kaikki-derived Thai TSV/SQLite.

### Sanskrit (`sa`)

- Trankit syntax model: `sanskrit-vedic`.
- UD tokenizer/tagger/parser source: [UD Sanskrit Vedic](https://github.com/UniversalDependencies/UD_Sanskrit-Vedic), CC BY-SA 4.0.
- Runtime NER: `sanskrit-vedic`; finished NER model folder `san_gemini_ner_chunks_0001_1800_corrected_supervised_even95_5`, trained from local Gemini-corrected Sanskrit BIO data. REVIEW exact source/provenance and disclosure language.
- Runtime dictionaries: DCS-derived Sanskrit SQLite. REVIEW exact DCS source/license link before publication.

### Old English (`ang`)

- Trankit syntax model: `customized`.
- UD tokenizer/tagger/parser source: local `UD_Old_English-OEDT (unreleased)` runtime artifact. Local historical dump contains Old English OEDT license CC BY-SA 4.0; confirm exact treebank source before publishing.
- Runtime NER: `customized`; finished NER model folder `ang_oedt`. Source is Old English OEDT NER data in local historical dump, CC BY-SA 4.0.
- Runtime dictionaries: Wiktionary/Kaikki-derived Old English TSV/SQLite, plus Bosworth-Toller-derived SQLite. Bosworth-Toller is generally public-domain source material, but REVIEW exact digital source and attribution link.

### French (`fr`)

- Trankit syntax model: `french`.
- UD tokenizer/tagger/parser source: [UD French GSD](https://github.com/UniversalDependencies/UD_French-GSD), CC BY-SA 4.0.
- Runtime NER: `french`; finished NER model folder is unknown from finished-folder hash matching. REVIEW.
- Runtime dictionaries: Wiktionary/Kaikki-derived French TSV/SQLite.

### Italian (`it`)

- Trankit syntax model: `italian-twittiro`.
- UD tokenizer/tagger/parser source: [UD Italian TWITTIRO](https://github.com/UniversalDependencies/UD_Italian-TWITTIRO), CC BY-SA 4.0.
- Runtime NER: `italian-twittiro`; finished NER model folder `it_multiconer_v2_coarse6`. Source is [MultiCoNER v2 Italian](https://huggingface.co/datasets/MultiCoNER/multiconer_v2), CC BY 4.0.
- Runtime dictionaries: Wiktionary/Kaikki-derived Italian TSV/SQLite.

### Russian (`ru`)

- Trankit syntax model: `russian-gsd`.
- UD tokenizer/tagger/parser source: [UD Russian GSD](https://github.com/UniversalDependencies/UD_Russian-GSD), CC BY-SA 4.0.
- Runtime NER: `russian-gsd`; finished NER model folder is unknown from finished-folder hash matching. REVIEW.
- Runtime dictionaries: Wiktionary/Kaikki-derived Russian TSV/SQLite.

### Spanish (`es`)

- Trankit syntax model: `spanish-gsd`.
- UD tokenizer/tagger/parser source: [UD Spanish GSD](https://github.com/UniversalDependencies/UD_Spanish-GSD), CC BY-SA 4.0.
- Runtime NER: `spanish-gsd`; finished NER model folder is unknown from finished-folder hash matching. REVIEW.
- Runtime dictionaries: Wiktionary/Kaikki-derived Spanish TSV/SQLite.

### German (`de`)

- Trankit syntax model: `german`.
- UD tokenizer/tagger/parser source: [UD German GSD](https://github.com/UniversalDependencies/UD_German-GSD), CC BY-SA 4.0.
- Runtime NER: `german`; finished NER model folder is unknown from finished-folder hash matching. REVIEW.
- Runtime dictionaries: Wiktionary/Kaikki-derived German TSV/SQLite.

### Dutch (`nl`)

- Trankit syntax model: `dutch`.
- UD tokenizer/tagger/parser source: [UD Dutch Alpino](https://github.com/UniversalDependencies/UD_Dutch-Alpino), CC BY-SA 4.0.
- Runtime NER: `dutch`; finished NER model folder is unknown from finished-folder hash matching. REVIEW.
- Runtime dictionaries: Wiktionary/Kaikki-derived Dutch TSV/SQLite.

### Portuguese (`pt`)

- Trankit syntax model: `portuguese`.
- UD tokenizer/tagger/parser source: [UD Portuguese Bosque](https://github.com/UniversalDependencies/UD_Portuguese-Bosque), CC BY-SA 4.0.
- Runtime NER: `portuguese`; finished NER model folder `pt_multiconer_v2_coarse6`. Source is [MultiCoNER v2 Portuguese](https://huggingface.co/datasets/MultiCoNER/multiconer_v2), CC BY 4.0.
- Runtime dictionaries: Wiktionary/Kaikki-derived Portuguese TSV/SQLite.

### Latin (`la`)

- Trankit syntax model: `latin`.
- UD tokenizer/tagger/parser source: [UD Latin LLCT](https://github.com/UniversalDependencies/UD_Latin-LLCT), CC BY-SA 4.0.
- Runtime NER: `latin`; finished NER model folder `lat_herodotos_latin_ner`. Source is [Herodotos Latin NER](https://huggingface.co/datasets/daidalos-project/Herodotos_dataset), AGPL-3.0 per local license file.
- Runtime dictionaries: Wiktionary/Kaikki-derived Latin TSV/SQLite.

### Modern Greek (`el`)

- Trankit syntax model: `greek`.
- UD tokenizer/tagger/parser source: [UD Greek GUD](https://github.com/UniversalDependencies/UD_Greek-GUD), CC BY-SA 4.0.
- Runtime NER: `greek`; finished NER model folder `ell_greek_ner_nel`. Source is [Greek NER/NEL](https://zenodo.org/records/7429037), CC BY 3.0.
- Runtime dictionaries: Wiktionary/Kaikki-derived Greek TSV/SQLite.

### Armenian (`hy`)

- Trankit syntax model: `armenian`.
- UD tokenizer/tagger/parser source: [UD Armenian ArmTDP](https://github.com/UniversalDependencies/UD_Armenian-ArmTDP), CC BY-SA 4.0.
- Runtime NER: `armenian`; finished NER model folder `hye_wikiann`. Source is WikiANN Armenian, unknown license on primary HF card.
- Runtime dictionaries: Wiktionary/Kaikki-derived Armenian TSV/SQLite.

### Ancient Greek (`grc`)

- Trankit syntax model: `ancient-greek`.
- UD tokenizer/tagger/parser source: [UD Ancient Greek PTNK](https://github.com/UniversalDependencies/UD_Ancient_Greek-PTNK), CC BY-SA 4.0.
- Runtime NER: `ancient-greek`; finished NER model folder `grc_pausanias_ethnic_civic_misc`, trained from `training/trankit_finerweb_prep/datasets/grc_pausanias_ethnic_civic_misc`. REVIEW exact upstream source/license before public attribution.
- Runtime dictionaries: Wiktionary/Kaikki-derived Ancient Greek TSV/SQLite, plus [Perseus LSJ lexica](https://github.com/PerseusDL/lexica), CC BY-SA 4.0 unless a component says otherwise.

### Hebrew, Modern (`he`)

- Trankit syntax model: `hebrew`.
- UD tokenizer/tagger/parser source: [UD Hebrew IAHLTwiki](https://github.com/UniversalDependencies/UD_Hebrew-IAHLTwiki), CC BY-SA 4.0.
- Runtime NER: `hebrew`; finished NER model folder `heb_nemo_token_single`. Source is [NEMO-Corpus](https://github.com/OnlpLab/NEMO-Corpus), CC BY 4.0 according to local note.
- Runtime dictionaries: Wiktionary/Kaikki-derived Hebrew TSV/SQLite.

### Tagalog / Filipino (`tl`)

- Trankit syntax model: `tagalog-custom`.
- UD tokenizer/tagger/parser source: `UD_Tagalog (unreleased)` custom runtime artifact. REVIEW exact source split. If based on UD Tagalog TRG/Ugnayan, note that TRG is CC BY-SA 4.0 while Ugnayan is CC BY-NC-SA 4.0.
- Runtime NER: `tagalog-custom`; finished NER model folder `fil_tlunified_ner`. Source is [TLUnified-NER](https://huggingface.co/datasets/ljvmiranda921/tlunified-ner), GPL-3.0.
- Runtime dictionaries: Wiktionary/Kaikki-derived Tagalog TSV/SQLite.

### Swahili (`sw`)

- Trankit syntax model: `swahili-custom`.
- UD tokenizer/tagger/parser source: `UD_Swahili (unreleased)` custom runtime artifact. REVIEW exact source/license.
- Runtime NER: `swahili-custom`; finished NER model folder `swh_finerweb_top100_lpo_20260507_201707`. Source is local FiNERweb-style Swahili top100 LPO BIO, license unclear.
- Runtime dictionaries: Wiktionary/Kaikki-derived Swahili TSV/SQLite.

## Cross-Language Dictionary Sources

These are separate from the Trankit models and should have a dedicated "Dictionaries" section on the transparency page.

- Wiktionary/Kaikki-derived dictionaries: used for most app languages in `dict_sqlite/*.sqlite`. Attribute [Wiktionary](https://www.wiktionary.org/) and/or [Kaikki](https://kaikki.org/dictionary/) according to the exact export pipeline. Treat as Creative Commons share-alike content and include the exact license link used by the source dump.
- [JMDict/EDICT](https://www.edrdg.org/edrdg/licence.html): Japanese, CC BY-SA 4.0.
- [CC-CEDICT](https://www.mdbg.net/chinese/dictionary?page=cc-cedict): Chinese simplified/traditional, current MDBG page says CC BY-SA 4.0.
- [Korean Learners' Dictionary / KRDict](https://krdict.korean.go.kr/eng/kboardPolicy/copyRightTermsInfo): Korean, Creative Commons Attribution-ShareAlike terms; Korean page references CC BY-SA 2.0 Korea for text materials.
- Chinese Notes: Classical Chinese. REVIEW exact source URL and license for the local `cnotes_zh_en_dict.tsv` / `dict-classical-chinese.tsv` source.
- DCS Sanskrit: Sanskrit dictionary source. REVIEW exact DCS source URL and license/terms before publishing.
- Bosworth-Toller: Old English supplemental dictionary. REVIEW exact digital source and attribution text.
- [Perseus LSJ lexica](https://github.com/PerseusDL/lexica): Ancient Greek LSJ, CC BY-SA 4.0 unless a component-specific notice says otherwise.

## Runtime Code, Libraries, Services, And Other Non-Dataset Items

This section is intentionally narrower than a full dependency inventory. For a public transparency page, prioritize data/model-training sources, bundled browser code, network-copyleft items, and external services that affect users. Ordinary backend libraries usually belong in an internal OSS notice/dependency inventory rather than a user-facing attribution page, unless the app is distributed as software.

### Backend Python / NLP Stack

- [Trankit](https://github.com/nlp-uoregon/trankit): Apache-2.0.
- XLM-RoBERTa base: keep as optional model transparency, not a must-attribute item for the hosted app unless model files are distributed.
- [PyTorch](https://github.com/pytorch/pytorch): backend runtime dependency through Trankit. Track internally; not usually a public attribution-page item for a hosted service.
- [Flask](https://github.com/pallets/flask), [Werkzeug](https://github.com/pallets/werkzeug), [Flask-Login](https://github.com/maxcountryman/flask-login), [Flask-CORS](https://github.com/corydolphin/flask-cors), [Flask-SQLAlchemy](https://github.com/pallets-eco/flask-sqlalchemy), [SQLAlchemy](https://github.com/sqlalchemy/sqlalchemy), [Requests](https://github.com/psf/requests): backend OSS dependencies. Track internally; not public transparency-page priorities for hosted-only use.
- [EbookLib](https://pypi.org/project/EbookLib/): AGPL. Include only if EPUB handling still ships server-side; otherwise move to internal/dead-dependency cleanup.
- [Beautiful Soup 4](https://www.crummy.com/software/BeautifulSoup/): include only if server-side document conversion still ships.
- [Stripe Python/API](https://github.com/stripe/stripe-python): billing integration.
- Google OAuth and Google Gemini API: service integrations. Include privacy/data-flow transparency even though they are not open-source attribution items.
- CAMeL Tools / CALIMA data: only if enabled in production. Local CALIMA MSA data license is GPL-2.0, so this needs explicit review before shipping Arabic tokenization through that path.

### Frontend/runtime browser libraries

- [PDF.js](https://mozilla.github.io/pdf.js/) / local `static/vendor/pdfjs`: Apache-2.0 for PDF.js code; docs are CC BY-SA 2.5. This is the active PDF path.
- [Foliate JS](https://github.com/johnfactotum/foliate-js) / local `static/foliate-js`: MIT. It vendors [zip.js](https://github.com/gildas-lormeau/zip.js), BSD-3-Clause, and [fflate](https://github.com/101arrowz/fflate), MIT.
- [JSZip 3.10.1](https://github.com/Stuk/jszip): MIT or GPL-3.0 dual license.
- [DOMPurify 3.2.4](https://github.com/cure53/DOMPurify): dual Apache-2.0 or MPL-2.0.
- [Mammoth.js 1.9.0](https://github.com/mwilliamson/mammoth.js): BSD-2-Clause.
- [marked 15.0.7](https://github.com/markedjs/marked): MIT; local `static/marked.min.js` header confirms version/license.
- Google Fonts Inter: loaded by `templates/reader_jshybrid.html`; include in third-party service/resource transparency.

### Dev-only / operational dependencies

- [Playwright](https://github.com/microsoft/playwright): Apache-2.0, listed in `package-lock.json`. Dev/test dependency, not user-facing runtime unless bundled into tooling.
- Debug/profiling tools in `debug_panel.py`, `debug_trace_runtime.py`, and local reports do not need public attribution unless deployed publicly, but their third-party dependencies still inherit the backend stack above.

## High-Priority Review List Before Building The Public Page

- Confirm the exact finished-model source for deployed runtime NER models that did not hash-match a folder in `training/trankit_finerweb_prep/trankit_training_run/finished_models`: `zh`, `zh-Hant`, `ja`, `ko`, `ar`, `fr`, `ru`, `es`, `de`, `nl`.
- Confirm exact licenses for deployed NER folders with unresolved or local provenance: `wikiann_vi`, `hye_wikiann`, `lzh_cmag_200k`, `grc_pausanias_ethnic_civic_misc`, `san_gemini_ner_chunks_0001_1800_corrected_supervised_even95_5`, and `swh_finerweb_top100_lpo_20260507_201707`.
- Verify/remove lingering PyMuPDF/`fitz` paths in `document_handling.py`. This inventory assumes the shipped PDF path is PDF.js-only; if those server-side paths remain reachable, PyMuPDF comes back as an AGPL/commercial compliance item.
- Confirm GPL/AGPL implications only for shipped/runtime items: EbookLib if EPUB handling remains server-side, Herodotos Latin NER, TLUnified-NER, and CAMeL/CALIMA data if enabled.
- Confirm exact dictionary source/version/license for Chinese Notes, DCS Sanskrit, Bosworth-Toller, and the local Wiktionary/Kaikki TSV conversion pipeline.
- For CC BY-SA dictionary content and UD/NER data, the transparency page should include: source name, upstream link, license link, whether the app modified/converted the data, and the runtime artifact it powers.
