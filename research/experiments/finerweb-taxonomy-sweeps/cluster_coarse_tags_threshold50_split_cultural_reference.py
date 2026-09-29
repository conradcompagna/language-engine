from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

import cluster_coarse_tags_snowball_recursive as rec
import cluster_coarse_tags_snowball_recursive_no_cultural_parent_k100 as split_cultural


BASE_DIR = Path(__file__).resolve().parent
OUT_DIR = BASE_DIR / "derived_fasttext_categories"

SUMMARY_OUT = OUT_DIR / "coarse_threshold50_split_cultural_reference_summary.tsv"
TAG_MAP_OUT = OUT_DIR / "coarse_threshold50_split_cultural_reference_tag_map.tsv"
REPORT_OUT = OUT_DIR / "coarse_threshold50_split_cultural_reference_report.md"

THRESHOLD = 0.50
BLOCK_SIZE = 256
MAX_PASSES = 64


class Dsu:
    def __init__(self, n: int):
        self.parent = list(range(n))
        self.rank = [0] * n

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: int, b: int) -> bool:
        ra = self.find(a)
        rb = self.find(b)
        if ra == rb:
            return False
        if self.rank[ra] < self.rank[rb]:
            ra, rb = rb, ra
        self.parent[rb] = ra
        if self.rank[ra] == self.rank[rb]:
            self.rank[ra] += 1
        return True


