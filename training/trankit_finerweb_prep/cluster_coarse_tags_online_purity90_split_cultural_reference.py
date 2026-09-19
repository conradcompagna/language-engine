from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

import cluster_coarse_tags_snowball_recursive as rec
import cluster_coarse_tags_snowball_recursive_no_cultural_parent_k100 as split_cultural


BASE_DIR = Path(__file__).resolve().parent
OUT_DIR = BASE_DIR / "derived_fasttext_categories"

SUMMARY_OUT = OUT_DIR / "coarse_online_purity90_split_cultural_reference_summary.tsv"
TAG_MAP_OUT = OUT_DIR / "coarse_online_purity90_split_cultural_reference_tag_map.tsv"
REPORT_OUT = OUT_DIR / "coarse_online_purity90_split_cultural_reference_report.md"

PURITY_THRESHOLD = 0.90
TOP_K = 2048
MAX_PASSES = 64


def merged_item(item_indices: list[int], items: list[rec.Item], rows: list[dict[str, object]]) -> rec.Item:
    return rec.make_item(item_indices, items, rows)


def candidate_from_neighbor_list(
    item_idx: int,
    active: np.ndarray,
    neighbor_idx: np.ndarray,
    neighbor_sim: np.ndarray,
    x: np.ndarray,
) -> tuple[int | None, float]:
    for neighbor, similarity in zip(neighbor_idx[item_idx], neighbor_sim[item_idx]):
        candidate = int(neighbor)
        if active[candidate]:
            return candidate, float(similarity)

    active_existing = active[: x.shape[0]]
    candidates = np.flatnonzero(active_existing)
    candidates = candidates[candidates != item_idx]
    if not len(candidates):
        return None, -np.inf
    sims = x[candidates] @ x[item_idx]
    best_pos = int(np.argmax(sims))
    return int(candidates[best_pos]), float(sims[best_pos])


def best_created_candidate(
    item: rec.Item,
    items: list[rec.Item],
    active: np.ndarray,
    created_indices: list[int],
) -> tuple[int | None, float]:
    candidates = [idx for idx in created_indices if active[idx]]
    if not candidates:
        return None, -np.inf
    matrix = np.stack([items[idx].vector for idx in candidates]).astype(np.float32)
    sims = matrix @ item.vector
    best_pos = int(np.argmax(sims))
    return candidates[best_pos], float(sims[best_pos])


def merge_purity(item: rec.Item, rows: list[dict[str, object]]) -> float:
    return rec.item_mean_similarity(item, rows)


def online_pass(
    items: list[rec.Item],
    rows: list[dict[str, object]],
) -> tuple[list[rec.Item], dict[str, object]]:
    starting_count = len(items)
    x = np.stack([item.vector for item in items]).astype(np.float32)
    neighbor_idx, neighbor_sim = rec.compute_top_neighbors(x, min(TOP_K, max(1, len(items) - 1)))
    active = np.ones(len(items), dtype=bool)
    created_indices: list[int] = []
    order = sorted(range(starting_count), key=lambda idx: (-items[idx].count, items[idx].anchor))

    attempted = 0
    blocked = 0
    merges = 0
    best_blocked_similarity = -np.inf
    worst_allowed_purity = 1.0

    for item_idx in order:
        if not active[item_idx]:
            continue

        existing_candidate, existing_similarity = candidate_from_neighbor_list(
            item_idx,
            active,
            neighbor_idx,
            neighbor_sim,
            x,
        )
        created_candidate, created_similarity = best_created_candidate(
            items[item_idx],
            items,
            active,
            created_indices,
        )

        if created_similarity > existing_similarity:
            candidate = created_candidate
            similarity = created_similarity
        else:
            candidate = existing_candidate
            similarity = existing_similarity
        if candidate is None:
            continue

        attempted += 1
        proposed = merged_item([item_idx, candidate], items, rows)
        purity = merge_purity(proposed, rows)
        if purity < PURITY_THRESHOLD:
            blocked += 1
            best_blocked_similarity = max(best_blocked_similarity, similarity)
            continue

        active[item_idx] = False
        active[candidate] = False
        items.append(proposed)
        active = np.append(active, True)
        created_indices.append(len(items) - 1)
        merges += 1
        worst_allowed_purity = min(worst_allowed_purity, purity)

    next_items = [item for idx, item in enumerate(items) if active[idx]]
    next_items.sort(key=lambda item: (-item.count, item.anchor))
    return next_items, {
        "attempted": attempted,
        "blocked": blocked,
        "merges": merges,
        "best_blocked_similarity": best_blocked_similarity,
        "worst_allowed_purity": worst_allowed_purity,
    }


