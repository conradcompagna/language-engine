# FiNERweb label-taxonomy preparation

Created: 2026-05-03T01:01:08

Source folder: `training\nerdump\fiNERweb_app_languages`

I built this review inventory to organize the fine-grained FiNERweb labels into candidate training categories. It preserves every original label across the source parquet files and assigns each to one proposed bucket, with counts, language distributions and mention examples supporting review.

Files:

- `finerweb_source_files.tsv`: source parquet files, rows, spans.
- `finerweb_label_inventory.tsv`: global original label counts and proposed bucket.
- `finerweb_label_bucket_map.tsv`: review file with bucket, original label, count, language counts, and mention examples.
- `finerweb_label_bucket_map.json`: machine-readable mapping to edit/review.
- `finerweb_bucket_summary.tsv`: aggregate span counts per proposed bucket.

The [dataset builders](dataset_builders/) encode the candidate label schemes for Trankit training; the [taxonomy experiments](../../experiments/finerweb-taxonomy-sweeps/OUTCOME.md) record the clustering and acceptance criteria.
