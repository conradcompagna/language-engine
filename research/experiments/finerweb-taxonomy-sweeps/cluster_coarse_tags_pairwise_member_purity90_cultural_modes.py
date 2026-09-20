from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

import numpy as np

import cluster_coarse_tags_snowball_recursive as rec
import cluster_coarse_tags_snowball_recursive_no_cultural_parent_k100 as split_cultural


BASE_DIR = Path(__file__).resolve().parent
OUT_DIR = BASE_DIR / "derived_fasttext_categories"

SUMMARY_OUT = OUT_DIR / "coarse_pairwise_member_purity90_cultural_modes_summary.tsv"
TAG_MAP_OUT = OUT_DIR / "coarse_pairwise_member_purity90_cultural_modes_tag_map.tsv"
REPORT_OUT = OUT_DIR / "coarse_pairwise_member_purity90_cultural_modes_report.md"

PURITY_THRESHOLD = 0.90
TOP_K = 2048
MAX_PASSES = 64


@dataclass
class PairwiseCluster:
    members: list[int]
    weighted_vector_sum: np.ndarray
    weight_sum: float
    pair_num: float
    pair_den: float
    count: int
    anchor: str
    active: bool = True


def make_singleton(row_idx: int, rows: list[dict[str, object]]) -> PairwiseCluster:
    weight = float(rows[row_idx]["count"])
    vector = rows[row_idx]["vector"].astype(np.float64)
    return PairwiseCluster(
        members=[row_idx],
        weighted_vector_sum=vector * weight,
        weight_sum=weight,
        pair_num=0.0,
        pair_den=0.0,
        count=int(rows[row_idx]["count"]),
        anchor=str(rows[row_idx]["coarse_tag"]),
    )


def merged_cluster(
    left: PairwiseCluster,
    right: PairwiseCluster,
    rows: list[dict[str, object]],
) -> tuple[PairwiseCluster, float]:
    cross_num = float(np.dot(left.weighted_vector_sum, right.weighted_vector_sum))
    cross_den = left.weight_sum * right.weight_sum
    pair_num = left.pair_num + right.pair_num + cross_num
    pair_den = left.pair_den + right.pair_den + cross_den
    purity = pair_num / pair_den if pair_den else 1.0

    members = left.members + right.members
    anchor_idx = max(members, key=lambda idx: (int(rows[idx]["count"]), str(rows[idx]["coarse_tag"])))
    return (
        PairwiseCluster(
            members=members,
            weighted_vector_sum=left.weighted_vector_sum + right.weighted_vector_sum,
            weight_sum=left.weight_sum + right.weight_sum,
            pair_num=pair_num,
            pair_den=pair_den,
            count=left.count + right.count,
            anchor=str(rows[anchor_idx]["coarse_tag"]),
        ),
        purity,
    )


def cluster_purity(cluster: PairwiseCluster) -> float:
    if not cluster.pair_den:
        return 1.0
    return cluster.pair_num / cluster.pair_den


def exact_best_outside_cluster(
    row_idx: int,
    x: np.ndarray,
    assignment: np.ndarray,
) -> tuple[int | None, float]:
    current_cluster = int(assignment[row_idx])
    candidates = np.flatnonzero(assignment != current_cluster)
    if not len(candidates):
        return None, -np.inf
    sims = x[candidates] @ x[row_idx]
    best_pos = int(np.argmax(sims))
    return int(candidates[best_pos]), float(sims[best_pos])


def best_outside_cluster(
    row_idx: int,
    neighbor_idx: np.ndarray,
    neighbor_sim: np.ndarray,
    x: np.ndarray,
    assignment: np.ndarray,
) -> tuple[int | None, float]:
    current_cluster = int(assignment[row_idx])
    for candidate, similarity in zip(neighbor_idx[row_idx], neighbor_sim[row_idx]):
        if int(assignment[int(candidate)]) != current_cluster:
            return int(candidate), float(similarity)
    return exact_best_outside_cluster(row_idx, x, assignment)


