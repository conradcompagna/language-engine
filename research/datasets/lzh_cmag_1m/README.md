# Classical Chinese CMAG: one-million-token corpus

Ancient Chinese CMAG subset for Trankit NER training. The subset keeps complete sentences and lands at roughly one million non-blank source tokens.

Source: `training\nerdump\anc\AncientChineseProject-main.zip` / `AncientChineseProject-main/CMAG`.

I sampled complete sentences with a fixed seed: 800,018 training tokens from the upstream training pool, plus disjoint development and test subsets of 100,004 and 100,018 tokens from the upstream development pool. The dataset report records the seed and source-file selection.

CMAG BEIS labels were converted to BIO labels for Trankit: `*-S` and `*-B` become `B-*`; `*-I` and `*-E` become `I-*`; `O` stays `O`. Blank source tokens are skipped.

Corpus-build outputs: `train.bio`, `dev.bio`, `test.bio`, `all.bio`, `label_token_counts.tsv`, `dataset_report.json`.

The [dataset report](dataset_report.json) records corpus sizes and label counts.
The [model-run record](../../models/lzh_cmag_1m/) connects
it to the NER training work.
