from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

import build_finerweb_final12_no_cultural_raw_dataset as raw


BASE = Path(__file__).resolve().parent
DATASETS = BASE / "datasets"
ASSIGNMENT_MAP = BASE / "derived_fasttext_categories" / "extended_main11_no_cultural_bucket_tag_map.tsv"
FINAL_TAG_MAP = BASE / "derived_fasttext_categories" / "extended_main11_threshold50_final_tag_map.tsv"
FINAL_SUMMARY = BASE / "derived_fasttext_categories" / "extended_main11_threshold50_summary.tsv"
MIN_SIMILARITY_PCT = 50.0

REGION_TO_FINAL = {
    "PERSON": "PERSON",
    "GROUP": "GROUP",
    "TITLE_ROLE": "TITLE_ROLE",
    "LOCATION": "LOCATION",
    "ORGANIZATION": "ORGANIZATION",
    "TIME": "TIME",
    "QUANTITY": "QUANTITY",
    "EVENT": "EVENT",
    "WORK_OF_ART": "WORK_OF_ART",
    "PRODUCT": "PRODUCT",
    "CONCEPT": "CONCEPT",
}

FINAL_LABELS = set(REGION_TO_FINAL.values())


def final_label_for_region(region: str) -> str:
    label = REGION_TO_FINAL.get(region)
    if label is None:
        raise ValueError(f"Unexpected vector region {region!r}")
    return label


def row_is_retained(row: dict[str, str]) -> bool:
    if row["assigned_region"] not in REGION_TO_FINAL:
        return False
    similarity = row["similarity_pct"].strip()
    if not similarity:
        return False
    return float(similarity) >= MIN_SIMILARITY_PCT


def load_assignment_rows() -> list[dict[str, str]]:
    with ASSIGNMENT_MAP.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def write_final_vector_sheets(rows: list[dict[str, str]]) -> None:
    with FINAL_TAG_MAP.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = [
            "row_id",
            "display_tag",
            "source_label",
            "source_kind",
            "count",
            "pct_total",
            "vector_region",
            "final_label",
            "retained",
            "assignment_source",
            "similarity_pct",
            "runner_up_region",
            "runner_up_similarity_pct",
            "margin_pct",
        ]
        writer = csv.DictWriter(handle, delimiter="\t", lineterminator="\n", fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            retained = row_is_retained(row)
            writer.writerow(
                {
                    "row_id": row["row_id"],
                    "display_tag": row["display_tag"],
                    "source_label": row["source_label"],
                    "source_kind": row["source_kind"],
                    "count": row["count"],
                    "pct_total": row["pct_total"],
                    "vector_region": row["assigned_region"],
                    "final_label": final_label_for_region(row["assigned_region"]) if retained else "",
                    "retained": "yes" if retained else "no",
                    "assignment_source": row["assignment_source"],
                    "similarity_pct": row["similarity_pct"],
                    "runner_up_region": row["runner_up_region"],
                    "runner_up_similarity_pct": row["runner_up_similarity_pct"],
                    "margin_pct": row["margin_pct"],
                }
            )

    summary: dict[str, dict[str, object]] = {}
    dropped_rows = 0
    dropped_mentions = 0
    retained_mentions = 0
    for row in rows:
        if not row_is_retained(row):
            dropped_rows += 1
            dropped_mentions += int(row["count"])
            continue
        final_label = final_label_for_region(row["assigned_region"])
        item = summary.setdefault(final_label, {"rows": 0, "mentions": 0, "regions": Counter()})
        item["rows"] = int(item["rows"]) + 1
        item["mentions"] = int(item["mentions"]) + int(row["count"])
        item["regions"][row["assigned_region"]] += int(row["count"])
        retained_mentions += int(row["count"])

    total = sum(int(row["count"]) for row in rows)
    with FINAL_SUMMARY.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["final_label", "candidate_rows", "mentions", "pct_total", "pct_retained", "source_vector_regions"])
        for label, item in sorted(summary.items(), key=lambda kv: (-int(kv[1]["mentions"]), kv[0])):
            regions = "; ".join(f"{region} ({count})" for region, count in item["regions"].most_common())
            mentions = int(item["mentions"])
            writer.writerow(
                [
                    label,
                    item["rows"],
                    mentions,
                    f"{mentions / total * 100:.6f}",
                    f"{mentions / retained_mentions * 100:.6f}" if retained_mentions else "",
                    regions,
                ]
            )
        writer.writerow(["DROPPED_BELOW_50_OR_NO_VECTOR", dropped_rows, dropped_mentions, f"{dropped_mentions / total * 100:.6f}", "", ""])


