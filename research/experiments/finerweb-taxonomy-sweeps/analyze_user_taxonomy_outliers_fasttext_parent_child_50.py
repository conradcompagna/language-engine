from __future__ import annotations

import csv
from collections import defaultdict

import numpy as np

import analyze_user_taxonomy_outliers_fasttext as full
import assign_coarse_tags_to_manual_full_label_child_regions as base


RUN_SLUG = "parent_child_50"
RUN_TITLE = "Parent/Child 50-50"
PARENT_WEIGHT = 0.5
CHILD_WEIGHT = 0.5
OUT_TSV = full.OUT_DIR / f"user_13_bucket_fasttext_outliers_{RUN_SLUG}.tsv"
OUT_MD = full.OUT_DIR / f"user_13_bucket_fasttext_outliers_{RUN_SLUG}.md"
OUT_CROSS_TSV = full.OUT_DIR / f"user_13_bucket_fasttext_outliers_{RUN_SLUG}_cross_bucket_all.tsv"
OUT_CROSS_BY_BUCKET_MD = full.OUT_DIR / f"user_13_bucket_fasttext_outliers_{RUN_SLUG}_cross_bucket_by_bucket.md"
OUT_CROSS_BY_BUCKET_TSV = full.OUT_DIR / f"user_13_bucket_fasttext_outliers_{RUN_SLUG}_cross_bucket_by_bucket.tsv"
OUT_CROSS_BY_BUCKET_GT10_MD = full.OUT_DIR / f"user_13_bucket_fasttext_outliers_{RUN_SLUG}_cross_bucket_by_bucket_gt10.md"
OUT_CROSS_BY_BUCKET_GT10_TSV = full.OUT_DIR / f"user_13_bucket_fasttext_outliers_{RUN_SLUG}_cross_bucket_by_bucket_gt10.tsv"
STRONG_MARGIN_PCT = 10.0


def split_parent_child(tag: str) -> tuple[str, str]:
    if "/" not in tag:
        stripped = tag.strip()
        return stripped, ""
    parent, child = tag.split("/", 1)
    return parent.strip(), child.strip()


def side_vector(text: str, vectors: dict[str, np.ndarray]) -> tuple[np.ndarray | None, list[str]]:
    return base.label_vector({"tokens": base.text_tokens(text)}, vectors)


def vectorize_rows(rows: list[dict[str, object]]) -> None:
    needed = set()
    for row in rows:
        parent_text, child_text = split_parent_child(str(row["tag"]))
        row["parent_text"] = parent_text
        row["child_text"] = child_text
        row["vector_text"] = parent_text if not child_text else f"{parent_text} + {child_text}"
        for token in base.text_tokens(parent_text):
            needed.update(base.vector_variants(token))
        for token in base.text_tokens(child_text):
            needed.update(base.vector_variants(token))

    vectors = base.ft.load_fasttext(needed)
    for row in rows:
        parent_vec, parent_matched = side_vector(str(row["parent_text"]), vectors)
        child_vec, child_matched = side_vector(str(row["child_text"]), vectors)
        if child_vec is None:
            vec = parent_vec
            actual_weighting = "single"
        elif parent_vec is None:
            vec = child_vec
            actual_weighting = "child_only"
        else:
            vec = (PARENT_WEIGHT * parent_vec) + (CHILD_WEIGHT * child_vec)
            norm = np.linalg.norm(vec)
            vec = None if not norm else (vec / norm).astype(np.float32)
            actual_weighting = f"parent_{int(PARENT_WEIGHT * 100)}_child_{int(CHILD_WEIGHT * 100)}"

        row["vector"] = vec
        row["actual_weighting"] = actual_weighting
        row["matched_words"] = (
            f"parent: {'; '.join(parent_matched)}"
            if not child_matched
            else f"parent: {'; '.join(parent_matched)} | child: {'; '.join(child_matched)}"
        )


