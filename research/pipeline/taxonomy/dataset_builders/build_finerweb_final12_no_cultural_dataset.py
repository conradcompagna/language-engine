from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

import build_finerweb_slim75_dataset as builder


BASE = Path(__file__).resolve().parent
DATASETS = BASE / "datasets"
ASSIGNMENT_MAP = BASE / "derived_fasttext_categories" / "user_grouped_5050_no_cultural_bucket_tag_map.tsv"
FINAL_TAG_MAP = BASE / "derived_fasttext_categories" / "user_grouped_5050_no_cultural_final12_tag_map.tsv"
FINAL_SUMMARY = BASE / "derived_fasttext_categories" / "user_grouped_5050_no_cultural_final12_summary.tsv"


REGION_TO_FINAL = {
    "person | deity | religious figure | character": "PERSON",
    "location | country | city | region": "LOCATION",
    "organization | media | political/government/sports/web": "ORGANIZATION",
    "concept | science | medical/legal/economic": "CONCEPT",
    "product | technology | brand | food": "PRODUCT",
    "date | time period | year | duration": "TIME",
    "quantity | measurement | currency | percentage": "QUANTITY",
    "event": "EVENT",
    "title | profession | position": "TITLE",
    "work of art | film": "WORK_OF_ART",
    "nationality | group | ethnic/demographic": "GROUP",
    "legal document | document": "MISC",
    "language": "MISC",
    "animal": "MISC",
    "material": "MISC",
    "industry": "MISC",
    "program": "MISC",
    "award": "MISC",
    "sport": "MISC",
    "UNVECTORIZED": "MISC",
}

FINAL_LABELS = {
    "LOCATION",
    "PERSON",
    "ORGANIZATION",
    "CONCEPT",
    "PRODUCT",
    "TIME",
    "QUANTITY",
    "EVENT",
    "TITLE",
    "WORK_OF_ART",
    "GROUP",
    "MISC",
}


def load_assignment_rows() -> list[dict[str, str]]:
    with ASSIGNMENT_MAP.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle, delimiter="\t"))


def final_label_for_region(region: str) -> str:
    label = REGION_TO_FINAL.get(region)
    if label is None:
        raise ValueError(f"Unexpected vector region {region!r}")
    return label


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
            "assignment_source",
            "similarity_pct",
            "runner_up_region",
            "runner_up_similarity_pct",
            "margin_pct",
        ]
        writer = csv.DictWriter(handle, delimiter="\t", lineterminator="\n", fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "row_id": row["row_id"],
                    "display_tag": row["display_tag"],
                    "source_label": row["source_label"],
                    "source_kind": row["source_kind"],
                    "count": row["count"],
                    "pct_total": row["pct_total"],
                    "vector_region": row["assigned_region"],
                    "final_label": final_label_for_region(row["assigned_region"]),
                    "assignment_source": row["assignment_source"],
                    "similarity_pct": row["similarity_pct"],
                    "runner_up_region": row["runner_up_region"],
                    "runner_up_similarity_pct": row["runner_up_similarity_pct"],
                    "margin_pct": row["margin_pct"],
                }
            )

    summary: dict[str, dict[str, object]] = {}
    for row in rows:
        final_label = final_label_for_region(row["assigned_region"])
        bucket = summary.setdefault(
            final_label,
            {
                "rows": 0,
                "mentions": 0,
                "regions": Counter(),
            },
        )
        bucket["rows"] = int(bucket["rows"]) + 1
        bucket["mentions"] = int(bucket["mentions"]) + int(row["count"])
        bucket["regions"][row["assigned_region"]] += int(row["count"])
    total = sum(int(item["mentions"]) for item in summary.values())
    with FINAL_SUMMARY.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["final_label", "candidate_rows", "mentions", "pct_total", "source_vector_regions"])
        for label, item in sorted(summary.items(), key=lambda kv: (-int(kv[1]["mentions"]), kv[0])):
            regions = "; ".join(f"{region} ({count})" for region, count in item["regions"].most_common())
            writer.writerow([label, item["rows"], item["mentions"], f"{int(item['mentions']) / total * 100:.6f}", regions])


def load_final_maps() -> tuple[dict[str, str], dict[str, str]]:
    rows = load_assignment_rows()
    write_final_vector_sheets(rows)

    coarse_to_label: dict[str, str] = {}
    exact_to_label: dict[str, str] = {}
    for row in rows:
        final_label = final_label_for_region(row["assigned_region"])
        source_label = builder.norm_label(row["source_label"])
        if row["source_kind"] == "coarse":
            coarse_to_label[builder.norm_label(row["display_tag"])] = final_label
        else:
            exact_to_label[source_label] = final_label
    return coarse_to_label, exact_to_label


def load_retained_coarse_map() -> dict[str, str]:
    coarse_to_label, _exact_to_label = load_final_maps()
    return coarse_to_label


def build_original_label_map(retained_coarse: dict[str, str]) -> dict[str, dict[str, str]]:
    _coarse_to_label, exact_to_label = load_final_maps()
    label_map = {}
    with builder.LABEL_INVENTORY.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            original = row["original_label"]
            original_norm = builder.norm_label(original)
            coarse, fine = builder.split_original_label(original)
            if original_norm in exact_to_label:
                bucket = exact_to_label[original_norm]
                status = "retained"
            else:
                bucket = retained_coarse.get(coarse)
                status = "retained" if bucket else "dropped"
            label_map[original] = {
                "original_label": original,
                "coarse_label": coarse,
                "fine_label": fine,
                "count": row["count"],
                "retained_label": bucket or "",
                "status": status if bucket else "dropped",
            }
            label_map[original_norm] = label_map[original]
    return label_map


builder.DATASET_NAME = "finerweb_final12_no_cultural"
builder.DATASET_DISPLAY_NAME = "final12_no_cultural"
builder.DATASET_DESCRIPTION = (
    "Original fiNERweb labels are mapped through the full 50/50 parent-child FastText assignment. "
    "The `cultural reference` aggregate is not a vector bucket; its child labels are mapped by child text. "
    "Low singleton/vector buckets and legal-document/document are collapsed to MISC after vector assignment."
)
builder.SOURCE_ROOT = DATASETS / "finerweb_plo75_by_language_ready"
builder.OUTPUT_BY_LANG = DATASETS / "finerweb_final12_no_cultural_by_language"
builder.OUTPUT_COMBINED = DATASETS / "finerweb_final12_no_cultural"
builder.ZIP_BY_LANG = builder.OUTPUT_BY_LANG.with_suffix(".zip")
builder.ZIP_COMBINED = builder.OUTPUT_COMBINED.with_suffix(".zip")
builder.RETAINED_MAP = FINAL_TAG_MAP
builder.REGION_LABELS = {label: label for label in FINAL_LABELS}
builder.load_retained_coarse_map = load_retained_coarse_map
builder.build_original_label_map = build_original_label_map


if __name__ == "__main__":
    builder.main()
