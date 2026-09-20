from __future__ import annotations

import csv
import json
import shutil
from pathlib import Path

import numpy as np

import build_finerweb_final12_no_cultural_raw_dataset as raw_builder
import build_finerweb_slim75_dataset as generic_builder
import cluster_coarse_tags_pairwise_member_purity90_cultural_modes as pairwise


BASE = Path(__file__).resolve().parent
DATASETS = BASE / "datasets"
OUT_DIR = BASE / "derived_fasttext_categories" / "minimal9_seed90_weighted_centroids"

ASSIGNMENT_MAP = OUT_DIR / "minimal9_seed90_assignment_map.tsv"
TAG_MAP = OUT_DIR / "minimal9_seed90_final_tag_map.tsv"
SUMMARY = OUT_DIR / "minimal9_seed90_summary.tsv"

OUTPUT_BY_LANG = DATASETS / "finerweb_minimal9_seed90_raw_by_language"
OUTPUT_COMBINED = DATASETS / "finerweb_minimal9_seed90_raw"
ZIP_BY_LANG = OUTPUT_BY_LANG.with_suffix(".zip")
ZIP_COMBINED = OUTPUT_COMBINED.with_suffix(".zip")

THRESHOLD = 0.90

SEED_LABELS = {
    "PERSON": ["person"],
    "LOCATION": ["location", "country"],
    "ORGANIZATION": ["organization"],
    "TIME": ["date", "time period"],
    "QUANTITY": ["quantity"],
    "CULTURAL_REFERENCE": ["cultural reference"],
    "EVENT": ["event"],
    "PRODUCT": ["product", "technology"],
    "CONCEPT": ["scientific concept", "concept"],
}

FINAL_LABELS = set(SEED_LABELS)


