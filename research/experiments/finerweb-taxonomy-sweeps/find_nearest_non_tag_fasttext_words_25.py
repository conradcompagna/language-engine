from __future__ import annotations

import csv
import re
import zipfile
from pathlib import Path

import numpy as np

import analyze_user_taxonomy_outliers_fasttext_parent_child_25 as pc25
import assign_coarse_tags_to_manual_full_label_child_regions as base


run = pc25.run
OUT_DIR = run.full.OUT_DIR
OUT_TSV = OUT_DIR / "user_13_bucket_nearest_non_tag_fasttext_word_parent_child_25.tsv"
OUT_MD = OUT_DIR / "user_13_bucket_nearest_non_tag_fasttext_word_parent_child_25.md"

WORD_RE = re.compile(r"^[a-z]+$")
CHUNK_SIZE = 25000


def extra_exclusions(token: str) -> set[str]:
    out = {token}
    if token.endswith("y") and len(token) > 2:
        out.add(token[:-1] + "ies")
    if token.endswith("s"):
        out.add(token[:-1])
    else:
        out.add(token + "s")
        out.add(token + "es")
    return out


def exclusion_words(tag: str) -> set[str]:
    excluded = set()
    for token in base.text_tokens(tag):
        for candidate in base.vector_variants(token):
            excluded.add(candidate)
            excluded.update(extra_exclusions(candidate))
    return excluded


def clean_vocab_word(word: str) -> bool:
    return (
        len(word) > 1
        and WORD_RE.match(word) is not None
        and word not in base.FUNCTION_STOPWORDS
    )


def update_best(
    query: np.ndarray,
    rows: list[dict[str, object]],
    words: list[str],
    vectors: list[np.ndarray],
    best_scores: np.ndarray,
    best_words: list[str],
) -> None:
    matrix = np.stack(vectors).astype(np.float32)
    sims = query @ matrix.T
    for row_idx, row in enumerate(rows):
        excluded = row["excluded_words"]
        row_sims = sims[row_idx]
        top = np.argpartition(row_sims, -50)[-50:]
        top = top[np.argsort(-row_sims[top])]
        for col_idx in top:
            word = words[int(col_idx)]
            if word in excluded:
                continue
            score = float(row_sims[int(col_idx)])
            if score > float(best_scores[row_idx]):
                best_scores[row_idx] = score
                best_words[row_idx] = word
            break


def main() -> None:
    rows = run.full.parse_raw()
    run.vectorize_rows(rows)
    vectorized_rows = [row for row in rows if row["vector"] is not None]
    for row in vectorized_rows:
        row["excluded_words"] = exclusion_words(str(row["tag"]))

    query = np.stack([row["vector"] for row in vectorized_rows]).astype(np.float32)
    best_scores = np.full(len(vectorized_rows), -2.0, dtype=np.float32)
    best_words = [""] * len(vectorized_rows)

    with zipfile.ZipFile(base.ft.FASTTEXT_ZIP, "r") as zf:
        vec_name = next(name for name in zf.namelist() if name.endswith(".vec"))
        with zf.open(vec_name, "r") as handle:
            handle.readline()
            words: list[str] = []
            vectors: list[np.ndarray] = []
            for line in handle:
                word_bytes, _, rest = line.partition(b" ")
                try:
                    word = word_bytes.decode("utf-8")
                except UnicodeDecodeError:
                    continue
                if not clean_vocab_word(word):
                    continue
                arr = np.fromstring(rest.decode("ascii"), sep=" ", dtype=np.float32)
                norm = np.linalg.norm(arr)
                if not norm:
                    continue
                words.append(word)
                vectors.append((arr / norm).astype(np.float32))
                if len(words) >= CHUNK_SIZE:
                    update_best(query, vectorized_rows, words, vectors, best_scores, best_words)
                    words = []
                    vectors = []
            if words:
                update_best(query, vectorized_rows, words, vectors, best_scores, best_words)

    for idx, row in enumerate(vectorized_rows):
        row["nearest_non_tag_word"] = best_words[idx]
        row["nearest_non_tag_word_similarity"] = float(best_scores[idx])

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
                "nearest_non_tag_word",
                "similarity_pct",
                "excluded_words",
                "matched_words",
            ]
        )
        for row in rows:
            if row.get("vector") is None:
                writer.writerow(
                    [
                        row["bucket"],
                        row["tag"],
                        row.get("parent_text", ""),
                        row.get("child_text", ""),
                        row.get("vector_text", ""),
                        row.get("actual_weighting", ""),
                        row["count"],
                        "NO_VECTOR",
                        "",
                        "",
                        "",
                    ]
                )
                continue
            writer.writerow(
                [
                    row["bucket"],
                    row["tag"],
                    row["parent_text"],
                    row["child_text"],
                    row["vector_text"],
                    row["actual_weighting"],
                    row["count"],
                    row["nearest_non_tag_word"],
                    run.full.pct(row["nearest_non_tag_word_similarity"]),
                    "; ".join(sorted(row["excluded_words"])),
                    row["matched_words"],
                ]
            )

    by_bucket: dict[str, list[dict[str, object]]] = {}
    for row in vectorized_rows:
        by_bucket.setdefault(str(row["bucket"]), []).append(row)

    with OUT_MD.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("# Nearest Non-Tag fastText Word, Parent/Child 25-75\n\n")
        handle.write(
            "Each tag vector uses the 25% parent / 75% child rule. "
            "The nearest word is searched across clean alphabetic fastText vocabulary words, excluding words "
            "that already appear in the original tag plus simple singular/plural variants.\n\n"
        )
        handle.write(f"- Parsed rows: {len(rows)}\n")
        handle.write(f"- Vectorized rows: {len(vectorized_rows)}\n\n")
        for bucket, bucket_rows in by_bucket.items():
            handle.write(f"## {bucket}\n\n")
            for row in sorted(bucket_rows, key=lambda item: -int(item["count"]))[:25]:
                handle.write(
                    f"- `{row['tag']}` ({row['count']}) -> **{row['nearest_non_tag_word']}** "
                    f"({run.full.pct(row['nearest_non_tag_word_similarity'])}%)\n"
                )
            handle.write("\n")

    print(f"rows\t{len(rows)}")
    print(f"vectorized\t{len(vectorized_rows)}")
    print(f"tsv\t{OUT_TSV}")
    print(f"report\t{OUT_MD}")


if __name__ == "__main__":
    main()
