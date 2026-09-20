# ang_oedt

Old English OEDT NER dataset converted/copied into Trankit BIO format.

Source: `training\nerdump\commercial_ner_datasets_downloaded.zip` members under `datasets/ang/Old_English-OEDT/`.

Files: `train.bio`, `dev.bio`, `test.bio`, `all.bio`, `label_token_counts.tsv`, `dataset_report.json`.

Use with:

```powershell
python training\trankit_finerweb_prep\trankit_training_run\train_ner.py --dataset-dir training\trankit_finerweb_prep\datasets\ang_oedt --run-id ang_oedt
```