def best_neighbors(x: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    n = x.shape[0]
    best_idx = np.full(n, -1, dtype=np.int32)
    best_sim = np.full(n, -np.inf, dtype=np.float32)
    all_indices = np.arange(n)

    for start in range(0, n, BLOCK_SIZE):
        end = min(start + BLOCK_SIZE, n)
        sims = x[start:end] @ x.T
        row_offsets = all_indices[start:end] - start
        sims[row_offsets, all_indices[start:end]] = -np.inf
        local_best_idx = np.argmax(sims, axis=1)
        local_best_sim = sims[np.arange(end - start), local_best_idx]
        best_idx[start:end] = local_best_idx.astype(np.int32)
        best_sim[start:end] = local_best_sim.astype(np.float32)
    return best_idx, best_sim


def merge_once(
    items: list[rec.Item],
    rows: list[dict[str, object]],
) -> tuple[list[rec.Item], dict[str, object]]:
    x = np.stack([item.vector for item in items]).astype(np.float32)
    best_idx, best_sim = best_neighbors(x)
    dsu = Dsu(len(items))
    threshold_edges = 0
    best_pair_sim = float(np.max(best_sim)) if len(best_sim) else -np.inf

    for idx, (neighbor, sim) in enumerate(zip(best_idx, best_sim)):
        if int(neighbor) == -1:
            continue
        if float(sim) >= THRESHOLD:
            threshold_edges += 1
            dsu.union(idx, int(neighbor))

    components: dict[int, list[int]] = {}
    for idx in range(len(items)):
        components.setdefault(dsu.find(idx), []).append(idx)

    merged_components = sum(1 for component in components.values() if len(component) > 1)
    next_items = [rec.make_item(component, items, rows) for component in components.values()]
    next_items.sort(key=lambda item: (-item.count, item.anchor))

    return next_items, {
        "best_pair_similarity": best_pair_sim,
        "threshold_edges": threshold_edges,
        "merged_components": merged_components,
    }


def run_threshold(
    rows: list[dict[str, object]],
    total_count: int,
) -> tuple[list[rec.Item], list[dict[str, object]]]:
    items = rec.initial_items(rows)
    log = []

    for pass_num in range(MAX_PASSES + 1):
        top25_pct = sum(item.count for item in sorted(items, key=lambda item: -item.count)[:25]) / total_count * 100.0
        if pass_num == 0:
            log.append(
                {
                    "pass": 0,
                    "clusters": len(items),
                    "top25_pct": top25_pct,
                    "best_pair_similarity": "",
                    "threshold_edges": "",
                    "merged_components": "",
                }
            )
        if pass_num == MAX_PASSES:
            break

        next_items, stats = merge_once(items, rows)
        next_top25_pct = sum(item.count for item in sorted(next_items, key=lambda item: -item.count)[:25]) / total_count * 100.0
        log.append(
            {
                "pass": pass_num + 1,
                "clusters": len(next_items),
                "top25_pct": next_top25_pct,
                "best_pair_similarity": stats["best_pair_similarity"],
                "threshold_edges": stats["threshold_edges"],
                "merged_components": stats["merged_components"],
            }
        )
        if stats["threshold_edges"] == 0 or len(next_items) == len(items):
            items = next_items
            break
        items = next_items
    return items, log


def item_mean_similarity(item: rec.Item, rows: list[dict[str, object]]) -> float:
    return rec.item_mean_similarity(item, rows)


def write_outputs(
    rows: list[dict[str, object]],
    unvectorized: list[dict[str, object]],
    total_count: int,
    items: list[rec.Item],
    log: list[dict[str, object]],
) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    ranked = sorted(items, key=lambda item: (-item.count, item.anchor))

    with SUMMARY_OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
                "cluster_rank",
                "anchor_tag",
                "member_count",
                "mention_count",
                "pct_total",
                "weighted_mean_similarity_pct",
                "top_tags",
            ]
        )
        for rank, item in enumerate(ranked, start=1):
            top_members = sorted(
                item.members,
                key=lambda idx: (-int(rows[idx]["count"]), str(rows[idx]["coarse_tag"])),
            )[:40]
            writer.writerow(
                [
                    rank,
                    item.anchor,
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
                "coarse_tag",
                "count",
                "pct_total",
                "cluster_rank",
                "anchor_tag",
                "centroid_similarity_pct",
            ]
        )
        for rank, item in enumerate(ranked, start=1):
            for idx in sorted(item.members, key=lambda row_idx: (-int(rows[row_idx]["count"]), str(rows[row_idx]["coarse_tag"]))):
                sim = float(np.dot(rows[idx]["vector"], item.vector)) * 100.0
                writer.writerow(
                    [
                        rows[idx]["coarse_tag"],
                        rows[idx]["count"],
                        f"{rows[idx]['percent']:.6f}",
                        rank,
                        item.anchor,
                        f"{sim:.2f}",
                    ]
                )
        for row in unvectorized:
            writer.writerow(
                [
                    row["coarse_tag"],
                    row["count"],
                    f"{row['percent']:.6f}",
                    "UNVECTORIZED",
                    "UNVECTORIZED",
                    "",
                ]
            )

    with REPORT_OUT.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("# Threshold-50 Recursive Coarse Tag Clustering\n\n")
        handle.write(
            "Standalone `cultural reference` is included as its own item. "
            "`cultural reference / X` labels are split into standalone orphan `X` items, "
            "so the parent label cannot drag all children as a single vector. "
            "At each pass, each cluster links to its nearest other cluster; linked components "
            "with nearest-neighbor similarity >= 50% are merged, centroids are recomputed, "
            "and the process stops when no cluster has any nearest neighbor >= 50%.\n\n"
        )
        handle.write(f"- Total mentions: {total_count}\n")
        handle.write(f"- Vectorized items: {len(rows)}\n")
        handle.write(f"- Unvectorized items: {len(unvectorized)}\n")
        handle.write(f"- Final clusters: {len(ranked)}\n")
        handle.write(f"- Threshold: {THRESHOLD * 100:.2f}%\n\n")

        handle.write("## Pass Log\n\n")
        for row in log:
            best = row["best_pair_similarity"]
            if best != "":
                best = f"{float(best) * 100.0:.2f}%"
            handle.write(
                f"- pass {row['pass']}: {row['clusters']} clusters, "
                f"top25 {row['top25_pct']:.4f}%, best remaining pair {best}, "
                f"threshold links {row['threshold_edges']}, merged components {row['merged_components']}\n"
            )

        handle.write("\n## Final Clusters\n\n")
        for rank, item in enumerate(ranked, start=1):
            top_members = sorted(
                item.members,
                key=lambda idx: (-int(rows[idx]["count"]), str(rows[idx]["coarse_tag"])),
            )[:16]
            handle.write(
                f"{rank}. `{item.anchor}`: {item.count} mentions "
                f"({item.count / total_count * 100.0:.4f}%), {len(item.members)} tags, "
                f"mean sim {item_mean_similarity(item, rows) * 100.0:.2f}%\n"
            )
            handle.write(
                "   - "
                + "; ".join(f"`{rows[idx]['coarse_tag']}` ({rows[idx]['count']})" for idx in top_members)
                + "\n"
            )


def main() -> None:
    rows, unvectorized, total_count, standalone_count = split_cultural.load_rows_no_cultural_parent()
    items, log = run_threshold(rows, total_count)
    write_outputs(rows, unvectorized, total_count, items, log)

    top25_pct = sum(item.count for item in sorted(items, key=lambda item: -item.count)[:25]) / total_count * 100.0
    largest_pct = max(item.count for item in items) / total_count * 100.0
    print(f"total={total_count}")
    print(f"vectorized={len(rows)}")
    print(f"unvectorized={len(unvectorized)}")
    print(f"standalone_cultural_reference_mentions={standalone_count}")
    print(f"passes={log[-1]['pass']}")
    print(f"clusters={len(items)}")
    print(f"top25_pct={top25_pct:.4f}")
    print(f"largest_pct={largest_pct:.4f}")
    print(f"summary={SUMMARY_OUT}")
    print(f"tag_map={TAG_MAP_OUT}")
    print(f"report={REPORT_OUT}")


if __name__ == "__main__":
    main()
