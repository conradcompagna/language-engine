from __future__ import annotations

import csv
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

import cluster_full_coarse_tags_weighted_child_seeded_k25 as child


BASE_DIR = Path(__file__).resolve().parent
OUT_DIR = BASE_DIR / "derived_fasttext_categories"
SUMMARY_OUT = OUT_DIR / "user_grouped_5050_no_cultural_bucket_summary.tsv"
TAG_MAP_OUT = OUT_DIR / "user_grouped_5050_no_cultural_bucket_tag_map.tsv"
TOP10_OUT = OUT_DIR / "user_grouped_5050_no_cultural_bucket_top10_attracted.tsv"
REPORT_OUT = OUT_DIR / "user_grouped_5050_no_cultural_bucket_top10_attracted.md"


USER_GROUPS: list[tuple[str, list[str]]] = [
    ("person | deity | religious figure | character", ["person", "deity", "religious figure", "character"]),
    ("location | country | city | region", ["location", "country", "city", "region"]),
    (
        "organization | media | political/government/sports/web",
        [
            "organization",
            "media",
            "political party",
            "government organization",
            "political organization",
            "website",
            "educational institution",
            "social media platform",
            "sports team",
            "news agency",
            "political entity",
            "government agency",
        ],
    ),
    (
        "date | time period | year | duration",
        ["date", "time period", "year", "time", "duration", "day of the week", "month"],
    ),
    (
        "quantity | measurement | currency | percentage",
        ["quantity", "measurement", "currency", "percentage", "age", "statistic", "monetary value"],
    ),
    ("event", ["event"]),
    ("product | technology | brand | food", ["product", "technology", "brand", "food"]),
    (
        "concept | science | medical/legal/economic",
        [
            "scientific concept",
            "concept",
            "medical condition",
            "disease",
            "legal concept",
            "economic concept",
            "cultural concept",
            "field of study",
            "financial concept",
            "philosophical concept",
        ],
    ),
    ("work of art | film", ["work of art", "film"]),
    (
        "title | profession | position",
        ["title", "profession", "position", "occupation", "job title", "political position"],
    ),
    ("language", ["language"]),
    (
        "nationality | group | ethnic/demographic",
        ["nationality", "group", "ethnic group", "demographic group"],
    ),
    ("legal document | document", ["legal document", "document"]),
    ("industry", ["industry"]),
    ("material", ["material"]),
    ("sport", ["sport"]),
    ("animal", ["animal"]),
    ("program", ["program"]),
    ("award", ["award"]),
]


def normalize_vector(vec: np.ndarray) -> np.ndarray | None:
    norm = np.linalg.norm(vec)
    if not norm:
        return None
    return (vec / norm).astype(np.float32)


def cultural_reference_parts() -> tuple[int, list[dict[str, object]]]:
    standalone_count = 0
    orphan_rows: list[dict[str, object]] = []
    with child.IN_FINE.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            original = row["original_label"].strip()
            if original == "cultural reference":
                standalone_count += int(row["count"])
                continue
            coarse, fine = child.split_original_label(original)
            if coarse != "cultural reference" or original == fine:
                continue
            orphan_rows.append(
                {
                    "row_id": f"cultural reference / {fine}",
                    "display_tag": fine,
                    "source_label": original,
                    "source_kind": "cultural_child_orphan",
                    "coarse_tag": fine,
                    "coarse_tag_english": fine,
                    "count": int(row["count"]),
                    "tokens": child.text_tokens(fine),
                    "children": [],
                    "seedable": False,
                }
            )
    return standalone_count, orphan_rows


def load_rows_with_cultural_orphans() -> tuple[list[dict[str, object]], int]:
    fine_children = child.load_fine_children()
    base_rows, _base_total = child.load_rows(fine_children)
    standalone_count, cultural_orphans = cultural_reference_parts()

    rows: list[dict[str, object]] = []
    for row in base_rows:
        if row["coarse_tag"] == "cultural reference":
            continue
        row["row_id"] = str(row["coarse_tag"])
        row["display_tag"] = str(row["coarse_tag"])
        row["source_label"] = str(row["coarse_tag"])
        row["source_kind"] = "coarse"
        row["seedable"] = True
        rows.append(row)

    if standalone_count:
        rows.append(
            {
                "row_id": "cultural reference",
                "display_tag": "cultural reference",
                "source_label": "cultural reference",
                "source_kind": "cultural_standalone",
                "coarse_tag": "cultural reference",
                "coarse_tag_english": "cultural reference",
                "count": standalone_count,
                "tokens": child.text_tokens("cultural reference"),
                "children": [],
                "seedable": False,
            }
        )
    rows.extend(cultural_orphans)

    total = sum(int(row["count"]) for row in rows)
    for row in rows:
        row["percent"] = int(row["count"]) / total * 100.0
    rows.sort(key=lambda item: (-int(item["count"]), str(item["display_tag"]), str(item["row_id"])))
    return rows, total


