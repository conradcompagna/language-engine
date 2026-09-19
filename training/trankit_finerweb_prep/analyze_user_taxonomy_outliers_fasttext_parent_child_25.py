from __future__ import annotations

import analyze_user_taxonomy_outliers_fasttext_parent_child_50 as run


run.RUN_SLUG = "parent_child_25"
run.RUN_TITLE = "Parent/Child 25-75"
run.PARENT_WEIGHT = 0.25
run.CHILD_WEIGHT = 0.75
run.OUT_TSV = run.full.OUT_DIR / f"user_13_bucket_fasttext_outliers_{run.RUN_SLUG}.tsv"
run.OUT_MD = run.full.OUT_DIR / f"user_13_bucket_fasttext_outliers_{run.RUN_SLUG}.md"
run.OUT_CROSS_TSV = run.full.OUT_DIR / f"user_13_bucket_fasttext_outliers_{run.RUN_SLUG}_cross_bucket_all.tsv"
run.OUT_CROSS_BY_BUCKET_MD = run.full.OUT_DIR / f"user_13_bucket_fasttext_outliers_{run.RUN_SLUG}_cross_bucket_by_bucket.md"
run.OUT_CROSS_BY_BUCKET_TSV = run.full.OUT_DIR / f"user_13_bucket_fasttext_outliers_{run.RUN_SLUG}_cross_bucket_by_bucket.tsv"
run.OUT_CROSS_BY_BUCKET_GT10_MD = run.full.OUT_DIR / f"user_13_bucket_fasttext_outliers_{run.RUN_SLUG}_cross_bucket_by_bucket_gt10.md"
run.OUT_CROSS_BY_BUCKET_GT10_TSV = run.full.OUT_DIR / f"user_13_bucket_fasttext_outliers_{run.RUN_SLUG}_cross_bucket_by_bucket_gt10.tsv"


if __name__ == "__main__":
    run.main()
