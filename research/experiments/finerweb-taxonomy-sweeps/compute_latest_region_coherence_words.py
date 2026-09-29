from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

import numpy as np

import assign_coarse_tags_to_manual_full_label_child_regions as base
from compute_latest_seed_coverage_v5 import SEEDS


OUT = base.OUT_DIR / "finerweb_latest_region_coherence_words.tsv"


def normalize(vec: np.ndarray) -> np.ndarray | None:
    norm = np.linalg.norm(vec)
    if not norm:
        return None
    return (vec / norm).astype(np.float32)


def top_vocab(seed_rows: list[dict[str, object]], limit: int = 10) -> str:
    counts: Counter[str] = Counter()
    for row in seed_rows:
        for item in row["original_labels"]:
            count = int(item["count"])
            for token in item["tokens"]:
                counts[token] += count
    return "; ".join(f"{word} ({count})" for word, count in counts.most_common(limit))


def main() -> None:
    label_sets = base.load_label_sets()
    rows, total_count = base.load_rows(label_sets)
    vectors = base.ft.load_fasttext(base.collect_needed_words(label_sets))

    for row in rows:
        vec, _vectorized_count, _vectorized_mentions, _matched = base.pooled_vector(row["original_labels"], vectors)
        row["vector"] = vec

    rows_by_tag = {str(row["coarse_tag"]): row for row in rows}
    output_rows = []

    for bucket, tags in SEEDS.items():
        seed_rows = [rows_by_tag[tag] for tag in tags if tag in rows_by_tag]
        vector_rows = [row for row in seed_rows if row.get("vector") is not None]
        weights = np.array([float(row["count"]) for row in vector_rows], dtype=np.float64)
        matrix = np.stack([row["vector"] for row in vector_rows]).astype(np.float32)
        centroid = normalize(np.average(matrix, axis=0, weights=weights))
        sims = matrix @ centroid
        weighted_mean = float(np.average(sims, weights=weights))
        mean = float(np.mean(sims))
        p10 = float(np.percentile(sims, 10))
        min_sim = float(np.min(sims))
        mentions = sum(int(row["count"]) for row in seed_rows)
        output_rows.append(
            {
                "bucket": bucket,
                "seed_tags": len(tags),
                "vectorized_seed_tags": len(vector_rows),
                "seed_mentions": mentions,
                "percent_of_total": mentions / total_count * 100.0,
                "weighted_internal_coherence_pct": weighted_mean * 100.0,
                "mean_internal_coherence_pct": mean * 100.0,
                "p10_internal_coherence_pct": p10 * 100.0,
                "min_internal_coherence_pct": min_sim * 100.0,
                "top_vocab_words": top_vocab(seed_rows),
            }
        )

    output_rows.sort(key=lambda row: -row["seed_mentions"])
    with OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            delimiter="\t",
            lineterminator="\n",
            fieldnames=[
                "bucket",
                "seed_tags",
                "vectorized_seed_tags",
                "seed_mentions",
                "percent_of_total",
                "weighted_internal_coherence_pct",
                "mean_internal_coherence_pct",
                "p10_internal_coherence_pct",
                "min_internal_coherence_pct",
                "top_vocab_words",
            ],
        )
        writer.writeheader()
        for row in output_rows:
            formatted = dict(row)
            for field in (
                "percent_of_total",
                "weighted_internal_coherence_pct",
                "mean_internal_coherence_pct",
                "p10_internal_coherence_pct",
                "min_internal_coherence_pct",
            ):
                formatted[field] = f"{formatted[field]:.2f}"
            writer.writerow(formatted)

    print(f"wrote={OUT}")
    print("bucket\tweighted_internal_coherence_pct\ttop_vocab_words")
    for row in output_rows:
        print(f"{row['bucket']}\t{row['weighted_internal_coherence_pct']:.2f}\t{row['top_vocab_words']}")


if __name__ == "__main__":
    main()