def load_vector_maps() -> tuple[dict[str, str], dict[str, str], dict[str, str], dict[str, str]]:
    rows = load_assignment_rows()
    write_final_vector_sheets(rows)

    coarse_to_label: dict[str, str] = {}
    exact_to_label: dict[str, str] = {}
    coarse_to_region: dict[str, str] = {}
    exact_to_region: dict[str, str] = {}
    for row in rows:
        if not row_is_retained(row):
            continue
        final_label = final_label_for_region(row["assigned_region"])
        source_label = raw.builder.norm_label(row["source_label"])
        if row["source_kind"] == "coarse":
            coarse = raw.builder.norm_label(row["display_tag"])
            coarse_to_label[coarse] = final_label
            coarse_to_region[coarse] = row["assigned_region"]
        else:
            exact_to_label[source_label] = final_label
            exact_to_region[source_label] = row["assigned_region"]
    return coarse_to_label, exact_to_label, coarse_to_region, exact_to_region


def configure() -> None:
    raw.ASSIGNMENT_MAP = ASSIGNMENT_MAP
    raw.FINAL_TAG_MAP = FINAL_TAG_MAP
    raw.FINAL_SUMMARY = FINAL_SUMMARY
    raw.OUTPUT_BY_LANG = DATASETS / "finerweb_extended_main11_threshold50_raw_by_language"
    raw.OUTPUT_COMBINED = DATASETS / "finerweb_extended_main11_threshold50_raw"
    raw.ZIP_BY_LANG = raw.OUTPUT_BY_LANG.with_suffix(".zip")
    raw.ZIP_COMBINED = raw.OUTPUT_COMBINED.with_suffix(".zip")
    raw.REGION_TO_FINAL = REGION_TO_FINAL
    raw.FINAL_LABELS = FINAL_LABELS
    raw.final_label_for_region = final_label_for_region
    raw.load_vector_maps = load_vector_maps

    raw.builder.DATASET_NAME = "finerweb_extended_main11_threshold50_raw"
    raw.builder.DATASET_DISPLAY_NAME = "extended_main11_threshold50_raw"
    raw.builder.DATASET_DESCRIPTION = (
        "Raw fiNERweb parquet character spans are projected to BIO, then mapped through the expanded "
        "main-category FastText seed centroids. Only PERSON, GROUP, TITLE_ROLE, LOCATION, ORGANIZATION, "
        "TIME, QUANTITY, EVENT, WORK_OF_ART, PRODUCT, and CONCEPT are retained. Labels below 50% "
        "similarity to their assigned centroid, plus unvectorized labels, are dropped."
    )
    raw.builder.SOURCE_ROOT = raw.RAW_ROOT
    raw.builder.OUTPUT_BY_LANG = raw.OUTPUT_BY_LANG
    raw.builder.OUTPUT_COMBINED = raw.OUTPUT_COMBINED
    raw.builder.ZIP_BY_LANG = raw.ZIP_BY_LANG
    raw.builder.ZIP_COMBINED = raw.ZIP_COMBINED
    raw.builder.RETAINED_MAP = FINAL_TAG_MAP
    raw.builder.REGION_LABELS = {label: label for label in FINAL_LABELS}


if __name__ == "__main__":
    configure()
    raw.main()
