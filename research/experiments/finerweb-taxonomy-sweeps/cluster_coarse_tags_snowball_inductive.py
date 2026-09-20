from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

import numpy as np

import cluster_full_coarse_tags_weighted_child_seeded_k25 as child


BASE_DIR = Path(__file__).resolve().parent
OUT_DIR = BASE_DIR / "derived_fasttext_categories"
TOP71 = BASE_DIR / "finerweb_label_inventory_coarse_buckets_pct_of_total.tsv"

SUMMARY_OUT = OUT_DIR / "coarse_snowball_inductive_summary.tsv"
TAG_MAP_OUT = OUT_DIR / "coarse_snowball_inductive_tag_map.tsv"
REPORT_OUT = OUT_DIR / "coarse_snowball_inductive_report.md"

TOP_K_NEIGHBORS = 512
BLOCK_SIZE = 256


def normalize(vec: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(vec)
    if not norm:
        return vec.astype(np.float32)
    return (vec / norm).astype(np.float32)


def load_vectorized_rows() -> tuple[list[dict[str, object]], list[dict[str, object]], int]:
    children = child.load_fine_children()
    rows, total_count = child.load_rows(children)
    vectors = child.ft.load_fasttext(child.collect_needed_words(rows))

    vectorized = []
    unvectorized = []
    for row in rows:
        vec = child.enriched_row_vector(row, vectors)
        if vec is None:
            unvectorized.append(row)
            continue
        row["vector"] = vec.astype(np.float32)
        vectorized.append(row)
    return vectorized, unvectorized, total_count


def load_top71_seed_tags() -> set[str]:
    with TOP71.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    return {row["coarse_label"] for row in rows[:71]}


def compute_top_neighbors(x: np.ndarray, top_k: int = TOP_K_NEIGHBORS) -> tuple[np.ndarray, np.ndarray]:
    n = x.shape[0]
    k = min(top_k, n - 1)
    neighbor_idx = np.empty((n, k), dtype=np.int32)
    neighbor_sim = np.empty((n, k), dtype=np.float32)
    all_indices = np.arange(n)

    for start in range(0, n, BLOCK_SIZE):
        end = min(start + BLOCK_SIZE, n)
        sims = x[start:end] @ x.T
        row_offsets = all_indices[start:end] - start
        sims[row_offsets, all_indices[start:end]] = -np.inf
        top_idx = np.argpartition(-sims, kth=k - 1, axis=1)[:, :k]
        top_sims = np.take_along_axis(sims, top_idx, axis=1)
        order = np.argsort(-top_sims, axis=1)
        neighbor_idx[start:end] = np.take_along_axis(top_idx, order, axis=1)
        neighbor_sim[start:end] = np.take_along_axis(top_sims, order, axis=1)
    return neighbor_idx, neighbor_sim


class ClusterState:
    def __init__(self, x: np.ndarray, rows: list[dict[str, object]], seed_indices: set[int] | None = None):
        self.x = x
        self.rows = rows
        self.assignment = np.full(x.shape[0], -1, dtype=np.int32)
        self.members: list[list[int]] = []
        self.vector_sums: list[np.ndarray] = []
        self.centroids: list[np.ndarray] = []
        self.seed_anchor: list[str] = []

        for idx in sorted(seed_indices or set(), key=lambda item: -int(rows[item]["count"])):
            self.create_cluster([idx], str(rows[idx]["coarse_tag"]))

    def create_cluster(self, indices: list[int], seed_anchor: str = "") -> int:
        cluster_id = len(self.members)
        self.members.append([])
        self.vector_sums.append(np.zeros(self.x.shape[1], dtype=np.float32))
        self.centroids.append(np.zeros(self.x.shape[1], dtype=np.float32))
        self.seed_anchor.append(seed_anchor)
        for idx in indices:
            self.add_to_cluster(idx, cluster_id)
        return cluster_id

    def add_to_cluster(self, idx: int, cluster_id: int) -> None:
        if self.assignment[idx] != -1:
            return
        self.assignment[idx] = cluster_id
        self.members[cluster_id].append(idx)
        self.vector_sums[cluster_id] += self.x[idx]
        self.centroids[cluster_id] = normalize(self.vector_sums[cluster_id])

    def best_cluster(self, idx: int) -> tuple[int | None, float]:
        if not self.centroids:
            return None, -np.inf
        matrix = np.stack(self.centroids).astype(np.float32)
        sims = matrix @ self.x[idx]
        best = int(np.argmax(sims))
        return best, float(sims[best])


def first_unassigned_neighbor(
    row_idx: int,
    assignment: np.ndarray,
    neighbor_idx: np.ndarray,
    neighbor_sim: np.ndarray,
) -> tuple[int | None, float]:
    for idx, sim in zip(neighbor_idx[row_idx], neighbor_sim[row_idx]):
        if assignment[int(idx)] == -1:
            return int(idx), float(sim)
    return None, -np.inf


def greedy_pairwise(
    x: np.ndarray,
    rows: list[dict[str, object]],
    neighbor_idx: np.ndarray,
    neighbor_sim: np.ndarray,
    seed_indices: set[int] | None = None,
) -> ClusterState:
    state = ClusterState(x, rows, seed_indices)
    order = sorted(range(len(rows)), key=lambda idx: (-int(rows[idx]["count"]), str(rows[idx]["coarse_tag"])))

    for idx in order:
        if state.assignment[idx] != -1:
            continue
        neighbor = int(neighbor_idx[idx, 0])
        cluster_id = int(state.assignment[neighbor])
        if cluster_id != -1:
            state.add_to_cluster(idx, cluster_id)
        else:
            state.create_cluster([idx, neighbor])
    return state


def greedy_centroid(
    x: np.ndarray,
    rows: list[dict[str, object]],
    neighbor_idx: np.ndarray,
    neighbor_sim: np.ndarray,
    seed_indices: set[int] | None = None,
) -> ClusterState:
    state = ClusterState(x, rows, seed_indices)
    order = sorted(range(len(rows)), key=lambda idx: (-int(rows[idx]["count"]), str(rows[idx]["coarse_tag"])))

    for idx in order:
        if state.assignment[idx] != -1:
            continue
        cluster_id, cluster_sim = state.best_cluster(idx)
        neighbor, neighbor_score = first_unassigned_neighbor(idx, state.assignment, neighbor_idx, neighbor_sim)

        if cluster_id is not None and (neighbor is None or cluster_sim >= neighbor_score):
            state.add_to_cluster(idx, cluster_id)
        elif neighbor is not None:
            state.create_cluster([idx, neighbor])
        else:
            state.create_cluster([idx])
    return state


def cluster_summaries(
    version: str,
    state: ClusterState,
    rows: list[dict[str, object]],
    total_count: int,
) -> list[dict[str, object]]:
    summaries = []
    for cluster_id, members in enumerate(state.members):
        if not members:
            continue
        member_rows = [rows[idx] for idx in members]
        mention_count = sum(int(row["count"]) for row in member_rows)
        anchor = max(member_rows, key=lambda row: (int(row["count"]), str(row["coarse_tag"])))
        centroid = state.centroids[cluster_id]
        sims = [float(np.dot(rows[idx]["vector"], centroid)) for idx in members]
        weights = [float(rows[idx]["count"]) for idx in members]
        top_tags = sorted(member_rows, key=lambda row: (-int(row["count"]), str(row["coarse_tag"])))[:25]
        summaries.append(
            {
                "version": version,
                "cluster_id": cluster_id,
                "anchor": str(anchor["coarse_tag"]),
                "seed_anchor": state.seed_anchor[cluster_id],
                "member_count": len(members),
                "mention_count": mention_count,
                "percent_total": mention_count / total_count * 100.0,
                "weighted_mean_similarity": float(np.average(sims, weights=weights)),
                "top_tags": top_tags,
            }
        )
    summaries.sort(key=lambda item: (-float(item["percent_total"]), str(item["anchor"])))
    for rank, summary in enumerate(summaries, start=1):
        summary["rank"] = rank
    return summaries


def write_outputs(
    rows: list[dict[str, object]],
    unvectorized: list[dict[str, object]],
    total_count: int,
    results: list[tuple[str, ClusterState, list[dict[str, object]]]],
) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    with SUMMARY_OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
                "version",
                "cluster_rank",
                "anchor_tag",
                "seed_anchor",
                "member_count",
                "mention_count",
                "pct_total",
                "weighted_mean_similarity_pct",
                "top_tags",
            ]
        )
        for version, _state, summaries in results:
            for summary in summaries:
                writer.writerow(
                    [
                        version,
                        summary["rank"],
                        summary["anchor"],
                        summary["seed_anchor"],
                        summary["member_count"],
                        summary["mention_count"],
                        f"{summary['percent_total']:.6f}",
                        f"{summary['weighted_mean_similarity'] * 100:.2f}",
                        "; ".join(f"{row['coarse_tag']} ({row['count']})" for row in summary["top_tags"]),
                    ]
                )

    summary_by_version = {
        version: {int(summary["cluster_id"]): summary for summary in summaries}
        for version, _state, summaries in results
    }

    with TAG_MAP_OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
                "version",
                "coarse_tag",
                "count",
                "pct_total",
                "cluster_rank",
                "anchor_tag",
                "seed_anchor",
                "centroid_similarity_pct",
            ]
        )
        for version, state, _summaries in results:
            by_cluster = summary_by_version[version]
            for idx, row in enumerate(rows):
                cluster_id = int(state.assignment[idx])
                summary = by_cluster[cluster_id]
                sim = float(np.dot(row["vector"], state.centroids[cluster_id]))
                writer.writerow(
                    [
                        version,
                        row["coarse_tag"],
                        row["count"],
                        f"{row['percent']:.6f}",
                        summary["rank"],
                        summary["anchor"],
                        summary["seed_anchor"],
                        f"{sim * 100:.2f}",
                    ]
                )
            for row in unvectorized:
                writer.writerow(
                    [
                        version,
                        row["coarse_tag"],
                        row["count"],
                        f"{row['percent']:.6f}",
                        "UNVECTORIZED",
                        "UNVECTORIZED",
                        "",
                        "",
                    ]
                )

    with REPORT_OUT.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("# Coarse Tag Snowball Inductive Clustering\n\n")
        handle.write(
            "Every coarse tag is represented by its enriched vector: 50% parent label and "
            "50% frequency-weighted centroid of fine-grained child labels. No target category count is supplied. "
            f"Nearest-neighbor lookup uses the top {TOP_K_NEIGHBORS} neighbors per tag for greedy assignment.\n\n"
        )
        handle.write(f"- Total mentions: {total_count}\n")
        handle.write(f"- Vectorized coarse tags: {len(rows)}\n")
        handle.write(f"- Unvectorized coarse tags: {len(unvectorized)}\n\n")

        for version, _state, summaries in results:
            handle.write(f"## {version}\n\n")
            handle.write(f"- Clusters: {len(summaries)}\n")
            handle.write("- Top 30 clusters by mention coverage:\n\n")
            for summary in summaries[:30]:
                seed = f", seed `{summary['seed_anchor']}`" if summary["seed_anchor"] else ""
                handle.write(
                    f"{summary['rank']}. `{summary['anchor']}`{seed}: "
                    f"{summary['mention_count']} mentions ({summary['percent_total']:.4f}%), "
                    f"{summary['member_count']} tags, mean sim {summary['weighted_mean_similarity'] * 100:.2f}%\n"
                )
                handle.write(
                    "   - "
                    + "; ".join(f"`{row['coarse_tag']}` ({row['count']})" for row in summary["top_tags"][:12])
                    + "\n"
                )
            handle.write("\n")


