from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

import cluster_coarse_tags_nearest_cutoff50_split_cultural_reference as nearest
import cluster_coarse_tags_snowball_recursive as rec
import cluster_coarse_tags_snowball_recursive_no_cultural_parent_k100 as split_cultural


BASE_DIR = Path(__file__).resolve().parent
OUT_DIR = BASE_DIR / "derived_fasttext_categories"

SUMMARY_OUT = OUT_DIR / "coarse_nearest_cutoff50_damped_split_cultural_reference_summary.tsv"
TAG_MAP_OUT = OUT_DIR / "coarse_nearest_cutoff50_damped_split_cultural_reference_tag_map.tsv"
REPORT_OUT = OUT_DIR / "coarse_nearest_cutoff50_damped_split_cultural_reference_report.md"

BASE_THRESHOLD = 0.50
DAMPING = 0.50
MAX_PASSES = 64


def required_similarity(item_a: rec.Item, item_b: rec.Item, total_count: int) -> float:
    larger_share = max(item_a.count, item_b.count) / total_count
    return min(0.98, BASE_THRESHOLD + DAMPING * np.sqrt(larger_share))


def cluster_once_pairwise_damped(
    items: list[rec.Item],
    rows: list[dict[str, object]],
    total_count: int,
    seed_item_indices: set[int] | None = None,
) -> tuple[list[rec.Item], int]:
    _x, neighbor_idx, neighbor_sim = nearest.top_neighbors(items)
    assignment = np.full(len(items), -1, dtype=np.int32)
    clusters: list[list[int]] = []
    merges = 0

    for item_idx in sorted(seed_item_indices or set(), key=lambda idx: -items[idx].count):
        assignment[item_idx] = len(clusters)
        clusters.append([item_idx])

    order = sorted(range(len(items)), key=lambda idx: (-items[idx].count, items[idx].anchor))
    for item_idx in order:
        if assignment[item_idx] != -1:
            continue

        neighbor = int(neighbor_idx[item_idx, 0])
        similarity = float(neighbor_sim[item_idx, 0])
        if similarity < required_similarity(items[item_idx], items[neighbor], total_count):
            assignment[item_idx] = len(clusters)
            clusters.append([item_idx])
            continue

        cluster_id = int(assignment[neighbor])
        if cluster_id != -1:
            assignment[item_idx] = cluster_id
            clusters[cluster_id].append(item_idx)
            merges += 1
        else:
            assignment[item_idx] = len(clusters)
            assignment[neighbor] = len(clusters)
            clusters.append([item_idx, neighbor])
            merges += 1

    return [rec.make_item(cluster, items, rows) for cluster in clusters], merges


def cluster_once_centroid_damped(
    items: list[rec.Item],
    rows: list[dict[str, object]],
    total_count: int,
    seed_item_indices: set[int] | None = None,
) -> tuple[list[rec.Item], int]:
    x, neighbor_idx, neighbor_sim = nearest.top_neighbors(items)
    assignment = np.full(len(items), -1, dtype=np.int32)
    clusters: list[list[int]] = []
    cluster_sums: list[np.ndarray] = []
    centroids: list[np.ndarray] = []
    cluster_counts: list[int] = []
    merges = 0

    def add_cluster(indices: list[int]) -> int:
        cluster_id = len(clusters)
        clusters.append([])
        cluster_sums.append(np.zeros_like(items[0].vector_sum))
        centroids.append(np.zeros_like(items[0].vector))
        cluster_counts.append(0)
        for idx in indices:
            add_item(idx, cluster_id)
        return cluster_id

    def add_item(item_idx: int, cluster_id: int) -> None:
        if assignment[item_idx] != -1:
            return
        assignment[item_idx] = cluster_id
        clusters[cluster_id].append(item_idx)
        cluster_sums[cluster_id] += items[item_idx].vector_sum
        cluster_counts[cluster_id] += items[item_idx].count
        centroids[cluster_id] = rec.normalize(cluster_sums[cluster_id])

    for item_idx in sorted(seed_item_indices or set(), key=lambda idx: -items[idx].count):
        add_cluster([item_idx])

    order = sorted(range(len(items)), key=lambda idx: (-items[idx].count, items[idx].anchor))
    for item_idx in order:
        if assignment[item_idx] != -1:
            continue

        best_cluster = None
        best_cluster_sim = -np.inf
        best_cluster_threshold = np.inf
        if centroids:
            sims = np.stack(centroids).astype(np.float32) @ x[item_idx]
            cluster_order = np.argsort(-sims)
            for cluster_id in cluster_order:
                larger_share = max(items[item_idx].count, cluster_counts[int(cluster_id)]) / total_count
                threshold = min(0.98, BASE_THRESHOLD + DAMPING * np.sqrt(larger_share))
                if float(sims[int(cluster_id)]) >= threshold:
                    best_cluster = int(cluster_id)
                    best_cluster_sim = float(sims[int(cluster_id)])
                    best_cluster_threshold = threshold
                    break
            if best_cluster is None:
                best_cluster = int(cluster_order[0])
                best_cluster_sim = float(sims[best_cluster])
                larger_share = max(items[item_idx].count, cluster_counts[best_cluster]) / total_count
                best_cluster_threshold = min(0.98, BASE_THRESHOLD + DAMPING * np.sqrt(larger_share))

        neighbor, neighbor_score = nearest.first_unassigned_neighbor(item_idx, assignment, neighbor_idx, neighbor_sim, x)
        neighbor_threshold = np.inf
        if neighbor is not None:
            neighbor_threshold = required_similarity(items[item_idx], items[neighbor], total_count)

        cluster_allowed = best_cluster is not None and best_cluster_sim >= best_cluster_threshold
        neighbor_allowed = neighbor is not None and neighbor_score >= neighbor_threshold

        if cluster_allowed and (not neighbor_allowed or best_cluster_sim >= neighbor_score):
            add_item(item_idx, best_cluster)
            merges += 1
        elif neighbor_allowed:
            add_cluster([item_idx, neighbor])
            merges += 1
        else:
            add_cluster([item_idx])

    return [rec.make_item(cluster, items, rows) for cluster in clusters], merges


