from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import numpy as np

import cluster_coarse_tags_pairwise_member_purity90_cultural_modes as pairwise


BASE_DIR = Path(__file__).resolve().parent
OUT_DIR = BASE_DIR / "derived_fasttext_categories"

SUMMARY_OUT = OUT_DIR / "coarse_top500_fixed90_intact_summary.tsv"
TAG_MAP_OUT = OUT_DIR / "coarse_top500_fixed90_intact_tag_map.tsv"
LOG_OUT = OUT_DIR / "coarse_top500_fixed90_intact_log.tsv"
REPORT_OUT = OUT_DIR / "coarse_top500_fixed90_intact.md"

TOP_N = 500
SIMILARITY_THRESHOLD = 0.90
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


def unweighted_internal_coherence(cluster: Cluster, rows: list[dict[str, object]]) -> float:
    sims = [float(np.dot(rows[idx]["vector"], cluster.vector)) for idx in cluster.members]
    return float(np.mean(sims)) if sims else 1.0


def weighted_internal_coherence(cluster: Cluster, rows: list[dict[str, object]]) -> float:
    weights = np.array([float(rows[idx]["count"]) for idx in cluster.members], dtype=np.float64)
    sims = np.array([float(np.dot(rows[idx]["vector"], cluster.vector)) for idx in cluster.members], dtype=np.float64)
    if not weights.sum():
        return float(np.mean(sims)) if len(sims) else 1.0
    return float(np.average(sims, weights=weights))


def merge_pass(clusters: list[Cluster], rows: list[dict[str, object]]) -> tuple[list[Cluster], int]:
    x = np.stack([cluster.vector for cluster in clusters]).astype(np.float32)
    sims = x @ x.T
    np.fill_diagonal(sims, -np.inf)

    pairs: list[tuple[float, int, int]] = []
    for left in range(len(clusters)):
        for right in range(left + 1, len(clusters)):
            similarity = float(sims[left, right])
            if similarity >= SIMILARITY_THRESHOLD:
                pairs.append((similarity, left, right))
    pairs.sort(reverse=True)

    used: set[int] = set()
    new_clusters: list[Cluster] = []
    merge_pairs: list[tuple[int, int]] = []

    for _similarity, left, right in pairs:
        if left in used or right in used:
            continue
        used.add(left)
        used.add(right)
        merge_pairs.append((left, right))

    for left, right in merge_pairs:
        new_clusters.append(merge_clusters(clusters[left], clusters[right], rows))
    for idx, cluster in enumerate(clusters):
        if idx not in used:
            new_clusters.append(cluster)

    new_clusters.sort(key=lambda cluster: (-cluster.count, cluster.anchor))
    return new_clusters, len(merge_pairs)


