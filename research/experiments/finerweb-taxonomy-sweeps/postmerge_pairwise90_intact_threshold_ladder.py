from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

import analyze_pairwise_member_purity90_intact_collapse_targets as collapse
import cluster_coarse_tags_pairwise_member_purity90_cultural_modes as pairwise
import cluster_coarse_tags_snowball_recursive as rec


BASE_DIR = Path(__file__).resolve().parent
OUT_DIR = BASE_DIR / "derived_fasttext_categories"

SUMMARY_OUT = OUT_DIR / "coarse_pairwise90_intact_postmerge_threshold_ladder_summary.tsv"
TAG_MAP_OUT = OUT_DIR / "coarse_pairwise90_intact_postmerge_threshold_ladder_tag_map.tsv"
LOG_OUT = OUT_DIR / "coarse_pairwise90_intact_postmerge_threshold_ladder_log.tsv"
REPORT_OUT = OUT_DIR / "coarse_pairwise90_intact_postmerge_threshold_ladder.md"

START_THRESHOLD = 89
MIN_THRESHOLD = 0
TARGET_CLUSTERS = 50
CENTROID_TOP_K = 128
ROW_TOP_K = 512
ROW_SCAN_K = 128
MEMBER_TARGETS_PER_CLUSTER = 32


def normalize(vec: np.ndarray) -> np.ndarray:
    return rec.normalize(vec.astype(np.float32))


def merged_pairwise_purity(left: pairwise.PairwiseCluster, right: pairwise.PairwiseCluster) -> float:
    cross_num = float(np.dot(left.weighted_vector_sum, right.weighted_vector_sum))
    cross_den = left.weight_sum * right.weight_sum
    pair_num = left.pair_num + right.pair_num + cross_num
    pair_den = left.pair_den + right.pair_den + cross_den
    return pair_num / pair_den if pair_den else 1.0


def row_assignment(clusters: list[pairwise.PairwiseCluster], row_count: int) -> np.ndarray:
    assignment = np.full(row_count, -1, dtype=np.int32)
    for cluster_idx, cluster in enumerate(clusters):
        for row_idx in cluster.members:
            assignment[row_idx] = cluster_idx
    return assignment


def cluster_centroids(clusters: list[pairwise.PairwiseCluster]) -> np.ndarray:
    return np.stack([normalize(cluster.weighted_vector_sum) for cluster in clusters]).astype(np.float32)


def add_candidate(
    candidates: dict[tuple[int, int], dict[str, object]],
    clusters: list[pairwise.PairwiseCluster],
    rows: list[dict[str, object]],
    left_idx: int,
    right_idx: int,
    centroid_sim: float | None = None,
    bridge_sim: float | None = None,
    bridge_source: int | None = None,
    bridge_target: int | None = None,
) -> None:
    if left_idx == right_idx:
        return
    a, b = sorted((left_idx, right_idx))
    purity = merged_pairwise_purity(clusters[a], clusters[b])
    existing = candidates.get((a, b))
    if existing is None:
        candidates[(a, b)] = {
            "left_idx": a,
            "right_idx": b,
            "purity": purity,
            "centroid_sim": centroid_sim,
            "bridge_sim": bridge_sim,
            "bridge_source": bridge_source,
            "bridge_target": bridge_target,
        }
        return
    if centroid_sim is not None:
        current = existing.get("centroid_sim")
        existing["centroid_sim"] = centroid_sim if current is None else max(float(current), centroid_sim)
    if bridge_sim is not None:
        current = existing.get("bridge_sim")
        if current is None or bridge_sim > float(current):
            existing["bridge_sim"] = bridge_sim
            existing["bridge_source"] = bridge_source
            existing["bridge_target"] = bridge_target


def centroid_candidates(
    candidates: dict[tuple[int, int], dict[str, object]],
    clusters: list[pairwise.PairwiseCluster],
    rows: list[dict[str, object]],
) -> None:
    if len(clusters) <= 1:
        return
    centroids = cluster_centroids(clusters)
    neighbor_idx, neighbor_sim = rec.compute_top_neighbors(centroids, min(CENTROID_TOP_K, len(clusters) - 1))
    for left_idx in range(len(clusters)):
        for right_idx, sim in zip(neighbor_idx[left_idx], neighbor_sim[left_idx]):
            add_candidate(
                candidates,
                clusters,
                rows,
                left_idx,
                int(right_idx),
                centroid_sim=float(sim),
            )


