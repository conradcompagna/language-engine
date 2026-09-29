from __future__ import annotations

import csv
from collections import defaultdict

import numpy as np

import analyze_user_taxonomy_outliers_fasttext_parent_child_25 as pc25
import assign_coarse_tags_to_manual_full_label_child_regions as base


run = pc25.run
OUT_DIR = run.full.OUT_DIR
OUT_TSV = OUT_DIR / "user_13_bucket_parent_label_similarity_parent_child_25.tsv"
OUT_MD = OUT_DIR / "user_13_bucket_parent_label_similarity_parent_child_25.md"
OUT_CROSS_TSV = OUT_DIR / "user_13_bucket_parent_label_similarity_parent_child_25_cross_label.tsv"


def category_label_vector(label: str, vectors: dict[str, np.ndarray]) -> tuple[np.ndarray | None, str]:
    vec, matched = base.label_vector({"tokens": base.text_tokens(label)}, vectors)
    return vec, "; ".join(matched)


def main() -> None:
    rows = run.full.parse_raw()
    run.vectorize_rows(rows)

    needed = set()
    buckets = sorted({str(row["bucket"]) for row in rows})
    for bucket in buckets:
        for token in base.text_tokens(bucket):
            needed.update(base.vector_variants(token))
    vectors = base.ft.load_fasttext(needed)

    label_vectors = {}
    label_matches = {}
    for bucket in buckets:
        vec, matched = category_label_vector(bucket, vectors)
        if vec is None:
            raise RuntimeError(f"No vector for bucket label: {bucket}")
        label_vectors[bucket] = vec
        label_matches[bucket] = matched

    matrix = np.stack([label_vectors[bucket] for bucket in buckets]).astype(np.float32)
    for row in rows:
        vec = row["vector"]
        if vec is None:
            row["assigned_label_similarity"] = ""
            row["nearest_label"] = "NO_VECTOR"
            row["nearest_label_similarity"] = ""
            row["margin_to_nearest_other_label"] = ""
            continue
        sims = matrix @ vec
        order = np.argsort(-sims)
        nearest = buckets[int(order[0])]
        own = float(np.dot(label_vectors[str(row["bucket"])], vec))
        nearest_other = next(float(sims[int(idx)]) for idx in order if buckets[int(idx)] != row["bucket"])
        row["assigned_label_similarity"] = own
        row["nearest_label"] = nearest
        row["nearest_label_similarity"] = float(sims[int(order[0])])
        row["margin_to_nearest_other_label"] = own - nearest_other

    OUT_DIR.mkdir(parents=True, exist_ok=True)
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
                "assigned_parent_label_similarity_pct",
                "nearest_parent_label",
                "nearest_parent_label_similarity_pct",
                "margin_to_nearest_other_parent_label_pct",
                "tag_matched_words",
                "bucket_label_matched_words",
            ]
        )
        for row in sorted(
            rows,
            key=lambda r: (r["bucket"], float(r["assigned_label_similarity"] or -1), -int(r["count"])),
        ):
            writer.writerow(
                [
                    row["bucket"],
                    row["tag"],
                    row["parent_text"],
                    row["child_text"],
                    row["vector_text"],
                    row["actual_weighting"],
                    row["count"],
                    run.full.pct(row["assigned_label_similarity"]),
                    row["nearest_label"],
                    run.full.pct(row["nearest_label_similarity"]),
                    run.full.pct(row["margin_to_nearest_other_label"]),
                    row["matched_words"],
                    label_matches[str(row["bucket"])],
                ]
            )

    cross = [
        row
        for row in rows
        if row["vector"] is not None and row["nearest_label"] != row["bucket"]
    ]
    cross.sort(key=lambda row: (float(row["margin_to_nearest_other_label"]), -int(row["count"])))
    with OUT_CROSS_TSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
                "assigned_bucket",
                "tag",
                "vector_text",
                "count",
                "assigned_parent_label_similarity_pct",
                "nearest_parent_label",
                "nearest_parent_label_similarity_pct",
                "margin_to_nearest_other_parent_label_pct",
            ]
        )
        for row in cross:
            writer.writerow(
                [
                    row["bucket"],
                    row["tag"],
                    row["vector_text"],
                    row["count"],
                    run.full.pct(row["assigned_label_similarity"]),
                    row["nearest_label"],
                    run.full.pct(row["nearest_label_similarity"]),
                    run.full.pct(row["margin_to_nearest_other_label"]),
                ]
            )

    by_bucket: defaultdict[str, list[dict[str, object]]] = defaultdict(list)
    for row in rows:
        if row["vector"] is not None:
            by_bucket[str(row["bucket"])].append(row)

    summary = []
    for bucket, bucket_rows in by_bucket.items():
        counts = [int(row["count"]) for row in bucket_rows]
        sims = [float(row["assigned_label_similarity"]) * 100 for row in bucket_rows]
        total = sum(counts)
        weighted = sum(count * sim for count, sim in zip(counts, sims)) / total
        unweighted = sum(sims) / len(sims)
        low = sorted(bucket_rows, key=lambda row: float(row["assigned_label_similarity"]))[:8]
        summary.append((weighted, unweighted, len(bucket_rows), total, bucket, low))
    summary.sort()

    with OUT_MD.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("# Parent Category Label Similarity, Parent/Child 25-75 Tags\n\n")
        handle.write(
            "Each tag vector uses the 25% parent / 75% child rule for slash labels. "
            "Each bucket is represented only by the words in the bucket label itself, not by a member-tag centroid.\n\n"
        )
        handle.write(f"- Parsed rows: {len(rows)}\n")
        handle.write(f"- Vectorized rows: {sum(1 for row in rows if row['vector'] is not None)}\n")
        handle.write(f"- Cross-label nearest matches: {len(cross)}\n\n")
        handle.write("| Rank | Bucket | Weighted label similarity | Unweighted | Tags | Count |\n")
        handle.write("|---:|---|---:|---:|---:|---:|\n")
        for rank, (weighted, unweighted, tag_count, total, bucket, low) in enumerate(summary, 1):
            handle.write(
                f"| {rank} | {bucket} | {weighted:.2f}% | {unweighted:.2f}% | {tag_count} | {total} |\n"
            )

        handle.write("\n## Lowest Tags By Bucket\n\n")
        for weighted, unweighted, tag_count, total, bucket, low in summary:
            handle.write(f"### {bucket}\n\n")
            for row in low:
                nearest = ""
                if row["nearest_label"] != row["bucket"]:
                    nearest = (
                        f" -> nearest **{row['nearest_label']}** "
                        f"{run.full.pct(row['nearest_label_similarity'])}%"
                    )
                handle.write(
                    f"- `{row['tag']}` as `{row['vector_text']}` ({row['count']}): "
                    f"{run.full.pct(row['assigned_label_similarity'])}%{nearest}\n"
                )
            handle.write("\n")

    print(f"rows\t{len(rows)}")
    print(f"vectorized\t{sum(1 for row in rows if row['vector'] is not None)}")
    print(f"cross_label_nearest_matches\t{len(cross)}")
    print(f"tsv\t{OUT_TSV}")
    print(f"cross_label_tsv\t{OUT_CROSS_TSV}")
    print(f"report\t{OUT_MD}")


if __name__ == "__main__":
    main()
