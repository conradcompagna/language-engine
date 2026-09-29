from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

import cluster_coarse_tags_snowball_recursive as rec
import cluster_coarse_tags_pairwise_member_purity90_cultural_modes as pairwise


BASE_DIR = Path(__file__).resolve().parent
OUT_DIR = BASE_DIR / "derived_fasttext_categories"

TAG_MAP_IN = OUT_DIR / "coarse_pairwise_member_purity90_cultural_modes_tag_map.tsv"
SUMMARY_IN = OUT_DIR / "coarse_pairwise_member_purity90_cultural_modes_summary.tsv"
TSV_OUT = OUT_DIR / "coarse_pairwise_member_purity90_intact_collapse_targets.tsv"
MD_OUT = OUT_DIR / "coarse_pairwise_member_purity90_intact_collapse_targets.md"

MODE = "intact_cultural_reference"
TOP_K = 2048


def load_intact_cluster_members(rows: list[dict[str, object]]) -> dict[int, list[int]]:
    row_by_tag = {str(row["coarse_tag"]): idx for idx, row in enumerate(rows)}
    clusters: dict[int, list[int]] = {}
    with TAG_MAP_IN.open("r", encoding="utf-8", newline="") as handle:
        for line in csv.DictReader(handle, delimiter="\t"):
            if line["cultural_mode"] != MODE or line["cluster_rank"] == "UNVECTORIZED":
                continue
            tag = line["coarse_tag"]
            if tag not in row_by_tag:
                raise KeyError(tag)
            rank = int(line["cluster_rank"])
            clusters.setdefault(rank, []).append(row_by_tag[tag])
    return clusters


def load_summary_rows() -> dict[int, dict[str, str]]:
    summaries = {}
    with SUMMARY_IN.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            if row["cultural_mode"] != MODE:
                continue
            summaries[int(row["cluster_rank"])] = row
    return summaries


def make_cluster(members: list[int], rows: list[dict[str, object]]) -> pairwise.PairwiseCluster:
    cluster = pairwise.make_singleton(members[0], rows)
    for row_idx in members[1:]:
        other = pairwise.make_singleton(row_idx, rows)
        cluster, _purity = pairwise.merged_cluster(cluster, other, rows)
    return cluster


def exact_best_member_bridge(
    cluster_rank: int,
    cluster_members: list[int],
    assignment: np.ndarray,
    x: np.ndarray,
) -> tuple[int | None, int | None, float]:
    mask = assignment != cluster_rank
    candidates = np.flatnonzero(mask)
    if not len(candidates):
        return None, None, -np.inf
    best_source = None
    best_target = None
    best_sim = -np.inf
    candidate_x = x[candidates]
    for source_idx in cluster_members:
        sims = candidate_x @ x[source_idx]
        best_pos = int(np.argmax(sims))
        sim = float(sims[best_pos])
        if sim > best_sim:
            best_sim = sim
            best_source = source_idx
            best_target = int(candidates[best_pos])
    return best_source, best_target, best_sim


def best_member_bridge(
    cluster_rank: int,
    cluster_members: list[int],
    assignment: np.ndarray,
    neighbor_idx: np.ndarray,
    neighbor_sim: np.ndarray,
    x: np.ndarray,
) -> tuple[int | None, int | None, float]:
    best_source = None
    best_target = None
    best_sim = -np.inf
    for source_idx in cluster_members:
        for target_idx, sim in zip(neighbor_idx[source_idx], neighbor_sim[source_idx]):
            target_idx = int(target_idx)
            if int(assignment[target_idx]) == cluster_rank:
                continue
            if float(sim) > best_sim:
                best_source = source_idx
                best_target = target_idx
                best_sim = float(sim)
            break
    if best_target is not None:
        return best_source, best_target, best_sim
    return exact_best_member_bridge(cluster_rank, cluster_members, assignment, x)


