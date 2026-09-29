from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

import cluster_all_labels_unweighted_centroid_internalcoherence89_intact as base
import cluster_coarse_tags_pairwise_member_purity90_cultural_modes as pairwise


BASE_DIR = Path(__file__).resolve().parent
OUT_DIR = BASE_DIR / "derived_fasttext_categories" / "all_labels_unweighted_centroid_internalcoherence89_to85_compact"
SOURCE_89_TAG_MAP = (
    BASE_DIR
    / "derived_fasttext_categories"
    / "all_labels_unweighted_centroid_internalcoherence89"
    / "all_labels_unweighted_centroid_internalcoherence89_intact_tag_map.tsv"
)

base.MAX_PASSES = 256


def cluster_from_members(members: list[int], rows: list[dict[str, object]], anchor: str) -> base.Cluster:
    vector_sum = np.zeros_like(rows[0]["vector"], dtype=np.float32)
    count = 0
    for idx in members:
        vector_sum += rows[idx]["vector"].astype(np.float32)
        count += int(rows[idx]["count"])
    return base.Cluster(
        members=members,
        vector_sum=vector_sum,
        vector=base.normalize(vector_sum),
        count=count,
        anchor=anchor,
    )


def load_existing_89(rows: list[dict[str, object]]) -> list[base.Cluster]:
    tag_to_idx = {str(row["coarse_tag"]): idx for idx, row in enumerate(rows)}
    by_rank: dict[int, dict[str, object]] = {}
    with SOURCE_89_TAG_MAP.open("r", encoding="utf-8", newline="") as handle:
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
        cluster_from_members(list(entry["members"]), rows, str(entry["anchor"]))
        for _rank, entry in sorted(by_rank.items())
    ]
    clusters.sort(key=lambda cluster: (-cluster.count, cluster.anchor))
    return clusters


def run_threshold(threshold: int, rows: list[dict[str, object]], total_count: int) -> list[base.Cluster]:
    if threshold == 89 and SOURCE_89_TAG_MAP.exists():
        return load_existing_89(rows)
    base.THRESHOLD = threshold / 100.0
    clusters, _log = base.run(rows, total_count)
    clusters.sort(key=lambda cluster: (-cluster.count, cluster.anchor))
    return clusters


def top_members(cluster: base.Cluster, rows: list[dict[str, object]], limit: int = 10) -> list[int]:
    return sorted(cluster.members, key=lambda idx: (-int(rows[idx]["count"]), str(rows[idx]["coarse_tag"])))[:limit]


def all_members_by_freq(cluster: base.Cluster, rows: list[dict[str, object]]) -> list[int]:
    return sorted(cluster.members, key=lambda idx: (-int(rows[idx]["count"]), str(rows[idx]["coarse_tag"])))


def tag_text(idx: int, rows: list[dict[str, object]]) -> str:
    return f"{rows[idx]['coarse_tag']} ({rows[idx]['count']})"


def write_compact_report(
    threshold: int,
    clusters: list[base.Cluster],
    rows: list[dict[str, object]],
    unvectorized: list[dict[str, object]],
    total_count: int,
) -> None:
    report = OUT_DIR / f"all_labels_unweighted_centroid_internalcoherence{threshold}_compact.md"
    summary = OUT_DIR / f"all_labels_unweighted_centroid_internalcoherence{threshold}_compact_summary.tsv"
    tag_map = OUT_DIR / f"all_labels_unweighted_centroid_internalcoherence{threshold}_tag_map.tsv"

    top10_count = sum(cluster.count for cluster in clusters[:10])
    top100_count = sum(cluster.count for cluster in clusters[:100])
    vectorized_count = sum(int(row["count"]) for row in rows)

    with report.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(f"# All Labels Unweighted Centroid Internal-Coherence {threshold}% Compact Report\n\n")
        handle.write(
            "Full vectorized label set. `cultural reference` is intact. "
            "Centroids are unweighted means of member tag vectors. "
            f"Merges require centroid-pair similarity >= {threshold}% and proposed merged-cluster "
            f"unweighted internal coherence >= {threshold}%. Frequency is reporting-only.\n\n"
        )
        handle.write(f"- Total mentions: {total_count}\n")
        handle.write(f"- Vectorized rows: {len(rows)}\n")
        handle.write(f"- Vectorized mention mass: {vectorized_count} ({vectorized_count / total_count * 100.0:.4f}% of total)\n")
        handle.write(f"- Unvectorized rows: {len(unvectorized)}\n")
        handle.write(f"- Final clusters: {len(clusters)}\n")
        handle.write(f"- Top-10 coverage: {top10_count / total_count * 100.0:.4f}%\n")
        handle.write(f"- Top-100 coverage: {top100_count / total_count * 100.0:.4f}%\n\n")
        handle.write("## Clusters\n\n")
        for rank, cluster in enumerate(clusters, start=1):
            handle.write(
                f"{rank}. `{cluster.anchor}`: {cluster.count} mentions "
                f"({cluster.count / total_count * 100.0:.4f}%), {len(cluster.members)} tags, "
                f"unweighted coherence {base.unweighted_internal_coherence(cluster) * 100.0:.2f}%\n"
            )
            handle.write("   - " + "; ".join(f"`{tag_text(idx, rows)}`" for idx in top_members(cluster, rows)) + "\n")

    with summary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
                "threshold_pct",
                "cluster_rank",
                "anchor_tag",
                "member_count",
                "mention_count",
                "pct_total",
                "unweighted_internal_coherence_pct",
                "top10_tags",
            ]
        )
        for rank, cluster in enumerate(clusters, start=1):
            writer.writerow(
                [
                    threshold,
                    rank,
                    cluster.anchor,
                    len(cluster.members),
                    cluster.count,
                    f"{cluster.count / total_count * 100.0:.6f}",
                    f"{base.unweighted_internal_coherence(cluster) * 100.0:.2f}",
                    "; ".join(tag_text(idx, rows) for idx in top_members(cluster, rows)),
                ]
            )

    with tag_map.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["coarse_tag", "count", "pct_total", "cluster_rank", "anchor_tag", "centroid_similarity_pct"])
        for rank, cluster in enumerate(clusters, start=1):
            for idx in all_members_by_freq(cluster, rows):
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


