from __future__ import annotations

import argparse
import csv
import re
import unicodedata
from collections import Counter
from pathlib import Path

import numpy as np

import cluster_all_finerweb_labels_fasttext as ft


BASE_DIR = Path(__file__).resolve().parent
IN_COUNTS = BASE_DIR / "finerweb_label_inventory_coarse.tsv"
IN_MAP = BASE_DIR / "derived_fasttext_categories" / "finerweb_coarse_ge100_examples_under25_map.tsv"
OUT_GROUPS = BASE_DIR / "derived_fasttext_categories" / "finerweb_greedy_foundational_tags_75.tsv"
OUT_TAG_MAP = BASE_DIR / "derived_fasttext_categories" / "finerweb_greedy_foundational_tags_75_tag_map.tsv"
OUT_MD = BASE_DIR / "derived_fasttext_categories" / "finerweb_greedy_foundational_tags_75.md"

MIN_COUNT = 101
TOKEN_RE = re.compile(r"[a-z]+(?:'[a-z]+)?|\d+")
FUNCTION_STOPWORDS = {
    "a",
    "an",
    "and",
    "as",
    "at",
    "by",
    "for",
    "from",
    "in",
    "into",
    "of",
    "on",
    "or",
    "the",
    "to",
    "with",
}


def strip_accents(text: str) -> str:
    return "".join(
        ch
        for ch in unicodedata.normalize("NFKD", text)
        if not unicodedata.combining(ch)
    )


def text_tokens(text: str) -> list[str]:
    text = strip_accents((text or "").lower().replace("_", " "))
    return [tok for tok in TOKEN_RE.findall(text) if tok not in FUNCTION_STOPWORDS]


def load_english_map() -> dict[str, str]:
    mapping: dict[str, str] = {}
    with IN_MAP.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            mapping[row["coarse_tag"]] = row["coarse_tag_english"] or row["coarse_tag"]
    return mapping


def load_rows() -> list[dict[str, object]]:
    csv.field_size_limit(2**31 - 1)
    english = load_english_map()
    rows: list[dict[str, object]] = []
    with IN_COUNTS.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            count = int(row["total_count"])
            if count < MIN_COUNT:
                continue
            tag = row["coarse_label"]
            vector_text = english.get(tag, tag)
            rows.append(
                {
                    "coarse_tag": tag,
                    "coarse_tag_english": vector_text,
                    "count": count,
                    "tokens": text_tokens(vector_text),
                }
            )
    rows.sort(key=lambda item: (-int(item["count"]), str(item["coarse_tag_english"]), str(item["coarse_tag"])))
    return rows


def collect_needed_words(rows: list[dict[str, object]]) -> set[str]:
    needed: set[str] = set()
    for row in rows:
        for token in row["tokens"]:
            needed.update(ft.variants(token))
    return needed


def row_vector(row: dict[str, object], vectors: dict[str, np.ndarray]):
    found = []
    matched = []
    for token in row["tokens"]:
        word, vec = ft.token_vector(token, vectors)
        if vec is not None:
            found.append(vec)
            matched.append(word)
    row["matched_tokens"] = ", ".join(matched)
    if not found:
        return None
    vec = np.mean(found, axis=0)
    norm = np.linalg.norm(vec)
    if not norm:
        return None
    return vec / norm


def top_unigrams(members: list[dict[str, object]], limit: int = 8) -> str:
    tag_counts: Counter[str] = Counter()
    mention_counts: Counter[str] = Counter()
    for row in members:
        for token in row["tokens"]:
            tag_counts[token] += 1
            mention_counts[token] += int(row["count"])
    ranked = sorted(
        tag_counts,
        key=lambda tok: (tag_counts[tok], mention_counts[tok], tok),
        reverse=True,
    )
    return "; ".join(
        f"{tok} ({tag_counts[tok]} tags, {mention_counts[tok]} mentions)"
        for tok in ranked[:limit]
    )


def greedy_group(rows: list[dict[str, object]], threshold: float) -> list[dict[str, object]]:
    remaining = list(range(len(rows)))
    groups = []
    while remaining:
        seed_index = remaining[0]
        seed = rows[seed_index]
        seed_vec = seed.get("vector")
        members = [(seed_index, 1.0)]
        still_remaining = []

        for index in remaining[1:]:
            row = rows[index]
            row_vec = row.get("vector")
            if seed_vec is None or row_vec is None:
                still_remaining.append(index)
                continue
            sim = float(np.dot(seed_vec, row_vec))
            if sim >= threshold:
                members.append((index, sim))
            else:
                still_remaining.append(index)

        groups.append({"seed_index": seed_index, "members": members})
        remaining = still_remaining
    return groups


def output_paths(threshold: float) -> tuple[Path, Path, Path]:
    suffix = str(int(round(threshold * 100))).zfill(2)
    out_dir = BASE_DIR / "derived_fasttext_categories"
    return (
        out_dir / f"finerweb_greedy_foundational_tags_{suffix}.tsv",
        out_dir / f"finerweb_greedy_foundational_tags_{suffix}_tag_map.tsv",
        out_dir / f"finerweb_greedy_foundational_tags_{suffix}.md",
    )


