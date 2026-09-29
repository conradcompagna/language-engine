from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

import cluster_coarse_tags_snowball_recursive_no_cultural_parent_k100 as split_cultural
import expand_collapse13_seed_taxonomy_coherence_gate as gated


BASE_DIR = Path(__file__).resolve().parent
OUT_DIR = BASE_DIR / "derived_fasttext_categories" / "collapse13_seed_all_tags"

SUMMARY_OUT = OUT_DIR / "collapse13_seed_all_tags_summary.tsv"
TAG_MAP_OUT = OUT_DIR / "collapse13_seed_all_tags_map.tsv"
FINAL_TAGSETS_OUT = OUT_DIR / "collapse13_seed_all_tags_final_tagsets.md"


def assign_all_to_nearest_seed_centroid(
    buckets: dict[str, gated.BucketState],
    rows: list[dict[str, object]],
    seeded_vector_indices: set[int],
) -> None:
    labels = list(buckets)
    seed_centers = np.stack([buckets[label].center for label in labels]).astype(np.float32)
    for idx in sorted(
        set(range(len(rows))) - seeded_vector_indices,
        key=lambda row_idx: (-int(rows[row_idx]["count"]), str(rows[row_idx]["coarse_tag"])),
    ):
        sims = seed_centers @ rows[idx]["vector"]
        label = labels[int(np.argmax(sims))]
        buckets[label].accepted_indices.append(idx)

    for bucket in buckets.values():
        bucket.center = gated.weighted_center(bucket.indices, rows)
        bucket.count = sum(int(rows[idx]["count"]) for idx in bucket.indices)


def write_outputs(
    buckets: dict[str, gated.BucketState],
    rows: list[dict[str, object]],
    unvectorized: list[dict[str, object]],
    seeded_vector_indices: set[int],
    total_count: int,
) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    sorted_buckets = sorted(buckets.values(), key=lambda bucket: (-bucket.count, bucket.label))

    assigned_by_idx = {}
    seed_by_idx = {}
    for label, bucket in buckets.items():
        for idx in bucket.seed_indices:
            seed_by_idx[idx] = label
        for idx in bucket.accepted_indices:
            assigned_by_idx[idx] = label

    with SUMMARY_OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
                "label",
                "seed_tags",
                "assigned_new_tags",
                "seed_frequency_mass",
                "assigned_new_frequency_mass",
                "final_frequency_mass",
                "final_pct_total",
                "base_weighted_coherence_pct",
                "final_weighted_coherence_pct",
                "weighted_coherence_drop_pct",
                "base_unweighted_coherence_pct",
                "final_unweighted_coherence_pct",
                "unweighted_coherence_drop_pct",
            ]
        )
        for bucket in sorted_buckets:
            final_weighted, final_unweighted = gated.bucket_final_metrics(bucket, rows)
            seed_mass = sum(int(rows[idx]["count"]) for idx in bucket.seed_indices)
            assigned_mass = sum(int(rows[idx]["count"]) for idx in bucket.accepted_indices)
            writer.writerow(
                [
                    bucket.label,
                    len(bucket.seed_indices),
                    len(bucket.accepted_indices),
                    seed_mass,
                    assigned_mass,
                    bucket.count,
                    f"{bucket.count / total_count * 100.0:.6f}",
                    f"{bucket.base_weighted * 100.0:.2f}",
                    f"{final_weighted * 100.0:.2f}",
                    f"{(bucket.base_weighted - final_weighted) * 100.0:.2f}",
                    f"{bucket.base_unweighted * 100.0:.2f}",
                    f"{final_unweighted * 100.0:.2f}",
                    f"{(bucket.base_unweighted - final_unweighted) * 100.0:.2f}",
                ]
            )

    with TAG_MAP_OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
                "coarse_tag",
                "source_kind",
                "source_labels",
                "count",
                "pct_total",
                "label",
                "status",
                "similarity_to_label_centroid_pct",
            ]
        )
        for idx, row in sorted(
            enumerate(rows),
            key=lambda item: (-int(item[1]["count"]), str(item[1]["coarse_tag"])),
        ):
            label = seed_by_idx.get(idx) or assigned_by_idx[idx]
            status = "seed" if idx in seed_by_idx else "assigned"
            writer.writerow(
                [
                    row["coarse_tag"],
                    row.get("source_kind", "coarse"),
                    row.get("source_labels", row["coarse_tag"]),
                    row["count"],
                    f"{row['percent']:.6f}",
                    label,
                    status,
                    f"{float(np.dot(row['vector'], buckets[label].center)) * 100.0:.2f}",
                ]
            )
        for row in sorted(unvectorized, key=lambda item: (-int(item["count"]), str(item["coarse_tag"]))):
            writer.writerow(
                [
                    row["coarse_tag"],
                    row.get("source_kind", "coarse"),
                    row.get("source_labels", row["coarse_tag"]),
                    row["count"],
                    f"{row['percent']:.6f}",
                    "",
                    "no_vector",
                    "",
                ]
            )

    with FINAL_TAGSETS_OUT.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("# Collapse-13 All-Tags Assignment\n\n")
        handle.write(
            "Every vectorized non-seed row is assigned to the nearest starting seed centroid. "
            "`cultural reference / child` rows are matched as child text only. Unvectorized rows are listed only in the TSV map as `no_vector`.\n\n"
        )
        for bucket in sorted_buckets:
            final_weighted, final_unweighted = gated.bucket_final_metrics(bucket, rows)
            handle.write(f"## {bucket.label}\n\n")
            handle.write(
                f"{len(bucket.indices)} vectorized tags; {bucket.count} mentions; "
                f"{bucket.count / total_count * 100.0:.6f}% total; "
                f"weighted coherence {final_weighted * 100.0:.2f}% "
                f"(drop {(bucket.base_weighted - final_weighted) * 100.0:.2f}); "
                f"unweighted coherence {final_unweighted * 100.0:.2f}% "
                f"(drop {(bucket.base_unweighted - final_unweighted) * 100.0:.2f}).\n\n"
            )
            for idx in sorted(
                bucket.indices,
                key=lambda row_idx: (-int(rows[row_idx]["count"]), str(rows[row_idx]["coarse_tag"])),
            ):
                status = "seed" if idx in seed_by_idx else "assigned"
                source = rows[idx].get("source_labels", rows[idx]["coarse_tag"])
                if source == rows[idx]["coarse_tag"]:
                    handle.write(f"- {rows[idx]['coarse_tag']} ({rows[idx]['count']}) [{status}]\n")
                else:
                    handle.write(
                        f"- {rows[idx]['coarse_tag']} ({rows[idx]['count']}) [{status}; source: {source}]\n"
                    )
            handle.write("\n")


