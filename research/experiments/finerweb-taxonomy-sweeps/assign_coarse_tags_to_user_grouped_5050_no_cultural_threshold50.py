from __future__ import annotations

from collections import Counter
from pathlib import Path

import numpy as np

import assign_coarse_tags_to_user_grouped_5050_no_cultural_bucket as base


OUT_DIR = Path(__file__).resolve().parent / "derived_fasttext_categories"
THRESHOLD = 0.50

base.SUMMARY_OUT = OUT_DIR / "user_grouped_5050_no_cultural_threshold50_summary.tsv"
base.TAG_MAP_OUT = OUT_DIR / "user_grouped_5050_no_cultural_threshold50_tag_map.tsv"
base.TOP10_OUT = OUT_DIR / "user_grouped_5050_no_cultural_threshold50_top10_attracted.tsv"
base.REPORT_OUT = OUT_DIR / "user_grouped_5050_no_cultural_threshold50_top10_attracted.md"


def assign_rows_threshold50(rows: list[dict[str, object]], region_vectors: dict[str, np.ndarray]) -> None:
    seeds = base.seed_lookup()
    regions = [region for region, _seeds in base.USER_GROUPS]
    matrix = np.stack([region_vectors[region] for region in regions]).astype(np.float32)

    for row in rows:
        vec = row.get("vector")
        if vec is None:
            row["assigned_region"] = "UNVECTORIZED"
            row["assignment_source"] = "unvectorized"
            row["similarity"] = ""
            row["runner_up_region"] = ""
            row["runner_up_similarity"] = ""
            row["margin"] = ""
            continue

        sims = matrix @ vec
        order = np.argsort(-sims)
        best_region = regions[int(order[0])]
        best_similarity = float(sims[int(order[0])])
        runner_region = regions[int(order[1])]
        runner_similarity = float(sims[int(order[1])])

        seed_region = seeds.get(str(row["coarse_tag"])) if row.get("seedable") else None
        if seed_region:
            assigned_region = seed_region
            assigned_similarity = float(np.dot(region_vectors[seed_region], vec))
            source = "seed"
        else:
            assigned_region = best_region
            assigned_similarity = best_similarity
            source = "attracted"

        if assigned_similarity < THRESHOLD:
            row["assigned_region"] = "DROPPED_LT50"
            row["assignment_source"] = "below_threshold"
        else:
            row["assigned_region"] = assigned_region
            row["assignment_source"] = source
        row["similarity"] = assigned_similarity
        row["runner_up_region"] = runner_region
        row["runner_up_similarity"] = runner_similarity
        row["margin"] = assigned_similarity - runner_similarity


base.assign_rows = assign_rows_threshold50


if __name__ == "__main__":
    base.main()
    rows = []
    import csv

    with base.TAG_MAP_OUT.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            rows.append(row)
    counts = Counter(row["assigned_region"] for row in rows)
    dropped_mentions = sum(int(row["count"]) for row in rows if row["assigned_region"] == "DROPPED_LT50")
    unvectorized_mentions = sum(int(row["count"]) for row in rows if row["assigned_region"] == "UNVECTORIZED")
    retained_mentions = sum(
        int(row["count"])
        for row in rows
        if row["assigned_region"] not in {"DROPPED_LT50", "UNVECTORIZED"}
    )

    report = base.REPORT_OUT.read_text(encoding="utf-8")
    report = report.replace(
        "# User Grouped 50/50 FastText Pass, No Cultural Reference Bucket",
        "# User Grouped 50/50 FastText Pass, No Cultural Reference Bucket, 50% Similarity Gate",
        1,
    )
    report = report.replace(
        "All non-seed coarse tags are assigned to the nearest seed-region centroid by cosine similarity.",
        "All non-seed rows are assigned to the nearest seed-region centroid only if their best cosine similarity is at least 50%; otherwise they are dropped.",
        1,
    )
    insert_after = f"- Unvectorized candidate rows: {counts.get('UNVECTORIZED', 0)}\n"
    insert_text = (
        insert_after
        + f"- Dropped below 50% similarity: {counts.get('DROPPED_LT50', 0)} rows, {dropped_mentions} mentions\n"
        + f"- Dropped unvectorized mentions: {unvectorized_mentions}\n"
        + f"- Retained assigned mentions: {retained_mentions}\n"
    )
    report = report.replace(insert_after, insert_text, 1)
    base.REPORT_OUT.write_text(report, encoding="utf-8", newline="\n")
