# Old English OEDT: corpus preparation

I prepared the Old English OEDT NER dataset in Trankit BIO format.

Source: `training\nerdump\commercial_ner_datasets_downloaded.zip` members under `datasets/ang/Old_English-OEDT/`.

Corpus-build outputs: `train.bio`, `dev.bio`, `test.bio`, `all.bio`, `label_token_counts.tsv`, `dataset_report.json`.

The [dataset report](dataset_report.json) records corpus sizes and label counts.
The [model-run record](../../models/ang_oedt/) connects
it to the NER training work.
