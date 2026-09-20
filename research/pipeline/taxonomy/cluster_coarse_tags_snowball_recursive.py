from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import numpy as np

import cluster_full_coarse_tags_weighted_child_seeded_k25 as child
from cluster_coarse_tags_snowball_inductive import load_top71_seed_tags


BASE_DIR = Path(__file__).resolve().parent
OUT_DIR = BASE_DIR / "derived_fasttext_categories"

SUMMARY_OUT = OUT_DIR / "coarse_snowball_recursive_summary.tsv"
TAG_MAP_OUT = OUT_DIR / "coarse_snowball_recursive_tag_map.tsv"
REPORT_OUT = OUT_DIR / "coarse_snowball_recursive_report.md"

INITIAL_TOP_K = 512
RECURSIVE_TOP_K = 256
BLOCK_SIZE = 256
TARGET_CLUSTERS = 50
MAX_PASSES = 32


@dataclass
class Item:
    members: list[int]
    vector_sum: np.ndarray
    vector: np.ndarray
    count: int
    anchor: str
    seed_anchor: str = ""


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
        row["vector"] = normalize(vec.astype(np.float32))
        vectorized.append(row)
    return vectorized, unvectorized, total_count


def compute_top_neighbors(x: np.ndarray, top_k: int) -> tuple[np.ndarray, np.ndarray]:
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


def initial_items(rows: list[dict[str, object]]) -> list[Item]:
    return [
        Item(
            members=[idx],
            vector_sum=row["vector"].astype(np.float32).copy(),
            vector=row["vector"].astype(np.float32).copy(),
            count=int(row["count"]),
            anchor=str(row["coarse_tag"]),
        )
        for idx, row in enumerate(rows)
    ]


def make_item(member_item_indices: list[int], items: list[Item], rows: list[dict[str, object]]) -> Item:
    members: list[int] = []
    vector_sum = np.zeros_like(items[0].vector_sum)
    count = 0
    seed_anchors = []

    for item_idx in member_item_indices:
        item = items[item_idx]
        members.extend(item.members)
        vector_sum += item.vector_sum
        count += item.count
        if item.seed_anchor:
            seed_anchors.extend(item.seed_anchor.split("; "))

    anchor_idx = max(members, key=lambda idx: (int(rows[idx]["count"]), str(rows[idx]["coarse_tag"])))
    unique_seed_anchors = sorted(set(seed_anchors))
    return Item(
        members=members,
        vector_sum=vector_sum,
        vector=normalize(vector_sum),
        count=count,
        anchor=str(rows[anchor_idx]["coarse_tag"]),
        seed_anchor="; ".join(unique_seed_anchors),
    )


def first_unassigned_neighbor(
    item_idx: int,
    assignment: np.ndarray,
    neighbor_idx: np.ndarray,
    neighbor_sim: np.ndarray,
    x: np.ndarray,
) -> tuple[int | None, float]:
    for idx, sim in zip(neighbor_idx[item_idx], neighbor_sim[item_idx]):
        if assignment[int(idx)] == -1:
            return int(idx), float(sim)

    candidates = np.flatnonzero(assignment == -1)
    candidates = candidates[candidates != item_idx]
    if not len(candidates):
        return None, -np.inf
    sims = x[candidates] @ x[item_idx]
    best_pos = int(np.argmax(sims))
    return int(candidates[best_pos]), float(sims[best_pos])


def cluster_once_pairwise(
    items: list[Item],
    rows: list[dict[str, object]],
    seed_item_indices: set[int] | None = None,
) -> list[Item]:
    x = np.stack([item.vector for item in items]).astype(np.float32)
    top_k = INITIAL_TOP_K if len(items) > 10000 else RECURSIVE_TOP_K
    neighbor_idx, neighbor_sim = compute_top_neighbors(x, top_k)
    assignment = np.full(len(items), -1, dtype=np.int32)
    clusters: list[list[int]] = []

    for item_idx in sorted(seed_item_indices or set(), key=lambda idx: -items[idx].count):
        assignment[item_idx] = len(clusters)
        clusters.append([item_idx])

    order = sorted(range(len(items)), key=lambda idx: (-items[idx].count, items[idx].anchor))
    for item_idx in order:
        if assignment[item_idx] != -1:
            continue
        neighbor = int(neighbor_idx[item_idx, 0])
        cluster_id = int(assignment[neighbor])
        if cluster_id != -1:
            assignment[item_idx] = cluster_id
            clusters[cluster_id].append(item_idx)
        else:
            assignment[item_idx] = len(clusters)
            assignment[neighbor] = len(clusters)
            clusters.append([item_idx, neighbor])

    return [make_item(cluster, items, rows) for cluster in clusters]