def run_recursive(rows: list[dict[str, object]], total_count: int) -> tuple[list[rec.Item], list[dict[str, object]]]:
    items = rec.initial_items(rows)
    log = [{"pass": 0, "clusters": len(items), "top25_pct": 0.0, "attempted": "", "blocked": "", "merges": ""}]

    for pass_num in range(1, MAX_PASSES + 1):
        previous_count = len(items)
        items, stats = online_pass(items, rows)
        top25_pct = sum(item.count for item in sorted(items, key=lambda item: -item.count)[:25]) / total_count * 100.0
        log.append(
            {
                "pass": pass_num,
                "clusters": len(items),
                "top25_pct": top25_pct,
                "attempted": stats["attempted"],
                "blocked": stats["blocked"],
                "merges": stats["merges"],
                "best_blocked_similarity": stats["best_blocked_similarity"],
                "worst_allowed_purity": stats["worst_allowed_purity"],
            }
        )
        if stats["merges"] == 0 or len(items) == previous_count:
            break
    return items, log


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
                key=lambda idx: (-int(rows[idx]["count"]), str(rows[idx]["coarse_tag"]), str(rows[idx].get("source_kind", ""))),
            )[:40]
            writer.writerow(
                [
                    rank,
                    item.anchor,
                    len(item.members),
                    item.count,
                    f"{item.count / total_count * 100.0:.6f}",
                    f"{rec.item_mean_similarity(item, rows) * 100.0:.2f}",
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
        for rank, item in enumerate(ranked, start=1):
            for idx in sorted(
                item.members,
                key=lambda row_idx: (-int(rows[row_idx]["count"]), str(rows[row_idx]["coarse_tag"]), str(rows[row_idx].get("source_kind", ""))),
            ):
                sim = float(np.dot(rows[idx]["vector"], item.vector)) * 100.0
                writer.writerow(
                    [
                        rows[idx]["coarse_tag"],
                        rows[idx]["count"],
                        f"{rows[idx]['percent']:.6f}",
                        rows[idx].get("source_kind", ""),
                        rows[idx].get("source_labels", ""),
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
                    row.get("source_kind", ""),
                    row.get("source_labels", ""),
                    "UNVECTORIZED",
                    "UNVECTORIZED",
                    "",
                ]
            )

    with REPORT_OUT.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("# Online Purity-90 Recursive Coarse Tag Clustering\n\n")
        handle.write(
            "Standalone `cultural reference` is included as its own item. "
            "`cultural reference / X` labels are split into standalone orphan `X` items. "
            "The algorithm processes active clusters in descending frequency order. "
            "For each active cluster it picks the single nearest active candidate, including clusters created earlier in the same pass. "
            "The merge is accepted only if the resulting cluster has weighted mean member-to-centroid similarity >= 90%.\n\n"
        )
        handle.write(f"- Total mentions: {total_count}\n")
        handle.write(f"- Vectorized items: {len(rows)}\n")
        handle.write(f"- Unvectorized items: {len(unvectorized)}\n")
        handle.write(f"- Final clusters: {len(ranked)}\n")
        handle.write(f"- Purity threshold: {PURITY_THRESHOLD * 100:.2f}%\n\n")

        handle.write("## Pass Log\n\n")
        for entry in log:
            if entry["pass"] == 0:
                handle.write(f"- pass 0: {entry['clusters']} clusters\n")
                continue
            handle.write(
                f"- pass {entry['pass']}: {entry['clusters']} clusters, "
                f"top25 {entry['top25_pct']:.4f}%, attempted {entry['attempted']}, "
                f"merged {entry['merges']}, blocked {entry['blocked']}, "
                f"worst accepted purity {entry['worst_allowed_purity'] * 100.0:.2f}%\n"
            )

        handle.write("\n## Final Clusters\n\n")
        for rank, item in enumerate(ranked, start=1):
            top_members = sorted(
                item.members,
                key=lambda idx: (-int(rows[idx]["count"]), str(rows[idx]["coarse_tag"]), str(rows[idx].get("source_kind", ""))),
            )[:16]
            handle.write(
                f"{rank}. `{item.anchor}`: {item.count} mentions "
                f"({item.count / total_count * 100.0:.4f}%), {len(item.members)} tags, "
                f"mean sim {rec.item_mean_similarity(item, rows) * 100.0:.2f}%\n"
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
    rows, unvectorized, total_count, standalone_count = split_cultural.load_rows_no_cultural_parent()
    items, log = run_recursive(rows, total_count)
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