def normalize(vec: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(vec)
    if not norm:
        return vec.astype(np.float32)
    return (vec / norm).astype(np.float32)


def weighted_centroid(indices: list[int], rows: list[dict[str, object]]) -> np.ndarray:
    vectors = np.stack([rows[idx]["vector"] for idx in indices]).astype(np.float32)
    weights = np.array([float(rows[idx]["count"]) for idx in indices], dtype=np.float64)
    return normalize(np.average(vectors, axis=0, weights=weights))


def build_assignment_map() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows, unvectorized, total_count = pairwise.load_intact_rows()
    rows.sort(key=lambda row: (-int(row["count"]), str(row["coarse_tag"])))

    by_tag = {str(row["coarse_tag"]): idx for idx, row in enumerate(rows)}
    centroids = {}
    seed_indices_by_label = {}
    for label, seeds in SEED_LABELS.items():
        missing = [seed for seed in seeds if seed not in by_tag]
        if missing:
            raise RuntimeError(f"Missing seed tags for {label}: {missing}")
        indices = [by_tag[seed] for seed in seeds]
        seed_indices_by_label[label] = set(indices)
        centroids[label] = weighted_centroid(indices, rows)

    labels = list(SEED_LABELS)
    center_matrix = np.stack([centroids[label] for label in labels]).astype(np.float32)

    retained_rows = []
    rejected_rows = []
    for idx, row in enumerate(rows):
        sims = center_matrix @ row["vector"]
        order = np.argsort(-sims)
        best_pos = int(order[0])
        second_pos = int(order[1]) if len(order) > 1 else best_pos
        label = labels[best_pos]
        best_sim = float(sims[best_pos])
        second_label = labels[second_pos]
        second_sim = float(sims[second_pos])
        is_seed = idx in seed_indices_by_label[label]
        retained = best_sim >= THRESHOLD
        item = {
            "row_id": str(idx + 1),
            "display_tag": row["coarse_tag"],
            "source_label": row["coarse_tag"],
            "source_kind": "coarse",
            "count": int(row["count"]),
            "pct_total": float(row["percent"]),
            "assigned_region": label,
            "assignment_source": "seed" if is_seed else "centroid_threshold90",
            "similarity_pct": best_sim * 100.0,
            "runner_up_region": second_label,
            "runner_up_similarity_pct": second_sim * 100.0,
            "margin_pct": (best_sim - second_sim) * 100.0,
        }
        if retained:
            retained_rows.append(item)
        else:
            rejected_rows.append(item)

    with ASSIGNMENT_MAP.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = [
            "row_id",
            "display_tag",
            "source_label",
            "source_kind",
            "count",
            "pct_total",
            "assigned_region",
            "assignment_source",
            "similarity_pct",
            "runner_up_region",
            "runner_up_similarity_pct",
            "margin_pct",
        ]
        writer = csv.DictWriter(handle, delimiter="\t", lineterminator="\n", fieldnames=fieldnames)
        writer.writeheader()
        for item in sorted(retained_rows, key=lambda row: (-int(row["count"]), str(row["display_tag"]))):
            writer.writerow(
                {
                    **item,
                    "pct_total": f"{item['pct_total']:.6f}",
                    "similarity_pct": f"{item['similarity_pct']:.2f}",
                    "runner_up_similarity_pct": f"{item['runner_up_similarity_pct']:.2f}",
                    "margin_pct": f"{item['margin_pct']:.2f}",
                }
            )

    with (OUT_DIR / "minimal9_seed90_rejected.tsv").open("w", encoding="utf-8", newline="") as handle:
        fieldnames = [
            "display_tag",
            "count",
            "pct_total",
            "best_region",
            "similarity_pct",
            "runner_up_region",
            "runner_up_similarity_pct",
            "margin_pct",
        ]
        writer = csv.DictWriter(handle, delimiter="\t", lineterminator="\n", fieldnames=fieldnames)
        writer.writeheader()
        for item in sorted(rejected_rows, key=lambda row: (-int(row["count"]), str(row["display_tag"]))):
            writer.writerow(
                {
                    "display_tag": item["display_tag"],
                    "count": item["count"],
                    "pct_total": f"{item['pct_total']:.6f}",
                    "best_region": item["assigned_region"],
                    "similarity_pct": f"{item['similarity_pct']:.2f}",
                    "runner_up_region": item["runner_up_region"],
                    "runner_up_similarity_pct": f"{item['runner_up_similarity_pct']:.2f}",
                    "margin_pct": f"{item['margin_pct']:.2f}",
                }
            )

    summary_rows = {}
    for item in retained_rows:
        bucket = summary_rows.setdefault(item["assigned_region"], {"tags": 0, "mentions": 0, "seeds": 0})
        bucket["tags"] += 1
        bucket["mentions"] += int(item["count"])
        if item["assignment_source"] == "seed":
            bucket["seeds"] += 1

    with SUMMARY.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["label", "retained_tags", "seed_tags", "mentions", "pct_total"])
        for label, item in sorted(summary_rows.items(), key=lambda kv: (-kv[1]["mentions"], kv[0])):
            writer.writerow([label, item["tags"], item["seeds"], item["mentions"], f"{item['mentions'] / total_count * 100.0:.6f}"])
        writer.writerow(["__TOTAL_RETAINED__", len(retained_rows), "", sum(int(item["count"]) for item in retained_rows), f"{sum(int(item['count']) for item in retained_rows) / total_count * 100.0:.6f}"])
        writer.writerow(["__TOTAL_REJECTED__", len(rejected_rows), "", sum(int(item["count"]) for item in rejected_rows), f"{sum(int(item['count']) for item in rejected_rows) / total_count * 100.0:.6f}"])
        writer.writerow(["__UNVECTORIZED__", len(unvectorized), "", sum(int(row["count"]) for row in unvectorized), f"{sum(int(row['count']) for row in unvectorized) / total_count * 100.0:.6f}"])