def run_pairwise_member_purity(
    rows: list[dict[str, object]],
    total_count: int,
) -> tuple[list[PairwiseCluster], list[dict[str, object]]]:
    x = np.stack([row["vector"] for row in rows]).astype(np.float32)
    neighbor_idx, neighbor_sim = rec.compute_top_neighbors(x, min(TOP_K, max(1, len(rows) - 1)))

    clusters = [make_singleton(idx, rows) for idx in range(len(rows))]
    assignment = np.arange(len(rows), dtype=np.int32)
    order = sorted(range(len(rows)), key=lambda idx: (-int(rows[idx]["count"]), str(rows[idx]["coarse_tag"])))

    log: list[dict[str, object]] = [
        {
            "pass": 0,
            "clusters": len(clusters),
            "top25_pct": 0.0,
            "attempted": "",
            "merged": "",
            "blocked": "",
            "worst_accepted_purity": "",
            "best_blocked_similarity": "",
        }
    ]

    for pass_num in range(1, MAX_PASSES + 1):
        attempted = 0
        merged = 0
        blocked = 0
        worst_accepted_purity = 1.0
        best_blocked_similarity = -np.inf

        for row_idx in order:
            current_id = int(assignment[row_idx])
            if not clusters[current_id].active:
                continue
            candidate_row, similarity = best_outside_cluster(row_idx, neighbor_idx, neighbor_sim, x, assignment)
            if candidate_row is None:
                continue

            candidate_id = int(assignment[candidate_row])
            if candidate_id == current_id or not clusters[candidate_id].active:
                continue

            attempted += 1
            proposed, purity = merged_cluster(clusters[current_id], clusters[candidate_id], rows)
            if purity < PURITY_THRESHOLD:
                blocked += 1
                best_blocked_similarity = max(best_blocked_similarity, similarity)
                continue

            clusters[current_id].active = False
            clusters[candidate_id].active = False
            new_id = len(clusters)
            clusters.append(proposed)
            for member_idx in proposed.members:
                assignment[member_idx] = new_id
            merged += 1
            worst_accepted_purity = min(worst_accepted_purity, purity)

        active_clusters = [cluster for cluster in clusters if cluster.active]
        active_clusters.sort(key=lambda cluster: (-cluster.count, cluster.anchor))
        top25_pct = sum(cluster.count for cluster in active_clusters[:25]) / total_count * 100.0
        log.append(
            {
                "pass": pass_num,
                "clusters": len(active_clusters),
                "top25_pct": top25_pct,
                "attempted": attempted,
                "merged": merged,
                "blocked": blocked,
                "worst_accepted_purity": worst_accepted_purity,
                "best_blocked_similarity": best_blocked_similarity,
            }
        )
        if merged == 0:
            return active_clusters, log

    active_clusters = [cluster for cluster in clusters if cluster.active]
    active_clusters.sort(key=lambda cluster: (-cluster.count, cluster.anchor))
    return active_clusters, log


def load_intact_rows() -> tuple[list[dict[str, object]], list[dict[str, object]], int]:
    rows, unvectorized, total_count = rec.load_vectorized_rows()
    for row in rows:
        row.setdefault("source_kind", "coarse_intact")
        row.setdefault("source_labels", str(row["coarse_tag"]))
        row["percent"] = int(row["count"]) / total_count * 100.0
    for row in unvectorized:
        row.setdefault("source_kind", "coarse_intact")
        row.setdefault("source_labels", str(row["coarse_tag"]))
        row["percent"] = int(row["count"]) / total_count * 100.0
    return rows, unvectorized, total_count


