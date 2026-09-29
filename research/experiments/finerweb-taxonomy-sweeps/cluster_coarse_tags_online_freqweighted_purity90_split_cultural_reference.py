from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import numpy as np

import cluster_coarse_tags_snowball_recursive as rec
import cluster_coarse_tags_snowball_recursive_no_cultural_parent_k100 as split_cultural


BASE_DIR = Path(__file__).resolve().parent
OUT_DIR = BASE_DIR / "derived_fasttext_categories"

SUMMARY_OUT = OUT_DIR / "coarse_online_freqweighted_purity90_split_cultural_reference_summary.tsv"
TAG_MAP_OUT = OUT_DIR / "coarse_online_freqweighted_purity90_split_cultural_reference_tag_map.tsv"
REPORT_OUT = OUT_DIR / "coarse_online_freqweighted_purity90_split_cultural_reference_report.md"

PURITY_THRESHOLD = 0.90
TOP_K = 2048
MAX_PASSES = 64
MAX_CANDIDATE_TRIES = 96


@dataclass
class FreqItem:
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


def initial_items(rows: list[dict[str, object]]) -> list[FreqItem]:
    items = []
    for idx, row in enumerate(rows):
        count = int(row["count"])
        vector_sum = row["vector"].astype(np.float32) * float(count)
        items.append(
            FreqItem(
                members=[idx],
                vector_sum=vector_sum,
                vector=normalize(vector_sum),
                count=count,
                anchor=str(row["coarse_tag"]),
            )
        )
    return items


def make_item(item_indices: list[int], items: list[FreqItem], rows: list[dict[str, object]]) -> FreqItem:
    vector_sum = np.zeros_like(items[0].vector_sum)
    members: list[int] = []
    count = 0
    for item_idx in item_indices:
        item = items[item_idx]
        vector_sum += item.vector_sum
        count += item.count
        members.extend(item.members)
    anchor_idx = max(members, key=lambda idx: (int(rows[idx]["count"]), str(rows[idx]["coarse_tag"])))
    return FreqItem(
        members=members,
        vector_sum=vector_sum,
        vector=normalize(vector_sum),
        count=count,
        anchor=str(rows[anchor_idx]["coarse_tag"]),
    )


def item_purity(item: FreqItem) -> float:
    if item.count <= 0:
        return 0.0
    return float(np.dot(item.vector_sum, item.vector) / item.count)


def proposed_merge(item_a: int, item_b: int, items: list[FreqItem], rows: list[dict[str, object]]) -> tuple[FreqItem, float]:
    proposed = make_item([item_a, item_b], items, rows)
    return proposed, item_purity(proposed)


def attraction_score(similarity: float, candidate_count: int) -> float:
    return similarity * np.sqrt(float(candidate_count))


def old_candidate_order(
    item_idx: int,
    active: np.ndarray,
    neighbor_idx: np.ndarray,
    neighbor_sim: np.ndarray,
    items: list[FreqItem],
) -> list[tuple[float, int, float]]:
    candidates = []
    active_existing = active[: neighbor_idx.shape[0]]
    for neighbor, similarity in zip(neighbor_idx[item_idx], neighbor_sim[item_idx]):
        candidate = int(neighbor)
        if not active_existing[candidate]:
            continue
        sim = float(similarity)
        candidates.append((attraction_score(sim, items[candidate].count), candidate, sim))
    candidates.sort(reverse=True)
    return candidates[:MAX_CANDIDATE_TRIES]


def created_candidate_order(
    item: FreqItem,
    items: list[FreqItem],
    active: np.ndarray,
    created_indices: list[int],
) -> list[tuple[float, int, float]]:
    candidates = [idx for idx in created_indices if active[idx]]
    if not candidates:
        return []
    matrix = np.stack([items[idx].vector for idx in candidates]).astype(np.float32)
    sims = matrix @ item.vector
    scored = [
        (attraction_score(float(sim), items[idx].count), idx, float(sim))
        for idx, sim in zip(candidates, sims)
    ]
    scored.sort(reverse=True)
    return scored[:MAX_CANDIDATE_TRIES]


def online_pass(
    items: list[FreqItem],
    rows: list[dict[str, object]],
) -> tuple[list[FreqItem], dict[str, object]]:
    starting_count = len(items)
    x = np.stack([item.vector for item in items]).astype(np.float32)
    neighbor_idx, neighbor_sim = rec.compute_top_neighbors(x, min(TOP_K, max(1, len(items) - 1)))
    active = np.ones(len(items), dtype=bool)
    created_indices: list[int] = []
    order = sorted(range(starting_count), key=lambda idx: (-items[idx].count, items[idx].anchor))

    attempted = 0
    blocked = 0
    merges = 0
    worst_allowed_purity = 1.0

    for item_idx in order:
        if not active[item_idx]:
            continue

        old_candidates = old_candidate_order(item_idx, active, neighbor_idx, neighbor_sim, items)
        created_candidates = created_candidate_order(items[item_idx], items, active, created_indices)
        candidates = sorted(old_candidates + created_candidates, reverse=True)[:MAX_CANDIDATE_TRIES]
        if not candidates:
            continue

        attempted += 1
        accepted = False
        for _score, candidate, _similarity in candidates:
            if candidate == item_idx or not active[candidate]:
                continue
            proposed, purity = proposed_merge(item_idx, candidate, items, rows)
            if purity < PURITY_THRESHOLD:
                blocked += 1
                continue

            active[item_idx] = False
            active[candidate] = False
            items.append(proposed)
            active = np.append(active, True)
            created_indices.append(len(items) - 1)
            merges += 1
            worst_allowed_purity = min(worst_allowed_purity, purity)
            accepted = True
            break

        if not accepted:
            continue

    next_items = [item for idx, item in enumerate(items) if active[idx]]
    next_items.sort(key=lambda item: (-item.count, item.anchor))
    return next_items, {
        "attempted": attempted,
        "blocked": blocked,
        "merges": merges,
        "worst_allowed_purity": worst_allowed_purity,
    }


def run_recursive(rows: list[dict[str, object]], total_count: int) -> tuple[list[FreqItem], list[dict[str, object]]]:
    items = initial_items(rows)
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
    items: list[FreqItem],
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
                    f"{item_purity(item) * 100.0:.2f}",
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
        handle.write("# Online Frequency-Weighted Purity-90 Coarse Tag Clustering\n\n")
        handle.write(
            "Standalone `cultural reference` is included as its own item. "
            "`cultural reference / X` labels are split into standalone orphan `X` items. "
            "Cluster centroids are frequency-weighted: each tag vector contributes proportional to its mention count. "
            "Candidate merge targets are ranked by centroid similarity multiplied by sqrt(target mention count), "
            "so high-frequency clusters act as stronger attractors. A merge is accepted only if the resulting "
            "frequency-weighted member-to-centroid purity remains >= 90%.\n\n"
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
                f"mean sim {item_purity(item) * 100.0:.2f}%\n"
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
