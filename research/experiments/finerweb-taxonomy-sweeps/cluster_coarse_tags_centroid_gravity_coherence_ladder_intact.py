from __future__ import annotations

import csv
import math
from pathlib import Path

import numpy as np

import cluster_coarse_tags_pairwise_member_purity90_cultural_modes as pairwise
import cluster_coarse_tags_snowball_recursive as rec


BASE_DIR = Path(__file__).resolve().parent
OUT_DIR = BASE_DIR / "derived_fasttext_categories"

SUMMARY_OUT = OUT_DIR / "coarse_centroid_gravity_coherence_ladder_intact_summary.tsv"
TAG_MAP_OUT = OUT_DIR / "coarse_centroid_gravity_coherence_ladder_intact_tag_map.tsv"
LOG_OUT = OUT_DIR / "coarse_centroid_gravity_coherence_ladder_intact_log.tsv"
REPORT_OUT = OUT_DIR / "coarse_centroid_gravity_coherence_ladder_intact.md"

TOP_K = 2048
MAX_TARGET_TRIES = 160
MAX_PASSES = 64
TARGET_MAX_CLUSTERS = 50
START_COHERENCE = 0.95
MIN_COHERENCE = 0.75
COHERENCE_STEP = 0.01
GRAVITY_WEIGHT = 0.025