def orphan_vector(row: dict[str, object], vectors: dict[str, np.ndarray]) -> np.ndarray | None:
    vec, matched = child.vector_from_tokens(row["tokens"], vectors)
    row["matched_tokens"] = ", ".join(matched)
    row["child_vector_count"] = 0
    row["child_vector_mentions"] = 0
    row["child_matched_tokens"] = ""
    return vec


def seed_lookup() -> dict[str, str]:
    lookup: dict[str, str] = {}
    for region, seeds in USER_GROUPS:
        for seed in seeds:
            lookup[seed] = region
    return lookup


def build_region_vectors(
    rows_by_seed_tag: dict[str, dict[str, object]],
) -> tuple[dict[str, np.ndarray], dict[str, list[str]]]:
    region_vectors: dict[str, np.ndarray] = {}
    missing: dict[str, list[str]] = {}

    for region, seeds in USER_GROUPS:
        vectors = []
        weights = []
        missing_here = []
        for seed in seeds:
            row = rows_by_seed_tag.get(seed)
            if row is None or row.get("vector") is None:
                missing_here.append(seed)
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
        if missing_here:
            missing[region] = missing_here
    return region_vectors, missing


def assign_rows(rows: list[dict[str, object]], region_vectors: dict[str, np.ndarray]) -> None:
    seeds = seed_lookup()
    regions = [region for region, _seeds in USER_GROUPS]
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

        row["assigned_region"] = assigned_region
        row["assignment_source"] = source
        row["similarity"] = assigned_similarity
        row["runner_up_region"] = runner_region
        row["runner_up_similarity"] = runner_similarity
        row["margin"] = assigned_similarity - runner_similarity


def top_attracted_rows(region_rows: list[dict[str, object]], limit: int = 10) -> list[dict[str, object]]:
    attracted = [row for row in region_rows if row.get("assignment_source") == "attracted" and row.get("similarity") != ""]
    return sorted(attracted, key=lambda row: (-int(row["count"]), str(row["display_tag"]), str(row["source_label"])))[:limit]


