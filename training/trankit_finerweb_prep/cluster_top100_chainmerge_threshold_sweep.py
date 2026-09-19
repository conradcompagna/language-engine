from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import numpy as np

import cluster_all_labels_unweighted_centroid_internalcoherence89_intact as base
import cluster_all_labels_unweighted_centroid_internalcoherence89_to85_compact as compact
import cluster_all_labels_unweighted_centroid_internalcoherence90_to80_chainmerge_compact as chain
import cluster_coarse_tags_pairwise_member_purity90_cultural_modes as pairwise


BASE_DIR = Path(__file__).resolve().parent
SOURCE_DIR = BASE_DIR / "derived_fasttext_categories" / "all_labels_unweighted_centroid_internalcoherence90_to80_chainmerge_compact"
SOURCE_TAG_MAP = SOURCE_DIR / "all_labels_unweighted_centroid_internalcoherence100_tag_map.tsv"
OUT_DIR = SOURCE_DIR / "top100_chainmerge_100_to70"


@dataclass
class Item:
    source_rank: int
    anchor: str
    count: int
    vector: np.ndarray
    source_tags: list[str]


@dataclass
class MetaCluster:
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


def load_top100_items() -> tuple[list[Item], int]:
    rows, _unvectorized, total_count = pairwise.load_intact_rows()
    tag_to_idx = {str(row["coarse_tag"]): idx for idx, row in enumerate(rows)}
    by_rank: dict[int, dict[str, object]] = {}

    with SOURCE_TAG_MAP.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            if row["cluster_rank"] == "UNVECTORIZED":
                continue
            rank = int(row["cluster_rank"])
            if rank > 100:
                continue
            idx = tag_to_idx.get(row["coarse_tag"])
            if idx is None:
                continue
            entry = by_rank.setdefault(rank, {"anchor": row["anchor_tag"], "indices": [], "tags": []})
            entry["indices"].append(idx)
            entry["tags"].append(str(row["coarse_tag"]))

    items: list[Item] = []
    for rank, entry in sorted(by_rank.items()):
        indices = list(entry["indices"])
        vector_sum = np.zeros_like(rows[0]["vector"], dtype=np.float32)
        count = 0
        for idx in indices:
            vector_sum += rows[idx]["vector"].astype(np.float32)
            count += int(rows[idx]["count"])
        items.append(
            Item(
                source_rank=rank,
                anchor=str(entry["anchor"]),
                count=count,
                vector=normalize(vector_sum),
                source_tags=list(entry["tags"]),
            )
        )

    items.sort(key=lambda item: item.source_rank)
    return items, total_count


def initial_clusters(items: list[Item]) -> list[MetaCluster]:
    return [
        MetaCluster(
            members=[idx],
            vector_sum=item.vector.copy(),
            vector=item.vector.copy(),
            count=item.count,
            anchor=item.anchor,
        )
        for idx, item in enumerate(items)
    ]


def merge_clusters(left: MetaCluster, right: MetaCluster, items: list[Item]) -> MetaCluster:
    members = left.members + right.members
    vector_sum = left.vector_sum + right.vector_sum
    anchor_idx = max(members, key=lambda idx: (items[idx].count, items[idx].anchor))
    return MetaCluster(
        members=members,
        vector_sum=vector_sum,
        vector=normalize(vector_sum),
        count=left.count + right.count,
        anchor=items[anchor_idx].anchor,
    )


def internal_coherence(cluster: MetaCluster) -> float:
    if not cluster.members:
        return 1.0
    return float(np.linalg.norm(cluster.vector_sum) / len(cluster.members))


def proposed_coherence(left: MetaCluster, right: MetaCluster) -> float:
    members = len(left.members) + len(right.members)
    if not members:
        return 1.0
    return float(np.linalg.norm(left.vector_sum + right.vector_sum) / members)


def collect_pairs(clusters: list[MetaCluster], threshold: float) -> list[tuple[float, int, int]]:
    x = np.stack([cluster.vector for cluster in clusters]).astype(np.float32)
    sims = x @ x.T
    pairs: list[tuple[float, int, int]] = []
    for left in range(len(clusters)):
        for right in range(left + 1, len(clusters)):
            sim = float(sims[left, right])
            if sim >= threshold:
                pairs.append((sim, left, right))
    pairs.sort(reverse=True)
    return pairs


def find(parent: list[int], idx: int) -> int:
    while parent[idx] != idx:
        parent[idx] = parent[parent[idx]]
        idx = parent[idx]
    return idx