def write_outputs(rows: list[dict[str, object]], groups: list[dict[str, object]], threshold: float) -> None:
    out_groups, out_tag_map, out_md = output_paths(threshold)
    assignment: dict[int, tuple[int, float]] = {}
    for group_id, group in enumerate(groups, start=1):
        for index, sim in group["members"]:
            assignment[index] = (group_id, sim)

    with out_groups.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
                "foundation_rank",
                "foundation_tag",
                "foundation_english",
                "foundation_count",
                "bucket_size",
                "bucket_total_count",
                "top_unigrams",
                "collapsed_tags_with_similarity",
            ]
        )
        for group_id, group in enumerate(groups, start=1):
            seed = rows[group["seed_index"]]
            members = [rows[index] for index, _sim in group["members"]]
            collapsed = []
            for index, sim in sorted(group["members"][1:], key=lambda item: (-item[1], -int(rows[item[0]]["count"]))):
                row = rows[index]
                collapsed.append(f"{row['coarse_tag']} ({sim * 100:.2f}%, count={row['count']})")
            writer.writerow(
                [
                    group_id,
                    seed["coarse_tag"],
                    seed["coarse_tag_english"],
                    seed["count"],
                    len(members),
                    sum(int(row["count"]) for row in members),
                    top_unigrams(members),
                    "; ".join(collapsed),
                ]
            )

    with out_tag_map.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
                "coarse_tag",
                "coarse_tag_english",
                "count",
                "foundation_rank",
                "foundation_tag",
                "foundation_english",
                "similarity_to_foundation_pct",
                "assignment",
            ]
        )
        for index, row in enumerate(rows):
            group_id, sim = assignment[index]
            seed = rows[groups[group_id - 1]["seed_index"]]
            writer.writerow(
                [
                    row["coarse_tag"],
                    row["coarse_tag_english"],
                    row["count"],
                    group_id,
                    seed["coarse_tag"],
                    seed["coarse_tag_english"],
                    f"{sim * 100:.2f}",
                    "foundation" if index == groups[group_id - 1]["seed_index"] else "collapsed",
                ]
            )

    with out_md.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(f"# Greedy Foundational Coarse Tags at {threshold * 100:.0f}% Similarity\n\n")
        handle.write(
            "Algorithm: sort coarse tags by original frequency, take the highest-frequency unassigned tag as the foundation, "
            "assign every still-unassigned tag with cosine similarity >=75% to that foundation, then continue to the next remaining tag. "
            "Similarity is computed over canonical English coarse-tag text using local fastText vectors.\n\n"
        )
        handle.write(f"- Input tags: {len(rows)}\n")
        handle.write(f"- Foundation buckets produced: {len(groups)}\n")
        handle.write(f"- Collapsed tags: {sum(len(group['members']) - 1 for group in groups)}\n")
        handle.write(f"- Singleton foundations: {sum(1 for group in groups if len(group['members']) == 1)}\n")
        handle.write(f"- Threshold: {threshold * 100:.0f}%\n\n")

        handle.write("## Foundation Buckets With Collapses\n\n")
        for group_id, group in enumerate(groups, start=1):
            seed = rows[group["seed_index"]]
            members = [rows[index] for index, _sim in group["members"]]
            if len(members) == 1:
                continue
            bucket_total = sum(int(row["count"]) for row in members)
            handle.write(f"### {group_id}. {seed['coarse_tag']}\n\n")
            handle.write(f"Foundation English: {seed['coarse_tag_english']}\n\n")
            handle.write(f"Foundation count: {seed['count']}; bucket tags: {len(members)}; bucket count: {bucket_total}\n\n")
            handle.write(f"Top unigrams: {top_unigrams(members)}\n\n")
            handle.write("Collapsed tags:\n")
            for index, sim in sorted(group["members"][1:], key=lambda item: (-item[1], -int(rows[item[0]]["count"]))):
                row = rows[index]
                handle.write(f"- `{row['coarse_tag']}` ({sim * 100:.2f}%, count={row['count']})\n")
            handle.write("\n")

        singletons = [rows[group["seed_index"]] for group in groups if len(group["members"]) == 1]
        handle.write("## Singleton Foundations\n\n")
        handle.write(
            "These tags were not >=75% similar to any earlier, higher-frequency remaining foundation tag.\n\n"
        )
        handle.write(", ".join(f"`{row['coarse_tag']}`" for row in singletons))
        handle.write("\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--threshold", type=float, default=0.75)
    parser.add_argument("--summary-only", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    threshold = args.threshold
    if threshold > 1:
        threshold = threshold / 100.0
    rows = load_rows()
    vectors = ft.load_fasttext(collect_needed_words(rows))
    vectorized = 0
    for row in rows:
        vec = row_vector(row, vectors)
        row["vector"] = vec
        if vec is not None:
            vectorized += 1
    groups = greedy_group(rows, threshold)
    if not args.summary_only:
        write_outputs(rows, groups, threshold)
    out_groups, out_tag_map, out_md = output_paths(threshold)
    print(f"tags={len(rows)}")
    print(f"vectorized={vectorized}")
    print(f"threshold={threshold:.2f}")
    print(f"foundations={len(groups)}")
    print(f"collapsed={sum(len(group['members']) - 1 for group in groups)}")
    print(f"singletons={sum(1 for group in groups if len(group['members']) == 1)}")
    if not args.summary_only:
        print(f"groups={out_groups}")
        print(f"tag_map={out_tag_map}")
        print(f"report={out_md}")


if __name__ == "__main__":
    main()
