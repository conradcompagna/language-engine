from __future__ import annotations

import csv
import math
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from sklearn.cluster import MiniBatchKMeans
from sklearn.metrics import silhouette_score

import assign_coarse_tags_to_manual_full_label_child_regions as base
from compute_latest_seed_coverage_v5 import SEEDS


OUT_DIR = base.OUT_DIR
HIGH95_OUT = OUT_DIR / "finerweb_latest_seed_high95_additions.tsv"
SUMMARY_OUT = OUT_DIR / "finerweb_latest_seed_high95_summary.tsv"
SWEEP_OUT = OUT_DIR / "finerweb_latest_seed_residual_cluster_k_sweep.tsv"
CLUSTER_SUMMARY_OUT = OUT_DIR / "finerweb_latest_seed_residual_cluster_summary.tsv"
CLUSTER_MAP_OUT = OUT_DIR / "finerweb_latest_seed_residual_cluster_tag_map.tsv"
REPORT_OUT = OUT_DIR / "finerweb_latest_seed_high95_and_residual_clusters.md"

K_CANDIDATES = (2, 3)
RANDOM_STATE = 19
HIGH_SIM_THRESHOLD = 0.95


def normalized_centers(model: MiniBatchKMeans) -> np.ndarray:
    centers = model.cluster_centers_.astype(np.float32)
    norms = np.linalg.norm(centers, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return centers / norms


def top_words(rows: list[dict[str, object]], limit: int = 18) -> str:
    counts: Counter[str] = Counter()
    for row in rows:
        for item in row["original_labels"]:
            count = int(item["count"])
            for token in item["tokens"]:
                counts[token] += count
    return "; ".join(f"{word} ({count})" for word, count in counts.most_common(limit))


def choose_anchor(rows: list[dict[str, object]], center: np.ndarray) -> dict[str, object]:
    best = None
    for row in rows:
        sim = float(np.dot(row["vector"], center))
        score = sim + 0.02 * math.log1p(int(row["count"]))
        if best is None or score > best[0]:
            best = (score, row)
    return best[1]


def fit_residual_clusters(rows: list[dict[str, object]]):
    x = np.stack([row["vector"] for row in rows]).astype(np.float32)
    weights = np.array([math.sqrt(int(row["count"])) for row in rows], dtype=np.float64)
    scaled_weights = weights / weights.mean()
    sweep_rows = []
    best = None

    for k in K_CANDATES_SAFE(len(rows)):
        model = MiniBatchKMeans(
            n_clusters=k,
            random_state=RANDOM_STATE,
            batch_size=4096,
            n_init=8,
            max_iter=350,
            reassignment_ratio=0.0,
        )
        model.fit(x, sample_weight=scaled_weights)
        labels = model.predict(x)
        centers = normalized_centers(model)
        sims = np.sum(x * centers[labels], axis=1)
        weighted_mean = float(np.average(sims, weights=weights))
        mean = float(np.mean(sims))
        p10 = float(np.percentile(sims, 10))
        sizes = Counter(labels)
        sample_size = min(3000, len(rows))
        silhouette = float(
            silhouette_score(
                x,
                labels,
                metric="cosine",
                sample_size=sample_size,
                random_state=RANDOM_STATE,
            )
        )
        sweep = {
            "k": k,
            "silhouette_cosine_sample": silhouette,
            "weighted_mean_centroid_similarity": weighted_mean,
            "mean_centroid_similarity": mean,
            "p10_centroid_similarity": p10,
            "min_cluster_size": min(sizes.values()),
            "max_cluster_size": max(sizes.values()),
        }
        sweep_rows.append(sweep)
        score = (silhouette, weighted_mean)
        if best is None or score > best[0]:
            best = (score, k, labels, centers, sims)

    return best[1], best[2], best[3], best[4], sweep_rows


def K_CANDATES_SAFE(n: int):
    for k in K_CANDIDATES:
        if 1 < k < n:
            yield k


def main() -> None:
    label_sets = base.load_label_sets()
    rows, total_count = base.load_rows(label_sets)
    vectors = base.ft.load_fasttext(base.collect_needed_words(label_sets))

    for row in rows:
        vec, vectorized_count, vectorized_mentions, matched = base.pooled_vector(row["original_labels"], vectors)
        row["vector"] = vec
        row["vectorized_original_label_count"] = vectorized_count
        row["vectorized_original_label_mentions"] = vectorized_mentions
        row["matched_words"] = matched

    seed_to_bucket = {}
    for bucket, tags in SEEDS.items():
        for tag in tags:
            seed_to_bucket[tag] = bucket

    rows_by_tag = {str(row["coarse_tag"]): row for row in rows}
    seed_rows = []
    missing_seed_vectors = []
    for tag, bucket in seed_to_bucket.items():
        row = rows_by_tag.get(tag)
        if row is None or row.get("vector") is None:
            missing_seed_vectors.append((bucket, tag))
            continue
        seed_rows.append((bucket, tag, row))

    seed_matrix = np.stack([row["vector"] for _bucket, _tag, row in seed_rows]).astype(np.float32)
    seed_buckets = [bucket for bucket, _tag, _row in seed_rows]
    seed_tags = [tag for _bucket, tag, _row in seed_rows]
    seed_set = set(seed_to_bucket)

    high95_rows = []
    residual_rows = []
    no_vector_rows = []

    for row in rows:
        tag = str(row["coarse_tag"])
        if tag in seed_set:
            continue
        vec = row.get("vector")
        if vec is None:
            no_vector_rows.append(row)
            continue
        sims = seed_matrix @ vec
        best_idx = int(np.argmax(sims))
        best_sim = float(sims[best_idx])
        row["nearest_seed_bucket"] = seed_buckets[best_idx]
        row["nearest_seed_tag"] = seed_tags[best_idx]
        row["nearest_seed_similarity"] = best_sim
        if best_sim >= HIGH_SIM_THRESHOLD:
            high95_rows.append(row)
        else:
            residual_rows.append(row)

    high95_by_bucket: defaultdict[str, list[dict[str, object]]] = defaultdict(list)
    for row in high95_rows:
        high95_by_bucket[str(row["nearest_seed_bucket"])].append(row)

    with HIGH95_OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
                "bucket",
                "coarse_tag",
                "count",
                "percent_of_total",
                "matched_seed_tag",
                "similarity_to_seed_pct",
            ]
        )
        for row in sorted(high95_rows, key=lambda item: (str(item["nearest_seed_bucket"]), -int(item["count"]), str(item["coarse_tag"]))):
            writer.writerow(
                [
                    row["nearest_seed_bucket"],
                    row["coarse_tag"],
                    row["count"],
                    f"{row['percent']:.6f}",
                    row["nearest_seed_tag"],
                    f"{float(row['nearest_seed_similarity']) * 100:.2f}",
                ]
            )

    seed_mentions_by_bucket = {
        bucket: sum(int(rows_by_tag[tag]["count"]) for tag in tags if tag in rows_by_tag)
        for bucket, tags in SEEDS.items()
    }
    with SUMMARY_OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
                "bucket",
                "seed_mentions",
                "seed_percent_of_total",
                "high95_added_tags",
                "high95_added_mentions",
                "high95_added_percent_of_total",
                "combined_mentions",
                "combined_percent_of_total",
                "top_high95_additions",
            ]
        )
        for bucket in SEEDS:
            additions = sorted(high95_by_bucket.get(bucket, []), key=lambda row: (-int(row["count"]), str(row["coarse_tag"])))
            added_mentions = sum(int(row["count"]) for row in additions)
            seed_mentions = seed_mentions_by_bucket[bucket]
            top = "; ".join(
                f"{row['coarse_tag']} ({row['count']}, seed={row['nearest_seed_tag']}, sim={float(row['nearest_seed_similarity']) * 100:.2f}%)"
                for row in additions[:20]
            )
            writer.writerow(
                [
                    bucket,
                    seed_mentions,
                    f"{seed_mentions / total_count * 100:.6f}",
                    len(additions),
                    added_mentions,
                    f"{added_mentions / total_count * 100:.6f}",
                    seed_mentions + added_mentions,
                    f"{(seed_mentions + added_mentions) / total_count * 100:.6f}",
                    top,
                ]
            )

    k, labels, centers, sims, sweep_rows = fit_residual_clusters(residual_rows)
    for row, label, sim in zip(residual_rows, labels, sims):
        row["residual_cluster_id"] = int(label)
        row["residual_centroid_similarity"] = float(sim)

    with SWEEP_OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            delimiter="\t",
            lineterminator="\n",
            fieldnames=[
                "k",
                "silhouette_cosine_sample",
                "weighted_mean_centroid_similarity",
                "mean_centroid_similarity",
                "p10_centroid_similarity",
                "min_cluster_size",
                "max_cluster_size",
            ],
        )
        writer.writeheader()
        for row in sweep_rows:
            writer.writerow(row)

    by_cluster: defaultdict[int, list[dict[str, object]]] = defaultdict(list)
    for row in residual_rows:
        by_cluster[int(row["residual_cluster_id"])].append(row)

    summaries = []
    for cluster_id, group_rows in by_cluster.items():
        group_rows.sort(key=lambda row: (-int(row["count"]), str(row["coarse_tag"])))
        mention_count = sum(int(row["count"]) for row in group_rows)
        anchor = choose_anchor(group_rows, centers[cluster_id])
        summaries.append(
            {
                "cluster_id": cluster_id,
                "anchor": anchor,
                "rows": group_rows,
                "tag_count": len(group_rows),
                "mention_count": mention_count,
                "percent": mention_count / total_count * 100.0,
                "weighted_mean_similarity": float(
                    np.average(
                        [float(row["residual_centroid_similarity"]) for row in group_rows],
                        weights=[math.sqrt(int(row["count"])) for row in group_rows],
                    )
                ),
                "top_words": top_words(group_rows),
            }
        )
    summaries.sort(key=lambda item: (-item["percent"], str(item["anchor"]["coarse_tag"])))
    rank_by_cluster = {summary["cluster_id"]: rank for rank, summary in enumerate(summaries, start=1)}

    with CLUSTER_SUMMARY_OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
                "cluster_rank",
                "anchor_tag",
                "tag_count",
                "mention_count",
                "percent_of_total",
                "weighted_mean_centroid_similarity_pct",
                "top_words",
                "top_tags",
            ]
        )
        for rank, summary in enumerate(summaries, start=1):
            top_tags = "; ".join(
                f"{row['coarse_tag']} ({row['count']}, sim={float(row['residual_centroid_similarity']) * 100:.2f}%)"
                for row in summary["rows"][:40]
            )
            writer.writerow(
                [
                    rank,
                    summary["anchor"]["coarse_tag"],
                    summary["tag_count"],
                    summary["mention_count"],
                    f"{summary['percent']:.6f}",
                    f"{summary['weighted_mean_similarity'] * 100:.2f}",
                    summary["top_words"],
                    top_tags,
                ]
            )

    with CLUSTER_MAP_OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
                "coarse_tag",
                "count",
                "percent_of_total",
                "residual_cluster_rank",
                "residual_cluster_anchor",
                "centroid_similarity_pct",
                "nearest_seed_bucket",
                "nearest_seed_tag",
                "nearest_seed_similarity_pct",
            ]
        )
        for row in sorted(residual_rows, key=lambda item: (-int(item["count"]), str(item["coarse_tag"]))):
            rank = rank_by_cluster[int(row["residual_cluster_id"])]
            summary = summaries[rank - 1]
            writer.writerow(
                [
                    row["coarse_tag"],
                    row["count"],
                    f"{row['percent']:.6f}",
                    rank,
                    summary["anchor"]["coarse_tag"],
                    f"{float(row['residual_centroid_similarity']) * 100:.2f}",
                    row["nearest_seed_bucket"],
                    row["nearest_seed_tag"],
                    f"{float(row['nearest_seed_similarity']) * 100:.2f}",
                ]
            )
        for row in sorted(no_vector_rows, key=lambda item: (-int(item["count"]), str(item["coarse_tag"]))):
            writer.writerow([row["coarse_tag"], row["count"], f"{row['percent']:.6f}", "NO_VECTOR", "NO_VECTOR", "", "", "", ""])

    high95_mentions = sum(int(row["count"]) for row in high95_rows)
    residual_mentions = sum(int(row["count"]) for row in residual_rows)
    no_vector_mentions = sum(int(row["count"]) for row in no_vector_rows)
    seed_mentions = sum(seed_mentions_by_bucket.values())

    with REPORT_OUT.open("w", encoding="utf-8", newline="") as handle:
        handle.write("# Latest Seed High-95 Additions And Residual Clusters\n\n")
        handle.write(f"- Total mentions: {total_count}\n")
        handle.write(f"- Seed tags: {len(seed_set)}; seed mentions: {seed_mentions} ({seed_mentions / total_count * 100:.4f}%)\n")
        handle.write(
            f"- High-95 additions: {len(high95_rows)} tags; {high95_mentions} mentions "
            f"({high95_mentions / total_count * 100:.4f}%)\n"
        )
        handle.write(
            f"- Residual clustered: {len(residual_rows)} tags; {residual_mentions} mentions "
            f"({residual_mentions / total_count * 100:.4f}%)\n"
        )
        handle.write(f"- No-vector residual: {len(no_vector_rows)} tags; {no_vector_mentions} mentions ({no_vector_mentions / total_count * 100:.4f}%)\n")
        handle.write(f"- Chosen residual K: {k}\n")
        if missing_seed_vectors:
            handle.write("- Missing seed vectors: " + "; ".join(f"{bucket}: {tag}" for bucket, tag in missing_seed_vectors) + "\n")
        handle.write("\n## Residual Cluster Summaries\n\n")
        for rank, summary in enumerate(summaries, start=1):
            handle.write(f"### {rank}. {summary['anchor']['coarse_tag']}\n\n")
            handle.write(
                f"{summary['tag_count']} tags; {summary['mention_count']} mentions; "
                f"{summary['percent']:.4f}% of total; weighted mean sim {summary['weighted_mean_similarity'] * 100:.2f}%\n\n"
            )
            handle.write(f"Top words: {summary['top_words']}\n\n")
            handle.write("Top tags:\n")
            for row in summary["rows"][:25]:
                handle.write(
                    f"- `{row['coarse_tag']}`: {row['count']}, "
                    f"sim={float(row['residual_centroid_similarity']) * 100:.2f}%, "
                    f"nearest seed={row['nearest_seed_bucket']} / {row['nearest_seed_tag']} "
                    f"({float(row['nearest_seed_similarity']) * 100:.2f}%)\n"
                )
            handle.write("\n")

    print(f"total={total_count}")
    print(f"seed_tags={len(seed_set)}")
    print(f"seed_mentions={seed_mentions}\t{seed_mentions / total_count * 100:.6f}")
    print(f"high95_tags={len(high95_rows)}")
    print(f"high95_mentions={high95_mentions}\t{high95_mentions / total_count * 100:.6f}")
    print(f"residual_vectorized_tags={len(residual_rows)}")
    print(f"residual_mentions={residual_mentions}\t{residual_mentions / total_count * 100:.6f}")
    print(f"no_vector_tags={len(no_vector_rows)}")
    print(f"no_vector_mentions={no_vector_mentions}\t{no_vector_mentions / total_count * 100:.6f}")
    print(f"chosen_residual_k={k}")
    print(f"high95={HIGH95_OUT}")
    print(f"summary={SUMMARY_OUT}")
    print(f"sweep={SWEEP_OUT}")
    print(f"cluster_summary={CLUSTER_SUMMARY_OUT}")
    print(f"cluster_map={CLUSTER_MAP_OUT}")
    print(f"report={REPORT_OUT}")


if __name__ == "__main__":
    main()
