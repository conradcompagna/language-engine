from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

import cluster_coarse_tags_pairwise_member_purity90_cultural_modes as pairwise
import cluster_coarse_tags_snowball_recursive as rec


BASE_DIR = Path(__file__).resolve().parent
OUT_DIR = BASE_DIR / "derived_fasttext_categories"

SUMMARY_OUT = OUT_DIR / "coarse_unweighted_centroid90_raw_and_freqpost_intact_summary.tsv"
TAG_MAP_OUT = OUT_DIR / "coarse_unweighted_centroid90_raw_and_freqpost_intact_tag_map.tsv"
LOG_OUT = OUT_DIR / "coarse_unweighted_centroid90_raw_and_freqpost_intact_log.tsv"
REPORT_OUT = OUT_DIR / "coarse_unweighted_centroid90_raw_and_freqpost_intact.md"

RAW_SIMILARITY_THRESHOLD = 0.90
TOP_K = 2048
MAX_TARGET_TRIES = 160
MAX_RAW_PASSES = 64
MAX_POST_PASSES = 64
TARGET_POST_CLUSTERS = 50


@dataclass
class Cluster:
    members: list[int]
    vector_sum: np.ndarray
    vector: np.ndarray
    count: int
    anchor: str


def normalize(vec: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(vec)
    if not norm:
        return vec.astype(np.float32)
    return (vec / norm).astype(np.float32)


def initial_clusters(rows: list[dict[str, object]]) -> list[Cluster]:
    clusters = []
    for idx, row in enumerate(rows):
        vector = row["vector"].astype(np.float32)
        clusters.append(
            Cluster(
                members=[idx],
                vector_sum=vector.copy(),
                vector=vector.copy(),
                count=int(row["count"]),
                anchor=str(row["coarse_tag"]),
            )
        )
    return clusters


def merge_clusters(left: Cluster, right: Cluster, rows: list[dict[str, object]]) -> Cluster:
    members = left.members + right.members
    vector_sum = left.vector_sum + right.vector_sum
    anchor_idx = max(members, key=lambda idx: (int(rows[idx]["count"]), str(rows[idx]["coarse_tag"])))
    return Cluster(
        members=members,
        vector_sum=vector_sum,
        vector=normalize(vector_sum),
        count=left.count + right.count,
        anchor=str(rows[anchor_idx]["coarse_tag"]),
    )


def weighted_internal_coherence(cluster: Cluster, rows: list[dict[str, object]]) -> float:
    weights = np.array([float(rows[idx]["count"]) for idx in cluster.members], dtype=np.float64)
    sims = np.array([float(np.dot(rows[idx]["vector"], cluster.vector)) for idx in cluster.members], dtype=np.float64)
    if not weights.sum():
        return float(np.mean(sims)) if len(sims) else 1.0
    return float(np.average(sims, weights=weights))


def unweighted_internal_coherence(cluster: Cluster, rows: list[dict[str, object]]) -> float:
    sims = [float(np.dot(rows[idx]["vector"], cluster.vector)) for idx in cluster.members]
    return float(np.mean(sims)) if sims else 1.0


def weighted_pairwise_purity(cluster: Cluster, rows: list[dict[str, object]]) -> float:
    if len(cluster.members) < 2:
        return 1.0
    vectors = np.stack([rows[idx]["vector"] for idx in cluster.members]).astype(np.float64)
    weights = np.array([float(rows[idx]["count"]) for idx in cluster.members], dtype=np.float64)
    weighted = vectors * weights[:, None]
    total_pair_num = 0.5 * (float(np.dot(weighted.sum(axis=0), weighted.sum(axis=0))) - float(np.sum(weights * weights)))
    total_pair_den = 0.5 * (float(weights.sum() ** 2) - float(np.sum(weights * weights)))
    if not total_pair_den:
        return 1.0
    return total_pair_num / total_pair_den


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


def raw_pass(clusters: list[Cluster], rows: list[dict[str, object]]) -> tuple[list[Cluster], dict[str, object]]:
    starting_count = len(clusters)
    if starting_count < 2:
        return clusters, {"attempted": 0, "merged": 0, "blocked": 0, "min_accepted_similarity": 1.0, "max_blocked_similarity": -np.inf}

    centroids = [cluster.vector for cluster in clusters]
    x = np.stack(centroids[:starting_count]).astype(np.float32)
    neighbor_idx, neighbor_sim = rec.compute_top_neighbors(x, min(TOP_K, max(1, starting_count - 1)))
    active = np.ones(starting_count, dtype=bool)
    created_indices: list[int] = []
    order = sorted(range(starting_count), key=lambda idx: clusters[idx].anchor)

    attempted = 0
    merged = 0
    blocked = 0
    min_accepted_similarity = 1.0
    max_blocked_similarity = -np.inf

    for item_idx in order:
        if not active[item_idx]:
            continue

        old_candidate, old_similarity = first_active_old_candidate(item_idx, active, neighbor_idx, neighbor_sim, x)
        created_candidate, created_similarity = best_created_candidate(item_idx, active, created_indices, centroids)
        if created_similarity > old_similarity:
            target_idx = created_candidate
            similarity = created_similarity
        else:
            target_idx = old_candidate
            similarity = old_similarity
        if target_idx is None:
            continue

        attempted += 1
        if similarity < RAW_SIMILARITY_THRESHOLD:
            blocked += 1
            max_blocked_similarity = max(max_blocked_similarity, similarity)
            continue

        proposed = merge_clusters(clusters[item_idx], clusters[target_idx], rows)
        active[item_idx] = False
        active[target_idx] = False
        clusters.append(proposed)
        active = np.append(active, True)
        centroids.append(proposed.vector)
        created_indices.append(len(clusters) - 1)
        merged += 1
        min_accepted_similarity = min(min_accepted_similarity, similarity)

    next_clusters = [cluster for idx, cluster in enumerate(clusters) if active[idx]]
    next_clusters.sort(key=lambda cluster: (-cluster.count, cluster.anchor))
    return next_clusters, {
        "attempted": attempted,
        "merged": merged,
        "blocked": blocked,
        "min_accepted_similarity": min_accepted_similarity,
        "max_blocked_similarity": max_blocked_similarity,
    }


def run_raw(rows: list[dict[str, object]], total_count: int) -> tuple[list[Cluster], list[dict[str, object]]]:
    clusters = initial_clusters(rows)
    log = [
        {
            "phase": "raw_centroid90",
            "pass": 0,
            "clusters": len(clusters),
            "top25_pct": 0.0,
            "attempted": "",
            "merged": "",
            "blocked": "",
            "threshold_pct": RAW_SIMILARITY_THRESHOLD * 100.0,
            "min_accepted_similarity": "",
            "max_blocked_similarity": "",
            "max_blocked_candidate_pct": "",
        }
    ]
    for pass_num in range(1, MAX_RAW_PASSES + 1):
        previous_count = len(clusters)
        clusters, stats = raw_pass(clusters, rows)
        top25_pct = sum(cluster.count for cluster in sorted(clusters, key=lambda cluster: -cluster.count)[:25]) / total_count * 100.0
        log.append(
            {
                "phase": "raw_centroid90",
                "pass": pass_num,
                "clusters": len(clusters),
                "top25_pct": top25_pct,
                "attempted": stats["attempted"],
                "merged": stats["merged"],
                "blocked": stats["blocked"],
                "threshold_pct": RAW_SIMILARITY_THRESHOLD * 100.0,
                "min_accepted_similarity": stats["min_accepted_similarity"] * 100.0,
                "max_blocked_similarity": stats["max_blocked_similarity"] * 100.0,
                "max_blocked_candidate_pct": "",
            }
        )
        if stats["merged"] == 0 or len(clusters) == previous_count:
            break
    return clusters, log


def postpass_threshold(cluster: Cluster, total_count: int) -> float:
    pct = cluster.count / total_count * 100.0
    return min(0.99, 0.30 + 0.18 * math.log10(1.0 + pct * 1000.0))


def postpass_candidates(
    item_idx: int,
    active: np.ndarray,
    neighbor_idx: np.ndarray,
    neighbor_sim: np.ndarray,
    x: np.ndarray,
    created_indices: list[int],
    centroids: list[np.ndarray],
) -> list[tuple[float, int]]:
    candidates: list[tuple[float, int]] = []
    for candidate, similarity in zip(neighbor_idx[item_idx], neighbor_sim[item_idx]):
        candidate = int(candidate)
        if active[candidate]:
            candidates.append((float(similarity), candidate))
            if len(candidates) >= MAX_TARGET_TRIES:
                break

    created = [idx for idx in created_indices if active[idx]]
    if created:
        matrix = np.stack([centroids[idx] for idx in created]).astype(np.float32)
        sims = matrix @ centroids[item_idx]
        candidates.extend((float(sim), idx) for sim, idx in zip(sims, created))

    if not candidates:
        active_old = np.flatnonzero(active[: x.shape[0]])
        active_old = active_old[active_old != item_idx]
        if len(active_old):
            sims = x[active_old] @ x[item_idx]
            candidates.extend((float(sim), int(idx)) for sim, idx in zip(sims, active_old))

    candidates.sort(reverse=True)
    return candidates[:MAX_TARGET_TRIES]


def postpass_once(
    clusters: list[Cluster],
    rows: list[dict[str, object]],
    total_count: int,
) -> tuple[list[Cluster], dict[str, object]]:
    starting_count = len(clusters)
    target_merges = max(0, starting_count - TARGET_POST_CLUSTERS)
    if starting_count < 2:
        return clusters, {"attempted": 0, "merged": 0, "blocked": 0, "min_accepted_similarity": 1.0, "max_blocked_similarity": -np.inf, "max_blocked_candidate_pct": 0.0}

    centroids = [cluster.vector for cluster in clusters]
    x = np.stack(centroids[:starting_count]).astype(np.float32)
    neighbor_idx, neighbor_sim = rec.compute_top_neighbors(x, min(TOP_K, max(1, starting_count - 1)))
    active = np.ones(starting_count, dtype=bool)
    created_indices: list[int] = []
    order = sorted(range(starting_count), key=lambda idx: (clusters[idx].count, clusters[idx].anchor))

    attempted = 0
    merged = 0
    blocked = 0
    min_accepted_similarity = 1.0
    max_blocked_similarity = -np.inf
    max_blocked_candidate_pct = 0.0

    for item_idx in order:
        if target_merges and merged >= target_merges:
            break
        if not active[item_idx]:
            continue

        candidates = postpass_candidates(item_idx, active, neighbor_idx, neighbor_sim, x, created_indices, centroids)
        if not candidates:
            continue
        threshold = postpass_threshold(clusters[item_idx], total_count)
        attempted += 1

        accepted = False
        for similarity, target_idx in candidates:
            if target_idx == item_idx or not active[target_idx]:
                continue
            if similarity < threshold:
                max_blocked_similarity = max(max_blocked_similarity, similarity)
                max_blocked_candidate_pct = max(max_blocked_candidate_pct, clusters[item_idx].count / total_count * 100.0)
                continue

            proposed = merge_clusters(clusters[item_idx], clusters[target_idx], rows)
            active[item_idx] = False
            active[target_idx] = False
            clusters.append(proposed)
            active = np.append(active, True)
            centroids.append(proposed.vector)
            created_indices.append(len(clusters) - 1)
            merged += 1
            min_accepted_similarity = min(min_accepted_similarity, similarity)
            accepted = True
            break

        if not accepted:
            blocked += 1

    next_clusters = [cluster for idx, cluster in enumerate(clusters) if active[idx]]
    next_clusters.sort(key=lambda cluster: (-cluster.count, cluster.anchor))
    return next_clusters, {
        "attempted": attempted,
        "merged": merged,
        "blocked": blocked,
        "min_accepted_similarity": min_accepted_similarity,
        "max_blocked_similarity": max_blocked_similarity,
        "max_blocked_candidate_pct": max_blocked_candidate_pct,
    }


def run_postpass(
    raw_clusters: list[Cluster],
    rows: list[dict[str, object]],
    total_count: int,
) -> tuple[list[Cluster], list[dict[str, object]]]:
    clusters = [
        Cluster(
            members=list(cluster.members),
            vector_sum=cluster.vector_sum.copy(),
            vector=cluster.vector.copy(),
            count=cluster.count,
            anchor=cluster.anchor,
        )
        for cluster in raw_clusters
    ]
    log = [
        {
            "phase": "freq_threshold_postpass",
            "pass": 0,
            "clusters": len(clusters),
            "top25_pct": sum(cluster.count for cluster in sorted(clusters, key=lambda cluster: -cluster.count)[:25]) / total_count * 100.0,
            "attempted": "",
            "merged": "",
            "blocked": "",
            "threshold_pct": "candidate_size_curve",
            "min_accepted_similarity": "",
            "max_blocked_similarity": "",
            "max_blocked_candidate_pct": "",
        }
    ]
    for pass_num in range(1, MAX_POST_PASSES + 1):
        if len(clusters) <= TARGET_POST_CLUSTERS:
            break
        previous_count = len(clusters)
        clusters, stats = postpass_once(clusters, rows, total_count)
        top25_pct = sum(cluster.count for cluster in sorted(clusters, key=lambda cluster: -cluster.count)[:25]) / total_count * 100.0
        log.append(
            {
                "phase": "freq_threshold_postpass",
                "pass": pass_num,
                "clusters": len(clusters),
                "top25_pct": top25_pct,
                "attempted": stats["attempted"],
                "merged": stats["merged"],
                "blocked": stats["blocked"],
                "threshold_pct": "candidate_size_curve",
                "min_accepted_similarity": stats["min_accepted_similarity"] * 100.0,
                "max_blocked_similarity": stats["max_blocked_similarity"] * 100.0,
                "max_blocked_candidate_pct": stats["max_blocked_candidate_pct"],
            }
        )
        if len(clusters) <= TARGET_POST_CLUSTERS:
            break
        if stats["merged"] == 0 or len(clusters) == previous_count:
            break
    return clusters, log


def write_outputs(
    rows: list[dict[str, object]],
    unvectorized: list[dict[str, object]],
    total_count: int,
    raw_clusters: list[Cluster],
    raw_log: list[dict[str, object]],
    post_clusters: list[Cluster],
    post_log: list[dict[str, object]],
) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    results = [
        ("raw_centroid90", raw_clusters),
        ("freq_threshold_postpass", post_clusters),
    ]

    with SUMMARY_OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
                "phase",
                "cluster_rank",
                "anchor_tag",
                "member_count",
                "mention_count",
                "pct_total",
                "unweighted_internal_coherence_pct",
                "weighted_internal_coherence_pct",
                "weighted_pairwise_purity_pct",
                "top_tags",
            ]
        )
        for phase, clusters in results:
            ranked = sorted(clusters, key=lambda cluster: (-cluster.count, cluster.anchor))
            for rank, cluster in enumerate(ranked, start=1):
                top_members = sorted(
                    cluster.members,
                    key=lambda idx: (-int(rows[idx]["count"]), str(rows[idx]["coarse_tag"]), str(rows[idx].get("source_kind", ""))),
                )[:40]
                writer.writerow(
                    [
                        phase,
                        rank,
                        cluster.anchor,
                        len(cluster.members),
                        cluster.count,
                        f"{cluster.count / total_count * 100.0:.6f}",
                        f"{unweighted_internal_coherence(cluster, rows) * 100.0:.2f}",
                        f"{weighted_internal_coherence(cluster, rows) * 100.0:.2f}",
                        f"{weighted_pairwise_purity(cluster, rows) * 100.0:.2f}",
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
                "phase",
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
        for phase, clusters in results:
            ranked = sorted(clusters, key=lambda cluster: (-cluster.count, cluster.anchor))
            for rank, cluster in enumerate(ranked, start=1):
                for idx in sorted(
                    cluster.members,
                    key=lambda row_idx: (-int(rows[row_idx]["count"]), str(rows[row_idx]["coarse_tag"]), str(rows[row_idx].get("source_kind", ""))),
                ):
                    writer.writerow(
                        [
                            phase,
                            rows[idx]["coarse_tag"],
                            rows[idx]["count"],
                            f"{rows[idx]['percent']:.6f}",
                            rows[idx].get("source_kind", ""),
                            rows[idx].get("source_labels", ""),
                            rank,
                            cluster.anchor,
                            f"{float(np.dot(rows[idx]['vector'], cluster.vector)) * 100.0:.2f}",
                        ]
                    )
        for row in unvectorized:
            for phase, _clusters in results:
                writer.writerow(
                    [
                        phase,
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
                "phase",
                "pass",
                "clusters",
                "top25_pct",
                "attempted",
                "merged",
                "blocked",
                "threshold_pct",
                "min_accepted_similarity",
                "max_blocked_similarity",
                "max_blocked_candidate_pct",
            ],
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        for entry in raw_log + post_log:
            row = dict(entry)
            for key in ["top25_pct", "threshold_pct", "min_accepted_similarity", "max_blocked_similarity", "max_blocked_candidate_pct"]:
                if isinstance(row.get(key), float):
                    row[key] = f"{row[key]:.6f}"
            writer.writerow(row)

    with REPORT_OUT.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("# Unweighted Centroid-90 Raw Clusters And Frequency-Threshold Postpass\n\n")
        handle.write(
            "Raw phase: each tag starts as its own cluster. Cluster centroids are unweighted means of member tag vectors. "
            "A candidate can merge with its nearest active target only if centroid-to-centroid cosine similarity is at least 90%. "
            "No frequency is used in centroid construction or raw merge gating.\n\n"
        )
        handle.write(
            "Postpass: starts from the raw clusters. Centroids remain unweighted. Candidates are processed from low frequency to high frequency. "
            "A candidate can merge with its nearest target only if similarity clears a threshold based on the candidate's own percent of total mentions: "
            "`min(99%, 30% + 18% * log10(1 + candidate_pct_total * 1000))`. "
            "This makes small clusters easy to roll up and large clusters hard to move. "
            f"The postpass stops once it reaches {TARGET_POST_CLUSTERS} or fewer clusters, or at equilibrium.\n\n"
        )
        handle.write(f"- Total mentions: {total_count}\n")
        handle.write(f"- Vectorized items: {len(rows)}\n")
        handle.write(f"- Unvectorized items: {len(unvectorized)}\n\n")

        for phase, clusters, log in [
            ("raw_centroid90", raw_clusters, raw_log),
            ("freq_threshold_postpass", post_clusters, post_log),
        ]:
            ranked = sorted(clusters, key=lambda cluster: (-cluster.count, cluster.anchor))
            handle.write(f"## {phase}\n\n")
            handle.write(f"- Final clusters: {len(ranked)}\n")
            handle.write(f"- Top 25 coverage: {sum(cluster.count for cluster in ranked[:25]) / total_count * 100.0:.4f}%\n\n")
            handle.write("### Pass Log\n\n")
            for entry in log:
                if entry["pass"] == 0:
                    handle.write(f"- pass 0: {entry['clusters']} clusters\n")
                    continue
                handle.write(
                    f"- pass {entry['pass']}: {entry['clusters']} clusters, top25 {entry['top25_pct']:.4f}%, "
                    f"attempted {entry['attempted']}, merged {entry['merged']}, blocked {entry['blocked']}, "
                    f"min accepted sim {float(entry['min_accepted_similarity']):.2f}%, "
                    f"max blocked sim {float(entry['max_blocked_similarity']):.2f}%\n"
                )
            handle.write("\n### Top Clusters\n\n")
            for rank, cluster in enumerate(ranked[:80], start=1):
                top_members = sorted(
                    cluster.members,
                    key=lambda idx: (-int(rows[idx]["count"]), str(rows[idx]["coarse_tag"]), str(rows[idx].get("source_kind", ""))),
                )[:16]
                handle.write(
                    f"{rank}. `{cluster.anchor}`: {cluster.count} mentions "
                    f"({cluster.count / total_count * 100.0:.4f}%), {len(cluster.members)} tags, "
                    f"unweighted coherence {unweighted_internal_coherence(cluster, rows) * 100.0:.2f}%, "
                    f"weighted coherence {weighted_internal_coherence(cluster, rows) * 100.0:.2f}%\n"
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
    rows, unvectorized, total_count = pairwise.load_intact_rows()
    raw_clusters, raw_log = run_raw(rows, total_count)
    post_clusters, post_log = run_postpass(raw_clusters, rows, total_count)
    write_outputs(rows, unvectorized, total_count, raw_clusters, raw_log, post_clusters, post_log)

    for phase, clusters, log in [
        ("raw_centroid90", raw_clusters, raw_log),
        ("freq_threshold_postpass", post_clusters, post_log),
    ]:
        ranked = sorted(clusters, key=lambda cluster: (-cluster.count, cluster.anchor))
        top25_pct = sum(cluster.count for cluster in ranked[:25]) / total_count * 100.0
        print(
            f"{phase}: passes={log[-1]['pass']} clusters={len(ranked)} "
            f"top25_pct={top25_pct:.4f} largest_pct={ranked[0].count / total_count * 100.0:.4f}"
        )
    print(f"total={total_count}")
    print(f"vectorized={len(rows)}")
    print(f"unvectorized={len(unvectorized)}")
    print(f"summary={SUMMARY_OUT}")
    print(f"tag_map={TAG_MAP_OUT}")
    print(f"log={LOG_OUT}")
    print(f"report={REPORT_OUT}")


if __name__ == "__main__":
    main()
