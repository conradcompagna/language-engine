# fiNERweb Trankit NER prep

Created: 2026-05-03T01:01:08

Source folder: `training\nerdump\fiNERweb_app_languages`

This is the review stage only. No labels were dropped. Every original fiNERweb label seen across all local fiNERweb parquet files is mapped to exactly one proposed bucket in `finerweb_label_bucket_map.tsv` and `finerweb_label_bucket_map.json`.

Files:

- `finerweb_source_files.tsv`: source parquet files, rows, spans.
- `finerweb_label_inventory.tsv`: global original label counts and proposed bucket.
- `finerweb_label_bucket_map.tsv`: review file with bucket, original label, count, language counts, and mention examples.
- `finerweb_label_bucket_map.json`: machine-readable mapping to edit/review.
- `finerweb_bucket_summary.tsv`: aggregate span counts per proposed bucket.

Next step after review: convert each parquet to Trankit-style BIO/CoNLL using the reviewed bucket map.
