from __future__ import annotations

import csv
from collections import defaultdict

import numpy as np

import analyze_user_taxonomy_outliers_fasttext as full
import assign_coarse_tags_to_manual_full_label_child_regions as base


full.OUT_TSV = full.OUT_DIR / "user_13_bucket_fasttext_outliers_fine_only.tsv"
full.OUT_MD = full.OUT_DIR / "user_13_bucket_fasttext_outliers_fine_only.md"
OUT_CROSS_TSV = full.OUT_DIR / "user_13_bucket_fasttext_outliers_fine_only_cross_bucket_all.tsv"
OUT_CROSS_BY_BUCKET_MD = full.OUT_DIR / "user_13_bucket_fasttext_outliers_fine_only_cross_bucket_by_bucket.md"
OUT_CROSS_BY_BUCKET_TSV = full.OUT_DIR / "user_13_bucket_fasttext_outliers_fine_only_cross_bucket_by_bucket.tsv"
OUT_CROSS_BY_BUCKET_GT10_MD = full.OUT_DIR / "user_13_bucket_fasttext_outliers_fine_only_cross_bucket_by_bucket_gt10.md"
OUT_CROSS_BY_BUCKET_GT10_TSV = full.OUT_DIR / "user_13_bucket_fasttext_outliers_fine_only_cross_bucket_by_bucket_gt10.tsv"
STRONG_MARGIN_PCT = 10.0


def vectorize_rows(rows: list[dict[str, object]]) -> None:
    needed = set()
    for row in rows:
        row["vector_text"] = full.fine_vector_text(str(row["tag"]))
        row["tokens"] = base.text_tokens(str(row["vector_text"]))
        for token in row["tokens"]:
            needed.update(base.vector_variants(token))
    vectors = base.ft.load_fasttext(needed)
    for row in rows:
        vec, matched = base.label_vector(row, vectors)
        row["vector"] = vec
        row["matched_words"] = "; ".join(matched)


