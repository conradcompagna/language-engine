from __future__ import annotations

import csv
import math
from pathlib import Path

import numpy as np

import cluster_coarse_tags_pairwise_member_purity90_cultural_modes as pairwise
import cluster_coarse_tags_snowball_recursive as rec


BASE_DIR = Path(__file__).resolve().parent
OUT_DIR = BASE_DIR / "derived_fasttext_categories"

SUMMARY_OUT = OUT_DIR / "coarse_centroid_freqweighted_candidate_weight_gate_intact_summary.tsv"
TAG_MAP_OUT = OUT_DIR / "coarse_centroid_freqweighted_candidate_weight_gate_intact_tag_map.tsv"
LOG_OUT = OUT_DIR / "coarse_centroid_freqweighted_candidate_weight_gate_intact_log.tsv"
REPORT_OUT = OUT_DIR / "coarse_centroid_freqweighted_candidate_weight_gate_intact.md"

TOP_K = 2048
MAX_PASSES = 64


def normalize(vec: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(vec)
    if not norm:
        return vec.astype(np.float32)
    return (vec / norm).astype(np.float32)


def centroid(cluster: pairwise.PairwiseCluster) -> np.ndarray:
    return normalize(cluster.weighted_vector_sum.astype(np.float32))


def candidate_threshold(cluster: pairwise.PairwiseCluster, total_count: int) -> float:
    if len(cluster.members) == 1:
        return -1.0
    pct_total = cluster.count / total_count * 100.0
    return min(0.99, 0.50 + 0.15 * math.log10(1.0 + pct_total * 1000.0))


def weighted_internal_coherence(
    cluster: pairwise.PairwiseCluster,
    rows: list[dict[str, object]],
) -> float:
    center = centroid(cluster)
    weights = np.array([float(rows[idx]["count"]) for idx in cluster.members], dtype=np.float64)
    sims = np.array([float(np.dot(rows[idx]["vector"], center)) for idx in cluster.members], dtype=np.float64)
    if not weights.sum():
        return float(np.mean(sims)) if len(sims) else 1.0
    return float(np.average(sims, weights=weights))


def first_active_old_candidate(
    item_idx: int,
    active: np.ndarray,
    neighbor_idx: np.ndarray,
    neighbor_sim: np.ndarray,
    x: np.ndarray,
) -> tuple[int | None, float]:
    for candidate, similarity in zip(neighbor_idx[item_idx], neighbor_sim[item_idx]):
        candidate = int(candidate)
        if active[candidate]:
            return candidate, float(similarity)

    active_old = np.flatnonzero(active[: x.shape[0]])
    active_old = active_old[active_old != item_idx]
    if not len(active_old):
        return None, -np.inf
    sims = x[active_old] @ x[item_idx]
    best_pos = int(np.argmax(sims))
    return int(active_old[best_pos]), float(sims[best_pos])


def best_created_candidate(
    item_idx: int,
    active: np.ndarray,
    created_indices: list[int],
    centroids: list[np.ndarray],
) -> tuple[int | None, float]:
    candidates = [idx for idx in created_indices if active[idx]]
    if not candidates:
        return None, -np.inf

    matrix = np.stack([centroids[idx] for idx in candidates]).astype(np.float32)
    sims = matrix @ centroids[item_idx]
    best_pos = int(np.argmax(sims))
    return candidates[best_pos], float(sims[best_pos])


def online_pass(
    clusters: list[pairwise.PairwiseCluster],
    rows: list[dict[str, object]],
    total_count: int,
) -> tuple[list[pairwise.PairwiseCluster], dict[str, object]]:
    starting_count = len(clusters)
    if starting_count < 2:
        return clusters, {
            "attempted": 0,
            "merged": 0,
            "blocked": 0,
            "singleton_merges": 0,
            "min_accepted_similarity": 1.0,
            "max_blocked_similarity": -np.inf,
            "max_blocked_candidate_pct": 0.0,
        }

    centroids = [centroid(cluster) for cluster in clusters]
    x = np.stack(centroids[:starting_count]).astype(np.float32)
    neighbor_idx, neighbor_sim = rec.compute_top_neighbors(x, min(TOP_K, max(1, starting_count - 1)))
    active = np.ones(starting_count, dtype=bool)
    created_indices: list[int] = []
    order = sorted(range(starting_count), key=lambda idx: (-clusters[idx].count, clusters[idx].anchor))

    attempted = 0
    merged = 0
    blocked = 0
    singleton_merges = 0
    min_accepted_similarity = 1.0
    max_blocked_similarity = -np.inf
    max_blocked_candidate_pct = 0.0

    for item_idx in order:
        if not active[item_idx]:
            continue

        old_candidate, old_similarity = first_active_old_candidate(
            item_idx,
            active,
            neighbor_idx,
            neighbor_sim,
            x,
        )
        created_candidate, created_similarity = best_created_candidate(
            item_idx,
            active,
            created_indices,
            centroids,
        )

        if created_similarity > old_similarity:
            candidate = created_candidate
            similarity = created_similarity
        else:
            candidate = old_candidate
            similarity = old_similarity
        if candidate is None:
            continue

        attempted += 1
        threshold = candidate_threshold(clusters[item_idx], total_count)
        if similarity < threshold:
            blocked += 1
            max_blocked_similarity = max(max_blocked_similarity, similarity)
            max_blocked_candidate_pct = max(max_blocked_candidate_pct, clusters[item_idx].count / total_count * 100.0)
            continue

        proposed, _pairwise_purity = pairwise.merged_cluster(clusters[item_idx], clusters[candidate], rows)
        active[item_idx] = False
        active[candidate] = False
        clusters.append(proposed)
        active = np.append(active, True)
        centroids.append(centroid(proposed))
        created_indices.append(len(clusters) - 1)
        merged += 1
        if threshold < 0:
            singleton_merges += 1
        min_accepted_similarity = min(min_accepted_similarity, similarity)

    next_clusters = [cluster for idx, cluster in enumerate(clusters) if active[idx]]
    next_clusters.sort(key=lambda cluster: (-cluster.count, cluster.anchor))
    return next_clusters, {
        "attempted": attempted,
        "merged": merged,
        "blocked": blocked,
        "singleton_merges": singleton_merges,
        "min_accepted_similarity": min_accepted_similarity,
        "max_blocked_similarity": max_blocked_similarity,
        "max_blocked_candidate_pct": max_blocked_candidate_pct,
    }


def run_recursive(
    rows: list[dict[str, object]],
    total_count: int,
) -> tuple[list[pairwise.PairwiseCluster], list[dict[str, object]]]:
    clusters = [pairwise.make_singleton(idx, rows) for idx in range(len(rows))]
    log: list[dict[str, object]] = [
        {
            "pass": 0,
            "clusters": len(clusters),
            "top25_pct": 0.0,
            "attempted": "",
            "merged": "",
            "blocked": "",
            "singleton_merges": "",
            "min_accepted_similarity": "",
            "max_blocked_similarity": "",
            "max_blocked_candidate_pct": "",
        }
    ]

    for pass_num in range(1, MAX_PASSES + 1):
        previous_count = len(clusters)
        clusters, stats = online_pass(clusters, rows, total_count)
        top25_pct = sum(cluster.count for cluster in sorted(clusters, key=lambda cluster: -cluster.count)[:25]) / total_count * 100.0
        log.append(
            {
                "pass": pass_num,
                "clusters": len(clusters),
                "top25_pct": top25_pct,
                "attempted": stats["attempted"],
                "merged": stats["merged"],
                "blocked": stats["blocked"],
                "singleton_merges": stats["singleton_merges"],
                "min_accepted_similarity": stats["min_accepted_similarity"],
                "max_blocked_similarity": stats["max_blocked_similarity"],
                "max_blocked_candidate_pct": stats["max_blocked_candidate_pct"],
            }
        )
        if stats["merged"] == 0 or len(clusters) == previous_count:
            break

    clusters.sort(key=lambda cluster: (-cluster.count, cluster.anchor))
    return clusters, log


def write_outputs(
    rows: list[dict[str, object]],
    unvectorized: list[dict[str, object]],
    total_count: int,
    clusters: list[pairwise.PairwiseCluster],
    log: list[dict[str, object]],
) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ranked = sorted(clusters, key=lambda cluster: (-cluster.count, cluster.anchor))

    with SUMMARY_OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
                "cluster_rank",
                "anchor_tag",
                "member_count",
                "mention_count",
                "pct_total",
                "weighted_internal_coherence_pct",
                "weighted_pairwise_purity_pct",
                "top_tags",
            ]
        )
        for rank, cluster in enumerate(ranked, start=1):
            top_members = sorted(
                cluster.members,
                key=lambda idx: (-int(rows[idx]["count"]), str(rows[idx]["coarse_tag"]), str(rows[idx].get("source_kind", ""))),
            )[:40]
            writer.writerow(
                [
                    rank,
                    cluster.anchor,
                    len(cluster.members),
                    cluster.count,
                    f"{cluster.count / total_count * 100.0:.6f}",
                    f"{weighted_internal_coherence(cluster, rows) * 100.0:.2f}",
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
                "centroid_similarity_pct",
            ]
        )
        for rank, cluster in enumerate(ranked, start=1):
            center = centroid(cluster)
            for idx in sorted(
                cluster.members,
                key=lambda row_idx: (-int(rows[row_idx]["count"]), str(rows[row_idx]["coarse_tag"]), str(rows[row_idx].get("source_kind", ""))),
            ):
                writer.writerow(
                    [
                        rows[idx]["coarse_tag"],
                        rows[idx]["count"],
                        f"{rows[idx]['percent']:.6f}",
                        rows[idx].get("source_kind", ""),
                        rows[idx].get("source_labels", ""),
                        rank,
                        cluster.anchor,
                        f"{float(np.dot(rows[idx]['vector'], center)) * 100.0:.2f}",
                    ]
                )
        for row in unvectorized:
            writer.writerow(
                [
                    row["coarse_tag"],
                    row["count"],
                    f"{row['percent']:.6f}",
                    row.get("source_kind", ""),
                    row.get("source_labels", ""),
                    "UNVECTORIZED",
                    "UNVECTORIZED",
                    "",
                ]
            )

    with LOG_OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "pass",
                "clusters",
                "top25_pct",
                "attempted",
                "merged",
                "blocked",
                "singleton_merges",
                "min_accepted_similarity",
                "max_blocked_similarity",
                "max_blocked_candidate_pct",
            ],
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        for entry in log:
            row = dict(entry)
            for key in ["top25_pct", "max_blocked_candidate_pct"]:
                if isinstance(row.get(key), float):
                    row[key] = f"{row[key]:.6f}"
            for key in ["min_accepted_similarity", "max_blocked_similarity"]:
                if isinstance(row.get(key), float):
                    row[key] = f"{row[key] * 100.0:.2f}"
            writer.writerow(row)

    with REPORT_OUT.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("# Frequency-Weighted Centroid Clustering With Candidate-Weight Gate\n\n")
        handle.write(
            "Each active cluster is represented by a frequency-weighted centroid. "
            "For each pass, clusters are processed by descending mention count and each candidate tries to merge "
            "with its most similar active target centroid. Singleton candidates have no threshold. "
            "Non-singleton candidates must exceed a sliding threshold based only on the candidate's own percent of total mentions: "
            "`min(99%, 50% + 15% * log10(1 + candidate_pct_total * 1000))`. "
            "The target cluster's size does not raise the threshold.\n\n"
        )
        handle.write(f"- Total mentions: {total_count}\n")
        handle.write(f"- Vectorized items: {len(rows)}\n")
        handle.write(f"- Unvectorized items: {len(unvectorized)}\n")
        handle.write(f"- Final clusters: {len(ranked)}\n")
        handle.write(f"- Top 25 coverage: {sum(cluster.count for cluster in ranked[:25]) / total_count * 100.0:.4f}%\n\n")

        handle.write("## Pass Log\n\n")
        for entry in log:
            if entry["pass"] == 0:
                handle.write(f"- pass 0: {entry['clusters']} clusters\n")
                continue
            handle.write(
                f"- pass {entry['pass']}: {entry['clusters']} clusters, top25 {entry['top25_pct']:.4f}%, "
                f"attempted {entry['attempted']}, merged {entry['merged']}, blocked {entry['blocked']}, "
                f"singleton merges {entry['singleton_merges']}, "
                f"minimum accepted sim {float(entry['min_accepted_similarity']) * 100.0:.2f}%, "
                f"maximum blocked sim {float(entry['max_blocked_similarity']) * 100.0:.2f}%\n"
            )

        handle.write("\n## Final Clusters\n\n")
        for rank, cluster in enumerate(ranked[:150], start=1):
            top_members = sorted(
                cluster.members,
                key=lambda idx: (-int(rows[idx]["count"]), str(rows[idx]["coarse_tag"]), str(rows[idx].get("source_kind", ""))),
            )[:18]
            handle.write(
                f"{rank}. `{cluster.anchor}`: {cluster.count} mentions "
                f"({cluster.count / total_count * 100.0:.4f}%), {len(cluster.members)} tags, "
                f"internal coherence {weighted_internal_coherence(cluster, rows) * 100.0:.2f}%, "
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


def main() -> None:
    rows, unvectorized, total_count = pairwise.load_intact_rows()
    clusters, log = run_recursive(rows, total_count)
    write_outputs(rows, unvectorized, total_count, clusters, log)

    ranked = sorted(clusters, key=lambda cluster: (-cluster.count, cluster.anchor))
    top25_pct = sum(cluster.count for cluster in ranked[:25]) / total_count * 100.0
    largest_pct = ranked[0].count / total_count * 100.0
    print(f"total={total_count}")
    print(f"vectorized={len(rows)}")
    print(f"unvectorized={len(unvectorized)}")
    print(f"passes={log[-1]['pass']}")
    print(f"clusters={len(ranked)}")
    print(f"top25_pct={top25_pct:.4f}")
    print(f"largest_pct={largest_pct:.4f}")
    print(f"summary={SUMMARY_OUT}")
    print(f"tag_map={TAG_MAP_OUT}")
    print(f"log={LOG_OUT}")
    print(f"report={REPORT_OUT}")


if __name__ == "__main__":
    main()
