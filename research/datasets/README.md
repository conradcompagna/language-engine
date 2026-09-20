# Dataset cards

One directory per training corpus, holding a README, a machine-readable dataset report,
and label/token counts. **No corpora.** These record what each dataset contains, how
big it is, and where it came from, so the training configurations in `../models/` can
be interpreted without the data.

| Card | Language | Source |
|---|---|---|
| `ang_oedt/` | Old English | OEDT treebank |
| `grc_pausanias_ethnic_civic_misc/` | Ancient Greek | Pausanias, ethnic/civic/misc entity scheme |
| `lzh_cmag_200k/`, `lzh_cmag_1m/` | Classical Chinese | CMAG, two corpus sizes |
| `wikiann_vi/` | Vietnamese | WikiANN |
| `sanskrit_annotated_20_chunks_bio/` | Sanskrit | the Gemini-annotated set, see [the build chain](../pipeline/README.md#1b-sanskrit--named-entities-from-a-synthetic-corpus) |
| `thai_nner_full_coarse_bio/` | Thai | Thai-NNER, coarse BIO conversion |
