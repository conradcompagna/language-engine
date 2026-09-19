from __future__ import annotations

import filter_selected_manual_seed_regions_threshold90 as runner


runner.THRESHOLD = 0.75
runner.RETAIN_ALL_SEEDS = False
runner.SUMMARY_OUT = runner.OUT_DIR / "finerweb_selected_manual_seed_regions_threshold75_summary.tsv"
runner.TAG_MAP_OUT = runner.OUT_DIR / "finerweb_selected_manual_seed_regions_threshold75_retained_tag_map.tsv"
runner.REPORT_OUT = runner.OUT_DIR / "finerweb_selected_manual_seed_regions_threshold75_report.md"


if __name__ == "__main__":
    runner.main()
