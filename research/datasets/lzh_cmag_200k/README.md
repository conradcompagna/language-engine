# lzh_cmag_200k

A smaller Classical Chinese CMAG Trankit BIO dataset derived from `lzh_cmag_1m`.

Sampling rule:

```text
Take every fifth complete sentence from each original split: sentence_index % 5 == 0.
```

This keeps train/dev/test proportions close to the 1M-token source while reducing total size by about 5x.

Files:

```text
train.bio
dev.bio
test.bio
all.bio
label_token_counts.tsv
dataset_report.json
```

Token counts:

```text
train  159,903
dev     20,030
test    20,467
all    200,400
```

Train with:

```powershell
python training\trankit_finerweb_prep\trankit_training_run\train_ner.py --dataset-dir training\trankit_finerweb_prep\datasets\lzh_cmag_200k --run-id lzh_cmag_200k
```
