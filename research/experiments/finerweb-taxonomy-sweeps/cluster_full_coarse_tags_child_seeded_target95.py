from __future__ import annotations

import argparse
import csv
from collections import Counter
from pathlib import Path

import numpy as np
from sklearn.cluster import KMeans

import cluster_full_coarse_tags_weighted_child_seeded_k25 as child


BASE_DIR = Path(__file__).resolve().parent
OUT_DIR = BASE_DIR / "derived_fasttext_categories"

MIN_SPLIT_TAGS = 8
RANDOM_STATES = (3, 7, 13, 19, 29)


def output_paths(target_sim: float, max_clusters: int) -> tuple[Path, Path, Path]:
    target = int(round(target_sim * 100))
    return (
        OUT_DIR / f"finerweb_full_coarse_child_seeded_target{target}_max{max_clusters}_summary.tsv",
        OUT_DIR / f"finerweb_full_coarse_child_seeded_target{target}_max{max_clusters}_tag_map.tsv",
        OUT_DIR / f"finerweb_full_coarse_child_seeded_target{target}_max{max_clusters}.md",
    )


def weighted_centroid(x: np.ndarray, weights: np.ndarray) -> np.ndarray:
    center = np.average(x, axis=0, weights=weights)
    norm = np.linalg.norm(center)
    if not norm:
        return center.astype(np.float32)
    return (center / norm).astype(np.float32)


def cluster_stats(indices: list[int], x: np.ndarray, weights: np.ndarray) -> dict[str, object]:
    local_x = x[indices]
    local_w = weights[indices]
    center = weighted_centroid(local_x, local_w)
    sims = local_x @ center
    return {
        "indices": indices,
        "center": center,
        "weighted_mean_similarity": float(np.average(sims, weights=local_w)),
        "min_similarity": float(np.min(sims)),
        "p10_similarity": float(np.percentile(sims, 10)),
        "median_similarity": float(np.median(sims)),
        "weight": float(np.sum(local_w)),
        "tag_count": len(indices),
    }


def split_cluster(indices: list[int], x: np.ndarray, weights: np.ndarray) -> tuple[list[int], list[int]] | None:
    if len(indices) < MIN_SPLIT_TAGS * 2:
        return None

    local_x = x[indices]
    local_w = weights[indices]
    scaled_w = local_w / local_w.mean()
    best = None

    for random_state in RANDOM_STATES:
        model = KMeans(
            n_clusters=2,
            random_state=random_state,
            n_init=12,
            max_iter=400,
            algorithm="lloyd",
        )
        labels = model.fit_predict(local_x, sample_weight=scaled_w)
        left = [indices[i] for i, label in enumerate(labels) if label == 0]
        right = [indices[i] for i, label in enumerate(labels) if label == 1]
        if len(left) < MIN_SPLIT_TAGS or len(right) < MIN_SPLIT_TAGS:
            continue
        left_stats = cluster_stats(left, x, weights)
        right_stats = cluster_stats(right, x, weights)
        combined = (
            left_stats["weighted_mean_similarity"] * left_stats["weight"]
            + right_stats["weighted_mean_similarity"] * right_stats["weight"]
        ) / (left_stats["weight"] + right_stats["weight"])
        balance_penalty = abs(len(left) - len(right)) / len(indices) * 0.002
        score = combined - balance_penalty
        if best is None or score > best[0]:
            best = (score, left, right)

    if best is None:
        return None
    return best[1], best[2]


def recursive_target_clustering(
    x: np.ndarray,
    weights: np.ndarray,
    target_sim: float,
    max_clusters: int,
) -> tuple[list[list[int]], set[int]]:
    clusters = [list(range(len(x)))]
    unsplittable: set[int] = set()

    while len(clusters) < max_clusters:
        stats = [cluster_stats(indices, x, weights) for indices in clusters]
        below = [
            (i, stat)
            for i, stat in enumerate(stats)
            if stat["weighted_mean_similarity"] < target_sim and i not in unsplittable
        ]
        if not below:
            break

        split_index, _stat = min(below, key=lambda item: item[1]["weighted_mean_similarity"])
        split = split_cluster(clusters[split_index], x, weights)
        if split is None:
            unsplittable.add(split_index)
            continue

        left, right = split
        clusters[split_index] = left
        clusters.append(right)
        unsplittable = set()

    return clusters, unsplittable