def previous_cluster_lookup(clusters: list[base.Cluster]) -> dict[int, base.Cluster]:
    lookup = {}
    for cluster in clusters:
        for idx in cluster.members:
            lookup[idx] = cluster
    return lookup


def write_transition(
    previous_threshold: int,
    current_threshold: int,
    previous: list[base.Cluster],
    current: list[base.Cluster],
    rows: list[dict[str, object]],
    total_count: int,
) -> None:
    report = OUT_DIR / f"added_tags_{previous_threshold}_to_{current_threshold}.md"
    tsv = OUT_DIR / f"added_tags_{previous_threshold}_to_{current_threshold}.tsv"
    previous_by_member = previous_cluster_lookup(previous)

    additions_by_cluster: list[tuple[int, base.Cluster, list[int]]] = []
    for rank, cluster in enumerate(current, start=1):
        anchor_idx = max(cluster.members, key=lambda idx: (int(rows[idx]["count"]), str(rows[idx]["coarse_tag"])))
        previous_anchor_cluster = previous_by_member[anchor_idx]
        previous_members = set(previous_anchor_cluster.members)
        added = [idx for idx in all_members_by_freq(cluster, rows) if idx not in previous_members]
        if added:
            additions_by_cluster.append((rank, cluster, added))

    with report.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(f"# Tags Added When Lowering {previous_threshold}% to {current_threshold}%\n\n")
        handle.write(
            "For each current cluster, this lists every tag that was not in that cluster anchor's "
            f"{previous_threshold}% cluster and was absorbed at {current_threshold}%.\n\n"
        )
        for rank, cluster, added in additions_by_cluster:
            added_count = sum(int(rows[idx]["count"]) for idx in added)
            handle.write(
                f"## {rank}. `{cluster.anchor}`\n\n"
                f"- Cluster mentions: {cluster.count} ({cluster.count / total_count * 100.0:.4f}%)\n"
                f"- Added tags: {len(added)}\n"
                f"- Added mention mass: {added_count} ({added_count / total_count * 100.0:.4f}%)\n\n"
            )
            for idx in added:
                handle.write(f"- {tag_text(idx, rows)}\n")
            handle.write("\n")

    with tsv.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
                "from_threshold_pct",
                "to_threshold_pct",
                "current_cluster_rank",
                "current_anchor_tag",
                "added_tag",
                "added_tag_count",
                "added_tag_pct_total",
            ]
        )
        for rank, cluster, added in additions_by_cluster:
            for idx in added:
                writer.writerow(
                    [
                        previous_threshold,
                        current_threshold,
                        rank,
                        cluster.anchor,
                        rows[idx]["coarse_tag"],
                        rows[idx]["count"],
                        f"{rows[idx]['percent']:.6f}",
                    ]
                )


def write_coverage(
    thresholds: list[int],
    clusters_by_threshold: dict[int, list[base.Cluster]],
    rows: list[dict[str, object]],
    total_count: int,
) -> None:
    path = OUT_DIR / "all_labels_unweighted_centroid_internalcoherence89_to85_compact_coverage.md"
    vectorized_count = sum(int(row["count"]) for row in rows)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("# All Labels Unweighted Centroid Internal-Coherence 89-85 Coverage\n\n")
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
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    rows, unvectorized, total_count = pairwise.load_intact_rows()
    thresholds = [89, 88, 87, 86, 85]
    clusters_by_threshold: dict[int, list[base.Cluster]] = {}

    for threshold in thresholds:
        print(f"running threshold={threshold}", flush=True)
        clusters = run_threshold(threshold, rows, total_count)
        clusters_by_threshold[threshold] = clusters
        write_compact_report(threshold, clusters, rows, unvectorized, total_count)
        print(f"threshold={threshold} clusters={len(clusters)}", flush=True)

    for previous_threshold, current_threshold in zip(thresholds, thresholds[1:]):
        write_transition(
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
