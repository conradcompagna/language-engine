from __future__ import annotations

import csv
from collections import Counter, defaultdict

import assign_coarse_tags_to_manual_full_label_child_regions as base
import compute_latest_seed_coverage_v5 as latest


OUT_DIR = base.OUT_DIR
THRESHOLD = 0.60

SUMMARY_OUT = OUT_DIR / "finerweb_selected_manual_seed_regions_threshold60_concept_title_split_cultural_summary.tsv"
TAG_MAP_OUT = OUT_DIR / "finerweb_selected_manual_seed_regions_threshold60_concept_title_split_cultural_retained_tag_map.tsv"
REPORT_OUT = OUT_DIR / "finerweb_selected_manual_seed_regions_threshold60_concept_title_split_cultural_report.md"
ASSIGNMENT_OUT = OUT_DIR / "finerweb_selected_manual_seed_regions_threshold60_concept_title_split_cultural_all_assignments.tsv"


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
    "concept": "concept",
    "title": "title",
}

SELECTED_REGIONS = {
    region: latest.SEEDS[source]
    for region, source in REGION_SOURCES.items()
}


def norm_label(text: str) -> str:
    return " ".join((text or "").strip().lower().split())


def build_candidate_rows(label_sets: dict[str, list[dict[str, object]]]) -> tuple[list[dict[str, object]], int, int]:
    coarse_rows, total_count = base.load_rows(label_sets)
    rows: list[dict[str, object]] = []

    for row in coarse_rows:
        row = dict(row)
        row["map_level"] = "coarse"
        row["original_label"] = ""
        rows.append(row)

    rows.sort(key=lambda row: (-int(row["count"]), str(row["map_level"]), str(row["coarse_tag"]), str(row["original_label"])))
    return rows, total_count, 0


def retained_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    retained = []
    threshold_source = f"similarity_ge{int(THRESHOLD * 100)}"
    for row in rows:
        similarity = row["similarity"]
        passes_threshold = similarity != "" and float(similarity) >= THRESHOLD
        if not passes_threshold:
            continue
        is_seed = row["assignment_source"] in {"manual_seed", "manual_seed_no_vector"}
        row["retention_source"] = "manual_seed" if is_seed else threshold_source
        retained.append(row)
    return retained


def write_all_assignments(rows: list[dict[str, object]]) -> None:
    with ASSIGNMENT_OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
                "map_level",
                "coarse_tag",
                "original_label",
                "vector_text",
                "count",
                "percent_of_total",
                "assigned_region",
                "assignment_source",
                "similarity_to_region_pct",
                "runner_up_region",
                "runner_up_similarity_pct",
                "matched_words",
            ]
        )
        for row in rows:
            writer.writerow(
                [
                    row["map_level"],
                    row["coarse_tag"],
                    row["original_label"],
                    row.get("vector_text", ""),
                    row["count"],
                    f"{row['percent']:.6f}",
                    row["assigned_region"],
                    row["assignment_source"],
                    "" if row["similarity"] == "" else f"{float(row['similarity']) * 100:.2f}",
                    row["runner_up_region"],
                    "" if row["runner_up_similarity"] == "" else f"{float(row['runner_up_similarity']) * 100:.2f}",
                    row["matched_words"],
                ]
            )