def top_unigrams(rows: list[dict[str, object]], limit: int = 10) -> str:
    tag_counts: Counter[str] = Counter()
    parent_mentions: Counter[str] = Counter()
    child_mentions: Counter[str] = Counter()
    for row in rows:
        for token in row["tokens"]:
            tag_counts[token] += 1
            parent_mentions[token] += int(row["count"])
        for fine_child in row["children"]:
            for token in fine_child["tokens"]:
                child_mentions[token] += int(fine_child["count"])
    ranked = sorted(
        set(tag_counts) | set(child_mentions),
        key=lambda tok: (parent_mentions[tok] + child_mentions[tok], tag_counts[tok], tok),
        reverse=True,
    )
    return "; ".join(
        f"{tok} ({parent_mentions[tok]} parent mentions, {child_mentions[tok]} child mentions, {tag_counts[tok]} parent tags)"
        for tok in ranked[:limit]
    )


def choose_anchor(cluster_rows: list[dict[str, object]], center: np.ndarray) -> dict[str, object]:
    best = None
    for row in cluster_rows:
        sim = float(np.dot(row["vector"], center))
        score = sim + 0.025 * np.log1p(int(row["count"]))
        if best is None or score > best[0]:
            best = (score, row)
    return best[1]


def build_summaries(
    clusters: list[list[int]],
    rows: list[dict[str, object]],
    x: np.ndarray,
    weights: np.ndarray,
    total_count: int,
) -> list[dict[str, object]]:
    summaries = []
    for cluster_id, indices in enumerate(clusters):
        stat = cluster_stats(indices, x, weights)
        cluster_rows = [rows[index] for index in indices]
        cluster_rows.sort(key=lambda row: (-int(row["count"]), str(row["coarse_tag_english"]), str(row["coarse_tag"])))
        anchor = choose_anchor(cluster_rows, stat["center"])
        mention_count = sum(int(row["count"]) for row in cluster_rows)
        summaries.append(
            {
                "cluster_id": cluster_id,
                "indices": indices,
                "rows": cluster_rows,
                "anchor": anchor,
                "mention_count": mention_count,
                "percent": mention_count / total_count * 100.0,
                "weighted_mean_similarity": stat["weighted_mean_similarity"],
                "min_similarity": stat["min_similarity"],
                "p10_similarity": stat["p10_similarity"],
                "median_similarity": stat["median_similarity"],
                "tag_count": len(indices),
                "top_unigrams": top_unigrams(cluster_rows),
                "center": stat["center"],
            }
        )
    summaries.sort(key=lambda item: (-item["percent"], str(item["anchor"]["coarse_tag_english"])))
    return summaries


