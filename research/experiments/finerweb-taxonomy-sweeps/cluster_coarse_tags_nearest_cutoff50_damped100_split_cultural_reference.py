from __future__ import annotations

from pathlib import Path

import cluster_coarse_tags_nearest_cutoff50_damped_split_cultural_reference as damped


BASE_DIR = Path(__file__).resolve().parent
OUT_DIR = BASE_DIR / "derived_fasttext_categories"

damped.DAMPING = 1.00
damped.SUMMARY_OUT = OUT_DIR / "coarse_nearest_cutoff50_damped100_split_cultural_reference_summary.tsv"
damped.TAG_MAP_OUT = OUT_DIR / "coarse_nearest_cutoff50_damped100_split_cultural_reference_tag_map.tsv"
damped.REPORT_OUT = OUT_DIR / "coarse_nearest_cutoff50_damped100_split_cultural_reference_report.md"


if __name__ == "__main__":
    damped.main()
