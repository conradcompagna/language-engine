from __future__ import annotations

from pathlib import Path

import assign_coarse_tags_to_user_grouped_5050_no_cultural_bucket as base


OUT_DIR = Path(__file__).resolve().parent / "derived_fasttext_categories"

DROP_REGIONS = {
    "language",
    "industry",
    "material",
    "sport",
    "animal",
    "program",
    "award",
    "legal document | document",
}
DROP_TAGS = {
    "language",
    "animal",
    "material",
    "industry",
    "program",
    "award",
    "sport",
    "legal document",
    "document",
}

base.USER_GROUPS = [
    (region, seeds)
    for region, seeds in base.USER_GROUPS
    if region not in DROP_REGIONS
]

_base_load_rows = base.load_rows_with_cultural_orphans


def load_rows_with_drops():
    rows, _total = _base_load_rows()
    kept = [row for row in rows if str(row["coarse_tag"]) not in DROP_TAGS]
    total = sum(int(row["count"]) for row in kept)
    for row in kept:
        row["percent"] = int(row["count"]) / total * 100.0
    return kept, total


base.load_rows_with_cultural_orphans = load_rows_with_drops
base.SUMMARY_OUT = OUT_DIR / "user_grouped_5050_no_cultural_drop_low_legal_summary.tsv"
base.TAG_MAP_OUT = OUT_DIR / "user_grouped_5050_no_cultural_drop_low_legal_tag_map.tsv"
base.TOP10_OUT = OUT_DIR / "user_grouped_5050_no_cultural_drop_low_legal_top10_attracted.tsv"
base.REPORT_OUT = OUT_DIR / "user_grouped_5050_no_cultural_drop_low_legal_top10_attracted.md"


if __name__ == "__main__":
    base.main()
    report = base.REPORT_OUT.read_text(encoding="utf-8")
    report = report.replace(
        "# User Grouped 50/50 FastText Pass, No Cultural Reference Bucket",
        "# User Grouped 50/50 FastText Pass, Dropping Low Buckets And Legal Document/Document",
        1,
    )
    report = report.replace(
        "`cultural reference` is not a seed bucket.",
        "`cultural reference` is not a seed bucket. "
        "`language`, `animal`, `material`, `industry`, `program`, `award`, `sport`, "
        "`legal document`, and `document` are dropped from the candidate pool.",
        1,
    )
    base.REPORT_OUT.write_text(report, encoding="utf-8", newline="\n")
