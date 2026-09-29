from __future__ import annotations

import filter_selected_manual_seed_regions_threshold90 as runner


runner.THRESHOLD = 0.50
runner.RETAIN_ALL_SEEDS = False
runner.SUMMARY_OUT = runner.OUT_DIR / "finerweb_selected_manual_seed_regions_threshold50_summary.tsv"
runner.TAG_MAP_OUT = runner.OUT_DIR / "finerweb_selected_manual_seed_regions_threshold50_retained_tag_map.tsv"
runner.REPORT_OUT = runner.OUT_DIR / "finerweb_selected_manual_seed_regions_threshold50_report.md"


if __name__ == "__main__":
    runner.main()
