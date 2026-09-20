from __future__ import annotations

import csv
from collections import Counter, defaultdict

import numpy as np

import assign_coarse_tags_to_manual_full_label_child_regions as base
import compute_latest_seed_coverage_v5 as latest


OUT_DIR = base.OUT_DIR
THRESHOLD = 0.90
RETAIN_ALL_SEEDS = True

SUMMARY_OUT = OUT_DIR / "finerweb_selected_manual_seed_regions_threshold90_summary.tsv"
TAG_MAP_OUT = OUT_DIR / "finerweb_selected_manual_seed_regions_threshold90_retained_tag_map.tsv"
REPORT_OUT = OUT_DIR / "finerweb_selected_manual_seed_regions_threshold90_report.md"


REGION_SOURCES = {
    "person": "person",
    "location": "location",
    "organization": "organization",
    "product": "product",
    "money": "currency",
    "time": "time",
    "event": "event",
    "work of art": "work of art",
    "group": "group",
    "language": "language",
    "quantity": "quantity",
}

SELECTED_REGIONS = {
    region: latest.SEEDS[source]
    for region, source in REGION_SOURCES.items()
}


def retained_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    retained = []
    threshold_source = f"similarity_ge{int(THRESHOLD * 100)}"
    for row in rows:
        is_seed = row["assignment_source"] in {"manual_seed", "manual_seed_no_vector"}
        similarity = row["similarity"]
        passes_threshold = similarity != "" and float(similarity) >= THRESHOLD
        retain_seed = is_seed and (RETAIN_ALL_SEEDS or passes_threshold)
        if retain_seed or passes_threshold:
            row["retention_source"] = "manual_seed" if is_seed else threshold_source
            retained.append(row)
    return retained


