from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import numpy as np

import cluster_coarse_tags_pairwise_member_purity90_cultural_modes as pairwise


BASE_DIR = Path(__file__).resolve().parent
OUT_DIR = BASE_DIR / "derived_fasttext_categories"

OVERVIEW_OUT = OUT_DIR / "coarse_top500_fixed_threshold_series_intact_overview.tsv"
CLUSTERS_OUT = OUT_DIR / "coarse_top500_fixed_threshold_series_intact_clusters.tsv"
LOG_OUT = OUT_DIR / "coarse_top500_fixed_threshold_series_intact_log.tsv"
REPORT_OUT = OUT_DIR / "coarse_top500_fixed_threshold_series_intact.md"

TOP_N = 500
THRESHOLDS = [0.85, 0.80, 0.75, 0.70, 0.65, 0.60, 0.55, 0.50]
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
    return [
        Cluster(
            members=[idx],
            vector_sum=row["vector"].astype(np.float32).copy(),
            vector=row["vector"].astype(np.float32).copy(),
            count=int(row["count"]),
            anchor=str(row["coarse_tag"]),
        )
        for idx, row in enumerate(rows)
    ]


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


def merge_pass(clusters: list[Cluster], rows: list[dict[str, object]], threshold: float) -> tuple[list[Cluster], int]:
    x = np.stack([cluster.vector for cluster in clusters]).astype(np.float32)
    sims = x @ x.T
    np.fill_diagonal(sims, -np.inf)

    pairs: list[tuple[float, int, int]] = []
    for left in range(len(clusters)):
        for right in range(left + 1, len(clusters)):
            similarity = float(sims[left, right])
            if similarity >= threshold:
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


def run_threshold(rows: list[dict[str, object]], total_count: int, threshold: float) -> tuple[list[Cluster], list[dict[str, object]]]:
    clusters = initial_clusters(rows)
    log = [
        {
            "threshold_pct": threshold * 100.0,
            "pass": 0,
            "clusters": len(clusters),
            "merged": "",
            "top25_pct": sum(cluster.count for cluster in sorted(clusters, key=lambda cluster: -cluster.count)[:25]) / total_count * 100.0,
        }
    ]

    for pass_num in range(1, MAX_PASSES + 1):
        previous_count = len(clusters)
        clusters, merged = merge_pass(clusters, rows, threshold)
        log.append(
            {
                "threshold_pct": threshold * 100.0,
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


def coverage(clusters: list[Cluster], total_count: int, top_n: int) -> float:
    return sum(cluster.count for cluster in clusters[:top_n]) / total_count * 100.0


def write_outputs(
    rows: list[dict[str, object]],
    total_count: int,
    results: list[tuple[float, list[Cluster], list[dict[str, object]]]],
) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    top500_count = sum(int(row["count"]) for row in rows)

    with OVERVIEW_OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
                "threshold_pct",
                "clusters",
                "passes",
                "top10_pct",
                "top25_pct",
                "top50_pct",
                "top100_pct",
                "top500_pct",
                "largest_anchor",
                "largest_pct_total",
                "largest_pct_top500",
                "largest_member_count",
                "largest_unweighted_coherence_pct",
                "largest_weighted_coherence_pct",
            ]
        )
        for threshold, clusters, log in results:
            largest = clusters[0]
            writer.writerow(
                [
                    f"{threshold * 100.0:.0f}",
                    len(clusters),
                    log[-1]["pass"],
                    f"{coverage(clusters, total_count, 10):.6f}",
                    f"{coverage(clusters, total_count, 25):.6f}",
                    f"{coverage(clusters, total_count, 50):.6f}",
                    f"{coverage(clusters, total_count, 100):.6f}",
                    f"{top500_count / total_count * 100.0:.6f}",
                    largest.anchor,
                    f"{largest.count / total_count * 100.0:.6f}",
                    f"{largest.count / top500_count * 100.0:.6f}",
                    len(largest.members),
                    f"{unweighted_internal_coherence(largest, rows) * 100.0:.2f}",
                    f"{weighted_internal_coherence(largest, rows) * 100.0:.2f}",
                ]
            )

    with CLUSTERS_OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
                "threshold_pct",
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
        for threshold, clusters, _log in results:
            for rank, cluster in enumerate(clusters, start=1):
                top_members = sorted(
                    cluster.members,
                    key=lambda idx: (-int(rows[idx]["count"]), str(rows[idx]["coarse_tag"]), str(rows[idx].get("source_kind", ""))),
                )[:50]
                writer.writerow(
                    [
                        f"{threshold * 100.0:.0f}",
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

    with LOG_OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["threshold_pct", "pass", "clusters", "merged", "top25_pct"],
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        for _threshold, _clusters, log in results:
            for entry in log:
                row = dict(entry)
                for key in ["threshold_pct", "top25_pct"]:
                    if isinstance(row.get(key), float):
                        row[key] = f"{row[key]:.6f}"
                writer.writerow(row)

    with REPORT_OUT.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("# Top-500 Fixed Threshold Series\n\n")
        handle.write(
            "This uses the 500 highest-frequency vectorized coarse tags. "
            "For each fixed threshold, it starts over from singleton tags, uses unweighted centroids, "
            "and repeatedly merges non-overlapping centroid pairs above that threshold until equilibrium. "
            "There is no threshold lowering inside a run and no forced target cluster count.\n\n"
        )
        handle.write(f"- Full total mentions: {total_count}\n")
        handle.write(f"- Top-500 mentions: {top500_count} ({top500_count / total_count * 100.0:.4f}% of full total)\n\n")
        handle.write("| threshold | clusters | top25 % | largest cluster |\n")
        handle.write("|---:|---:|---:|---|\n")
        for threshold, clusters, _log in results:
            largest = clusters[0]
            handle.write(
                f"| {threshold * 100.0:.0f}% | {len(clusters)} | {coverage(clusters, total_count, 25):.4f}% | "
                f"{largest.anchor} ({largest.count / total_count * 100.0:.4f}%) |\n"
            )
        handle.write("\n")


def main() -> None:
    all_rows, _unvectorized, total_count = pairwise.load_intact_rows()
    rows = sorted(all_rows, key=lambda row: (-int(row["count"]), str(row["coarse_tag"])))[:TOP_N]

    results = []
    for threshold in THRESHOLDS:
        clusters, log = run_threshold(rows, total_count, threshold)
        results.append((threshold, clusters, log))
        print(
            f"{threshold * 100.0:.0f}%: clusters={len(clusters)} passes={log[-1]['pass']} "
            f"top25_pct={coverage(clusters, total_count, 25):.4f} largest={clusters[0].anchor} "
            f"{clusters[0].count / total_count * 100.0:.4f}%"
        )

    write_outputs(rows, total_count, results)
    print(f"overview={OVERVIEW_OUT}")
    print(f"clusters={CLUSTERS_OUT}")
    print(f"log={LOG_OUT}")
    print(f"report={REPORT_OUT}")


if __name__ == "__main__":
    main()
