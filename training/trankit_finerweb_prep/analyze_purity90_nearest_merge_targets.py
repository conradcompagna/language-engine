from __future__ import annotations

import csv
from collections import defaultdict, deque
from pathlib import Path

import numpy as np

import cluster_coarse_tags_snowball_recursive as rec
import cluster_coarse_tags_snowball_recursive_no_cultural_parent_k100 as split_cultural


BASE_DIR = Path(__file__).resolve().parent
OUT_DIR = BASE_DIR / "derived_fasttext_categories"

BASE_TAG_MAP = OUT_DIR / "coarse_online_purity90_split_cultural_reference_tag_map.tsv"
OUT_TSV = OUT_DIR / "coarse_online_purity90_nearest_merge_targets.tsv"
OUT_MD = OUT_DIR / "coarse_online_purity90_nearest_merge_targets.md"

BLOCK_SIZE = 256


def row_key(row: dict[str, object]) -> tuple[str, int, str, str]:
    return (
        str(row["coarse_tag"]),
        int(row["count"]),
        str(row.get("source_kind", "")),
        str(row.get("source_labels", "")),
    )


def reconstruct_items(rows: list[dict[str, object]]) -> list[rec.Item]:
    by_key: defaultdict[tuple[str, int, str, str], deque[int]] = defaultdict(deque)
    for idx, row in enumerate(rows):
        by_key[row_key(row)].append(idx)

    members_by_rank: defaultdict[int, list[int]] = defaultdict(list)
    with BASE_TAG_MAP.open("r", encoding="utf-8", newline="") as handle:
        for tag_row in csv.DictReader(handle, delimiter="\t"):
            if tag_row["cluster_rank"] == "UNVECTORIZED":
                continue
            key = (
                tag_row["coarse_tag"],
                int(tag_row["count"]),
                tag_row["source_kind"],
                tag_row["source_labels"],
            )
            if not by_key[key]:
                raise RuntimeError(f"Could not match tag-map row back to vector row: {key!r}")
            members_by_rank[int(tag_row["cluster_rank"])].append(by_key[key].popleft())

    items = []
    singleton_items = rec.initial_items(rows)
    for rank in sorted(members_by_rank):
        member_item_indices = members_by_rank[rank]
        items.append(rec.make_item(member_item_indices, singleton_items, rows))
    return items


def nearest_targets(items: list[rec.Item], rows: list[dict[str, object]], total_count: int) -> list[dict[str, object]]:
    x = np.stack([item.vector for item in items]).astype(np.float32)
    n = len(items)
    best_idx = np.full(n, -1, dtype=np.int32)
    best_sim = np.full(n, -np.inf, dtype=np.float32)
    all_indices = np.arange(n)

    for start in range(0, n, BLOCK_SIZE):
        end = min(start + BLOCK_SIZE, n)
        sims = x[start:end] @ x.T
        row_offsets = all_indices[start:end] - start
        sims[row_offsets, all_indices[start:end]] = -np.inf
        local_best = np.argmax(sims, axis=1)
        local_sim = sims[np.arange(end - start), local_best]
        best_idx[start:end] = local_best.astype(np.int32)
        best_sim[start:end] = local_sim.astype(np.float32)

    rows_out = []
    for idx, item in enumerate(items):
        target_idx = int(best_idx[idx])
        target = items[target_idx]
        merged = rec.make_item([idx, target_idx], items, rows)
        rows_out.append(
            {
                "cluster_rank": idx + 1,
                "anchor_tag": item.anchor,
                "member_count": len(item.members),
                "mention_count": item.count,
                "pct_total": item.count / total_count * 100.0,
                "current_purity_pct": rec.item_mean_similarity(item, rows) * 100.0,
                "nearest_cluster_rank": target_idx + 1,
                "nearest_anchor_tag": target.anchor,
                "nearest_member_count": len(target.members),
                "nearest_mention_count": target.count,
                "nearest_pct_total": target.count / total_count * 100.0,
                "centroid_similarity_pct": float(best_sim[idx]) * 100.0,
                "merged_anchor_tag": merged.anchor,
                "merged_member_count": len(merged.members),
                "merged_mention_count": merged.count,
                "merged_pct_total": merged.count / total_count * 100.0,
                "merged_purity_pct": rec.item_mean_similarity(merged, rows) * 100.0,
            }
        )
    return rows_out


