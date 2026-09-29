from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

import cluster_all_labels_unweighted_centroid_internalcoherence89_intact as base
import cluster_all_labels_unweighted_centroid_internalcoherence89_to85_compact as compact
import cluster_coarse_tags_pairwise_member_purity90_cultural_modes as pairwise


BASE_DIR = Path(__file__).resolve().parent
OUT_DIR = BASE_DIR / "derived_fasttext_categories" / "all_labels_unweighted_centroid_internalcoherence90_to80_chainmerge_compact"

base.MAX_PASSES = 256


def find(parent: list[int], idx: int) -> int:
    while parent[idx] != idx:
        parent[idx] = parent[parent[idx]]
        idx = parent[idx]
    return idx


def chain_merge_pass(
    clusters: list[base.Cluster],
    rows: list[dict[str, object]],
    threshold: float,
) -> tuple[list[base.Cluster], dict[str, object]]:
    pairs = base.collect_candidate_pairs(clusters)
    parent = list(range(len(clusters)))
    active: dict[int, base.Cluster] = {idx: cluster for idx, cluster in enumerate(clusters)}

    accepted = 0
    stale_similarity_blocked = 0
    coherence_blocked = 0
    skipped_same_component = 0
    worst_accepted_similarity = 1.0
    worst_accepted_coherence = 1.0
    best_blocked_similarity = -np.inf
    best_blocked_coherence = -np.inf

    for _original_similarity, left_idx, right_idx in pairs:
        left_root = find(parent, left_idx)
        right_root = find(parent, right_idx)
        if left_root == right_root:
            skipped_same_component += 1
            continue

        left = active[left_root]
        right = active[right_root]
        current_similarity = float(np.dot(left.vector, right.vector))
        if current_similarity < threshold:
            stale_similarity_blocked += 1
            best_blocked_similarity = max(best_blocked_similarity, current_similarity)
            continue

        coherence = base.proposed_unweighted_coherence(left, right)
        if coherence < threshold:
            coherence_blocked += 1
            best_blocked_similarity = max(best_blocked_similarity, current_similarity)
            best_blocked_coherence = max(best_blocked_coherence, coherence)
            continue

        merged = base.merge_clusters(left, right, rows)
        parent[right_root] = left_root
        active[left_root] = merged
        del active[right_root]
        accepted += 1
        worst_accepted_similarity = min(worst_accepted_similarity, current_similarity)
        worst_accepted_coherence = min(worst_accepted_coherence, coherence)

    next_clusters = list(active.values())
    next_clusters.sort(key=lambda cluster: (cluster.anchor, len(cluster.members), cluster.count))
    return next_clusters, {
        "candidate_pairs": len(pairs),
        "merged": accepted,
        "stale_similarity_blocked": stale_similarity_blocked,
        "coherence_blocked": coherence_blocked,
        "skipped_same_component": skipped_same_component,
        "worst_accepted_similarity": worst_accepted_similarity,
        "worst_accepted_coherence": worst_accepted_coherence,
        "best_blocked_similarity": best_blocked_similarity,
        "best_blocked_coherence": best_blocked_coherence,
    }


def run_threshold(
    threshold_pct: int,
    rows: list[dict[str, object]],
    total_count: int,
) -> tuple[list[base.Cluster], list[dict[str, object]]]:
    threshold = threshold_pct / 100.0
    base.THRESHOLD = threshold
    clusters = base.initial_clusters(rows)
    log: list[dict[str, object]] = []

    for pass_num in range(1, base.MAX_PASSES + 1):
        previous_count = len(clusters)
        clusters, stats = chain_merge_pass(clusters, rows, threshold)
        ranked = sorted(clusters, key=lambda cluster: (-cluster.count, cluster.anchor))
        log.append(
            {
                "pass": pass_num,
                "clusters": len(clusters),
                "top100_pct": sum(cluster.count for cluster in ranked[:100]) / total_count * 100.0,
                **stats,
            }
        )
        print(
            f"threshold={threshold_pct} pass={pass_num} clusters={len(clusters)} "
            f"merged={stats['merged']} candidates={stats['candidate_pairs']}",
            flush=True,
        )
        if stats["merged"] == 0 or len(clusters) == previous_count:
            break

    clusters.sort(key=lambda cluster: (-cluster.count, cluster.anchor))
    return clusters, log


