# Arabic segmentation training data

Builds the training data for the Arabic tokenizer and clitic expander (run `t_ar10k2`).

| Script | Role |
|---|---|
| `build_cameltools_tokenizer_dataset.py` | Annotates 10,000 sentences of `ara_news_2022` with the CAMeL Tools `calima-msa-r13` analyzer (ATB tokenization) and writes a 95/5 CoNLL-U split |
| `fix_conllu.py` | Corrects recurring analyzer errors: false proper-noun and nisba splits, truncated expansions, NOAN output, and preposition and suffix forms |

The scripts use the file names of the original training folder. The released model is
described in [`../../../releases/arabic-clitic-tokenizer/`](../../../releases/arabic-clitic-tokenizer/).
