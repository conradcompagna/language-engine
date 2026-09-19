from __future__ import annotations

import csv
from pathlib import Path

import numpy as np

import cluster_all_finerweb_labels_fasttext as ft


BASE_DIR = Path(__file__).resolve().parent
IN_TSV = BASE_DIR / "derived_fasttext_categories" / "finerweb_coarse_ge100_examples_under25_map.tsv"
OUT_TSV = BASE_DIR / "derived_fasttext_categories" / "finerweb_coarse_tag_pairwise_fasttext_similarity.tsv"
NEAREST_TSV = BASE_DIR / "derived_fasttext_categories" / "finerweb_coarse_tag_nearest_neighbors.tsv"


def load_tags() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    seen: set[str] = set()
    with IN_TSV.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            coarse_tag = row["coarse_tag"]
            if coarse_tag in seen:
                continue
            seen.add(coarse_tag)
            vector_text = row["coarse_tag_english"] or coarse_tag
            rows.append(
                {
                    "coarse_tag": coarse_tag,
                    "coarse_tag_english": row["coarse_tag_english"],
                    "mapped_label": row["mapped_label"],
                    "vector_text": vector_text,
                    "tokens": ft.text_tokens(vector_text),
                }
            )
    return rows


def vectorize(rows: list[dict[str, str]], vectors: dict[str, np.ndarray]) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    vectorized: list[dict[str, str]] = []
    unvectorized: list[dict[str, str]] = []
    for row in rows:
        vec, matched = ft.row_vector(row, vectors)
        row["matched_tokens"] = ", ".join(matched)
        if vec is None:
            unvectorized.append(row)
            continue
        row["vector"] = vec
        vectorized.append(row)
    return vectorized, unvectorized


def main() -> None:
    rows = load_tags()
    needed = ft.collect_needed_words(rows)
    vectors = ft.load_fasttext(needed)
    vectorized, unvectorized = vectorize(rows, vectors)

    matrix = np.stack([row["vector"] for row in vectorized]).astype(np.float32)
    sim = matrix @ matrix.T

    pairs = []
    for i in range(len(vectorized)):
        for j in range(i + 1, len(vectorized)):
            pairs.append((float(sim[i, j]), i, j))
    pairs.sort(reverse=True, key=lambda item: item[0])

    with OUT_TSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
                "similarity_pct",
                "coarse_tag_a",
                "coarse_tag_b",
                "coarse_tag_english_a",
                "coarse_tag_english_b",
                "mapped_label_a",
                "mapped_label_b",
                "matched_tokens_a",
                "matched_tokens_b",
            ]
        )
        for score, i, j in pairs:
            a = vectorized[i]
            b = vectorized[j]
            writer.writerow(
                [
                    f"{score * 100:.2f}",
                    a["coarse_tag"],
                    b["coarse_tag"],
                    a["coarse_tag_english"],
                    b["coarse_tag_english"],
                    a["mapped_label"],
                    b["mapped_label"],
                    a["matched_tokens"],
                    b["matched_tokens"],
                ]
            )

    with NEAREST_TSV.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
                "coarse_tag",
                "coarse_tag_english",
                "mapped_label",
                "nearest_tag",
                "nearest_tag_english",
                "nearest_mapped_label",
                "similarity_pct",
            ]
        )
        for i, row in enumerate(vectorized):
            scores = sim[i].copy()
            scores[i] = -2.0
            j = int(np.argmax(scores))
            nearest = vectorized[j]
            writer.writerow(
                [
                    row["coarse_tag"],
                    row["coarse_tag_english"],
                    row["mapped_label"],
                    nearest["coarse_tag"],
                    nearest["coarse_tag_english"],
                    nearest["mapped_label"],
                    f"{float(scores[j]) * 100:.2f}",
                ]
            )

    print(f"tags={len(rows)}")
    print(f"vectorized={len(vectorized)}")
    print(f"unvectorized={len(unvectorized)}")
    print(f"pairs={len(pairs)}")
    print(f"wrote={OUT_TSV}")
    print(f"nearest={NEAREST_TSV}")
    if unvectorized:
        print("unvectorized_tags=" + "; ".join(row["coarse_tag"] for row in unvectorized[:20]))


if __name__ == "__main__":
    main()