def main() -> None:
    rows, unvectorized, total_count, standalone_cultural_count = split_cultural.load_rows_no_cultural_parent()
    rows.sort(key=lambda row: (-int(row["count"]), str(row["coarse_tag"])))
    unvectorized.sort(key=lambda row: (-int(row["count"]), str(row["coarse_tag"])))
    seed_labels = gated.parse_seed_labels()
    buckets, seeded_vector_indices, _seeded_no_vector_indices, missing = gated.initialize_buckets(
        seed_labels,
        rows,
        unvectorized,
    )
    if missing:
        raise RuntimeError(f"Missing seed labels: {missing}")

    assign_all_to_nearest_seed_centroid(buckets, rows, seeded_vector_indices)
    write_outputs(buckets, rows, unvectorized, seeded_vector_indices, total_count)

    weighted_drops = []
    unweighted_drops = []
    mass_weighted_drops = []
    total_assigned_mass = 0
    for bucket in buckets.values():
        final_weighted, final_unweighted = gated.bucket_final_metrics(bucket, rows)
        weighted_drop = (bucket.base_weighted - final_weighted) * 100.0
        unweighted_drop = (bucket.base_unweighted - final_unweighted) * 100.0
        weighted_drops.append(weighted_drop)
        unweighted_drops.append(unweighted_drop)
        mass_weighted_drops.append(weighted_drop * bucket.count)
        total_assigned_mass += bucket.count

    print(f"vectorized_tags={len(rows)}")
    print(f"unvectorized_tags={len(unvectorized)}")
    print(f"standalone_cultural_reference_mentions={standalone_cultural_count}")
    print(f"seed_vectorized_tags={len(seeded_vector_indices)}")
    print(f"assigned_new_tags={len(rows) - len(seeded_vector_indices)}")
    print(f"assigned_vectorized_mass={total_assigned_mass}")
    print(f"assigned_vectorized_pct={total_assigned_mass / total_count * 100.0:.6f}")
    print(f"mean_weighted_coherence_drop={float(np.mean(weighted_drops)):.2f}")
    print(f"median_weighted_coherence_drop={float(np.median(weighted_drops)):.2f}")
    print(f"mass_weighted_coherence_drop={sum(mass_weighted_drops) / total_assigned_mass:.2f}")
    print(f"mean_unweighted_coherence_drop={float(np.mean(unweighted_drops)):.2f}")
    print(f"summary={SUMMARY_OUT}")
    print(f"tag_map={TAG_MAP_OUT}")
    print(f"final_tagsets={FINAL_TAGSETS_OUT}")


if __name__ == "__main__":
    main()