def merge_pass(
    clusters: list[MetaCluster],
    items: list[Item],
    threshold: float,
) -> tuple[list[MetaCluster], dict[str, object]]:
    pairs = collect_pairs(clusters, threshold)
    parent = list(range(len(clusters)))
    active = {idx: cluster for idx, cluster in enumerate(clusters)}
    accepted = 0
    similarity_blocked = 0
    coherence_blocked = 0

    for _sim, left_idx, right_idx in pairs:
        left_root = find(parent, left_idx)
        right_root = find(parent, right_idx)
        if left_root == right_root:
            continue
        left = active[left_root]
        right = active[right_root]
        current_sim = float(np.dot(left.vector, right.vector))
        if current_sim < threshold:
            similarity_blocked += 1
            continue
        current_coherence = proposed_coherence(left, right)
        if current_coherence < threshold:
            coherence_blocked += 1
            continue
        active[left_root] = merge_clusters(left, right, items)
        parent[right_root] = left_root
        del active[right_root]
        accepted += 1

    next_clusters = list(active.values())
    next_clusters.sort(key=lambda cluster: (-cluster.count, cluster.anchor))
    return next_clusters, {
        "candidate_pairs": len(pairs),
        "merged": accepted,
        "similarity_blocked": similarity_blocked,
        "coherence_blocked": coherence_blocked,
    }


def run_threshold(threshold_pct: int, items: list[Item]) -> tuple[list[MetaCluster], list[dict[str, object]]]:
    threshold = threshold_pct / 100.0
    clusters = initial_clusters(items)
    log: list[dict[str, object]] = []
    for pass_num in range(1, 256):
        previous = len(clusters)
        clusters, stats = merge_pass(clusters, items, threshold)
        log.append({"pass": pass_num, "clusters": len(clusters), **stats})
        if stats["merged"] == 0 or len(clusters) == previous:
            break
    clusters.sort(key=lambda cluster: (-cluster.count, cluster.anchor))
    return clusters, log


def item_text(idx: int, items: list[Item]) -> str:
    item = items[idx]
    return f"{item.source_rank}. {item.anchor} ({item.count})"


def write_report(
    threshold: int,
    clusters: list[MetaCluster],
    log: list[dict[str, object]],
    items: list[Item],
    total_count: int,
) -> None:
    report = OUT_DIR / f"top100_chainmerge_{threshold}.md"
    summary = OUT_DIR / f"top100_chainmerge_{threshold}_summary.tsv"
    tag_map = OUT_DIR / f"top100_chainmerge_{threshold}_map.tsv"

    with report.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(f"# Top 100 Source Categories Chain-Merge {threshold}%\n\n")
        handle.write(
            "Input items are the corpus-wide top 100 clusters from the full-label 100% chain-merge report. "
            "This reclusters only those 100 category centroids. Merge gate uses current centroid similarity "
            f"and proposed unweighted internal coherence >= {threshold}%.\n\n"
        )
        handle.write(f"- Output clusters: {len(clusters)}\n")
        handle.write(f"- Source mention mass: {sum(item.count for item in items):,} ({sum(item.count for item in items) / total_count * 100.0:.4f}% of full corpus)\n\n")
        handle.write("## Pass Log\n\n")
        for entry in log:
            handle.write(
                f"- pass {entry['pass']}: {entry['clusters']} clusters, merged {entry['merged']}, "
                f"candidate pairs {entry['candidate_pairs']}, sim blocked {entry['similarity_blocked']}, "
                f"coherence blocked {entry['coherence_blocked']}\n"
            )
        handle.write("\n## Clusters\n\n")
        for rank, cluster in enumerate(clusters, start=1):
            members = sorted(cluster.members, key=lambda idx: (items[idx].source_rank, items[idx].anchor))
            handle.write(
                f"{rank}. `{cluster.anchor}`: {cluster.count:,} mentions "
                f"({cluster.count / total_count * 100.0:.4f}% full), {len(members)} source categories, "
                f"coherence {internal_coherence(cluster) * 100.0:.2f}%\n"
            )
            handle.write("   - " + "; ".join(f"`{item_text(idx, items)}`" for idx in members) + "\n")

    with summary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["threshold", "rank", "anchor", "source_category_count", "mention_count", "pct_full_total", "coherence_pct", "source_categories"])
        for rank, cluster in enumerate(clusters, start=1):
            members = sorted(cluster.members, key=lambda idx: (items[idx].source_rank, items[idx].anchor))
            writer.writerow(
                [
                    threshold,
                    rank,
                    cluster.anchor,
                    len(members),
                    cluster.count,
                    f"{cluster.count / total_count * 100.0:.6f}",
                    f"{internal_coherence(cluster) * 100.0:.2f}",
                    "; ".join(item_text(idx, items) for idx in members),
                ]
            )

    with tag_map.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(["threshold", "output_rank", "output_anchor", "source_rank", "source_anchor", "source_count"])
        for rank, cluster in enumerate(clusters, start=1):
            for idx in sorted(cluster.members, key=lambda member_idx: items[member_idx].source_rank):
                item = items[idx]
                writer.writerow([threshold, rank, cluster.anchor, item.source_rank, item.anchor, item.count])


