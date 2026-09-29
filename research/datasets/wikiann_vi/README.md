# Vietnamese WikiANN

Vietnamese WikiANN converted to Trankit BIO format, with tags `O`, `B-/I-PER`,
`B-/I-ORG` and `B-/I-LOC`.

Training data is the WikiANN train and test splits combined; development data is the
WikiANN validation split. Because the test split is part of the training data, results
for this run are development scores only.

Details are in [`dataset_report.json`](dataset_report.json). The training run is
[`../../models/wikiann_vi/`](../../models/wikiann_vi/).