def normalize(vec: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(vec)
    if not norm:
        return vec.astype(np.float32)
    return (vec / norm).astype(np.float32)


def centroid(cluster: pairwise.PairwiseCluster) -> np.ndarray:
    return normalize(cluster.weighted_vector_sum.astype(np.float32))


def pct_total(cluster: pairwise.PairwiseCluster, total_count: int) -> float:
    return cluster.count / total_count * 100.0


def candidate_similarity_threshold(cluster: pairwise.PairwiseCluster, total_count: int) -> float:
    pct = pct_total(cluster, total_count)
    return min(0.985, 0.45 + 0.12 * math.log10(1.0 + pct * 1000.0))


def target_gravity_bonus(cluster: pairwise.PairwiseCluster, total_count: int) -> float:
    pct = pct_total(cluster, total_count)
    return GRAVITY_WEIGHT * math.log10(1.0 + pct * 1000.0)


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


def old_candidates(
    item_idx: int,
    active: np.ndarray,
    neighbor_idx: np.ndarray,
    neighbor_sim: np.ndarray,
    clusters: list[pairwise.PairwiseCluster],
    total_count: int,
) -> list[tuple[float, int, float]]:
    candidates: list[tuple[float, int, float]] = []
    for candidate, similarity in zip(neighbor_idx[item_idx], neighbor_sim[item_idx]):
        candidate = int(candidate)
        if not active[candidate]:
            continue
        sim = float(similarity)
        score = sim + target_gravity_bonus(clusters[candidate], total_count)
        candidates.append((score, candidate, sim))
        if len(candidates) >= MAX_TARGET_TRIES:
            break
    candidates.sort(reverse=True)
    return candidates


def created_candidates(
    item_idx: int,
    active: np.ndarray,
    created_indices: list[int],
    centroids: list[np.ndarray],
    clusters: list[pairwise.PairwiseCluster],
    total_count: int,
) -> list[tuple[float, int, float]]:
    candidates = [idx for idx in created_indices if active[idx]]
    if not candidates:
        return []

    matrix = np.stack([centroids[idx] for idx in candidates]).astype(np.float32)
    sims = matrix @ centroids[item_idx]
    scored = [
        (
            float(sim) + target_gravity_bonus(clusters[idx], total_count),
            idx,
            float(sim),
        )
        for idx, sim in zip(candidates, sims)
    ]
    scored.sort(reverse=True)
    return scored[:MAX_TARGET_TRIES]


def online_pass(
    clusters: list[pairwise.PairwiseCluster],
    rows: list[dict[str, object]],
    total_count: int,
    coherence_threshold: float,
) -> tuple[list[pairwise.PairwiseCluster], dict[str, object]]:
    starting_count = len(clusters)
    if starting_count < 2:
        return clusters, {
            "attempted": 0,
            "merged": 0,
            "blocked_similarity": 0,
            "blocked_coherence": 0,
            "min_accepted_similarity": 1.0,
            "min_accepted_coherence": 1.0,
            "max_blocked_similarity": -np.inf,
            "max_blocked_candidate_pct": 0.0,
        }

    centroids = [centroid(cluster) for cluster in clusters]
    x = np.stack(centroids[:starting_count]).astype(np.float32)
    neighbor_idx, neighbor_sim = rec.compute_top_neighbors(x, min(TOP_K, max(1, starting_count - 1)))
    active = np.ones(starting_count, dtype=bool)
    created_indices: list[int] = []
    order = sorted(range(starting_count), key=lambda idx: (clusters[idx].count, clusters[idx].anchor))

    attempted = 0
    merged = 0
    blocked_similarity = 0
    blocked_coherence = 0
    min_accepted_similarity = 1.0
    min_accepted_coherence = 1.0
    max_blocked_similarity = -np.inf
    max_blocked_candidate_pct = 0.0

    for item_idx in order:
        if not active[item_idx]:
            continue

        threshold = candidate_similarity_threshold(clusters[item_idx], total_count)
        candidate_list = old_candidates(item_idx, active, neighbor_idx, neighbor_sim, clusters, total_count)
        candidate_list.extend(
            created_candidates(item_idx, active, created_indices, centroids, clusters, total_count)
        )
        if not candidate_list:
            continue
        candidate_list.sort(reverse=True)

        attempted += 1
        accepted = False
        saw_similarity_failure = False
        saw_coherence_failure = False

        for _score, target_idx, similarity in candidate_list[:MAX_TARGET_TRIES]:
            if target_idx == item_idx or not active[target_idx]:
                continue
            if similarity < threshold:
                saw_similarity_failure = True
                max_blocked_similarity = max(max_blocked_similarity, similarity)
                max_blocked_candidate_pct = max(max_blocked_candidate_pct, pct_total(clusters[item_idx], total_count))
                continue

            proposed, _pairwise_purity = pairwise.merged_cluster(clusters[item_idx], clusters[target_idx], rows)
            coherence = weighted_internal_coherence(proposed, rows)
            if coherence < coherence_threshold:
                saw_coherence_failure = True
                max_blocked_similarity = max(max_blocked_similarity, similarity)
                max_blocked_candidate_pct = max(max_blocked_candidate_pct, pct_total(clusters[item_idx], total_count))
                continue

            active[item_idx] = False
            active[target_idx] = False
            clusters.append(proposed)
            active = np.append(active, True)
            centroids.append(centroid(proposed))
            created_indices.append(len(clusters) - 1)
            merged += 1
            min_accepted_similarity = min(min_accepted_similarity, similarity)
            min_accepted_coherence = min(min_accepted_coherence, coherence)
            accepted = True
            break

        if not accepted:
            if saw_similarity_failure:
                blocked_similarity += 1
            if saw_coherence_failure:
                blocked_coherence += 1

    next_clusters = [cluster for idx, cluster in enumerate(clusters) if active[idx]]
    next_clusters.sort(key=lambda cluster: (-cluster.count, cluster.anchor))
    return next_clusters, {
        "attempted": attempted,
        "merged": merged,
        "blocked_similarity": blocked_similarity,
        "blocked_coherence": blocked_coherence,
        "min_accepted_similarity": min_accepted_similarity,
        "min_accepted_coherence": min_accepted_coherence,
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
            "coherence_threshold": "",
            "clusters": len(clusters),
            "top25_pct": 0.0,
            "attempted": "",
            "merged": "",
            "blocked_similarity": "",
            "blocked_coherence": "",
            "min_accepted_similarity": "",
            "min_accepted_coherence": "",
            "max_blocked_similarity": "",
            "max_blocked_candidate_pct": "",
        }
    ]

    for pass_num in range(1, MAX_PASSES + 1):
        threshold = max(MIN_COHERENCE, START_COHERENCE - COHERENCE_STEP * (pass_num - 1))
        previous_count = len(clusters)
        clusters, stats = online_pass(clusters, rows, total_count, threshold)
        top25_pct = sum(cluster.count for cluster in sorted(clusters, key=lambda cluster: -cluster.count)[:25]) / total_count * 100.0
        log.append(
            {
                "pass": pass_num,
                "coherence_threshold": threshold,
                "clusters": len(clusters),
                "top25_pct": top25_pct,
                "attempted": stats["attempted"],
                "merged": stats["merged"],
                "blocked_similarity": stats["blocked_similarity"],
                "blocked_coherence": stats["blocked_coherence"],
                "min_accepted_similarity": stats["min_accepted_similarity"],
                "min_accepted_coherence": stats["min_accepted_coherence"],
                "max_blocked_similarity": stats["max_blocked_similarity"],
                "max_blocked_candidate_pct": stats["max_blocked_candidate_pct"],
            }
        )
        if len(clusters) <= TARGET_MAX_CLUSTERS:
            break
        if stats["merged"] == 0 and len(clusters) == previous_count and threshold <= MIN_COHERENCE:
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
                "coherence_threshold",
                "clusters",
                "top25_pct",
                "attempted",
                "merged",
                "blocked_similarity",
                "blocked_coherence",
                "min_accepted_similarity",
                "min_accepted_coherence",
                "max_blocked_similarity",
                "max_blocked_candidate_pct",
            ],
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        for entry in log:
            row = dict(entry)
            for key in ["coherence_threshold", "min_accepted_similarity", "min_accepted_coherence", "max_blocked_similarity"]:
                if isinstance(row.get(key), float):
                    row[key] = f"{row[key] * 100.0:.2f}"
            for key in ["top25_pct", "max_blocked_candidate_pct"]:
                if isinstance(row.get(key), float):
                    row[key] = f"{row[key]:.6f}"
            writer.writerow(row)

    with REPORT_OUT.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("# Gravity Centroid Coherence-Ladder Clustering\n\n")
        handle.write(
            "Each cluster is represented by a frequency-weighted centroid. "
            "Low-frequency candidates are processed first. Candidate targets are scored by centroid similarity plus "
            "a small target-size gravity bonus, so high-frequency centroids pull nearby small tags. "
            "A candidate's own percent of total mentions sets its minimum centroid similarity threshold; "
            "larger candidates need higher similarity to move, including high-frequency singleton tags. "
            "Each accepted merge must also pass a weighted internal-coherence floor. The floor starts at 95% "
            "and drops one point per pass down to 75%, stopping once the result has at most 50 clusters.\n\n"
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
                f"- pass {entry['pass']} @ coherence {float(entry['coherence_threshold']) * 100.0:.2f}%: "
                f"{entry['clusters']} clusters, top25 {entry['top25_pct']:.4f}%, "
                f"attempted {entry['attempted']}, merged {entry['merged']}, "
                f"blocked similarity {entry['blocked_similarity']}, blocked coherence {entry['blocked_coherence']}, "
                f"min accepted sim {float(entry['min_accepted_similarity']) * 100.0:.2f}%, "
                f"min accepted coherence {float(entry['min_accepted_coherence']) * 100.0:.2f}%\n"
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
