# Model and corpus preparation

Training source is grouped by language or dataset. The repository includes architecture and preparation code; corpora, trained models, and generated evaluation output are external.

| Area | Contents |
|---|---|
| `ner/` | Shared NER training and Finerweb dataset builders |
| `arabiccomponents/` | Arabic tokenization, lemmatization, and Trankit experiments |
| `perseus/` | Ancient Greek treebank conversion and sampling |
| `oldeng/` | Old English dataset construction and training |
| `tagalog/`, `tagalog_mwt_retrain/` | Tagalog corpus, tokenizer, and multi-word-token work |
| `UD_Japanese-GSD-r2.10-NE/` | Japanese entity conversion, evaluation, and spaCy configurations |
| Sanskrit scripts and directories | DCS conversion, MWT datasets, NER annotation, and dictionary preparation |
| `upstream_patches/` | Trankit source patches; kept separate from authored-code formatting |

Each workflow has its own input paths and training dependencies. Run Python modules from the repository root where package imports are used. Inspect the selected script and its CLI before training; these are separate workflows, not one combined training command. Runtime ONNX artifact preparation is under `tools/models/`.