def run_recursive_damped(
    version: str,
    mode: str,
    rows: list[dict[str, object]],
    total_count: int,
    seed_tags: set[str] | None = None,
) -> tuple[str, list[rec.Item], list[dict[str, object]]]:
    items = rec.initial_items(rows)
    seed_indices = nearest.attach_seed_anchors(items, rows, seed_tags or set()) if seed_tags else None
    log = [{"pass": 0, "clusters": len(items), "top25_pct": 0.0, "merges": ""}]

    for pass_num in range(1, MAX_PASSES + 1):
        previous_count = len(items)
        if mode == "pairwise":
            items, merges = cluster_once_pairwise_damped(
                items,
                rows,
                total_count,
                seed_indices if pass_num == 1 else None,
            )
        elif mode == "centroid":
            items, merges = cluster_once_centroid_damped(
                items,
                rows,
                total_count,
                seed_indices if pass_num == 1 else None,
            )
        else:
            raise ValueError(mode)

        top25_pct = sum(item.count for item in sorted(items, key=lambda item: -item.count)[:25]) / total_count * 100.0
        log.append({"pass": pass_num, "clusters": len(items), "top25_pct": top25_pct, "merges": merges})
        if merges == 0 or len(items) == previous_count:
            break

    return version, items, log


def write_outputs(
    rows: list[dict[str, object]],
    unvectorized: list[dict[str, object]],
    total_count: int,
    results: list[tuple[str, list[rec.Item], list[dict[str, object]]]],
) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    with SUMMARY_OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
                "version",
                "pass",
                "cluster_count",
                "top25_pct",
                "cluster_rank",
                "anchor_tag",
                "seed_anchors",
                "member_count",
                "mention_count",
                "pct_total",
                "weighted_mean_similarity_pct",
                "top_tags",
            ]
        )
        for version, items, log in results:
            ranked = sorted(items, key=lambda item: (-item.count, item.anchor))
            final = log[-1]
            for rank, item in enumerate(ranked, start=1):
                top_members = sorted(
                    item.members,
                    key=lambda idx: (-int(rows[idx]["count"]), str(rows[idx]["coarse_tag"]), str(rows[idx].get("source_kind", ""))),
                )[:40]
                writer.writerow(
                    [
                        version,
                        final["pass"],
                        len(items),
                        f"{final['top25_pct']:.6f}",
                        rank,
                        item.anchor,
                        item.seed_anchor,
                        len(item.members),
                        item.count,
                        f"{item.count / total_count * 100.0:.6f}",
                        f"{rec.item_mean_similarity(item, rows) * 100.0:.2f}",
                        "; ".join(
                            f"{rows[idx]['coarse_tag']} ({rows[idx]['count']}, {rows[idx].get('source_kind', '')})"
                            for idx in top_members
                        ),
                    ]
                )

    with TAG_MAP_OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
                "version",
                "coarse_tag",
                "count",
                "pct_total",
                "source_kind",
                "source_labels",
                "cluster_rank",
                "anchor_tag",
                "seed_anchors",
                "centroid_similarity_pct",
                "damped_required_similarity_pct",
            ]
        )
        for version, items, _log in results:
            ranked = sorted(items, key=lambda item: (-item.count, item.anchor))
            for rank, item in enumerate(ranked, start=1):
                for idx in sorted(
                    item.members,
                    key=lambda row_idx: (-int(rows[row_idx]["count"]), str(rows[row_idx]["coarse_tag"]), str(rows[row_idx].get("source_kind", ""))),
                ):
                    sim = float(np.dot(rows[idx]["vector"], item.vector)) * 100.0
                    threshold = required_similarity(
                        rec.Item(
                            members=[idx],
                            vector_sum=rows[idx]["vector"],
                            vector=rows[idx]["vector"],
                            count=int(rows[idx]["count"]),
                            anchor=str(rows[idx]["coarse_tag"]),
                        ),
                        item,
                        total_count,
                    )
                    writer.writerow(
                        [
                            version,
                            rows[idx]["coarse_tag"],
                            rows[idx]["count"],
                            f"{rows[idx]['percent']:.6f}",
                            rows[idx].get("source_kind", ""),
                            rows[idx].get("source_labels", ""),
                            rank,
                            item.anchor,
                            item.seed_anchor,
                            f"{sim:.2f}",
                            f"{threshold * 100.0:.2f}",
                        ]
                    )
            for row in unvectorized:
                writer.writerow(
                    [
                        version,
                        row["coarse_tag"],
                        row["count"],
                        f"{row['percent']:.6f}",
                        row.get("source_kind", ""),
                        row.get("source_labels", ""),
                        "UNVECTORIZED",
                        "UNVECTORIZED",
                        "",
                        "",
                        "",
                    ]
                )

    with REPORT_OUT.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("# Damped Nearest-Match Cutoff-50 Recursive Clustering\n\n")
        handle.write(
            "Standalone `cultural reference` is included as its own item. "
            "`cultural reference / X` labels are split into standalone orphan `X` items. "
            "At each recursive pass, each item or cluster considers its best match, but large clusters "
            "need a higher similarity to merge.\n\n"
        )
        handle.write("Merge threshold:\n\n")
        handle.write(
            f"`required_similarity = {BASE_THRESHOLD:.2f} + {DAMPING:.2f} * sqrt(larger_cluster_mention_share)`\n\n"
        )
        handle.write(f"- Total mentions: {total_count}\n")
        handle.write(f"- Vectorized items: {len(rows)}\n")
        handle.write(f"- Unvectorized items: {len(unvectorized)}\n\n")

        for version, items, log in results:
            ranked = sorted(items, key=lambda item: (-item.count, item.anchor))
            handle.write(f"## {version}\n\n")
            handle.write("### Pass Log\n\n")
            for entry in log:
                handle.write(
                    f"- pass {entry['pass']}: {entry['clusters']} clusters"
                    + (f", top25 {entry['top25_pct']:.4f}%, merges {entry['merges']}" if entry["pass"] else "")
                    + "\n"
                )
            handle.write("\n### Final Clusters\n\n")
            for rank, item in enumerate(ranked, start=1):
                top_members = sorted(
                    item.members,
                    key=lambda idx: (-int(rows[idx]["count"]), str(rows[idx]["coarse_tag"]), str(rows[idx].get("source_kind", ""))),
                )[:16]
                seed = f", seeds `{item.seed_anchor}`" if item.seed_anchor else ""
                handle.write(
                    f"{rank}. `{item.anchor}`{seed}: {item.count} mentions "
                    f"({item.count / total_count * 100.0:.4f}%), {len(item.members)} tags, "
                    f"mean sim {rec.item_mean_similarity(item, rows) * 100.0:.2f}%\n"
                )
                handle.write(
                    "   - "
                    + "; ".join(
                        f"`{rows[idx]['coarse_tag']}` ({rows[idx]['count']}, {rows[idx].get('source_kind', '')})"
                        for idx in top_members
                    )
                    + "\n"
                )
            handle.write("\n")