def write_outputs(rows: list[dict[str, object]], retained: list[dict[str, object]], total_count: int, disallowed_parent_mentions: int) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    threshold_pct = int(THRESHOLD * 100)
    threshold_label = f">={threshold_pct}%"
    threshold_source = f"similarity_ge{threshold_pct}"

    by_region: defaultdict[str, list[dict[str, object]]] = defaultdict(list)
    for row in retained:
        by_region[str(row["assigned_region"])].append(row)

    seed_lookup = base.seed_lookup()
    seed_rows = [row for row in rows if str(row["coarse_tag"]) in seed_lookup]
    retained_seed_rows = [row for row in retained if row["retention_source"] == "manual_seed"]
    similarity_rows = [row for row in retained if row["retention_source"] == threshold_source]

    with SUMMARY_OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
                "region",
                "seed_tag_count",
                "retained_seed_unit_count",
                "added_threshold_unit_count",
                "retained_unit_count",
                "retained_mentions",
                "retained_pct_of_total_mentions",
                "top_added_threshold_units",
            ]
        )
        for region in SELECTED_REGIONS:
            region_rows = sorted(by_region.get(region, []), key=lambda row: (-int(row["count"]), str(row["coarse_tag"]), str(row["original_label"])))
            added = [row for row in region_rows if row["retention_source"] == threshold_source]
            mention_count = sum(int(row["count"]) for row in region_rows)
            top_added = "; ".join(
                f"{row['original_label'] or row['coarse_tag']} ({row['count']}, sim={float(row['similarity']) * 100:.2f}%)"
                for row in added[:15]
            )
            writer.writerow(
                [
                    region,
                    len(SELECTED_REGIONS[region]),
                    sum(1 for row in region_rows if row["retention_source"] == "manual_seed"),
                    len(added),
                    len(region_rows),
                    mention_count,
                    f"{mention_count / total_count * 100:.6f}",
                    top_added,
                ]
            )

    with TAG_MAP_OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
                "map_level",
                "coarse_tag",
                "original_label",
                "vector_text",
                "count",
                "percent_of_total",
                "retained_region",
                "retention_source",
                "similarity_to_region_pct",
                "runner_up_region",
                "runner_up_similarity_pct",
            ]
        )
        for row in sorted(retained, key=lambda row: (str(row["assigned_region"]), str(row["map_level"]), -int(row["count"]), str(row["coarse_tag"]), str(row["original_label"]))):
            writer.writerow(
                [
                    row["map_level"],
                    row["coarse_tag"],
                    row["original_label"],
                    row.get("vector_text", ""),
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

    with REPORT_OUT.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(f"# Selected Manual Seed Regions, {threshold_pct}% Similarity, Concept/Title Restored\n\n")
        handle.write("Regions kept: " + ", ".join(SELECTED_REGIONS) + ".\n\n")
        handle.write(
            "Candidate units are coarse tags. Full original labels under each coarse tag provide the vector evidence; "
            "there is no special child-only stripping for cultural-reference labels.\n\n"
        )
        handle.write(f"- Total mentions: {total_count}\n")
        handle.write(f"- Candidate units: {len(rows)}\n")
        handle.write(f"- Retained candidate units: {len(retained)} ({len(retained) / len(rows) * 100:.6f}% of candidate units)\n")
        handle.write(f"- Retained mentions: {retained_mentions} ({retained_mentions / total_count * 100:.6f}% of mentions)\n")
        handle.write(f"- Input manual-seed mentions: {input_seed_mentions} ({input_seed_mentions / total_count * 100:.6f}% of mentions)\n")
        handle.write(f"- Retained manual-seed mentions: {seed_mentions} ({seed_mentions / total_count * 100:.6f}% of mentions)\n")
        handle.write(f"- Retained {threshold_label} non-seed mentions: {similarity_mentions} ({similarity_mentions / total_count * 100:.6f}% of mentions)\n")
        handle.write(f"- Dropped mentions: {dropped_count} ({dropped_count / total_count * 100:.6f}% of mentions)\n\n")

        handle.write("## Region Summary\n\n")
        with SUMMARY_OUT.open("r", encoding="utf-8", newline="") as summary_handle:
            for row in csv.DictReader(summary_handle, delimiter="\t"):
                handle.write(
                    f"- {row['region']}: {row['retained_mentions']} mentions "
                    f"({row['retained_pct_of_total_mentions']}%), {row['retained_unit_count']} retained units, "
                    f"{row['added_threshold_unit_count']} non-seed {threshold_label} additions\n"
                )

        handle.write(f"\n## Top {threshold_label} Non-Seed Additions\n\n")
        for region in SELECTED_REGIONS:
            additions = sorted(
                [row for row in by_region.get(region, []) if row["retention_source"] == threshold_source],
                key=lambda row: (-int(row["count"]), str(row["coarse_tag"]), str(row["original_label"])),
            )
            handle.write(f"### {region}\n\n")
            if not additions:
                handle.write("None.\n\n")
                continue
            for row in additions[:20]:
                label = row["original_label"] or row["coarse_tag"]
                handle.write(f"- `{label}`: {row['count']}, sim {float(row['similarity']) * 100:.2f}%\n")
            handle.write("\n")

    print(f"total_mentions\t{total_count}")
    print(f"candidate_units\t{len(rows)}")
    print(f"retained_units\t{len(retained)}")
    print(f"retained_mentions\t{retained_mentions}")
    print(f"retained_mentions_pct\t{retained_mentions / total_count * 100:.6f}")
    print(f"seed_mentions_pct\t{seed_mentions / total_count * 100:.6f}")
    print(f"{threshold_source}_mentions_pct\t{similarity_mentions / total_count * 100:.6f}")
    print(f"dropped_mentions_pct\t{dropped_count / total_count * 100:.6f}")
    print(f"summary\t{SUMMARY_OUT}")
    print(f"tag_map\t{TAG_MAP_OUT}")
    print(f"report\t{REPORT_OUT}")
    print(f"assignments\t{ASSIGNMENT_OUT}")
    print("retained_by_region")
    for region, count in Counter(str(row["assigned_region"]) for row in retained).most_common():
        print(f"{region}\t{count}")


def main() -> None:
    base.MANUAL_REGIONS = SELECTED_REGIONS
    label_sets = base.load_label_sets()
    rows, total_count, disallowed_parent_mentions = build_candidate_rows(label_sets)
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
    write_all_assignments(rows)
    write_outputs(rows, retained, total_count, disallowed_parent_mentions)


if __name__ == "__main__":
    main()