def write_outputs(rows: list[dict[str, object]]) -> None:
    full.OUT_DIR.mkdir(parents=True, exist_ok=True)
    with full.OUT_TSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
                "bucket",
                "tag",
                "vector_text",
                "count",
                "own_similarity_pct",
                "nearest_bucket",
                "nearest_similarity_pct",
                "margin_to_nearest_other_pct",
                "matched_words",
            ]
        )
        for row in sorted(rows, key=lambda r: (r["bucket"], float(r["own_similarity"] or -1), -int(r["count"]))):
            writer.writerow(
                [
                    row["bucket"],
                    row["tag"],
                    row["vector_text"],
                    row["count"],
                    full.pct(row["own_similarity"]),
                    row["nearest_bucket"],
                    full.pct(row["nearest_similarity"]),
                    full.pct(row["margin_to_nearest_other"]),
                    row["matched_words"],
                ]
            )

    by_bucket: defaultdict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        by_bucket[row["bucket"]].append(row)
    collisions = [
        row for row in rows if row["vector"] is not None and row["nearest_bucket"] != row["bucket"]
    ]
    collisions.sort(key=lambda row: (float(row["margin_to_nearest_other"]), -int(row["count"])))

    with OUT_CROSS_TSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
                "assigned_bucket",
                "tag",
                "vector_text",
                "count",
                "own_similarity_pct",
                "nearest_bucket",
                "nearest_similarity_pct",
                "margin_to_nearest_other_pct",
                "matched_words",
            ]
        )
        for row in collisions:
            writer.writerow(
                [
                    row["bucket"],
                    row["tag"],
                    row["vector_text"],
                    row["count"],
                    full.pct(row["own_similarity"]),
                    row["nearest_bucket"],
                    full.pct(row["nearest_similarity"]),
                    full.pct(row["margin_to_nearest_other"]),
                    row["matched_words"],
                ]
            )

    with OUT_CROSS_BY_BUCKET_TSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
                "assigned_bucket",
                "rank_in_bucket",
                "tag",
                "vector_text",
                "count",
                "own_similarity_pct",
                "nearest_bucket",
                "nearest_similarity_pct",
                "margin_to_nearest_other_pct",
                "matched_words",
            ]
        )
        for bucket in by_bucket:
            bucket_collisions = [row for row in collisions if row["bucket"] == bucket]
            for rank, row in enumerate(bucket_collisions, start=1):
                writer.writerow(
                    [
                        row["bucket"],
                        rank,
                        row["tag"],
                        row["vector_text"],
                        row["count"],
                        full.pct(row["own_similarity"]),
                        row["nearest_bucket"],
                        full.pct(row["nearest_similarity"]),
                        full.pct(row["margin_to_nearest_other"]),
                        row["matched_words"],
                    ]
                )

    with OUT_CROSS_BY_BUCKET_MD.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("# Fine-Only Cross-Bucket Outliers, Grouped By Assigned Bucket\n\n")
        handle.write(
            "Only tags whose nearest fastText centroid is a different bucket are shown. "
            "Rows inside each bucket are sorted by strongest negative margin.\n\n"
        )
        for bucket in by_bucket:
            bucket_collisions = [row for row in collisions if row["bucket"] == bucket]
            handle.write(f"## {bucket}\n\n")
            handle.write(f"{len(bucket_collisions)} outliers\n\n")
            for row in bucket_collisions:
                handle.write(
                    f"- `{row['tag']}` as `{row['vector_text']}` ({row['count']}) -> "
                    f"**{row['nearest_bucket']}**; own {full.pct(row['own_similarity'])}%, "
                    f"nearest {full.pct(row['nearest_similarity'])}%, "
                    f"margin {full.pct(row['margin_to_nearest_other'])}%\n"
                )
            handle.write("\n")

    strong_collisions = [
        row for row in collisions if float(row["margin_to_nearest_other"]) * 100 < -STRONG_MARGIN_PCT
    ]

    with OUT_CROSS_BY_BUCKET_GT10_TSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
                "assigned_bucket",
                "rank_in_bucket",
                "tag",
                "vector_text",
                "count",
                "own_similarity_pct",
                "nearest_bucket",
                "nearest_similarity_pct",
                "margin_to_nearest_other_pct",
                "matched_words",
            ]
        )
        for bucket in by_bucket:
            bucket_collisions = [row for row in strong_collisions if row["bucket"] == bucket]
            for rank, row in enumerate(bucket_collisions, start=1):
                writer.writerow(
                    [
                        row["bucket"],
                        rank,
                        row["tag"],
                        row["vector_text"],
                        row["count"],
                        full.pct(row["own_similarity"]),
                        row["nearest_bucket"],
                        full.pct(row["nearest_similarity"]),
                        full.pct(row["margin_to_nearest_other"]),
                        row["matched_words"],
                    ]
                )

    with OUT_CROSS_BY_BUCKET_GT10_MD.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("# Fine-Only Cross-Bucket Outliers >10 Point Margin\n\n")
        handle.write(
            "Only tags whose nearest fastText centroid is a different bucket by more than "
            f"{STRONG_MARGIN_PCT:.0f} percentage points are shown. Rows inside each bucket are sorted by strongest "
            "negative margin.\n\n"
        )
        for bucket in by_bucket:
            bucket_collisions = [row for row in strong_collisions if row["bucket"] == bucket]
            if not bucket_collisions:
                continue
            handle.write(f"## {bucket}\n\n")
            handle.write(f"{len(bucket_collisions)} outliers\n\n")
            for row in bucket_collisions:
                handle.write(
                    f"- `{row['tag']}` as `{row['vector_text']}` ({row['count']}) -> "
                    f"**{row['nearest_bucket']}**; own {full.pct(row['own_similarity'])}%, "
                    f"nearest {full.pct(row['nearest_similarity'])}%, "
                    f"margin {full.pct(row['margin_to_nearest_other'])}%\n"
                )
            handle.write("\n")

    with full.OUT_MD.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("# 13-Bucket fastText Outlier Check, Fine-Only Vector Text\n\n")
        handle.write(
            "Each tag keeps its assigned bucket and count, but vector text is only the fine-grained part after "
            "the first `/`. Example: `cultural reference / mythological figure` is embedded as "
            "`mythological figure`. Bucket centroids are frequency-weighted by the counts in the prompt.\n\n"
        )
        handle.write(f"- Parsed rows: {len(rows)}\n")
        handle.write(f"- Vectorized rows: {sum(1 for row in rows if row['vector'] is not None)}\n")
        handle.write(f"- No-vector rows: {sum(1 for row in rows if row['vector'] is None)}\n")
        handle.write(f"- Cross-bucket nearest-centroid collisions: {len(collisions)}\n\n")

        handle.write("## All Cross-Bucket Outliers\n\n")
        for row in collisions:
            handle.write(
                f"- `{row['tag']}` as `{row['vector_text']}` ({row['count']}) in **{row['bucket']}** -> nearest "
                f"**{row['nearest_bucket']}**; own {full.pct(row['own_similarity'])}%, "
                f"nearest {full.pct(row['nearest_similarity'])}%\n"
            )
        handle.write("\n")

        handle.write("## Lowest Own-Bucket Similarity By Bucket\n\n")
        for bucket in by_bucket:
            bucket_rows = [row for row in by_bucket[bucket] if row["vector"] is not None]
            bucket_rows.sort(key=lambda row: (float(row["own_similarity"]), -int(row["count"])))
            handle.write(f"### {bucket}\n\n")
            for row in bucket_rows[:12]:
                nearest = ""
                if row["nearest_bucket"] != row["bucket"]:
                    nearest = f" -> nearest **{row['nearest_bucket']}** {full.pct(row['nearest_similarity'])}%"
                handle.write(
                    f"- `{row['tag']}` as `{row['vector_text']}` ({row['count']}): "
                    f"own {full.pct(row['own_similarity'])}%{nearest}\n"
                )
            handle.write("\n")

    print(f"rows\t{len(rows)}")
    print(f"vectorized\t{sum(1 for row in rows if row['vector'] is not None)}")
    print(f"cross_bucket_collisions\t{len(collisions)}")
    print(f"tsv\t{full.OUT_TSV}")
    print(f"cross_bucket_tsv\t{OUT_CROSS_TSV}")
    print(f"cross_bucket_by_bucket_tsv\t{OUT_CROSS_BY_BUCKET_TSV}")
    print(f"cross_bucket_by_bucket_report\t{OUT_CROSS_BY_BUCKET_MD}")
    print(f"cross_bucket_by_bucket_gt10_tsv\t{OUT_CROSS_BY_BUCKET_GT10_TSV}")
    print(f"cross_bucket_by_bucket_gt10_report\t{OUT_CROSS_BY_BUCKET_GT10_MD}")
    print(f"cross_bucket_gt10_collisions\t{len(strong_collisions)}")
    print(f"report\t{full.OUT_MD}")


def main() -> None:
    rows = full.parse_raw()
    vectorize_rows(rows)
    centroids = full.build_centroids(rows)
    full.score_rows(rows, centroids)
    write_outputs(rows)


if __name__ == "__main__":
    main()
