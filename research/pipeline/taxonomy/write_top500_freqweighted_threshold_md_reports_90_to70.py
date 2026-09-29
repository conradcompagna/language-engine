from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import numpy as np

import cluster_coarse_tags_pairwise_member_purity90_cultural_modes as pairwise


BASE_DIR = Path(__file__).resolve().parent
OUT_DIR = BASE_DIR / "derived_fasttext_categories" / "top500_freqweighted_threshold_reports_90_to70"
OVERVIEW_MD = OUT_DIR / "README.md"
OVERVIEW_TSV = OUT_DIR / "overview.tsv"

TOP_N = 500
THRESHOLDS = [value / 100.0 for value in range(90, 69, -1)]
MAX_PASSES = 64
TOP_TAGS_PER_CLUSTER = 20


@dataclass
class Cluster:
    members: list[int]
    weighted_vector_sum: np.ndarray
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
        count = int(row["count"])
        weighted_vector_sum = row["vector"].astype(np.float32) * float(count)
        clusters.append(
            Cluster(
                members=[idx],
                weighted_vector_sum=weighted_vector_sum,
                vector=normalize(weighted_vector_sum),
                count=count,
                anchor=str(row["coarse_tag"]),
            )
        )
    return clusters


def merge_clusters(left: Cluster, right: Cluster, rows: list[dict[str, object]]) -> Cluster:
    members = left.members + right.members
    weighted_vector_sum = left.weighted_vector_sum + right.weighted_vector_sum
    anchor_idx = max(members, key=lambda idx: (int(rows[idx]["count"]), str(rows[idx]["coarse_tag"])))
    return Cluster(
        members=members,
        weighted_vector_sum=weighted_vector_sum,
        vector=normalize(weighted_vector_sum),
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
    merge_pairs: list[tuple[int, int]] = []
    new_clusters: list[Cluster] = []

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


def top_tags(cluster: Cluster, rows: list[dict[str, object]]) -> list[str]:
    ordered = sorted(
        cluster.members,
        key=lambda idx: (-int(rows[idx]["count"]), str(rows[idx]["coarse_tag"]), str(rows[idx].get("source_kind", ""))),
    )[:TOP_TAGS_PER_CLUSTER]
    return [f"{rows[idx]['coarse_tag']} ({rows[idx]['count']})" for idx in ordered]


def write_threshold_report(
    threshold: float,
    clusters: list[Cluster],
    log: list[dict[str, object]],
    rows: list[dict[str, object]],
    total_count: int,
    top500_count: int,
) -> Path:
    threshold_pct = int(round(threshold * 100.0))
    path = OUT_DIR / f"threshold_{threshold_pct:02d}.md"
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(f"# Top-500 Frequency-Weighted Fixed {threshold_pct}% Threshold\n\n")
        handle.write(
            "Centroids are frequency-weighted: `normalize(sum(tag_vector * tag_frequency))`. "
            "This run starts from the same top-500 frequency tags and repeatedly merges "
            f"non-overlapping centroid pairs with cosine similarity >= {threshold_pct}% until equilibrium. "
            "There is no forced collapse target.\n\n"
        )
        handle.write("## Summary\n\n")
        handle.write(f"- Threshold: {threshold_pct}%\n")
        handle.write(f"- Final clusters: {len(clusters)}\n")
        handle.write(f"- Passes: {log[-1]['pass']}\n")
        handle.write(f"- Top-10 coverage: {coverage(clusters, total_count, 10):.4f}% of full total\n")
        handle.write(f"- Top-25 coverage: {coverage(clusters, total_count, 25):.4f}% of full total\n")
        handle.write(f"- Top-50 coverage: {coverage(clusters, total_count, 50):.4f}% of full total\n")
        handle.write(f"- Top-500 selected coverage: {top500_count / total_count * 100.0:.4f}% of full total\n\n")

        handle.write("## Pass Log\n\n")
        handle.write("| pass | clusters | merged | top25 % full |\n")
        handle.write("|---:|---:|---:|---:|\n")
        for entry in log:
            merged = entry["merged"] if entry["merged"] != "" else ""
            handle.write(
                f"| {entry['pass']} | {entry['clusters']} | {merged} | "
                f"{float(entry['top25_pct']):.4f}% |\n"
            )
        handle.write("\n")

        handle.write("## Clusters\n\n")
        for rank, cluster in enumerate(clusters, start=1):
            handle.write(f"### {rank}. {cluster.anchor}\n\n")
            handle.write(
                f"{cluster.count} mentions "
                f"({cluster.count / total_count * 100.0:.4f}% full, "
                f"{cluster.count / top500_count * 100.0:.4f}% top500), "
                f"{len(cluster.members)} tags, "
                f"unweighted coherence {unweighted_internal_coherence(cluster, rows) * 100.0:.2f}%, "
                f"weighted coherence {weighted_internal_coherence(cluster, rows) * 100.0:.2f}%\n\n"
            )
            for tag in top_tags(cluster, rows):
                handle.write(f"- {tag}\n")
            handle.write("\n")
    return path


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    all_rows, _unvectorized, total_count = pairwise.load_intact_rows()
    rows = sorted(all_rows, key=lambda row: (-int(row["count"]), str(row["coarse_tag"])))[:TOP_N]
    top500_count = sum(int(row["count"]) for row in rows)

    overview_rows: list[dict[str, object]] = []
    report_paths: list[tuple[int, Path]] = []

    for threshold in THRESHOLDS:
        clusters, log = run_threshold(rows, total_count, threshold)
        threshold_pct = int(round(threshold * 100.0))
        path = write_threshold_report(threshold, clusters, log, rows, total_count, top500_count)
        report_paths.append((threshold_pct, path))
        largest = clusters[0]
        overview_rows.append(
            {
                "threshold_pct": threshold_pct,
                "clusters": len(clusters),
                "passes": log[-1]["pass"],
                "top10_pct": f"{coverage(clusters, total_count, 10):.6f}",
                "top25_pct": f"{coverage(clusters, total_count, 25):.6f}",
                "top50_pct": f"{coverage(clusters, total_count, 50):.6f}",
                "largest_anchor": largest.anchor,
                "largest_pct_total": f"{largest.count / total_count * 100.0:.6f}",
                "largest_member_count": len(largest.members),
                "largest_unweighted_coherence_pct": f"{unweighted_internal_coherence(largest, rows) * 100.0:.2f}",
                "largest_weighted_coherence_pct": f"{weighted_internal_coherence(largest, rows) * 100.0:.2f}",
            }
        )
        print(
            f"{threshold_pct}%: clusters={len(clusters)} passes={log[-1]['pass']} "
            f"top25={coverage(clusters, total_count, 25):.4f}% "
            f"largest={largest.anchor} {largest.count / total_count * 100.0:.4f}% "
            f"weighted_coh={weighted_internal_coherence(largest, rows) * 100.0:.2f}%"
        )

    with OVERVIEW_TSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "threshold_pct",
                "clusters",
                "passes",
                "top10_pct",
                "top25_pct",
                "top50_pct",
                "largest_anchor",
                "largest_pct_total",
                "largest_member_count",
                "largest_unweighted_coherence_pct",
                "largest_weighted_coherence_pct",
            ],
            delimiter="\t",
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(overview_rows)

    with OVERVIEW_MD.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("# Top-500 Frequency-Weighted Threshold Reports, 90% To 70%\n\n")
        handle.write(
            "Each file is a separate fixed-threshold run from the same top-500 frequency tag set. "
            "Centroids are frequency-weighted. No threshold lowering happens inside a report, "
            "and no target cluster count is forced.\n\n"
        )
        handle.write("| threshold | clusters | top25 % | largest cluster | weighted coherence | report |\n")
        handle.write("|---:|---:|---:|---|---:|---|\n")
        by_threshold = {row["threshold_pct"]: row for row in overview_rows}
        for threshold_pct, path in report_paths:
            row = by_threshold[threshold_pct]
            rel = path.name
            handle.write(
                f"| {threshold_pct}% | {row['clusters']} | {float(row['top25_pct']):.4f}% | "
                f"{row['largest_anchor']} ({float(row['largest_pct_total']):.4f}%) | "
                f"{float(row['largest_weighted_coherence_pct']):.2f}% | "
                f"[{rel}]({rel}) |\n"
            )

    print(f"reports_dir={OUT_DIR}")
    print(f"overview_md={OVERVIEW_MD}")
    print(f"overview_tsv={OVERVIEW_TSV}")


if __name__ == "__main__":
    main()
