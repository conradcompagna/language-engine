# NER dataset cards

Preparation records for five NER training corpora. Each folder has a README and a
`dataset_report.json` with split sizes and label counts. The corpus files themselves
are not included.

| Folder | Language | Source |
|---|---|---|
| [ang_oedt/](ang_oedt/) | Old English | OEDT treebank |
| [grc_pausanias_ethnic_civic_misc/](grc_pausanias_ethnic_civic_misc/) | Ancient Greek | Pausanias NER corpus with an added ethnic/civic-group label |
| [lzh_cmag_1m/](lzh_cmag_1m/) | Classical Chinese | CMAG, about 1 million tokens |
| [lzh_cmag_200k/](lzh_cmag_200k/) | Classical Chinese | One-in-five sample of `lzh_cmag_1m` |
| [wikiann_vi/](wikiann_vi/) | Vietnamese | WikiANN |

The Sanskrit NER corpus is documented in
[`../pipeline/README.md`](../pipeline/README.md#1b-sanskrit--semantic-annotations-over-authentic-texts).
The training runs that use these corpora are in [`../models/`](../models/).