def write_log(threshold: int, log: list[dict[str, object]]) -> None:
    path = OUT_DIR / f"all_labels_unweighted_centroid_internalcoherence{threshold}_chainmerge_log.tsv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "pass",
                "clusters",
                "top100_pct",
                "candidate_pairs",
                "merged",
                "stale_similarity_blocked",
                "coherence_blocked",
                "skipped_same_component",
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
            row["top100_pct"] = f"{float(row['top100_pct']):.6f}"
            for key in [
                "worst_accepted_similarity",
                "worst_accepted_coherence",
                "best_blocked_similarity",
                "best_blocked_coherence",
            ]:
                value = row.get(key)
                if isinstance(value, float) and np.isfinite(value):
                    row[key] = f"{value * 100.0:.6f}"
                elif isinstance(value, float):
                    row[key] = ""
            writer.writerow(row)


def write_coverage(
    thresholds: list[int],
    clusters_by_threshold: dict[int, list[base.Cluster]],
    rows: list[dict[str, object]],
    total_count: int,
) -> None:
    path = OUT_DIR / "all_labels_unweighted_centroid_internalcoherence90_to80_chainmerge_coverage.md"
    vectorized_count = sum(int(row["count"]) for row in rows)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("# All Labels Unweighted Centroid Internal-Coherence 90-80 Chain-Merge Coverage\n\n")
        handle.write(
            "Full vectorized label set. `cultural reference` is intact. "
            "Centroids are unweighted means of member tag vectors. "
            "Within each pass, accepted merges update the component centroid immediately, "
            "so a cluster can keep merging in the same pass as long as current centroid similarity "
            "and proposed merged-cluster unweighted coherence both remain at or above that threshold. "
            "Frequency is reporting-only.\n\n"
        )
        handle.write(f"- Total mentions: {total_count}\n")
        handle.write(f"- Vectorized mention mass: {vectorized_count} ({vectorized_count / total_count * 100.0:.4f}% of total)\n\n")
        handle.write("| Threshold | Final clusters | Top-10 % total | Top-100 % total | Min unweighted coherence |\n")
        handle.write("| ---: | ---: | ---: | ---: | ---: |\n")
        for threshold in thresholds:
            clusters = clusters_by_threshold[threshold]
            top10_count = sum(cluster.count for cluster in clusters[:10])
            top100_count = sum(cluster.count for cluster in clusters[:100])
            min_coherence = min(base.unweighted_internal_coherence(cluster) for cluster in clusters) * 100.0
            handle.write(
                f"| {threshold}% | {len(clusters)} | {top10_count / total_count * 100.0:.4f}% | "
                f"{top100_count / total_count * 100.0:.4f}% | {min_coherence:.2f}% |\n"
            )


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    compact.OUT_DIR = OUT_DIR

    rows, unvectorized, total_count = pairwise.load_intact_rows()
    thresholds = list(range(90, 79, -1))
    clusters_by_threshold: dict[int, list[base.Cluster]] = {}

    for threshold in thresholds:
        print(f"running threshold={threshold}", flush=True)
        clusters, log = run_threshold(threshold, rows, total_count)
        clusters_by_threshold[threshold] = clusters
        compact.write_compact_report(threshold, clusters, rows, unvectorized, total_count)
        write_log(threshold, log)
        print(f"threshold={threshold} clusters={len(clusters)}", flush=True)

    for previous_threshold, current_threshold in zip(thresholds, thresholds[1:]):
        compact.write_transition(
            previous_threshold,
            current_threshold,
            clusters_by_threshold[previous_threshold],
            clusters_by_threshold[current_threshold],
            rows,
            total_count,
        )

    write_coverage(thresholds, clusters_by_threshold, rows, total_count)
    print(f"out_dir={OUT_DIR}")


if __name__ == "__main__":
    main()