def main() -> None:
    rows, unvectorized, total_count = pairwise.load_intact_rows()
    cluster_members = load_intact_cluster_members(rows)
    summaries = load_summary_rows()
    clusters = {rank: make_cluster(members, rows) for rank, members in cluster_members.items()}

    x = np.stack([row["vector"] for row in rows]).astype(np.float32)
    neighbor_idx, neighbor_sim = rec.compute_top_neighbors(x, min(TOP_K, max(1, len(rows) - 1)))
    assignment = np.full(len(rows), -1, dtype=np.int32)
    for rank, members in cluster_members.items():
        for row_idx in members:
            assignment[row_idx] = rank

    output_rows = []
    for rank in sorted(clusters, key=lambda item: (-clusters[item].count, summaries[item]["anchor_tag"])):
        cluster = clusters[rank]
        source_idx, target_idx, bridge_sim = best_member_bridge(
            rank,
            cluster_members[rank],
            assignment,
            neighbor_idx,
            neighbor_sim,
            x,
        )
        if target_idx is None:
            continue
        target_rank = int(assignment[target_idx])
        target = clusters[target_rank]
        merged, merged_purity = pairwise.merged_cluster(cluster, target, rows)
        source_centroid = pairwise.rec.normalize(cluster.weighted_vector_sum.astype(np.float32))
        target_centroid = pairwise.rec.normalize(target.weighted_vector_sum.astype(np.float32))
        centroid_sim = float(np.dot(source_centroid, target_centroid))
        output_rows.append(
            {
                "cluster_rank": rank,
                "anchor_tag": summaries[rank]["anchor_tag"],
                "mention_count": cluster.count,
                "pct_total": cluster.count / total_count * 100.0,
                "member_count": len(cluster.members),
                "current_pairwise_purity_pct": pairwise.cluster_purity(cluster) * 100.0,
                "target_cluster_rank": target_rank,
                "target_anchor_tag": summaries[target_rank]["anchor_tag"],
                "target_mention_count": target.count,
                "target_pct_total": target.count / total_count * 100.0,
                "target_member_count": len(target.members),
                "bridge_source_tag": rows[source_idx]["coarse_tag"] if source_idx is not None else "",
                "bridge_target_tag": rows[target_idx]["coarse_tag"],
                "best_member_pair_similarity_pct": bridge_sim * 100.0,
                "centroid_similarity_pct": centroid_sim * 100.0,
                "merged_mention_count": merged.count,
                "merged_pct_total": merged.count / total_count * 100.0,
                "merged_pairwise_purity_pct": merged_purity * 100.0,
                "would_pass_90": "yes" if merged_purity >= pairwise.PURITY_THRESHOLD else "no",
                "top_tags": summaries[rank]["top_tags"],
                "target_top_tags": summaries[target_rank]["top_tags"],
            }
        )

    with TSV_OUT.open("w", encoding="utf-8", newline="") as handle:
        fields = [
            "cluster_rank",
            "anchor_tag",
            "mention_count",
            "pct_total",
            "member_count",
            "current_pairwise_purity_pct",
            "target_cluster_rank",
            "target_anchor_tag",
            "target_mention_count",
            "target_pct_total",
            "target_member_count",
            "bridge_source_tag",
            "bridge_target_tag",
            "best_member_pair_similarity_pct",
            "centroid_similarity_pct",
            "merged_mention_count",
            "merged_pct_total",
            "merged_pairwise_purity_pct",
            "would_pass_90",
            "top_tags",
            "target_top_tags",
        ]
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in output_rows:
            writer.writerow(
                {
                    key: f"{value:.6f}" if isinstance(value, float) else value
                    for key, value in row.items()
                }
            )

    with MD_OUT.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("# Intact Cultural Reference Pairwise-90 Collapse Targets\n\n")
        handle.write(
            "For each pairwise-90 cluster, this reports the nearest potential collapse target using the strongest individual member-to-member bridge. "
            "It also reports the resulting frequency-weighted internal pairwise purity if the whole source cluster were merged into that target.\n\n"
        )
        handle.write(f"- Total mentions: {total_count}\n")
        handle.write(f"- Vectorized items: {len(rows)}\n")
        handle.write(f"- Unvectorized items: {len(unvectorized)}\n")
        handle.write(f"- Clusters: {len(clusters)}\n\n")
        handle.write("## High-Frequency Clusters\n\n")
        for row in output_rows[:200]:
            handle.write(
                f"- `{row['anchor_tag']}` ({row['pct_total']:.4f}%) -> `{row['target_anchor_tag']}` "
                f"({row['target_pct_total']:.4f}%); bridge `{row['bridge_source_tag']}` -> `{row['bridge_target_tag']}` "
                f"{row['best_member_pair_similarity_pct']:.2f}%; centroid {row['centroid_similarity_pct']:.2f}%; "
                f"merged purity {row['merged_pairwise_purity_pct']:.2f}%"
                f"{' PASS' if row['would_pass_90'] == 'yes' else ''}\n"
            )
        handle.write("\n## Strong Candidate Collapses Passing 90%\n\n")
        passing = [row for row in output_rows if row["would_pass_90"] == "yes"]
        passing.sort(key=lambda row: (-row["mention_count"], row["anchor_tag"]))
        for row in passing[:300]:
            handle.write(
                f"- `{row['anchor_tag']}` ({row['pct_total']:.4f}%) -> `{row['target_anchor_tag']}` "
                f"({row['target_pct_total']:.4f}%); merged purity {row['merged_pairwise_purity_pct']:.2f}%; "
                f"bridge `{row['bridge_source_tag']}` -> `{row['bridge_target_tag']}` {row['best_member_pair_similarity_pct']:.2f}%\n"
            )

    passing_count = sum(1 for row in output_rows if row["would_pass_90"] == "yes")
    passing_mentions = sum(row["mention_count"] for row in output_rows if row["would_pass_90"] == "yes")
    print(f"mode={MODE}")
    print(f"clusters={len(clusters)}")
    print(f"rows={len(rows)}")
    print(f"unvectorized={len(unvectorized)}")
    print(f"passing_90_targets={passing_count}")
    print(f"passing_90_source_pct={passing_mentions / total_count * 100.0:.4f}")
    print(f"tsv={TSV_OUT}")
    print(f"md={MD_OUT}")


if __name__ == "__main__":
    main()
