from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

import cluster_coarse_tags_online_purity90_split_cultural_reference as purity90
import cluster_coarse_tags_snowball_recursive as rec
import cluster_coarse_tags_snowball_recursive_no_cultural_parent_k100 as split_cultural


BASE_DIR = Path(__file__).resolve().parent
OUT_DIR = BASE_DIR / "derived_fasttext_categories"

SUMMARY_OUT = OUT_DIR / "coarse_online_purity90_postmerge_min1pct_summary.tsv"
TAG_MAP_OUT = OUT_DIR / "coarse_online_purity90_postmerge_min1pct_tag_map.tsv"
REPORT_OUT = OUT_DIR / "coarse_online_purity90_postmerge_min1pct_report.md"

MIN_SHARE = 0.01


def postmerge_min_share(
    items: list[rec.Item],
    rows: list[dict[str, object]],
    total_count: int,
) -> tuple[list[rec.Item], list[dict[str, object]]]:
    items = list(items)
    log = []

    while True:
        items.sort(key=lambda item: (item.count, item.anchor))
        small_indices = [idx for idx, item in enumerate(items) if item.count / total_count < MIN_SHARE]
        if not small_indices:
            break
        source_idx = small_indices[0]
        source = items[source_idx]

        candidates = [idx for idx in range(len(items)) if idx != source_idx]
        if not candidates:
            break
        matrix = np.stack([items[idx].vector for idx in candidates]).astype(np.float32)
        sims = matrix @ source.vector
        best_pos = int(np.argmax(sims))
        target_idx = candidates[best_pos]
        target = items[target_idx]

        proposed = rec.make_item([source_idx, target_idx], items, rows)
        old_source_share = source.count / total_count * 100.0
        old_target_share = target.count / total_count * 100.0
        merged_share = proposed.count / total_count * 100.0
        log.append(
            {
                "step": len(log) + 1,
                "source": source.anchor,
                "source_count": source.count,
                "source_pct": old_source_share,
                "target": target.anchor,
                "target_count": target.count,
                "target_pct": old_target_share,
                "similarity": float(sims[best_pos]) * 100.0,
                "merged_anchor": proposed.anchor,
                "merged_count": proposed.count,
                "merged_pct": merged_share,
                "merged_purity": rec.item_mean_similarity(proposed, rows) * 100.0,
            }
        )

        for idx in sorted([source_idx, target_idx], reverse=True):
            del items[idx]
        items.append(proposed)

    items.sort(key=lambda item: (-item.count, item.anchor))
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
            )[:60]
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
        handle.write("# Online Purity-90 Postmerge Minimum 1 Percent\n\n")
        handle.write(
            "This is a postpass over `coarse_online_purity90_split_cultural_reference_*`. "
            "The original purity-90 files are untouched. Any cluster below 1% of total mentions "
            "is repeatedly merged into its nearest remaining cluster, allowing purity to drop.\n\n"
        )
        handle.write(f"- Total mentions: {total_count}\n")
        handle.write(f"- Final clusters: {len(ranked)}\n")
        handle.write(f"- Minimum cluster share: {MIN_SHARE * 100:.2f}%\n")
        handle.write(f"- Postmerge steps: {len(log)}\n\n")

        handle.write("## Final Clusters\n\n")
        for rank, item in enumerate(ranked, start=1):
            top_members = sorted(
                item.members,
                key=lambda idx: (-int(rows[idx]["count"]), str(rows[idx]["coarse_tag"]), str(rows[idx].get("source_kind", ""))),
            )[:20]
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

        handle.write("\n## Merge Log\n\n")
        for entry in log[:500]:
            handle.write(
                f"- {entry['step']}. `{entry['source']}` ({entry['source_pct']:.4f}%) -> "
                f"`{entry['target']}` ({entry['target_pct']:.4f}%), "
                f"sim {entry['similarity']:.2f}%, merged `{entry['merged_anchor']}` "
                f"({entry['merged_pct']:.4f}%), purity {entry['merged_purity']:.2f}%\n"
            )
        if len(log) > 500:
            handle.write(f"\n... {len(log) - 500} additional merge steps omitted from report; full result is in TSV files.\n")


def main() -> None:
    rows, unvectorized, total_count, _standalone_count = split_cultural.load_rows_no_cultural_parent()
    base_items, base_log = purity90.run_recursive(rows, total_count)
    merged_items, merge_log = postmerge_min_share(base_items, rows, total_count)
    write_outputs(rows, unvectorized, total_count, merged_items, merge_log)

    top25_pct = sum(item.count for item in sorted(merged_items, key=lambda item: -item.count)[:25]) / total_count * 100.0
    largest_pct = max(item.count for item in merged_items) / total_count * 100.0
    print(f"total={total_count}")
    print(f"base_clusters={len(base_items)}")
    print(f"base_passes={base_log[-1]['pass']}")
    print(f"postmerge_steps={len(merge_log)}")
    print(f"final_clusters={len(merged_items)}")
    print(f"top25_pct={top25_pct:.4f}")
    print(f"largest_pct={largest_pct:.4f}")
    print(f"summary={SUMMARY_OUT}")
    print(f"tag_map={TAG_MAP_OUT}")
    print(f"report={REPORT_OUT}")


if __name__ == "__main__":
    main()
