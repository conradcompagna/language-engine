import csv
import json
import math
import re
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from sklearn.cluster import MiniBatchKMeans


BASE = Path(__file__).resolve().parent
FULL_TAG_MAP = BASE / "final_full_tag_maps_extracted" / "final_full_tag_maps" / "full_coarse_and_fine_grained_tag_map.tsv"
INVENTORY = BASE / "finerweb_label_inventory.tsv"
FASTTEXT_ZIP = BASE / "embeddings" / "wiki-news-300d-1M.vec.zip"
OUTPUT_DIR = BASE / "derived_fasttext_categories"

TARGET_CATEGORY_COUNT = 50
RANDOM_STATE = 13
TOKEN_RE = re.compile(r"[a-z]+(?:'[a-z]+)?|\d+")
STOPWORDS = {
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
    "da",
    "das",
    "de",
    "del",
    "der",
    "des",
    "di",
    "do",
    "dos",
    "du",
    "el",
    "la",
    "las",
    "le",
    "les",
    "los",
    "van",
    "von",
    "about",
    "related",
    "type",
    "types",
    "category",
    "categories",
    "entity",
    "entities",
    "item",
    "items",
    "misc",
    "other",
    "reference",
    "references",
    "name",
    "names",
}


def norm_text(text):
    text = (text or "").strip().lower()
    text = text.replace("_", " ")
    text = re.sub(r"\s+", " ", text)
    return text


def text_tokens(text):
    return [token for token in TOKEN_RE.findall(norm_text(text)) if len(token) > 1]


def variants(token):
    yielded = {token}
    yield token
    if token.endswith("ies") and len(token) > 4:
        cand = token[:-3] + "y"
        if cand not in yielded:
            yielded.add(cand)
            yield cand
    if token.endswith("es") and len(token) > 3:
        cand = token[:-2]
        if cand not in yielded:
            yielded.add(cand)
            yield cand
    if token.endswith("s") and len(token) > 3:
        cand = token[:-1]
        if cand not in yielded:
            yield cand


def load_counts():
    counts = {}
    with INVENTORY.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            counts[row["original_label"]] = int(row["count"])
    return counts


def load_tags():
    counts = load_counts()
    rows = []
    with FULL_TAG_MAP.open("r", encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f, delimiter="\t"):
            label = row["fine_grained_tag"]
            rows.append(
                {
                    "main_bucket": row["main_bucket"],
                    "coarse_label": row["coarse_label"],
                    "fine_grained_tag": label,
                    "count": counts.get(label, 0),
                    "tokens": text_tokens(label),
                }
            )
    return rows


def collect_needed_words(rows):
    needed = set()
    for row in rows:
        for token in row["tokens"]:
            needed.update(variants(token))
    return needed


def load_needed_fasttext(needed):
    needed_bytes = {word.encode("utf-8") for word in needed}
    vectors = {}
    with zipfile.ZipFile(FASTTEXT_ZIP, "r") as zf:
        vec_name = next(name for name in zf.namelist() if name.endswith(".vec"))
        with zf.open(vec_name, "r") as f:
            f.readline()
            for line in f:
                word, _, rest = line.partition(b" ")
                if word not in needed_bytes:
                    continue
                arr = np.fromstring(rest.decode("ascii"), sep=" ", dtype=np.float32)
                norm = np.linalg.norm(arr)
                if norm:
                    vectors[word.decode("utf-8")] = arr / norm
    return vectors


def get_token_vector(token, vectors):
    for candidate in variants(token):
        vec = vectors.get(candidate)
        if vec is not None:
            return candidate, vec
    return "", None


def row_vector(row, vectors):
    found = []
    matched_tokens = []
    for token in row["tokens"]:
        matched, vec = get_token_vector(token, vectors)
        if vec is not None:
            found.append(vec)
            matched_tokens.append(matched)
    if not found:
        return None, matched_tokens
    vec = np.mean(found, axis=0)
    norm = np.linalg.norm(vec)
    if not norm:
        return None, matched_tokens
    return vec / norm, matched_tokens


