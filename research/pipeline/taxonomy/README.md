# NER label taxonomy

Scripts for grouping the fine-grained FiNERweb entity labels into coarse label sets
suitable for training. Labels are compared by fastText embeddings of the label strings
and by co-occurrence, then grouped with Louvain community detection or centroid
clustering. The review inventories these scripts produced are not included.

| Scripts | Role |
|---|---|
| `cluster_all_finerweb_labels_fasttext.py`, `derive_finerweb_fasttext_categories.py` | Embed and cluster all labels |
| `build_statistical_ner_taxonomy_louvain.py`, `build_statistical_ner_taxonomy_louvain_full_tagset.py` | Louvain communities over label co-occurrence |
| `cluster_coarse_tags_centroid_freqweighted_internalcoherence90_intact.py`, `cluster_coarse_tags_snowball_recursive.py`, `greedy_foundational_coarse_tags.py` | Alternative grouping methods |
| `pairwise_coarse_tag_similarity.py`, `compute_user_category_similarity.py`, `balance_user_labels_by_fasttext.py`, `build_coarse_tag_grouping_recommendation.py` | Compare and adjust candidate groupings |
| `extract_finerweb_coarse_examples_ge100.py`, `sample_finerweb_ge100_tag_span_examples.py`, `write_top500_freqweighted_threshold_md_reports_90_to70.py` | Examples and review reports |
| `dataset_builders/` | One script per candidate label scheme, each building a training set |

Parameter sweeps behind these scripts are in
[`../../experiments/finerweb-taxonomy-sweeps/`](../../experiments/finerweb-taxonomy-sweeps/).