def write_outputs(rows: list[dict[str, object]], total_count: int, missing: dict[str, list[str]]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    by_region: defaultdict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        by_region[str(row["assigned_region"])].append(row)

    with TAG_MAP_OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
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
                "child_vector_count",
                "child_vector_mentions",
            ]
        )
        for row in sorted(rows, key=lambda item: (-int(item["count"]), str(item["display_tag"]), str(item["source_label"]))):
            if row["similarity"] == "":
                writer.writerow(
                    [
                        row["row_id"],
                        row["display_tag"],
                        row["source_label"],
                        row["source_kind"],
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
                    row["row_id"],
                    row["display_tag"],
                    row["source_label"],
                    row["source_kind"],
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

    with SUMMARY_OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
                "region",
                "seed_tags",
                "assigned_row_count",
                "assigned_mentions",
                "assigned_pct_total",
                "seed_mentions",
                "attracted_row_count",
                "attracted_mentions",
                "attracted_pct_total",
                "weighted_mean_similarity_pct",
            ]
        )
        for region, seeds in USER_GROUPS:
            region_rows = by_region.get(region, [])
            seed_rows = [row for row in region_rows if row.get("assignment_source") == "seed"]
            attracted_rows = [row for row in region_rows if row.get("assignment_source") == "attracted"]
            sims = [float(row["similarity"]) for row in region_rows if row["similarity"] != ""]
            weights = [float(row["count"]) for row in region_rows if row["similarity"] != ""]
            assigned_mentions = sum(int(row["count"]) for row in region_rows)
            seed_mentions = sum(int(row["count"]) for row in seed_rows)
            attracted_mentions = sum(int(row["count"]) for row in attracted_rows)
            writer.writerow(
                [
                    region,
                    "; ".join(seeds),
                    len(region_rows),
                    assigned_mentions,
                    f"{assigned_mentions / total_count * 100:.6f}",
                    seed_mentions,
                    len(attracted_rows),
                    attracted_mentions,
                    f"{attracted_mentions / total_count * 100:.6f}",
                    f"{float(np.average(sims, weights=weights)) * 100:.2f}" if sims else "",
                ]
            )

    with TOP10_OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["region", "rank", "display_tag", "source_kind", "source_label", "count", "pct_total", "similarity_pct"])
        for region, _seeds in USER_GROUPS:
            for rank, row in enumerate(top_attracted_rows(by_region.get(region, [])), start=1):
                writer.writerow(
                    [
                        region,
                        rank,
                        row["display_tag"],
                        row["source_kind"],
                        row["source_label"],
                        row["count"],
                        f"{row['percent']:.6f}",
                        f"{float(row['similarity']) * 100:.2f}",
                    ]
                )

    with REPORT_OUT.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("# User Grouped 50/50 FastText Pass, No Cultural Reference Bucket\n\n")
        handle.write(
            "`cultural reference` is not a seed bucket. The aggregate coarse row was broken apart: "
            "standalone `cultural reference` remains a non-seed candidate, and every "
            "`cultural reference / child` label is an orphan candidate vectorized only as `child`.\n\n"
        )
        handle.write(f"- Total candidate rows assigned: {len(rows)}\n")
        handle.write(f"- Total mentions: {total_count}\n")
        handle.write(f"- Seed regions: {len(USER_GROUPS)}\n")
        handle.write(f"- Seed coarse tags: {len(seed_lookup())}\n")
        handle.write(f"- Unvectorized candidate rows: {len(by_region.get('UNVECTORIZED', []))}\n")
        if missing:
            handle.write("- Missing/unvectorized seeds: ")
            handle.write("; ".join(f"{region}: {', '.join(tags)}" for region, tags in missing.items()))
            handle.write("\n")
        handle.write("\n")

        for region, seeds in USER_GROUPS:
            region_rows = by_region.get(region, [])
            attracted = top_attracted_rows(region_rows)
            assigned_mentions = sum(int(row["count"]) for row in region_rows)
            attracted_mentions = sum(int(row["count"]) for row in region_rows if row.get("assignment_source") == "attracted")
            handle.write(f"## {region}\n\n")
            handle.write(f"Seeds: {', '.join(f'`{seed}`' for seed in seeds)}\n\n")
            handle.write(
                f"Assigned: {len(region_rows)} rows, {assigned_mentions} mentions "
                f"({assigned_mentions / total_count * 100:.4f}% total); "
                f"non-seed attracted mentions {attracted_mentions}.\n\n"
            )
            handle.write("Top 10 attracted rows by frequency:\n\n")
            if not attracted:
                handle.write("- none\n\n")
                continue
            for row in attracted:
                source_note = ""
                if row["source_kind"] != "coarse":
                    source_note = f", source `{row['source_label']}`"
                handle.write(
                    f"- `{row['display_tag']}` ({row['count']}, {row['percent']:.4f}% total), "
                    f"sim {float(row['similarity']) * 100:.2f}%{source_note}\n"
                )
            handle.write("\n")


def main() -> None:
    rows, total_count = load_rows_with_cultural_orphans()
    vectors = child.ft.load_fasttext(child.collect_needed_words(rows))

    vectorized = 0
    child_seeded = 0
    cultural_child_orphans = 0
    for row in rows:
        if row["source_kind"] in {"cultural_child_orphan", "cultural_standalone"}:
            vec = orphan_vector(row, vectors)
            if row["source_kind"] == "cultural_child_orphan":
                cultural_child_orphans += 1
        else:
            vec = child.enriched_row_vector(row, vectors)
            if int(row.get("child_vector_count", 0)):
                child_seeded += 1
        row["vector"] = vec
        if vec is not None:
            vectorized += 1

    rows_by_seed_tag = {str(row["coarse_tag"]): row for row in rows if row.get("seedable")}
    region_vectors, missing = build_region_vectors(rows_by_seed_tag)
    assign_rows(rows, region_vectors)
    write_outputs(rows, total_count, missing)

    assigned = Counter(str(row["assigned_region"]) for row in rows)
    print(f"total={total_count}")
    print(f"rows={len(rows)}")
    print(f"vectorized={vectorized}")
    print(f"child_seeded_coarse_rows={child_seeded}")
    print(f"cultural_child_orphans={cultural_child_orphans}")
    print(f"regions={len(USER_GROUPS)}")
    print(f"unvectorized={assigned.get('UNVECTORIZED', 0)}")
    print(f"wrote={REPORT_OUT}")
    print(f"top10={TOP10_OUT}")
    print(f"summary={SUMMARY_OUT}")
    print(f"tag_map={TAG_MAP_OUT}")


if __name__ == "__main__":
    main()
