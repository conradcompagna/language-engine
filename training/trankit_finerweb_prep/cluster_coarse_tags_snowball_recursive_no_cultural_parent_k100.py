from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

import numpy as np

import cluster_coarse_tags_snowball_recursive as rec
import cluster_full_coarse_tags_weighted_child_seeded_k25 as child


BASE_DIR = Path(__file__).resolve().parent
OUT_DIR = BASE_DIR / "derived_fasttext_categories"

SUMMARY_OUT = OUT_DIR / "coarse_snowball_recursive_split_cultural_reference_k100_summary.tsv"
TAG_MAP_OUT = OUT_DIR / "coarse_snowball_recursive_split_cultural_reference_k100_tag_map.tsv"
REPORT_OUT = OUT_DIR / "coarse_snowball_recursive_split_cultural_reference_k100_report.md"


def cultural_reference_orphan_rows() -> tuple[int, list[dict[str, object]]]:
    standalone_count = 0
    grouped: defaultdict[str, dict[str, object]] = defaultdict(lambda: {"count": 0, "source_labels": []})
    with child.IN_FINE.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            original = row["original_label"].strip()
            count = int(row["count"])
            if original == "cultural reference":
                standalone_count += count
                continue
            coarse, fine = child.split_original_label(original)
            if coarse != "cultural reference" or original == fine:
                continue
            grouped[fine]["count"] += count
            grouped[fine]["source_labels"].append(original)

    rows = []
    for fine, data in grouped.items():
        rows.append(
            {
                "coarse_tag": fine,
                "coarse_tag_english": fine,
                "count": int(data["count"]),
                "tokens": child.text_tokens(fine),
                "children": [],
                "source_kind": "cultural_child_orphan",
                "source_labels": "; ".join(sorted(set(data["source_labels"]))[:25]),
            }
        )
    return standalone_count, rows


def load_rows_no_cultural_parent() -> tuple[list[dict[str, object]], list[dict[str, object]], int, int]:
    fine_children = child.load_fine_children()
    base_rows, full_total = child.load_rows(fine_children)
    standalone_count, cultural_orphans = cultural_reference_orphan_rows()

    rows = []
    for row in base_rows:
        if row["coarse_tag"] == "cultural reference":
            continue
        row["source_kind"] = "coarse"
        row["source_labels"] = str(row["coarse_tag"])
        rows.append(row)
    if standalone_count:
        rows.append(
            {
                "coarse_tag": "cultural reference",
                "coarse_tag_english": "cultural reference",
                "count": standalone_count,
                "tokens": child.text_tokens("cultural reference"),
                "children": [],
                "source_kind": "cultural_parent_standalone",
                "source_labels": "cultural reference",
            }
        )
    rows.extend(cultural_orphans)

    needed = child.collect_needed_words(rows)
    vectors = child.ft.load_fasttext(needed)

    vectorized = []
    unvectorized = []
    for row in rows:
        if row.get("source_kind") == "cultural_child_orphan":
            vec, matched = child.vector_from_tokens(row["tokens"], vectors)
            row["matched_tokens"] = ", ".join(matched)
            row["child_vector_count"] = 0
            row["child_vector_mentions"] = 0
            row["child_matched_tokens"] = ""
        else:
            vec = child.enriched_row_vector(row, vectors)
        row["percent"] = int(row["count"]) / full_total * 100.0
        if vec is None:
            unvectorized.append(row)
            continue
        row["vector"] = rec.normalize(vec.astype(np.float32))
        vectorized.append(row)

    vectorized.sort(key=lambda item: (-int(item["count"]), str(item["coarse_tag"])))
    unvectorized.sort(key=lambda item: (-int(item["count"]), str(item["coarse_tag"])))
    return vectorized, unvectorized, full_total, standalone_count


def main() -> None:
    rec.TARGET_CLUSTERS = 100
    rec.SUMMARY_OUT = SUMMARY_OUT
    rec.TAG_MAP_OUT = TAG_MAP_OUT
    rec.REPORT_OUT = REPORT_OUT

    rows, unvectorized, total_count, standalone_count = load_rows_no_cultural_parent()
    top71 = rec.load_top71_seed_tags()

    results = [
        rec.run_recursive("v1_pairwise_recursive_no_cultural_parent_k100", "pairwise", rows, total_count),
        rec.run_recursive("v2_centroid_recursive_no_cultural_parent_k100", "centroid", rows, total_count),
        rec.run_recursive("v3_pairwise_top71_seeded_recursive_no_cultural_parent_k100", "pairwise", rows, total_count, top71),
        rec.run_recursive("v4_centroid_top71_seeded_recursive_no_cultural_parent_k100", "centroid", rows, total_count, top71),
    ]
    rec.write_outputs(rows, unvectorized, total_count, results)

    print(f"total={total_count}")
    print(f"vectorized={len(rows)}")
    print(f"unvectorized={len(unvectorized)}")
    print(f"standalone_cultural_reference_mentions={standalone_count}")
    for version, items, log in results:
        top25_pct = sum(item.count for item in sorted(items, key=lambda item: -item.count)[:25]) / total_count * 100.0
        largest_pct = max(item.count for item in items) / total_count * 100.0
        print(
            f"{version}: passes={log[-1]['pass']} clusters={len(items)} "
            f"top25_pct={top25_pct:.4f} largest={largest_pct:.4f}"
        )
    print(f"summary={SUMMARY_OUT}")
    print(f"tag_map={TAG_MAP_OUT}")
    print(f"report={REPORT_OUT}")


if __name__ == "__main__":
    main()
