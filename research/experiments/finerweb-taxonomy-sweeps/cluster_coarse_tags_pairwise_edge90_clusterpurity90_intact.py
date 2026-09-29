from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import numpy as np

import cluster_coarse_tags_pairwise_member_purity90_cultural_modes as pairwise


BASE_DIR = Path(__file__).resolve().parent
OUT_DIR = BASE_DIR / "derived_fasttext_categories"

SUMMARY_OUT = OUT_DIR / "coarse_pairwise_edge90_clusterpurity90_intact_summary.tsv"
TAG_MAP_OUT = OUT_DIR / "coarse_pairwise_edge90_clusterpurity90_intact_tag_map.tsv"
REPORT_OUT = OUT_DIR / "coarse_pairwise_edge90_clusterpurity90_intact.md"

EDGE_THRESHOLD = 0.90
PURITY_THRESHOLD = 0.90
BLOCK_SIZE = 256


@dataclass
class MergeStats:
    candidate_edges: int = 0
    accepted_merges: int = 0
    skipped_same_cluster: int = 0
    rejected_purity: int = 0
    worst_accepted_purity: float = 1.0
    best_rejected_purity: float = 0.0


class DynamicClusters:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.parent = list(range(len(rows)))
        self.clusters: list[pairwise.PairwiseCluster | None] = [
            pairwise.make_singleton(idx, rows) for idx in range(len(rows))
        ]
        self.active_roots = set(range(len(rows)))

    def find(self, item: int) -> int:
        root = item
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[item] != item:
            parent = self.parent[item]
            self.parent[item] = root
            item = parent
        return root

    def merge(
        self,
        left_row: int,
        right_row: int,
        rows: list[dict[str, object]],
    ) -> tuple[bool, float]:
        left_root = self.find(left_row)
        right_root = self.find(right_row)
        if left_root == right_root:
            return False, 1.0

        left = self.clusters[left_root]
        right = self.clusters[right_root]
        if left is None or right is None:
            raise RuntimeError("inactive root")

        proposed, purity = pairwise.merged_cluster(left, right, rows)
        if purity < PURITY_THRESHOLD:
            return False, purity

        if right.count > left.count:
            left_root, right_root = right_root, left_root
        self.parent[right_root] = left_root
        self.clusters[left_root] = proposed
        self.clusters[right_root] = None
        self.active_roots.discard(right_root)
        self.active_roots.add(left_root)
        return True, purity

    def final_clusters(self) -> list[pairwise.PairwiseCluster]:
        clusters = [self.clusters[root] for root in self.active_roots]
        return sorted(
            [cluster for cluster in clusters if cluster is not None],
            key=lambda cluster: (-cluster.count, cluster.anchor),
        )


def collect_edges(x: np.ndarray) -> list[tuple[float, int, int]]:
    n = x.shape[0]
    all_indices = np.arange(n)
    edges: list[tuple[float, int, int]] = []
    for start in range(0, n, BLOCK_SIZE):
        end = min(start + BLOCK_SIZE, n)
        sims = x[start:end] @ x.T
        for local_idx, row_idx in enumerate(range(start, end)):
            mask = (sims[local_idx] >= EDGE_THRESHOLD) & (all_indices > row_idx)
            targets = np.flatnonzero(mask)
            for target_idx in targets:
                edges.append((float(sims[local_idx, target_idx]), row_idx, int(target_idx)))
    edges.sort(key=lambda item: (-item[0], item[1], item[2]))
    return edges


def run(rows: list[dict[str, object]]) -> tuple[list[pairwise.PairwiseCluster], MergeStats, int]:
    x = np.stack([row["vector"] for row in rows]).astype(np.float32)
    edges = collect_edges(x)
    manager = DynamicClusters(rows)
    stats = MergeStats(candidate_edges=len(edges))

    for _sim, left_row, right_row in edges:
        left_root = manager.find(left_row)
        right_root = manager.find(right_row)
        if left_root == right_root:
            stats.skipped_same_cluster += 1
            continue
        merged, purity = manager.merge(left_row, right_row, rows)
        if merged:
            stats.accepted_merges += 1
            stats.worst_accepted_purity = min(stats.worst_accepted_purity, purity)
        else:
            stats.rejected_purity += 1
            stats.best_rejected_purity = max(stats.best_rejected_purity, purity)

    return manager.final_clusters(), stats, len(edges)


