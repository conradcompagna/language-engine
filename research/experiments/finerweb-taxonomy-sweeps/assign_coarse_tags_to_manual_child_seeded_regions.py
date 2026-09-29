from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

import cluster_full_coarse_tags_weighted_child_seeded_k25 as child


BASE_DIR = Path(__file__).resolve().parent
OUT_DIR = BASE_DIR / "derived_fasttext_categories"
SUMMARY_OUT = OUT_DIR / "finerweb_manual_child_seeded_region_summary.tsv"
TAG_MAP_OUT = OUT_DIR / "finerweb_manual_child_seeded_region_tag_map.tsv"
REPORT_OUT = OUT_DIR / "finerweb_manual_child_seeded_region_report.md"


MANUAL_REGIONS = {
    "person": ["person", "religious figure", "character"],
    "location": ["location", "country", "city", "region", "infrastructure", "continent", "building", "province"],
    "organization": [
        "organization",
        "political party",
        "government organization",
        "political organization",
        "educational institution",
        "sports team",
        "news agency",
        "government agency",
        "political entity",
        "company",
        "state",
        "government",
    ],
    "time": ["time", "date", "time period", "year", "duration", "day of the week", "month"],
    "cultural reference": ["cultural reference"],
    "quantity": ["quantity", "measurement", "percentage", "age", "statistic", "monetary value", "score", "number"],
    "event": ["event"],
    "product": ["product", "technology", "brand", "financial product"],
    "concept": [
        "concept",
        "scientific concept",
        "legal concept",
        "economic concept",
        "cultural concept",
        "financial concept",
        "philosophical concept",
        "political concept",
    ],
    "media": ["media", "social media platform", "website", "platform"],
    "title": [
        "title",
        "profession",
        "position",
        "occupation",
        "job title",
        "political position",
        "award",
        "role",
        "government position",
    ],
    "deity": ["deity"],
    "currency": ["currency", "cryptocurrency", "financial instrument"],
    "language": ["language"],
    "group": ["group", "nationality", "ethnic group", "demographic group", "social group"],
    "work of art": ["work of art", "film", "literary work", "video game"],
    "document": ["document", "legal document"],
    "program": ["program", "service", "activity", "field of study", "industry", "sport", "game"],
    "medical condition": ["medical condition", "disease", "body part", "animal"],
    "material": ["material", "food"],
}


def normalize_vector(vec: np.ndarray) -> np.ndarray | None:
    norm = np.linalg.norm(vec)
    if not norm:
        return None
    return (vec / norm).astype(np.float32)


def top_unigrams(rows: list[dict[str, object]], limit: int = 10) -> str:
    parent_mentions: Counter[str] = Counter()
    child_mentions: Counter[str] = Counter()
    tag_counts: Counter[str] = Counter()
    for row in rows:
        for token in row["tokens"]:
            parent_mentions[token] += int(row["count"])
            tag_counts[token] += 1
        for fine_child in row["children"]:
            for token in fine_child["tokens"]:
                child_mentions[token] += int(fine_child["count"])
    ranked = sorted(
        set(parent_mentions) | set(child_mentions),
        key=lambda tok: (parent_mentions[tok] + child_mentions[tok], tag_counts[tok], tok),
        reverse=True,
    )
    return "; ".join(
        f"{tok} ({parent_mentions[tok]} parent mentions, {child_mentions[tok]} child mentions, {tag_counts[tok]} tags)"
        for tok in ranked[:limit]
    )


def build_region_vectors(rows_by_tag: dict[str, dict[str, object]]) -> tuple[dict[str, np.ndarray], dict[str, list[str]]]:
    region_vectors: dict[str, np.ndarray] = {}
    missing_or_unvectorized: dict[str, list[str]] = {}

    for region, seed_tags in MANUAL_REGIONS.items():
        vectors = []
        weights = []
        missing = []
        for seed in seed_tags:
            row = rows_by_tag.get(seed)
            if row is None or row.get("vector") is None:
                missing.append(seed)
                continue
            vectors.append(row["vector"])
            weights.append(float(row["count"]))
        if not vectors:
            raise RuntimeError(f"No vectorized seeds for region {region!r}")
        region_vec = np.average(np.stack(vectors).astype(np.float32), axis=0, weights=np.array(weights, dtype=np.float64))
        normalized = normalize_vector(region_vec)
        if normalized is None:
            raise RuntimeError(f"Zero region vector for {region!r}")
        region_vectors[region] = normalized
        if missing:
            missing_or_unvectorized[region] = missing
    return region_vectors, missing_or_unvectorized


