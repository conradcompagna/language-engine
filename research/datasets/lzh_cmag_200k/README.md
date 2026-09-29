# Classical Chinese CMAG: corpus-size comparison

A smaller Classical Chinese CMAG Trankit BIO dataset derived from `lzh_cmag_1m`.

Sampling rule:

```text
Take every fifth complete sentence from each original split: sentence_index % 5 == 0.
```

This keeps train/dev/test proportions close to the 1M-token source while reducing total size by about 5x.

Corpus-build outputs:

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

The [dataset report](dataset_report.json) records corpus sizes and label counts.
The [model-run record](../../models/lzh_cmag_200k/) connects
it to the NER training work.