def write_outputs(rows: list[dict[str, object]]) -> None:
    full.OUT_DIR.mkdir(parents=True, exist_ok=True)
    with OUT_TSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
                "bucket",
                "tag",
                "parent_text",
                "child_text",
                "vector_text",
                "actual_weighting",
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
                    row["parent_text"],
                    row["child_text"],
                    row["vector_text"],
                    row["actual_weighting"],
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
                "parent_text",
                "child_text",
                "vector_text",
                "actual_weighting",
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
                    row["parent_text"],
                    row["child_text"],
                    row["vector_text"],
                    row["actual_weighting"],
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
                "parent_text",
                "child_text",
                "vector_text",
                "actual_weighting",
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
                        row["parent_text"],
                        row["child_text"],
                        row["vector_text"],
                        row["actual_weighting"],
                        row["count"],
                        full.pct(row["own_similarity"]),
                        row["nearest_bucket"],
                        full.pct(row["nearest_similarity"]),
                        full.pct(row["margin_to_nearest_other"]),
                        row["matched_words"],
                    ]
                )

    with OUT_CROSS_BY_BUCKET_MD.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(f"# {RUN_TITLE} Cross-Bucket Outliers, Grouped By Assigned Bucket\n\n")
        handle.write(
            f"For slash labels, vectors are {PARENT_WEIGHT * 100:.0f}% parent phrase and "
            f"{CHILD_WEIGHT * 100:.0f}% child phrase "
            "when both sides have fastText vectors. Rows inside each bucket are sorted by strongest negative margin.\n\n"
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
                "parent_text",
                "child_text",
                "vector_text",
                "actual_weighting",
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
                        row["parent_text"],
                        row["child_text"],
                        row["vector_text"],
                        row["actual_weighting"],
                        row["count"],
                        full.pct(row["own_similarity"]),
                        row["nearest_bucket"],
                        full.pct(row["nearest_similarity"]),
                        full.pct(row["margin_to_nearest_other"]),
                        row["matched_words"],
                    ]
                )

    with OUT_CROSS_BY_BUCKET_GT10_MD.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(f"# {RUN_TITLE} Cross-Bucket Outliers >10 Point Margin\n\n")
        handle.write(
            "Only tags whose nearest fastText centroid is a different bucket by more than "
            f"{STRONG_MARGIN_PCT:.0f} percentage points are shown.\n\n"
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

    with OUT_MD.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(f"# 13-Bucket fastText Outlier Check, {RUN_TITLE}\n\n")
        handle.write(
            "For slash labels, vectors are built from the parent phrase and child phrase separately, then combined "
            f"as {PARENT_WEIGHT * 100:.0f}% parent + {CHILD_WEIGHT * 100:.0f}% child when both sides have vectors. "
            "Non-slash labels use the whole label. "
            "Bucket centroids are frequency-weighted by the counts in the prompt.\n\n"
        )
        handle.write(f"- Parsed rows: {len(rows)}\n")
        handle.write(f"- Vectorized rows: {sum(1 for row in rows if row['vector'] is not None)}\n")
        handle.write(f"- No-vector rows: {sum(1 for row in rows if row['vector'] is None)}\n")
        handle.write(f"- Cross-bucket nearest-centroid collisions: {len(collisions)}\n")
        handle.write(f"- Cross-bucket >10 point collisions: {len(strong_collisions)}\n\n")

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
    print(f"cross_bucket_gt10_collisions\t{len(strong_collisions)}")
    print(f"tsv\t{OUT_TSV}")
    print(f"report\t{OUT_MD}")
    print(f"cross_bucket_by_bucket_gt10_tsv\t{OUT_CROSS_BY_BUCKET_GT10_TSV}")
    print(f"cross_bucket_by_bucket_gt10_report\t{OUT_CROSS_BY_BUCKET_GT10_MD}")


def main() -> None:
    rows = full.parse_raw()
    vectorize_rows(rows)
    centroids = full.build_centroids(rows)
    full.score_rows(rows, centroids)
    write_outputs(rows)


if __name__ == "__main__":
    main()