def write_coverage(
    thresholds: list[int],
    clusters_by_threshold: dict[int, list[MetaCluster]],
    items: list[Item],
    total_count: int,
) -> None:
    path = OUT_DIR / "top100_chainmerge_100_to70_coverage.md"
    source_mass = sum(item.count for item in items)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("# Top 100 Source Categories Chain-Merge 100-70 Coverage\n\n")
        handle.write(f"- Source categories: {len(items)}\n")
        handle.write(f"- Source mention mass: {source_mass:,} ({source_mass / total_count * 100.0:.4f}% of full corpus)\n\n")
        handle.write("| Threshold | Output clusters | Largest cluster % full | Largest cluster source categories | Min coherence |\n")
        handle.write("| ---: | ---: | ---: | ---: | ---: |\n")
        for threshold in thresholds:
            clusters = clusters_by_threshold[threshold]
            largest = clusters[0]
            min_coh = min(internal_coherence(cluster) for cluster in clusters) * 100.0
            handle.write(
                f"| {threshold}% | {len(clusters)} | {largest.count / total_count * 100.0:.4f}% | "
                f"{len(largest.members)} | {min_coh:.2f}% |\n"
            )


def write_combined_report(
    thresholds: list[int],
    clusters_by_threshold: dict[int, list[MetaCluster]],
    logs_by_threshold: dict[int, list[dict[str, object]]],
    items: list[Item],
    total_count: int,
) -> None:
    path = OUT_DIR / "top100_chainmerge_100_to70_full.md"
    source_mass = sum(item.count for item in items)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("# Top 100 Source Categories Chain-Merge 100-70 Full Report\n\n")
        handle.write(
            "Input items are the corpus-wide top 100 clusters from the full-label 100% chain-merge report. "
            "This reclusters only those 100 category centroids. At each threshold, a merge requires current "
            "centroid similarity and proposed unweighted internal coherence to both meet the threshold. "
            "Frequency is reporting-only.\n\n"
        )
        handle.write(f"- Source categories: {len(items)}\n")
        handle.write(f"- Source mention mass: {source_mass:,} ({source_mass / total_count * 100.0:.4f}% of full corpus)\n\n")

        handle.write("## Summary\n\n")
        handle.write("| Threshold | Output clusters | Largest cluster % full | Largest cluster categories | Min coherence |\n")
        handle.write("| ---: | ---: | ---: | ---: | ---: |\n")
        for threshold in thresholds:
            clusters = clusters_by_threshold[threshold]
            largest = clusters[0]
            min_coh = min(internal_coherence(cluster) for cluster in clusters) * 100.0
            handle.write(
                f"| {threshold}% | {len(clusters)} | {largest.count / total_count * 100.0:.4f}% | "
                f"{len(largest.members)} | {min_coh:.2f}% |\n"
            )

        for threshold in thresholds:
            clusters = clusters_by_threshold[threshold]
            handle.write(f"\n## {threshold}%\n\n")
            handle.write(
                f"- Output clusters: {len(clusters)}\n"
                f"- Merge passes: {len(logs_by_threshold[threshold])}\n"
                f"- Min coherence: {min(internal_coherence(cluster) for cluster in clusters) * 100.0:.2f}%\n\n"
            )
            for rank, cluster in enumerate(clusters, start=1):
                members = sorted(cluster.members, key=lambda idx: (items[idx].source_rank, items[idx].anchor))
                handle.write(
                    f"{rank}. `{cluster.anchor}`: {cluster.count:,} mentions "
                    f"({cluster.count / total_count * 100.0:.4f}% full), "
                    f"{len(members)} source categories, coherence {internal_coherence(cluster) * 100.0:.2f}%\n"
                )
                handle.write("   - " + "; ".join(f"`{item_text(idx, items)}`" for idx in members) + "\n")


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    items, total_count = load_top100_items()
    thresholds = list(range(100, 69, -1))
    clusters_by_threshold: dict[int, list[MetaCluster]] = {}
    logs_by_threshold: dict[int, list[dict[str, object]]] = {}
    for threshold in thresholds:
        print(f"running threshold={threshold}", flush=True)
        clusters, log = run_threshold(threshold, items)
        clusters_by_threshold[threshold] = clusters
        logs_by_threshold[threshold] = log
        print(f"threshold={threshold} clusters={len(clusters)}", flush=True)
    write_coverage(thresholds, clusters_by_threshold, items, total_count)
    write_combined_report(thresholds, clusters_by_threshold, logs_by_threshold, items, total_count)
    print(f"out_dir={OUT_DIR}")


if __name__ == "__main__":
    main()
