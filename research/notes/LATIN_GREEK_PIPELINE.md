# Latin and Ancient Greek: lexical and model engineering

Classical-language support combines scholarly lexical sources, inflected-form
lookup, Unicode handling, and language-specific NLP models within the shared
reading application. The work spans data conversion, morphological resource
construction, quality studies, and model integration.

## Runtime integration

[language_registry.py](../../language_registry.py) registers Latin (`la`) and
Ancient Greek (`grc`), with [Latin display configuration](../../wiktionary_general/lang_config_la.json)
and [Greek display configuration](../../wiktionary_general/lang_config_grc.json).
They use the same [hybrid lookup flow](NLP_HUB_CONSTRUCTION_REPORT.md): neural
analysis, browser candidate selection, SQLite hydration, and shared dictionary
rendering. The registry selects the dictionary sources available to the reader;
separately built research dictionaries have their own construction records.

## Dictionary construction

| Work | Published implementation and evidence |
|---|---|
| Wiktionary/Kaikki conversion | [JSONL-to-TSV converter](../pipeline/dictionaries/wiktionary/convert_jsonl_to_tsv.py) and [SQLite builder](../pipeline/dictionaries/convert_tsv_to_sqlite.py) |
| Perseus LSJ import | [TEI importer](../pipeline/dictionaries/convert_lsj_to_sqlite.py) and [streaming ZIP importer](../pipeline/dictionaries/convert_lsj_zip_to_sqlite.py) |
| Greek inflectional paradigms | [Paradigm exporter](../pipeline/dictionaries/export_grc_lsj_greek_inflexion.py) |
| Form integration and entry consolidation | [Regeneration script](../pipeline/dictionaries/regenerate_grc_lsj_sqlite.py) and [recorded summary](../evaluation/reports/grc_lsj_regeneration_summary.json) |
| Cross-source comparison | [LSJ and Wiktionary samples](../evaluation/reports/grc_lsj_vs_wiktionary_samples.md) |
| Form-quality review | [Greek form audit](../evaluation/reports/grc_wiktionary_forms_artifact_sweep_2026-04-11.md) and [multilingual form audit](../evaluation/reports/wiktionary_forms_surface_audit_2026-04-11.md) |

The Wiktionary converter preserves source readings and form tags. The LSJ
importers parse scholarly TEI data, convert Beta Code, and shape entries for
SQLite. The paradigm exporter integrates upstream inflection and accentuation
libraries with LSJ lemmas; the regeneration step merges those forms with
usable entries. Its saved run records **884,289 generated forms inserted** and
**914,813 final form rows**. These are construction results from that run.

The comparison samples retain the distinction between Wiktionary's supplied
forms and paradigms generated for the LSJ resource. This makes the source and
transformation behind a lexical match inspectable.

## Normalization and display

[Dictionary key normalization](../../static/dictionary_normalization_layer.js)
handles lookup equivalences such as final sigma, Greek diacritics, apostrophes,
and editorial marks. [NLP normalization](../../universal_normalization.py)
prepares model input and offset maps. Display fields retain the source spelling
and reading, with the matched form and lemma represented separately in the
[hydration contract](HYDRATION_FIRST_RENDERING_REFERENCE.md).

Contextual entry generation uses [morphology policy](../../language_engine/gemini/morphology.py)
and [structured prompts](../../language_engine/gemini/prompts.py). Latin and
Ancient Greek receive inflection-aware lemma and morphology fields; Greek also
requests a romanized reading. These services are separate from dictionary import.

## NER and linguistic supervision

The [Latin training configuration](../models/lat_herodotos_latin_ner/training_config.json)
records the Herodotos-derived BIO inputs, XLM-R base encoder, batch size, and
epoch budget. The [Ancient Greek dataset card](../datasets/grc_pausanias_ethnic_civic_misc/README.md)
records the Pausanias-derived label mapping, including `ETHNIC_CIVIC_GROUP`,
alongside person, location, and miscellaneous entities. Its
[model configuration](../models/grc_pausanias_ethnic_civic_misc/training_config.json)
connects that corpus to training.

[Perseus treebank conversion](../pipeline/datasets/ancient_greek/convert_perseus_greek_to_conllu.py)
supplies a separate path for dependency data. The [training record](../STATUS.md)
and [model guide](../models/README.md) distinguish saved run configurations,
selected results, and application model resources. Dataset provenance and
upstream terms are recorded with the [published resources](../../THIRD_PARTY_NOTICES.md).