def member_bridge_candidates(
    candidates: dict[tuple[int, int], dict[str, object]],
    clusters: list[pairwise.PairwiseCluster],
    rows: list[dict[str, object]],
    assignment: np.ndarray,
    row_neighbor_idx: np.ndarray,
    row_neighbor_sim: np.ndarray,
) -> None:
    for cluster_idx, cluster in enumerate(clusters):
        local_targets: dict[int, tuple[float, int, int]] = {}
        for source_idx in cluster.members:
            scanned = 0
            for target_idx, sim in zip(row_neighbor_idx[source_idx, :ROW_SCAN_K], row_neighbor_sim[source_idx, :ROW_SCAN_K]):
                target_idx = int(target_idx)
                target_cluster = int(assignment[target_idx])
                if target_cluster < 0 or target_cluster == cluster_idx:
                    continue
                scanned += 1
                current = local_targets.get(target_cluster)
                if current is None or float(sim) > current[0]:
                    local_targets[target_cluster] = (float(sim), source_idx, target_idx)
                if scanned >= 2:
                    break
        for target_cluster, (sim, source_idx, target_idx) in sorted(
            local_targets.items(),
            key=lambda item: item[1][0],
            reverse=True,
        )[:MEMBER_TARGETS_PER_CLUSTER]:
            add_candidate(
                candidates,
                clusters,
                rows,
                cluster_idx,
                target_cluster,
                bridge_sim=sim,
                bridge_source=source_idx,
                bridge_target=target_idx,
            )


def build_candidates(
    clusters: list[pairwise.PairwiseCluster],
    rows: list[dict[str, object]],
    assignment: np.ndarray,
    row_neighbor_idx: np.ndarray,
    row_neighbor_sim: np.ndarray,
) -> list[dict[str, object]]:
    candidates: dict[tuple[int, int], dict[str, object]] = {}
    centroid_candidates(candidates, clusters, rows)
    member_bridge_candidates(candidates, clusters, rows, assignment, row_neighbor_idx, row_neighbor_sim)
    return sorted(
        candidates.values(),
        key=lambda item: (
            -float(item["purity"]),
            -float(item["bridge_sim"] if item.get("bridge_sim") is not None else -1.0),
            -float(item["centroid_sim"] if item.get("centroid_sim") is not None else -1.0),
            -(clusters[int(item["left_idx"])].count + clusters[int(item["right_idx"])].count),
        ),
    )


def threshold_pass(
    clusters: list[pairwise.PairwiseCluster],
    rows: list[dict[str, object]],
    threshold_pct: int,
    row_neighbor_idx: np.ndarray,
    row_neighbor_sim: np.ndarray,
) -> tuple[list[pairwise.PairwiseCluster], dict[str, object]]:
    threshold = threshold_pct / 100.0
    assignment = row_assignment(clusters, len(rows))
    candidates = build_candidates(clusters, rows, assignment, row_neighbor_idx, row_neighbor_sim)
    used: set[int] = set()
    merged_clusters: list[pairwise.PairwiseCluster] = []
    accepted = []

    for candidate in candidates:
        if float(candidate["purity"]) < threshold:
            break
        left_idx = int(candidate["left_idx"])
        right_idx = int(candidate["right_idx"])
        if left_idx in used or right_idx in used:
            continue
        merged, actual_purity = pairwise.merged_cluster(clusters[left_idx], clusters[right_idx], rows)
        if actual_purity < threshold:
            continue
        used.add(left_idx)
        used.add(right_idx)
        merged_clusters.append(merged)
        accepted.append((left_idx, right_idx, candidate, actual_purity))

    next_clusters = [cluster for idx, cluster in enumerate(clusters) if idx not in used]
    next_clusters.extend(merged_clusters)
    next_clusters.sort(key=lambda cluster: (-cluster.count, cluster.anchor))

    top25_pct = sum(cluster.count for cluster in next_clusters[:25]) / TOTAL_COUNT * 100.0
    largest_pct = next_clusters[0].count / TOTAL_COUNT * 100.0 if next_clusters else 0.0
    return next_clusters, {
        "threshold_pct": threshold_pct,
        "start_clusters": len(clusters),
        "end_clusters": len(next_clusters),
        "candidate_count": len(candidates),
        "merged": len(accepted),
        "blocked_by_reuse": sum(
            1
            for candidate in candidates
            if float(candidate["purity"]) >= threshold
            and (int(candidate["left_idx"]) in used or int(candidate["right_idx"]) in used)
        ),
        "top25_pct": top25_pct,
        "largest_pct": largest_pct,
        "worst_accepted_purity": min((purity for *_rest, purity in accepted), default=1.0),
        "best_candidate_purity": max((float(candidate["purity"]) for candidate in candidates), default=0.0),
        "accepted": accepted,
    }


