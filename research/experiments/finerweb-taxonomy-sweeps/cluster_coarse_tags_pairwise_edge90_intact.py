from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import numpy as np

import cluster_coarse_tags_pairwise_member_purity90_cultural_modes as pairwise
import cluster_coarse_tags_snowball_recursive as rec


BASE_DIR = Path(__file__).resolve().parent
OUT_DIR = BASE_DIR / "derived_fasttext_categories"

SUMMARY_OUT = OUT_DIR / "coarse_pairwise_edge90_intact_summary.tsv"
TAG_MAP_OUT = OUT_DIR / "coarse_pairwise_edge90_intact_tag_map.tsv"
REPORT_OUT = OUT_DIR / "coarse_pairwise_edge90_intact.md"

SIM_THRESHOLD = 0.90
BLOCK_SIZE = 256


class UnionFind:
    def __init__(self, size: int) -> None:
        self.parent = list(range(size))
        self.rank = [0] * size

    def find(self, item: int) -> int:
        parent = self.parent[item]
        if parent != item:
            self.parent[item] = self.find(parent)
        return self.parent[item]

    def union(self, left: int, right: int) -> bool:
        left_root = self.find(left)
        right_root = self.find(right)
        if left_root == right_root:
            return False
        if self.rank[left_root] < self.rank[right_root]:
            left_root, right_root = right_root, left_root
        self.parent[right_root] = left_root
        if self.rank[left_root] == self.rank[right_root]:
            self.rank[left_root] += 1
        return True


@dataclass
class EdgeCluster:
    members: list[int]
    count: int
    anchor: str
    vector: np.ndarray


def build_components(x: np.ndarray) -> tuple[UnionFind, int]:
    n = x.shape[0]
    uf = UnionFind(n)
    edge_count = 0
    all_indices = np.arange(n)

    for start in range(0, n, BLOCK_SIZE):
        end = min(start + BLOCK_SIZE, n)
        sims = x[start:end] @ x.T
        for local_idx, row_idx in enumerate(range(start, end)):
            mask = (sims[local_idx] >= SIM_THRESHOLD) & (all_indices > row_idx)
            targets = np.flatnonzero(mask)
            for target_idx in targets:
                if uf.union(row_idx, int(target_idx)):
                    edge_count += 1
    return uf, edge_count


def cluster_purity(cluster: EdgeCluster, rows: list[dict[str, object]]) -> float:
    if len(cluster.members) < 2:
        return 1.0
    vector_sum = np.zeros_like(rows[0]["vector"], dtype=np.float64)
    weight_sum = 0.0
    for row_idx in cluster.members:
        weight = float(rows[row_idx]["count"])
        vector_sum += rows[row_idx]["vector"].astype(np.float64) * weight
        weight_sum += weight
    pair_num = float(np.dot(vector_sum, vector_sum))
    pair_den = weight_sum * weight_sum
    self_num = 0.0
    self_den = 0.0
    for row_idx in cluster.members:
        weight = float(rows[row_idx]["count"])
        self_num += weight * weight
        self_den += weight * weight
    numerator = pair_num - self_num
    denominator = pair_den - self_den
    return numerator / denominator if denominator else 1.0


def make_clusters(uf: UnionFind, rows: list[dict[str, object]]) -> list[EdgeCluster]:
    grouped: dict[int, list[int]] = {}
    for row_idx in range(len(rows)):
        grouped.setdefault(uf.find(row_idx), []).append(row_idx)

    clusters = []
    for members in grouped.values():
        count = sum(int(rows[idx]["count"]) for idx in members)
        anchor_idx = max(members, key=lambda idx: (int(rows[idx]["count"]), str(rows[idx]["coarse_tag"])))
        weighted = np.zeros_like(rows[0]["vector"], dtype=np.float64)
        for idx in members:
            weighted += rows[idx]["vector"].astype(np.float64) * float(rows[idx]["count"])
        clusters.append(
            EdgeCluster(
                members=members,
                count=count,
                anchor=str(rows[anchor_idx]["coarse_tag"]),
                vector=rec.normalize(weighted.astype(np.float32)),
            )
        )
    clusters.sort(key=lambda cluster: (-cluster.count, cluster.anchor))
    return clusters


def write_outputs(
    rows: list[dict[str, object]],
    unvectorized: list[dict[str, object]],
    total_count: int,
    clusters: list[EdgeCluster],
    edge_count: int,
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
                    f"{cluster_purity(cluster, rows) * 100.0:.2f}",
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
                "centroid_similarity_pct",
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
                        f"{float(np.dot(rows[idx]['vector'], cluster.vector)) * 100.0:.2f}",
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
                    "",
                ]
            )

    with REPORT_OUT.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("# Intact Cultural Reference Pairwise Edge-90 Clustering\n\n")
        handle.write(
            "This pass uses only original tag-to-tag pairwise similarity. "
            "An edge is created for every pair of vectorized tags with cosine similarity >= 90%. "
            "Final clusters are recursive connected components over those edges. "
            "There is no internal-cluster purity threshold and no centroid merge target.\n\n"
        )
        handle.write(f"- Total mentions: {total_count}\n")
        handle.write(f"- Vectorized tags: {len(rows)}\n")
        handle.write(f"- Unvectorized tags: {len(unvectorized)}\n")
        handle.write(f"- Similarity threshold: {SIM_THRESHOLD * 100.0:.2f}%\n")
        handle.write(f"- Union edges accepted: {edge_count}\n")
        handle.write(f"- Final clusters: {len(clusters)}\n")
        handle.write(f"- Top 25 coverage: {sum(cluster.count for cluster in clusters[:25]) / total_count * 100.0:.4f}%\n\n")
        handle.write("## Final Clusters\n\n")
        for rank, cluster in enumerate(clusters[:250], start=1):
            top_members = sorted(
                cluster.members,
                key=lambda idx: (-int(rows[idx]["count"]), str(rows[idx]["coarse_tag"]), str(rows[idx].get("source_kind", ""))),
            )[:24]
            handle.write(
                f"{rank}. `{cluster.anchor}`: {cluster.count} mentions "
                f"({cluster.count / total_count * 100.0:.4f}%), {len(cluster.members)} tags, "
                f"weighted pairwise purity {cluster_purity(cluster, rows) * 100.0:.2f}%\n"
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
    x = np.stack([row["vector"] for row in rows]).astype(np.float32)
    uf, edge_count = build_components(x)
    clusters = make_clusters(uf, rows)
    write_outputs(rows, unvectorized, total_count, clusters, edge_count)
    print(f"total={total_count}")
    print(f"vectorized={len(rows)}")
    print(f"unvectorized={len(unvectorized)}")
    print(f"edge_threshold_pct={SIM_THRESHOLD * 100.0:.2f}")
    print(f"union_edges={edge_count}")
    print(f"clusters={len(clusters)}")
    print(f"top25_pct={sum(cluster.count for cluster in clusters[:25]) / total_count * 100.0:.4f}")
    print(f"largest_pct={clusters[0].count / total_count * 100.0:.4f}")
    print(f"summary={SUMMARY_OUT}")
    print(f"tag_map={TAG_MAP_OUT}")
    print(f"report={REPORT_OUT}")


if __name__ == "__main__":
    main()