def main() -> None:
    rows, unvectorized, total_count, standalone_count = split_cultural.load_rows_no_cultural_parent()
    top71 = rec.load_top71_seed_tags()
    results = [
        run_recursive_damped("v1_pairwise_damped50_split_cultural", "pairwise", rows, total_count),
        run_recursive_damped("v2_centroid_damped50_split_cultural", "centroid", rows, total_count),
        run_recursive_damped("v3_pairwise_top71_seeded_damped50_split_cultural", "pairwise", rows, total_count, top71),
        run_recursive_damped("v4_centroid_top71_seeded_damped50_split_cultural", "centroid", rows, total_count, top71),
    ]
    write_outputs(rows, unvectorized, total_count, results)

    print(f"total={total_count}")
    print(f"vectorized={len(rows)}")
    print(f"unvectorized={len(unvectorized)}")
    print(f"standalone_cultural_reference_mentions={standalone_count}")
    print(f"base_threshold={BASE_THRESHOLD}")
    print(f"damping={DAMPING}")
    for version, items, log in results:
        largest_pct = max(item.count for item in items) / total_count * 100.0
        print(
            f"{version}: passes={log[-1]['pass']} clusters={len(items)} "
            f"top25_pct={log[-1]['top25_pct']:.4f} largest={largest_pct:.4f}"
        )
    print(f"summary={SUMMARY_OUT}")
    print(f"tag_map={TAG_MAP_OUT}")
    print(f"report={REPORT_OUT}")


if __name__ == "__main__":
    main()
