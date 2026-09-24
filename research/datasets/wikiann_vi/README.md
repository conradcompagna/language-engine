# Vietnamese WikiANN: Trankit preparation

Vietnamese WikiANN converted into Trankit BIO format.

Source: `training\nerdump\wikiann` parquet files.

Split policy: `train.bio` is WikiANN train + test joined together; `dev.bio` is WikiANN validation. `test.bio` is kept separately for auditing.

WikiANN label mapping from parquet metadata: `0=O`, `1=B-PER`, `2=I-PER`, `3=B-ORG`, `4=I-ORG`, `5=B-LOC`, `6=I-LOC`.

Corpus-build outputs: `train.bio`, `dev.bio`, `test.bio`, `all.bio`, `label_token_counts.tsv`, `dataset_report.json`.

The [dataset report](dataset_report.json) records corpus sizes and label counts.
The [model-run record](../../models/wikiann_vi/) connects
it to the NER training work.

The separately retained test copy overlaps training; I report this run's
results as [development F1](../../models/README.md#selected-training-results)
on the validation split.
