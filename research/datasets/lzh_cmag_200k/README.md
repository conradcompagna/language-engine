# Classical Chinese CMAG, 200k tokens

Every fifth sentence of each split of [`lzh_cmag_1m`](../lzh_cmag_1m/), keeping the
split proportions and reducing the size about five times.

| Split | Tokens |
|---|---:|
| train | 159,903 |
| dev | 20,030 |
| test | 20,467 |

Details are in [`dataset_report.json`](dataset_report.json). The training run is
[`../../models/lzh_cmag_200k/`](../../models/lzh_cmag_200k/); this is the Classical
Chinese NER model used in the application.
