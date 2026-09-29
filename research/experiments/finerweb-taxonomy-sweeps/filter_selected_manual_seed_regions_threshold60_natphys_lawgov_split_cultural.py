from __future__ import annotations

import filter_selected_manual_seed_regions_threshold75_natphys_lawgov_split_cultural as setup


setup.runner.THRESHOLD = 0.60
setup.runner.SUMMARY_OUT = setup.runner.OUT_DIR / "finerweb_selected_manual_seed_regions_threshold60_natphys_lawgov_split_cultural_summary.tsv"
setup.runner.TAG_MAP_OUT = setup.runner.OUT_DIR / "finerweb_selected_manual_seed_regions_threshold60_natphys_lawgov_split_cultural_retained_tag_map.tsv"
setup.runner.REPORT_OUT = setup.runner.OUT_DIR / "finerweb_selected_manual_seed_regions_threshold60_natphys_lawgov_split_cultural_report.md"
setup.runner.ASSIGNMENT_OUT = setup.runner.OUT_DIR / "finerweb_selected_manual_seed_regions_threshold60_natphys_lawgov_split_cultural_all_assignments.tsv"


if __name__ == "__main__":
    setup.runner.main()