def cluster_once_centroid(
    items: list[Item],
    rows: list[dict[str, object]],
    seed_item_indices: set[int] | None = None,
) -> list[Item]:
    x = np.stack([item.vector for item in items]).astype(np.float32)
    top_k = INITIAL_TOP_K if len(items) > 10000 else RECURSIVE_TOP_K
    neighbor_idx, neighbor_sim = compute_top_neighbors(x, top_k)
    assignment = np.full(len(items), -1, dtype=np.int32)
    clusters: list[list[int]] = []
    cluster_sums: list[np.ndarray] = []
    centroids: list[np.ndarray] = []

    def add_cluster(indices: list[int]) -> int:
        cluster_id = len(clusters)
        clusters.append([])
        cluster_sums.append(np.zeros_like(items[0].vector_sum))
        centroids.append(np.zeros_like(items[0].vector))
        for idx in indices:
            add_item(idx, cluster_id)
        return cluster_id

    def add_item(item_idx: int, cluster_id: int) -> None:
        if assignment[item_idx] != -1:
            return
        assignment[item_idx] = cluster_id
        clusters[cluster_id].append(item_idx)
        cluster_sums[cluster_id] += items[item_idx].vector_sum
        centroids[cluster_id] = normalize(cluster_sums[cluster_id])

    for item_idx in sorted(seed_item_indices or set(), key=lambda idx: -items[idx].count):
        add_cluster([item_idx])

    order = sorted(range(len(items)), key=lambda idx: (-items[idx].count, items[idx].anchor))
    for item_idx in order:
        if assignment[item_idx] != -1:
            continue

        best_cluster = None
        best_cluster_sim = -np.inf
        if centroids:
            sims = np.stack(centroids).astype(np.float32) @ x[item_idx]
            best_cluster = int(np.argmax(sims))
            best_cluster_sim = float(sims[best_cluster])

        neighbor, neighbor_sim_score = first_unassigned_neighbor(
            item_idx,
            assignment,
            neighbor_idx,
            neighbor_sim,
            x,
        )
        if best_cluster is not None and (neighbor is None or best_cluster_sim >= neighbor_sim_score):
            add_item(item_idx, best_cluster)
        elif neighbor is not None:
            add_cluster([item_idx, neighbor])
        else:
            add_cluster([item_idx])

    return [make_item(cluster, items, rows) for cluster in clusters]


def attach_seed_anchors(items: list[Item], rows: list[dict[str, object]], seed_tags: set[str]) -> set[int]:
    seed_indices = set()
    for item_idx, item in enumerate(items):
        tag = str(rows[item.members[0]]["coarse_tag"])
        if tag in seed_tags:
            item.seed_anchor = tag
            seed_indices.add(item_idx)
    return seed_indices


def run_recursive(
    version: str,
    mode: str,
    rows: list[dict[str, object]],
    total_count: int,
    seed_tags: set[str] | None = None,
) -> tuple[str, list[Item], list[dict[str, object]]]:
    items = initial_items(rows)
    seed_indices = attach_seed_anchors(items, rows, seed_tags or set()) if seed_tags else None
    log = []
    pass_num = 0
    log.append({"pass": pass_num, "clusters": len(items), "top25_pct": 0.0})

    while len(items) > TARGET_CLUSTERS and pass_num < MAX_PASSES:
        pass_num += 1
        if mode == "pairwise":
            items = cluster_once_pairwise(items, rows, seed_indices if pass_num == 1 else None)
        elif mode == "centroid":
            items = cluster_once_centroid(items, rows, seed_indices if pass_num == 1 else None)
        else:
            raise ValueError(mode)

        top25_pct = sum(item.count for item in sorted(items, key=lambda item: -item.count)[:25]) / total_count * 100.0
        log.append({"pass": pass_num, "clusters": len(items), "top25_pct": top25_pct})

    return version, items, log


def item_mean_similarity(item: Item, rows: list[dict[str, object]]) -> float:
    weights = np.array([float(rows[idx]["count"]) for idx in item.members], dtype=np.float64)
    sims = np.array([float(np.dot(rows[idx]["vector"], item.vector)) for idx in item.members], dtype=np.float64)
    if not weights.sum():
        return float(np.mean(sims))
    return float(np.average(sims, weights=weights))


