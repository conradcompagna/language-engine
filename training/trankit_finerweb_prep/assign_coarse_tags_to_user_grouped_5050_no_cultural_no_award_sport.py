from __future__ import annotations

from pathlib import Path

import assign_coarse_tags_to_user_grouped_5050_no_cultural_bucket as base


OUT_DIR = Path(__file__).resolve().parent / "derived_fasttext_categories"

base.USER_GROUPS = [
    (region, seeds)
    for region, seeds in base.USER_GROUPS
    if region not in {"sport", "award"}
]
base.SUMMARY_OUT = OUT_DIR / "user_grouped_5050_no_cultural_no_award_sport_summary.tsv"
base.TAG_MAP_OUT = OUT_DIR / "user_grouped_5050_no_cultural_no_award_sport_tag_map.tsv"
base.TOP10_OUT = OUT_DIR / "user_grouped_5050_no_cultural_no_award_sport_top10_attracted.tsv"
base.REPORT_OUT = OUT_DIR / "user_grouped_5050_no_cultural_no_award_sport_top10_attracted.md"


if __name__ == "__main__":
    base.main()
    report = base.REPORT_OUT.read_text(encoding="utf-8")
    report = report.replace(
        "# User Grouped 50/50 FastText Pass, No Cultural Reference Bucket",
        "# User Grouped 50/50 FastText Pass, No Cultural Reference, Award, or Sport Buckets",
        1,
    )
    report = report.replace(
        "`cultural reference` is not a seed bucket.",
        "`cultural reference`, `award`, and `sport` are not seed buckets.",
        1,
    )
    base.REPORT_OUT.write_text(report, encoding="utf-8", newline="\n")
