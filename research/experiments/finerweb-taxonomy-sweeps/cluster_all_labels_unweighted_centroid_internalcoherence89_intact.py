from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import numpy as np

import cluster_coarse_tags_pairwise_member_purity90_cultural_modes as pairwise


BASE_DIR = Path(__file__).resolve().parent
OUT_DIR = BASE_DIR / "derived_fasttext_categories" / "all_labels_unweighted_centroid_internalcoherence89"

SUMMARY_OUT = OUT_DIR / "all_labels_unweighted_centroid_internalcoherence89_intact_summary.tsv"
TAG_MAP_OUT = OUT_DIR / "all_labels_unweighted_centroid_internalcoherence89_intact_tag_map.tsv"
LOG_OUT = OUT_DIR / "all_labels_unweighted_centroid_internalcoherence89_intact_log.tsv"
REPORT_OUT = OUT_DIR / "all_labels_unweighted_centroid_internalcoherence89_intact.md"

THRESHOLD = 0.89
BLOCK_SIZE = 384
MAX_PASSES = 64


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
        vec = row["vector"].astype(np.float32)
        clusters.append(
            Cluster(
                members=[idx],
                vector_sum=vec.copy(),
                vector=vec.copy(),
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


def unweighted_internal_coherence(cluster: Cluster) -> float:
    if not cluster.members:
        return 1.0
    return float(np.linalg.norm(cluster.vector_sum) / len(cluster.members))


def weighted_internal_coherence(cluster: Cluster, rows: list[dict[str, object]]) -> float:
    weights = np.array([float(rows[idx]["count"]) for idx in cluster.members], dtype=np.float64)
    sims = np.array([float(np.dot(rows[idx]["vector"], cluster.vector)) for idx in cluster.members], dtype=np.float64)
    if not weights.sum():
        return float(np.mean(sims)) if len(sims) else 1.0
    return float(np.average(sims, weights=weights))


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


def proposed_unweighted_coherence(left: Cluster, right: Cluster) -> float:
    vector_sum = left.vector_sum + right.vector_sum
    member_count = len(left.members) + len(right.members)
    if not member_count:
        return 1.0
    return float(np.linalg.norm(vector_sum) / member_count)


def collect_candidate_pairs(clusters: list[Cluster]) -> list[tuple[float, int, int]]:
    x = np.stack([cluster.vector for cluster in clusters]).astype(np.float32)
    n = x.shape[0]
    all_indices = np.arange(n)
    pairs: list[tuple[float, int, int]] = []

    for start in range(0, n, BLOCK_SIZE):
        end = min(start + BLOCK_SIZE, n)
        sims = x[start:end] @ x.T
        row_ids = all_indices[start:end]
        sims[np.arange(end - start), row_ids] = -np.inf

        col_ids = all_indices[None, :]
        row_matrix = row_ids[:, None]
        mask = (sims >= THRESHOLD) & (col_ids > row_matrix)
        local_rows, cols = np.nonzero(mask)
        if not len(local_rows):
            continue
        vals = sims[local_rows, cols]
        for local_row, col, val in zip(local_rows.tolist(), cols.tolist(), vals.tolist()):
            pairs.append((float(val), int(start + local_row), int(col)))

    pairs.sort(reverse=True)
    return pairs


def merge_pass(clusters: list[Cluster], rows: list[dict[str, object]]) -> tuple[list[Cluster], dict[str, object]]:
    pairs = collect_candidate_pairs(clusters)
    used: set[int] = set()
    accepted: list[tuple[int, int, float, float]] = []
    blocked = 0
    best_blocked_similarity = -np.inf
    best_blocked_coherence = -np.inf
    worst_accepted_similarity = 1.0
    worst_accepted_coherence = 1.0

    for similarity, left_idx, right_idx in pairs:
        if left_idx in used or right_idx in used:
            continue
        coherence = proposed_unweighted_coherence(clusters[left_idx], clusters[right_idx])
        if coherence < THRESHOLD:
            blocked += 1
            best_blocked_similarity = max(best_blocked_similarity, similarity)
            best_blocked_coherence = max(best_blocked_coherence, coherence)
            continue

        used.add(left_idx)
        used.add(right_idx)
        accepted.append((left_idx, right_idx, similarity, coherence))
        worst_accepted_similarity = min(worst_accepted_similarity, similarity)
        worst_accepted_coherence = min(worst_accepted_coherence, coherence)

    next_clusters = [merge_clusters(clusters[left_idx], clusters[right_idx], rows) for left_idx, right_idx, _sim, _coh in accepted]
    next_clusters.extend(cluster for idx, cluster in enumerate(clusters) if idx not in used)
    next_clusters.sort(key=lambda cluster: (cluster.anchor, len(cluster.members), cluster.count))

    return next_clusters, {
        "candidate_pairs": len(pairs),
        "merged": len(accepted),
        "blocked": blocked,
        "worst_accepted_similarity": worst_accepted_similarity,
        "worst_accepted_coherence": worst_accepted_coherence,
        "best_blocked_similarity": best_blocked_similarity,
        "best_blocked_coherence": best_blocked_coherence,
    }


def run(rows: list[dict[str, object]], total_count: int) -> tuple[list[Cluster], list[dict[str, object]]]:
    clusters = initial_clusters(rows)
    log: list[dict[str, object]] = [
        {
            "pass": 0,
            "clusters": len(clusters),
            "top25_pct": 0.0,
            "candidate_pairs": "",
            "merged": "",
            "blocked": "",
            "worst_accepted_similarity": "",
            "worst_accepted_coherence": "",
            "best_blocked_similarity": "",
            "best_blocked_coherence": "",
        }
    ]

    for pass_num in range(1, MAX_PASSES + 1):
        previous_count = len(clusters)
        clusters, stats = merge_pass(clusters, rows)
        ranked = sorted(clusters, key=lambda cluster: (-cluster.count, cluster.anchor))
        log.append(
            {
                "pass": pass_num,
                "clusters": len(clusters),
                "top25_pct": sum(cluster.count for cluster in ranked[:25]) / total_count * 100.0,
                **stats,
            }
        )
        print(
            f"pass={pass_num} clusters={len(clusters)} merged={stats['merged']} "
            f"candidates={stats['candidate_pairs']}",
            flush=True,
        )
        if stats["merged"] == 0 or len(clusters) == previous_count:
            break

    clusters.sort(key=lambda cluster: (-cluster.count, cluster.anchor))
    return clusters, log


def write_outputs(
    rows: list[dict[str, object]],
    unvectorized: list[dict[str, object]],
    total_count: int,
    clusters: list[Cluster],
    log: list[dict[str, object]],
) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    vectorized_count = sum(int(row["count"]) for row in rows)
    top10_count = sum(cluster.count for cluster in clusters[:10])
    top25_count = sum(cluster.count for cluster in clusters[:25])
    top100_count = sum(cluster.count for cluster in clusters[:100])

    with SUMMARY_OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
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
        for rank, cluster in enumerate(clusters, start=1):
            members = sorted(cluster.members, key=lambda idx: (-int(rows[idx]["count"]), str(rows[idx]["coarse_tag"])))
            writer.writerow(
                [
                    rank,
                    cluster.anchor,
                    len(cluster.members),
                    cluster.count,
                    f"{cluster.count / total_count * 100.0:.6f}",
                    f"{unweighted_internal_coherence(cluster) * 100.0:.2f}",
                    f"{weighted_internal_coherence(cluster, rows) * 100.0:.2f}",
                    f"{weighted_pairwise_purity(cluster, rows) * 100.0:.2f}",
                    "; ".join(f"{rows[idx]['coarse_tag']} ({rows[idx]['count']})" for idx in members),
                ]
            )

    with TAG_MAP_OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["coarse_tag", "count", "pct_total", "cluster_rank", "anchor_tag", "centroid_similarity_pct"])
        for rank, cluster in enumerate(clusters, start=1):
            for idx in sorted(cluster.members, key=lambda row_idx: (-int(rows[row_idx]["count"]), str(rows[row_idx]["coarse_tag"]))):
                writer.writerow(
                    [
                        rows[idx]["coarse_tag"],
                        rows[idx]["count"],
                        f"{rows[idx]['percent']:.6f}",
                        rank,
                        cluster.anchor,
                        f"{float(np.dot(rows[idx]['vector'], cluster.vector)) * 100.0:.2f}",
                    ]
                )
        for row in unvectorized:
            writer.writerow([row["coarse_tag"], row["count"], f"{row['percent']:.6f}", "UNVECTORIZED", "UNVECTORIZED", ""])

    with LOG_OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "pass",
                "clusters",
                "top25_pct",
                "candidate_pairs",
                "merged",
                "blocked",
                "worst_accepted_similarity",
                "worst_accepted_coherence",
                "best_blocked_similarity",
                "best_blocked_coherence",
            ],
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        for entry in log:
            row = dict(entry)
            if isinstance(row.get("top25_pct"), float):
                row["top25_pct"] = f"{row['top25_pct']:.6f}"
            for key in [
                "worst_accepted_similarity",
                "worst_accepted_coherence",
                "best_blocked_similarity",
                "best_blocked_coherence",
            ]:
                if isinstance(row.get(key), float):
                    row[key] = f"{row[key] * 100.0:.6f}"
            writer.writerow(row)

    with REPORT_OUT.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("# All Labels Unweighted Centroid Internal-Coherence 89% Clustering\n\n")
        handle.write(
            "Full vectorized label set. `cultural reference` is intact. "
            "Each tag starts as a singleton. Cluster centroids are normalized unweighted means of member tag vectors. "
            "Frequency is not used in centroid construction, merge acceptance, or merge ordering. "
            "A merge is accepted only when centroid-to-centroid similarity is >= 89% and the proposed merged cluster's "
            "unweighted member-to-centroid coherence is also >= 89%. No postpass.\n\n"
        )
        handle.write(f"- Total mentions: {total_count}\n")
        handle.write(f"- Vectorized rows: {len(rows)}\n")
        handle.write(f"- Vectorized mention mass: {vectorized_count} ({vectorized_count / total_count * 100.0:.4f}% of total)\n")
        handle.write(f"- Unvectorized rows: {len(unvectorized)}\n")
        handle.write(f"- Final clusters: {len(clusters)}\n")
        handle.write(f"- Top-10 coverage: {top10_count / total_count * 100.0:.4f}%\n")
        handle.write(f"- Top-25 coverage: {top25_count / total_count * 100.0:.4f}%\n")
        handle.write(f"- Top-100 coverage: {top100_count / total_count * 100.0:.4f}%\n\n")

        handle.write("## Pass Log\n\n")
        for entry in log:
            if entry["pass"] == 0:
                handle.write(f"- pass 0: {entry['clusters']} clusters\n")
                continue
            handle.write(
                f"- pass {entry['pass']}: {entry['clusters']} clusters, top25 {entry['top25_pct']:.4f}%, "
                f"candidate pairs {entry['candidate_pairs']}, merged {entry['merged']}, blocked {entry['blocked']}, "
                f"worst accepted sim {float(entry['worst_accepted_similarity']) * 100.0:.2f}%, "
                f"worst accepted coherence {float(entry['worst_accepted_coherence']) * 100.0:.2f}%\n"
            )

        handle.write("\n## Final Clusters\n\n")
        for rank, cluster in enumerate(clusters, start=1):
            members = sorted(cluster.members, key=lambda idx: (-int(rows[idx]["count"]), str(rows[idx]["coarse_tag"])))
            handle.write(
                f"{rank}. `{cluster.anchor}`: {cluster.count} mentions "
                f"({cluster.count / total_count * 100.0:.4f}%), {len(cluster.members)} tags, "
                f"unweighted coherence {unweighted_internal_coherence(cluster) * 100.0:.2f}%, "
                f"weighted coherence {weighted_internal_coherence(cluster, rows) * 100.0:.2f}%\n"
            )
            handle.write("   - " + "; ".join(f"`{rows[idx]['coarse_tag']}` ({rows[idx]['count']})" for idx in members) + "\n")


def main() -> None:
    rows, unvectorized, total_count = pairwise.load_intact_rows()
    clusters, log = run(rows, total_count)
    write_outputs(rows, unvectorized, total_count, clusters, log)
    print(f"total={total_count}")
    print(f"vectorized={len(rows)}")
    print(f"unvectorized={len(unvectorized)}")
    print(f"clusters={len(clusters)}")
    print(f"report={REPORT_OUT}")
    print(f"summary={SUMMARY_OUT}")
    print(f"tag_map={TAG_MAP_OUT}")
    print(f"log={LOG_OUT}")


if __name__ == "__main__":
    main()
