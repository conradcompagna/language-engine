# Dataset cards

One directory per training corpus, holding a README, a machine-readable dataset report,
and label/token counts. Together they document source provenance, corpus size, and
supervision choices for the [model runs](../models/).

| Card | Language | Source |
|---|---|---|
| `ang_oedt/` | Old English | OEDT treebank |
| `grc_pausanias_ethnic_civic_misc/` | Ancient Greek | Pausanias, ethnic/civic/misc entity scheme |
| `lzh_cmag_200k/`, `lzh_cmag_1m/` | Classical Chinese | CMAG, two corpus sizes |
| `wikiann_vi/` | Vietnamese | WikiANN |
| `sanskrit_annotated_20_chunks_bio/` | Sanskrit | the Gemini-annotated set, see [the build chain](../pipeline/README.md#1b-sanskrit--named-entities-from-a-synthetic-corpus) |
| `thai_nner_full_coarse_bio/` | Thai | Thai-NNER, coarse BIO conversion |
