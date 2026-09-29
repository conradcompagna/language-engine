# Classical Chinese CMAG, 1 million tokens

A subset of the CMAG Classical Chinese NER corpus (AncientChineseProject), sampled as
complete sentences with a fixed seed: 800,018 training tokens from the CMAG training
split, and disjoint development (100,004) and test (100,018) sets from the CMAG
development split. The original CMAG test file could not be read and was not used.

CMAG's BEIS tags were converted to BIO: `*-S` and `*-B` become `B-*`; `*-I` and `*-E`
become `I-*`.

Details are in [`dataset_report.json`](dataset_report.json). The training run is
[`../../models/lzh_cmag_1m/`](../../models/lzh_cmag_1m/).
