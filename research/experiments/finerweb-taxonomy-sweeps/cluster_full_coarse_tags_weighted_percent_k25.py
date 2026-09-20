from __future__ import annotations

import csv
import math
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from sklearn.cluster import KMeans

import cluster_all_finerweb_labels_fasttext as ft


BASE_DIR = Path(__file__).resolve().parent
IN_COUNTS = BASE_DIR / "finerweb_label_inventory_coarse.tsv"
IN_ENGLISH = BASE_DIR / "derived_fasttext_categories" / "finerweb_coarse_ge100_examples_under25_map.tsv"
OUT_DIR = BASE_DIR / "derived_fasttext_categories"
SUMMARY_OUT = OUT_DIR / "finerweb_full_coarse_weighted_percent_k25_summary.tsv"
TAG_MAP_OUT = OUT_DIR / "finerweb_full_coarse_weighted_percent_k25_tag_map.tsv"
REPORT_OUT = OUT_DIR / "finerweb_full_coarse_weighted_percent_k25.md"

K = 25
RANDOM_STATES = (3, 7, 13, 19, 29)
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
    if not IN_ENGLISH.exists():
        return {}
    mapping: dict[str, str] = {}
    with IN_ENGLISH.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            mapping[row["coarse_tag"]] = row["coarse_tag_english"] or row["coarse_tag"]
    return mapping