def configure_raw_builder() -> None:
    raw_builder.ASSIGNMENT_MAP = ASSIGNMENT_MAP
    raw_builder.FINAL_TAG_MAP = TAG_MAP
    raw_builder.FINAL_SUMMARY = SUMMARY
    raw_builder.OUTPUT_BY_LANG = OUTPUT_BY_LANG
    raw_builder.OUTPUT_COMBINED = OUTPUT_COMBINED
    raw_builder.ZIP_BY_LANG = ZIP_BY_LANG
    raw_builder.ZIP_COMBINED = ZIP_COMBINED
    raw_builder.REGION_TO_FINAL = {label: label for label in FINAL_LABELS}
    raw_builder.FINAL_LABELS = FINAL_LABELS

    generic_builder.DATASET_NAME = "finerweb_minimal9_seed90_raw"
    generic_builder.DATASET_DISPLAY_NAME = "minimal9_seed90_raw"
    generic_builder.DATASET_DESCRIPTION = (
        "Raw fiNERweb parquet character spans are projected to BIO, then mapped through a 9-label "
        "frequency-weighted seed-centroid map. Coarse tags are retained only if their best seed-centroid "
        "similarity is at least 90%; all other tags are dropped, and sentences with no retained labels are omitted."
    )
    generic_builder.SOURCE_ROOT = raw_builder.RAW_ROOT
    generic_builder.OUTPUT_BY_LANG = OUTPUT_BY_LANG
    generic_builder.OUTPUT_COMBINED = OUTPUT_COMBINED
    generic_builder.ZIP_BY_LANG = ZIP_BY_LANG
    generic_builder.ZIP_COMBINED = ZIP_COMBINED
    generic_builder.RETAINED_MAP = TAG_MAP
    generic_builder.REGION_LABELS = {label: label for label in FINAL_LABELS}


def main() -> None:
    build_assignment_map()
    configure_raw_builder()
    coarse_to_label, exact_to_label, coarse_to_region, exact_to_region = raw_builder.load_vector_maps()
    original_label_map, lookup_label_map = raw_builder.build_original_label_maps(
        coarse_to_label,
        exact_to_label,
        coarse_to_region,
        exact_to_region,
    )

    generic_builder.guarded_remove_tree(OUTPUT_BY_LANG)
    generic_builder.guarded_remove_tree(OUTPUT_COMBINED)
    OUTPUT_BY_LANG.mkdir(parents=True, exist_ok=True)

    lang_reports = raw_builder.build_by_language(lookup_label_map)
    langs = sorted(lang_reports)
    generic_builder.build_combined_files(langs)
    generic_builder.write_root_reports(langs, lang_reports, coarse_to_label, original_label_map)
    shutil.copy2(TAG_MAP, OUTPUT_BY_LANG / TAG_MAP.name)
    shutil.copy2(SUMMARY, OUTPUT_BY_LANG / SUMMARY.name)
    shutil.copy2(ASSIGNMENT_MAP, OUTPUT_BY_LANG / ASSIGNMENT_MAP.name)
    shutil.copy2(TAG_MAP, OUTPUT_COMBINED / TAG_MAP.name)
    shutil.copy2(SUMMARY, OUTPUT_COMBINED / SUMMARY.name)
    shutil.copy2(ASSIGNMENT_MAP, OUTPUT_COMBINED / ASSIGNMENT_MAP.name)

    health_by_lang = generic_builder.validate_tree(OUTPUT_BY_LANG, by_language=True)
    health_combined = generic_builder.validate_tree(OUTPUT_COMBINED, by_language=False)
    zip_by_lang = generic_builder.make_zip(OUTPUT_BY_LANG, ZIP_BY_LANG)
    zip_combined = generic_builder.make_zip(OUTPUT_COMBINED, ZIP_COMBINED)

    summary = {
        "by_language": str(OUTPUT_BY_LANG),
        "combined": str(OUTPUT_COMBINED),
        "health_by_language": health_by_lang,
        "health_combined": health_combined,
        "zip_by_language": zip_by_lang,
        "zip_combined": zip_combined,
    }
    (OUTPUT_BY_LANG / "build_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    (OUTPUT_COMBINED / "build_summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