def write_outputs(
    rows: list[dict[str, object]],
    unvectorized: list[dict[str, object]],
    total_count: int,
    results: list[tuple[str, list[Item], list[dict[str, object]]]],
) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    with SUMMARY_OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
                "version",
                "pass",
                "cluster_count",
                "top25_pct",
                "cluster_rank",
                "anchor_tag",
                "seed_anchors",
                "member_count",
                "mention_count",
                "pct_total",
                "weighted_mean_similarity_pct",
                "top_tags",
            ]
        )
        for version, items, log in results:
            final_pass = log[-1]["pass"]
            final_cluster_count = log[-1]["clusters"]
            final_top25_pct = log[-1]["top25_pct"]
            ranked = sorted(items, key=lambda item: (-item.count, item.anchor))
            for rank, item in enumerate(ranked, start=1):
                top_members = sorted(
                    item.members,
                    key=lambda idx: (-int(rows[idx]["count"]), str(rows[idx]["coarse_tag"])),
                )[:40]
                writer.writerow(
                    [
                        version,
                        final_pass,
                        final_cluster_count,
                        f"{final_top25_pct:.6f}",
                        rank,
                        item.anchor,
                        item.seed_anchor,
                        len(item.members),
                        item.count,
                        f"{item.count / total_count * 100.0:.6f}",
                        f"{item_mean_similarity(item, rows) * 100.0:.2f}",
                        "; ".join(f"{rows[idx]['coarse_tag']} ({rows[idx]['count']})" for idx in top_members),
                    ]
                )

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
                "seed_anchors",
                "centroid_similarity_pct",
            ]
        )
        for version, items, _log in results:
            ranked = sorted(items, key=lambda item: (-item.count, item.anchor))
            rank_by_identity = {id(item): rank for rank, item in enumerate(ranked, start=1)}
            for item in ranked:
                rank = rank_by_identity[id(item)]
                for idx in sorted(item.members, key=lambda row_idx: (-int(rows[row_idx]["count"]), str(rows[row_idx]["coarse_tag"]))):
                    sim = float(np.dot(rows[idx]["vector"], item.vector)) * 100.0
                    writer.writerow(
                        [
                            version,
                            rows[idx]["coarse_tag"],
                            rows[idx]["count"],
                            f"{rows[idx]['percent']:.6f}",
                            rank,
                            item.anchor,
                            item.seed_anchor,
                            f"{sim:.2f}",
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
        handle.write("# Recursive Coarse Tag Snowball Clustering\n\n")
        handle.write(
            "This starts with the same enriched coarse-tag vectors as the previous snowball run, "
            "then repeatedly clusters the cluster centroids until the result is at or below 50 clusters. "
            "Cluster centroids are the normalized average of their member coarse-tag vectors.\n\n"
        )
        handle.write(f"- Total mentions: {total_count}\n")
        handle.write(f"- Vectorized coarse tags: {len(rows)}\n")
        handle.write(f"- Unvectorized coarse tags: {len(unvectorized)}\n")
        handle.write(f"- Target cluster ceiling: {TARGET_CLUSTERS}\n\n")

        for version, items, log in results:
            ranked = sorted(items, key=lambda item: (-item.count, item.anchor))
            handle.write(f"## {version}\n\n")
            handle.write("### Pass Log\n\n")
            for row in log:
                handle.write(
                    f"- pass {row['pass']}: {row['clusters']} clusters"
                    + (f", top25 {row['top25_pct']:.4f}%" if row["pass"] else "")
                    + "\n"
                )
            handle.write("\n### Final Clusters\n\n")
            for rank, item in enumerate(ranked, start=1):
                top_members = sorted(
                    item.members,
                    key=lambda idx: (-int(rows[idx]["count"]), str(rows[idx]["coarse_tag"])),
                )[:16]
                seed = f", seeds `{item.seed_anchor}`" if item.seed_anchor else ""
                handle.write(
                    f"{rank}. `{item.anchor}`{seed}: {item.count} mentions "
                    f"({item.count / total_count * 100.0:.4f}%), {len(item.members)} tags, "
                    f"mean sim {item_mean_similarity(item, rows) * 100.0:.2f}%\n"
                )
                handle.write(
                    "   - "
                    + "; ".join(f"`{rows[idx]['coarse_tag']}` ({rows[idx]['count']})" for idx in top_members)
                    + "\n"
                )
            handle.write("\n")


def main() -> None:
    rows, unvectorized, total_count = load_vectorized_rows()
    top71 = load_top71_seed_tags()

    results = [
        run_recursive("v1_pairwise_recursive", "pairwise", rows, total_count),
        run_recursive("v2_centroid_recursive", "centroid", rows, total_count),
        run_recursive("v3_pairwise_top71_seeded_recursive", "pairwise", rows, total_count, top71),
        run_recursive("v4_centroid_top71_seeded_recursive", "centroid", rows, total_count, top71),
    ]
    write_outputs(rows, unvectorized, total_count, results)

    print(f"total={total_count}")
    print(f"vectorized={len(rows)}")
    print(f"unvectorized={len(unvectorized)}")
    for version, items, log in results:
        top25_pct = sum(item.count for item in sorted(items, key=lambda item: -item.count)[:25]) / total_count * 100.0
        print(
            f"{version}: passes={log[-1]['pass']} clusters={len(items)} "
            f"top25_pct={top25_pct:.4f} largest={max(item.count for item in items) / total_count * 100.0:.4f}"
        )
    print(f"summary={SUMMARY_OUT}")
    print(f"tag_map={TAG_MAP_OUT}")
    print(f"report={REPORT_OUT}")


if __name__ == "__main__":
    main()
