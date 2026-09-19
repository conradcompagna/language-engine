from __future__ import annotations

import csv
from pathlib import Path

import cluster_all_labels_unweighted_centroid_internalcoherence89_intact as base
import cluster_all_labels_unweighted_centroid_internalcoherence89_to85_compact as compact
import cluster_coarse_tags_pairwise_member_purity90_cultural_modes as pairwise


BASE_DIR = Path(__file__).resolve().parent
OUT_DIR = compact.OUT_DIR

base.MAX_PASSES = 256


def load_existing_threshold(threshold: int, rows: list[dict[str, object]]) -> list[base.Cluster]:
    path = OUT_DIR / f"all_labels_unweighted_centroid_internalcoherence{threshold}_tag_map.tsv"
    tag_to_idx = {str(row["coarse_tag"]): idx for idx, row in enumerate(rows)}
    by_rank: dict[int, dict[str, object]] = {}
    with path.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            if row["cluster_rank"] == "UNVECTORIZED":
                continue
            tag = row["coarse_tag"]
            if tag not in tag_to_idx:
                continue
            rank = int(row["cluster_rank"])
            entry = by_rank.setdefault(rank, {"anchor": row["anchor_tag"], "members": []})
            entry["members"].append(tag_to_idx[tag])

    clusters = [
        compact.cluster_from_members(list(entry["members"]), rows, str(entry["anchor"]))
        for _rank, entry in sorted(by_rank.items())
    ]
    clusters.sort(key=lambda cluster: (-cluster.count, cluster.anchor))
    return clusters


def write_coverage_89_to80(
    thresholds: list[int],
    clusters_by_threshold: dict[int, list[base.Cluster]],
    rows: list[dict[str, object]],
    total_count: int,
) -> None:
    path = OUT_DIR / "all_labels_unweighted_centroid_internalcoherence89_to80_compact_coverage.md"
    vectorized_count = sum(int(row["count"]) for row in rows)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("# All Labels Unweighted Centroid Internal-Coherence 89-80 Coverage\n\n")
        handle.write("Compact reports show top 10 tags by frequency per cluster. Transitions list all tags newly added at each lower threshold.\n\n")
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
    rows, unvectorized, total_count = pairwise.load_intact_rows()
    all_thresholds = list(range(89, 79, -1))
    clusters_by_threshold: dict[int, list[base.Cluster]] = {}

    for threshold in range(89, 84, -1):
        clusters_by_threshold[threshold] = load_existing_threshold(threshold, rows)

    previous_threshold = 85
    previous_clusters = clusters_by_threshold[previous_threshold]
    for threshold in range(84, 79, -1):
        print(f"running threshold={threshold}", flush=True)
        base.THRESHOLD = threshold / 100.0
        clusters, _log = base.run(rows, total_count)
        clusters.sort(key=lambda cluster: (-cluster.count, cluster.anchor))
        clusters_by_threshold[threshold] = clusters
        compact.write_compact_report(threshold, clusters, rows, unvectorized, total_count)
        compact.write_transition(previous_threshold, threshold, previous_clusters, clusters, rows, total_count)
        print(f"threshold={threshold} clusters={len(clusters)}", flush=True)
        previous_threshold = threshold
        previous_clusters = clusters

    write_coverage_89_to80(all_thresholds, clusters_by_threshold, rows, total_count)
    print(f"out_dir={OUT_DIR}")
    print(f"coverage={OUT_DIR / 'all_labels_unweighted_centroid_internalcoherence89_to80_compact_coverage.md'}")


if __name__ == "__main__":
    main()