def write_outputs(
    rows: list[dict[str, object]],
    unvectorized: list[dict[str, object]],
    total_count: int,
    clusters: list[pairwise.PairwiseCluster],
    stats: MergeStats,
) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    with SUMMARY_OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
                "cluster_rank",
                "anchor_tag",
                "member_count",
                "mention_count",
                "pct_total",
                "weighted_pairwise_purity_pct",
                "top_tags",
            ]
        )
        for rank, cluster in enumerate(clusters, start=1):
            top_members = sorted(
                cluster.members,
                key=lambda idx: (-int(rows[idx]["count"]), str(rows[idx]["coarse_tag"]), str(rows[idx].get("source_kind", ""))),
            )[:60]
            writer.writerow(
                [
                    rank,
                    cluster.anchor,
                    len(cluster.members),
                    cluster.count,
                    f"{cluster.count / total_count * 100.0:.6f}",
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
            ]
        )
        for rank, cluster in enumerate(clusters, start=1):
            for idx in sorted(
                cluster.members,
                key=lambda row_idx: (-int(rows[row_idx]["count"]), str(rows[row_idx]["coarse_tag"]), str(rows[row_idx].get("source_kind", ""))),
            ):
                writer.writerow(
                    [
                        rows[idx]["coarse_tag"],
                        rows[idx]["count"],
                        f"{int(rows[idx]['count']) / total_count * 100.0:.6f}",
                        rows[idx].get("source_kind", ""),
                        rows[idx].get("source_labels", ""),
                        rank,
                        cluster.anchor,
                    ]
                )
        for row in unvectorized:
            writer.writerow(
                [
                    row["coarse_tag"],
                    row["count"],
                    f"{int(row['count']) / total_count * 100.0:.6f}",
                    row.get("source_kind", ""),
                    row.get("source_labels", ""),
                    "UNVECTORIZED",
                    "UNVECTORIZED",
                ]
            )

    with REPORT_OUT.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("# Intact Cultural Reference Pairwise Edge-90 With Cluster Purity-90\n\n")
        handle.write(
            "This pass uses only original tag-to-tag pairwise edges with cosine similarity >= 90%. "
            "Edges are processed from highest similarity downward. "
            "A recursive merge is accepted only if the resulting cluster's frequency-weighted internal pairwise purity remains >= 90%.\n\n"
        )
        handle.write(f"- Total mentions: {total_count}\n")
        handle.write(f"- Vectorized tags: {len(rows)}\n")
        handle.write(f"- Unvectorized tags: {len(unvectorized)}\n")
        handle.write(f"- Edge threshold: {EDGE_THRESHOLD * 100.0:.2f}%\n")
        handle.write(f"- Cluster purity threshold: {PURITY_THRESHOLD * 100.0:.2f}%\n")
        handle.write(f"- Candidate edges: {stats.candidate_edges}\n")
        handle.write(f"- Accepted merges: {stats.accepted_merges}\n")
        handle.write(f"- Rejected on purity: {stats.rejected_purity}\n")
        handle.write(f"- Final clusters: {len(clusters)}\n")
        handle.write(f"- Top 25 coverage: {sum(cluster.count for cluster in clusters[:25]) / total_count * 100.0:.4f}%\n")
        handle.write(f"- Largest cluster: `{clusters[0].anchor}` ({clusters[0].count / total_count * 100.0:.4f}%)\n\n")
        handle.write("## Final Clusters\n\n")
        for rank, cluster in enumerate(clusters[:250], start=1):
            top_members = sorted(
                cluster.members,
                key=lambda idx: (-int(rows[idx]["count"]), str(rows[idx]["coarse_tag"]), str(rows[idx].get("source_kind", ""))),
            )[:24]
            handle.write(
                f"{rank}. `{cluster.anchor}`: {cluster.count} mentions "
                f"({cluster.count / total_count * 100.0:.4f}%), {len(cluster.members)} tags, "
                f"weighted pairwise purity {pairwise.cluster_purity(cluster) * 100.0:.2f}%\n"
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
    clusters, stats, _edge_count = run(rows)
    write_outputs(rows, unvectorized, total_count, clusters, stats)

    print(f"total={total_count}")
    print(f"vectorized={len(rows)}")
    print(f"unvectorized={len(unvectorized)}")
    print(f"edge_threshold_pct={EDGE_THRESHOLD * 100.0:.2f}")
    print(f"cluster_purity_threshold_pct={PURITY_THRESHOLD * 100.0:.2f}")
    print(f"candidate_edges={stats.candidate_edges}")
    print(f"accepted_merges={stats.accepted_merges}")
    print(f"rejected_purity={stats.rejected_purity}")
    print(f"skipped_same_cluster={stats.skipped_same_cluster}")
    print(f"clusters={len(clusters)}")
    print(f"top25_pct={sum(cluster.count for cluster in clusters[:25]) / total_count * 100.0:.4f}")
    print(f"largest_pct={clusters[0].count / total_count * 100.0:.4f}")
    print(f"summary={SUMMARY_OUT}")
    print(f"tag_map={TAG_MAP_OUT}")
    print(f"report={REPORT_OUT}")


if __name__ == "__main__":
    main()