def write_outputs(
    rows: list[dict[str, object]],
    unvectorized: list[dict[str, object]],
    clusters: list[pairwise.PairwiseCluster],
    log: list[dict[str, object]],
) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ranked = sorted(clusters, key=lambda cluster: (-cluster.count, cluster.anchor))
    cluster_rank = {id(cluster): rank for rank, cluster in enumerate(ranked, start=1)}

    with SUMMARY_OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
                "cluster_rank",
                "anchor_tag",
                "member_count",
                "mention_count",
                "pct_total",
                "weighted_pairwise_purity_pct",
                "top_tags",
            ]
        )
        for rank, cluster in enumerate(ranked, start=1):
            top_members = sorted(
                cluster.members,
                key=lambda idx: (-int(rows[idx]["count"]), str(rows[idx]["coarse_tag"]), str(rows[idx].get("source_kind", ""))),
            )[:60]
            writer.writerow(
                [
                    rank,
                    cluster.anchor,
                    len(cluster.members),
                    cluster.count,
                    f"{cluster.count / TOTAL_COUNT * 100.0:.6f}",
                    f"{pairwise.cluster_purity(cluster) * 100.0:.2f}",
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
                "coarse_tag",
                "count",
                "pct_total",
                "source_kind",
                "source_labels",
                "cluster_rank",
                "anchor_tag",
            ]
        )
        for cluster in ranked:
            rank = cluster_rank[id(cluster)]
            for idx in sorted(
                cluster.members,
                key=lambda row_idx: (-int(rows[row_idx]["count"]), str(rows[row_idx]["coarse_tag"]), str(rows[row_idx].get("source_kind", ""))),
            ):
                writer.writerow(
                    [
                        rows[idx]["coarse_tag"],
                        rows[idx]["count"],
                        f"{int(rows[idx]['count']) / TOTAL_COUNT * 100.0:.6f}",
                        rows[idx].get("source_kind", ""),
                        rows[idx].get("source_labels", ""),
                        rank,
                        cluster.anchor,
                    ]
                )
        for row in unvectorized:
            writer.writerow(
                [
                    row["coarse_tag"],
                    row["count"],
                    f"{int(row['count']) / TOTAL_COUNT * 100.0:.6f}",
                    row.get("source_kind", ""),
                    row.get("source_labels", ""),
                    "UNVECTORIZED",
                    "UNVECTORIZED",
                ]
            )

    with LOG_OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
                "threshold_pct",
                "start_clusters",
                "end_clusters",
                "candidate_count",
                "merged",
                "top25_pct",
                "largest_pct",
                "worst_accepted_purity_pct",
                "best_candidate_purity_pct",
            ]
        )
        for row in log:
            writer.writerow(
                [
                    row["threshold_pct"],
                    row["start_clusters"],
                    row["end_clusters"],
                    row["candidate_count"],
                    row["merged"],
                    f"{row['top25_pct']:.6f}",
                    f"{row['largest_pct']:.6f}",
                    f"{row['worst_accepted_purity'] * 100.0:.2f}",
                    f"{row['best_candidate_purity'] * 100.0:.2f}",
                ]
            )

    with REPORT_OUT.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("# Pairwise-90 Intact Cultural Reference Threshold-Ladder Postmerge\n\n")
        handle.write(
            "This starts from the intact-cultural pairwise-90 clusters and does not modify that source result. "
            "Each recursion lowers the required merged internal pairwise purity by one point: 89%, 88%, 87%, and so on. "
            "At each threshold, candidate pairs are generated from centroid-nearest clusters and strongest member-to-member bridges. "
            "Candidate pairs are greedily accepted from highest merged pairwise purity downward if neither cluster has already merged in that recursion.\n\n"
        )
        handle.write(f"- Total mentions: {TOTAL_COUNT}\n")
        handle.write(f"- Final clusters: {len(ranked)}\n")
        handle.write(f"- Top 25 coverage: {sum(cluster.count for cluster in ranked[:25]) / TOTAL_COUNT * 100.0:.4f}%\n")
        handle.write(f"- Largest cluster: `{ranked[0].anchor}` ({ranked[0].count / TOTAL_COUNT * 100.0:.4f}%)\n\n")
        handle.write("## Threshold Log\n\n")
        for row in log:
            handle.write(
                f"- {row['threshold_pct']}%: {row['start_clusters']} -> {row['end_clusters']} clusters; "
                f"merged {row['merged']}; top25 {row['top25_pct']:.4f}%; largest {row['largest_pct']:.4f}%; "
                f"worst accepted {row['worst_accepted_purity'] * 100.0:.2f}%\n"
            )
        handle.write("\n## Final Clusters\n\n")
        for rank, cluster in enumerate(ranked, start=1):
            top_members = sorted(
                cluster.members,
                key=lambda idx: (-int(rows[idx]["count"]), str(rows[idx]["coarse_tag"]), str(rows[idx].get("source_kind", ""))),
            )[:24]
            handle.write(
                f"{rank}. `{cluster.anchor}`: {cluster.count} mentions "
                f"({cluster.count / TOTAL_COUNT * 100.0:.4f}%), {len(cluster.members)} tags, "
                f"pairwise purity {pairwise.cluster_purity(cluster) * 100.0:.2f}%\n"
            )
            handle.write(
                "   - "
                + "; ".join(
                    f"`{rows[idx]['coarse_tag']}` ({rows[idx]['count']}, {rows[idx].get('source_kind', '')})"
                    for idx in top_members
                )
                + "\n"
            )