def write_outputs(
    results: list[
        tuple[
            str,
            list[dict[str, object]],
            list[dict[str, object]],
            int,
            list[PairwiseCluster],
            list[dict[str, object]],
        ]
    ],
) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    with SUMMARY_OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
                "cultural_mode",
                "pass",
                "cluster_count",
                "top25_pct",
                "cluster_rank",
                "anchor_tag",
                "member_count",
                "mention_count",
                "pct_total",
                "weighted_pairwise_purity_pct",
                "top_tags",
            ]
        )
        for mode, rows, _unvectorized, total_count, clusters, log in results:
            final = log[-1]
            ranked = sorted(clusters, key=lambda cluster: (-cluster.count, cluster.anchor))
            for rank, cluster in enumerate(ranked, start=1):
                top_members = sorted(
                    cluster.members,
                    key=lambda idx: (-int(rows[idx]["count"]), str(rows[idx]["coarse_tag"]), str(rows[idx].get("source_kind", ""))),
                )[:40]
                writer.writerow(
                    [
                        mode,
                        final["pass"],
                        final["clusters"],
                        f"{final['top25_pct']:.6f}",
                        rank,
                        cluster.anchor,
                        len(cluster.members),
                        cluster.count,
                        f"{cluster.count / total_count * 100.0:.6f}",
                        f"{cluster_purity(cluster) * 100.0:.2f}",
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
                "cultural_mode",
                "coarse_tag",
                "count",
                "pct_total",
                "source_kind",
                "source_labels",
                "cluster_rank",
                "anchor_tag",
            ]
        )
        for mode, rows, unvectorized, total_count, clusters, _log in results:
            ranked = sorted(clusters, key=lambda cluster: (-cluster.count, cluster.anchor))
            for rank, cluster in enumerate(ranked, start=1):
                for idx in sorted(
                    cluster.members,
                    key=lambda row_idx: (-int(rows[row_idx]["count"]), str(rows[row_idx]["coarse_tag"]), str(rows[row_idx].get("source_kind", ""))),
                ):
                    writer.writerow(
                        [
                            mode,
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
                        mode,
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
        handle.write("# Pairwise-Member Purity-90 Coarse Tag Clustering\n\n")
        handle.write(
            "This run does not use merged centroids as merge targets. "
            "Each original tag keeps its individual vector. For each tag in descending-frequency order, "
            "the algorithm finds that tag's nearest individual tag outside its current cluster. "
            "It merges the two clusters only if the resulting cluster's frequency-weighted internal pairwise similarity remains >= 90%. "
            "Internal purity is the weighted mean similarity over all unordered member pairs.\n\n"
        )
        for mode, rows, unvectorized, total_count, clusters, log in results:
            ranked = sorted(clusters, key=lambda cluster: (-cluster.count, cluster.anchor))
            handle.write(f"## {mode}\n\n")
            handle.write(f"- Total mentions: {total_count}\n")
            handle.write(f"- Vectorized items: {len(rows)}\n")
            handle.write(f"- Unvectorized items: {len(unvectorized)}\n")
            handle.write(f"- Final clusters: {len(ranked)}\n")
            handle.write(f"- Top 25 coverage: {sum(cluster.count for cluster in ranked[:25]) / total_count * 100.0:.4f}%\n\n")
            handle.write("### Pass Log\n\n")
            for row in log:
                if row["pass"] == 0:
                    handle.write(f"- pass 0: {row['clusters']} clusters\n")
                    continue
                worst = row["worst_accepted_purity"]
                blocked = row["best_blocked_similarity"]
                handle.write(
                    f"- pass {row['pass']}: {row['clusters']} clusters, top25 {row['top25_pct']:.4f}%, "
                    f"attempted {row['attempted']}, merged {row['merged']}, blocked {row['blocked']}, "
                    f"worst accepted purity {float(worst) * 100.0:.2f}%, "
                    f"best blocked pair sim {float(blocked) * 100.0:.2f}%\n"
                )
            handle.write("\n### Final Clusters\n\n")
            for rank, cluster in enumerate(ranked[:150], start=1):
                top_members = sorted(
                    cluster.members,
                    key=lambda idx: (-int(rows[idx]["count"]), str(rows[idx]["coarse_tag"]), str(rows[idx].get("source_kind", ""))),
                )[:18]
                handle.write(
                    f"{rank}. `{cluster.anchor}`: {cluster.count} mentions "
                    f"({cluster.count / total_count * 100.0:.4f}%), {len(cluster.members)} tags, "
                    f"pairwise purity {cluster_purity(cluster) * 100.0:.2f}%\n"
                )
                handle.write(
                    "   - "
                    + "; ".join(
                        f"`{rows[idx]['coarse_tag']}` ({rows[idx]['count']}, {rows[idx].get('source_kind', '')})"
                        for idx in top_members
                    )
                    + "\n"
                )
            handle.write("\n")


def main() -> None:
    fragmented_rows, fragmented_unvectorized, fragmented_total, standalone_count = split_cultural.load_rows_no_cultural_parent()
    intact_rows, intact_unvectorized, intact_total = load_intact_rows()

    results = []
    for mode, rows, unvectorized, total_count in [
        ("fragmented_cultural_reference", fragmented_rows, fragmented_unvectorized, fragmented_total),
        ("intact_cultural_reference", intact_rows, intact_unvectorized, intact_total),
    ]:
        clusters, log = run_pairwise_member_purity(rows, total_count)
        results.append((mode, rows, unvectorized, total_count, clusters, log))
        ranked = sorted(clusters, key=lambda cluster: (-cluster.count, cluster.anchor))
        print(
            f"{mode}: total={total_count} vectorized={len(rows)} unvectorized={len(unvectorized)} "
            f"passes={log[-1]['pass']} clusters={len(ranked)} "
            f"top25_pct={sum(cluster.count for cluster in ranked[:25]) / total_count * 100.0:.4f} "
            f"largest_pct={ranked[0].count / total_count * 100.0:.4f}"
        )

    write_outputs(results)
    print(f"standalone_cultural_reference_mentions_fragmented={standalone_count}")
    print(f"summary={SUMMARY_OUT}")
    print(f"tag_map={TAG_MAP_OUT}")
    print(f"report={REPORT_OUT}")


if __name__ == "__main__":
    main()