def write_outputs(rows_out: list[dict[str, object]], total_count: int) -> None:
    with OUT_TSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
                "cluster_rank",
                "anchor_tag",
                "member_count",
                "mention_count",
                "pct_total",
                "current_purity_pct",
                "nearest_cluster_rank",
                "nearest_anchor_tag",
                "nearest_member_count",
                "nearest_mention_count",
                "nearest_pct_total",
                "centroid_similarity_pct",
                "merged_anchor_tag",
                "merged_member_count",
                "merged_mention_count",
                "merged_pct_total",
                "merged_purity_pct",
            ]
        )
        for row in rows_out:
            writer.writerow(
                [
                    row["cluster_rank"],
                    row["anchor_tag"],
                    row["member_count"],
                    row["mention_count"],
                    f"{row['pct_total']:.6f}",
                    f"{row['current_purity_pct']:.2f}",
                    row["nearest_cluster_rank"],
                    row["nearest_anchor_tag"],
                    row["nearest_member_count"],
                    row["nearest_mention_count"],
                    f"{row['nearest_pct_total']:.6f}",
                    f"{row['centroid_similarity_pct']:.2f}",
                    row["merged_anchor_tag"],
                    row["merged_member_count"],
                    row["merged_mention_count"],
                    f"{row['merged_pct_total']:.6f}",
                    f"{row['merged_purity_pct']:.2f}",
                ]
            )

    by_frequency = sorted(rows_out, key=lambda row: (-float(row["pct_total"]), row["anchor_tag"]))
    by_merge_purity = sorted(rows_out, key=lambda row: (-float(row["merged_purity_pct"]), -float(row["pct_total"])))
    by_nearest_similarity = sorted(rows_out, key=lambda row: (-float(row["centroid_similarity_pct"]), -float(row["pct_total"])))

    with OUT_MD.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("# Purity-90 Cluster Nearest Merge Targets\n\n")
        handle.write(
            "This analyzes the original 962-cluster `coarse_online_purity90_split_cultural_reference` result. "
            "For each cluster, it finds the nearest other cluster by centroid similarity and computes the weighted "
            "mean member-to-centroid purity that would result if the pair were merged. No cluster assignments are changed.\n\n"
        )
        handle.write(f"- Total mentions: {total_count}\n")
        handle.write(f"- Clusters analyzed: {len(rows_out)}\n\n")

        handle.write("## Largest Clusters\n\n")
        for row in by_frequency[:80]:
            handle.write(
                f"- `{row['anchor_tag']}` ({row['pct_total']:.4f}%) -> "
                f"`{row['nearest_anchor_tag']}` ({row['nearest_pct_total']:.4f}%), "
                f"centroid sim {row['centroid_similarity_pct']:.2f}%, "
                f"merged purity {row['merged_purity_pct']:.2f}%\n"
            )

        handle.write("\n## Best Merge-Purity Candidates\n\n")
        for row in by_merge_purity[:80]:
            handle.write(
                f"- `{row['anchor_tag']}` ({row['pct_total']:.4f}%) -> "
                f"`{row['nearest_anchor_tag']}` ({row['nearest_pct_total']:.4f}%), "
                f"centroid sim {row['centroid_similarity_pct']:.2f}%, "
                f"merged purity {row['merged_purity_pct']:.2f}%\n"
            )

        handle.write("\n## Nearest Centroid Pairs\n\n")
        for row in by_nearest_similarity[:80]:
            handle.write(
                f"- `{row['anchor_tag']}` ({row['pct_total']:.4f}%) -> "
                f"`{row['nearest_anchor_tag']}` ({row['nearest_pct_total']:.4f}%), "
                f"centroid sim {row['centroid_similarity_pct']:.2f}%, "
                f"merged purity {row['merged_purity_pct']:.2f}%\n"
            )


def main() -> None:
    rows, _unvectorized, total_count, _standalone_count = split_cultural.load_rows_no_cultural_parent()
    items = reconstruct_items(rows)
    rows_out = nearest_targets(items, rows, total_count)
    write_outputs(rows_out, total_count)
    print(f"total={total_count}")
    print(f"clusters={len(items)}")
    print(f"out_tsv={OUT_TSV}")
    print(f"out_md={OUT_MD}")


if __name__ == "__main__":
    main()