TOTAL_COUNT = 935998


def main() -> None:
    rows, unvectorized, total_count = pairwise.load_intact_rows()
    if total_count != TOTAL_COUNT:
        raise ValueError(f"Unexpected total count {total_count}")

    cluster_members = collapse.load_intact_cluster_members(rows)
    clusters = [collapse.make_cluster(cluster_members[rank], rows) for rank in sorted(cluster_members)]
    clusters.sort(key=lambda cluster: (-cluster.count, cluster.anchor))

    x = np.stack([row["vector"] for row in rows]).astype(np.float32)
    row_neighbor_idx, row_neighbor_sim = rec.compute_top_neighbors(x, min(ROW_TOP_K, max(1, len(rows) - 1)))

    log: list[dict[str, object]] = []
    for threshold_pct in range(START_THRESHOLD, MIN_THRESHOLD - 1, -1):
        if len(clusters) <= TARGET_CLUSTERS:
            break
        clusters, row = threshold_pass(clusters, rows, threshold_pct, row_neighbor_idx, row_neighbor_sim)
        log.append(row)
        print(
            f"{threshold_pct}%: {row['start_clusters']} -> {row['end_clusters']} "
            f"merged={row['merged']} top25={row['top25_pct']:.4f} largest={row['largest_pct']:.4f}"
        )

    write_outputs(rows, unvectorized, clusters, log)
    print(f"final_clusters={len(clusters)}")
    print(f"summary={SUMMARY_OUT}")
    print(f"tag_map={TAG_MAP_OUT}")
    print(f"log={LOG_OUT}")
    print(f"report={REPORT_OUT}")


if __name__ == "__main__":
    main()