def load_rows() -> tuple[list[dict[str, object]], int]:
    csv.field_size_limit(2**31 - 1)
    english = load_english_map()
    rows: list[dict[str, object]] = []
    with IN_COUNTS.open("r", encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            count = int(row["total_count"])
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
    total = sum(int(row["count"]) for row in rows)
    for row in rows:
        row["percent"] = int(row["count"]) / total * 100.0
    rows.sort(key=lambda item: (-int(item["count"]), str(item["coarse_tag_english"]), str(item["coarse_tag"])))
    return rows, total


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


def normalized_centers(model: KMeans) -> np.ndarray:
    centers = model.cluster_centers_.astype(np.float32)
    norms = np.linalg.norm(centers, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return centers / norms


def fit_weighted_kmeans(x: np.ndarray, weights: np.ndarray):
    best = None
    attempts = []
    scaled_weights = weights / weights.mean()
    for random_state in RANDOM_STATES:
        model = KMeans(
            n_clusters=K,
            random_state=random_state,
            n_init=20,
            max_iter=500,
            algorithm="lloyd",
        )
        labels = model.fit_predict(x, sample_weight=scaled_weights)
        centers = normalized_centers(model)
        sims = np.sum(x * centers[labels], axis=1)
        weighted_mean = float(np.average(sims, weights=weights))
        attempts.append((weighted_mean, random_state))
        if best is None or weighted_mean > best[0]:
            best = (weighted_mean, labels, centers, sims, random_state)
    return best[1], best[2], best[3], best[4], attempts


def top_unigrams(rows: list[dict[str, object]], limit: int = 10) -> str:
    tag_counts: Counter[str] = Counter()
    mention_counts: Counter[str] = Counter()
    for row in rows:
        for token in row["tokens"]:
            tag_counts[token] += 1
            mention_counts[token] += int(row["count"])
    ranked = sorted(
        tag_counts,
        key=lambda tok: (mention_counts[tok], tag_counts[tok], tok),
        reverse=True,
    )
    return "; ".join(
        f"{tok} ({mention_counts[tok]} mentions, {tag_counts[tok]} tags)"
        for tok in ranked[:limit]
    )


def choose_anchor(group_rows: list[dict[str, object]], center: np.ndarray) -> dict[str, object]:
    best = None
    for row in group_rows:
        sim = float(np.dot(row["vector"], center))
        count_boost = 0.025 * math.log1p(int(row["count"]))
        score = sim + count_boost
        if best is None or score > best[0]:
            best = (score, sim, row)
    return best[2]


def main() -> None:
    rows, total_count = load_rows()
    vectors = ft.load_fasttext(collect_needed_words(rows))

    vectorized = []
    unvectorized = []
    for row in rows:
        vec = row_vector(row, vectors)
        if vec is None:
            unvectorized.append(row)
            continue
        row["vector"] = vec
        vectorized.append(row)

    x = np.stack([row["vector"] for row in vectorized]).astype(np.float32)
    weights = np.array([float(row["percent"]) for row in vectorized], dtype=np.float64)
    labels, centers, sims, random_state, attempts = fit_weighted_kmeans(x, weights)

    groups: defaultdict[int, list[dict[str, object]]] = defaultdict(list)
    for row, label, sim in zip(vectorized, labels, sims):
        row["cluster_id"] = int(label)
        row["centroid_similarity"] = float(sim)
        groups[int(label)].append(row)

    summaries = []
    for cluster_id, group_rows in groups.items():
        group_count = sum(int(row["count"]) for row in group_rows)
        group_percent = group_count / total_count * 100.0
        anchor = choose_anchor(group_rows, centers[cluster_id])
        weighted_mean = float(
            np.average([float(row["centroid_similarity"]) for row in group_rows], weights=[float(row["percent"]) for row in group_rows])
        )
        sorted_rows = sorted(group_rows, key=lambda row: (-int(row["count"]), str(row["coarse_tag_english"]), str(row["coarse_tag"])))
        summaries.append(
            {
                "cluster_id": cluster_id,
                "anchor": anchor,
                "rows": sorted_rows,
                "tag_count": len(group_rows),
                "count": group_count,
                "percent": group_percent,
                "weighted_mean_similarity": weighted_mean,
                "top_unigrams": top_unigrams(sorted_rows),
            }
        )
    summaries.sort(key=lambda item: (-item["percent"], str(item["anchor"]["coarse_tag_english"])))

    rank_by_cluster = {summary["cluster_id"]: rank for rank, summary in enumerate(summaries, start=1)}

    with SUMMARY_OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
                "weighted_rank",
                "parent_anchor_tag",
                "parent_anchor_english",
                "tag_count",
                "mention_count",
                "percent_of_total",
                "weighted_mean_similarity_pct",
                "top_unigrams",
                "top_child_tags",
            ]
        )
        for rank, summary in enumerate(summaries, start=1):
            top_children = "; ".join(
                f"{row['coarse_tag']} ({row['percent']:.4f}%)"
                for row in summary["rows"][:40]
            )
            writer.writerow(
                [
                    rank,
                    summary["anchor"]["coarse_tag"],
                    summary["anchor"]["coarse_tag_english"],
                    summary["tag_count"],
                    summary["count"],
                    f"{summary['percent']:.6f}",
                    f"{summary['weighted_mean_similarity'] * 100:.2f}",
                    summary["top_unigrams"],
                    top_children,
                ]
            )

    with TAG_MAP_OUT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
                "coarse_tag",
                "coarse_tag_english",
                "count",
                "percent_of_total",
                "weighted_parent_rank",
                "weighted_parent_anchor",
                "weighted_parent_anchor_english",
                "centroid_similarity_pct",
            ]
        )
        for row in rows:
            if "cluster_id" not in row:
                writer.writerow(
                    [
                        row["coarse_tag"],
                        row["coarse_tag_english"],
                        row["count"],
                        f"{row['percent']:.6f}",
                        "UNVECTORIZED",
                        "UNVECTORIZED",
                        "UNVECTORIZED",
                        "",
                    ]
                )
                continue
            rank = rank_by_cluster[int(row["cluster_id"])]
            summary = summaries[rank - 1]
            writer.writerow(
                [
                    row["coarse_tag"],
                    row["coarse_tag_english"],
                    row["count"],
                    f"{row['percent']:.6f}",
                    rank,
                    summary["anchor"]["coarse_tag"],
                    summary["anchor"]["coarse_tag_english"],
                    f"{float(row['centroid_similarity']) * 100:.2f}",
                ]
            )

    with REPORT_OUT.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("# Full Coarse Tagset Weighted Percent K=25\n\n")
        handle.write(
            "All coarse tags are vectorized with local fastText. Clustering uses `sample_weight = count / total_count`, "
            "so high-frequency tags shape the parent buckets and rare tags attach without dominating the structure.\n\n"
        )
        handle.write(f"- Total mentions: {total_count}\n")
        handle.write(f"- Coarse tags: {len(rows)}\n")
        handle.write(f"- Vectorized tags: {len(vectorized)}\n")
        handle.write(f"- Unvectorized tags: {len(unvectorized)}\n")
        handle.write(f"- Weighted parent buckets: {len(summaries)}\n")
        handle.write(f"- Best random_state: {random_state}\n")
        handle.write("- Attempts weighted mean centroid similarity: " + "; ".join(f"{rs}={score * 100:.2f}%" for score, rs in attempts) + "\n\n")
        handle.write("## Weighted Parent Buckets\n\n")
        for rank, summary in enumerate(summaries, start=1):
            anchor = summary["anchor"]
            handle.write(f"### {rank}. {anchor['coarse_tag']}\n\n")
            handle.write(f"Anchor English: {anchor['coarse_tag_english']}\n\n")
            handle.write(
                f"Coverage: {summary['percent']:.4f}% of mentions; "
                f"{summary['count']} mentions; {summary['tag_count']} coarse tags\n\n"
            )
            handle.write(f"Weighted mean similarity to centroid: {summary['weighted_mean_similarity'] * 100:.2f}%\n\n")
            handle.write(f"Top unigrams: {summary['top_unigrams']}\n\n")
            handle.write("Top child tags by corpus share:\n")
            for row in summary["rows"][:35]:
                handle.write(f"- `{row['coarse_tag']}`: {row['percent']:.4f}% ({row['count']})\n")
            handle.write("\n")

    print(f"total={total_count}")
    print(f"tags={len(rows)}")
    print(f"vectorized={len(vectorized)}")
    print(f"unvectorized={len(unvectorized)}")
    print(f"clusters={len(summaries)}")
    print(f"wrote={SUMMARY_OUT}")
    print(f"tag_map={TAG_MAP_OUT}")
    print(f"report={REPORT_OUT}")


if __name__ == "__main__":
    main()
