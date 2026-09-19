from __future__ import annotations

import csv

import build_finerweb_slim75_dataset as builder


builder.DATASET_NAME = "finerweb_slim75_natphys_lawgov"
builder.DATASET_DISPLAY_NAME = "slim75 nat/phys + law/governance"
builder.DATASET_DESCRIPTION = (
    "Original fiNERweb labels are mapped through the 75% FastText retained map with MEDIA, "
    "LAW_GOVERNANCE, NAT_PHYS_WORLD, and RELIGIOUS_PRACTICE included. LAW_GOVERNANCE is seeded with "
    "procedural/legal/governance labels, while institutional labels are seeded toward ORGANIZATION. "
    "Full original labels under each coarse tag provide vector evidence; no special cultural-reference child "
    "stripping is applied. Labels outside the retained map are dropped to `O`; sentences with no retained entity "
    "labels are omitted."
)

builder.OUTPUT_BY_LANG = builder.DATASETS / "finerweb_slim75_natphys_lawgov_by_language"
builder.OUTPUT_COMBINED = builder.DATASETS / "finerweb_slim75_natphys_lawgov"
builder.ZIP_BY_LANG = builder.OUTPUT_BY_LANG.with_suffix(".zip")
builder.ZIP_COMBINED = builder.OUTPUT_COMBINED.with_suffix(".zip")
builder.RETAINED_MAP = (
    builder.BASE
    / "derived_fasttext_categories"
    / "finerweb_selected_manual_seed_regions_threshold75_natphys_lawgov_split_cultural_retained_tag_map.tsv"
)

builder.REGION_LABELS = {
    "person": "PERSON",
    "location": "LOCATION",
    "organization": "ORGANIZATION",
    "product": "PRODUCT",
    "money": "MONEY",
    "time": "TIME",
    "event": "EVENT",
    "work of art": "WORK_OF_ART",
    "group": "GROUP",
    "language": "LANGUAGE",
    "quantity": "QUANTITY",
    "concept": "CONCEPT",
    "title": "TITLE",
    "media": "MEDIA",
    "law/governance": "LAW_GOVERNANCE",
    "religious practice": "RELIGIOUS_PRACTICE",
    "nat/phys world": "NAT_PHYS_WORLD",
}

RETAINED_ORIGINAL_LABELS: dict[str, str] = {}


def load_retained_coarse_map() -> dict[str, str]:
    retained_coarse: dict[str, str] = {}
    retained_original: dict[str, str] = {}
    with builder.RETAINED_MAP.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            region = row["retained_region"]
            bio_label = builder.REGION_LABELS.get(region)
            if bio_label is None:
                raise ValueError(f"Unexpected retained region {region!r}")

            map_level = row.get("map_level", "coarse")
            if map_level == "original":
                retained_original[builder.norm_label(row["original_label"])] = bio_label
            elif map_level == "coarse":
                retained_coarse[builder.norm_label(row["coarse_tag"])] = bio_label
            else:
                raise ValueError(f"Unexpected map_level {map_level!r}")

    RETAINED_ORIGINAL_LABELS.clear()
    RETAINED_ORIGINAL_LABELS.update(retained_original)
    return retained_coarse


def build_original_label_map(retained_coarse: dict[str, str]) -> dict[str, dict[str, str]]:
    label_map = {}
    with builder.LABEL_INVENTORY.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            original = row["original_label"]
            original_key = builder.norm_label(original)
            coarse, fine = builder.split_original_label(original)
            bucket = RETAINED_ORIGINAL_LABELS.get(original_key) or retained_coarse.get(coarse)
            label_map[original] = {
                "original_label": original,
                "coarse_label": coarse,
                "fine_label": fine,
                "count": row["count"],
                "retained_label": bucket or "",
                "status": "retained" if bucket else "dropped",
            }
    return label_map


builder.load_retained_coarse_map = load_retained_coarse_map
builder.build_original_label_map = build_original_label_map


if __name__ == "__main__":
    builder.main()
