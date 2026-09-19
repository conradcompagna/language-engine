from __future__ import annotations

import build_finerweb_slim75_natphys_lawgov_dataset as setup


setup.builder.DATASET_NAME = "finerweb_slim60_natphys_lawgov"
setup.builder.DATASET_DISPLAY_NAME = "slim60 nat/phys + law/governance"
setup.builder.OUTPUT_BY_LANG = setup.builder.DATASETS / "finerweb_slim60_natphys_lawgov_by_language"
setup.builder.OUTPUT_COMBINED = setup.builder.DATASETS / "finerweb_slim60_natphys_lawgov"
setup.builder.ZIP_BY_LANG = setup.builder.OUTPUT_BY_LANG.with_suffix(".zip")
setup.builder.ZIP_COMBINED = setup.builder.OUTPUT_COMBINED.with_suffix(".zip")
setup.builder.RETAINED_MAP = (
    setup.builder.BASE
    / "derived_fasttext_categories"
    / "finerweb_selected_manual_seed_regions_threshold60_natphys_lawgov_split_cultural_retained_tag_map.tsv"
)


if __name__ == "__main__":
    setup.builder.main()
