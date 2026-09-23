# wikiann_vi

Vietnamese WikiANN converted into Trankit BIO format.

Source: `training\nerdump\wikiann` parquet files.

Split policy: `train.bio` is WikiANN train + test joined together; `dev.bio` is WikiANN validation. `test.bio` is kept separately for auditing.

WikiANN label mapping from parquet metadata: `0=O`, `1=B-PER`, `2=I-PER`, `3=B-ORG`, `4=I-ORG`, `5=B-LOC`, `6=I-LOC`.

Files: `train.bio`, `dev.bio`, `test.bio`, `all.bio`, `label_token_counts.tsv`, `dataset_report.json`.

Use with:

```powershell
python research/pipeline/models/train_ner.py --dataset-dir /path/to/wikiann_vi --run-id wikiann_vi
```

The retained test split overlaps training by design and must not be used as a held-out test score; supply authorized local files for the command above.