def run_fixed90(rows: list[dict[str, object]], total_count: int) -> tuple[list[Cluster], list[dict[str, object]]]:
    clusters = initial_clusters(rows)
    log = [
        {
            "pass": 0,
            "clusters": len(clusters),
            "merged": "",
            "top25_pct": sum(cluster.count for cluster in sorted(clusters, key=lambda cluster: -cluster.count)[:25]) / total_count * 100.0,
        }
    ]

    for pass_num in range(1, MAX_PASSES + 1):
        previous_count = len(clusters)
        clusters, merged = merge_pass(clusters, rows)
        log.append(
            {
                "pass": pass_num,
                "clusters": len(clusters),
                "merged": merged,
                "top25_pct": sum(cluster.count for cluster in sorted(clusters, key=lambda cluster: -cluster.count)[:25]) / total_count * 100.0,
            }
        )
        if merged == 0 or len(clusters) == previous_count:
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
    top500_count = sum(int(row["count"]) for row in rows)

    with SUMMARY_OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
                "cluster_rank",
                "anchor_tag",
                "member_count",
                "mention_count",
                "pct_total",
                "pct_top500",
                "unweighted_internal_coherence_pct",
                "weighted_internal_coherence_pct",
                "top_tags",
            ]
        )
        for rank, cluster in enumerate(clusters, start=1):
            top_members = sorted(
                cluster.members,
                key=lambda idx: (-int(rows[idx]["count"]), str(rows[idx]["coarse_tag"]), str(rows[idx].get("source_kind", ""))),
            )[:50]
            writer.writerow(
                [
                    rank,
                    cluster.anchor,
                    len(cluster.members),
                    cluster.count,
                    f"{cluster.count / total_count * 100.0:.6f}",
                    f"{cluster.count / top500_count * 100.0:.6f}",
                    f"{unweighted_internal_coherence(cluster, rows) * 100.0:.2f}",
                    f"{weighted_internal_coherence(cluster, rows) * 100.0:.2f}",
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
                "cluster_rank",
                "anchor_tag",
                "centroid_similarity_pct",
            ]
        )
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

    with LOG_OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["pass", "clusters", "merged", "top25_pct"],
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        for entry in log:
            row = dict(entry)
            if isinstance(row.get("top25_pct"), float):
                row["top25_pct"] = f"{row['top25_pct']:.6f}"
            writer.writerow(row)

    with REPORT_OUT.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("# Top-500 Fixed 90% Coarse Tag Clustering\n\n")
        handle.write(
            "This run uses only the 500 highest-frequency vectorized coarse tags. "
            "Cluster centroids are unweighted sums of member tag vectors. "
            "It repeatedly merges non-overlapping centroid pairs whose cosine similarity is >= 90%, "
            "then stops at equilibrium. There is no threshold lowering and no forced collapse target.\n\n"
        )
        handle.write(f"- Full total mentions: {total_count}\n")
        handle.write(f"- Top-500 mentions: {top500_count} ({top500_count / total_count * 100.0:.4f}% of full total)\n")
        handle.write(f"- Unvectorized full-inventory rows: {len(unvectorized)}\n")
        handle.write(f"- Final clusters: {len(clusters)}\n")
        handle.write(f"- Top-25 cluster coverage: {sum(cluster.count for cluster in clusters[:25]) / total_count * 100.0:.4f}% of full total\n\n")

        handle.write("## Final Clusters\n\n")
        for rank, cluster in enumerate(clusters, start=1):
            top_members = sorted(
                cluster.members,
                key=lambda idx: (-int(rows[idx]["count"]), str(rows[idx]["coarse_tag"]), str(rows[idx].get("source_kind", ""))),
            )[:20]
            handle.write(
                f"{rank}. `{cluster.anchor}`: {cluster.count} mentions "
                f"({cluster.count / total_count * 100.0:.4f}% full, {cluster.count / top500_count * 100.0:.4f}% top500), "
                f"{len(cluster.members)} tags, unweighted coherence {unweighted_internal_coherence(cluster, rows) * 100.0:.2f}%\n"
            )
            handle.write(
                "   - "
                + "; ".join(f"`{rows[idx]['coarse_tag']}` ({rows[idx]['count']})" for idx in top_members)
                + "\n"
            )


def main() -> None:
    all_rows, unvectorized, total_count = pairwise.load_intact_rows()
    rows = sorted(all_rows, key=lambda row: (-int(row["count"]), str(row["coarse_tag"])))[:TOP_N]
    clusters, log = run_fixed90(rows, total_count)
    write_outputs(rows, unvectorized, total_count, clusters, log)

    top500_count = sum(int(row["count"]) for row in rows)
    print(f"total={total_count}")
    print(f"top500_mentions={top500_count}")
    print(f"top500_pct={top500_count / total_count * 100.0:.4f}")
    print(f"passes={log[-1]['pass']}")
    print(f"clusters={len(clusters)}")
    print(f"top25_pct={sum(cluster.count for cluster in clusters[:25]) / total_count * 100.0:.4f}")
    print(f"summary={SUMMARY_OUT}")
    print(f"tag_map={TAG_MAP_OUT}")
    print(f"log={LOG_OUT}")
    print(f"report={REPORT_OUT}")


if __name__ == "__main__":
    main()