def write_outputs(
    summaries: list[dict[str, object]],
    rows: list[dict[str, object]],
    vectorized_rows: list[dict[str, object]],
    unvectorized: list[dict[str, object]],
    total_count: int,
    target_sim: float,
    max_clusters: int,
) -> None:
    summary_out, tag_map_out, report_out = output_paths(target_sim, max_clusters)
    rank_by_cluster = {summary["cluster_id"]: rank for rank, summary in enumerate(summaries, start=1)}
    summary_by_cluster = {summary["cluster_id"]: summary for summary in summaries}
    row_assignment: dict[str, dict[str, object]] = {}
    for summary in summaries:
        center = summary["center"]
        for row in summary["rows"]:
            row_assignment[str(row["coarse_tag"])] = {
                "rank": rank_by_cluster[summary["cluster_id"]],
                "summary": summary,
                "similarity": float(np.dot(row["vector"], center)),
            }

    with summary_out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
                "rank",
                "anchor_tag",
                "anchor_english",
                "tag_count",
                "mention_count",
                "percent_of_total",
                "weighted_mean_similarity_pct",
                "median_similarity_pct",
                "p10_similarity_pct",
                "min_similarity_pct",
                "meets_95_target",
                "top_unigrams_with_child_evidence",
                "top_child_tags",
            ]
        )
        for rank, summary in enumerate(summaries, start=1):
            top_tags = "; ".join(
                f"{row['coarse_tag']} ({row['percent']:.4f}%, sim={float(np.dot(row['vector'], summary['center'])) * 100:.2f}%)"
                for row in summary["rows"][:45]
            )
            writer.writerow(
                [
                    rank,
                    summary["anchor"]["coarse_tag"],
                    summary["anchor"]["coarse_tag_english"],
                    summary["tag_count"],
                    summary["mention_count"],
                    f"{summary['percent']:.6f}",
                    f"{summary['weighted_mean_similarity'] * 100:.2f}",
                    f"{summary['median_similarity'] * 100:.2f}",
                    f"{summary['p10_similarity'] * 100:.2f}",
                    f"{summary['min_similarity'] * 100:.2f}",
                    "yes" if summary["weighted_mean_similarity"] >= target_sim else "no",
                    summary["top_unigrams"],
                    top_tags,
                ]
            )

    with tag_map_out.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
                "coarse_tag",
                "coarse_tag_english",
                "count",
                "percent_of_total",
                "child_vector_count",
                "child_vector_mentions",
                "target95_parent_rank",
                "target95_parent_anchor",
                "target95_parent_anchor_english",
                "similarity_to_parent_centroid_pct",
            ]
        )
        for row in rows:
            assigned = row_assignment.get(str(row["coarse_tag"]))
            if not assigned:
                writer.writerow(
                    [
                        row["coarse_tag"],
                        row["coarse_tag_english"],
                        row["count"],
                        f"{row['percent']:.6f}",
                        row.get("child_vector_count", 0),
                        row.get("child_vector_mentions", 0),
                        "UNVECTORIZED",
                        "UNVECTORIZED",
                        "UNVECTORIZED",
                        "",
                    ]
                )
                continue
            summary = assigned["summary"]
            writer.writerow(
                [
                    row["coarse_tag"],
                    row["coarse_tag_english"],
                    row["count"],
                    f"{row['percent']:.6f}",
                    row.get("child_vector_count", 0),
                    row.get("child_vector_mentions", 0),
                    assigned["rank"],
                    summary["anchor"]["coarse_tag"],
                    summary["anchor"]["coarse_tag_english"],
                    f"{assigned['similarity'] * 100:.2f}",
                ]
            )

    below = [summary for summary in summaries if summary["weighted_mean_similarity"] < target_sim]
    with report_out.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(f"# Full Coarse Tagset Child-Seeded Target-{target_sim * 100:.0f} Clustering\n\n")
        handle.write(
            "This recursively splits child-seeded coarse-tag vector clusters until every cluster reaches "
            f"{target_sim * 100:.0f}% weighted mean similarity to its centroid, or until the cap of {max_clusters} clusters is reached. "
            "Vectors are the same child-seeded vectors as the previous run: 50% parent coarse-label vector "
            "+ 50% frequency-weighted fine-child centroid. Weights are coarse-tag percent of total mentions.\n\n"
        )
        handle.write(f"- Total mentions: {total_count}\n")
        handle.write(f"- Coarse tags: {len(rows)}\n")
        handle.write(f"- Vectorized tags: {len(vectorized_rows)}\n")
        handle.write(f"- Unvectorized tags: {len(unvectorized)}\n")
        handle.write(f"- Cluster cap: {max_clusters}\n")
        handle.write(f"- Clusters produced: {len(summaries)}\n")
        handle.write(f"- Clusters meeting >={target_sim * 100:.0f}% weighted mean similarity: {len(summaries) - len(below)}\n")
        handle.write(f"- Clusters below target: {len(below)}\n")
        handle.write(f"- Singleton vectorized clusters: {sum(1 for summary in summaries if summary['tag_count'] == 1)}\n\n")
        if below:
            handle.write("## Below-Target Clusters\n\n")
            handle.write(
                f"These clusters remain below {target_sim * 100:.0f}% because the cluster cap was reached "
                "or because they became too small to split without making tiny buckets.\n\n"
            )
            for summary in sorted(below, key=lambda item: item["weighted_mean_similarity"]):
                handle.write(
                    f"- `{summary['anchor']['coarse_tag']}`: {summary['weighted_mean_similarity'] * 100:.2f}% "
                    f"weighted mean, {summary['tag_count']} tags, {summary['percent']:.4f}% coverage\n"
                )
            handle.write("\n")
        handle.write("## Clusters\n\n")
        for rank, summary in enumerate(summaries, start=1):
            handle.write(f"### {rank}. {summary['anchor']['coarse_tag']}\n\n")
            handle.write(f"Anchor English: {summary['anchor']['coarse_tag_english']}\n\n")
            handle.write(
                f"Coverage: {summary['percent']:.4f}% of mentions; {summary['mention_count']} mentions; "
                f"{summary['tag_count']} coarse tags\n\n"
            )
            handle.write(
                f"Centroid similarity: weighted mean {summary['weighted_mean_similarity'] * 100:.2f}%, "
                f"median {summary['median_similarity'] * 100:.2f}%, p10 {summary['p10_similarity'] * 100:.2f}%, "
                f"min {summary['min_similarity'] * 100:.2f}%\n\n"
            )
            handle.write(f"Top unigram evidence from parent + children: {summary['top_unigrams']}\n\n")
            handle.write("Top child tags by corpus share:\n")
            for row in summary["rows"][:35]:
                sim = float(np.dot(row["vector"], summary["center"]))
                handle.write(
                    f"- `{row['coarse_tag']}`: {row['percent']:.4f}% ({row['count']}), sim={sim * 100:.2f}%\n"
                )
            handle.write("\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", type=float, default=0.95)
    parser.add_argument("--max-clusters", type=int, default=50)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    target_sim = args.target / 100.0 if args.target > 1 else args.target
    max_clusters = args.max_clusters
    fine_children = child.load_fine_children()
    rows, total_count = child.load_rows(fine_children)
    vectors = child.ft.load_fasttext(child.collect_needed_words(rows))

    vectorized_rows = []
    unvectorized = []
    for row in rows:
        vec = child.enriched_row_vector(row, vectors)
        if vec is None:
            unvectorized.append(row)
            continue
        row["vector"] = vec
        vectorized_rows.append(row)

    x = np.stack([row["vector"] for row in vectorized_rows]).astype(np.float32)
    weights = np.array([float(row["percent"]) for row in vectorized_rows], dtype=np.float64)
    clusters, _unsplittable = recursive_target_clustering(x, weights, target_sim, max_clusters)
    summaries = build_summaries(clusters, vectorized_rows, x, weights, total_count)
    write_outputs(summaries, rows, vectorized_rows, unvectorized, total_count, target_sim, max_clusters)

    summary_out, tag_map_out, report_out = output_paths(target_sim, max_clusters)
    below = [summary for summary in summaries if summary["weighted_mean_similarity"] < target_sim]
    print(f"total={total_count}")
    print(f"tags={len(rows)}")
    print(f"vectorized={len(vectorized_rows)}")
    print(f"unvectorized={len(unvectorized)}")
    print(f"target={target_sim:.2f}")
    print(f"max_clusters={max_clusters}")
    print(f"clusters={len(summaries)}")
    print(f"meeting_target={len(summaries) - len(below)}")
    print(f"below_target={len(below)}")
    print(f"singletons={sum(1 for summary in summaries if summary['tag_count'] == 1)}")
    print(f"min_weighted_mean_similarity={min(summary['weighted_mean_similarity'] for summary in summaries) * 100:.2f}")
    print(f"wrote={summary_out}")
    print(f"tag_map={tag_map_out}")
    print(f"report={report_out}")


if __name__ == "__main__":
    main()
