# lzh_cmag_1m

Ancient Chinese CMAG subset for Trankit NER training. The subset keeps complete sentences and lands at roughly one million non-blank source tokens.

Source: `training\nerdump\anc\AncientChineseProject-main.zip` / `AncientChineseProject-main/CMAG`.

Split construction: deterministic shuffled subset with about 800k train tokens and about 100k each for dev/test from the original dev split. The original CMAG test pickle is not used because it does not unpickle cleanly locally.

CMAG BEIS labels were converted to BIO labels for Trankit: `*-S` and `*-B` become `B-*`; `*-I` and `*-E` become `I-*`; `O` stays `O`. Blank source tokens are skipped.

Files: `train.bio`, `dev.bio`, `test.bio`, `all.bio`, `label_token_counts.tsv`, `dataset_report.json`.

Use with:

```powershell
python training\trankit_finerweb_prep\trankit_training_run\train_ner.py --dataset-dir training\trankit_finerweb_prep\datasets\lzh_cmag_1m --run-id lzh_cmag_1m
```