def build_seed_lookup() -> dict[str, str]:
    lookup = {}
    for region, seeds in MANUAL_REGIONS.items():
        for seed in seeds:
            lookup[seed] = region
    return lookup


def assign_rows(
    rows: list[dict[str, object]],
    region_vectors: dict[str, np.ndarray],
) -> None:
    seed_lookup = build_seed_lookup()
    regions = list(MANUAL_REGIONS)
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

        seed_region = seed_lookup.get(str(row["coarse_tag"]))
        if seed_region:
            assigned_region = seed_region
            assigned_similarity = float(np.dot(region_vectors[seed_region], vec))
            row["assignment_source"] = "manual_seed"
        else:
            assigned_region = best_region
            assigned_similarity = best_similarity
            row["assignment_source"] = "nearest_region"

        row["assigned_region"] = assigned_region
        row["similarity"] = assigned_similarity
        row["runner_up_region"] = runner_region
        row["runner_up_similarity"] = runner_similarity
        row["margin"] = assigned_similarity - runner_similarity


def write_outputs(
    rows: list[dict[str, object]],
    total_count: int,
    missing_or_unvectorized: dict[str, list[str]],
) -> None:
    by_region: defaultdict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        by_region[str(row["assigned_region"])].append(row)

    summaries = []
    for region in MANUAL_REGIONS:
        region_rows = by_region.get(region, [])
        region_rows.sort(key=lambda row: (-int(row["count"]), str(row["coarse_tag"])))
        sims = [float(row["similarity"]) for row in region_rows if row["similarity"] != ""]
        weights = [float(row["percent"]) for row in region_rows if row["similarity"] != ""]
        mention_count = sum(int(row["count"]) for row in region_rows)
        summaries.append(
            {
                "region": region,
                "rows": region_rows,
                "tag_count": len(region_rows),
                "mention_count": mention_count,
                "percent": mention_count / total_count * 100.0,
                "weighted_mean_similarity": float(np.average(sims, weights=weights)) if sims else 0.0,
                "mean_similarity": float(np.mean(sims)) if sims else 0.0,
                "p10_similarity": float(np.percentile(sims, 10)) if sims else 0.0,
                "min_similarity": float(np.min(sims)) if sims else 0.0,
                "top_unigrams": top_unigrams(region_rows),
            }
        )
    summaries.sort(key=lambda item: (-item["percent"], item["region"]))

    with SUMMARY_OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
                "region",
                "seed_tags",
                "assigned_tag_count",
                "mention_count",
                "percent_of_total",
                "weighted_mean_similarity_pct",
                "p10_similarity_pct",
                "min_similarity_pct",
                "top_unigrams_from_parent_and_children",
                "top_assigned_tags",
            ]
        )
        for summary in summaries:
            top_tags = "; ".join(
                f"{row['coarse_tag']} ({row['percent']:.4f}%, sim={float(row['similarity']) * 100:.2f}%, {row['assignment_source']})"
                for row in summary["rows"][:60]
                if row["similarity"] != ""
            )
            writer.writerow(
                [
                    summary["region"],
                    "; ".join(MANUAL_REGIONS[summary["region"]]),
                    summary["tag_count"],
                    summary["mention_count"],
                    f"{summary['percent']:.6f}",
                    f"{summary['weighted_mean_similarity'] * 100:.2f}",
                    f"{summary['p10_similarity'] * 100:.2f}",
                    f"{summary['min_similarity'] * 100:.2f}",
                    summary["top_unigrams"],
                    top_tags,
                ]
            )

    with TAG_MAP_OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
                "coarse_tag",
                "coarse_tag_english",
                "count",
                "percent_of_total",
                "assigned_region",
                "assignment_source",
                "similarity_to_region_pct",
                "runner_up_region",
                "runner_up_similarity_pct",
                "margin_pct",
                "child_vector_count",
                "child_vector_mentions",
            ]
        )
        for row in sorted(rows, key=lambda item: (-int(item["count"]), str(item["coarse_tag"]))):
            if row["similarity"] == "":
                writer.writerow(
                    [
                        row["coarse_tag"],
                        row["coarse_tag_english"],
                        row["count"],
                        f"{row['percent']:.6f}",
                        row["assigned_region"],
                        row["assignment_source"],
                        "",
                        "",
                        "",
                        "",
                        row.get("child_vector_count", 0),
                        row.get("child_vector_mentions", 0),
                    ]
                )
                continue
            writer.writerow(
                [
                    row["coarse_tag"],
                    row["coarse_tag_english"],
                    row["count"],
                    f"{row['percent']:.6f}",
                    row["assigned_region"],
                    row["assignment_source"],
                    f"{float(row['similarity']) * 100:.2f}",
                    row["runner_up_region"],
                    f"{float(row['runner_up_similarity']) * 100:.2f}",
                    f"{float(row['margin']) * 100:.2f}",
                    row.get("child_vector_count", 0),
                    row.get("child_vector_mentions", 0),
                ]
            )

    with REPORT_OUT.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("# Manual Region Assignment With Child-Seeded Coarse Vectors\n\n")
        handle.write(
            "Manual seed regions are used as anchors. Each coarse tag vector is the child-seeded vector: "
            "50% parent coarse-label vector plus 50% frequency-weighted fine-child centroid. "
            "Each manual region vector is the count-weighted centroid of its seed coarse-tag vectors. "
            "All non-seed coarse tags are assigned to the nearest manual region by cosine similarity.\n\n"
        )
        handle.write(f"- Total coarse tags: {len(rows)}\n")
        handle.write(f"- Total mentions: {total_count}\n")
        handle.write(f"- Manual regions: {len(MANUAL_REGIONS)}\n")
        handle.write(f"- Unvectorized tags: {len(by_region.get('UNVECTORIZED', []))}\n")
        if missing_or_unvectorized:
            handle.write("- Missing/unvectorized manual seeds: ")
            handle.write("; ".join(f"{region}: {', '.join(tags)}" for region, tags in missing_or_unvectorized.items()))
            handle.write("\n")
        handle.write("\n## Region Summaries\n\n")
        for summary in summaries:
            handle.write(f"### {summary['region']}\n\n")
            handle.write(f"Seeds: {', '.join(f'`{tag}`' for tag in MANUAL_REGIONS[summary['region']])}\n\n")
            handle.write(
                f"Assigned tags: {summary['tag_count']}; coverage: {summary['percent']:.4f}% "
                f"({summary['mention_count']} mentions)\n\n"
            )
            handle.write(
                f"Similarity to region: weighted mean {summary['weighted_mean_similarity'] * 100:.2f}%, "
                f"p10 {summary['p10_similarity'] * 100:.2f}%, min {summary['min_similarity'] * 100:.2f}%\n\n"
            )
            handle.write(f"Top unigram evidence from assigned parent+children: {summary['top_unigrams']}\n\n")
            handle.write("Top assigned coarse tags:\n")
            for row in summary["rows"][:45]:
                if row["similarity"] == "":
                    continue
                handle.write(
                    f"- `{row['coarse_tag']}`: {row['percent']:.4f}%, "
                    f"sim={float(row['similarity']) * 100:.2f}%, {row['assignment_source']}\n"
                )
            handle.write("\n")


def main() -> None:
    fine_children = child.load_fine_children()
    rows, total_count = child.load_rows(fine_children)
    vectors = child.ft.load_fasttext(child.collect_needed_words(rows))

    for row in rows:
        vec = child.enriched_row_vector(row, vectors)
        row["vector"] = vec

    rows_by_tag = {str(row["coarse_tag"]): row for row in rows}
    region_vectors, missing_or_unvectorized = build_region_vectors(rows_by_tag)
    assign_rows(rows, region_vectors)
    write_outputs(rows, total_count, missing_or_unvectorized)

    assigned = Counter(str(row["assigned_region"]) for row in rows)
    print(f"total={total_count}")
    print(f"tags={len(rows)}")
    print(f"regions={len(MANUAL_REGIONS)}")
    print(f"unvectorized={assigned.get('UNVECTORIZED', 0)}")
    print(f"wrote={SUMMARY_OUT}")
    print(f"tag_map={TAG_MAP_OUT}")
    print(f"report={REPORT_OUT}")
    for region, count in assigned.most_common():
        print(f"{region}\t{count}")


if __name__ == "__main__":
    main()