def write_outputs(rows: list[dict[str, object]], retained: list[dict[str, object]], total_count: int) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    threshold_pct = int(THRESHOLD * 100)
    threshold_label = f">={threshold_pct}%"
    threshold_source = f"similarity_ge{threshold_pct}"
    by_region: defaultdict[str, list[dict[str, object]]] = defaultdict(list)
    for row in retained:
        by_region[str(row["assigned_region"])].append(row)

    seed_lookup = base.seed_lookup()
    retained_tags = {str(row["coarse_tag"]) for row in retained}
    seed_tags = set(seed_lookup)
    seed_rows = [row for row in rows if str(row["coarse_tag"]) in seed_tags]
    retained_seed_rows = [row for row in retained if row["retention_source"] == "manual_seed"]
    similarity_rows = [row for row in retained if row["retention_source"] == threshold_source]

    with SUMMARY_OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
                "region",
                "seed_tag_count",
                "retained_seed_tag_count",
                "added_threshold_tag_count",
                "retained_tag_count",
                "retained_mentions",
                "retained_pct_of_total_mentions",
                "retained_pct_of_all_coarse_tags",
                "top_added_threshold_tags",
            ]
        )
        for region in SELECTED_REGIONS:
            region_rows = sorted(by_region.get(region, []), key=lambda row: (-int(row["count"]), str(row["coarse_tag"])))
            region_seed_tags = set(SELECTED_REGIONS[region])
            retained_seed_count = sum(1 for row in region_rows if str(row["coarse_tag"]) in region_seed_tags)
            added = [row for row in region_rows if row["retention_source"] == threshold_source]
            mention_count = sum(int(row["count"]) for row in region_rows)
            top_added = "; ".join(
                f"{row['coarse_tag']} ({row['count']}, sim={float(row['similarity']) * 100:.2f}%)"
                for row in added[:15]
            )
            writer.writerow(
                [
                    region,
                    len(region_seed_tags),
                    retained_seed_count,
                    len(added),
                    len(region_rows),
                    mention_count,
                    f"{mention_count / total_count * 100:.6f}",
                    f"{len(region_rows) / len(rows) * 100:.6f}",
                    top_added,
                ]
            )

    with TAG_MAP_OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
                "coarse_tag",
                "count",
                "percent_of_total",
                "retained_region",
                "retention_source",
                "similarity_to_region_pct",
                "runner_up_region",
                "runner_up_similarity_pct",
            ]
        )
        for row in sorted(retained, key=lambda row: (str(row["assigned_region"]), -int(row["count"]), str(row["coarse_tag"]))):
            writer.writerow(
                [
                    row["coarse_tag"],
                    row["count"],
                    f"{row['percent']:.6f}",
                    row["assigned_region"],
                    row["retention_source"],
                    "" if row["similarity"] == "" else f"{float(row['similarity']) * 100:.2f}",
                    row["runner_up_region"],
                    "" if row["runner_up_similarity"] == "" else f"{float(row['runner_up_similarity']) * 100:.2f}",
                ]
            )

    retained_mentions = sum(int(row["count"]) for row in retained)
    input_seed_mentions = sum(int(row["count"]) for row in seed_rows)
    seed_mentions = sum(int(row["count"]) for row in retained_seed_rows)
    similarity_mentions = sum(int(row["count"]) for row in similarity_rows)
    dropped_count = total_count - retained_mentions
    dropped_tags = len(rows) - len(retained_tags)

    with REPORT_OUT.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(f"# Selected Manual Seed Regions, {threshold_pct}% Similarity Retention\n\n")
        handle.write("Regions kept: " + ", ".join(SELECTED_REGIONS) + ".\n\n")
        if RETAIN_ALL_SEEDS:
            handle.write(
                "Manual seed tags from the existing curated lists are retained automatically. Every other coarse tag is "
                "assigned to the nearest retained region by whole-original-label FastText centroid. Non-seeds are retained "
                f"only when similarity to that nearest region is at least {threshold_pct}%.\n\n"
            )
        else:
            handle.write(
                "Every coarse tag is assigned to the nearest retained region by whole-original-label FastText centroid. "
                f"Manual seed tags and non-seeds are both retained only when similarity to that region is at least {threshold_pct}%.\n\n"
            )
        handle.write(f"- Total coarse tags: {len(rows)}\n")
        handle.write(f"- Total mentions: {total_count}\n")
        handle.write(f"- Retained coarse tags: {len(retained_tags)} ({len(retained_tags) / len(rows) * 100:.6f}% of coarse tags)\n")
        handle.write(f"- Retained mentions: {retained_mentions} ({retained_mentions / total_count * 100:.6f}% of mentions)\n")
        handle.write(f"- Input manual-seed mentions: {input_seed_mentions} ({input_seed_mentions / total_count * 100:.6f}% of mentions)\n")
        handle.write(f"- Retained manual-seed mentions: {seed_mentions} ({seed_mentions / total_count * 100:.6f}% of mentions)\n")
        handle.write(
            f"- Retained {threshold_label} non-seed mentions: {similarity_mentions} "
            f"({similarity_mentions / total_count * 100:.6f}% of mentions)\n"
        )
        handle.write(f"- Dropped coarse tags: {dropped_tags} ({dropped_tags / len(rows) * 100:.6f}% of coarse tags)\n")
        handle.write(f"- Dropped mentions: {dropped_count} ({dropped_count / total_count * 100:.6f}% of mentions)\n\n")

        handle.write("## Region Summary\n\n")
        with SUMMARY_OUT.open("r", encoding="utf-8", newline="") as summary_handle:
            for row in csv.DictReader(summary_handle, delimiter="\t"):
                handle.write(
                    f"- {row['region']}: {row['retained_mentions']} mentions "
                    f"({row['retained_pct_of_total_mentions']}%), {row['retained_tag_count']} tags, "
                    f"{row['added_threshold_tag_count']} non-seed {threshold_label} additions\n"
                )

        handle.write(f"\n## Top {threshold_label} Non-Seed Additions\n\n")
        for region in SELECTED_REGIONS:
            additions = sorted(
                [
                    row
                    for row in by_region.get(region, [])
                    if row["retention_source"] == threshold_source
                ],
                key=lambda row: (-int(row["count"]), str(row["coarse_tag"])),
            )
            handle.write(f"### {region}\n\n")
            if not additions:
                handle.write("None.\n\n")
                continue
            for row in additions[:20]:
                handle.write(f"- `{row['coarse_tag']}`: {row['count']}, sim {float(row['similarity']) * 100:.2f}%\n")
            handle.write("\n")

    print(f"total_mentions\t{total_count}")
    print(f"total_coarse_tags\t{len(rows)}")
    print(f"retained_tags\t{len(retained_tags)}")
    print(f"retained_tag_pct\t{len(retained_tags) / len(rows) * 100:.6f}")
    print(f"retained_mentions\t{retained_mentions}")
    print(f"retained_mentions_pct\t{retained_mentions / total_count * 100:.6f}")
    print(f"input_seed_mentions\t{input_seed_mentions}")
    print(f"input_seed_mentions_pct\t{input_seed_mentions / total_count * 100:.6f}")
    print(f"seed_mentions\t{seed_mentions}")
    print(f"seed_mentions_pct\t{seed_mentions / total_count * 100:.6f}")
    print(f"{threshold_source}_mentions\t{similarity_mentions}")
    print(f"{threshold_source}_mentions_pct\t{similarity_mentions / total_count * 100:.6f}")
    print(f"dropped_mentions_pct\t{dropped_count / total_count * 100:.6f}")
    print(f"summary\t{SUMMARY_OUT}")
    print(f"tag_map\t{TAG_MAP_OUT}")
    print(f"report\t{REPORT_OUT}")
    print("retained_by_region")
    for region, count in Counter(str(row["assigned_region"]) for row in retained).most_common():
        print(f"{region}\t{count}")


def main() -> None:
    base.MANUAL_REGIONS = SELECTED_REGIONS
    label_sets = base.load_label_sets()
    rows, total_count = base.load_rows(label_sets)
    vectors = base.ft.load_fasttext(base.collect_needed_words(label_sets))

    for row in rows:
        vec, vectorized_count, vectorized_mentions, matched = base.pooled_vector(row["original_labels"], vectors)
        row["vector"] = vec
        row["vectorized_original_label_count"] = vectorized_count
        row["vectorized_original_label_mentions"] = vectorized_mentions
        row["matched_words"] = matched

    region_vectors, _region_evidence, _missing = base.build_region_vectors(label_sets, vectors)
    base.assign_rows(rows, region_vectors)
    retained = retained_rows(rows)
    write_outputs(rows, retained, total_count)


if __name__ == "__main__":
    main()