def normalized_centers(model):
    centers = model.cluster_centers_.astype(np.float32)
    norms = np.linalg.norm(centers, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return centers / norms


def fit_kmeans(x, k):
    model = MiniBatchKMeans(
        n_clusters=k,
        random_state=RANDOM_STATE,
        batch_size=4096,
        n_init=10,
        max_iter=200,
    )
    labels = model.fit_predict(x)
    centers = normalized_centers(model)
    sims = np.sum(x * centers[labels], axis=1)
    return labels, centers, sims


def summarize_k(x, k):
    labels, centers, sims = fit_kmeans(x, k)
    sizes = Counter(labels)
    return {
        "k": k,
        "mean_centroid_cosine": float(np.mean(sims)),
        "median_centroid_cosine": float(np.median(sims)),
        "p10_centroid_cosine": float(np.percentile(sims, 10)),
        "min_cluster_tags": min(sizes.values()),
        "median_cluster_tags": float(np.median(list(sizes.values()))),
        "max_cluster_tags": max(sizes.values()),
    }


def choose_category_word(cluster_indices, rows, x, center, vectors, used_words):
    token_rows = defaultdict(set)
    token_counts = Counter()
    token_weighted_counts = Counter()
    for pos in cluster_indices:
        row = rows[pos]
        for token in row["tokens"]:
            matched, vec = get_token_vector(token, vectors)
            if vec is None or matched in STOPWORDS:
                continue
            token_rows[matched].add(pos)
            token_counts[matched] += 1
            token_weighted_counts[matched] += max(1, row["count"])

    candidates = []
    for token, positions in token_rows.items():
        vec = vectors[token]
        cosine = float(np.dot(center, vec))
        support = len(positions)
        weighted = token_weighted_counts[token]
        score = cosine + 0.035 * math.log1p(support) + 0.01 * math.log1p(weighted)
        candidates.append((score, cosine, support, weighted, token))
    candidates.sort(reverse=True)

    chosen = ""
    for _, _, _, _, token in candidates:
        if token not in used_words:
            chosen = token
            break
    if not chosen and candidates:
        chosen = candidates[0][4]
    if not chosen:
        nearest_pos = max(cluster_indices, key=lambda pos: float(np.dot(x[pos], center)))
        chosen = rows[nearest_pos]["tokens"][0] if rows[nearest_pos]["tokens"] else "unlabeled"
    used_words.add(chosen)

    top_words = [
        {
            "word": token,
            "score": round(score, 4),
            "cosine": round(cosine, 4),
            "tag_support": support,
            "span_support": weighted,
        }
        for score, cosine, support, weighted, token in candidates[:12]
    ]
    return chosen, top_words


def write_outputs(rows, vector_positions, x, labels, centers, sims, stats, no_vector_rows):
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    pos_to_cluster = {row_pos: int(label) for row_pos, label in zip(vector_positions, labels)}
    pos_to_sim = {row_pos: float(sim) for row_pos, sim in zip(vector_positions, sims)}
    pos_to_x_index = {row_pos: idx for idx, row_pos in enumerate(vector_positions)}
    cluster_to_positions = defaultdict(list)
    for row_pos, label in pos_to_cluster.items():
        cluster_to_positions[label].append(row_pos)

    used_words = set()
    summaries = []
    for cluster, positions in cluster_to_positions.items():
        center = centers[cluster]
        local_x_indices = [pos_to_x_index[pos] for pos in positions]
        nearest_positions = sorted(
            positions,
            key=lambda pos: pos_to_sim[pos],
            reverse=True,
        )[:20]
        frequent_positions = sorted(
            positions,
            key=lambda pos: rows[pos]["count"],
            reverse=True,
        )[:20]
        chosen, top_words = choose_category_word(local_x_indices, [rows[p] for p in vector_positions], x, center, vectors_global, used_words)
        summaries.append(
            {
                "raw_cluster": cluster,
                "category_word": chosen,
                "tag_count": len(positions),
                "span_count": sum(rows[pos]["count"] for pos in positions),
                "mean_centroid_cosine": float(np.mean([pos_to_sim[pos] for pos in positions])),
                "top_words": top_words,
                "nearest_tags": [
                    {
                        "tag": rows[pos]["fine_grained_tag"],
                        "count": rows[pos]["count"],
                        "similarity": round(pos_to_sim[pos], 4),
                    }
                    for pos in nearest_positions
                ],
                "frequent_tags": [
                    {"tag": rows[pos]["fine_grained_tag"], "count": rows[pos]["count"]}
                    for pos in frequent_positions
                ],
            }
        )

    summaries.sort(key=lambda item: (-item["tag_count"], -item["span_count"], item["category_word"]))
    raw_to_category_id = {}
    for idx, summary in enumerate(summaries, start=1):
        category_id = f"C{idx:02d}"
        summary["category_id"] = category_id
        raw_to_category_id[summary["raw_cluster"]] = category_id

    no_vector_category = None
    if no_vector_rows:
        no_vector_category = {
            "category_id": f"C{len(summaries) + 1:02d}",
            "raw_cluster": None,
            "category_word": "unvectorized",
            "tag_count": len(no_vector_rows),
            "span_count": sum(rows[pos]["count"] for pos in no_vector_rows),
            "mean_centroid_cosine": None,
            "top_words": [],
            "nearest_tags": [],
            "frequent_tags": [
                {"tag": rows[pos]["fine_grained_tag"], "count": rows[pos]["count"]}
                for pos in sorted(no_vector_rows, key=lambda pos: rows[pos]["count"], reverse=True)[:20]
            ],
        }
        summaries.append(no_vector_category)

    categories_tsv = OUTPUT_DIR / "fasttext_derived_categories_k50.tsv"
    with categories_tsv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
                "category_id",
                "category_word",
                "tag_count",
                "span_count",
                "mean_centroid_cosine",
                "top_words",
                "nearest_tags",
                "frequent_tags",
            ]
        )
        for summary in summaries:
            writer.writerow(
                [
                    summary["category_id"],
                    summary["category_word"],
                    summary["tag_count"],
                    summary["span_count"],
                    "" if summary["mean_centroid_cosine"] is None else f"{summary['mean_centroid_cosine']:.4f}",
                    ", ".join(word["word"] for word in summary["top_words"][:10]),
                    " | ".join(item["tag"] for item in summary["nearest_tags"][:10]),
                    " | ".join(item["tag"] for item in summary["frequent_tags"][:10]),
                ]
            )

    tag_map_tsv = OUTPUT_DIR / "fasttext_derived_tag_map_k50.tsv"
    with tag_map_tsv.open("w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter="\t", lineterminator="\n")
        writer.writerow(
            [
                "category_id",
                "category_word",
                "fine_grained_tag",
                "count",
                "vector_hits",
                "vector_tokens",
                "similarity",
            ]
        )
        summary_by_id = {summary["category_id"]: summary for summary in summaries}
        no_vector_id = no_vector_category["category_id"] if no_vector_category else ""
        for pos, row in enumerate(rows):
            if pos in pos_to_cluster:
                category_id = raw_to_category_id[pos_to_cluster[pos]]
                similarity = f"{pos_to_sim[pos]:.4f}"
            else:
                category_id = no_vector_id
                similarity = ""
            category_word = summary_by_id[category_id]["category_word"] if category_id else ""
            writer.writerow(
                [
                    category_id,
                    category_word,
                    row["fine_grained_tag"],
                    row["count"],
                    len(row.get("matched_tokens", [])),
                    " ".join(row.get("matched_tokens", [])),
                    similarity,
                ]
            )

    report_md = OUTPUT_DIR / "fasttext_derived_categories_k50.md"
    with report_md.open("w", encoding="utf-8", newline="\n") as f:
        f.write("# FastText-Derived fiNERweb Categories\n\n")
        f.write(f"- Source labels: `{FULL_TAG_MAP.relative_to(BASE)}`\n")
        f.write(f"- Labels total: {len(rows)}\n")
        f.write(f"- Vectorized labels: {len(vector_positions)}\n")
        f.write(f"- Unvectorized labels: {len(no_vector_rows)}\n")
        f.write(f"- Final categories: {len(summaries)}\n\n")
        f.write("## K diagnostics\n\n")
        f.write("| k | mean cosine | median cosine | p10 cosine | min size | median size | max size |\n")
        f.write("|---:|---:|---:|---:|---:|---:|---:|\n")
        for row in stats:
            f.write(
                f"| {row['k']} | {row['mean_centroid_cosine']:.4f} | {row['median_centroid_cosine']:.4f} | "
                f"{row['p10_centroid_cosine']:.4f} | {row['min_cluster_tags']} | "
                f"{row['median_cluster_tags']:.1f} | {row['max_cluster_tags']} |\n"
            )
        f.write("\n## Categories\n\n")
        for summary in summaries:
            f.write(
                f"### {summary['category_id']} `{summary['category_word']}` "
                f"({summary['tag_count']} tags, {summary['span_count']} spans)\n\n"
            )
            if summary["top_words"]:
                f.write("Top words: " + ", ".join(word["word"] for word in summary["top_words"][:12]) + "\n\n")
            if summary["nearest_tags"]:
                f.write("Nearest tags: " + "; ".join(item["tag"] for item in summary["nearest_tags"][:8]) + "\n\n")
            if summary["frequent_tags"]:
                f.write("Frequent tags: " + "; ".join(item["tag"] for item in summary["frequent_tags"][:8]) + "\n\n")

    metadata_json = OUTPUT_DIR / "fasttext_derived_categories_k50.json"
    metadata_json.write_text(
        json.dumps(
            {
                "source": str(FULL_TAG_MAP.relative_to(BASE)),
                "labels_total": len(rows),
                "vectorized_labels": len(vector_positions),
                "unvectorized_labels": len(no_vector_rows),
                "target_category_count": TARGET_CATEGORY_COUNT,
                "k_diagnostics": stats,
                "categories": summaries,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    rows = load_tags()
    needed = collect_needed_words(rows)
    vectors_global = load_needed_fasttext(needed)

    vector_positions = []
    vectors = []
    no_vector_rows = []
    for pos, row in enumerate(rows):
        vec, matched_tokens = row_vector(row, vectors_global)
        row["matched_tokens"] = matched_tokens
        if vec is None:
            no_vector_rows.append(pos)
            continue
        vector_positions.append(pos)
        vectors.append(vec)

    x = np.vstack(vectors).astype(np.float32)
    category_count = TARGET_CATEGORY_COUNT - 1 if no_vector_rows else TARGET_CATEGORY_COUNT
    candidate_ks = [k for k in (20, 30, 40, category_count) if k < len(vector_positions)]
    stats = [summarize_k(x, k) for k in candidate_ks]
    labels, centers, sims = fit_kmeans(x, category_count)
    write_outputs(rows, vector_positions, x, labels, centers, sims, stats, no_vector_rows)