def main() -> None:
    rows, unvectorized, total_count = load_vectorized_rows()
    x = np.stack([row["vector"] for row in rows]).astype(np.float32)
    neighbor_idx, neighbor_sim = compute_top_neighbors(x)

    top71 = load_top71_seed_tags()
    seed_indices = {idx for idx, row in enumerate(rows) if str(row["coarse_tag"]) in top71}

    runs = [
        ("v1_pairwise_snowball", greedy_pairwise(x, rows, neighbor_idx, neighbor_sim)),
        ("v2_centroid_snowball", greedy_centroid(x, rows, neighbor_idx, neighbor_sim)),
        ("v3_pairwise_top71_seeded", greedy_pairwise(x, rows, neighbor_idx, neighbor_sim, seed_indices)),
        ("v4_centroid_top71_seeded", greedy_centroid(x, rows, neighbor_idx, neighbor_sim, seed_indices)),
    ]
    results = []
    for version, state in runs:
        summaries = cluster_summaries(version, state, rows, total_count)
        results.append((version, state, summaries))

    write_outputs(rows, unvectorized, total_count, results)

    print(f"total={total_count}")
    print(f"vectorized={len(rows)}")
    print(f"unvectorized={len(unvectorized)}")
    print(f"top71_seeded_vectorized={len(seed_indices)}")
    for version, _state, summaries in results:
        top_pct = sum(float(summary["percent_total"]) for summary in summaries[:25])
        print(f"{version}: clusters={len(summaries)} top25_pct={top_pct:.4f}")
    print(f"summary={SUMMARY_OUT}")
    print(f"tag_map={TAG_MAP_OUT}")
    print(f"report={REPORT_OUT}")


if __name__ == "__main__":
    main()
