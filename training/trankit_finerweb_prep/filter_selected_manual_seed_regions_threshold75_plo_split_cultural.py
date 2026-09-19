from __future__ import annotations

import compute_latest_seed_coverage_v5 as latest
import filter_selected_manual_seed_regions_threshold60_concept_title_split_cultural as runner


runner.THRESHOLD = 0.75
runner.SUMMARY_OUT = runner.OUT_DIR / "finerweb_selected_manual_seed_regions_threshold75_plo_split_cultural_summary.tsv"
runner.TAG_MAP_OUT = runner.OUT_DIR / "finerweb_selected_manual_seed_regions_threshold75_plo_split_cultural_retained_tag_map.tsv"
runner.REPORT_OUT = runner.OUT_DIR / "finerweb_selected_manual_seed_regions_threshold75_plo_split_cultural_report.md"
runner.ASSIGNMENT_OUT = runner.OUT_DIR / "finerweb_selected_manual_seed_regions_threshold75_plo_split_cultural_all_assignments.tsv"

runner.SELECTED_REGIONS = {
    "person": latest.SEEDS["person"],
    "location": latest.SEEDS["location"],
    "organization": latest.SEEDS["organization"],
}


if __name__ == "__main__":
    runner.main()
